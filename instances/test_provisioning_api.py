from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from customers.models import Plan, Customer, Subscription
from instances.models import Instance


@override_settings(PROVISIONING_AGENT_TOKEN='test-agent-token')
class CompleteInstanceViewMailTest(TestCase):
    """Tests for the 'instance ready' mail triggered by POST .../complete/."""

    def setUp(self):
        self.plan = Plan.objects.filter(name='standard').first()
        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Company',
            contact_name='John Doe',
            contact_email='john@testco.com',
            billing_email='billing@testco.com',
            billing_address='123 Test St',
            billing_city='Test City',
            billing_postal_code='12345',
            billing_country='DE',
            status='active',
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=3,
        )
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master Instance',
            is_master=True,
            status='provisioning',
            claimed_at=timezone.now(),
        )
        self.url = reverse('api:provisioning-complete', args=[self.instance.id])

    def _post_complete(self):
        return self.client.post(
            self.url,
            data={'server_host': 'docker-host-01'},
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer test-agent-token',
        )

    @patch('instances.services.MailService.send_template')
    def test_complete_sends_instance_ready_mail(self, mock_send_template):
        mock_send_template.return_value = True

        response = self._post_complete()

        self.assertEqual(response.status_code, 200)
        mock_send_template.assert_called_once()
        call_kwargs = mock_send_template.call_args.kwargs
        self.assertEqual(call_kwargs['to'], 'john@testco.com')
        self.assertEqual(call_kwargs['template'], 'instance_ready')
        self.assertEqual(
            call_kwargs['context']['instance_url'], f'https://{self.instance.fqdn}'
        )

        self.instance.refresh_from_db()
        self.assertIsNotNone(self.instance.instance_ready_mail_sent_at)
        self.assertTrue(
            AuditLog.objects.filter(
                action='instance.ready_mail_sent', instance_id=self.instance.id
            ).exists()
        )

    @patch('instances.services.MailService.send_template')
    def test_retry_does_not_send_second_mail(self, mock_send_template):
        mock_send_template.return_value = True

        first = self._post_complete()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(mock_send_template.call_count, 1)

        # Simulate a retry: instance is already active, complete/ rejects it,
        # but even a direct re-invocation of the mail step must stay idempotent.
        from instances.services import send_instance_ready_mail

        self.instance.refresh_from_db()
        send_instance_ready_mail(self.instance)

        self.assertEqual(mock_send_template.call_count, 1)

    def test_retry_after_active_returns_conflict(self):
        with patch('instances.services.MailService.send_template', return_value=True) as mock_send:
            first = self._post_complete()
            self.assertEqual(first.status_code, 200)
            self.assertEqual(mock_send.call_count, 1)

            second = self._post_complete()
            self.assertEqual(second.status_code, 409)
            self.assertEqual(mock_send.call_count, 1)

    @patch('instances.services.MailService.send_template')
    def test_mail_failure_does_not_fail_complete_response(self, mock_send_template):
        mock_send_template.side_effect = Exception('Graph API unreachable')

        response = self._post_complete()

        self.assertEqual(response.status_code, 200)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, 'active')
        self.assertIsNone(self.instance.instance_ready_mail_sent_at)
