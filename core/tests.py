"""
Tests for AuditService.

Tests that AuditService is the correct way to create audit logs and that
direct updates to AuditLog are prevented.
"""

import uuid
from decimal import Decimal
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


class StripeServiceTests(TestCase):
    """Test suite for StripeService."""

    def setUp(self):
        """Set up test data."""
        import os
        os.environ['STRIPE_SECRET_KEY'] = 'sk_test_fake'
        os.environ['STRIPE_TAX_ENABLED'] = 'true'

        from customers.models import Plan
        # Use existing plan from migration or get_or_create to avoid unique constraint error
        self.plan, _ = Plan.objects.get_or_create(
            name='professional',
            defaults={
                'display_name': 'Professional Plan',
                'price_per_user': 19.00,
                'price_per_instance': 5.00,
                'price_ai_addon': 7.50,
                'stripe_price_id_user': 'price_user_123',
                'stripe_price_id_instance': 'price_instance_123',
                'stripe_price_id_ai': 'price_ai_123',
            }
        )
        # Update the plan to ensure stripe price IDs are set
        if not self.plan.stripe_price_id_user:
            self.plan.stripe_price_id_user = 'price_user_123'
            self.plan.stripe_price_id_instance = 'price_instance_123'
            self.plan.stripe_price_id_ai = 'price_ai_123'
            self.plan.save()

        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Company',
            contact_name='Test User',
            contact_email='test@example.com',
            billing_email='billing@example.com',
            stripe_customer_id='cus_test123',
        )

    def test_create_customer_success(self):
        """Test successful Stripe customer creation."""
        from core.services.stripe import StripeService
        from unittest.mock import patch, MagicMock

        # Create customer without stripe_customer_id
        new_customer = Customer.objects.create(
            slug='newco',
            company_name='New Company',
            contact_name='New User',
            contact_email='new@example.com',
            billing_email='billing@newco.com',
        )

        with patch('stripe.Customer.create') as mock_create:
            mock_stripe_customer = MagicMock()
            mock_stripe_customer.id = 'cus_new123'
            mock_create.return_value = mock_stripe_customer

            stripe_customer_id = StripeService.create_customer(new_customer)

            self.assertEqual(stripe_customer_id, 'cus_new123')
            new_customer.refresh_from_db()
            self.assertEqual(new_customer.stripe_customer_id, 'cus_new123')

            # Verify audit log
            self.assertTrue(AuditLog.objects.filter(
                action='stripe.customer_created',
                resource_id='cus_new123'
            ).exists())

    def test_update_customer_success(self):
        """Test successful Stripe customer update."""
        from core.services.stripe import StripeService
        from unittest.mock import patch

        with patch('stripe.Customer.modify') as mock_modify:
            StripeService.update_customer(self.customer)

            mock_modify.assert_called_once_with(
                'cus_test123',
                name='Test Company',
                email='billing@example.com',
            )

            # Verify audit log
            self.assertTrue(AuditLog.objects.filter(
                action='stripe.customer_updated',
                customer=self.customer
            ).exists())

    def test_create_subscription_with_all_items(self):
        """Test creating subscription with user, instance, and AI addon."""
        from core.services.stripe import StripeService
        from unittest.mock import patch, MagicMock

        with patch('stripe.Subscription.create') as mock_create:
            mock_subscription = MagicMock()
            mock_subscription.id = 'sub_test123'
            mock_create.return_value = mock_subscription

            result = StripeService.create_subscription(
                customer=self.customer,
                plan=self.plan,
                user_seats=10,
                instance_seats=2,
                ai_addon=True,
                trial_days=14,
            )

            self.assertEqual(result.id, 'sub_test123')

            # Verify call arguments
            call_kwargs = mock_create.call_args.kwargs if hasattr(mock_create.call_args, 'kwargs') else mock_create.call_args[1]
            self.assertEqual(call_kwargs['customer'], 'cus_test123')
            self.assertEqual(len(call_kwargs['items']), 3)  # user + instance + AI
            self.assertEqual(call_kwargs['trial_period_days'], 14)
            self.assertTrue(call_kwargs['automatic_tax']['enabled'])

            # Verify audit log
            self.assertTrue(AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_CREATED,
                resource_id='sub_test123'
            ).exists())

    def test_cancel_subscription_at_period_end(self):
        """Test cancelling subscription at period end."""
        from core.services.stripe import StripeService
        from customers.models import Subscription
        from unittest.mock import patch, MagicMock

        subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=2,
        )

        with patch('stripe.Subscription.modify') as mock_modify:
            mock_cancelled = MagicMock()
            mock_cancelled.status = 'active'
            mock_modify.return_value = mock_cancelled

            result = StripeService.cancel_subscription(subscription, at_period_end=True)

            mock_modify.assert_called_once_with(
                'sub_test123',
                cancel_at_period_end=True,
            )

            # Verify audit log
            self.assertTrue(AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_CANCELLED,
                resource_id='sub_test123'
            ).exists())

    def test_sync_invoice_creates_new(self):
        """Test syncing invoice from Stripe creates new local invoice."""
        from core.services.stripe import StripeService

        stripe_invoice_data = {
            'id': 'in_test123',
            'customer': 'cus_test123',
            'subscription': None,
            'amount_due': 19900,  # $199.00 in cents
            'amount_paid': 19900,
            'currency': 'usd',
            'status': 'paid',
            'hosted_invoice_url': 'https://stripe.com/invoice/test',
            'invoice_pdf': 'https://stripe.com/invoice/test.pdf',
        }

        invoice = StripeService.sync_invoice(stripe_invoice_data, self.customer)

        self.assertEqual(invoice.stripe_invoice_id, 'in_test123')
        self.assertEqual(invoice.customer, self.customer)
        self.assertEqual(invoice.amount_due, Decimal('199.00'))
        self.assertEqual(invoice.status, 'paid')

        # Verify audit log
        self.assertTrue(AuditLog.objects.filter(
            action='stripe.invoice_synced',
            resource_id='in_test123'
        ).exists())

    def test_create_billing_portal_session(self):
        """Test creating Stripe billing portal session."""
        from core.services.stripe import StripeService
        from unittest.mock import patch, MagicMock

        with patch('stripe.billing_portal.Session.create') as mock_create:
            mock_session = MagicMock()
            mock_session.id = 'bps_test123'
            mock_session.url = 'https://billing.stripe.com/session/test'
            mock_create.return_value = mock_session

            portal_url = StripeService.create_billing_portal_session(
                self.customer,
                'https://admin.zenico.app/billing'
            )

            self.assertEqual(portal_url, 'https://billing.stripe.com/session/test')

            # Verify audit log
            self.assertTrue(AuditLog.objects.filter(
                action='stripe.portal_session_created',
                resource_id='bps_test123'
            ).exists())
