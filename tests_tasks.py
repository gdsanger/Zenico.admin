"""
Unit tests for newsletter Celery tasks.
"""

from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock
from datetime import timedelta

from newsletter.models import (
    Subscriber, Campaign, CampaignMail,
    AutomationSequence, SequenceStep, SequenceEnrollment
)
from newsletter.tasks import (
    process_sequence_enrollments,
    send_campaign,
    send_scheduled_campaigns
)


class SequenceEnrollmentTasksTestCase(TestCase):
    """Test cases for sequence enrollment processing."""

    def setUp(self):
        # Create a subscriber
        self.subscriber = Subscriber.objects.create(
            email='test@example.com',
            first_name='Test',
            source='web_form',
            status='active',
            confirmed_at=timezone.now()
        )

        # Create a sequence with steps
        self.sequence = AutomationSequence.objects.create(
            name='Test Sequence',
            trigger='subscriber_confirmed',
            is_active=True
        )

        self.step1 = SequenceStep.objects.create(
            sequence=self.sequence,
            order=1,
            delay_days=0,
            subject='Step 1',
            html_body='Step 1 body',
        )

        self.step2 = SequenceStep.objects.create(
            sequence=self.sequence,
            order=2,
            delay_days=2,
            subject='Step 2',
            html_body='Step 2 body',
        )

    @patch('newsletter.tasks.MailService.send')
    def test_process_sequence_enrollments_sends_next_step(self, mock_send):
        """Test that process_sequence_enrollments sends the next step."""
        mock_send.return_value = True

        # Create enrollment ready for step 1
        enrollment = SequenceEnrollment.objects.create(
            sequence=self.sequence,
            subscriber=self.subscriber,
            status='active',
            current_step=0,
            next_send_at=timezone.now() - timedelta(minutes=1)
        )

        # Run task
        result = process_sequence_enrollments()

        # Verify email was sent
        self.assertTrue(mock_send.called)
        self.assertEqual(result['processed'], 1)

        # Verify enrollment was updated
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.current_step, 1)

    @patch('newsletter.tasks.MailService.send')
    def test_process_sequence_enrollments_completes_when_no_more_steps(self, mock_send):
        """Test that enrollments are marked completed when no more steps."""
        mock_send.return_value = True

        # Create enrollment at last step
        enrollment = SequenceEnrollment.objects.create(
            sequence=self.sequence,
            subscriber=self.subscriber,
            status='active',
            current_step=2,  # Already sent step 2
            next_send_at=timezone.now() - timedelta(minutes=1)
        )

        # Run task
        result = process_sequence_enrollments()

        # Verify enrollment was marked as completed
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'completed')
        self.assertIsNotNone(enrollment.completed_at)
        self.assertEqual(result['completed'], 1)

    def test_process_sequence_enrollments_skips_unconfirmed(self):
        """Test that unconfirmed subscribers are skipped."""
        # Create unconfirmed subscriber
        unconfirmed = Subscriber.objects.create(
            email='unconfirmed@example.com',
            source='web_form',
            status='active',
            confirmed_at=None
        )

        enrollment = SequenceEnrollment.objects.create(
            sequence=self.sequence,
            subscriber=unconfirmed,
            status='active',
            current_step=0,
            next_send_at=timezone.now() - timedelta(minutes=1)
        )

        # Run task
        with patch('newsletter.tasks.MailService.send') as mock_send:
            process_sequence_enrollments()
            self.assertFalse(mock_send.called)


class CampaignTasksTestCase(TestCase):
    """Test cases for campaign sending tasks."""

    def setUp(self):
        # Create confirmed subscribers
        self.subscriber1 = Subscriber.objects.create(
            email='test1@example.com',
            first_name='Test1',
            source='web_form',
            status='active',
            confirmed_at=timezone.now()
        )

        self.subscriber2 = Subscriber.objects.create(
            email='test2@example.com',
            first_name='Test2',
            source='web_form',
            status='active',
            confirmed_at=timezone.now()
        )

        # Create campaign
        self.campaign = Campaign.objects.create(
            name='Test Campaign',
            subject='Test Subject',
            html_body='Test Body {{unsubscribe_url}}',
            status='draft',
            segment='all'
        )

    @patch('newsletter.tasks.MailService.send')
    def test_send_campaign_creates_campaign_mails(self, mock_send):
        """Test that send_campaign creates CampaignMail entries."""
        mock_send.return_value = True

        # Send campaign
        result = send_campaign(str(self.campaign.id))

        # Verify CampaignMail entries were created
        self.assertEqual(CampaignMail.objects.filter(campaign=self.campaign).count(), 2)
        self.assertEqual(result['sent'], 2)

        # Verify campaign status
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, 'sent')
        self.assertIsNotNone(self.campaign.sent_at)
        self.assertEqual(self.campaign.recipient_count, 2)

    @patch('newsletter.tasks.MailService.send')
    def test_send_campaign_updates_mail_status(self, mock_send):
        """Test that send_campaign updates CampaignMail status."""
        mock_send.return_value = True

        # Send campaign
        send_campaign(str(self.campaign.id))

        # Verify all mails are marked as sent
        sent_count = CampaignMail.objects.filter(
            campaign=self.campaign,
            status='sent'
        ).count()
        self.assertEqual(sent_count, 2)

    def test_send_scheduled_campaigns_triggers_send(self):
        """Test that send_scheduled_campaigns triggers send_campaign."""
        # Create scheduled campaign
        scheduled_campaign = Campaign.objects.create(
            name='Scheduled Campaign',
            subject='Test',
            html_body='Test',
            status='scheduled',
            scheduled_at=timezone.now() - timedelta(minutes=1),
            segment='all'
        )

        with patch('newsletter.tasks.send_campaign.delay') as mock_delay:
            result = send_scheduled_campaigns()

            # Verify send_campaign was triggered
            self.assertTrue(mock_delay.called)
            self.assertEqual(result['triggered'], 1)

            # Verify campaign status changed to sending
            scheduled_campaign.refresh_from_db()
            self.assertEqual(scheduled_campaign.status, 'sending')
