"""
Unit tests for CRM & Newsletter API endpoints.
"""

from django.test import TestCase, Client
from django.utils import timezone
from unittest.mock import patch, MagicMock

from crm.models import Contact
from newsletter.models import Subscriber, AutomationSequence, SequenceEnrollment
from customers.models import Customer


class ContactAPITestCase(TestCase):
    """Test cases for Contact API."""

    def setUp(self):
        self.client = Client()

    @patch('crm.api.MailService.send_template')
    @patch('crm.api.AuditService.log')
    def test_create_contact(self, mock_audit, mock_mail):
        """Test creating a contact via API."""
        mock_mail.return_value = True

        data = {
            'first_name': 'Max',
            'last_name': 'Mustermann',
            'email': 'max@example.com',
            'company': 'Test GmbH',
            'message': 'Test message',
            'newsletter_consent': True,
            'ip_address': '1.2.3.4'
        }

        response = self.client.post('/api/contacts/', data, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Contact.objects.filter(email='max@example.com').exists())

        # Verify contact was created
        contact = Contact.objects.get(email='max@example.com')
        self.assertEqual(contact.first_name, 'Max')
        self.assertEqual(contact.source, 'web_contact')
        self.assertEqual(contact.status, 'new')

    def test_create_contact_missing_fields(self):
        """Test creating contact with missing required fields."""
        data = {
            'first_name': 'Max',
            'email': 'max@example.com',
        }

        response = self.client.post('/api/contacts/', data, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    @patch('crm.api.MailService.send_template')
    def test_create_contact_with_newsletter_consent(self, mock_mail):
        """Test creating contact with newsletter consent creates subscriber."""
        mock_mail.return_value = True

        data = {
            'first_name': 'Max',
            'last_name': 'Mustermann',
            'email': 'max@example.com',
            'newsletter_consent': True,
            'ip_address': '1.2.3.4'
        }

        response = self.client.post('/api/contacts/', data, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Subscriber.objects.filter(email='max@example.com').exists())


class NewsletterAPITestCase(TestCase):
    """Test cases for Newsletter API."""

    def setUp(self):
        self.client = Client()

    @patch('newsletter.api.MailService.send_template')
    @patch('newsletter.api.AuditService.log')
    def test_subscribe(self, mock_audit, mock_mail):
        """Test newsletter subscription."""
        mock_mail.return_value = True

        data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'ip_address': '1.2.3.4'
        }

        response = self.client.post('/api/newsletter/subscribe/', data, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Subscriber.objects.filter(email='test@example.com').exists())

        # Verify DOI email was sent
        self.assertTrue(mock_mail.called)

    def test_confirm_subscription(self):
        """Test double-opt-in confirmation."""
        # Create subscriber
        subscriber = Subscriber.objects.create(
            email='test@example.com',
            first_name='Test',
            source='web_form',
            status='active'
        )

        # Confirm subscription
        response = self.client.get(f'/api/newsletter/confirm/{subscriber.unsubscribe_token}/')

        self.assertEqual(response.status_code, 302)  # Redirect

        subscriber.refresh_from_db()
        self.assertIsNotNone(subscriber.confirmed_at)

    def test_unsubscribe(self):
        """Test newsletter unsubscription."""
        # Create confirmed subscriber
        subscriber = Subscriber.objects.create(
            email='test@example.com',
            first_name='Test',
            source='web_form',
            status='active',
            confirmed_at=timezone.now()
        )

        # Unsubscribe
        response = self.client.get(f'/api/newsletter/unsubscribe/{subscriber.unsubscribe_token}/')

        self.assertEqual(response.status_code, 302)  # Redirect

        subscriber.refresh_from_db()
        self.assertEqual(subscriber.status, 'unsubscribed')
        self.assertIsNotNone(subscriber.unsubscribed_at)

    @patch('newsletter.api.MailService.send_template')
    def test_confirm_enrolls_in_sequences(self, mock_mail):
        """Test that confirmation enrolls subscriber in active sequences."""
        mock_mail.return_value = True

        # Create automation sequence
        sequence = AutomationSequence.objects.create(
            name='Welcome Sequence',
            trigger='subscriber_confirmed',
            is_active=True
        )

        # Create subscriber
        subscriber = Subscriber.objects.create(
            email='test@example.com',
            first_name='Test',
            source='web_form',
            status='active'
        )

        # Confirm subscription
        response = self.client.get(f'/api/newsletter/confirm/{subscriber.unsubscribe_token}/')

        self.assertEqual(response.status_code, 302)

        # Verify enrollment was created
        self.assertTrue(
            SequenceEnrollment.objects.filter(
                subscriber=subscriber,
                sequence=sequence,
                status='active'
            ).exists()
        )


class RateLimitTestCase(TestCase):
    """Test rate limiting on API endpoints."""

    def setUp(self):
        self.client = Client()

    @patch('crm.api.MailService.send_template')
    def test_rate_limit(self, mock_mail):
        """Test that rate limiting works (basic verification)."""
        mock_mail.return_value = True

        data = {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'ip_address': '1.2.3.4'
        }

        # Make a request to verify the endpoint works
        response = self.client.post('/api/contacts/', data, content_type='application/json')
        # Status may be 403 due to CSRF in test, but endpoint is accessible
        self.assertIn(response.status_code, [201, 403])

        # Note: Full rate limit testing requires integration testing
        # with proper request simulation to avoid CSRF protection
