from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.core.cache import cache

from customers.models import Plan, Customer
from instances.models import Instance
from audit.models import AuditLog
from .models import Order


def _mock_stripe():
    """Return a stripe mock whose checkout.Session.create yields a session."""
    stripe_mock = MagicMock()
    session = MagicMock()
    session.id = 'cs_test_123'
    session.url = 'https://checkout.stripe.com/pay/cs_test_123'
    stripe_mock.checkout.Session.create.return_value = session
    return stripe_mock, session


class OrderCreateAPITest(TestCase):
    """Tests for POST /api/orders/."""

    def setUp(self):
        cache.clear()
        self.plan = Plan.objects.filter(name='standard').first()
        if self.plan is None:
            self.plan = Plan.objects.create(name='standard', display_name='Standard')
        self.plan.is_active = True
        self.plan.ai_addon_available = True
        self.plan.stripe_price_id_user = 'price_user_123'
        self.plan.stripe_price_id_instance = 'price_instance_123'
        self.plan.stripe_price_id_ai = 'price_ai_123'
        self.plan.save()

        self.valid_payload = {
            'plan': 'standard',
            'user_seats': 5,
            'ai_addon': True,
            'slug': 'acme',
            'company_name': 'Acme GmbH',
            'contact_name': 'Max Muster',
            'contact_email': 'max@acme.de',
            'billing_email': 'rechnung@acme.de',
            'terms_accepted': True,
        }

    def _post(self, payload):
        return self.client.post('/api/orders/', payload, format='json', content_type='application/json')

    @patch('orders.services.get_stripe')
    def test_valid_order_returns_201_with_checkout_url(self, mock_get_stripe):
        stripe_mock, session = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock

        response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertIn('order_id', data)
        self.assertEqual(data['checkout_url'], session.url)

        order = Order.objects.get(id=data['order_id'])
        self.assertEqual(order.status, 'pending_payment')
        self.assertEqual(order.slug, 'acme')
        self.assertEqual(order.stripe_checkout_session_id, 'cs_test_123')

    @patch('orders.services.get_stripe')
    def test_metadata_order_id_is_set_on_session(self, mock_get_stripe):
        stripe_mock, _ = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock

        response = self._post(self.valid_payload)
        self.assertEqual(response.status_code, 201, response.content)
        order_id = response.json()['order_id']

        _, kwargs = stripe_mock.checkout.Session.create.call_args
        self.assertEqual(kwargs['metadata']['order_id'], order_id)
        self.assertEqual(kwargs['mode'], 'subscription')
        self.assertEqual(kwargs['subscription_data']['metadata']['order_id'], order_id)

    @patch('orders.services.get_stripe')
    def test_line_items_reflect_seats_and_ai_addon(self, mock_get_stripe):
        stripe_mock, _ = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock

        self._post(self.valid_payload)

        _, kwargs = stripe_mock.checkout.Session.create.call_args
        line_items = kwargs['line_items']
        prices = {li['price']: li['quantity'] for li in line_items}
        self.assertEqual(prices['price_user_123'], 5)
        self.assertEqual(prices['price_instance_123'], 1)
        self.assertEqual(prices['price_ai_123'], 1)

    @patch('orders.services.get_stripe')
    def test_no_ai_addon_omits_ai_line_item(self, mock_get_stripe):
        stripe_mock, _ = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock

        payload = {**self.valid_payload, 'ai_addon': False}
        self._post(payload)

        _, kwargs = stripe_mock.checkout.Session.create.call_args
        prices = [li['price'] for li in kwargs['line_items']]
        self.assertNotIn('price_ai_123', prices)

    @patch('orders.services.get_stripe')
    def test_order_creation_writes_audit_log(self, mock_get_stripe):
        stripe_mock, _ = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock

        self._post(self.valid_payload)

        self.assertTrue(
            AuditLog.objects.filter(action='order.created', resource_type='Order').exists()
        )

    @patch('orders.services.get_stripe')
    def test_no_customer_or_instance_created(self, mock_get_stripe):
        stripe_mock, _ = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock

        customers_before = Customer.objects.count()
        instances_before = Instance.objects.count()

        self._post(self.valid_payload)

        self.assertEqual(Customer.objects.count(), customers_before)
        self.assertEqual(Instance.objects.count(), instances_before)

    # --- Validation ---

    def test_missing_required_fields_returns_400(self):
        response = self._post({'plan': 'standard'})
        self.assertEqual(response.status_code, 400)
        errors = response.json()['errors']
        for field in ['user_seats', 'slug', 'company_name', 'contact_name', 'contact_email', 'terms_accepted']:
            self.assertIn(field, errors)

    def test_unknown_plan_returns_400(self):
        response = self._post({**self.valid_payload, 'plan': 'does-not-exist'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('plan', response.json()['errors'])

    def test_retired_starter_plan_name_returns_400(self):
        """'starter' was retired in favor of 'standard' and must no longer resolve."""
        response = self._post({**self.valid_payload, 'plan': 'starter'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('plan', response.json()['errors'])

    def test_retired_professional_plan_name_returns_400(self):
        """'professional' never corresponded to a real offering and must not resolve."""
        response = self._post({**self.valid_payload, 'plan': 'professional'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('plan', response.json()['errors'])

    def test_enterprise_plan_not_orderable_via_api(self):
        """Enterprise is sold manually/by contact, not through the order API."""
        response = self._post({**self.valid_payload, 'plan': 'enterprise'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('plan', response.json()['errors'])

    def test_inactive_plan_returns_400(self):
        self.plan.is_active = False
        self.plan.save()
        response = self._post(self.valid_payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('plan', response.json()['errors'])

    def test_non_positive_seats_returns_400(self):
        response = self._post({**self.valid_payload, 'user_seats': 0})
        self.assertEqual(response.status_code, 400)
        self.assertIn('user_seats', response.json()['errors'])

    def test_invalid_slug_format_returns_400(self):
        response = self._post({**self.valid_payload, 'slug': 'Not-Valid!'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('slug', response.json()['errors'])

    def test_missing_terms_returns_400(self):
        response = self._post({**self.valid_payload, 'terms_accepted': False})
        self.assertEqual(response.status_code, 400)
        self.assertIn('terms_accepted', response.json()['errors'])

    def test_slug_taken_by_customer_returns_400(self):
        Customer.objects.create(
            slug='acme',
            company_name='Existing',
            contact_name='X',
            contact_email='x@y.de',
            billing_email='x@y.de',
            billing_address='A',
            billing_city='B',
            billing_postal_code='12345',
        )
        response = self._post(self.valid_payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('slug', response.json()['errors'])

    def test_slug_taken_by_open_order_returns_400(self):
        Order.objects.create(
            plan=self.plan,
            user_seats=1,
            slug='acme',
            company_name='Other',
            contact_name='Y',
            contact_email='y@z.de',
            billing_email='y@z.de',
            status='pending_payment',
        )
        response = self._post(self.valid_payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('slug', response.json()['errors'])

    @patch('orders.services.get_stripe')
    def test_slug_free_after_failed_order(self, mock_get_stripe):
        stripe_mock, _ = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock

        Order.objects.create(
            plan=self.plan,
            user_seats=1,
            slug='acme',
            company_name='Other',
            contact_name='Y',
            contact_email='y@z.de',
            billing_email='y@z.de',
            status='failed',
        )
        response = self._post(self.valid_payload)
        self.assertEqual(response.status_code, 201, response.content)

    def test_ai_addon_unavailable_for_plan_returns_400(self):
        self.plan.ai_addon_available = False
        self.plan.save()
        response = self._post(self.valid_payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('ai_addon', response.json()['errors'])

    @override_settings(RATELIMIT_ENABLE=True)
    @patch('orders.services.get_stripe')
    def test_rate_limit_blocks_after_five(self, mock_get_stripe):
        stripe_mock, _ = _mock_stripe()
        mock_get_stripe.return_value = stripe_mock
        cache.clear()

        for i in range(5):
            payload = {**self.valid_payload, 'slug': f'acme{i}'}
            resp = self._post(payload)
            self.assertEqual(resp.status_code, 201, resp.content)

        # django-ratelimit with block=True raises Ratelimited -> HTTP 403
        # (same convention as ContactCreateAPIView).
        blocked = self._post({**self.valid_payload, 'slug': 'acme9'})
        self.assertEqual(blocked.status_code, 403)


class CheckSlugAPITest(TestCase):
    """Tests for GET /api/orders/check-slug/."""

    def setUp(self):
        cache.clear()
        self.plan = Plan.objects.filter(name='standard').first()
        if self.plan is None:
            self.plan = Plan.objects.create(name='standard', display_name='Standard')

    def _get(self, slug=None):
        params = {} if slug is None else {'slug': slug}
        return self.client.get('/api/orders/check-slug/', params)

    def test_free_slug_returns_available(self):
        response = self._get('acme')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['available'])
        self.assertIn('message', data)

    def test_slug_taken_by_customer_returns_unavailable(self):
        Customer.objects.create(
            slug='acme',
            company_name='Existing',
            contact_name='X',
            contact_email='x@y.de',
            billing_email='x@y.de',
            billing_address='A',
            billing_city='B',
            billing_postal_code='12345',
        )
        response = self._get('acme')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])

    def test_slug_taken_by_open_order_returns_unavailable(self):
        Order.objects.create(
            plan=self.plan,
            user_seats=1,
            slug='acme',
            company_name='Other',
            contact_name='Y',
            contact_email='y@z.de',
            billing_email='y@z.de',
            status='pending_payment',
        )
        response = self._get('acme')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])

    def test_slug_free_after_failed_order(self):
        Order.objects.create(
            plan=self.plan,
            user_seats=1,
            slug='acme',
            company_name='Other',
            contact_name='Y',
            contact_email='y@z.de',
            billing_email='y@z.de',
            status='failed',
        )
        response = self._get('acme')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['available'])

    def test_uppercase_slug_is_normalized(self):
        Customer.objects.create(
            slug='acme',
            company_name='Existing',
            contact_name='X',
            contact_email='x@y.de',
            billing_email='x@y.de',
            billing_address='A',
            billing_city='B',
            billing_postal_code='12345',
        )
        response = self._get('ACME')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])

    def test_invalid_slug_format_returns_unavailable(self):
        for bad in ['a', 'toolongslug', 'Not-Valid!', 'ab cd']:
            response = self._get(bad)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['available'], bad)

    def test_missing_slug_returns_unavailable(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])

    def test_no_auth_required(self):
        response = self._get('acme')
        self.assertEqual(response.status_code, 200)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_rate_limit_blocks_after_thirty(self):
        cache.clear()
        for i in range(30):
            resp = self._get('acme')
            self.assertEqual(resp.status_code, 200, resp.content)

        blocked = self._get('acme')
        self.assertEqual(blocked.status_code, 403)
