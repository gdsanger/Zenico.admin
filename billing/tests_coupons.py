"""
Comprehensive tests for coupon and discount management functionality.
Tests models, service layer, validation, and Stripe integration.
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from billing.models import Coupon, CouponRedemption
from billing.coupon_service import CouponService
from customers.models import Customer, Plan, Subscription

AdminUser = get_user_model()


class CouponModelTest(TestCase):
    """Tests for Coupon model validation and properties."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = AdminUser.objects.create(
            email='admin@test.com',
            display_name='Admin User',
            role='superadmin'
        )

    def test_create_percent_coupon(self):
        """Test creating a percentage discount coupon."""
        coupon = Coupon.objects.create(
            code='TEST20',
            name='Test 20% Discount',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            is_active=True,
            created_by=self.admin_user
        )

        self.assertEqual(coupon.code, 'TEST20')
        self.assertEqual(coupon.type, 'percent')
        self.assertEqual(coupon.discount_percent, Decimal('20.00'))
        self.assertIsNone(coupon.discount_amount)
        self.assertTrue(coupon.is_valid)

    def test_create_fixed_coupon(self):
        """Test creating a fixed amount discount coupon."""
        coupon = Coupon.objects.create(
            code='FIXED50',
            name='Fixed 50 EUR Discount',
            type='fixed',
            discount_amount=Decimal('50.00'),
            duration='forever',
            is_active=True
        )

        self.assertEqual(coupon.type, 'fixed')
        self.assertEqual(coupon.discount_amount, Decimal('50.00'))
        self.assertIsNone(coupon.discount_percent)

    def test_percent_coupon_validation_missing_percent(self):
        """Test validation fails for percent coupon without discount_percent."""
        coupon = Coupon(
            code='INVALID',
            name='Invalid Coupon',
            type='percent',
            duration='forever'
        )

        with self.assertRaises(ValidationError) as context:
            coupon.full_clean()

        self.assertIn('discount_percent', str(context.exception))

    def test_fixed_coupon_validation_missing_amount(self):
        """Test validation fails for fixed coupon without discount_amount."""
        coupon = Coupon(
            code='INVALID',
            name='Invalid Coupon',
            type='fixed',
            duration='forever'
        )

        with self.assertRaises(ValidationError) as context:
            coupon.full_clean()

        self.assertIn('discount_amount', str(context.exception))

    def test_repeating_coupon_validation_missing_months(self):
        """Test validation fails for repeating coupon without duration_in_months."""
        coupon = Coupon(
            code='INVALID',
            name='Invalid Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='repeating'
        )

        with self.assertRaises(ValidationError) as context:
            coupon.full_clean()

        self.assertIn('duration_in_months', str(context.exception))

    def test_forever_coupon_validation_with_months(self):
        """Test validation fails for forever coupon with duration_in_months."""
        coupon = Coupon(
            code='INVALID',
            name='Invalid Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            duration_in_months=3
        )

        with self.assertRaises(ValidationError) as context:
            coupon.full_clean()

        self.assertIn('duration_in_months', str(context.exception))

    def test_is_valid_inactive_coupon(self):
        """Test is_valid returns False for inactive coupon."""
        coupon = Coupon.objects.create(
            code='INACTIVE',
            name='Inactive Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            is_active=False
        )

        self.assertFalse(coupon.is_valid)

    def test_is_valid_future_coupon(self):
        """Test is_valid returns False for coupon not yet valid."""
        future_date = timezone.now() + timedelta(days=7)
        coupon = Coupon.objects.create(
            code='FUTURE',
            name='Future Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            valid_from=future_date,
            is_active=True
        )

        self.assertFalse(coupon.is_valid)

    def test_is_valid_expired_coupon(self):
        """Test is_valid returns False for expired coupon."""
        past_date = timezone.now() - timedelta(days=7)
        coupon = Coupon.objects.create(
            code='EXPIRED',
            name='Expired Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            valid_until=past_date,
            is_active=True
        )

        self.assertFalse(coupon.is_valid)

    def test_is_valid_exhausted_coupon(self):
        """Test is_valid returns False for exhausted coupon."""
        coupon = Coupon.objects.create(
            code='EXHAUSTED',
            name='Exhausted Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            max_redemptions=10,
            redemptions_count=10,
            is_active=True
        )

        self.assertFalse(coupon.is_valid)

    def test_discount_display_percent(self):
        """Test discount_display property for percent coupon."""
        coupon = Coupon.objects.create(
            code='TEST',
            name='Test',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever'
        )

        self.assertEqual(coupon.discount_display, '20.00%')

    def test_discount_display_fixed(self):
        """Test discount_display property for fixed coupon."""
        coupon = Coupon.objects.create(
            code='TEST',
            name='Test',
            type='fixed',
            discount_amount=Decimal('50.00'),
            duration='forever'
        )

        self.assertEqual(coupon.discount_display, '50.00 €')

    def test_duration_display_forever(self):
        """Test duration_display property for forever coupon."""
        coupon = Coupon.objects.create(
            code='TEST',
            name='Test',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever'
        )

        self.assertEqual(coupon.duration_display, 'Dauerhaft')

    def test_duration_display_repeating(self):
        """Test duration_display property for repeating coupon."""
        coupon = Coupon.objects.create(
            code='TEST',
            name='Test',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='repeating',
            duration_in_months=3
        )

        self.assertEqual(coupon.duration_display, '3 Monate')

    def test_redemptions_display_unlimited(self):
        """Test redemptions_display property for unlimited redemptions."""
        coupon = Coupon.objects.create(
            code='TEST',
            name='Test',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            redemptions_count=5
        )

        self.assertEqual(coupon.redemptions_display, '5 / ∞')

    def test_redemptions_display_limited(self):
        """Test redemptions_display property for limited redemptions."""
        coupon = Coupon.objects.create(
            code='TEST',
            name='Test',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            max_redemptions=100,
            redemptions_count=45
        )

        self.assertEqual(coupon.redemptions_display, '45 / 100')


class CouponRedemptionModelTest(TestCase):
    """Tests for CouponRedemption model."""

    def setUp(self):
        """Set up test data."""
        self.plan, _ = Plan.objects.get_or_create(
            name='professional',
            defaults={
                'display_name': 'Professional',
                'price_per_user': Decimal('5.00'),
                'price_per_instance': Decimal('30.00')
            }
        )

        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Company',
            contact_name='Test Contact',
            contact_email='contact@test.com',
            billing_email='billing@test.com',
            billing_address='Test Address',
            billing_city='Test City',
            billing_postal_code='12345',
            billing_country='DE'
        )

        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=2
        )

        self.coupon = Coupon.objects.create(
            code='TEST20',
            name='Test Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever'
        )

    def test_create_redemption(self):
        """Test creating a coupon redemption."""
        redemption = CouponRedemption.objects.create(
            coupon=self.coupon,
            customer=self.customer,
            subscription=self.subscription
        )

        self.assertEqual(redemption.coupon, self.coupon)
        self.assertEqual(redemption.customer, self.customer)
        self.assertEqual(redemption.subscription, self.subscription)
        self.assertIsNotNone(redemption.redeemed_at)

    def test_unique_constraint(self):
        """Test unique constraint prevents duplicate redemptions."""
        CouponRedemption.objects.create(
            coupon=self.coupon,
            customer=self.customer,
            subscription=self.subscription
        )

        # Try to create duplicate
        with self.assertRaises(Exception):  # IntegrityError
            CouponRedemption.objects.create(
                coupon=self.coupon,
                customer=self.customer,
                subscription=self.subscription
            )


class CouponServiceTest(TestCase):
    """Tests for CouponService business logic."""

    def setUp(self):
        """Set up test data."""
        self.plan, _ = Plan.objects.get_or_create(
            name='professional',
            defaults={
                'display_name': 'Professional',
                'price_per_user': Decimal('5.00'),
                'price_per_instance': Decimal('30.00')
            }
        )

        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Company',
            contact_name='Test Contact',
            contact_email='contact@test.com',
            billing_email='billing@test.com',
            billing_address='Test Address',
            billing_city='Test City',
            billing_postal_code='12345',
            billing_country='DE',
            stripe_customer_id='cus_test123'
        )

        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=2
        )

        self.coupon = Coupon.objects.create(
            code='TEST20',
            name='Test Coupon',
            type='percent',
            discount_percent=Decimal('20.00'),
            duration='forever',
            is_active=True
        )

    @patch('stripe.Coupon.create')
    @patch('stripe.PromotionCode.create')
    def test_create_stripe_coupon_percent(self, mock_promo, mock_coupon):
        """Test creating Stripe coupon for percentage discount."""
        mock_coupon.return_value = MagicMock(id='co_test123')
        mock_promo.return_value = MagicMock(id='promo_test123')

        stripe_coupon_id, stripe_promo_id = CouponService.create_stripe_coupon(self.coupon)

        self.assertEqual(stripe_coupon_id, 'co_test123')
        self.assertEqual(stripe_promo_id, 'promo_test123')
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.stripe_coupon_id, 'co_test123')
        self.assertEqual(self.coupon.stripe_promotion_code_id, 'promo_test123')

        # Verify Stripe API calls
        mock_coupon.assert_called_once()
        mock_promo.assert_called_once()

    @patch('stripe.Subscription.modify')
    def test_apply_to_subscription_success(self, mock_modify):
        """Test successfully applying coupon to subscription."""
        self.coupon.stripe_promotion_code_id = 'promo_test123'
        self.coupon.save()

        mock_modify.return_value = {'discount': {'id': 'di_test123'}}

        redemption = CouponService.apply_to_subscription(
            coupon=self.coupon,
            subscription=self.subscription,
            customer=self.customer
        )

        self.assertIsNotNone(redemption)
        self.assertEqual(redemption.coupon, self.coupon)
        self.assertEqual(redemption.customer, self.customer)

        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.redemptions_count, 1)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.coupon, self.coupon)

    def test_apply_to_subscription_invalid_coupon(self):
        """Test applying invalid coupon raises ValidationError."""
        self.coupon.is_active = False
        self.coupon.save()

        with self.assertRaises(ValidationError):
            CouponService.apply_to_subscription(
                coupon=self.coupon,
                subscription=self.subscription,
                customer=self.customer
            )

    def test_apply_to_subscription_duplicate(self):
        """Test applying coupon twice to same customer raises ValidationError."""
        self.coupon.stripe_promotion_code_id = 'promo_test123'
        self.coupon.save()

        CouponRedemption.objects.create(
            coupon=self.coupon,
            customer=self.customer,
            subscription=self.subscription
        )

        with self.assertRaises(ValidationError) as context:
            CouponService.apply_to_subscription(
                coupon=self.coupon,
                subscription=self.subscription,
                customer=self.customer
            )

        self.assertIn('bereits', str(context.exception))

    @patch('stripe.Subscription.delete_discount')
    def test_remove_from_subscription(self, mock_delete):
        """Test removing coupon from subscription."""
        self.subscription.coupon = self.coupon
        self.subscription.save()

        CouponService.remove_from_subscription(self.subscription)

        self.subscription.refresh_from_db()
        self.assertIsNone(self.subscription.coupon)

        mock_delete.assert_called_once_with(self.subscription.stripe_subscription_id)


class InternalCouponTest(TestCase):
    """Test that INTERNAL coupon exists from data migration."""

    def test_internal_coupon_exists(self):
        """Test INTERNAL coupon was created by migration."""
        internal = Coupon.objects.filter(code='INTERNAL').first()

        self.assertIsNotNone(internal)
        self.assertEqual(internal.code, 'INTERNAL')
        self.assertEqual(internal.type, 'percent')
        self.assertEqual(internal.discount_percent, Decimal('100.00'))
        self.assertEqual(internal.duration, 'forever')
        self.assertIsNone(internal.max_redemptions)
        self.assertTrue(internal.is_active)
