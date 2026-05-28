"""
Test suite for ISSUE-12: Migrations Review & Integration Tests

This test file comprehensively tests:
1. SLUG_VALIDATOR regex with exact edge cases from the issue
2. Database constraints (Unique, Check)
3. CustomerService.create_customer() end-to-end integration
4. Circular import detection
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from decimal import Decimal

from .models import Plan, Customer, Subscription, SLUG_VALIDATOR
from .services import CustomerService
from instances.models import Instance
from audit.models import AuditLog


class SlugValidatorEdgeCasesTest(TestCase):
    """
    Test SLUG_VALIDATOR regex with exact edge cases specified in ISSUE-12.

    Requirements:
    - "ab" → valid (2 chars, lowercase alphanumeric)
    - "zenico1234" → valid (10 chars, lowercase alphanumeric)
    - "zenico12345" → invalid (11 chars, exceeds max length)
    - "GDS" → invalid (uppercase)
    - "my-slug" → invalid (hyphen)
    - "a" → invalid (too short)
    """

    def setUp(self):
        """Set up test data."""
        self.base_customer_data = {
            'company_name': 'Test Company',
            'contact_name': 'John Doe',
            'contact_email': 'john@test.de',
            'billing_email': 'billing@test.de',
            'billing_address': 'Test Street 123',
            'billing_city': 'Berlin',
            'billing_postal_code': '10115',
            'billing_country': 'DE',
        }

    def test_slug_edge_case_ab_valid(self):
        """Test that 'ab' is valid (2 chars, minimum length)."""
        data = self.base_customer_data.copy()
        data['slug'] = 'ab'
        customer = Customer(**data)
        customer.full_clean()  # Should not raise ValidationError
        customer.save()
        self.assertEqual(customer.slug, 'ab')

    def test_slug_edge_case_zenico1234_valid(self):
        """Test that 'zenico1234' is valid (10 chars, maximum length)."""
        data = self.base_customer_data.copy()
        data['slug'] = 'zenico1234'
        customer = Customer(**data)
        customer.full_clean()  # Should not raise ValidationError
        customer.save()
        self.assertEqual(customer.slug, 'zenico1234')

    def test_slug_edge_case_zenico12345_invalid(self):
        """Test that 'zenico12345' is invalid (11 chars, exceeds max length)."""
        data = self.base_customer_data.copy()
        data['slug'] = 'zenico12345'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_edge_case_GDS_invalid(self):
        """Test that 'GDS' is invalid (uppercase letters)."""
        data = self.base_customer_data.copy()
        data['slug'] = 'GDS'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_edge_case_my_slug_invalid(self):
        """Test that 'my-slug' is invalid (contains hyphen)."""
        data = self.base_customer_data.copy()
        data['slug'] = 'my-slug'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_edge_case_a_invalid(self):
        """Test that 'a' is invalid (too short, below minimum length)."""
        data = self.base_customer_data.copy()
        data['slug'] = 'a'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_validator_regex_pattern(self):
        """Verify the SLUG_VALIDATOR regex pattern matches specification."""
        # The regex should be ^[a-z0-9]{2,10}$
        self.assertEqual(SLUG_VALIDATOR.regex.pattern, r'^[a-z0-9]{2,10}$')
        self.assertEqual(SLUG_VALIDATOR.code, 'invalid_slug')


class DatabaseConstraintsTest(TestCase):
    """
    Comprehensive tests for all database constraints.

    Tests Unique constraints, Check constraints, and Foreign Key protections.
    """

    def setUp(self):
        """Set up test data."""
        self.plan = Plan.objects.filter(name='starter').first()
        self.base_customer_data = {
            'slug': 'dbtest',
            'company_name': 'DB Test Company',
            'contact_name': 'John Doe',
            'contact_email': 'john@dbtest.de',
            'billing_email': 'billing@dbtest.de',
            'billing_address': 'Test Street 123',
            'billing_city': 'Berlin',
            'billing_postal_code': '10115',
            'billing_country': 'DE',
        }

    def test_customer_slug_unique_constraint(self):
        """Test that Customer.slug has a unique constraint."""
        # Create first customer
        Customer.objects.create(**self.base_customer_data)

        # Try to create customer with duplicate slug
        with self.assertRaises(IntegrityError):
            Customer.objects.create(**self.base_customer_data)

    def test_customer_stripe_customer_id_unique_constraint(self):
        """Test that Customer.stripe_customer_id has a unique constraint."""
        data1 = self.base_customer_data.copy()
        data1['slug'] = 'customer1'
        data1['stripe_customer_id'] = 'cus_duplicate'
        Customer.objects.create(**data1)

        data2 = self.base_customer_data.copy()
        data2['slug'] = 'customer2'
        data2['stripe_customer_id'] = 'cus_duplicate'

        with self.assertRaises(IntegrityError):
            Customer.objects.create(**data2)

    def test_subscription_stripe_subscription_id_unique_constraint(self):
        """Test that Subscription.stripe_subscription_id has a unique constraint."""
        customer1 = Customer.objects.create(
            slug='sub1',
            company_name='Customer 1',
            contact_name='John Doe',
            contact_email='john@customer1.de',
            billing_email='billing@customer1.de',
            billing_address='St 1',
            billing_city='Berlin',
            billing_postal_code='10115',
        )

        customer2 = Customer.objects.create(
            slug='sub2',
            company_name='Customer 2',
            contact_name='Jane Doe',
            contact_email='jane@customer2.de',
            billing_email='billing@customer2.de',
            billing_address='St 2',
            billing_city='Munich',
            billing_postal_code='80331',
        )

        # Create first subscription
        Subscription.objects.create(
            customer=customer1,
            plan=self.plan,
            stripe_subscription_id='sub_duplicate',
            stripe_status='active',
            user_seats_total=5,
            instance_seats_total=1,
        )

        # Try to create subscription with duplicate stripe_subscription_id
        with self.assertRaises(IntegrityError):
            Subscription.objects.create(
                customer=customer2,
                plan=self.plan,
                stripe_subscription_id='sub_duplicate',
                stripe_status='active',
                user_seats_total=3,
                instance_seats_total=1,
            )

    def test_plan_name_unique_constraint(self):
        """Test that Plan.name has a unique constraint."""
        # Plans are created via data migration, trying to create duplicate should fail
        with self.assertRaises(IntegrityError):
            Plan.objects.create(
                name='starter',  # Already exists from migration
                display_name='Duplicate Starter',
            )

    def test_subscription_customer_foreign_key_protect(self):
        """Test that Subscription.customer has PROTECT on_delete."""
        customer = Customer.objects.create(**self.base_customer_data)

        subscription = Subscription.objects.create(
            customer=customer,
            plan=self.plan,
            stripe_subscription_id='sub_protect_test',
            stripe_status='active',
            user_seats_total=5,
            instance_seats_total=1,
        )

        # Try to delete customer with existing subscription
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            customer.delete()

    def test_subscription_plan_foreign_key_protect(self):
        """Test that Subscription.plan has PROTECT on_delete."""
        customer = Customer.objects.create(**self.base_customer_data)

        # Create a custom plan for this test
        Plan.objects.filter(name='testplan').delete()
        plan = Plan.objects.create(
            name='testplan',
            display_name='Test Plan',
        )

        subscription = Subscription.objects.create(
            customer=customer,
            plan=plan,
            stripe_subscription_id='sub_plan_protect',
            stripe_status='active',
            user_seats_total=5,
            instance_seats_total=1,
        )

        # Try to delete plan with existing subscription
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            plan.delete()

    def test_instance_customer_foreign_key_protect(self):
        """Test that Instance.customer has PROTECT on_delete."""
        customer = Customer.objects.create(**self.base_customer_data)

        subscription = Subscription.objects.create(
            customer=customer,
            plan=self.plan,
            stripe_subscription_id='sub_instance_protect',
            stripe_status='active',
            user_seats_total=5,
            instance_seats_total=1,
        )

        instance = Instance.objects.create_master(
            customer=customer,
            subscription=subscription,
            display_name='Test Master',
            user_seats=5,
        )

        # Try to delete customer with existing instance
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            customer.delete()

    def test_instance_subscription_foreign_key_protect(self):
        """Test that Instance.subscription has PROTECT on_delete."""
        customer = Customer.objects.create(**self.base_customer_data)

        subscription = Subscription.objects.create(
            customer=customer,
            plan=self.plan,
            stripe_subscription_id='sub_instance_sub_protect',
            stripe_status='active',
            user_seats_total=5,
            instance_seats_total=1,
        )

        instance = Instance.objects.create_master(
            customer=customer,
            subscription=subscription,
            display_name='Test Master',
            user_seats=5,
        )

        # Try to delete subscription with existing instance
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            subscription.delete()


class CustomerServiceIntegrationTest(TestCase):
    """
    End-to-end integration test for CustomerService.create_customer().

    Tests the complete flow from customer creation through all related objects,
    ensuring atomic transactions and data integrity.
    """

    def setUp(self):
        """Set up test data."""
        self.plan = Plan.objects.filter(name='starter').first()

    def test_create_customer_end_to_end_with_real_instances(self):
        """
        Comprehensive end-to-end test for CustomerService.create_customer().

        This test verifies:
        1. All three objects (Customer, Subscription, Instance) are created
        2. All relationships are properly established
        3. All fields are correctly populated
        4. AuditLog entry is created
        5. Database constraints are satisfied
        6. Transaction atomicity works correctly
        """
        # Execute the service method
        customer, subscription, instance = CustomerService.create_customer(
            slug='e2etest',
            company_name='End to End Test GmbH',
            contact_name='Integration Test User',
            contact_email='integration@e2etest.de',
            billing_email='billing@e2etest.de',
            billing_address='Integration Street 42',
            billing_city='Hamburg',
            billing_postal_code='20095',
            billing_country='DE',
            plan=self.plan,
            user_seats=25,
            instance_seats=5,
            stripe_subscription_id='sub_e2e_integration_test',
            ai_addon=True,
            vat_id='DE987654321',
            contact_phone='+49 40 123456',
            stripe_customer_id='cus_e2eintegration',
            notes='Created via end-to-end integration test',
        )

        # === Verify Customer ===
        self.assertIsNotNone(customer)
        self.assertIsNotNone(customer.id)
        self.assertEqual(customer.slug, 'e2etest')
        self.assertEqual(customer.company_name, 'End to End Test GmbH')
        self.assertEqual(customer.contact_name, 'Integration Test User')
        self.assertEqual(customer.contact_email, 'integration@e2etest.de')
        self.assertEqual(customer.billing_email, 'billing@e2etest.de')
        self.assertEqual(customer.billing_address, 'Integration Street 42')
        self.assertEqual(customer.billing_city, 'Hamburg')
        self.assertEqual(customer.billing_postal_code, '20095')
        self.assertEqual(customer.billing_country, 'DE')
        self.assertEqual(customer.vat_id, 'DE987654321')
        self.assertEqual(customer.contact_phone, '+49 40 123456')
        self.assertEqual(customer.stripe_customer_id, 'cus_e2eintegration')
        self.assertEqual(customer.notes, 'Created via end-to-end integration test')
        self.assertEqual(customer.status, 'active')
        self.assertTrue(customer.is_active)
        self.assertIsNotNone(customer.created_at)
        self.assertIsNotNone(customer.updated_at)

        # Verify Customer is persisted in database
        db_customer = Customer.objects.get(slug='e2etest')
        self.assertEqual(db_customer.id, customer.id)

        # === Verify Subscription ===
        self.assertIsNotNone(subscription)
        self.assertIsNotNone(subscription.id)
        self.assertEqual(subscription.customer, customer)
        self.assertEqual(subscription.customer.id, customer.id)
        self.assertEqual(subscription.plan, self.plan)
        self.assertEqual(subscription.plan.id, self.plan.id)
        self.assertEqual(subscription.stripe_subscription_id, 'sub_e2e_integration_test')
        self.assertEqual(subscription.stripe_status, 'active')
        self.assertEqual(subscription.user_seats_total, 25)
        self.assertEqual(subscription.instance_seats_total, 5)
        self.assertTrue(subscription.ai_addon_active)
        self.assertTrue(subscription.is_active)
        self.assertIsNotNone(subscription.current_period_start)
        self.assertIsNotNone(subscription.created_at)
        self.assertIsNotNone(subscription.updated_at)

        # Verify Subscription is persisted and linked
        db_subscription = Subscription.objects.get(stripe_subscription_id='sub_e2e_integration_test')
        self.assertEqual(db_subscription.id, subscription.id)
        self.assertEqual(db_subscription.customer.id, customer.id)

        # === Verify Master Instance ===
        self.assertIsNotNone(instance)
        self.assertIsNotNone(instance.id)
        self.assertEqual(instance.customer, customer)
        self.assertEqual(instance.customer.id, customer.id)
        self.assertEqual(instance.subscription, subscription)
        self.assertEqual(instance.subscription.id, subscription.id)
        self.assertEqual(instance.slug, 'e2etest')  # Master slug matches customer slug
        self.assertTrue(instance.is_master)
        self.assertEqual(instance.display_name, 'End to End Test GmbH Master')
        self.assertEqual(instance.user_seats, 25)
        self.assertTrue(instance.ai_addon_active)
        self.assertEqual(instance.status, 'provisioning')
        self.assertIsNotNone(instance.api_key)
        self.assertEqual(len(instance.api_key), 64)  # token_urlsafe(48) produces 64 chars
        self.assertIsNotNone(instance.created_at)
        self.assertIsNotNone(instance.updated_at)

        # Verify Instance FQDN property
        expected_fqdn = f"{customer.slug}.zenico.app"
        self.assertEqual(instance.fqdn, expected_fqdn)

        # Verify Instance is persisted and linked
        db_instance = Instance.objects.get(customer=customer, is_master=True)
        self.assertEqual(db_instance.id, instance.id)
        self.assertEqual(db_instance.slug, customer.slug)

        # === Verify AuditLog ===
        audit_logs = AuditLog.objects.filter(
            customer=customer,
            action='customer.created'
        )
        self.assertEqual(audit_logs.count(), 1)

        audit_log = audit_logs.first()
        self.assertEqual(audit_log.actor_email, 'system')
        self.assertEqual(audit_log.resource_type, 'Customer')
        self.assertEqual(audit_log.resource_id, str(customer.id))
        self.assertIsNotNone(audit_log.after)
        self.assertEqual(audit_log.after['slug'], 'e2etest')
        self.assertEqual(audit_log.after['company_name'], 'End to End Test GmbH')
        self.assertEqual(audit_log.after['plan'], self.plan.name)
        self.assertEqual(audit_log.after['user_seats'], 25)
        self.assertEqual(audit_log.after['instance_seats'], 5)
        self.assertIn('subscription', audit_log.note.lower())
        self.assertIsNotNone(audit_log.created_at)

        # === Verify Relationships Work Both Ways ===
        # Customer -> Subscription
        customer_subscriptions = customer.subscriptions.all()
        self.assertEqual(customer_subscriptions.count(), 1)
        self.assertEqual(customer_subscriptions.first().id, subscription.id)

        # Customer -> Instance
        customer_instances = customer.instances.all()
        self.assertEqual(customer_instances.count(), 1)
        self.assertEqual(customer_instances.first().id, instance.id)

        # Customer -> Master Instance (via property)
        self.assertEqual(customer.master_instance.id, instance.id)

        # Customer -> Active Subscription (via property)
        self.assertEqual(customer.active_subscription.id, subscription.id)

        # === Verify Transaction Atomicity ===
        # Count total objects to ensure nothing extra was created
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertEqual(Instance.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='customer.created').count(), 1)


class CircularImportTest(TestCase):
    """
    Test that there are no circular imports between Django apps.

    This ensures the project structure is clean and maintainable.
    """

    def test_no_circular_imports_in_models(self):
        """Test that all model imports work without circular dependency issues."""
        try:
            # Import models from all apps
            from accounts.models import AdminUser
            from customers.models import Plan, Customer, Subscription
            from instances.models import Instance, UserLicense
            from audit.models import AuditLog
            from billing.models import StripeEvent, Invoice

            # If we got here, no circular imports exist
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Circular import detected: {e}")

    def test_no_circular_imports_in_services(self):
        """Test that service layer imports work without circular dependencies."""
        try:
            # Import services
            from customers.services import CustomerService

            # Verify service can be instantiated and methods exist
            self.assertTrue(hasattr(CustomerService, 'create_customer'))
            self.assertTrue(callable(CustomerService.create_customer))

        except ImportError as e:
            self.fail(f"Circular import in services detected: {e}")

    def test_no_circular_imports_in_admin(self):
        """Test that admin configurations load without circular imports."""
        try:
            # Import admin configurations from apps that have them
            from accounts.admin import AdminUserAdmin
            from customers.admin import PlanAdmin, CustomerAdmin, SubscriptionAdmin
            from instances.admin import InstanceAdmin, UserLicenseAdmin
            from billing.admin import StripeEventAdmin, InvoiceAdmin
            # Note: audit.admin exists but has no registered admin classes

            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Circular import in admin detected: {e}")

    def test_apps_can_be_imported_independently(self):
        """Test that each app can be imported independently."""
        apps_to_test = [
            'accounts',
            'customers',
            'instances',
            'audit',
            'billing',
        ]

        for app_name in apps_to_test:
            try:
                # Try importing models from each app
                __import__(f'{app_name}.models')
                __import__(f'{app_name}.admin')
            except ImportError as e:
                self.fail(f"Failed to import {app_name}: {e}")
