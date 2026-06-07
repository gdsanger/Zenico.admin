"""Tests for billing Stripe helpers."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from billing.stripe_helpers import _cancel_ai_addon_stripe
from customers.models import Customer, Plan, Subscription
from instances.models import Instance


class CancelAIAddonStripeTestCase(TestCase):
    """Tests for _cancel_ai_addon_stripe helper."""

    def setUp(self):
        self.plan, _ = Plan.objects.get_or_create(
            name='starter',
            defaults={
                'display_name': 'Starter',
                'stripe_price_id_ai': 'price_ai_test',
                'is_active': True,
            },
        )
        self.plan.stripe_price_id_ai = 'price_ai_test'
        self.plan.save(update_fields=['stripe_price_id_ai'])
        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Co',
            contact_name='Test User',
            contact_email='test@example.com',
            billing_email='billing@example.com',
            billing_address='Street 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            billing_country='DE',
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            ai_addon_active=True,
        )
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Instance',
            is_master=True,
            status='active',
        )

    @patch('billing.stripe_helpers.get_stripe')
    def test_cancel_ai_addon_stripe_uses_plan_price(self, mock_get_stripe):
        """Helper removes AI addon item and returns period end date."""
        period_end_ts = 1782864000  # 2026-07-01 UTC
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe
        mock_stripe.Subscription.retrieve.return_value = {
            'current_period_end': period_end_ts,
            'items': {
                'data': [
                    {'id': 'si_user', 'price': {'id': 'price_user'}},
                    {'id': 'si_ai', 'price': {'id': 'price_ai_test'}},
                ],
            },
        }

        result = _cancel_ai_addon_stripe(self.instance)

        self.assertEqual(result, '2026-07-01')
        mock_stripe.SubscriptionItem.delete.assert_called_once_with(
            'si_ai',
            proration_behavior='none',
        )

    @override_settings(STRIPE_AI_ADDON_PRICE_ID='price_global_ai')
    @patch('billing.stripe_helpers.get_stripe')
    def test_cancel_ai_addon_stripe_uses_settings_price(self, mock_get_stripe):
        """Helper prefers STRIPE_AI_ADDON_PRICE_ID when configured."""
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe
        mock_stripe.Subscription.retrieve.return_value = {
            'current_period_end': 1782864000,
            'items': {
                'data': [
                    {'id': 'si_ai', 'price': {'id': 'price_global_ai'}},
                ],
            },
        }

        result = _cancel_ai_addon_stripe(self.instance)

        self.assertEqual(result, '2026-07-01')
        mock_stripe.SubscriptionItem.delete.assert_called_once_with(
            'si_ai',
            proration_behavior='none',
        )

    @patch('billing.stripe_helpers.get_stripe')
    def test_cancel_ai_addon_stripe_item_not_found(self, mock_get_stripe):
        """Helper raises when AI addon item is missing from subscription."""
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe
        mock_stripe.Subscription.retrieve.return_value = {
            'current_period_end': 1782864000,
            'items': {
                'data': [
                    {'id': 'si_user', 'price': {'id': 'price_user'}},
                ],
            },
        }

        with self.assertRaises(ValueError) as ctx:
            _cancel_ai_addon_stripe(self.instance)

        self.assertEqual(str(ctx.exception), 'KI-Addon nicht in Subscription gefunden.')
