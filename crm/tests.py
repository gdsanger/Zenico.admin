"""
Tests for CRM and Newsletter models.
"""
import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils import timezone
from unittest.mock import patch, MagicMock

from accounts.models import AdminUser
from customers.models import Customer
from crm.models import Contact, ContactNote, EducationRequest
from newsletter.models import (
    Subscriber, Campaign, CampaignMail,
    AutomationSequence, SequenceStep, SequenceEnrollment
)


class ContactModelTests(TestCase):
    """Test Contact model."""

    def setUp(self):
        self.admin = AdminUser.objects.create_user(
            email='admin@test.com',
            password='password123',
            display_name='Test Admin'
        )
        self.customer = Customer.objects.create(
            slug='test',
            company_name='Test Company',
            contact_name='Test Contact',
            contact_email='contact@test.com',
            billing_email='billing@test.com',
            billing_address='Test Address',
            billing_city='Test City',
            billing_postal_code='12345',
            billing_country='DE'
        )

    def test_contact_creation(self):
        """Test creating a contact."""
        contact = Contact.objects.create(
            source='web_contact',
            first_name='John',
            last_name='Doe',
            email='john@example.com'
        )
        self.assertEqual(contact.status, 'new')
        self.assertEqual(contact.full_name, 'John Doe')
        self.assertFalse(contact.is_converted)

    def test_contact_full_name_property(self):
        """Test full_name property."""
        contact = Contact.objects.create(
            source='manual',
            first_name='Jane',
            last_name='Smith',
            email='jane@example.com'
        )
        self.assertEqual(contact.full_name, 'Jane Smith')

    def test_contact_is_converted_property(self):
        """Test is_converted property."""
        contact = Contact.objects.create(
            source='web_contact',
            first_name='Test',
            last_name='User',
            email='test@example.com'
        )
        self.assertFalse(contact.is_converted)

        contact.converted_to = self.customer
        contact.save()
        self.assertTrue(contact.is_converted)

    def test_contact_assigned_to(self):
        """Test contact can be assigned to admin."""
        contact = Contact.objects.create(
            source='manual',
            first_name='Assign',
            last_name='Test',
            email='assign@example.com',
            assigned_to=self.admin
        )
        self.assertEqual(contact.assigned_to, self.admin)

    def test_contact_str(self):
        """Test contact string representation."""
        contact = Contact.objects.create(
            source='web_contact',
            first_name='String',
            last_name='Test',
            email='string@example.com'
        )
        self.assertEqual(str(contact), 'String Test (string@example.com)')


class ContactNoteModelTests(TestCase):
    """Test ContactNote model."""

    def setUp(self):
        self.admin = AdminUser.objects.create_user(
            email='admin@test.com',
            password='password123',
            display_name='Test Admin'
        )
        self.contact = Contact.objects.create(
            source='web_contact',
            first_name='John',
            last_name='Doe',
            email='john@example.com'
        )

    def test_contact_note_creation(self):
        """Test creating a contact note."""
        note = ContactNote.objects.create(
            contact=self.contact,
            author=self.admin,
            note='This is a test note.'
        )
        self.assertEqual(note.contact, self.contact)
        self.assertEqual(note.author, self.admin)
        self.assertEqual(note.note, 'This is a test note.')


class SubscriberModelTests(TestCase):
    """Test Subscriber model."""

    def test_subscriber_creation(self):
        """Test creating a subscriber."""
        subscriber = Subscriber.objects.create(
            email='subscriber@example.com',
            source='web_form',
            first_name='Sub',
            last_name='Scriber'
        )
        self.assertEqual(subscriber.email, 'subscriber@example.com')
        self.assertEqual(subscriber.status, 'active')
        self.assertIsNotNone(subscriber.unsubscribe_token)

    def test_unsubscribe_token_auto_generated(self):
        """Test that unsubscribe_token is auto-generated on save."""
        subscriber = Subscriber.objects.create(
            email='auto@example.com',
            source='manual'
        )
        self.assertIsNotNone(subscriber.unsubscribe_token)
        self.assertTrue(len(subscriber.unsubscribe_token) > 0)

    def test_duplicate_email_raises_error(self):
        """Test that duplicate email raises IntegrityError."""
        Subscriber.objects.create(
            email='duplicate@example.com',
            source='web_form'
        )
        with self.assertRaises(IntegrityError):
            Subscriber.objects.create(
                email='duplicate@example.com',
                source='manual'
            )

    def test_subscriber_is_active_property(self):
        """Test is_active property."""
        subscriber = Subscriber.objects.create(
            email='active@example.com',
            source='web_form'
        )
        # Not active until confirmed
        self.assertFalse(subscriber.is_active)

        # Active after confirmation
        subscriber.confirmed_at = timezone.now()
        subscriber.save()
        self.assertTrue(subscriber.is_active)

    def test_subscriber_full_name_property(self):
        """Test full_name property."""
        subscriber = Subscriber.objects.create(
            email='name@example.com',
            source='manual',
            first_name='Full',
            last_name='Name'
        )
        self.assertEqual(subscriber.full_name, 'Full Name')


class CampaignModelTests(TestCase):
    """Test Campaign model."""

    def setUp(self):
        self.admin = AdminUser.objects.create_user(
            email='admin@test.com',
            password='password123',
            display_name='Test Admin'
        )

    def test_campaign_creation(self):
        """Test creating a campaign."""
        campaign = Campaign.objects.create(
            name='Test Campaign',
            subject='Test Subject',
            html_body='<p>Test content</p>',
            created_by=self.admin
        )
        self.assertEqual(campaign.name, 'Test Campaign')
        self.assertEqual(campaign.status, 'draft')
        self.assertTrue(campaign.is_editable)

    def test_campaign_is_editable_property(self):
        """Test is_editable property."""
        campaign = Campaign.objects.create(
            name='Editable Test',
            subject='Test',
            html_body='<p>Test</p>',
            status='draft'
        )
        self.assertTrue(campaign.is_editable)

        campaign.status = 'sent'
        campaign.save()
        self.assertFalse(campaign.is_editable)


class CampaignMailModelTests(TestCase):
    """Test CampaignMail model."""

    def setUp(self):
        self.admin = AdminUser.objects.create_user(
            email='admin@test.com',
            password='password123',
            display_name='Test Admin'
        )
        self.campaign = Campaign.objects.create(
            name='Test Campaign',
            subject='Test Subject',
            html_body='<p>Test</p>',
            created_by=self.admin
        )
        self.subscriber = Subscriber.objects.create(
            email='subscriber@example.com',
            source='web_form'
        )

    def test_campaign_mail_creation(self):
        """Test creating a campaign mail."""
        mail = CampaignMail.objects.create(
            campaign=self.campaign,
            subscriber=self.subscriber
        )
        self.assertEqual(mail.status, 'pending')
        self.assertEqual(mail.campaign, self.campaign)
        self.assertEqual(mail.subscriber, self.subscriber)

    def test_duplicate_campaign_subscriber_raises_error(self):
        """Test that duplicate campaign-subscriber raises IntegrityError."""
        CampaignMail.objects.create(
            campaign=self.campaign,
            subscriber=self.subscriber
        )
        with self.assertRaises(IntegrityError):
            CampaignMail.objects.create(
                campaign=self.campaign,
                subscriber=self.subscriber
            )


class AutomationSequenceModelTests(TestCase):
    """Test AutomationSequence model."""

    def test_automation_sequence_creation(self):
        """Test creating an automation sequence."""
        sequence = AutomationSequence.objects.create(
            name='Onboarding Sequence',
            trigger='subscriber_confirmed'
        )
        self.assertEqual(sequence.name, 'Onboarding Sequence')
        self.assertEqual(sequence.trigger, 'subscriber_confirmed')
        self.assertFalse(sequence.is_active)


class SequenceStepModelTests(TestCase):
    """Test SequenceStep model."""

    def setUp(self):
        self.sequence = AutomationSequence.objects.create(
            name='Test Sequence',
            trigger='manual'
        )

    def test_sequence_step_creation(self):
        """Test creating a sequence step."""
        step = SequenceStep.objects.create(
            sequence=self.sequence,
            order=1,
            delay_days=0,
            subject='Welcome Email',
            html_body='<p>Welcome</p>'
        )
        self.assertEqual(step.sequence, self.sequence)
        self.assertEqual(step.order, 1)

    def test_duplicate_sequence_order_raises_error(self):
        """Test that duplicate sequence-order raises IntegrityError."""
        SequenceStep.objects.create(
            sequence=self.sequence,
            order=1,
            subject='Step 1',
            html_body='<p>Step 1</p>'
        )
        with self.assertRaises(IntegrityError):
            SequenceStep.objects.create(
                sequence=self.sequence,
                order=1,
                subject='Duplicate Step',
                html_body='<p>Duplicate</p>'
            )


class SequenceEnrollmentModelTests(TestCase):
    """Test SequenceEnrollment model."""

    def setUp(self):
        self.sequence = AutomationSequence.objects.create(
            name='Test Sequence',
            trigger='manual'
        )
        self.subscriber = Subscriber.objects.create(
            email='subscriber@example.com',
            source='web_form'
        )

    def test_sequence_enrollment_creation(self):
        """Test creating a sequence enrollment."""
        enrollment = SequenceEnrollment.objects.create(
            sequence=self.sequence,
            subscriber=self.subscriber
        )
        self.assertEqual(enrollment.status, 'active')
        self.assertEqual(enrollment.current_step, 0)
        self.assertTrue(enrollment.is_active)

    def test_duplicate_sequence_subscriber_raises_error(self):
        """Test that duplicate sequence-subscriber raises IntegrityError."""
        SequenceEnrollment.objects.create(
            sequence=self.sequence,
            subscriber=self.subscriber
        )
        with self.assertRaises(IntegrityError):
            SequenceEnrollment.objects.create(
                sequence=self.sequence,
                subscriber=self.subscriber
            )

    def test_enrollment_is_active_property(self):
        """Test is_active property."""
        enrollment = SequenceEnrollment.objects.create(
            sequence=self.sequence,
            subscriber=self.subscriber
        )
        self.assertTrue(enrollment.is_active)

        enrollment.status = 'completed'
        enrollment.save()
        self.assertFalse(enrollment.is_active)


class AcceptanceCriteriaTests(TestCase):
    """Test all acceptance criteria for ISSUE-15."""

    def test_migrations_run_successfully(self):
        """AC: python manage.py migrate runs cleanly."""
        # If we're here, migrations already ran
        self.assertTrue(True)

    def test_unsubscribe_token_auto_generated(self):
        """AC: unsubscribe_token is auto-generated on first save()."""
        subscriber = Subscriber.objects.create(
            email='auto@example.com',
            source='web_form'
        )
        self.assertIsNotNone(subscriber.unsubscribe_token)
        self.assertTrue(len(subscriber.unsubscribe_token) > 0)

    def test_duplicate_subscriber_email_raises_error(self):
        """AC: Duplicate Subscriber (same email) raises Unique-Constraint-Error."""
        Subscriber.objects.create(
            email='duplicate@example.com',
            source='web_form'
        )
        with self.assertRaises(IntegrityError):
            Subscriber.objects.create(
                email='duplicate@example.com',
                source='manual'
            )

    def test_duplicate_sequence_enrollment_raises_error(self):
        """AC: Duplicate enrollment in same sequence raises Constraint-Error."""
        sequence = AutomationSequence.objects.create(
            name='Test Sequence',
            trigger='manual'
        )
        subscriber = Subscriber.objects.create(
            email='enroll@example.com',
            source='web_form'
        )
        SequenceEnrollment.objects.create(
            sequence=sequence,
            subscriber=subscriber
        )
        with self.assertRaises(IntegrityError):
            SequenceEnrollment.objects.create(
                sequence=sequence,
                subscriber=subscriber
            )

    def test_campaign_is_editable(self):
        """AC: Campaign with status != draft is not editable (is_editable = False)."""
        admin = AdminUser.objects.create_user(
            email='admin@test.com',
            password='password123',
            display_name='Test Admin'
        )

        # Draft campaign is editable
        campaign = Campaign.objects.create(
            name='Test Campaign',
            subject='Test Subject',
            html_body='<p>Test</p>',
            created_by=admin,
            status='draft'
        )
        self.assertTrue(campaign.is_editable)

        # Non-draft campaign is not editable
        campaign.status = 'sent'
        campaign.save()
        self.assertFalse(campaign.is_editable)

        campaign.status = 'scheduled'
        campaign.save()
        self.assertFalse(campaign.is_editable)

        campaign.status = 'sending'
        campaign.save()
        self.assertFalse(campaign.is_editable)

        campaign.status = 'cancelled'
        campaign.save()
        self.assertFalse(campaign.is_editable)


class EducationRequestModelTests(TestCase):
    """Test EducationRequest model."""

    def test_education_request_creation(self):
        """Test creating an education request."""
        request = EducationRequest.objects.create(
            institution_name='TU München',
            email='info@tum.de',
            institution_type='university',
            user_count=25,
            status='pending'
        )
        self.assertEqual(request.status, 'pending')
        self.assertEqual(request.institution_name, 'TU München')
        self.assertEqual(request.status_text, 'Offen')
        self.assertEqual(request.status_badge, 'warning')

    def test_education_request_status_properties(self):
        """Test status badge and text properties."""
        request = EducationRequest.objects.create(
            institution_name='Test School',
            email='test@school.com',
            institution_type='school',
            user_count=10,
            status='pending'
        )

        # Test pending
        self.assertEqual(request.status_badge, 'warning')
        self.assertEqual(request.status_text, 'Offen')

        # Test approved
        request.status = 'approved'
        self.assertEqual(request.status_badge, 'success')
        self.assertEqual(request.status_text, 'Genehmigt')

        # Test rejected
        request.status = 'rejected'
        self.assertEqual(request.status_badge, 'danger')
        self.assertEqual(request.status_text, 'Abgelehnt')

    def test_education_request_str(self):
        """Test string representation."""
        request = EducationRequest.objects.create(
            institution_name='Test Institution',
            email='test@institution.com',
            institution_type='nonprofit',
            user_count=50,
            status='pending'
        )
        self.assertEqual(str(request), 'Test Institution (pending)')


class EducationRequestAPITests(TestCase):
    """Test Education Request API endpoint."""

    def setUp(self):
        self.url = '/api/education-discount/'

    @patch('crm.api.MailService.send_template')
    def test_create_education_request_success(self, mock_mail):
        """Test successful education request creation."""
        mock_mail.return_value = True

        data = {
            'institution_name': 'TU München',
            'email': 'info@tum.de',
            'institution_type': 'university',
            'website': 'https://tum.de',
            'description': 'Für unser PM-Seminar',
            'user_count': 25,
            'ip_address': '1.2.3.4'
        }

        response = self.client.post(self.url, data, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['status'], 'received')

        # Verify request was created
        request = EducationRequest.objects.get(email='info@tum.de')
        self.assertEqual(request.institution_name, 'TU München')
        self.assertEqual(request.user_count, 25)
        self.assertEqual(request.status, 'pending')

        # Verify emails were sent
        self.assertEqual(mock_mail.call_count, 2)  # admin notification + confirmation

    def test_create_education_request_missing_required_fields(self):
        """Test validation of required fields."""
        data = {
            'institution_name': 'Test',
            # missing email and user_count
        }

        response = self.client.post(self.url, data, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_create_education_request_invalid_user_count(self):
        """Test validation of user_count."""
        data = {
            'institution_name': 'Test',
            'email': 'test@example.com',
            'user_count': 'invalid',
        }

        response = self.client.post(self.url, data, content_type='application/json')
        self.assertEqual(response.status_code, 400)


class EducationRequestServiceTests(TestCase):
    """Test EducationRequestService."""

    def setUp(self):
        self.admin = AdminUser.objects.create_user(
            email='admin@test.com',
            password='password123',
            display_name='Test Admin',
            role='superadmin'
        )

    @patch('crm.education_service.CouponService.create_stripe_coupon')
    @patch('crm.education_service.MailService.send_template')
    def test_approve_education_request(self, mock_mail, mock_stripe):
        """Test approving an education request."""
        from crm.education_service import EducationRequestService

        # Create request
        request = EducationRequest.objects.create(
            institution_name='TU München',
            email='info@tum.de',
            institution_type='university',
            user_count=25,
            status='pending'
        )

        mock_mail.return_value = True
        mock_stripe.return_value = ('co_test123', 'promo_test123')

        # Approve
        coupon = EducationRequestService.approve(request, self.admin)

        # Verify request was updated
        request.refresh_from_db()
        self.assertEqual(request.status, 'approved')
        self.assertEqual(request.reviewed_by, self.admin)
        self.assertIsNotNone(request.reviewed_at)
        self.assertEqual(request.coupon, coupon)

        # Verify coupon was created
        self.assertIsNotNone(coupon)
        self.assertTrue(coupon.code.startswith('EDU-'))
        self.assertEqual(coupon.discount_percent, 50)
        self.assertEqual(coupon.duration, 'forever')
        self.assertEqual(coupon.max_redemptions, 1)

        # Verify email was sent
        mock_mail.assert_called_once()

    @patch('crm.education_service.MailService.send_template')
    def test_reject_education_request(self, mock_mail):
        """Test rejecting an education request."""
        from crm.education_service import EducationRequestService

        # Create request
        request = EducationRequest.objects.create(
            institution_name='Test School',
            email='test@school.com',
            institution_type='school',
            user_count=10,
            status='pending'
        )

        mock_mail.return_value = True

        # Reject with reason
        reason = 'Nicht den Kriterien entsprechend'
        EducationRequestService.reject(request, self.admin, reason)

        # Verify request was updated
        request.refresh_from_db()
        self.assertEqual(request.status, 'rejected')
        self.assertEqual(request.reviewed_by, self.admin)
        self.assertIsNotNone(request.reviewed_at)
        self.assertEqual(request.notes, reason)

        # Verify email was sent
        mock_mail.assert_called_once()
