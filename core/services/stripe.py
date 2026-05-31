"""
StripeService - Wrapper around Stripe SDK.

Centralizes all Stripe API operations and logs them via AuditService.
Handles customer creation, subscription management, and invoice synchronization.
"""

import logging
import os
from typing import Optional
from decimal import Decimal

import stripe
from django.conf import settings

from customers.models import Customer, Subscription
from billing.models import Invoice
from core.services.audit import AuditService, AuditAction

logger = logging.getLogger(__name__)


def get_stripe():
    """
    Get configured Stripe client using StripeConfig from database.

    Returns:
        stripe: Configured Stripe module with API key set
    """
    from billing.models import StripeConfig

    config = StripeConfig.get()
    stripe.api_key = config.active_secret_key

    if not stripe.api_key:
        # Fallback to environment variable for initial setup
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
        logger.warning('Using STRIPE_SECRET_KEY from environment (StripeConfig not configured)')

    return stripe


class StripeService:
    """
    Service for interacting with Stripe API.

    Configuration (environment variables):
        STRIPE_SECRET_KEY: Stripe secret key (sk_live_... or sk_test_...)
        STRIPE_WEBHOOK_SECRET: Stripe webhook signing secret (whsec_...)
        STRIPE_TAX_ENABLED: Whether to enable automatic tax calculation (default: true)
    """

    @staticmethod
    def create_customer(customer: Customer) -> str:
        """
        Create a Stripe customer and link it to the local Customer.

        Args:
            customer: Local Customer instance

        Returns:
            str: Stripe customer ID

        Side effects:
            - Updates customer.stripe_customer_id
            - Saves customer
            - Creates audit log entry
        """
        try:
            stripe_api = get_stripe()
            # Create Stripe customer
            stripe_customer = stripe_api.Customer.create(
                name=customer.company_name,
                email=customer.billing_email,
                metadata={
                    'customer_slug': customer.slug,
                    'customer_id': str(customer.id),
                },
            )

            # Update local customer
            customer.stripe_customer_id = stripe_customer.id
            customer.save()

            # Log action
            AuditService.log(
                action='stripe.customer_created',
                resource_type='StripeCustomer',
                resource_id=stripe_customer.id,
                customer=customer,
                after={
                    'stripe_customer_id': stripe_customer.id,
                    'company_name': customer.company_name,
                    'billing_email': customer.billing_email,
                },
                note=f'Stripe customer created for {customer.company_name}',
            )

            logger.info(f'Created Stripe customer {stripe_customer.id} for {customer.slug}')
            return stripe_customer.id

        except Exception as e:
            logger.exception(f'Failed to create Stripe customer for {customer.slug}: {e}')
            AuditService.log(
                action='stripe.customer_creation_failed',
                resource_type='StripeCustomer',
                resource_id=str(customer.id),
                customer=customer,
                after={'error': str(e)},
                note=f'Failed to create Stripe customer: {str(e)}',
            )
            raise

    @staticmethod
    def update_customer(customer: Customer) -> None:
        """
        Synchronize customer data to Stripe.

        Args:
            customer: Local Customer instance

        Side effects:
            - Updates Stripe customer
            - Creates audit log entry
        """
        if not customer.stripe_customer_id:
            raise ValueError(f'Customer {customer.slug} has no Stripe customer ID')

        try:
            stripe_api = get_stripe()
            # Update Stripe customer
            stripe_api.Customer.modify(
                customer.stripe_customer_id,
                name=customer.company_name,
                email=customer.billing_email,
            )

            # Log action
            AuditService.log(
                action='stripe.customer_updated',
                resource_type='StripeCustomer',
                resource_id=customer.stripe_customer_id,
                customer=customer,
                after={
                    'company_name': customer.company_name,
                    'billing_email': customer.billing_email,
                },
                note=f'Stripe customer updated for {customer.company_name}',
            )

            logger.info(f'Updated Stripe customer {customer.stripe_customer_id} for {customer.slug}')

        except Exception as e:
            logger.exception(f'Failed to update Stripe customer {customer.stripe_customer_id}: {e}')
            AuditService.log(
                action='stripe.customer_update_failed',
                resource_type='StripeCustomer',
                resource_id=customer.stripe_customer_id,
                customer=customer,
                after={'error': str(e)},
                note=f'Failed to update Stripe customer: {str(e)}',
            )
            raise

    @staticmethod
    def create_subscription(
        customer: Customer,
        plan,  # Plan object
        user_seats: int,
        instance_seats: int,
        ai_addon: bool = False,
        trial_days: int = 0,
    ) -> stripe.Subscription:
        """
        Create a Stripe subscription with multiple line items.

        Args:
            customer: Local Customer instance
            plan: Plan instance with Stripe price IDs
            user_seats: Number of user licenses
            instance_seats: Number of instance slots
            ai_addon: Whether to include AI addon (default: False)
            trial_days: Trial period in days (default: 0)

        Returns:
            stripe.Subscription: The created Stripe subscription

        Side effects:
            - Creates Stripe subscription
            - Creates audit log entry
        """
        if not customer.stripe_customer_id:
            raise ValueError(f'Customer {customer.slug} has no Stripe customer ID')

        try:
            # Build line items
            items = []

            if plan.stripe_price_id_user:
                items.append({
                    'price': plan.stripe_price_id_user,
                    'quantity': user_seats,
                })

            if plan.stripe_price_id_instance:
                items.append({
                    'price': plan.stripe_price_id_instance,
                    'quantity': instance_seats,
                })

            if ai_addon and plan.stripe_price_id_ai:
                items.append({
                    'price': plan.stripe_price_id_ai,
                    'quantity': 1,
                })

            # Create subscription
            subscription_params = {
                'customer': customer.stripe_customer_id,
                'items': items,
                'metadata': {
                    'customer_slug': customer.slug,
                    'customer_id': str(customer.id),
                    'plan_name': plan.name,
                },
            }

            # Add automatic tax if enabled
            if os.getenv('STRIPE_TAX_ENABLED', 'true').lower() == 'true':
                subscription_params['automatic_tax'] = {'enabled': True}

            # Add trial period if specified
            if trial_days > 0:
                subscription_params['trial_period_days'] = trial_days

            stripe_subscription = stripe.Subscription.create(**subscription_params)

            # Log action
            AuditService.log(
                action=AuditAction.SUBSCRIPTION_CREATED,
                resource_type='StripeSubscription',
                resource_id=stripe_subscription.id,
                customer=customer,
                after={
                    'stripe_subscription_id': stripe_subscription.id,
                    'plan': plan.name,
                    'user_seats': user_seats,
                    'instance_seats': instance_seats,
                    'ai_addon': ai_addon,
                    'trial_days': trial_days,
                },
                note=f'Stripe subscription created for {customer.company_name}',
            )

            logger.info(f'Created Stripe subscription {stripe_subscription.id} for {customer.slug}')
            return stripe_subscription

        except Exception as e:
            logger.exception(f'Failed to create Stripe subscription for {customer.slug}: {e}')
            AuditService.log(
                action='stripe.subscription_creation_failed',
                resource_type='StripeSubscription',
                resource_id=str(customer.id),
                customer=customer,
                after={'error': str(e)},
                note=f'Failed to create Stripe subscription: {str(e)}',
            )
            raise

    @staticmethod
    def update_seats(
        subscription: Subscription,
        user_seats: Optional[int] = None,
        instance_seats: Optional[int] = None,
    ) -> stripe.Subscription:
        """
        Update seat quantities on a Stripe subscription.

        Args:
            subscription: Local Subscription instance
            user_seats: New user seat count (optional)
            instance_seats: New instance seat count (optional)

        Returns:
            stripe.Subscription: The updated Stripe subscription

        Side effects:
            - Updates Stripe subscription line items
            - Creates audit log entry
            - Proration is automatic
        """
        if not subscription.stripe_subscription_id:
            raise ValueError('Subscription has no Stripe subscription ID')

        try:
            stripe_api = get_stripe()
            # Retrieve current subscription
            stripe_subscription = stripe.Subscription.retrieve(subscription.stripe_subscription_id)

            # Update line items
            items_to_update = []

            for item in stripe_subscription['items']['data']:
                price_id = item['price']['id']
                current_quantity = item['quantity']
                new_quantity = current_quantity

                # Match price ID to determine which line item to update
                if user_seats is not None and price_id == subscription.plan.stripe_price_id_user:
                    new_quantity = user_seats
                elif instance_seats is not None and price_id == subscription.plan.stripe_price_id_instance:
                    new_quantity = instance_seats

                if new_quantity != current_quantity:
                    items_to_update.append({
                        'id': item['id'],
                        'quantity': new_quantity,
                    })

            if not items_to_update:
                logger.info('No seat changes needed for subscription {subscription.stripe_subscription_id}')
                return stripe_subscription

            # Update subscription
            updated_subscription = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                items=items_to_update,
                proration_behavior='always_invoice',  # Prorate and invoice immediately
            )

            # Log action
            AuditService.log(
                action=AuditAction.SEATS_CHANGED,
                resource_type='StripeSubscription',
                resource_id=subscription.stripe_subscription_id,
                customer=subscription.customer,
                before={
                    'user_seats': subscription.user_seats_total,
                    'instance_seats': subscription.instance_seats_total,
                },
                after={
                    'user_seats': user_seats or subscription.user_seats_total,
                    'instance_seats': instance_seats or subscription.instance_seats_total,
                },
                note=f'Seat counts updated for {subscription.customer.company_name}',
            )

            logger.info(f'Updated seats for subscription {subscription.stripe_subscription_id}')
            return updated_subscription

        except Exception as e:
            logger.exception(f'Failed to update seats for subscription {subscription.stripe_subscription_id}: {e}')
            AuditService.log(
                action='stripe.subscription_update_failed',
                resource_type='StripeSubscription',
                resource_id=subscription.stripe_subscription_id,
                customer=subscription.customer,
                after={'error': str(e)},
                note=f'Failed to update subscription seats: {str(e)}',
            )
            raise

    @staticmethod
    def toggle_ai_addon(
        subscription: Subscription,
        active: bool,
    ) -> stripe.Subscription:
        """
        Add or remove AI addon from subscription.

        Args:
            subscription: Local Subscription instance
            active: True to add addon, False to remove

        Returns:
            stripe.Subscription: The updated Stripe subscription

        Side effects:
            - Updates Stripe subscription line items
            - Creates audit log entry
        """
        if not subscription.stripe_subscription_id:
            raise ValueError('Subscription has no Stripe subscription ID')

        try:
            stripe_api = get_stripe()
            # Retrieve current subscription
            stripe_subscription = stripe.Subscription.retrieve(subscription.stripe_subscription_id)

            # Find AI addon line item
            ai_item_id = None
            for item in stripe_subscription['items']['data']:
                if item['price']['id'] == subscription.plan.stripe_price_id_ai:
                    ai_item_id = item['id']
                    break

            if active and not ai_item_id:
                # Add AI addon
                stripe.SubscriptionItem.create(
                    subscription=subscription.stripe_subscription_id,
                    price=subscription.plan.stripe_price_id_ai,
                    quantity=1,
                )
                action_note = 'AI addon added'
            elif not active and ai_item_id:
                # Remove AI addon
                stripe.SubscriptionItem.delete(ai_item_id)
                action_note = 'AI addon removed'
            else:
                # No change needed
                logger.info(f'AI addon already {"active" if active else "inactive"} for {subscription.stripe_subscription_id}')
                return stripe_subscription

            # Retrieve updated subscription
            updated_subscription = stripe.Subscription.retrieve(subscription.stripe_subscription_id)

            # Log action
            AuditService.log(
                action='stripe.addon_toggled',
                resource_type='StripeSubscription',
                resource_id=subscription.stripe_subscription_id,
                customer=subscription.customer,
                after={
                    'ai_addon_active': active,
                },
                note=f'{action_note} for {subscription.customer.company_name}',
            )

            logger.info(f'{action_note} for subscription {subscription.stripe_subscription_id}')
            return updated_subscription

        except Exception as e:
            logger.exception(f'Failed to toggle AI addon for {subscription.stripe_subscription_id}: {e}')
            AuditService.log(
                action='stripe.addon_toggle_failed',
                resource_type='StripeSubscription',
                resource_id=subscription.stripe_subscription_id,
                customer=subscription.customer,
                after={'error': str(e)},
                note=f'Failed to toggle AI addon: {str(e)}',
            )
            raise

    @staticmethod
    def cancel_subscription(
        subscription: Subscription,
        at_period_end: bool = True,
    ) -> stripe.Subscription:
        """
        Cancel a Stripe subscription.

        Args:
            subscription: Local Subscription instance
            at_period_end: If True, cancel at period end; if False, cancel immediately

        Returns:
            stripe.Subscription: The cancelled Stripe subscription

        Side effects:
            - Cancels Stripe subscription
            - Creates audit log entry
        """
        if not subscription.stripe_subscription_id:
            raise ValueError('Subscription has no Stripe subscription ID')

        try:
            stripe_api = get_stripe()
            if at_period_end:
                # Cancel at period end
                cancelled_subscription = stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True,
                )
            else:
                # Cancel immediately
                cancelled_subscription = stripe.Subscription.delete(
                    subscription.stripe_subscription_id,
                )

            # Log action
            AuditService.log(
                action=AuditAction.SUBSCRIPTION_CANCELLED,
                resource_type='StripeSubscription',
                resource_id=subscription.stripe_subscription_id,
                customer=subscription.customer,
                after={
                    'at_period_end': at_period_end,
                    'status': cancelled_subscription.status,
                },
                note=f'Subscription cancelled {"at period end" if at_period_end else "immediately"} for {subscription.customer.company_name}',
            )

            logger.info(f'Cancelled subscription {subscription.stripe_subscription_id} (at_period_end={at_period_end})')
            return cancelled_subscription

        except Exception as e:
            logger.exception(f'Failed to cancel subscription {subscription.stripe_subscription_id}: {e}')
            AuditService.log(
                action='stripe.subscription_cancellation_failed',
                resource_type='StripeSubscription',
                resource_id=subscription.stripe_subscription_id,
                customer=subscription.customer,
                after={'error': str(e)},
                note=f'Failed to cancel subscription: {str(e)}',
            )
            raise

    @staticmethod
    def sync_invoice(stripe_invoice: dict, customer: Customer) -> Invoice:
        """
        Create or update local Invoice from Stripe invoice data.

        Args:
            stripe_invoice: Stripe invoice dict from webhook or API
            customer: Local Customer instance

        Returns:
            Invoice: The created or updated Invoice instance

        Side effects:
            - Creates or updates Invoice
            - Creates audit log entry
        """
        try:
            # Find subscription if linked
            subscription = None
            if stripe_invoice.get('subscription'):
                subscription = Subscription.objects.filter(
                    stripe_subscription_id=stripe_invoice['subscription']
                ).first()

            # Convert amounts from cents to decimal
            amount_due = Decimal(stripe_invoice['amount_due']) / 100
            amount_paid = Decimal(stripe_invoice['amount_paid']) / 100

            # Create or update invoice
            invoice, created = Invoice.objects.update_or_create(
                stripe_invoice_id=stripe_invoice['id'],
                defaults={
                    'customer': customer,
                    'subscription': subscription,
                    'stripe_hosted_url': stripe_invoice.get('hosted_invoice_url', ''),
                    'stripe_pdf_url': stripe_invoice.get('invoice_pdf', ''),
                    'amount_due': amount_due,
                    'amount_paid': amount_paid,
                    'currency': stripe_invoice['currency'].upper(),
                    'status': stripe_invoice['status'],
                    'period_start': None,  # Would need to parse from lines
                    'period_end': None,  # Would need to parse from lines
                    'due_date': None,  # Would parse from due_date field
                },
            )

            # Log action
            AuditService.log(
                action='stripe.invoice_synced',
                resource_type='Invoice',
                resource_id=stripe_invoice['id'],
                customer=customer,
                after={
                    'invoice_id': stripe_invoice['id'],
                    'status': stripe_invoice['status'],
                    'amount_due': float(amount_due),
                    'created': created,
                },
                note=f'Invoice {"created" if created else "updated"} from Stripe for {customer.company_name}',
            )

            logger.info(f'{"Created" if created else "Updated"} invoice {stripe_invoice["id"]} for {customer.slug}')
            return invoice

        except Exception as e:
            logger.exception(f'Failed to sync invoice {stripe_invoice.get("id", "unknown")}: {e}')
            AuditService.log(
                action='stripe.invoice_sync_failed',
                resource_type='Invoice',
                resource_id=stripe_invoice.get('id', 'unknown'),
                customer=customer,
                after={'error': str(e)},
                note=f'Failed to sync invoice: {str(e)}',
            )
            raise

    @staticmethod
    def create_billing_portal_session(customer: Customer, return_url: str) -> str:
        """
        Create a Stripe Billing Portal session for customer self-service.

        Args:
            customer: Local Customer instance
            return_url: URL to return to after portal session

        Returns:
            str: Billing Portal URL

        Side effects:
            - Creates Stripe Billing Portal session
            - Creates audit log entry
        """
        if not customer.stripe_customer_id:
            raise ValueError(f'Customer {customer.slug} has no Stripe customer ID')

        try:
            stripe_api = get_stripe()
            # Create portal session
            session = stripe_api.billing_portal.Session.create(
                customer=customer.stripe_customer_id,
                return_url=return_url,
            )

            # Log action
            AuditService.log(
                action='stripe.portal_session_created',
                resource_type='BillingPortalSession',
                resource_id=session.id,
                customer=customer,
                after={
                    'session_id': session.id,
                    'return_url': return_url,
                },
                note=f'Billing portal session created for {customer.company_name}',
            )

            logger.info(f'Created billing portal session for {customer.slug}')
            return session.url

        except Exception as e:
            logger.exception(f'Failed to create billing portal session for {customer.slug}: {e}')
            AuditService.log(
                action='stripe.portal_session_failed',
                resource_type='BillingPortalSession',
                resource_id=str(customer.id),
                customer=customer,
                after={'error': str(e)},
                note=f'Failed to create billing portal session: {str(e)}',
            )
            raise
