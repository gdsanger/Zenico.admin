from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Plan, Customer


class PlanModelTest(TestCase):
    """Test cases for the Plan model."""

    def setUp(self):
        """Set up test data."""
        # Use a unique name that won't conflict with data migration
        self.plan_data = {
            'name': 'starter',
            'display_name': 'Test Starter Plan',
            'description': 'Basic plan for small teams',
            'max_users_per_instance': 10,
            'max_instances': 5,
            'price_per_user': Decimal('19.00'),
            'price_per_instance': Decimal('5.00'),
            'price_ai_addon': Decimal('7.50'),
            'ai_addon_available': True,
            'is_active': True,
        }

    def test_plan_str_method(self):
        """Test the __str__ method returns display_name."""
        # Use existing plan from data migration
        plan = Plan.objects.filter(name='starter').first()
        self.assertEqual(str(plan), plan.display_name)

    def test_plan_name_unique(self):
        """Test that plan name must be unique."""
        # Try to create a duplicate of an existing plan
        with self.assertRaises(Exception):  # IntegrityError
            Plan.objects.create(
                name='starter',  # This already exists from data migration
                display_name='Duplicate Starter'
            )

    def test_plan_default_values(self):
        """Test default values for plan fields."""
        # Delete the professional plan if it exists and create a fresh one
        Plan.objects.filter(name='professional').delete()
        minimal_plan = Plan.objects.create(
            name='professional',
            display_name='Professional Plan'
        )
        self.assertEqual(minimal_plan.max_users_per_instance, 0)
        self.assertEqual(minimal_plan.max_instances, 0)
        self.assertEqual(minimal_plan.price_per_user, Decimal('0.00'))
        self.assertEqual(minimal_plan.price_per_instance, Decimal('0.00'))
        self.assertEqual(minimal_plan.price_ai_addon, Decimal('0.00'))
        self.assertFalse(minimal_plan.ai_addon_available)
        self.assertTrue(minimal_plan.is_active)

    def test_inactive_plan(self):
        """Test modifying a plan to be inactive."""
        plan = Plan.objects.filter(name='starter').first()
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
        plan = Plan.objects.filter(name='starter').first()
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
        plan = Plan.objects.filter(name='starter').first()
        self.assertIsNotNone(plan.created_at)
        self.assertIsNotNone(plan.updated_at)

    def test_plan_uuid_primary_key(self):
        """Test that plans use UUID as primary key."""
        plan = Plan.objects.filter(name='starter').first()
        self.assertIsNotNone(plan.id)
        # UUID should be a string representation of 36 characters with hyphens
        self.assertEqual(len(str(plan.id)), 36)

    def test_plan_pricing_validation(self):
        """Test that pricing fields accept decimal values correctly."""
        plan = Plan.objects.filter(name='professional').first()
        plan.price_per_user = Decimal('25.99')
        plan.price_per_instance = Decimal('10.50')
        plan.price_ai_addon = Decimal('15.00')
        plan.save()
        plan.refresh_from_db()
        self.assertEqual(plan.price_per_user, Decimal('25.99'))
        self.assertEqual(plan.price_per_instance, Decimal('10.50'))
        self.assertEqual(plan.price_ai_addon, Decimal('15.00'))


class PlanDataMigrationTest(TestCase):
    """Test cases for initial data migration."""

    def test_initial_plans_exist(self):
        """Test that initial plans were created by data migration."""
        starter = Plan.objects.filter(name='starter').first()
        professional = Plan.objects.filter(name='professional').first()
        enterprise = Plan.objects.filter(name='enterprise').first()

        self.assertIsNotNone(starter)
        self.assertIsNotNone(professional)
        self.assertIsNotNone(enterprise)

    def test_initial_plans_count(self):
        """Test that exactly 3 plans were created by data migration."""
        count = Plan.objects.filter(name__in=['starter', 'professional', 'enterprise']).count()
        self.assertEqual(count, 3)

    def test_initial_plans_pricing(self):
        """Test that initial plans have correct reference pricing."""
        plans = Plan.objects.filter(name__in=['starter', 'professional', 'enterprise'])

        for plan in plans:
            self.assertEqual(plan.price_per_user, Decimal('19.00'))
            self.assertEqual(plan.price_per_instance, Decimal('5.00'))
            self.assertEqual(plan.price_ai_addon, Decimal('7.50'))
            self.assertTrue(plan.ai_addon_available)
            self.assertTrue(plan.is_active)

    def test_initial_plans_unlimited_limits(self):
        """Test that initial plans have unlimited users and instances (0 = unlimited)."""
        plans = Plan.objects.filter(name__in=['starter', 'professional', 'enterprise'])

        for plan in plans:
            self.assertEqual(plan.max_users_per_instance, 0)
            self.assertEqual(plan.max_instances, 0)

    def test_initial_plans_display_names(self):
        """Test that initial plans have proper display names."""
        starter = Plan.objects.get(name='starter')
        professional = Plan.objects.get(name='professional')
        enterprise = Plan.objects.get(name='enterprise')

        self.assertEqual(starter.display_name, 'Starter')
        self.assertEqual(professional.display_name, 'Professional')
        self.assertEqual(enterprise.display_name, 'Enterprise')


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
