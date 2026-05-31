from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import AdminUser


class UIViewsTestCase(TestCase):
    """Test Admin UI views."""

    def setUp(self):
        """Create test user."""
        self.user = AdminUser.objects.create_superuser(
            email='test@zenico.app',
            password='testpass123',
            display_name='Test User'
        )
        self.client = Client()

    def test_login_page_loads(self):
        """Test login page loads successfully."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'zenico.admin')

    def test_dashboard_requires_login(self):
        """Test dashboard redirects to login when not authenticated."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_dashboard_loads_when_authenticated(self):
        """Test dashboard loads when authenticated."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')

    def test_customer_list_loads(self):
        """Test customer list view loads."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('customer_list'))
        self.assertEqual(response.status_code, 200)

    def test_instance_list_loads(self):
        """Test instance list view loads."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('instance_list'))
        self.assertEqual(response.status_code, 200)

    def test_subscription_list_loads(self):
        """Test subscription list view loads."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('subscription_list'))
        self.assertEqual(response.status_code, 200)

    def test_audit_log_loads(self):
        """Test audit log view loads."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('audit_log_list'))
        self.assertEqual(response.status_code, 200)

    def test_logout_redirects(self):
        """Test logout redirects to login page."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 302)


class TemplateTagsTestCase(TestCase):
    """Test custom template tags."""

    def test_money_filter(self):
        """Test money filter formatting."""
        from ui.templatetags.ui_tags import money
        from decimal import Decimal

        self.assertEqual(money(Decimal('1234.56')), '1.234,56 €')
        self.assertEqual(money(Decimal('0.00')), '0,00 €')
        self.assertEqual(money(None), '0,00 €')

    def test_mask_key_filter(self):
        """Test API key masking."""
        from ui.templatetags.ui_tags import mask_key

        result = mask_key('sk-1234567890abcdefghij')
        self.assertTrue(result.startswith('sk-'))
        self.assertTrue('•' in result)
        self.assertTrue(result.endswith('ghij'))

    def test_initials_filter(self):
        """Test initials extraction."""
        from ui.templatetags.ui_tags import initials

        self.assertEqual(initials('John Doe'), 'JD')
        self.assertEqual(initials('Alice'), 'A')
        self.assertEqual(initials('alice@example.com'), 'A')


class RoleDecoratorTestCase(TestCase):
    """Test role-based access control."""

    def setUp(self):
        """Create test users with different roles."""
        self.superadmin = AdminUser.objects.create_user(
            email='super@zenico.app',
            password='testpass123',
            display_name='Super Admin',
            role='superadmin'
        )
        self.support = AdminUser.objects.create_user(
            email='support@zenico.app',
            password='testpass123',
            display_name='Support User',
            role='support'
        )
        self.billing = AdminUser.objects.create_user(
            email='billing@zenico.app',
            password='testpass123',
            display_name='Billing User',
            role='billing'
        )
        self.client = Client()

    def test_superadmin_can_access_customers(self):
        """Test superadmin can access customer management."""
        self.client.force_login(self.superadmin)
        response = self.client.get(reverse('customer_list'))
        self.assertEqual(response.status_code, 200)

    def test_support_can_access_customers(self):
        """Test support can access customer management."""
        self.client.force_login(self.support)
        response = self.client.get(reverse('customer_list'))
        self.assertEqual(response.status_code, 200)

    def test_billing_cannot_access_customers(self):
        """Test billing user cannot access customer management."""
        self.client.force_login(self.billing)
        response = self.client.get(reverse('customer_list'))
        self.assertEqual(response.status_code, 403)

    def test_billing_can_access_subscriptions(self):
        """Test billing user can access subscriptions."""
        self.client.force_login(self.billing)
        response = self.client.get(reverse('subscription_list'))
        self.assertEqual(response.status_code, 200)


class DashboardEndpointsTestCase(TestCase):
    """Test dashboard HTMX endpoints."""

    def setUp(self):
        """Create test user."""
        self.user = AdminUser.objects.create_superuser(
            email='test@zenico.app',
            password='testpass123',
            display_name='Test User'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_kpis_endpoint(self):
        """Test dashboard KPIs endpoint returns successfully."""
        response = self.client.get(reverse('ui:dashboard_kpis'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kpi-grid')

    def test_dashboard_activity_endpoint(self):
        """Test dashboard activity endpoint returns successfully."""
        response = self.client.get(reverse('ui:dashboard_activity'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_kpis_requires_login(self):
        """Test dashboard KPIs endpoint requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('ui:dashboard_kpis'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_dashboard_activity_requires_login(self):
        """Test dashboard activity endpoint requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('ui:dashboard_activity'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

