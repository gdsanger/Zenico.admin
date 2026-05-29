from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import AdminUser
from newsletter.models import Subscriber


class SubscriberViewTests(TestCase):
    """Test subscriber views, especially CSRF token handling."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.admin = AdminUser.objects.create_user(
            email='admin@test.com',
            password='password123',
            display_name='Test Admin',
            role='superadmin'
        )
        self.client.login(email='admin@test.com', password='password123')

        self.subscriber = Subscriber.objects.create(
            email='test@example.com',
            first_name='Test',
            last_name='User',
            source='manual',
            status='active',
            confirmed_at=timezone.now()
        )

    def test_deactivate_subscriber_requires_post(self):
        """Test that deactivate_subscriber requires POST method."""
        url = reverse('ui:subscriber_deactivate', kwargs={'subscriber_id': self.subscriber.id})
        response = self.client.get(url)
        # Should return 405 Method Not Allowed
        self.assertEqual(response.status_code, 405)

    def test_deactivate_subscriber_with_csrf_token(self):
        """Test that deactivate_subscriber works with proper CSRF token."""
        url = reverse('ui:subscriber_deactivate', kwargs={'subscriber_id': self.subscriber.id})
        # Client automatically handles CSRF token when enforce_csrf_checks is not set
        response = self.client.post(url)

        # Should succeed (200) and return HTML
        self.assertEqual(response.status_code, 200)

        # Verify subscriber was deactivated
        self.subscriber.refresh_from_db()
        self.assertEqual(self.subscriber.status, 'unsubscribed')
        self.assertIsNotNone(self.subscriber.unsubscribed_at)

    def test_deactivate_subscriber_without_csrf_token(self):
        """Test that deactivate_subscriber fails without CSRF token."""
        url = reverse('ui:subscriber_deactivate', kwargs={'subscriber_id': self.subscriber.id})
        # Enforce CSRF checks for this test
        client = Client(enforce_csrf_checks=True)
        client.login(email='admin@test.com', password='password123')

        response = client.post(url)
        # Should return 403 Forbidden due to missing CSRF token
        self.assertEqual(response.status_code, 403)

        # Verify subscriber was NOT deactivated
        self.subscriber.refresh_from_db()
        self.assertEqual(self.subscriber.status, 'active')

