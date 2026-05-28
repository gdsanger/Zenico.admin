"""
Celery tasks for newsletter automation.

These tasks handle:
1. Processing sequence enrollments (hourly)
2. Sending campaigns (triggered)
3. Sending scheduled campaigns (every 5 minutes)
"""

import logging
import time
from celery import shared_task
from django.utils import timezone
from django.db import transaction

from newsletter.models import (
    Subscriber, Campaign, CampaignMail,
    AutomationSequence, SequenceEnrollment, SequenceStep
)
from core.services.mail import MailService
from core.services.audit import AuditService, AuditAction

logger = logging.getLogger(__name__)


@shared_task
def process_sequence_enrollments():
    """
    Process all active sequence enrollments where next_send_at <= now().

    For each enrollment:
    1. Get the next SequenceStep (current_step + 1)
    2. If step exists: send email, increment current_step, set next_send_at
    3. If no more steps: mark as completed

    Runs hourly via Celery Beat.
    """
    logger.info('Starting process_sequence_enrollments task')

    # Get all active enrollments that are due
    enrollments = SequenceEnrollment.objects.filter(
        status='active',
        next_send_at__lte=timezone.now()
    ).select_related('sequence', 'subscriber')

    processed_count = 0
    completed_count = 0
    failed_count = 0

    for enrollment in enrollments:
        try:
            with transaction.atomic():
                # Get the next step
                next_step_order = enrollment.current_step + 1

                try:
                    step = SequenceStep.objects.get(
                        sequence=enrollment.sequence,
                        order=next_step_order
                    )
                except SequenceStep.DoesNotExist:
                    # No more steps - mark as completed
                    enrollment.status = 'completed'
                    enrollment.completed_at = timezone.now()
                    enrollment.save()

                    completed_count += 1

                    # Log audit
                    AuditService.log(
                        action=AuditAction.SEQUENCE_COMPLETED,
                        resource_type='SequenceEnrollment',
                        resource_id=str(enrollment.id),
                        actor_email='system',
                        after={
                            'sequence': enrollment.sequence.name,
                            'subscriber': enrollment.subscriber.email,
                        },
                        note=f'Sequence completed for {enrollment.subscriber.email}'
                    )

                    continue

                # Check if subscriber is still active and confirmed
                if (enrollment.subscriber.status != 'active' or
                    not enrollment.subscriber.confirmed_at):
                    # Skip this enrollment
                    logger.info(
                        f'Skipping enrollment {enrollment.id}: subscriber not active/confirmed'
                    )
                    continue

                # Send the email
                unsubscribe_url = (
                    f"https://zenico.app/api/newsletter/unsubscribe/"
                    f"{enrollment.subscriber.unsubscribe_token}/"
                )

                success = MailService.send(
                    to=enrollment.subscriber.email,
                    subject=step.subject,
                    html_body=step.html_body.replace(
                        '{{unsubscribe_url}}', unsubscribe_url
                    ).replace(
                        '{{first_name}}', enrollment.subscriber.first_name or ''
                    ),
                    text_body=step.text_body,
                )

                if success:
                    # Update enrollment
                    enrollment.current_step = next_step_order

                    # Calculate next send time
                    # Get the next step to determine delay
                    try:
                        next_next_step = SequenceStep.objects.get(
                            sequence=enrollment.sequence,
                            order=next_step_order + 1
                        )
                        enrollment.next_send_at = timezone.now() + timezone.timedelta(
                            days=next_next_step.delay_days
                        )
                    except SequenceStep.DoesNotExist:
                        # This was the last step - will be completed next run
                        enrollment.next_send_at = timezone.now()

                    enrollment.save()
                    processed_count += 1

                    logger.info(
                        f'Sent step {next_step_order} of sequence {enrollment.sequence.name} '
                        f'to {enrollment.subscriber.email}'
                    )
                else:
                    failed_count += 1
                    logger.error(
                        f'Failed to send step {next_step_order} to {enrollment.subscriber.email}'
                    )

        except Exception as e:
            failed_count += 1
            logger.exception(f'Error processing enrollment {enrollment.id}: {e}')

    logger.info(
        f'Finished process_sequence_enrollments: '
        f'{processed_count} sent, {completed_count} completed, {failed_count} failed'
    )

    return {
        'processed': processed_count,
        'completed': completed_count,
        'failed': failed_count,
    }


@shared_task
def send_campaign(campaign_id: str):
    """
    Send a campaign to all eligible recipients.

    1. Get campaign by ID
    2. Determine recipients based on segment
    3. Create CampaignMail entries (status=pending)
    4. Send emails in batches (50 per batch, 1s pause between batches)
    5. Update CampaignMail status (sent/failed)
    6. Update campaign (status=sent, sent_at, recipient_count)

    Args:
        campaign_id: UUID of the campaign to send
    """
    logger.info(f'Starting send_campaign task for campaign {campaign_id}')

    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.error(f'Campaign {campaign_id} not found')
        return {'error': 'Campaign not found'}

    # Get recipients based on segment
    if campaign.segment == 'all':
        # All active confirmed subscribers
        subscribers = Subscriber.objects.filter(
            status='active',
            confirmed_at__isnull=False
        )
    elif campaign.segment == 'leads':
        # Subscribers with linked Contact (not converted)
        subscribers = Subscriber.objects.filter(
            status='active',
            confirmed_at__isnull=False,
            contact__isnull=False,
            contact__converted_to__isnull=True
        )
    elif campaign.segment == 'customers':
        # This would require matching email with Customer table
        # For now, just active confirmed subscribers
        subscribers = Subscriber.objects.filter(
            status='active',
            confirmed_at__isnull=False
        )
    else:  # manual
        # Manual segment not implemented yet - send to all for now
        subscribers = Subscriber.objects.filter(
            status='active',
            confirmed_at__isnull=False
        )

    recipient_count = subscribers.count()
    logger.info(f'Sending campaign to {recipient_count} recipients')

    # Create CampaignMail entries
    campaign_mails = []
    for subscriber in subscribers:
        campaign_mail, created = CampaignMail.objects.get_or_create(
            campaign=campaign,
            subscriber=subscriber,
            defaults={'status': 'pending'}
        )
        if created:
            campaign_mails.append(campaign_mail)

    # Send emails in batches
    BATCH_SIZE = 50
    sent_count = 0
    failed_count = 0

    for i in range(0, len(campaign_mails), BATCH_SIZE):
        batch = campaign_mails[i:i + BATCH_SIZE]

        for campaign_mail in batch:
            try:
                # Prepare email content
                unsubscribe_url = (
                    f"https://zenico.app/api/newsletter/unsubscribe/"
                    f"{campaign_mail.subscriber.unsubscribe_token}/"
                )

                html_body = campaign.html_body.replace(
                    '{{unsubscribe_url}}', unsubscribe_url
                ).replace(
                    '{{first_name}}', campaign_mail.subscriber.first_name or ''
                ).replace(
                    '{{email}}', campaign_mail.subscriber.email
                )

                # Send email
                success = MailService.send(
                    to=campaign_mail.subscriber.email,
                    subject=campaign.subject,
                    html_body=html_body,
                    text_body=campaign.text_body,
                )

                if success:
                    campaign_mail.status = 'sent'
                    campaign_mail.sent_at = timezone.now()
                    sent_count += 1
                else:
                    campaign_mail.status = 'failed'
                    campaign_mail.error_message = 'Failed to send email'
                    failed_count += 1

                campaign_mail.save()

            except Exception as e:
                campaign_mail.status = 'failed'
                campaign_mail.error_message = str(e)
                campaign_mail.save()
                failed_count += 1
                logger.exception(f'Error sending campaign mail {campaign_mail.id}: {e}')

        # Pause between batches to respect rate limits
        if i + BATCH_SIZE < len(campaign_mails):
            time.sleep(1)

    # Update campaign
    campaign.status = 'sent'
    campaign.sent_at = timezone.now()
    campaign.recipient_count = recipient_count
    campaign.save()

    # Log audit
    AuditService.log(
        action=AuditAction.CAMPAIGN_SENT,
        resource_type='Campaign',
        resource_id=str(campaign.id),
        actor_email='system',
        after={
            'campaign': campaign.name,
            'recipient_count': recipient_count,
            'sent': sent_count,
            'failed': failed_count,
        },
        note=f'Campaign {campaign.name} sent to {recipient_count} recipients'
    )

    logger.info(
        f'Finished send_campaign for {campaign.name}: '
        f'{sent_count} sent, {failed_count} failed'
    )

    return {
        'campaign': campaign.name,
        'recipient_count': recipient_count,
        'sent': sent_count,
        'failed': failed_count,
    }


@shared_task
def send_scheduled_campaigns():
    """
    Check for campaigns with scheduled_at <= now() and trigger send_campaign.

    Runs every 5 minutes via Celery Beat.
    """
    logger.info('Starting send_scheduled_campaigns task')

    campaigns = Campaign.objects.filter(
        status='scheduled',
        scheduled_at__lte=timezone.now()
    )

    triggered_count = 0

    for campaign in campaigns:
        # Update status to sending
        campaign.status = 'sending'
        campaign.save()

        # Trigger send_campaign task
        send_campaign.delay(str(campaign.id))
        triggered_count += 1

        logger.info(f'Triggered send_campaign for {campaign.name}')

    logger.info(f'Finished send_scheduled_campaigns: {triggered_count} campaigns triggered')

    return {'triggered': triggered_count}
