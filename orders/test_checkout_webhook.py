"""
Tests für die checkout.session.completed / .expired Verarbeitung im
StripeWebhookHandler (Kundenanlage nach Zahlung).

Stripe ist vollständig gemockt — es werden nur die Handler-Methoden direkt mit
konstruierten Event-Payloads aufgerufen.
"""

from unittest.mock import patch

from django.test import TestCase

from billing.models import StripeEvent
from customers.models import Plan, Customer, Subscription
from instances.models import Instance
from .models import Order


def _checkout_event(order, *, event_type='checkout.session.completed',
                    session_id='cs_test_1', customer='cus_test_1',
                    subscription='sub_test_1', with_metadata=True):
    """Baut ein minimales Stripe-Event-Dict für eine Checkout-Session."""
    obj = {
        'id': session_id,
        'customer': customer,
        'subscription': subscription,
        'metadata': {'order_id': str(order.id)} if with_metadata else {},
    }
    return {'id': 'evt_test_1', 'type': event_type, 'data': {'object': obj}}


class CheckoutWebhookTest(TestCase):
    """Tests für _handle_checkout_session_completed / _expired."""

    def setUp(self):
        self.plan = Plan.objects.filter(name='standard').first()
        if self.plan is None:
            self.plan = Plan.objects.create(name='standard', display_name='Standard')
        self.plan.ai_addon_available = True
        self.plan.stripe_price_id_user = 'price_user_1'
        self.plan.stripe_price_id_instance = 'price_instance_1'
        self.plan.stripe_price_id_ai = 'price_ai_1'
        self.plan.save()
        self.order = Order.objects.create(
            plan=self.plan,
            user_seats=5,
            ai_addon=True,
            slug='acme',
            company_name='Acme GmbH',
            contact_name='Max Muster',
            contact_email='max@acme.de',
            billing_email='rechnung@acme.de',
            billing_address='Hauptstr. 1',
            billing_city='München',
            billing_postal_code='80331',
            billing_country='DE',
            terms_accepted=True,
            status='pending_payment',
            stripe_checkout_session_id='cs_test_1',
        )

    def _db_event(self, event):
        return StripeEvent.objects.create(
            stripe_event_id=event['id'],
            event_type=event['type'],
            payload=event,
        )

    def _handle(self, event):
        from core.services.webhook import StripeWebhookHandler
        db_event = self._db_event(event)
        StripeWebhookHandler._dispatch(event, db_event)
        return db_event

    # --- Happy Path -----------------------------------------------------

    @patch('core.services.webhook.MailService.send_template')
    def test_completed_creates_customer_subscription_and_master_instance(self, mock_mail):
        event = _checkout_event(self.order)
        db_event = self._handle(event)

        customer = Customer.objects.get(slug='acme')
        self.assertEqual(customer.stripe_customer_id, 'cus_test_1')
        self.assertEqual(customer.company_name, 'Acme GmbH')
        self.assertEqual(customer.billing_city, 'München')

        subscription = Subscription.objects.get(customer=customer)
        self.assertEqual(subscription.stripe_subscription_id, 'sub_test_1')
        self.assertEqual(subscription.stripe_status, 'trialing')
        self.assertIsNotNone(subscription.trial_end)
        self.assertEqual(subscription.user_seats_total, 5)
        self.assertTrue(subscription.ai_addon_active)

        master = customer.master_instance
        self.assertIsNotNone(master)
        self.assertEqual(master.status, 'provisioning')
        self.assertEqual(master.slug, 'acme')
        self.assertIsNone(master.claimed_at)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'completed')

        db_event.refresh_from_db()
        self.assertEqual(db_event.customer, customer)

        mock_mail.assert_called_once()
        _, kwargs = mock_mail.call_args
        self.assertEqual(kwargs['template'], 'order_confirmed')
        self.assertEqual(kwargs['to'], 'max@acme.de')
        self.assertEqual(kwargs['context']['instance_url'], 'https://acme.zenico.app')
        self.assertNotEqual(kwargs['context']['trial_end_date'], '')

    @patch('core.services.webhook.MailService.send_template')
    def test_master_instance_appears_in_pending_query(self, mock_mail):
        """Die Master-Instanz muss vom Provisioner-Poll abgeholt werden können."""
        self._handle(_checkout_event(self.order))

        pending = Instance.objects.filter(status='provisioning', claimed_at__isnull=True)
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first().slug, 'acme')

    @patch('core.services.webhook.MailService.send_template')
    def test_session_without_metadata_found_via_session_id(self, mock_mail):
        event = _checkout_event(self.order, with_metadata=True)
        event['data']['object']['metadata'] = {}
        self._handle(event)

        self.assertTrue(Customer.objects.filter(slug='acme').exists())

    # --- Idempotenz -----------------------------------------------------

    @patch('core.services.webhook.MailService.send_template')
    def test_duplicate_delivery_creates_no_duplicates(self, mock_mail):
        event = _checkout_event(self.order)
        self._handle(event)
        # Zweite Zustellung desselben logischen Events (neue StripeEvent-Row,
        # z. B. anderer Event-Versuch) darf nichts doppeln.
        event2 = _checkout_event(self.order)
        event2['id'] = 'evt_test_2'
        self._handle(event2)

        self.assertEqual(Customer.objects.filter(slug='acme').count(), 1)
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertEqual(Instance.objects.filter(slug='acme').count(), 1)

    # --- Fremde / unbekannte Session -----------------------------------

    @patch('core.services.webhook.MailService.send_template')
    def test_unknown_session_is_ignored(self, mock_mail):
        event = _checkout_event(self.order, session_id='cs_foreign', with_metadata=False)
        # Kein passender Order (weder metadata noch session_id treffen)
        self._handle(event)

        self.assertFalse(Customer.objects.exists())
        mock_mail.assert_not_called()

    # --- Slug-Kollision -------------------------------------------------

    @patch('core.services.webhook.MailService.send_template')
    def test_slug_collision_fails_order_and_notifies_admin(self, mock_mail):
        # Slug wurde seit Bestellung anderweitig vergeben.
        Customer.objects.create(
            slug='acme',
            company_name='Other GmbH',
            contact_name='X',
            contact_email='x@other.de',
            billing_email='x@other.de',
            billing_address='a', billing_city='b', billing_postal_code='c',
        )

        self._handle(_checkout_event(self.order))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'failed')
        # Kein zweiter Kunde, keine Subscription/Instanz.
        self.assertEqual(Customer.objects.filter(slug='acme').count(), 1)
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertEqual(Instance.objects.count(), 0)

        mock_mail.assert_called_once()
        _, kwargs = mock_mail.call_args
        self.assertEqual(kwargs['template'], 'admin_order_failed')

    # --- Expired --------------------------------------------------------

    @patch('core.services.webhook.MailService.send_template')
    def test_expired_sets_order_expired(self, mock_mail):
        event = _checkout_event(self.order, event_type='checkout.session.expired')
        self._handle(event)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'expired')
        self.assertFalse(Customer.objects.exists())

    @patch('core.services.webhook.MailService.send_template')
    def test_expired_does_not_downgrade_completed_order(self, mock_mail):
        self.order.status = 'completed'
        self.order.save(update_fields=['status'])

        event = _checkout_event(self.order, event_type='checkout.session.expired')
        self._handle(event)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'completed')
