"""
CouponService - Manages coupon creation, validation, and application to subscriptions.

Integrates with Stripe to create coupons and promotion codes, applies discounts to subscriptions,
and tracks redemptions with proper audit logging.
"""

import logging
from typing import Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

import stripe

from billing.models import Coupon, CouponRedemption
from customers.models import Customer, Subscription
from core.services.audit import AuditService
from core.services.stripe import get_stripe

logger = logging.getLogger(__name__)


class CouponService:
    """
    Service for managing coupons and their application to subscriptions.
    Handles Stripe coupon and promotion code creation, validation, and redemption tracking.
    """

    @staticmethod
    def create_stripe_coupon(coupon: Coupon) -> tuple[str, str]:
        """
        Create Stripe coupon and promotion code for the given Coupon instance.

        Args:
            coupon: Local Coupon instance

        Returns:
            tuple: (stripe_coupon_id, stripe_promotion_code_id)

        Side effects:
            - Creates Stripe Coupon
            - Creates Stripe Promotion Code
            - Updates coupon.stripe_coupon_id and coupon.stripe_promotion_code_id
            - Saves coupon
            - Creates audit log entry

        Raises:
            Exception: If Stripe API call fails
        """
        try:
            # Initialize Stripe API with configured key
            get_stripe()

            # Prepare coupon parameters
            coupon_params = {
                'name': coupon.name,
                'metadata': {
                    'coupon_id': str(coupon.id),
                    'code': coupon.code,
                },
            }

            # Set discount type
            if coupon.type == 'percent':
                coupon_params['percent_off'] = float(coupon.discount_percent)
            else:  # fixed
                # Stripe expects amount in cents
                coupon_params['amount_off'] = int(coupon.discount_amount * 100)
                coupon_params['currency'] = 'eur'

            # Set duration
            if coupon.duration == 'forever':
                coupon_params['duration'] = 'forever'
            else:  # repeating
                coupon_params['duration'] = 'repeating'
                coupon_params['duration_in_months'] = coupon.duration_in_months

            # Set redemption limit if specified
            if coupon.max_redemptions is not None:
                coupon_params['max_redemptions'] = coupon.max_redemptions

            # Create Stripe coupon
            stripe_coupon = stripe.Coupon.create(**coupon_params)

            # Prepare promotion code parameters
            # Note: Stripe API requires coupon to be nested under promotion parameter
            promo_params = {
                'promotion': {
                    'type': 'coupon',
                    'coupon': stripe_coupon.id,
                },
                'code': coupon.code,
                'metadata': {
                    'coupon_id': str(coupon.id),
                },
            }

            # Set expiration time if valid_until is set
            if coupon.valid_until:
                # Stripe expects Unix timestamp
                promo_params['expires_at'] = int(coupon.valid_until.timestamp())

            if coupon.max_redemptions is not None:
                promo_params['max_redemptions'] = coupon.max_redemptions

            # Create Stripe promotion code
            stripe_promo = stripe.PromotionCode.create(**promo_params)

            # Update local coupon
            coupon.stripe_coupon_id = stripe_coupon.id
            coupon.stripe_promotion_code_id = stripe_promo.id
            coupon.save()

            # Log action
            AuditService.log(
                action='coupon.created_in_stripe',
                resource_type='Coupon',
                resource_id=str(coupon.id),
                after={
                    'code': coupon.code,
                    'stripe_coupon_id': stripe_coupon.id,
                    'stripe_promotion_code_id': stripe_promo.id,
                    'type': coupon.type,
                    'discount': coupon.discount_display,
                    'duration': coupon.duration,
                },
                note=f'Stripe coupon and promotion code created for {coupon.code}',
            )

            logger.info(f'Created Stripe coupon {stripe_coupon.id} and promo code {stripe_promo.id} for {coupon.code}')
            return stripe_coupon.id, stripe_promo.id

        except Exception as e:
            logger.exception(f'Failed to create Stripe coupon for {coupon.code}: {e}')
            AuditService.log(
                action='coupon.stripe_creation_failed',
                resource_type='Coupon',
                resource_id=str(coupon.id),
                after={'error': str(e)},
                note=f'Failed to create Stripe coupon: {str(e)}',
            )
            raise

    @staticmethod
    @transaction.atomic
    def apply_to_subscription(
        coupon: Coupon,
        subscription: Subscription,
        customer: Customer,
    ) -> CouponRedemption:
        """
        Apply coupon to a subscription with full validation.

        Args:
            coupon: Coupon to apply
            subscription: Target subscription
            customer: Customer redeeming the coupon

        Returns:
            CouponRedemption: The created redemption record

        Side effects:
            - Applies discount to Stripe subscription
            - Creates CouponRedemption record
            - Increments coupon.redemptions_count
            - Updates subscription.coupon
            - Creates audit log entry

        Raises:
            ValidationError: If coupon is invalid or already redeemed
            Exception: If Stripe API call fails
        """
        from django.core.exceptions import ValidationError

        # 1. Validate coupon is valid
        if not coupon.is_valid:
            reasons = []
            if not coupon.is_active:
                reasons.append('Der Code ist deaktiviert')
            elif coupon.valid_from and timezone.now() < coupon.valid_from:
                reasons.append('Der Code ist noch nicht gültig')
            elif coupon.valid_until and timezone.now() > coupon.valid_until:
                reasons.append('Der Code ist abgelaufen')
            elif coupon.max_redemptions is not None and coupon.redemptions_count >= coupon.max_redemptions:
                reasons.append('Der Code wurde bereits zu oft eingelöst')

            raise ValidationError('. '.join(reasons))

        # 2. Check for duplicate redemption (this will be caught by unique constraint anyway)
        existing = CouponRedemption.objects.filter(
            coupon=coupon,
            customer=customer
        ).first()

        if existing:
            raise ValidationError(f'Der Code {coupon.code} wurde bereits von diesem Kunden eingelöst')

        # 3. Apply to Stripe subscription
        try:
            # Initialize Stripe API with configured key
            get_stripe()

            # Apply promotion code to Stripe subscription
            stripe_subscription = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                promotion_code=coupon.stripe_promotion_code_id,
            )

            # Extract discount ID from Stripe response
            discount_id = ''
            if stripe_subscription.get('discount'):
                discount_id = stripe_subscription['discount'].get('id', '')

        except Exception as e:
            logger.exception(f'Failed to apply coupon {coupon.code} to subscription {subscription.stripe_subscription_id}: {e}')
            raise ValidationError(f'Fehler beim Anwenden des Codes: {str(e)}')

        # 4. Create redemption record
        redemption = CouponRedemption.objects.create(
            coupon=coupon,
            customer=customer,
            subscription=subscription,
            stripe_discount_id=discount_id,
        )

        # 5. Increment redemptions count
        coupon.redemptions_count += 1
        coupon.save()

        # 6. Update subscription coupon reference
        subscription.coupon = coupon
        subscription.save()

        # 7. Log action
        AuditService.log(
            action='coupon.redeemed',
            resource_type='CouponRedemption',
            resource_id=str(redemption.id),
            customer=customer,
            after={
                'coupon_code': coupon.code,
                'customer': customer.company_name,
                'subscription_id': str(subscription.id),
                'discount': coupon.discount_display,
                'duration': coupon.duration_display,
            },
            note=f'Coupon {coupon.code} redeemed by {customer.company_name}',
        )

        logger.info(f'Applied coupon {coupon.code} to subscription {subscription.stripe_subscription_id}')
        return redemption

    @staticmethod
    @transaction.atomic
    def remove_from_subscription(subscription: Subscription) -> None:
        """
        Remove discount from a subscription.

        Args:
            subscription: Subscription to remove discount from

        Side effects:
            - Removes discount from Stripe subscription
            - Sets subscription.coupon to None
            - Creates audit log entry

        Raises:
            Exception: If Stripe API call fails
        """
        if not subscription.coupon:
            logger.info(f'Subscription {subscription.stripe_subscription_id} has no coupon to remove')
            return

        coupon_code = subscription.coupon.code

        try:
            # Initialize Stripe API with configured key
            get_stripe()

            # Remove discount from Stripe subscription
            stripe.Subscription.delete_discount(subscription.stripe_subscription_id)

            # Update local subscription
            subscription.coupon = None
            subscription.save()

            # Log action
            AuditService.log(
                action='coupon.removed',
                resource_type='Subscription',
                resource_id=str(subscription.id),
                customer=subscription.customer,
                after={
                    'coupon_code': coupon_code,
                },
                note=f'Coupon {coupon_code} removed from subscription',
            )

            logger.info(f'Removed coupon {coupon_code} from subscription {subscription.stripe_subscription_id}')

        except Exception as e:
            logger.exception(f'Failed to remove coupon from subscription {subscription.stripe_subscription_id}: {e}')
            AuditService.log(
                action='coupon.removal_failed',
                resource_type='Subscription',
                resource_id=str(subscription.id),
                customer=subscription.customer,
                after={'error': str(e)},
                note=f'Failed to remove coupon: {str(e)}',
            )
            raise

    @staticmethod
    def sync_from_stripe(stripe_coupon_id: str) -> Coupon:
        """
        Import existing Stripe coupon into admin system.

        Args:
            stripe_coupon_id: Stripe coupon ID to import

        Returns:
            Coupon: The created or updated local Coupon instance

        Side effects:
            - Creates or updates Coupon record
            - Creates audit log entry

        Raises:
            Exception: If Stripe API call fails or coupon data is invalid
        """
        try:
            # Initialize Stripe API with configured key
            get_stripe()

            # Retrieve Stripe coupon
            stripe_coupon = stripe.Coupon.retrieve(stripe_coupon_id)

            # Determine discount type and value
            if stripe_coupon.get('percent_off'):
                coupon_type = 'percent'
                discount_percent = Decimal(str(stripe_coupon['percent_off']))
                discount_amount = None
            else:
                coupon_type = 'fixed'
                discount_percent = None
                # Stripe amount is in cents
                discount_amount = Decimal(stripe_coupon['amount_off']) / 100

            # Determine duration
            duration = stripe_coupon['duration']
            duration_in_months = stripe_coupon.get('duration_in_months')

            # Extract metadata
            metadata = stripe_coupon.get('metadata', {})
            code = metadata.get('code', stripe_coupon_id)
            name = stripe_coupon.get('name', f'Imported: {stripe_coupon_id}')

            # Create or update coupon
            coupon, created = Coupon.objects.update_or_create(
                stripe_coupon_id=stripe_coupon_id,
                defaults={
                    'code': code,
                    'name': name,
                    'type': coupon_type,
                    'discount_percent': discount_percent,
                    'discount_amount': discount_amount,
                    'duration': duration,
                    'duration_in_months': duration_in_months,
                    'max_redemptions': stripe_coupon.get('max_redemptions'),
                    'is_active': stripe_coupon.get('valid', True),
                }
            )

            # Log action
            AuditService.log(
                action='coupon.synced_from_stripe',
                resource_type='Coupon',
                resource_id=str(coupon.id),
                after={
                    'stripe_coupon_id': stripe_coupon_id,
                    'code': code,
                    'created': created,
                },
                note=f'Coupon {"imported" if created else "synced"} from Stripe',
            )

            logger.info(f'{"Imported" if created else "Synced"} coupon {code} from Stripe')
            return coupon

        except Exception as e:
            logger.exception(f'Failed to sync coupon from Stripe {stripe_coupon_id}: {e}')
            raise
