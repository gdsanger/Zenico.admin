from django.test import TestCase
from django.utils import timezone
from customers.models import Customer, Plan, Subscription
from .models import AuditLog
import uuid


class AuditLogModelTest(TestCase):
    """Test cases for the AuditLog model."""

    def setUp(self):
        """Set up test data."""
        # Use the existing 'starter' plan from data migration or create if it doesn't exist
        self.plan = Plan.objects.filter(name='starter').first()
        if not self.plan:
            self.plan = Plan.objects.create(
                name='starter',
                display_name='Test Starter Plan'
            )

        # Create a test customer
        self.customer = Customer.objects.create(
            slug='testcust',
            company_name='Test Company',
            contact_name='Test Contact',
            contact_email='contact@test.com',
            billing_email='billing@test.com',
            billing_address='123 Test St',
            billing_city='Test City',
            billing_postal_code='12345',
            billing_country='DE'
        )

        # Create a test subscription
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active'
        )

    def test_create_audit_log(self):
        """Test creating a basic audit log entry."""
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            action='customer.created',
            resource_type='Customer',
            resource_id=str(self.customer.id)
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.customer, self.customer)
        self.assertEqual(log.actor_email, 'admin@test.com')
        self.assertEqual(log.action, 'customer.created')
        self.assertIsNotNone(log.created_at)

    def test_audit_log_with_system_actor(self):
        """Test creating an audit log with 'system' as actor."""
        log = AuditLog.objects.create(
            actor_email='system',
            action='instance.provisioned',
            resource_type='Instance',
            resource_id=str(uuid.uuid4())
        )
        self.assertEqual(log.actor_email, 'system')
        self.assertIsNone(log.customer)

    def test_audit_log_with_instance_id(self):
        """Test creating an audit log with instance_id."""
        instance_id = uuid.uuid4()
        log = AuditLog.objects.create(
            customer=self.customer,
            instance_id=instance_id,
            actor_email='admin@test.com',
            action='instance.provisioned',
            resource_type='Instance',
            resource_id=str(instance_id)
        )
        self.assertEqual(log.instance_id, instance_id)

    def test_audit_log_with_ip_address(self):
        """Test creating an audit log with IP address."""
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            actor_ip='192.168.1.1',
            action='customer.suspended',
            resource_type='Customer',
            resource_id=str(self.customer.id)
        )
        self.assertEqual(log.actor_ip, '192.168.1.1')

    def test_audit_log_with_ipv6_address(self):
        """Test creating an audit log with IPv6 address."""
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            actor_ip='2001:0db8:85a3:0000:0000:8a2e:0370:7334',
            action='customer.reactivated',
            resource_type='Customer',
            resource_id=str(self.customer.id)
        )
        self.assertEqual(log.actor_ip, '2001:0db8:85a3:0000:0000:8a2e:0370:7334')

    def test_audit_log_with_before_after(self):
        """Test creating an audit log with before/after states."""
        before_state = {'status': 'active', 'user_seats': 5}
        after_state = {'status': 'suspended', 'user_seats': 5}

        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            action='customer.suspended',
            resource_type='Customer',
            resource_id=str(self.customer.id),
            before=before_state,
            after=after_state
        )
        self.assertEqual(log.before, before_state)
        self.assertEqual(log.after, after_state)

    def test_audit_log_with_note(self):
        """Test creating an audit log with a note."""
        note_text = 'Suspended due to non-payment'
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            action='customer.suspended',
            resource_type='Customer',
            resource_id=str(self.customer.id),
            note=note_text
        )
        self.assertEqual(log.note, note_text)

    def test_audit_log_update_raises_value_error(self):
        """Test that updating an existing audit log raises ValueError."""
        # Create an audit log
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            action='customer.created',
            resource_type='Customer',
            resource_id=str(self.customer.id)
        )

        # Try to update it
        log.action = 'customer.updated'
        with self.assertRaises(ValueError) as context:
            log.save()

        self.assertIn('append-only', str(context.exception).lower())

    def test_audit_log_update_via_queryset_still_allowed(self):
        """Test that queryset updates bypass the save() override (Django behavior)."""
        # Create an audit log
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            action='customer.created',
            resource_type='Customer',
            resource_id=str(self.customer.id)
        )

        # This test documents that bulk updates bypass save()
        # In production, this should be prevented at the database level or via permissions
        original_action = log.action
        AuditLog.objects.filter(pk=log.pk).update(action='should.not.happen')
        log.refresh_from_db()
        # The update went through because .update() bypasses save()
        self.assertNotEqual(log.action, original_action)

    def test_audit_log_str_method(self):
        """Test the __str__ method."""
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            action='customer.created',
            resource_type='Customer',
            resource_id=str(self.customer.id)
        )
        str_repr = str(log)
        self.assertIn('customer.created', str_repr)
        self.assertIn('admin@test.com', str_repr)

    def test_audit_log_uuid_primary_key(self):
        """Test that audit logs use UUID as primary key."""
        log = AuditLog.objects.create(
            actor_email='admin@test.com',
            action='test.action',
            resource_type='Test',
            resource_id='123'
        )
        self.assertIsNotNone(log.id)
        # Check that it's a valid UUID
        self.assertIsInstance(log.id, uuid.UUID)

    def test_audit_log_timestamp_auto_created(self):
        """Test that created_at is automatically set."""
        log = AuditLog.objects.create(
            actor_email='admin@test.com',
            action='test.action',
            resource_type='Test',
            resource_id='123'
        )
        self.assertIsNotNone(log.created_at)
        # Should be very recent
        time_diff = timezone.now() - log.created_at
        self.assertLess(time_diff.total_seconds(), 5)

    def test_audit_log_ordering(self):
        """Test that audit logs are ordered by created_at descending."""
        # Create multiple logs
        log1 = AuditLog.objects.create(
            actor_email='admin@test.com',
            action='action.first',
            resource_type='Test',
            resource_id='1'
        )
        log2 = AuditLog.objects.create(
            actor_email='admin@test.com',
            action='action.second',
            resource_type='Test',
            resource_id='2'
        )
        log3 = AuditLog.objects.create(
            actor_email='admin@test.com',
            action='action.third',
            resource_type='Test',
            resource_id='3'
        )

        # Get all logs
        logs = list(AuditLog.objects.all())

        # Should be in reverse chronological order
        self.assertEqual(logs[0].action, 'action.third')
        self.assertEqual(logs[1].action, 'action.second')
        self.assertEqual(logs[2].action, 'action.first')

    def test_audit_log_customer_set_null(self):
        """Test that customer FK uses SET_NULL on delete."""
        log = AuditLog.objects.create(
            customer=self.customer,
            actor_email='admin@test.com',
            action='customer.created',
            resource_type='Customer',
            resource_id=str(self.customer.id)
        )

        customer_id = self.customer.id
        # Delete subscription first (PROTECT FK)
        self.subscription.delete()
        self.customer.delete()

        log.refresh_from_db()
        self.assertIsNone(log.customer)
        # But the resource_id should still have the customer ID
        self.assertEqual(log.resource_id, str(customer_id))

    def test_standard_actions_examples(self):
        """Test creating logs with various standard action types."""
        actions = [
            'customer.created',
            'customer.suspended',
            'customer.reactivated',
            'instance.provisioned',
            'instance.suspended',
            'instance.deprovisioned',
            'instance.seats_changed',
            'subscription.created',
            'subscription.seats_changed',
            'api_key.regenerated',
            'user_license.activated',
            'user_license.deactivated',
        ]

        for action in actions:
            log = AuditLog.objects.create(
                actor_email='system',
                action=action,
                resource_type='Test',
                resource_id='123'
            )
            self.assertEqual(log.action, action)
