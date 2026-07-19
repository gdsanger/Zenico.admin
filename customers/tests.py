from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from unittest.mock import patch
from .models import Plan, Customer, Subscription
from .services import CustomerService
from instances.models import Instance
from audit.models import AuditLog
from core.services.audit import AuditService


class PlanModelTest(TestCase):
    """Test cases for the Plan model."""

    def setUp(self):
        """Set up test data."""
        # Use a unique name that won't conflict with data migration
        self.plan_data = {
            'name': 'standard',
            'display_name': 'Test Standard Plan',
            'description': 'Basic plan for small teams',
            'max_users_per_instance': 10,
            'max_instances': 5,
            'price_per_user': Decimal('19.00'),
            'price_ai_addon': Decimal('7.50'),
            'ai_addon_available': True,
            'is_active': True,
        }

    def test_plan_str_method(self):
        """Test the __str__ method returns display_name."""
        # Use existing plan from data migration
        plan = Plan.objects.filter(name='standard').first()
        self.assertEqual(str(plan), plan.display_name)

    def test_plan_name_unique(self):
        """Test that plan name must be unique."""
        # Try to create a duplicate of an existing plan
        with self.assertRaises(Exception):  # IntegrityError
            Plan.objects.create(
                name='standard',  # This already exists from data migration
                display_name='Duplicate Standard'
            )

    def test_plan_default_values(self):
        """Test default values for plan fields."""
        # Delete the enterprise plan if it exists and create a fresh one
        Plan.objects.filter(name='enterprise').delete()
        minimal_plan = Plan.objects.create(
            name='enterprise',
            display_name='Enterprise Plan'
        )
        self.assertEqual(minimal_plan.max_users_per_instance, 0)
        self.assertEqual(minimal_plan.max_instances, 0)
        self.assertEqual(minimal_plan.price_per_user, Decimal('0.00'))
        self.assertEqual(minimal_plan.price_ai_addon, Decimal('0.00'))
        self.assertFalse(minimal_plan.ai_addon_available)
        self.assertTrue(minimal_plan.is_active)

    def test_inactive_plan(self):
        """Test modifying a plan to be inactive."""
        plan = Plan.objects.filter(name='standard').first()
        plan.is_active = False
        plan.save()
        plan.refresh_from_db()
        self.assertFalse(plan.is_active)

    def test_stripe_fields_optional(self):
        """Test that Stripe fields are optional."""
        plan = Plan.objects.filter(name='enterprise').first()
        # Initial plans don't have Stripe IDs
        self.assertEqual(plan.stripe_product_id, '')
        self.assertEqual(plan.stripe_price_id_user, '')
        self.assertEqual(plan.stripe_price_id_instance, '')
        self.assertEqual(plan.stripe_price_id_ai, '')

    def test_plan_with_stripe_ids(self):
        """Test updating a plan with Stripe IDs."""
        plan = Plan.objects.filter(name='standard').first()
        plan.stripe_product_id = 'prod_123'
        plan.stripe_price_id_user = 'price_user_123'
        plan.stripe_price_id_instance = 'price_inst_123'
        plan.stripe_price_id_ai = 'price_ai_123'
        plan.save()
        plan.refresh_from_db()
        self.assertEqual(plan.stripe_product_id, 'prod_123')
        self.assertEqual(plan.stripe_price_id_user, 'price_user_123')
        self.assertEqual(plan.stripe_price_id_instance, 'price_inst_123')
        self.assertEqual(plan.stripe_price_id_ai, 'price_ai_123')

    def test_plan_timestamps(self):
        """Test that timestamps are automatically set."""
        plan = Plan.objects.filter(name='standard').first()
        self.assertIsNotNone(plan.created_at)
        self.assertIsNotNone(plan.updated_at)

    def test_plan_uuid_primary_key(self):
        """Test that plans use UUID as primary key."""
        plan = Plan.objects.filter(name='standard').first()
        self.assertIsNotNone(plan.id)
        # UUID should be a string representation of 36 characters with hyphens
        self.assertEqual(len(str(plan.id)), 36)

    def test_plan_pricing_validation(self):
        """Test that pricing fields accept decimal values correctly."""
        plan = Plan.objects.filter(name='enterprise').first()
        plan.price_per_user = Decimal('25.99')
        plan.price_ai_addon = Decimal('15.00')
        plan.save()
        plan.refresh_from_db()
        self.assertEqual(plan.price_per_user, Decimal('25.99'))
        self.assertEqual(plan.price_ai_addon, Decimal('15.00'))


class PlanDataMigrationTest(TestCase):
    """Test cases for the plan data migration (starter/professional/enterprise -> standard/enterprise)."""

    def test_initial_plans_exist(self):
        """Test that only the real plans remain after the data migration."""
        standard = Plan.objects.filter(name='standard').first()
        enterprise = Plan.objects.filter(name='enterprise').first()

        self.assertIsNotNone(standard)
        self.assertIsNotNone(enterprise)
        self.assertFalse(Plan.objects.filter(name__in=['starter', 'professional']).exists())

    def test_initial_plans_count(self):
        """Test that exactly the 2 real plans exist after the data migration."""
        count = Plan.objects.filter(name__in=['standard', 'enterprise']).count()
        self.assertEqual(count, 2)

    def test_initial_plans_pricing(self):
        """Test that the migrated plans kept their reference pricing."""
        plans = Plan.objects.filter(name__in=['standard', 'enterprise'])

        for plan in plans:
            self.assertEqual(plan.price_per_user, Decimal('19.00'))
            self.assertEqual(plan.price_ai_addon, Decimal('7.50'))
            self.assertTrue(plan.ai_addon_available)

    def test_instance_pricing_zeroed(self):
        """The retired per-instance price is zeroed on all plans by the data migration."""
        for plan in Plan.objects.all():
            self.assertEqual(plan.price_per_instance, Decimal('0.00'))

    def test_initial_plans_unlimited_limits(self):
        """Test that initial plans have unlimited users and instances (0 = unlimited)."""
        plans = Plan.objects.filter(name__in=['standard', 'enterprise'])

        for plan in plans:
            self.assertEqual(plan.max_users_per_instance, 0)
            self.assertEqual(plan.max_instances, 0)

    def test_initial_plans_display_names(self):
        """Test that migrated plans have proper display names."""
        standard = Plan.objects.get(name='standard')
        enterprise = Plan.objects.get(name='enterprise')

        self.assertEqual(standard.display_name, 'Standard')
        self.assertEqual(enterprise.display_name, 'Enterprise')

    def test_standard_plan_is_active_enterprise_is_not(self):
        """Standard is bookable via Stripe/the order API; enterprise is manual-only."""
        standard = Plan.objects.get(name='standard')
        enterprise = Plan.objects.get(name='enterprise')

        self.assertTrue(standard.is_active)
        self.assertFalse(enterprise.is_active)


class CustomerModelTest(TestCase):
    """Test cases for the Customer model."""

    def setUp(self):
        """Set up test data."""
        self.customer_data = {
            'slug': 'testco',
            'company_name': 'Test Company GmbH',
            'contact_name': 'John Doe',
            'contact_email': 'john@testco.de',
            'contact_phone': '+49 123 456789',
            'billing_email': 'billing@testco.de',
            'billing_address': 'Test Street 123',
            'billing_city': 'Berlin',
            'billing_postal_code': '10115',
            'billing_country': 'DE',
            'vat_id': 'DE123456789',
            'status': 'active',
            'notes': 'Test customer for unit tests',
        }

    def test_customer_creation(self):
        """Test creating a customer with valid data."""
        customer = Customer.objects.create(**self.customer_data)
        self.assertIsNotNone(customer.id)
        self.assertEqual(customer.slug, 'testco')
        self.assertEqual(customer.company_name, 'Test Company GmbH')
        self.assertEqual(customer.status, 'active')

    def test_customer_str_method(self):
        """Test the __str__ method returns company name and slug."""
        customer = Customer.objects.create(**self.customer_data)
        expected = f"{self.customer_data['company_name']} ({self.customer_data['slug']})"
        self.assertEqual(str(customer), expected)

    def test_slug_unique_constraint(self):
        """Test that slug must be unique."""
        Customer.objects.create(**self.customer_data)
        with self.assertRaises(Exception):  # IntegrityError
            Customer.objects.create(**self.customer_data)

    def test_slug_validator_lowercase_only(self):
        """Test that slug validator blocks uppercase letters."""
        data = self.customer_data.copy()
        data['slug'] = 'TestCo'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_validator_no_special_chars(self):
        """Test that slug validator blocks special characters."""
        data = self.customer_data.copy()
        data['slug'] = 'test-co'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_validator_no_spaces(self):
        """Test that slug validator blocks spaces."""
        data = self.customer_data.copy()
        data['slug'] = 'test co'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_validator_min_length(self):
        """Test that slug must be at least 2 characters."""
        data = self.customer_data.copy()
        data['slug'] = 'a'
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_validator_max_length(self):
        """Test that slug must be at most 10 characters."""
        data = self.customer_data.copy()
        data['slug'] = 'abcdefghijk'  # 11 characters
        customer = Customer(**data)
        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()
        self.assertIn('slug', ctx.exception.error_dict)

    def test_slug_validator_valid_alphanumeric(self):
        """Test that valid alphanumeric slugs are accepted."""
        valid_slugs = ['ab', 'test123', 'abc123xyz', '12345', 'abcdefghij']
        for slug in valid_slugs:
            data = self.customer_data.copy()
            data['slug'] = slug
            customer = Customer(**data)
            customer.full_clean()  # Should not raise
            customer.save()
            customer.delete()  # Clean up for next iteration

    def test_slug_immutability_after_save(self):
        """Test that slug cannot be changed after initial save."""
        customer = Customer.objects.create(**self.customer_data)
        original_slug = customer.slug

        # Try to change the slug
        customer.slug = 'newslug'

        with self.assertRaises(ValidationError) as ctx:
            customer.full_clean()

        self.assertIn('slug', ctx.exception.error_dict)
        self.assertIn('cannot be changed', str(ctx.exception.error_dict['slug'][0]).lower())

        # Verify slug hasn't changed in database
        customer.refresh_from_db()
        self.assertEqual(customer.slug, original_slug)

    def test_slug_can_be_set_on_new_instance(self):
        """Test that slug can be set on new instance before save."""
        customer = Customer(**self.customer_data)
        customer.full_clean()  # Should not raise
        customer.save()
        self.assertEqual(customer.slug, 'testco')

    def test_customer_default_values(self):
        """Test default values for customer fields."""
        minimal_data = {
            'slug': 'minimal',
            'company_name': 'Minimal Co',
            'contact_name': 'Jane Doe',
            'contact_email': 'jane@minimal.de',
            'billing_email': 'billing@minimal.de',
            'billing_address': 'Address 1',
            'billing_city': 'City',
            'billing_postal_code': '12345',
        }
        customer = Customer.objects.create(**minimal_data)
        self.assertEqual(customer.billing_country, 'DE')
        self.assertEqual(customer.status, 'active')
        self.assertEqual(customer.vat_id, '')
        self.assertEqual(customer.contact_phone, '')
        self.assertEqual(customer.notes, '')
        self.assertIsNone(customer.stripe_customer_id)

    def test_customer_status_choices(self):
        """Test that customer status can be set to different values."""
        customer = Customer.objects.create(**self.customer_data)

        for status, _ in Customer.STATUS_CHOICES:
            customer.status = status
            customer.save()
            customer.refresh_from_db()
            self.assertEqual(customer.status, status)

    def test_customer_is_active_property(self):
        """Test the is_active property."""
        customer = Customer.objects.create(**self.customer_data)

        customer.status = 'active'
        self.assertTrue(customer.is_active)

        customer.status = 'suspended'
        self.assertFalse(customer.is_active)

        customer.status = 'cancelled'
        self.assertFalse(customer.is_active)

    def test_customer_master_instance_property(self):
        """Test the master_instance property returns None (placeholder)."""
        customer = Customer.objects.create(**self.customer_data)
        self.assertIsNone(customer.master_instance)

    def test_customer_active_subscription_property(self):
        """Test the active_subscription property returns None (placeholder)."""
        customer = Customer.objects.create(**self.customer_data)
        self.assertIsNone(customer.active_subscription)

    def test_customer_timestamps(self):
        """Test that timestamps are automatically set."""
        customer = Customer.objects.create(**self.customer_data)
        self.assertIsNotNone(customer.created_at)
        self.assertIsNotNone(customer.updated_at)

    def test_customer_uuid_primary_key(self):
        """Test that customers use UUID as primary key."""
        customer = Customer.objects.create(**self.customer_data)
        self.assertIsNotNone(customer.id)
        # UUID should be a string representation of 36 characters with hyphens
        self.assertEqual(len(str(customer.id)), 36)

    def test_stripe_customer_id_unique(self):
        """Test that stripe_customer_id must be unique."""
        data1 = self.customer_data.copy()
        data1['slug'] = 'customer1'
        data1['stripe_customer_id'] = 'cus_123456'
        Customer.objects.create(**data1)

        data2 = self.customer_data.copy()
        data2['slug'] = 'customer2'
        data2['stripe_customer_id'] = 'cus_123456'

        with self.assertRaises(Exception):  # IntegrityError
            Customer.objects.create(**data2)

    def test_stripe_customer_id_can_be_null(self):
        """Test that stripe_customer_id can be null for multiple customers."""
        data1 = self.customer_data.copy()
        data1['slug'] = 'customer1'
        data1['stripe_customer_id'] = None
        customer1 = Customer.objects.create(**data1)

        data2 = self.customer_data.copy()
        data2['slug'] = 'customer2'
        data2['stripe_customer_id'] = None
        customer2 = Customer.objects.create(**data2)

        self.assertIsNone(customer1.stripe_customer_id)
        self.assertIsNone(customer2.stripe_customer_id)

    def test_customer_ordering(self):
        """Test that customers are ordered by company_name."""
        Customer.objects.create(slug='zebra', company_name='Zebra Co', **{
            k: v for k, v in self.customer_data.items()
            if k not in ['slug', 'company_name']
        })
        Customer.objects.create(slug='alpha', company_name='Alpha Co', **{
            k: v for k, v in self.customer_data.items()
            if k not in ['slug', 'company_name']
        })

        customers = list(Customer.objects.all())
        self.assertEqual(customers[0].company_name, 'Alpha Co')
        self.assertEqual(customers[1].company_name, 'Zebra Co')


class SubscriptionModelTest(TestCase):
    """Test cases for the Subscription model."""

    def setUp(self):
        """Set up test data."""
        # Create a customer
        self.customer = Customer.objects.create(
            slug='testco',
            company_name='Test Company GmbH',
            contact_name='John Doe',
            contact_email='john@testco.de',
            billing_email='billing@testco.de',
            billing_address='Test Street 123',
            billing_city='Berlin',
            billing_postal_code='10115',
            billing_country='DE',
            status='active',
        )

        # Create a plan
        self.plan = Plan.objects.filter(name='standard').first()

        # Subscription test data
        self.subscription_data = {
            'customer': self.customer,
            'plan': self.plan,
            'stripe_subscription_id': 'sub_test123',
            'stripe_status': 'active',
            'user_seats_total': 10,
            'instance_seats_total': 3,
            'ai_addon_active': False,
            'current_period_start': timezone.now(),
            'current_period_end': timezone.now() + timedelta(days=30),
        }

    def test_subscription_creation(self):
        """Test creating a subscription with valid data."""
        subscription = Subscription.objects.create(**self.subscription_data)
        self.assertIsNotNone(subscription.id)
        self.assertEqual(subscription.customer, self.customer)
        self.assertEqual(subscription.plan, self.plan)
        self.assertEqual(subscription.stripe_subscription_id, 'sub_test123')
        self.assertEqual(subscription.stripe_status, 'active')

    def test_subscription_str_method(self):
        """Test the __str__ method returns proper format."""
        subscription = Subscription.objects.create(**self.subscription_data)
        expected = f"{self.customer.company_name} - {self.plan.display_name} (active)"
        self.assertEqual(str(subscription), expected)

    def test_subscription_uuid_primary_key(self):
        """Test that subscriptions use UUID as primary key."""
        subscription = Subscription.objects.create(**self.subscription_data)
        self.assertIsNotNone(subscription.id)
        # UUID should be a string representation of 36 characters with hyphens
        self.assertEqual(len(str(subscription.id)), 36)

    def test_subscription_timestamps(self):
        """Test that timestamps are automatically set."""
        subscription = Subscription.objects.create(**self.subscription_data)
        self.assertIsNotNone(subscription.created_at)
        self.assertIsNotNone(subscription.updated_at)

    def test_stripe_subscription_id_unique(self):
        """Test that stripe_subscription_id must be unique."""
        Subscription.objects.create(**self.subscription_data)

        # Try to create another subscription with the same stripe_subscription_id
        data2 = self.subscription_data.copy()
        data2['stripe_subscription_id'] = 'sub_test123'

        with self.assertRaises(Exception):  # IntegrityError
            Subscription.objects.create(**data2)

    def test_subscription_default_values(self):
        """Test default values for subscription fields."""
        minimal_data = {
            'customer': self.customer,
            'plan': self.plan,
            'stripe_subscription_id': 'sub_minimal',
            'stripe_status': 'active',
        }
        subscription = Subscription.objects.create(**minimal_data)
        self.assertEqual(subscription.user_seats_total, 1)
        self.assertEqual(subscription.instance_seats_total, 1)
        self.assertFalse(subscription.ai_addon_active)
        self.assertIsNone(subscription.current_period_start)
        self.assertIsNone(subscription.current_period_end)
        self.assertIsNone(subscription.trial_end)
        self.assertIsNone(subscription.cancelled_at)

    def test_subscription_stripe_status_choices(self):
        """Test that subscription can be set to different Stripe statuses."""
        subscription = Subscription.objects.create(**self.subscription_data)

        statuses = [
            'active', 'trialing', 'past_due', 'cancelled',
            'unpaid', 'incomplete', 'incomplete_expired', 'paused'
        ]

        for status in statuses:
            subscription.stripe_status = status
            subscription.save()
            subscription.refresh_from_db()
            self.assertEqual(subscription.stripe_status, status)

    def test_is_active_property_active_status(self):
        """Test is_active property returns True for active status."""
        subscription = Subscription.objects.create(**self.subscription_data)
        subscription.stripe_status = 'active'
        self.assertTrue(subscription.is_active)

    def test_is_active_property_trialing_status(self):
        """Test is_active property returns True for trialing status."""
        subscription = Subscription.objects.create(**self.subscription_data)
        subscription.stripe_status = 'trialing'
        self.assertTrue(subscription.is_active)

    def test_is_active_property_inactive_statuses(self):
        """Test is_active property returns False for inactive statuses."""
        subscription = Subscription.objects.create(**self.subscription_data)

        inactive_statuses = ['past_due', 'cancelled', 'unpaid', 'incomplete', 'incomplete_expired', 'paused']

        for status in inactive_statuses:
            subscription.stripe_status = status
            self.assertFalse(subscription.is_active, f"Status {status} should not be active")

    def test_used_user_seats_returns_zero(self):
        """Test used_user_seats() returns 0 (placeholder until Instance model is ready)."""
        subscription = Subscription.objects.create(**self.subscription_data)
        self.assertEqual(subscription.used_user_seats(), 0)

    def test_available_user_seats_calculation(self):
        """Test available_user_seats() calculates correctly."""
        subscription = Subscription.objects.create(**self.subscription_data)
        subscription.user_seats_total = 10
        # Since used_user_seats() returns 0 (placeholder), available should equal total
        self.assertEqual(subscription.available_user_seats(), 10)

    def test_used_instance_seats_returns_zero(self):
        """Test used_instance_seats() returns 0 (placeholder until Instance model is ready)."""
        subscription = Subscription.objects.create(**self.subscription_data)
        self.assertEqual(subscription.used_instance_seats(), 0)

    def test_available_instance_seats_calculation(self):
        """Test available_instance_seats() calculates correctly."""
        subscription = Subscription.objects.create(**self.subscription_data)
        subscription.instance_seats_total = 5
        # Since used_instance_seats() returns 0 (placeholder), available should equal total
        self.assertEqual(subscription.available_instance_seats(), 5)

    def test_customer_foreign_key_protect(self):
        """Test that customer cannot be deleted if subscription exists."""
        subscription = Subscription.objects.create(**self.subscription_data)

        # Try to delete the customer
        with self.assertRaises(Exception):  # ProtectedError
            self.customer.delete()

        # Verify subscription still exists
        self.assertTrue(Subscription.objects.filter(id=subscription.id).exists())

    def test_plan_foreign_key_protect(self):
        """Test that plan cannot be deleted if subscription exists."""
        subscription = Subscription.objects.create(**self.subscription_data)

        # Try to delete the plan
        with self.assertRaises(Exception):  # ProtectedError
            self.plan.delete()

        # Verify subscription still exists
        self.assertTrue(Subscription.objects.filter(id=subscription.id).exists())

    def test_customer_can_have_multiple_subscriptions(self):
        """Test that a customer can have multiple subscriptions."""
        subscription1 = Subscription.objects.create(**self.subscription_data)

        data2 = self.subscription_data.copy()
        data2['stripe_subscription_id'] = 'sub_test456'
        data2['stripe_status'] = 'cancelled'
        subscription2 = Subscription.objects.create(**data2)

        subscriptions = self.customer.subscriptions.all()
        self.assertEqual(subscriptions.count(), 2)
        self.assertIn(subscription1, subscriptions)
        self.assertIn(subscription2, subscriptions)

    def test_customer_active_subscription_property(self):
        """Test that customer.active_subscription returns the active subscription."""
        # Create an active subscription
        Subscription.objects.create(**self.subscription_data)

        active_sub = self.customer.active_subscription
        self.assertIsNotNone(active_sub)
        self.assertEqual(active_sub.stripe_status, 'active')

    def test_customer_active_subscription_with_trialing(self):
        """Test that customer.active_subscription returns trialing subscription."""
        data = self.subscription_data.copy()
        data['stripe_status'] = 'trialing'
        Subscription.objects.create(**data)

        active_sub = self.customer.active_subscription
        self.assertIsNotNone(active_sub)
        self.assertEqual(active_sub.stripe_status, 'trialing')

    def test_customer_active_subscription_returns_none_when_no_active(self):
        """Test that customer.active_subscription returns None when no active subscription."""
        data = self.subscription_data.copy()
        data['stripe_status'] = 'cancelled'
        Subscription.objects.create(**data)

        active_sub = self.customer.active_subscription
        self.assertIsNone(active_sub)

    def test_customer_active_subscription_returns_first_when_multiple_active(self):
        """Test that customer.active_subscription returns first when multiple active."""
        subscription1 = Subscription.objects.create(**self.subscription_data)

        data2 = self.subscription_data.copy()
        data2['stripe_subscription_id'] = 'sub_test456'
        Subscription.objects.create(**data2)

        active_sub = self.customer.active_subscription
        self.assertIsNotNone(active_sub)
        # Should return the most recent one due to ordering by -created_at
        self.assertIn(active_sub.stripe_status, ['active', 'trialing'])

    def test_subscription_ordering(self):
        """Test that subscriptions are ordered by created_at descending."""
        subscription1 = Subscription.objects.create(**self.subscription_data)

        data2 = self.subscription_data.copy()
        data2['stripe_subscription_id'] = 'sub_test456'
        subscription2 = Subscription.objects.create(**data2)

        subscriptions = list(Subscription.objects.all())
        # Most recent should be first
        self.assertEqual(subscriptions[0].id, subscription2.id)
        self.assertEqual(subscriptions[1].id, subscription1.id)

    def test_subscription_with_trial_end(self):
        """Test subscription with trial_end date."""
        data = self.subscription_data.copy()
        data['stripe_status'] = 'trialing'
        data['trial_end'] = timezone.now() + timedelta(days=14)
        subscription = Subscription.objects.create(**data)

        self.assertIsNotNone(subscription.trial_end)
        self.assertTrue(subscription.is_active)

    def test_subscription_with_cancelled_at(self):
        """Test subscription with cancelled_at date."""
        data = self.subscription_data.copy()
        data['stripe_status'] = 'cancelled'
        data['cancelled_at'] = timezone.now()
        subscription = Subscription.objects.create(**data)

        self.assertIsNotNone(subscription.cancelled_at)
        self.assertFalse(subscription.is_active)

    def test_subscription_ai_addon_active(self):
        """Test subscription with AI addon active."""
        data = self.subscription_data.copy()
        data['ai_addon_active'] = True
        subscription = Subscription.objects.create(**data)

        self.assertTrue(subscription.ai_addon_active)

    def test_subscription_period_dates(self):
        """Test subscription with current period dates."""
        start_date = timezone.now()
        end_date = start_date + timedelta(days=30)

        data = self.subscription_data.copy()
        data['current_period_start'] = start_date
        data['current_period_end'] = end_date
        subscription = Subscription.objects.create(**data)

        self.assertEqual(subscription.current_period_start, start_date)
        self.assertEqual(subscription.current_period_end, end_date)


class CustomerServiceTest(TestCase):
    """Test cases for the CustomerService."""

    def setUp(self):
        """Set up test data."""
        self.plan = Plan.objects.filter(name='standard').first()

    def test_create_customer_success(self):
        """Test successful customer creation with all related objects."""
        # Call the service
        customer, subscription, instance = CustomerService.create_customer(
            slug='testco',
            company_name='Test Company GmbH',
            contact_name='John Doe',
            contact_email='john@testco.de',
            billing_email='billing@testco.de',
            plan=self.plan,
            user_seats=10,
            instance_seats=3,
            stripe_subscription_id='sub_test123',
            ai_addon=True,
            billing_address='Test Street 123',
            billing_city='Berlin',
            billing_postal_code='10115',
            billing_country='DE',
        )

        # Verify Customer was created
        self.assertIsNotNone(customer.id)
        self.assertEqual(customer.slug, 'testco')
        self.assertEqual(customer.company_name, 'Test Company GmbH')
        self.assertEqual(customer.contact_name, 'John Doe')
        self.assertEqual(customer.contact_email, 'john@testco.de')
        self.assertEqual(customer.billing_email, 'billing@testco.de')
        self.assertEqual(customer.status, 'active')

        # Verify Customer exists in database
        self.assertTrue(Customer.objects.filter(slug='testco').exists())

        # Verify Subscription was created
        self.assertIsNotNone(subscription.id)
        self.assertEqual(subscription.customer, customer)
        self.assertEqual(subscription.plan, self.plan)
        self.assertEqual(subscription.stripe_subscription_id, 'sub_test123')
        self.assertEqual(subscription.stripe_status, 'active')
        self.assertEqual(subscription.user_seats_total, 10)
        self.assertEqual(subscription.instance_seats_total, 3)
        self.assertTrue(subscription.ai_addon_active)
        self.assertIsNotNone(subscription.current_period_start)

        # Verify Subscription exists in database
        self.assertTrue(Subscription.objects.filter(customer=customer).exists())

        # Verify Master Instance was created
        self.assertIsNotNone(instance.id)
        self.assertEqual(instance.customer, customer)
        self.assertEqual(instance.subscription, subscription)
        self.assertEqual(instance.slug, 'testco')  # Master slug matches customer slug
        self.assertTrue(instance.is_master)
        self.assertEqual(instance.display_name, 'Test Company GmbH Master')
        self.assertEqual(instance.user_seats, 10)
        self.assertTrue(instance.ai_addon_active)
        self.assertEqual(instance.status, 'provisioning')
        self.assertIsNotNone(instance.api_key)

        # Verify Instance exists in database
        self.assertTrue(Instance.objects.filter(customer=customer, is_master=True).exists())

        # Verify AuditLog entry was created
        audit_logs = AuditLog.objects.filter(customer=customer, action='customer.created')
        self.assertEqual(audit_logs.count(), 1)
        audit_log = audit_logs.first()
        self.assertEqual(audit_log.actor_email, 'system')
        self.assertEqual(audit_log.resource_type, 'Customer')
        self.assertEqual(audit_log.resource_id, str(customer.id))
        self.assertIsNotNone(audit_log.after)
        self.assertEqual(audit_log.after['slug'], 'testco')
        self.assertEqual(audit_log.after['company_name'], 'Test Company GmbH')
        self.assertEqual(audit_log.after['user_seats'], 10)

    def test_create_customer_minimal_params(self):
        """Test customer creation with minimal required parameters."""
        customer, subscription, instance = CustomerService.create_customer(
            slug='minimal',
            company_name='Minimal Co',
            contact_name='Jane Doe',
            contact_email='jane@minimal.de',
            billing_email='billing@minimal.de',
            billing_address='Test St 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            plan=self.plan,
            user_seats=5,
            instance_seats=1,
            stripe_subscription_id='sub_minimal123',
        )

        # Verify all objects were created
        self.assertEqual(customer.slug, 'minimal')
        self.assertEqual(subscription.stripe_subscription_id, 'sub_minimal123')
        self.assertEqual(instance.slug, 'minimal')
        self.assertTrue(instance.is_master)
        self.assertFalse(subscription.ai_addon_active)

    def test_create_customer_rollback_on_duplicate_slug(self):
        """Test that duplicate slug causes complete rollback."""
        # Create first customer
        CustomerService.create_customer(
            slug='testco',
            company_name='Test Company',
            contact_name='John Doe',
            contact_email='john@testco.de',
            billing_email='billing@testco.de',
            billing_address='Test St 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            plan=self.plan,
            user_seats=5,
            instance_seats=1,
            stripe_subscription_id='sub_first',
        )

        # Try to create customer with duplicate slug
        with self.assertRaises(ValidationError):
            CustomerService.create_customer(
                slug='testco',  # Duplicate slug
                company_name='Another Company',
                contact_name='Jane Doe',
                contact_email='jane@another.de',
                billing_email='billing@another.de',
                billing_address='Another St 2',
                billing_city='Munich',
                billing_postal_code='80331',
                plan=self.plan,
                user_seats=3,
                instance_seats=1,
                stripe_subscription_id='sub_second',
            )

        # Verify only one customer exists
        self.assertEqual(Customer.objects.filter(slug='testco').count(), 1)

        # Verify only one subscription exists
        self.assertEqual(Subscription.objects.all().count(), 1)

        # Verify only one instance exists
        self.assertEqual(Instance.objects.all().count(), 1)

        # Verify only one audit log exists
        self.assertEqual(AuditLog.objects.filter(action='customer.created').count(), 1)

    def test_create_customer_rollback_on_duplicate_stripe_subscription_id(self):
        """Test rollback when Stripe subscription ID already exists."""
        # Create first customer
        CustomerService.create_customer(
            slug='first',
            company_name='First Company',
            contact_name='John Doe',
            contact_email='john@first.de',
            billing_email='billing@first.de',
            billing_address='First St 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            plan=self.plan,
            user_seats=5,
            instance_seats=1,
            stripe_subscription_id='sub_duplicate',
        )

        # Try to create customer with duplicate Stripe subscription ID
        with self.assertRaises(ValidationError):
            CustomerService.create_customer(
                slug='second',
                company_name='Second Company',
                contact_name='Jane Doe',
                contact_email='jane@second.de',
                billing_email='billing@second.de',
                billing_address='Second St 2',
                billing_city='Munich',
                billing_postal_code='80331',
                plan=self.plan,
                user_seats=3,
                instance_seats=1,
                stripe_subscription_id='sub_duplicate',  # Duplicate
            )

        # Verify only first customer exists
        self.assertTrue(Customer.objects.filter(slug='first').exists())
        self.assertFalse(Customer.objects.filter(slug='second').exists())

        # Verify rollback - no second customer was created
        self.assertEqual(Customer.objects.all().count(), 1)
        self.assertEqual(Subscription.objects.all().count(), 1)
        self.assertEqual(Instance.objects.all().count(), 1)

    def test_create_customer_rollback_on_instance_creation_failure(self):
        """Test rollback when instance creation fails."""
        # Mock Instance.objects.create_master to raise an exception
        with patch.object(Instance.objects, 'create_master', side_effect=Exception('Instance creation failed')):
            with self.assertRaises(Exception) as context:
                CustomerService.create_customer(
                    slug='failco',
                    company_name='Fail Company',
                    contact_name='John Doe',
                    contact_email='john@failco.de',
                    billing_email='billing@failco.de',
                    billing_address='Fail St 1',
                    billing_city='Berlin',
                    billing_postal_code='10115',
                    plan=self.plan,
                    user_seats=5,
                    instance_seats=1,
                    stripe_subscription_id='sub_fail',
                )
            self.assertIn('Instance creation failed', str(context.exception))

        # Verify complete rollback - no customer, subscription, or instance created
        self.assertFalse(Customer.objects.filter(slug='failco').exists())
        self.assertFalse(Subscription.objects.filter(stripe_subscription_id='sub_fail').exists())
        self.assertFalse(Instance.objects.filter(slug='failco').exists())

        # Verify no audit log was created
        self.assertEqual(AuditLog.objects.filter(action='customer.created').count(), 0)

    def test_create_customer_rollback_on_audit_log_failure(self):
        """Test rollback when audit log creation fails."""
        # Mock AuditService.log to raise an exception
        with patch.object(AuditService, 'log', side_effect=Exception('Audit log failed')):
            with self.assertRaises(Exception) as context:
                CustomerService.create_customer(
                    slug='auditfail',
                    company_name='Audit Fail Company',
                    contact_name='John Doe',
                    contact_email='john@auditfail.de',
                    billing_email='billing@auditfail.de',
                    billing_address='Audit St 1',
                    billing_city='Berlin',
                    billing_postal_code='10115',
                    plan=self.plan,
                    user_seats=5,
                    instance_seats=1,
                    stripe_subscription_id='sub_auditfail',
                )
            self.assertIn('Audit log failed', str(context.exception))

        # Verify complete rollback - no customer, subscription, or instance created
        self.assertFalse(Customer.objects.filter(slug='auditfail').exists())
        self.assertFalse(Subscription.objects.filter(stripe_subscription_id='sub_auditfail').exists())
        self.assertFalse(Instance.objects.filter(slug='auditfail').exists())

    def test_create_customer_invalid_slug(self):
        """Test that invalid slug is rejected."""
        with self.assertRaises(ValidationError):
            customer, subscription, instance = CustomerService.create_customer(
                slug='INVALID',  # Uppercase not allowed
                company_name='Invalid Company',
                contact_name='John Doe',
                contact_email='john@invalid.de',
                billing_email='billing@invalid.de',
                plan=self.plan,
                user_seats=5,
                instance_seats=1,
                stripe_subscription_id='sub_invalid',
            )

    def test_create_customer_with_optional_fields(self):
        """Test customer creation with optional fields."""
        customer, subscription, instance = CustomerService.create_customer(
            slug='optional',
            company_name='Optional Fields Company',
            contact_name='John Doe',
            contact_email='john@optional.de',
            billing_email='billing@optional.de',
            plan=self.plan,
            user_seats=10,
            instance_seats=2,
            stripe_subscription_id='sub_optional',
            ai_addon=True,
            vat_id='DE123456789',
            contact_phone='+49 123 456789',
            stripe_customer_id='cus_123',
            notes='Test customer with optional fields',
            billing_address='Optional Street 456',
            billing_city='Munich',
            billing_postal_code='80331',
            billing_country='DE',
        )

        # Verify optional fields were set
        self.assertEqual(customer.vat_id, 'DE123456789')
        self.assertEqual(customer.contact_phone, '+49 123 456789')
        self.assertEqual(customer.stripe_customer_id, 'cus_123')
        self.assertEqual(customer.notes, 'Test customer with optional fields')
        self.assertEqual(customer.billing_address, 'Optional Street 456')
        self.assertEqual(customer.billing_city, 'Munich')

    def test_create_customer_returns_tuple(self):
        """Test that create_customer returns a tuple of (Customer, Subscription, Instance)."""
        result = CustomerService.create_customer(
            slug='tuple',
            company_name='Tuple Test Company',
            contact_name='John Doe',
            contact_email='john@tuple.de',
            billing_email='billing@tuple.de',
            billing_address='Tuple St 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            plan=self.plan,
            user_seats=5,
            instance_seats=1,
            stripe_subscription_id='sub_tuple',
        )

        # Verify return type
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

        customer, subscription, instance = result
        self.assertIsInstance(customer, Customer)
        self.assertIsInstance(subscription, Subscription)
        self.assertIsInstance(instance, Instance)

    def test_customer_master_instance_after_creation(self):
        """Test that customer.master_instance property works after creation."""
        customer, subscription, instance = CustomerService.create_customer(
            slug='master',
            company_name='Master Test Company',
            contact_name='John Doe',
            contact_email='john@master.de',
            billing_email='billing@master.de',
            billing_address='Master St 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            plan=self.plan,
            user_seats=5,
            instance_seats=1,
            stripe_subscription_id='sub_master',
        )

        # Test that customer.master_instance returns the created instance
        master = customer.master_instance
        self.assertIsNotNone(master)
        self.assertEqual(master.id, instance.id)
        self.assertTrue(master.is_master)

    def test_customer_active_subscription_after_creation(self):
        """Test that customer.active_subscription property works after creation."""
        customer, subscription, instance = CustomerService.create_customer(
            slug='active',
            company_name='Active Test Company',
            contact_name='John Doe',
            contact_email='john@active.de',
            billing_email='billing@active.de',
            billing_address='Active St 1',
            billing_city='Berlin',
            billing_postal_code='10115',
            plan=self.plan,
            user_seats=5,
            instance_seats=1,
            stripe_subscription_id='sub_active',
        )

        # Test that customer.active_subscription returns the created subscription
        active_sub = customer.active_subscription
        self.assertIsNotNone(active_sub)
        self.assertEqual(active_sub.id, subscription.id)
        self.assertTrue(active_sub.is_active)

