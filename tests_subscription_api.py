"""
Unit tests for Subscription API endpoints.
"""

from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient

from instances.models import Instance, UserLicense
from customers.models import Customer, Plan, Subscription
from instances.subscription_api import (
    _build_schedule_phases_for_seat_reduction,
    _count_active_users,
    _get_price_per_seat,
    _get_subscription_schedule_id,
    _schedule_seat_reduction,
)


class SubscriptionAPITestCase(TestCase):
    """Test cases for Subscription API endpoints."""

    def setUp(self):
        """Set up test data."""
        # Get or create plan
        self.plan, _ = Plan.objects.get_or_create(
            name='professional',
            defaults={
                'display_name': 'Professional',
                'price_per_user': Decimal('15.00'),
                'is_active': True
            }
        )

        # Create customer
        self.customer = Customer.objects.create(
            slug='testcust',
            company_name='Test Customer GmbH',
            contact_name='Test User',
            contact_email='test@example.com',
            billing_email='billing@example.com',
            billing_address='Test Street 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            billing_country='DE',
            stripe_customer_id='cus_test123'
        )

        # Create subscription
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=5,
            instance_seats_total=1,
            ai_addon_active=False,
            current_period_end=timezone.now() + timedelta(days=30)
        )

        # Create instance
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testcust',
            display_name='Test Instance',
            is_master=True,
            user_seats=5,
            status='active'
        )

        # Set up API client
        self.client = APIClient()
        # Authenticate using API key
        self.client.credentials(HTTP_AUTHORIZATION=f'Api-Key {self.instance.api_key}')

    def test_get_price_per_seat(self):
        """Test volume-based pricing calculation."""
        self.assertEqual(_get_price_per_seat(1), Decimal('19.00'))
        self.assertEqual(_get_price_per_seat(3), Decimal('19.00'))
        self.assertEqual(_get_price_per_seat(4), Decimal('15.00'))
        self.assertEqual(_get_price_per_seat(10), Decimal('15.00'))
        self.assertEqual(_get_price_per_seat(11), Decimal('12.00'))
        self.assertEqual(_get_price_per_seat(50), Decimal('12.00'))

    def test_count_active_users(self):
        """Test counting active user licenses."""
        # Initially no licenses
        self.assertEqual(_count_active_users(self.instance), 0)

        # Create some user licenses
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user1',
            email='user1@example.com',
            display_name='User 1',
            is_active=True
        )
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user2',
            email='user2@example.com',
            display_name='User 2',
            is_active=True
        )
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user3',
            email='user3@example.com',
            display_name='User 3',
            is_active=False  # Inactive
        )

        # Should only count active licenses
        self.assertEqual(_count_active_users(self.instance), 2)

    def test_get_subscription_details(self):
        """Test GET /api/instance/subscription/ endpoint."""
        response = self.client.get('/api/instance/subscription/')

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['user_seats'], 5)
        self.assertEqual(data['user_seats_used'], 0)
        self.assertIn('price_per_seat', data)
        self.assertEqual(data['ai_addon'], False)
        self.assertIsNotNone(data['billing_period_end'])

    def test_get_subscription_with_coupon(self):
        """Test subscription details with coupon applied."""
        # Add coupon info to customer
        self.customer.coupon_code = 'TESTCODE'
        self.customer.coupon_description = 'Test Discount'
        self.customer.coupon_discount_pct = Decimal('10.00')
        self.customer.save()

        response = self.client.get('/api/instance/subscription/')

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['coupon_code'], 'TESTCODE')
        self.assertEqual(data['coupon_description'], 'Test Discount')
        self.assertEqual(data['coupon_discount'], 10.0)

    @patch('instances.subscription_api._create_seats_checkout')
    def test_add_seats(self, mock_checkout):
        """Test POST /api/instance/subscription/add-seats/ endpoint."""
        mock_checkout.return_value = 'https://checkout.stripe.com/test'

        response = self.client.post(
            '/api/instance/subscription/add-seats/',
            {'seats': 3},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('checkout_url', data)

    def test_add_seats_invalid(self):
        """Test adding seats with invalid quantity."""
        response = self.client.post(
            '/api/instance/subscription/add-seats/',
            {'seats': 0},
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_get_subscription_schedule_id(self):
        """Test extracting schedule ID from Stripe subscription payloads."""
        self.assertIsNone(_get_subscription_schedule_id({'schedule': None}))
        self.assertEqual(
            _get_subscription_schedule_id({'schedule': 'sub_sched_test'}),
            'sub_sched_test',
        )
        self.assertEqual(
            _get_subscription_schedule_id({'schedule': {'id': 'sub_sched_test'}}),
            'sub_sched_test',
        )

    def test_build_schedule_phases_for_seat_reduction_appends_future_phase(self):
        """Test schedule phase builder adds a future phase when none exists."""
        period_end = 1_700_000_000
        stripe_sub = {
            'current_period_end': period_end,
            'items': {
                'data': [
                    {
                        'price': {'id': 'price_user', 'nickname': 'User Seats'},
                        'quantity': 5,
                    },
                    {
                        'price': {'id': 'price_instance', 'nickname': 'Instance Fee'},
                        'quantity': 1,
                    },
                ]
            },
        }
        schedule = {
            'phases': [
                {
                    'start_date': period_end - 2_592_000,
                    'end_date': period_end,
                    'items': [
                        {'price': 'price_user', 'quantity': 5},
                        {'price': 'price_instance', 'quantity': 1},
                    ],
                }
            ]
        }

        phases = _build_schedule_phases_for_seat_reduction(
            schedule=schedule,
            stripe_sub=stripe_sub,
            new_seats=3,
        )

        self.assertEqual(len(phases), 2)
        self.assertEqual(phases[0]['items'][0]['quantity'], 5)
        self.assertEqual(phases[1]['start_date'], period_end)
        self.assertEqual(phases[1]['items'][0]['quantity'], 3)
        self.assertEqual(phases[1]['items'][1]['quantity'], 1)

    def test_build_schedule_phases_for_seat_reduction_updates_existing_future_phase(self):
        """Test schedule phase builder updates an existing future phase."""
        period_end = 1_700_000_000
        stripe_sub = {
            'current_period_end': period_end,
            'items': {
                'data': [
                    {
                        'price': {'id': 'price_user', 'nickname': 'User Seats'},
                        'quantity': 5,
                    }
                ]
            },
        }
        schedule = {
            'phases': [
                {
                    'start_date': period_end - 2_592_000,
                    'end_date': period_end,
                    'items': [{'price': 'price_user', 'quantity': 5}],
                },
                {
                    'start_date': period_end,
                    'items': [{'price': 'price_user', 'quantity': 4}],
                },
            ]
        }

        phases = _build_schedule_phases_for_seat_reduction(
            schedule=schedule,
            stripe_sub=stripe_sub,
            new_seats=3,
        )

        self.assertEqual(len(phases), 2)
        self.assertEqual(phases[1]['items'][0]['quantity'], 3)

    @patch('instances.subscription_api.AuditService.log')
    @patch('instances.subscription_api.get_stripe')
    def test_schedule_seat_reduction_creates_schedule_when_missing(
        self, mock_get_stripe, mock_audit_log
    ):
        """Test seat reduction creates a schedule when none is attached."""
        period_end = 1_700_000_000
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe
        mock_stripe.Subscription.retrieve.return_value = {
            'current_period_end': period_end,
            'schedule': None,
            'items': {
                'data': [
                    {
                        'price': {'id': 'price_user', 'nickname': 'User Seats'},
                        'quantity': 5,
                    }
                ]
            },
        }
        mock_stripe.SubscriptionSchedule.create.return_value = MagicMock(id='sub_sched_new')
        mock_stripe.SubscriptionSchedule.retrieve.return_value = {
            'phases': [
                {
                    'start_date': period_end - 2_592_000,
                    'items': [{'price': 'price_user', 'quantity': 5}],
                }
            ]
        }

        effective_date = _schedule_seat_reduction(self.instance, new_seats=3)

        mock_stripe.SubscriptionSchedule.create.assert_called_once_with(
            from_subscription='sub_test123',
        )
        mock_stripe.SubscriptionSchedule.modify.assert_called_once()
        modify_kwargs = mock_stripe.SubscriptionSchedule.modify.call_args.kwargs
        self.assertEqual(modify_kwargs['phases'][-1]['items'][0]['quantity'], 3)
        self.assertEqual(effective_date, date.fromtimestamp(period_end))
        mock_audit_log.assert_called_once()

    @patch('instances.subscription_api.AuditService.log')
    @patch('instances.subscription_api.get_stripe')
    def test_schedule_seat_reduction_updates_existing_schedule(
        self, mock_get_stripe, mock_audit_log
    ):
        """Test seat reduction updates an existing schedule instead of creating one."""
        period_end = 1_700_000_000
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe
        mock_stripe.Subscription.retrieve.return_value = {
            'current_period_end': period_end,
            'schedule': 'sub_sched_existing',
            'items': {
                'data': [
                    {
                        'price': {'id': 'price_user', 'nickname': 'User Seats'},
                        'quantity': 5,
                    }
                ]
            },
        }
        mock_stripe.SubscriptionSchedule.retrieve.return_value = {
            'phases': [
                {
                    'start_date': period_end - 2_592_000,
                    'end_date': period_end,
                    'items': [{'price': 'price_user', 'quantity': 5}],
                },
                {
                    'start_date': period_end,
                    'items': [{'price': 'price_user', 'quantity': 4}],
                },
            ]
        }

        _schedule_seat_reduction(self.instance, new_seats=3)

        mock_stripe.SubscriptionSchedule.create.assert_not_called()
        mock_stripe.SubscriptionSchedule.retrieve.assert_called_once_with('sub_sched_existing')
        modify_args, modify_kwargs = mock_stripe.SubscriptionSchedule.modify.call_args
        self.assertEqual(modify_args[0], 'sub_sched_existing')
        self.assertEqual(modify_kwargs['phases'][1]['items'][0]['quantity'], 3)
        mock_audit_log.assert_called_once()

    @patch('instances.subscription_api._schedule_seat_reduction')
    def test_remove_seats(self, mock_schedule):
        """Test POST /api/instance/subscription/remove-seats/ endpoint."""
        mock_schedule.return_value = date.today() + timedelta(days=30)

        response = self.client.post(
            '/api/instance/subscription/remove-seats/',
            {'seats': 2},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_seats'], 3)

    def test_remove_seats_too_many(self):
        """Test removing more seats than available."""
        response = self.client.post(
            '/api/instance/subscription/remove-seats/',
            {'seats': 5},
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    @patch('instances.subscription_api._create_ai_addon_checkout')
    def test_add_ai_addon(self, mock_checkout):
        """Test POST /api/instance/subscription/add-ai-addon/ endpoint."""
        mock_checkout.return_value = 'https://checkout.stripe.com/test'

        response = self.client.post('/api/instance/subscription/add-ai-addon/')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('checkout_url', data)

    def test_add_ai_addon_already_active(self):
        """Test adding AI addon when already active."""
        self.instance.ai_addon_active = True
        self.instance.save()

        response = self.client.post('/api/instance/subscription/add-ai-addon/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    @patch('instances.subscription_api._cancel_stripe_subscription')
    @patch('instances.subscription_api._send_cancellation_confirmation')
    @patch('instances.subscription_api._notify_admin_cancellation')
    def test_cancel_subscription(self, mock_notify, mock_confirm, mock_cancel):
        """Test POST /api/instance/subscription/cancel/ endpoint."""
        cancelled_date = date.today() + timedelta(days=30)
        mock_cancel.return_value = cancelled_date

        response = self.client.post(
            '/api/instance/subscription/cancel/',
            {
                'reason_category': 'too_expensive',
                'reason_text': 'Budget constraints',
            },
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIsNotNone(data['cancelled_at'])

        # Verify instance was updated
        self.instance.refresh_from_db()
        self.assertIsNotNone(self.instance.cancelled_at)
        self.assertEqual(self.instance.cancelled_reason, 'too_expensive')
        self.assertEqual(self.instance.cancelled_reason_text, 'Budget constraints')

    def test_cancel_subscription_invalid_reason(self):
        """Test cancellation with invalid reason category."""
        response = self.client.post(
            '/api/instance/subscription/cancel/',
            {'reason_category': 'invalid_reason'},
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    @patch('instances.subscription_api._create_billing_portal_url')
    def test_get_billing_portal_url(self, mock_portal):
        """Test GET /api/instance/subscription/portal-url/ endpoint."""
        mock_portal.return_value = 'https://billing.stripe.com/test'

        response = self.client.get('/api/instance/subscription/portal-url/')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('url', data)
        self.assertTrue(data['url'].startswith('https://billing.stripe.com'))

    def test_unauthenticated_access(self):
        """Test that endpoints require authentication."""
        # Remove credentials
        self.client.credentials()

        response = self.client.get('/api/instance/subscription/')
        # DRF returns 403 for IsAuthenticated when no auth is provided
        self.assertIn(response.status_code, [401, 403])


class CancellationTaskTestCase(TestCase):
    """Test cases for cancellation processing task."""

    def setUp(self):
        """Set up test data."""
        # Get or create plan
        self.plan, _ = Plan.objects.get_or_create(
            name='professional',
            defaults={
                'display_name': 'Professional',
                'price_per_user': Decimal('15.00'),
                'is_active': True
            }
        )

        # Create customer
        self.customer = Customer.objects.create(
            slug='testcust',
            company_name='Test Customer GmbH',
            contact_name='Test User',
            contact_email='test@example.com',
            billing_email='billing@example.com',
            billing_address='Test Street 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            billing_country='DE'
        )

        # Create subscription
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=5,
            instance_seats_total=1
        )

    @patch('instances.tasks._send_read_only_notification')
    def test_process_cancellation_to_read_only(self, mock_notify):
        """Test instance transitions to read_only on cancellation date."""
        from instances.tasks import process_cancellations

        # Create instance with cancellation date = today
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testcust',
            display_name='Test Instance',
            is_master=True,
            user_seats=5,
            status='active',
            cancelled_at=date.today()
        )

        # Run task
        result = process_cancellations()

        # Check instance is now read_only
        instance.refresh_from_db()
        self.assertEqual(instance.status, 'read_only')
        self.assertEqual(result['read_only_count'], 1)
        mock_notify.assert_called_once()

    @patch('instances.tasks._send_deletion_warning')
    def test_process_cancellation_75_day_warning(self, mock_warning):
        """Test deletion warning is sent after 75 days."""
        from instances.tasks import process_cancellations

        # Create instance cancelled 75 days ago
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testcust',
            display_name='Test Instance',
            is_master=True,
            user_seats=5,
            status='read_only',
            cancelled_at=date.today() - timedelta(days=75)
        )

        # Run task
        result = process_cancellations()

        self.assertEqual(result['warning_count'], 1)
        mock_warning.assert_called_once()

    @patch('instances.tasks._archive_and_delete')
    def test_process_cancellation_90_day_deletion(self, mock_delete):
        """Test instance is deleted after 90 days."""
        from instances.tasks import process_cancellations

        # Create instance cancelled 90 days ago
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testcust',
            display_name='Test Instance',
            is_master=True,
            user_seats=5,
            status='read_only',
            cancelled_at=date.today() - timedelta(days=90)
        )

        # Run task
        result = process_cancellations()

        self.assertEqual(result['deleted_count'], 1)
        mock_delete.assert_called_once()
