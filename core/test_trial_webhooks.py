"""
Tests für das Trial-Ende-Handling im StripeWebhookHandler (#920):
`customer.subscription.trial_will_end` (Erinnerungsmail) und die
Trial->aktiv-Synchronisierung in `customer.subscription.updated`.

Stripe ist vollständig gemockt — es werden nur die Handler-Methoden direkt mit
konstruierten Event-Payloads aufgerufen.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from billing.models import StripeEvent
from customers.models import Plan, Customer, Subscription
from core.services.webhook import StripeWebhookHandler


class TrialWebhookTestCase(TestCase):
    """Gemeinsames Setup: Kunde mit einer Subscription in Trial."""

    def setUp(self):
        self.plan = Plan.objects.filter(name='standard').first()
        if self.plan is None:
            self.plan = Plan.objects.create(name='standard', display_name='Standard')
        self.plan.price_per_user = Decimal('4.99')
        self.plan.save()

        self.customer = Customer.objects.create(
            slug='acme',
            company_name='Acme GmbH',
            contact_name='Max Muster',
            contact_email='max@acme.de',
            billing_email='rechnung@acme.de',
            billing_address='Hauptstr. 1',
            billing_city='München',
            billing_postal_code='80331',
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test_1',
            stripe_status='trialing',
            user_seats_total=5,
            instance_seats_total=1,
        )

    def _dispatch(self, event):
        db_event = StripeEvent.objects.create(
            stripe_event_id=event['id'],
            event_type=event['type'],
            payload=event,
        )
        StripeWebhookHandler._dispatch(event, db_event)
        return db_event


class TrialWillEndTest(TrialWebhookTestCase):
    """Tests für customer.subscription.trial_will_end."""

    @patch('core.services.webhook.MailService.send_template')
    def test_sends_reminder_with_price_and_trial_end(self, mock_mail):
        event = {
            'id': 'evt_trial_1',
            'type': 'customer.subscription.trial_will_end',
            'data': {'object': {
                'id': 'sub_test_1',
                'customer': 'cus_test_1',
                'trial_end': 1735689600,  # 2025-01-01T00:00:00Z
            }},
        }
        db_event = self._dispatch(event)

        mock_mail.assert_called_once()
        _, kwargs = mock_mail.call_args
        self.assertEqual(kwargs['template'], 'trial_will_end')
        self.assertEqual(kwargs['to'], 'rechnung@acme.de')
        self.assertEqual(kwargs['context']['trial_end_date'], '01.01.2025')
        self.assertEqual(kwargs['context']['monthly_price'], '24.95')  # 4.99 * 5 seats

        db_event.refresh_from_db()
        self.assertEqual(db_event.customer, self.customer)

    @patch('core.services.webhook.MailService.send_template')
    def test_unknown_subscription_is_ignored(self, mock_mail):
        event = {
            'id': 'evt_trial_2',
            'type': 'customer.subscription.trial_will_end',
            'data': {'object': {'id': 'sub_unknown', 'customer': 'cus_x', 'trial_end': 1735689600}},
        }
        self._dispatch(event)
        mock_mail.assert_not_called()


class SubscriptionUpdatedTrialConversionTest(TrialWebhookTestCase):
    """Tests für den stillen Trial->aktiv-Übergang in customer.subscription.updated."""

    @patch('core.services.webhook.MailService.send_template')
    def test_trial_to_active_updates_status_without_email(self, mock_mail):
        event = {
            'id': 'evt_sub_updated_1',
            'type': 'customer.subscription.updated',
            'data': {'object': {
                'id': 'sub_test_1',
                'status': 'active',
                'trial_end': None,
            }},
        }
        self._dispatch(event)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.stripe_status, 'active')
        self.assertIsNone(self.subscription.trial_end)
        mock_mail.assert_not_called()

    @patch('core.services.webhook.MailService.send_template')
    def test_past_due_to_active_still_sends_email(self, mock_mail):
        self.subscription.stripe_status = 'past_due'
        self.subscription.save(update_fields=['stripe_status'])

        event = {
            'id': 'evt_sub_updated_2',
            'type': 'customer.subscription.updated',
            'data': {'object': {
                'id': 'sub_test_1',
                'status': 'active',
                'trial_end': None,
            }},
        }
        self._dispatch(event)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.stripe_status, 'active')
        mock_mail.assert_called_once()
        _, kwargs = mock_mail.call_args
        self.assertEqual(kwargs['template'], 'subscription_updated')
