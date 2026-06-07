"""
Subscription management API endpoints.

These endpoints allow Zenico.app instances to manage their subscriptions,
add/remove seats, toggle AI addon, and access billing portal.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from instances.authentication import ApiKeyAuthentication
from instances.models import Instance, UserLicense
from customers.models import Subscription
from core.services.stripe import (
    StripeService,
    _stripe_get,
    get_stripe,
    get_stripe_subscription_cancel_at,
    get_stripe_subscription_period_end,
)
from core.services.audit import AuditService, AuditAction
from core.services.mail import MailService

logger = logging.getLogger(__name__)


def _get_stripe_subscription(customer):
    """
    Get the active Stripe subscription for a customer.

    Args:
        customer: Customer instance

    Returns:
        stripe.Subscription or None
    """
    subscription = customer.active_subscription
    if not subscription or not subscription.stripe_subscription_id:
        return None

    try:
        stripe_api = get_stripe()
        return stripe_api.Subscription.retrieve(subscription.stripe_subscription_id)
    except Exception as e:
        logger.error(f'Failed to retrieve Stripe subscription for {customer.slug}: {e}')
        return None


def _get_price_per_seat(seats: int) -> Decimal:
    """
    Calculate price per seat based on volume pricing tiers.

    Args:
        seats: Number of user seats

    Returns:
        Decimal: Price per seat in EUR
    """
    if seats <= 3:
        return Decimal('19.00')
    elif seats <= 10:
        return Decimal('15.00')
    else:
        return Decimal('12.00')


def _count_active_users(instance):
    """
    Count active user licenses for an instance.

    Args:
        instance: Instance object

    Returns:
        int: Number of active user licenses
    """
    return UserLicense.objects.filter(
        instance=instance,
        is_active=True
    ).count()


def _create_seats_checkout(instance, additional_seats):
    """
    Create Stripe Checkout session for adding seats.

    Args:
        instance: Instance object
        additional_seats: Number of seats to add

    Returns:
        str: Checkout URL

    Raises:
        Exception: If checkout creation fails
    """
    customer = instance.customer
    subscription = customer.active_subscription

    if not customer.stripe_customer_id:
        raise ValueError('Customer has no Stripe customer ID')

    if not subscription or not subscription.stripe_subscription_id:
        raise ValueError('No active subscription found')

    try:
        stripe_api = get_stripe()

        # Calculate new total seats
        new_total_seats = instance.user_seats + additional_seats
        new_price_per_seat = _get_price_per_seat(new_total_seats)

        # Create checkout session for immediate payment
        # Note: This is a simplified approach. In production, you'd want to
        # update the subscription directly and let Stripe handle proration.
        # For now, we'll update the subscription quantity directly.

        # Get current subscription
        stripe_sub = stripe_api.Subscription.retrieve(subscription.stripe_subscription_id)

        # Find the user seats line item
        user_seat_item = None
        for item in stripe_sub['items']['data']:
            # Identify by price metadata or product
            if 'user' in item['price'].get('nickname', '').lower():
                user_seat_item = item
                break

        if not user_seat_item:
            raise ValueError('Could not find user seats line item in subscription')

        # Update the subscription with new seat count
        updated_sub = stripe_api.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[{
                'id': user_seat_item['id'],
                'quantity': new_total_seats,
            }],
            proration_behavior='always_invoice',
        )

        # Update local instance
        instance.user_seats = new_total_seats
        instance.save(update_fields=['user_seats', 'updated_at'])

        # Update subscription total
        subscription.user_seats_total = new_total_seats
        subscription.save(update_fields=['user_seats_total', 'updated_at'])

        # Log audit
        AuditService.log(
            action=AuditAction.SEATS_CHANGED,
            resource_type='Instance',
            resource_id=str(instance.id),
            customer=customer,
            instance_id=instance.id,
            before={'user_seats': instance.user_seats - additional_seats},
            after={'user_seats': new_total_seats},
            note=f'Added {additional_seats} seats via API',
        )

        # Return success URL (in a real checkout flow, this would be the checkout URL)
        # For now, return a success indicator
        return f'https://{instance.fqdn}/subscription?seats_added={additional_seats}'

    except Exception as e:
        logger.exception(f'Failed to create seats checkout for {instance.fqdn}: {e}')
        raise


def _is_user_seat_line_item(item):
    """Return True if a Stripe subscription line item represents user seats."""
    price = _stripe_get(item, 'price') or {}
    if isinstance(price, str):
        return False
    return 'user' in _stripe_get(price, 'nickname', '').lower()


def _build_schedule_items(subscription_items, user_seat_quantity):
    """Build Stripe schedule phase items with an updated user seat quantity."""
    return [
        {
            'price': item['price']['id'] if isinstance(item['price'], dict) else item['price'],
            'quantity': user_seat_quantity if _is_user_seat_line_item(item) else item['quantity'],
        }
        for item in subscription_items
    ]


def _schedule_phase_items_from_phase(phase_items):
    """Convert schedule phase items into the format expected by SubscriptionSchedule.modify."""
    return [
        {
            'price': item['price'] if isinstance(item['price'], str) else item['price']['id'],
            'quantity': item['quantity'],
        }
        for item in phase_items
    ]


def _get_subscription_schedule_id(stripe_sub):
    """Return the attached subscription schedule ID, if any."""
    schedule = _stripe_get(stripe_sub, 'schedule')
    if not schedule:
        return None
    if isinstance(schedule, str):
        return schedule
    return _stripe_get(schedule, 'id')


def _build_schedule_phases_for_seat_reduction(schedule, stripe_sub, new_seats):
    """
    Build schedule phases for a seat reduction at period end.

    Preserves existing current phases and updates or appends the future phase.
    """
    period_end_ts = get_stripe_subscription_period_end(stripe_sub)
    future_items = _build_schedule_items(stripe_sub['items']['data'], new_seats)

    phases = []
    has_future_phase = False

    for phase in schedule['phases']:
        is_future_phase = phase['start_date'] >= period_end_ts
        phase_dict = {
            'start_date': phase['start_date'],
            'items': (
                future_items
                if is_future_phase
                else _schedule_phase_items_from_phase(phase['items'])
            ),
        }
        if phase.get('end_date'):
            phase_dict['end_date'] = phase['end_date']
        if is_future_phase:
            has_future_phase = True
        phases.append(phase_dict)

    if not has_future_phase:
        phases.append({
            'start_date': period_end_ts,
            'items': future_items,
        })

    return phases


def _schedule_seat_reduction(instance, new_seats):
    """
    Schedule seat reduction to take effect at period end.

    Args:
        instance: Instance object
        new_seats: New seat count (reduced)

    Returns:
        date: Effective date of reduction

    Raises:
        Exception: If scheduling fails
    """
    customer = instance.customer
    subscription = customer.active_subscription

    if not subscription or not subscription.stripe_subscription_id:
        raise ValueError('No active subscription found')

    try:
        stripe_api = get_stripe()

        stripe_sub = stripe_api.Subscription.retrieve(subscription.stripe_subscription_id)
        period_end = date.fromtimestamp(get_stripe_subscription_period_end(stripe_sub))

        schedule_id = _get_subscription_schedule_id(stripe_sub)
        if schedule_id:
            schedule = stripe_api.SubscriptionSchedule.retrieve(schedule_id)
        else:
            schedule = stripe_api.SubscriptionSchedule.create(
                from_subscription=subscription.stripe_subscription_id,
            )
            schedule_id = schedule.id
            schedule = stripe_api.SubscriptionSchedule.retrieve(schedule_id)

        stripe_api.SubscriptionSchedule.modify(
            schedule_id,
            phases=_build_schedule_phases_for_seat_reduction(
                schedule=schedule,
                stripe_sub=stripe_sub,
                new_seats=new_seats,
            ),
        )

        # Log audit
        AuditService.log(
            action='subscription.seats_scheduled_reduction',
            resource_type='Instance',
            resource_id=str(instance.id),
            customer=customer,
            instance_id=instance.id,
            before={'user_seats': instance.user_seats},
            after={'user_seats': new_seats, 'effective_date': period_end.isoformat()},
            note=f'Scheduled seat reduction from {instance.user_seats} to {new_seats} effective {period_end}',
        )

        return period_end

    except Exception as e:
        logger.exception(f'Failed to schedule seat reduction for {instance.fqdn}: {e}')
        raise


def _create_ai_addon_checkout(instance):
    """
    Create Stripe Checkout session for AI addon.

    Args:
        instance: Instance object

    Returns:
        str: Checkout URL

    Raises:
        Exception: If checkout creation fails
    """
    customer = instance.customer
    subscription = customer.active_subscription

    if not subscription or not subscription.stripe_subscription_id:
        raise ValueError('No active subscription found')

    try:
        # Use existing toggle_ai_addon method from StripeService
        StripeService.toggle_ai_addon(subscription, active=True)

        # Update local records
        subscription.ai_addon_active = True
        subscription.save(update_fields=['ai_addon_active', 'updated_at'])

        instance.ai_addon_active = True
        instance.save(update_fields=['ai_addon_active', 'updated_at'])

        # Return success URL
        return f'https://{instance.fqdn}/subscription?ai_addon=added'

    except Exception as e:
        logger.exception(f'Failed to create AI addon checkout for {instance.fqdn}: {e}')
        raise


def _cancel_stripe_subscription(instance):
    """
    Cancel Stripe subscription at period end.

    Args:
        instance: Instance object

    Returns:
        date: Cancellation effective date (period end)

    Raises:
        Exception: If cancellation fails
    """
    customer = instance.customer
    subscription = customer.active_subscription

    if not subscription or not subscription.stripe_subscription_id:
        raise ValueError('No active subscription found')

    try:
        # Cancel subscription at period end
        cancelled_sub = StripeService.cancel_subscription(subscription, at_period_end=True)

        # Use Stripe's resolved cancel_at, not max item period end.
        period_end = date.fromtimestamp(get_stripe_subscription_cancel_at(cancelled_sub))

        # Update subscription
        subscription.cancelled_at = timezone.make_aware(
            timezone.datetime.combine(period_end, timezone.datetime.min.time())
        )
        subscription.save(update_fields=['cancelled_at', 'updated_at'])

        return period_end

    except Exception as e:
        logger.exception(f'Failed to cancel subscription for {instance.fqdn}: {e}')
        raise


def _send_cancellation_confirmation(instance, cancelled_at):
    """
    Send cancellation confirmation email to customer.

    Args:
        instance: Instance object
        cancelled_at: Date when subscription ends
    """
    customer = instance.customer

    try:
        MailService.send_template(
            to=customer.billing_email,
            subject='Zenico Subscription Cancellation Confirmed',
            template_name='mail/cancellation_confirmation',
            context={
                'customer': customer,
                'instance': instance,
                'cancelled_at': cancelled_at,
            }
        )
    except Exception as e:
        logger.error(f'Failed to send cancellation confirmation to {customer.billing_email}: {e}')


def _notify_admin_cancellation(instance, reason_category, reason_text, missing_feature):
    """
    Notify admin team of cancellation.

    Args:
        instance: Instance object
        reason_category: Cancellation reason category
        reason_text: Free text reason
        missing_feature: Missing feature (if applicable)
    """
    customer = instance.customer

    try:
        # Send email to admin team
        admin_email = 'admin@zenico.app'  # Configure in settings

        MailService.send_template(
            to=admin_email,
            subject=f'Cancellation: {customer.company_name} ({customer.slug})',
            template_name='mail/admin_cancellation_notification',
            context={
                'customer': customer,
                'instance': instance,
                'reason_category': reason_category,
                'reason_text': reason_text,
                'missing_feature': missing_feature,
            }
        )
    except Exception as e:
        logger.error(f'Failed to notify admin of cancellation for {customer.slug}: {e}')


def _create_billing_portal_url(instance):
    """
    Generate Stripe Billing Portal URL.

    Args:
        instance: Instance object

    Returns:
        str: Billing portal URL

    Raises:
        Exception: If URL generation fails
    """
    customer = instance.customer
    return_url = f'https://{instance.fqdn}/subscription'

    try:
        return StripeService.create_billing_portal_session(customer, return_url)
    except Exception as e:
        logger.exception(f'Failed to create billing portal URL for {instance.fqdn}: {e}')
        raise


def _get_period_end(instance):
    """
    Get the current billing period end date.

    Args:
        instance: Instance object

    Returns:
        datetime or None: Period end datetime
    """
    subscription = instance.customer.active_subscription
    if subscription and subscription.current_period_end:
        return subscription.current_period_end
    return None


class SubscriptionView(APIView):
    """
    GET /api/instance/subscription/

    Returns current subscription details for the authenticated instance.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        instance = request.user
        customer = instance.customer

        # Get Stripe subscription
        stripe_sub = _get_stripe_subscription(customer)

        # Count active users
        active_users = _count_active_users(instance)

        # Calculate price per seat
        price_per_seat = _get_price_per_seat(instance.user_seats)

        # Get period end
        period_end = _get_period_end(instance)

        return Response({
            'user_seats': instance.user_seats,
            'user_seats_used': active_users,
            'price_per_seat': float(price_per_seat),
            'ai_addon': instance.ai_addon_active,
            'ai_weekly_limit': 200000 if instance.ai_addon_active else 0,
            'billing_period_end': period_end.isoformat() if period_end else None,
            'cancelled_at': instance.cancelled_at.isoformat() if instance.cancelled_at else None,
            'cancelled_reason': instance.cancelled_reason or None,
            'coupon_code': customer.coupon_code or None,
            'coupon_description': customer.coupon_description or None,
            'coupon_discount': float(customer.coupon_discount_pct) if customer.coupon_discount_pct else None,
        })


class AddSeatsView(APIView):
    """
    POST /api/instance/subscription/add-seats/

    Add additional user seats to the subscription.
    Creates Stripe checkout for immediate payment (with proration).
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        instance = request.user
        seats = int(request.data.get('seats', 0))

        if seats < 1:
            return Response(
                {'error': 'At least 1 seat required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            checkout_url = _create_seats_checkout(
                instance=instance,
                additional_seats=seats,
            )
            return Response({'checkout_url': checkout_url})
        except Exception as e:
            logger.exception(f'Failed to add seats for {instance.fqdn}: {e}')
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RemoveSeatsView(APIView):
    """
    POST /api/instance/subscription/remove-seats/

    Reduce user seats (effective at period end).
    Does not take effect immediately - allows customer to deactivate users first.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        instance = request.user
        reduce_by = int(request.data.get('seats', 0))
        current_seats = instance.user_seats
        new_seats = current_seats - reduce_by

        if new_seats < 1:
            return Response(
                {'error': f'At least 1 seat required. Current: {current_seats} seats.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            effective_date = _schedule_seat_reduction(
                instance=instance,
                new_seats=new_seats,
            )
            return Response({
                'success': True,
                'new_seats': new_seats,
                'effective_date': effective_date.isoformat(),
            })
        except Exception as e:
            logger.exception(f'Failed to remove seats for {instance.fqdn}: {e}')
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AddAIAddonView(APIView):
    """
    POST /api/instance/subscription/add-ai-addon/

    Add AI addon to subscription (€7.50/month).
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        instance = request.user

        if instance.ai_addon_active:
            return Response(
                {'error': 'AI addon already active.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            checkout_url = _create_ai_addon_checkout(instance)
            return Response({'checkout_url': checkout_url})
        except Exception as e:
            logger.exception(f'Failed to add AI addon for {instance.fqdn}: {e}')
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CancelSubscriptionView(APIView):
    """
    POST /api/instance/subscription/cancel/

    Cancel subscription at period end.
    Collects cancellation reason and notifies customer and admin.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        instance = request.user
        reason_category = request.data.get('reason_category', 'other')
        reason_text = request.data.get('reason_text', '')
        missing_feature = request.data.get('missing_feature', '')

        # Validate reason category
        valid_reasons = ['missing_feature', 'too_expensive', 'not_needed', 'switching', 'other']
        if reason_category not in valid_reasons:
            return Response(
                {'error': f'Invalid reason. Valid options: {valid_reasons}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Cancel subscription in Stripe
            cancelled_at = _cancel_stripe_subscription(instance)

            # Update instance
            instance.cancelled_at = cancelled_at
            instance.cancelled_reason = reason_category
            instance.cancelled_reason_text = reason_text
            instance.cancelled_missing_feature = missing_feature
            instance.save(update_fields=[
                'cancelled_at', 'cancelled_reason', 'cancelled_reason_text',
                'cancelled_missing_feature', 'updated_at'
            ])

            # Send confirmation email
            _send_cancellation_confirmation(instance, cancelled_at)

            # Notify admin
            _notify_admin_cancellation(instance, reason_category, reason_text, missing_feature)

            return Response({
                'success': True,
                'cancelled_at': cancelled_at.isoformat(),
            })
        except Exception as e:
            logger.exception(f'Failed to cancel subscription for {instance.fqdn}: {e}')
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BillingPortalView(APIView):
    """
    GET /api/instance/subscription/portal-url/

    Generate Stripe Billing Portal URL for invoices and payment methods.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        instance = request.user

        try:
            url = _create_billing_portal_url(instance)
            return Response({'url': url})
        except Exception as e:
            logger.exception(f'Failed to generate billing portal URL for {instance.fqdn}: {e}')
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
