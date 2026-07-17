from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from customers.models import Plan, Customer, Subscription
from .models import Instance, UserLicense


class InstanceModelTest(TestCase):
    """Test cases for the Instance model."""

    def setUp(self):
        """Set up test data."""
        # Create a plan
        self.plan = Plan.objects.filter(name='standard').first()

        # Create a customer
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
            status='active'
        )

        # Create a subscription
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=3
        )

    def test_instance_creation(self):
        """Test creating an instance with valid data."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master Instance',
            is_master=True,
            status='active',
            user_seats=5
        )
        self.assertEqual(instance.customer, self.customer)
        self.assertEqual(instance.subscription, self.subscription)
        self.assertEqual(instance.slug, 'testco')
        self.assertEqual(instance.display_name, 'Test Master Instance')
        self.assertTrue(instance.is_master)
        self.assertEqual(instance.status, 'active')
        self.assertEqual(instance.user_seats, 5)

    def test_instance_api_key_auto_generated(self):
        """Test that api_key is automatically generated on first save."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        self.assertIsNotNone(instance.api_key)
        self.assertGreater(len(instance.api_key), 0)

    def test_instance_api_key_unique(self):
        """Test that api_key must be unique."""
        instance1 = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        # Try to create another instance with the same api_key
        instance2 = Instance(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub Instance',
            is_master=False,
            api_key=instance1.api_key  # Force same api_key
        )
        with self.assertRaises(IntegrityError):
            instance2.save()

    def test_instance_default_values(self):
        """Test default values for instance fields."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        self.assertEqual(instance.status, 'provisioning')
        self.assertEqual(instance.user_seats, 1)
        self.assertFalse(instance.ai_addon_active)
        self.assertEqual(instance.server_host, '')
        self.assertEqual(instance.db_name, '')
        self.assertEqual(instance.db_user, '')
        self.assertIsNone(instance.provisioned_at)
        self.assertIsNone(instance.last_health_check)
        self.assertIsNone(instance.health_check_ok)

    def test_instance_str_method(self):
        """Test the __str__ method."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        expected = "Test Company - Test Master [Master] (testco)"
        self.assertEqual(str(instance), expected)

        sub_instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub Instance',
            is_master=False
        )
        expected = "Test Company - Sub Instance (sub1)"
        self.assertEqual(str(sub_instance), expected)

    def test_instance_timestamps(self):
        """Test that timestamps are automatically set."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        self.assertIsNotNone(instance.created_at)
        self.assertIsNotNone(instance.updated_at)

    def test_instance_uuid_primary_key(self):
        """Test that instances use UUID as primary key."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        self.assertIsNotNone(instance.id)
        # UUID should be a string representation
        self.assertEqual(len(str(instance.id)), 36)

    def test_fqdn_master_instance(self):
        """Test FQDN for master instance."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        self.assertEqual(instance.fqdn, 'testco.zenico.app')

    def test_fqdn_sub_instance(self):
        """Test FQDN for sub-instance."""
        # First create master
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        # Create sub-instance
        sub_instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub Instance',
            is_master=False
        )
        self.assertEqual(sub_instance.fqdn, 'sub1.testco.zenico.app')

    def test_is_active_property(self):
        """Test the is_active property."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True,
            status='active'
        )
        self.assertTrue(instance.is_active)

        instance.status = 'suspended'
        instance.save()
        self.assertFalse(instance.is_active)

    def test_regenerate_api_key(self):
        """Test regenerating the API key."""
        instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True
        )
        original_key = instance.api_key
        new_key = instance.regenerate_api_key()
        self.assertNotEqual(original_key, new_key)
        self.assertEqual(instance.api_key, new_key)
        # Verify it was saved
        instance.refresh_from_db()
        self.assertEqual(instance.api_key, new_key)

    def test_master_slug_validation(self):
        """Test that master instance slug must match customer slug."""
        instance = Instance(
            customer=self.customer,
            subscription=self.subscription,
            slug='wrongslug',
            display_name='Test Master',
            is_master=True
        )
        with self.assertRaises(ValidationError) as context:
            instance.full_clean()
        self.assertIn('slug', context.exception.message_dict)

    def test_unique_slug_per_customer(self):
        """Test that slug must be unique per customer."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True
        )
        with self.assertRaises(IntegrityError):
            Instance.objects.create(
                customer=self.customer,
                subscription=self.subscription,
                slug='testco',  # Duplicate slug
                display_name='Duplicate',
                is_master=False
            )

    def test_unique_master_per_customer(self):
        """Test that only one master instance is allowed per customer."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master 1',
            is_master=True
        )
        with self.assertRaises(IntegrityError):
            Instance.objects.create(
                customer=self.customer,
                subscription=self.subscription,
                slug='other',
                display_name='Master 2',
                is_master=True  # Duplicate master
            )

    def test_multiple_sub_instances_allowed(self):
        """Test that multiple sub-instances can be created."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True
        )
        sub1 = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub 1',
            is_master=False
        )
        sub2 = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub2',
            display_name='Sub 2',
            is_master=False
        )
        self.assertEqual(Instance.objects.filter(customer=self.customer, is_master=False).count(), 2)

    def test_user_seats_budget_validation(self):
        """Test that user seats cannot exceed subscription limit."""
        # Create master with 5 seats
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            user_seats=5,
            status='active'
        )
        # Try to create sub-instance with 6 seats (total would be 11, but limit is 10)
        instance = Instance(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub',
            is_master=False,
            user_seats=6,
            status='active'
        )
        with self.assertRaises(ValidationError) as context:
            instance.full_clean()
        self.assertIn('user_seats', context.exception.message_dict)

    def test_user_seats_budget_with_deprovisioned_instances(self):
        """Test that deprovisioned instances don't count against user seats."""
        # Create master with 5 seats (active)
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            user_seats=5,
            status='active'
        )
        # Create deprovisioned instance with 5 seats (shouldn't count)
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='old',
            display_name='Old Instance',
            is_master=False,
            user_seats=5,
            status='deprovisioned'
        )
        # Should be able to create another instance with 5 seats
        instance = Instance(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub',
            is_master=False,
            user_seats=5,
            status='active'
        )
        instance.full_clean()  # Should not raise ValidationError
        instance.save()
        self.assertEqual(instance.user_seats, 5)

    def test_customer_foreign_key_protect(self):
        """Test that customer cannot be deleted if instance exists."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True
        )
        with self.assertRaises(Exception):  # ProtectedError
            self.customer.delete()

    def test_subscription_foreign_key_protect(self):
        """Test that subscription cannot be deleted if instance exists."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True
        )
        with self.assertRaises(Exception):  # ProtectedError
            self.subscription.delete()

    def test_instance_ordering(self):
        """Test that instances are ordered by customer, master first, then slug."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='zsub',
            display_name='Z Sub',
            is_master=False
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='asub',
            display_name='A Sub',
            is_master=False
        )
        instances = list(Instance.objects.filter(customer=self.customer))
        self.assertEqual(len(instances), 3)
        self.assertTrue(instances[0].is_master)  # Master first
        self.assertEqual(instances[1].slug, 'asub')  # Then by slug
        self.assertEqual(instances[2].slug, 'zsub')


class InstanceManagerTest(TestCase):
    """Test cases for the InstanceManager."""

    def setUp(self):
        """Set up test data."""
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
            status='active'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=3
        )

    def test_create_master(self):
        """Test creating a master instance using the manager."""
        instance = Instance.objects.create_master(
            customer=self.customer,
            subscription=self.subscription,
            display_name='Master Instance'
        )
        self.assertTrue(instance.is_master)
        self.assertEqual(instance.slug, self.customer.slug)
        self.assertEqual(instance.display_name, 'Master Instance')

    def test_create_sub_instance(self):
        """Test creating a sub-instance using the manager."""
        # First create master
        Instance.objects.create_master(
            customer=self.customer,
            subscription=self.subscription,
            display_name='Master'
        )
        # Create sub-instance
        sub = Instance.objects.create_sub_instance(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub Instance'
        )
        self.assertFalse(sub.is_master)
        self.assertEqual(sub.slug, 'sub1')
        self.assertEqual(sub.display_name, 'Sub Instance')

    def test_create_sub_instance_with_customer_slug_raises_error(self):
        """Test that create_sub_instance raises error if slug matches customer."""
        with self.assertRaises(ValidationError):
            Instance.objects.create_sub_instance(
                customer=self.customer,
                subscription=self.subscription,
                slug='testco',  # Same as customer slug
                display_name='Sub Instance'
            )


class SubscriptionSeatCalculationTest(TestCase):
    """Test cases for Subscription seat calculation methods with Instance model."""

    def setUp(self):
        """Set up test data."""
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
            status='active'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=20,
            instance_seats_total=5
        )

    def test_used_user_seats_calculation(self):
        """Test that used_user_seats() correctly sums user seats from active instances."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            user_seats=5,
            status='active'
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub 1',
            is_master=False,
            user_seats=3,
            status='active'
        )
        self.assertEqual(self.subscription.used_user_seats(), 8)

    def test_used_user_seats_excludes_deprovisioned(self):
        """Test that deprovisioned instances don't count in used_user_seats()."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            user_seats=5,
            status='active'
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='old',
            display_name='Old',
            is_master=False,
            user_seats=10,
            status='deprovisioned'
        )
        self.assertEqual(self.subscription.used_user_seats(), 5)

    def test_used_user_seats_includes_provisioning(self):
        """Test that provisioning instances count in used_user_seats()."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            user_seats=5,
            status='provisioning'
        )
        self.assertEqual(self.subscription.used_user_seats(), 5)

    def test_available_user_seats_calculation(self):
        """Test available_user_seats() calculation."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            user_seats=8,
            status='active'
        )
        self.assertEqual(self.subscription.available_user_seats(), 12)  # 20 - 8

    def test_used_instance_seats_calculation(self):
        """Test that used_instance_seats() correctly counts active instances."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            status='active'
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub 1',
            is_master=False,
            status='active'
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub2',
            display_name='Sub 2',
            is_master=False,
            status='provisioning'
        )
        self.assertEqual(self.subscription.used_instance_seats(), 3)

    def test_used_instance_seats_excludes_deprovisioned(self):
        """Test that deprovisioned instances don't count in used_instance_seats()."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            status='active'
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='old',
            display_name='Old',
            is_master=False,
            status='deprovisioned'
        )
        self.assertEqual(self.subscription.used_instance_seats(), 1)

    def test_available_instance_seats_calculation(self):
        """Test available_instance_seats() calculation."""
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True,
            status='active'
        )
        Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub 1',
            is_master=False,
            status='active'
        )
        self.assertEqual(self.subscription.available_instance_seats(), 3)  # 5 - 2


class CustomerMasterInstanceTest(TestCase):
    """Test cases for Customer.master_instance property."""

    def setUp(self):
        """Set up test data."""
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
            status='active'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=3
        )

    def test_master_instance_returns_master(self):
        """Test that master_instance property returns the master instance."""
        master = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Master',
            is_master=True
        )
        self.assertEqual(self.customer.master_instance, master)

    def test_master_instance_returns_none_when_no_master(self):
        """Test that master_instance property returns None when no master exists."""
        self.assertIsNone(self.customer.master_instance)


class UserLicenseModelTest(TestCase):
    """Test cases for the UserLicense model."""

    def setUp(self):
        """Set up test data."""
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
            status='active'
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            stripe_subscription_id='sub_test123',
            stripe_status='active',
            user_seats_total=10,
            instance_seats_total=3
        )
        self.instance = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='testco',
            display_name='Test Master',
            is_master=True,
            user_seats=5,
            status='active'
        )

    def test_user_license_creation(self):
        """Test creating a user license with valid data."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='12345678-1234-1234-1234-123456789abc',
            email='user@example.com',
            display_name='Test User',
            role='contributor'
        )
        self.assertEqual(license.instance, self.instance)
        self.assertEqual(license.azure_oid, '12345678-1234-1234-1234-123456789abc')
        self.assertEqual(license.email, 'user@example.com')
        self.assertEqual(license.display_name, 'Test User')
        self.assertEqual(license.role, 'contributor')
        self.assertTrue(license.is_active)
        self.assertIsNotNone(license.activated_at)
        self.assertIsNone(license.deactivated_at)

    def test_user_license_default_values(self):
        """Test default values for user license fields."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='12345678-1234-1234-1234-123456789abc',
            email='user@example.com',
            display_name='Test User'
        )
        self.assertEqual(license.role, 'contributor')
        self.assertTrue(license.is_active)
        self.assertIsNone(license.deactivated_at)

    def test_user_license_uuid_primary_key(self):
        """Test that user licenses use UUID as primary key."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='12345678-1234-1234-1234-123456789abc',
            email='user@example.com',
            display_name='Test User'
        )
        self.assertIsNotNone(license.id)
        self.assertEqual(len(str(license.id)), 36)

    def test_user_license_str_method_active(self):
        """Test the __str__ method for active license."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='12345678-1234-1234-1234-123456789abc',
            email='user@example.com',
            display_name='Test User',
            is_active=True
        )
        expected = "Test User (user@example.com) - Test Master [Active]"
        self.assertEqual(str(license), expected)

    def test_user_license_str_method_inactive(self):
        """Test the __str__ method for inactive license."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='12345678-1234-1234-1234-123456789abc',
            email='user@example.com',
            display_name='Test User',
            is_active=False
        )
        expected = "Test User (user@example.com) - Test Master [Inactive]"
        self.assertEqual(str(license), expected)

    def test_user_license_role_choices(self):
        """Test all role choices are valid."""
        roles = ['project_manager', 'team_lead', 'contributor']
        for role in roles:
            license = UserLicense.objects.create(
                instance=self.instance,
                azure_oid=f'oid-{role}',
                email=f'{role}@example.com',
                display_name=f'User {role}',
                role=role
            )
            self.assertEqual(license.role, role)

    def test_unique_azure_oid_per_instance(self):
        """Test that azure_oid must be unique per instance."""
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='12345678-1234-1234-1234-123456789abc',
            email='user1@example.com',
            display_name='User One'
        )
        with self.assertRaises(IntegrityError):
            UserLicense.objects.create(
                instance=self.instance,
                azure_oid='12345678-1234-1234-1234-123456789abc',  # Duplicate
                email='user2@example.com',
                display_name='User Two'
            )

    def test_same_azure_oid_allowed_on_different_instances(self):
        """Test that same azure_oid can exist on different instances."""
        instance2 = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub Instance',
            is_master=False,
            user_seats=3,
            status='active'
        )

        license1 = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='12345678-1234-1234-1234-123456789abc',
            email='user@example.com',
            display_name='Test User'
        )
        license2 = UserLicense.objects.create(
            instance=instance2,
            azure_oid='12345678-1234-1234-1234-123456789abc',  # Same OID, different instance
            email='user@example.com',
            display_name='Test User'
        )
        self.assertNotEqual(license1.instance, license2.instance)
        self.assertEqual(license1.azure_oid, license2.azure_oid)

    def test_seat_limit_validation_at_capacity(self):
        """Test that clean() blocks activation when instance is at capacity."""
        # Create licenses up to the seat limit (5 seats)
        for i in range(5):
            UserLicense.objects.create(
                instance=self.instance,
                azure_oid=f'user-{i}',
                email=f'user{i}@example.com',
                display_name=f'User {i}',
                is_active=True
            )

        # Try to create one more active license
        license = UserLicense(
            instance=self.instance,
            azure_oid='user-6',
            email='user6@example.com',
            display_name='User Six',
            is_active=True
        )
        with self.assertRaises(ValidationError) as context:
            license.full_clean()
        self.assertIn('is_active', context.exception.message_dict)

    def test_seat_limit_validation_inactive_licenses_dont_count(self):
        """Test that inactive licenses don't count against seat limit."""
        # Create 5 active licenses
        for i in range(5):
            UserLicense.objects.create(
                instance=self.instance,
                azure_oid=f'user-{i}',
                email=f'user{i}@example.com',
                display_name=f'User {i}',
                is_active=True
            )

        # Create inactive licenses - should succeed
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='inactive-user',
            email='inactive@example.com',
            display_name='Inactive User',
            is_active=False
        )

        self.assertEqual(
            UserLicense.objects.filter(instance=self.instance, is_active=False).count(),
            1
        )

    def test_seat_limit_validation_allows_reactivation_of_own_slot(self):
        """Test that updating an existing license doesn't block itself."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user-1',
            email='user1@example.com',
            display_name='User One',
            is_active=True
        )

        # Modify the license (should not raise validation error)
        license.display_name = 'User One Updated'
        license.full_clean()  # Should not raise
        license.save()

        license.refresh_from_db()
        self.assertEqual(license.display_name, 'User One Updated')

    def test_seat_limit_validation_creating_under_capacity(self):
        """Test that creating licenses under capacity works fine."""
        # Create 3 licenses (under the 5 seat limit)
        for i in range(3):
            license = UserLicense(
                instance=self.instance,
                azure_oid=f'user-{i}',
                email=f'user{i}@example.com',
                display_name=f'User {i}',
                is_active=True
            )
            license.full_clean()  # Should not raise
            license.save()

        self.assertEqual(
            UserLicense.objects.filter(instance=self.instance, is_active=True).count(),
            3
        )

    def test_instance_foreign_key_cascade(self):
        """Test that deleting instance cascades to user licenses."""
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user-1',
            email='user1@example.com',
            display_name='User One'
        )
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user-2',
            email='user2@example.com',
            display_name='User Two'
        )

        license_count_before = UserLicense.objects.filter(instance=self.instance).count()
        self.assertEqual(license_count_before, 2)

        # Delete the instance
        self.instance.delete()

        # Licenses should be deleted too
        license_count_after = UserLicense.objects.filter(instance_id=self.instance.id).count()
        self.assertEqual(license_count_after, 0)

    def test_user_license_ordering(self):
        """Test that user licenses are ordered by instance, then email."""
        instance2 = Instance.objects.create(
            customer=self.customer,
            subscription=self.subscription,
            slug='sub1',
            display_name='Sub Instance',
            is_master=False,
            user_seats=3,
            status='active'
        )

        # Create licenses in mixed order
        UserLicense.objects.create(
            instance=instance2,
            azure_oid='oid-3',
            email='charlie@example.com',
            display_name='Charlie'
        )
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='oid-2',
            email='bob@example.com',
            display_name='Bob'
        )
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='oid-1',
            email='alice@example.com',
            display_name='Alice'
        )

        licenses = list(UserLicense.objects.all())
        # Should be ordered by instance (master first due to Instance ordering), then email
        self.assertEqual(licenses[0].email, 'alice@example.com')
        self.assertEqual(licenses[1].email, 'bob@example.com')
        self.assertEqual(licenses[2].email, 'charlie@example.com')

    def test_deactivated_at_field(self):
        """Test that deactivated_at can be set when deactivating a license."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user-1',
            email='user1@example.com',
            display_name='User One',
            is_active=True
        )

        # Deactivate the license
        license.is_active = False
        license.deactivated_at = timezone.now()
        license.save()

        license.refresh_from_db()
        self.assertFalse(license.is_active)
        self.assertIsNotNone(license.deactivated_at)

    def test_activated_at_auto_set(self):
        """Test that activated_at is automatically set on creation."""
        license = UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user-1',
            email='user1@example.com',
            display_name='User One'
        )
        self.assertIsNotNone(license.activated_at)

    def test_related_name_user_licenses(self):
        """Test that instances can access their licenses via user_licenses."""
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user-1',
            email='user1@example.com',
            display_name='User One'
        )
        UserLicense.objects.create(
            instance=self.instance,
            azure_oid='user-2',
            email='user2@example.com',
            display_name='User Two'
        )

        licenses = self.instance.user_licenses.all()
        self.assertEqual(licenses.count(), 2)
        self.assertTrue(all(lic.instance == self.instance for lic in licenses))

