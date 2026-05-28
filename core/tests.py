"""
Tests for AuditService.

Tests that AuditService is the correct way to create audit logs and that
direct updates to AuditLog are prevented.
"""

import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from customers.models import Customer
from audit.models import AuditLog
from core.services.audit import AuditService, AuditAction


class AuditServiceTests(TestCase):
    """Test suite for AuditService."""

    def setUp(self):
        """Set up test data."""
        self.customer = Customer.objects.create(
            slug='testcust',
            company_name='Test Company',
            contact_name='Test User',
            contact_email='test@example.com',
            billing_email='billing@example.com',
        )

    def test_log_creates_audit_entry(self):
        """Test that log() creates a valid AuditLog entry."""
        audit_log = AuditService.log(
            action=AuditAction.CUSTOMER_CREATED,
            resource_type='Customer',
            resource_id=str(self.customer.id),
            actor_email='admin@example.com',
            customer=self.customer,
            after={'slug': 'testcust', 'company_name': 'Test Company'},
            note='Customer created via API',
        )

        self.assertIsInstance(audit_log, AuditLog)
        self.assertEqual(audit_log.action, AuditAction.CUSTOMER_CREATED)
        self.assertEqual(audit_log.resource_type, 'Customer')
        self.assertEqual(audit_log.resource_id, str(self.customer.id))
        self.assertEqual(audit_log.actor_email, 'admin@example.com')
        self.assertEqual(audit_log.customer, self.customer)
        self.assertEqual(audit_log.after, {'slug': 'testcust', 'company_name': 'Test Company'})
        self.assertEqual(audit_log.note, 'Customer created via API')
        self.assertIsNotNone(audit_log.created_at)

    def test_log_with_system_actor(self):
        """Test that log() uses 'system' as default actor."""
        audit_log = AuditService.log(
            action=AuditAction.CUSTOMER_CREATED,
            resource_type='Customer',
            resource_id=str(self.customer.id),
        )

        self.assertEqual(audit_log.actor_email, 'system')

    def test_log_with_instance_id(self):
        """Test that log() correctly stores instance_id."""
        instance_uuid = uuid.uuid4()
        audit_log = AuditService.log(
            action=AuditAction.INSTANCE_PROVISIONED,
            resource_type='Instance',
            resource_id=str(instance_uuid),
            instance_id=instance_uuid,
            customer=self.customer,
        )

        self.assertEqual(audit_log.instance_id, instance_uuid)

    def test_log_with_actor_ip(self):
        """Test that log() correctly stores actor IP."""
        audit_log = AuditService.log(
            action=AuditAction.CUSTOMER_CREATED,
            resource_type='Customer',
            resource_id=str(self.customer.id),
            actor_email='admin@example.com',
            actor_ip='192.168.1.1',
        )

        self.assertEqual(audit_log.actor_ip, '192.168.1.1')

    def test_log_with_before_and_after(self):
        """Test that log() correctly stores before/after states."""
        before_state = {'status': 'active'}
        after_state = {'status': 'suspended'}

        audit_log = AuditService.log(
            action=AuditAction.CUSTOMER_SUSPENDED,
            resource_type='Customer',
            resource_id=str(self.customer.id),
            customer=self.customer,
            before=before_state,
            after=after_state,
            note='Customer suspended due to payment failure',
        )

        self.assertEqual(audit_log.before, before_state)
        self.assertEqual(audit_log.after, after_state)

    def test_audit_log_cannot_be_updated(self):
        """Test that attempting to update an AuditLog entry raises ValueError."""
        audit_log = AuditService.log(
            action=AuditAction.CUSTOMER_CREATED,
            resource_type='Customer',
            resource_id=str(self.customer.id),
        )

        # Try to update the audit log
        audit_log.note = 'Attempted update'

        with self.assertRaises(ValueError) as context:
            audit_log.save()

        self.assertIn('append-only', str(context.exception).lower())

    def test_audit_action_constants_exist(self):
        """Test that all required AuditAction constants are defined."""
        # Customer actions
        self.assertEqual(AuditAction.CUSTOMER_CREATED, 'customer.created')
        self.assertEqual(AuditAction.CUSTOMER_SUSPENDED, 'customer.suspended')
        self.assertEqual(AuditAction.CUSTOMER_REACTIVATED, 'customer.reactivated')
        self.assertEqual(AuditAction.CUSTOMER_CANCELLED, 'customer.cancelled')

        # Instance actions
        self.assertEqual(AuditAction.INSTANCE_PROVISIONED, 'instance.provisioned')
        self.assertEqual(AuditAction.INSTANCE_SUSPENDED, 'instance.suspended')
        self.assertEqual(AuditAction.INSTANCE_REACTIVATED, 'instance.reactivated')
        self.assertEqual(AuditAction.INSTANCE_DEPROVISIONED, 'instance.deprovisioned')
        self.assertEqual(AuditAction.INSTANCE_SEATS_CHANGED, 'instance.seats_changed')

        # Subscription actions
        self.assertEqual(AuditAction.SUBSCRIPTION_CREATED, 'subscription.created')
        self.assertEqual(AuditAction.SUBSCRIPTION_UPDATED, 'subscription.updated')
        self.assertEqual(AuditAction.SUBSCRIPTION_CANCELLED, 'subscription.cancelled')
        self.assertEqual(AuditAction.SEATS_CHANGED, 'subscription.seats_changed')

        # API Key actions
        self.assertEqual(AuditAction.API_KEY_REGENERATED, 'api_key.regenerated')

        # User License actions
        self.assertEqual(AuditAction.LICENSE_ACTIVATED, 'user_license.activated')
        self.assertEqual(AuditAction.LICENSE_DEACTIVATED, 'user_license.deactivated')

        # Mail actions
        self.assertEqual(AuditAction.MAIL_SENT, 'mail.sent')
        self.assertEqual(AuditAction.MAIL_FAILED, 'mail.failed')

        # Stripe actions
        self.assertEqual(AuditAction.STRIPE_WEBHOOK_RECEIVED, 'stripe.webhook_received')
        self.assertEqual(AuditAction.STRIPE_WEBHOOK_PROCESSED, 'stripe.webhook_processed')
        self.assertEqual(AuditAction.STRIPE_WEBHOOK_FAILED, 'stripe.webhook_failed')

    def test_multiple_audit_logs_can_be_created(self):
        """Test that multiple audit log entries can be created."""
        log1 = AuditService.log(
            action=AuditAction.CUSTOMER_CREATED,
            resource_type='Customer',
            resource_id=str(self.customer.id),
        )
        log2 = AuditService.log(
            action=AuditAction.CUSTOMER_SUSPENDED,
            resource_type='Customer',
            resource_id=str(self.customer.id),
        )

        self.assertNotEqual(log1.id, log2.id)
        self.assertEqual(AuditLog.objects.count(), 2)


class MailServiceTests(TestCase):
    """Test suite for MailService."""

    def setUp(self):
        """Set up test data."""
        # Set required environment variables for tests
        import os
        os.environ['AZURE_TENANT_ID'] = 'test-tenant-id'
        os.environ['AZURE_CLIENT_ID'] = 'test-client-id'
        os.environ['AZURE_CLIENT_SECRET'] = 'test-client-secret'
        os.environ['MAIL_FROM_ADDRESS'] = 'test@zenico.app'
        os.environ['MAIL_FROM_NAME'] = 'Test Zenico'

    def test_send_with_mocked_graph_api(self):
        """Test that send() calls Graph API correctly."""
        from core.services.mail import MailService
        from unittest.mock import patch, MagicMock

        # Mock the MSAL token acquisition
        with patch.object(MailService, '_get_access_token', return_value='fake-token'):
            # Mock the requests.post call
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 202
                mock_post.return_value = mock_response

                result = MailService.send(
                    to='recipient@example.com',
                    subject='Test Subject',
                    html_body='<p>Test body</p>',
                )

                self.assertTrue(result)
                # Verify requests.post was called
                mock_post.assert_called_once()
                call_args = mock_post.call_args
                self.assertIn('https://graph.microsoft.com', call_args[0][0])

                # Verify audit log was created
                self.assertEqual(AuditLog.objects.filter(action=AuditAction.MAIL_SENT).count(), 1)

    def test_send_failure_logs_error(self):
        """Test that failed send() logs error."""
        from core.services.mail import MailService
        from unittest.mock import patch, MagicMock

        with patch.object(MailService, '_get_access_token', return_value='fake-token'):
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.text = 'Bad Request'
                mock_post.return_value = mock_response

                result = MailService.send(
                    to='recipient@example.com',
                    subject='Test Subject',
                    html_body='<p>Test body</p>',
                )

                self.assertFalse(result)
                # Verify audit log was created for failure
                self.assertEqual(AuditLog.objects.filter(action=AuditAction.MAIL_FAILED).count(), 1)

    def test_send_exception_logs_error(self):
        """Test that exception during send() logs error."""
        from core.services.mail import MailService
        from unittest.mock import patch

        with patch.object(MailService, '_get_access_token', side_effect=Exception('Token error')):
            result = MailService.send(
                to='recipient@example.com',
                subject='Test Subject',
                html_body='<p>Test body</p>',
            )

            self.assertFalse(result)
            # Verify audit log was created for failure
            failed_logs = AuditLog.objects.filter(action=AuditAction.MAIL_FAILED)
            self.assertEqual(failed_logs.count(), 1)
            self.assertIn('Token error', failed_logs.first().after['error'])

    def test_send_with_multiple_recipients(self):
        """Test sending to multiple recipients."""
        from core.services.mail import MailService
        from unittest.mock import patch, MagicMock

        with patch.object(MailService, '_get_access_token', return_value='fake-token'):
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 202
                mock_post.return_value = mock_response

                result = MailService.send(
                    to=['recipient1@example.com', 'recipient2@example.com'],
                    subject='Test Subject',
                    html_body='<p>Test body</p>',
                )

                self.assertTrue(result)
                # Verify the call included both recipients
                call_args = mock_post.call_args
                message = call_args[1]['json']['message']
                self.assertEqual(len(message['toRecipients']), 2)

    def test_send_template_renders_and_sends(self):
        """Test that send_template() renders template and sends."""
        from core.services.mail import MailService
        from unittest.mock import patch, MagicMock

        with patch.object(MailService, '_get_access_token', return_value='fake-token'):
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 202
                mock_post.return_value = mock_response

                result = MailService.send_template(
                    to='recipient@example.com',
                    template='welcome',
                    context={
                        'contact_name': 'John Doe',
                        'company_name': 'Test Company',
                        'slug': 'testco',
                        'plan_name': 'Professional',
                        'user_seats': 10,
                        'instance_seats': 2,
                    },
                    subject_override='Welcome to Zenico',
                )

                self.assertTrue(result)
                # Verify email was sent
                self.assertEqual(AuditLog.objects.filter(action=AuditAction.MAIL_SENT).count(), 1)

    def test_send_template_with_invalid_template(self):
        """Test that send_template() handles template errors."""
        from core.services.mail import MailService

        result = MailService.send_template(
            to='recipient@example.com',
            template='nonexistent_template',
            context={},
        )

        self.assertFalse(result)
        # Verify error was logged
        self.assertEqual(AuditLog.objects.filter(action=AuditAction.MAIL_FAILED).count(), 1)

