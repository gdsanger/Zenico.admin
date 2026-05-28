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
