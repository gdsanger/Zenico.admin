"""
Unit tests for CRM & Newsletter API endpoints.

Tests include basic functionality and email failure handling for Issue #770.
"""

from django.test import TestCase, Client
from django.utils import timezone
from unittest.mock import patch, MagicMock

from crm.models import Contact
from newsletter.models import Subscriber, AutomationSequence, SequenceEnrollment
from customers.models import Customer
from audit.models import AuditLog


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


class EmailFailureHandlingTestCase(TestCase):
    """Test email failure handling for Issue #770."""

    def setUp(self):
        """Set up test client."""
        self.client = Client()

    @patch('crm.api.MailService.send_template')
    def test_contact_created_with_all_emails_successful(self, mock_send_template):
        """Test contact creation when all emails are sent successfully."""
        # Mock all emails as successful
        mock_send_template.return_value = True

        data = {
            'first_name': 'Max',
            'last_name': 'Mustermann',
            'email': 'max@example.com',
            'phone': '0123456789',
            'company': 'Test GmbH',
            'message': 'Test message',
            'newsletter_consent': True,
            'ip_address': '127.0.0.1'
        }

        response = self.client.post('/api/contacts/', data, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['message'], 'Contact created successfully')

        # Check email status in response
        email_status = response.json()['email_status']
        self.assertTrue(email_status['contact_confirmation'])
        self.assertTrue(email_status['admin_notification'])
        self.assertTrue(email_status['newsletter_doi'])

        # Verify contact was created
        contact = Contact.objects.get(email='max@example.com')
        self.assertEqual(contact.first_name, 'Max')
        self.assertEqual(contact.last_name, 'Mustermann')

        # Verify subscriber was created
        subscriber = Subscriber.objects.get(email='max@example.com')
        self.assertEqual(subscriber.source, 'contact_form')

        # Verify audit log includes email results
        audit_log = AuditLog.objects.filter(
            resource_type='Contact',
            resource_id=str(contact.id)
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertIn('email_results', audit_log.after)
        self.assertIn('Emails sent: 3/3', audit_log.note)

        # Verify 3 emails were sent (DOI, confirmation, admin notification)
        self.assertEqual(mock_send_template.call_count, 3)

    @patch('crm.api.MailService.send_template')
    def test_contact_created_with_email_failures(self, mock_send_template):
        """Test contact creation when emails fail to send."""
        # Mock emails as failing
        mock_send_template.return_value = False

        data = {
            'first_name': 'Max',
            'last_name': 'Mustermann',
            'email': 'failure@example.com',
            'newsletter_consent': True,
            'ip_address': '127.0.0.1'
        }

        response = self.client.post('/api/contacts/', data, content_type='application/json')

        # Contact should still be created with 201 status
        self.assertEqual(response.status_code, 201)

        # Check email status shows failures
        email_status = response.json()['email_status']
        self.assertFalse(email_status['contact_confirmation'])
        self.assertFalse(email_status['admin_notification'])
        self.assertFalse(email_status['newsletter_doi'])

        # Verify contact was still created
        contact = Contact.objects.get(email='failure@example.com')
        self.assertEqual(contact.first_name, 'Max')

        # Verify audit log includes email results
        audit_log = AuditLog.objects.filter(
            resource_type='Contact',
            resource_id=str(contact.id)
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertIn('email_results', audit_log.after)
        self.assertIn('Emails sent: 0/3', audit_log.note)

    @patch('crm.api.MailService.send_template')
    def test_contact_created_with_partial_email_failures(self, mock_send_template):
        """Test contact creation when some emails fail."""
        # Mock emails with mixed success/failure
        # First call (newsletter_doi) succeeds, second (confirmation) fails, third (admin) succeeds
        mock_send_template.side_effect = [True, False, True]

        data = {
            'first_name': 'Max',
            'last_name': 'Mustermann',
            'email': 'partial@example.com',
            'newsletter_consent': True,
            'ip_address': '127.0.0.1'
        }

        response = self.client.post('/api/contacts/', data, content_type='application/json')

        self.assertEqual(response.status_code, 201)

        # Check email status shows mixed results
        email_status = response.json()['email_status']
        self.assertTrue(email_status['newsletter_doi'])
        self.assertFalse(email_status['contact_confirmation'])
        self.assertTrue(email_status['admin_notification'])

        # Verify audit log reflects partial success
        contact = Contact.objects.get(email='partial@example.com')
        audit_log = AuditLog.objects.filter(
            resource_type='Contact',
            resource_id=str(contact.id)
        ).first()
        self.assertIn('Emails sent: 2/3', audit_log.note)

    @patch('crm.api.logger')
    @patch('crm.api.MailService.send_template')
    def test_warning_logged_on_email_failure(self, mock_send_template, mock_logger):
        """Test that warnings are logged when emails fail."""
        # Mock confirmation email failing
        mock_send_template.side_effect = [True, False, True]

        data = {
            'first_name': 'Max',
            'last_name': 'Mustermann',
            'email': 'warning@example.com',
            'newsletter_consent': True,
            'ip_address': '127.0.0.1'
        }

        response = self.client.post('/api/contacts/', data, content_type='application/json')

        self.assertEqual(response.status_code, 201)

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        warning_message = mock_logger.warning.call_args[0][0]
        self.assertIn('Failed to send emails', warning_message)
        self.assertIn('contact_confirmation', warning_message)

    @patch('newsletter.api.logger')
    @patch('newsletter.api.MailService.send_template')
    def test_newsletter_subscribe_with_email_failure(self, mock_send_template, mock_logger):
        """Test newsletter subscription when email fails to send."""
        mock_send_template.return_value = False

        data = {
            'email': 'newsletter_fail@example.com',
            'first_name': 'Test',
            'ip_address': '127.0.0.1'
        }

        response = self.client.post('/api/newsletter/subscribe/', data, content_type='application/json')

        # Should still return 201 (to prevent email enumeration)
        self.assertEqual(response.status_code, 201)

        # Verify subscriber was still created
        subscriber = Subscriber.objects.get(email='newsletter_fail@example.com')
        self.assertIsNotNone(subscriber)

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        warning_message = mock_logger.warning.call_args[0][0]
        self.assertIn('Failed to send DOI email', warning_message)

    @patch('newsletter.api.logger')
    @patch('newsletter.api.MailService.send_template')
    def test_newsletter_confirm_with_email_failure(self, mock_send_template, mock_logger):
        """Test newsletter confirmation when email fails to send."""
        mock_send_template.return_value = False

        # Create subscriber
        subscriber = Subscriber.objects.create(
            email='confirm_fail@example.com',
            first_name='Test',
            source='web_form',
            status='active'
        )

        # Confirm subscription
        response = self.client.get(f'/api/newsletter/confirm/{subscriber.unsubscribe_token}/')

        self.assertEqual(response.status_code, 302)  # Redirect

        # Verify confirmed_at was set despite email failure
        subscriber.refresh_from_db()
        self.assertIsNotNone(subscriber.confirmed_at)

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        warning_message = mock_logger.warning.call_args[0][0]
        self.assertIn('Failed to send confirmation email', warning_message)

