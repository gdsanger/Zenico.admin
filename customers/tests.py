from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Plan


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
