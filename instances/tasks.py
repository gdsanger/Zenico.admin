"""
Celery tasks for the instances app.
"""

import logging
from datetime import date, timedelta
from celery import shared_task
from django.db.models import Count
from instances.models import InstanceHeartbeat, Instance
from core.services.mail import MailService

logger = logging.getLogger(__name__)


@shared_task
def cleanup_old_heartbeats():
    """
    Clean up old instance heartbeats, keeping only the last 30 per instance.
    This task runs daily via Celery Beat.
    """
    logger.info('Starting cleanup_old_heartbeats task')

    # Get all instances that have more than 30 heartbeats
    instances_with_heartbeats = (
        InstanceHeartbeat.objects
        .values('instance_id')
        .annotate(count=Count('id'))
        .filter(count__gt=30)
    )

    total_deleted = 0

    for item in instances_with_heartbeats:
        instance_id = item['instance_id']

        # Get heartbeats for this instance, ordered by received_at descending
        heartbeats = InstanceHeartbeat.objects.filter(
            instance_id=instance_id
        ).order_by('-received_at')

        # Get IDs of heartbeats to keep (last 30)
        ids_to_keep = list(heartbeats.values_list('id', flat=True)[:30])

        # Delete all heartbeats except the last 30
        deleted_count, _ = InstanceHeartbeat.objects.filter(
            instance_id=instance_id
        ).exclude(id__in=ids_to_keep).delete()

        total_deleted += deleted_count
        logger.debug(f'Deleted {deleted_count} heartbeats for instance {instance_id}')

    logger.info(f'Cleanup completed. Deleted {total_deleted} heartbeats total.')

    return {
        'deleted': total_deleted,
        'instances_processed': len(instances_with_heartbeats)
    }


@shared_task
def process_cancellations():
    """
    Process cancelled instances daily at 06:00 UTC.

    Actions:
    1. Instances whose subscription ends today → set status to 'read_only'
    2. Instances 75 days after cancellation → send deletion warning email
    3. Instances 90 days after cancellation → archive and delete data
    """
    logger.info('Starting process_cancellations task')
    today = date.today()

    # 1. Instances whose subscription ends today → read_only mode
    instances_ending_today = Instance.objects.filter(
        cancelled_at=today,
        status='active'
    )

    read_only_count = 0
    for instance in instances_ending_today:
        instance.status = 'read_only'
        instance.save(update_fields=['status', 'updated_at'])

        # Send read-only notification
        _send_read_only_notification(instance)

        logger.info(f'Set instance {instance.fqdn} to read_only mode')
        read_only_count += 1

    # 2. 75 days after cancellation → deletion warning
    warning_date = today - timedelta(days=75)
    instances_75_days = Instance.objects.filter(
        cancelled_at=warning_date,
        status='read_only'
    )

    warning_count = 0
    for instance in instances_75_days:
        _send_deletion_warning(instance)
        logger.info(f'Sent deletion warning to {instance.customer.billing_email} for {instance.fqdn}')
        warning_count += 1

    # 3. 90 days after cancellation → archive and delete
    deletion_date = today - timedelta(days=90)
    instances_90_days = Instance.objects.filter(
        cancelled_at=deletion_date,
        status='read_only'
    )

    deleted_count = 0
    for instance in instances_90_days:
        _archive_and_delete(instance)
        logger.info(f'Archived and deleted instance {instance.fqdn}')
        deleted_count += 1

    logger.info(
        f'Cancellation processing completed: '
        f'{read_only_count} set to read-only, '
        f'{warning_count} warnings sent, '
        f'{deleted_count} deleted'
    )

    return {
        'read_only_count': read_only_count,
        'warning_count': warning_count,
        'deleted_count': deleted_count,
    }


def _send_read_only_notification(instance):
    """
    Send email notification that instance is now in read-only mode.

    Args:
        instance: Instance object
    """
    customer = instance.customer

    try:
        MailService.send_template(
            to=customer.billing_email,
            subject='Zenico Instance Now in Read-Only Mode',
            template_name='mail/read_only_notification',
            context={
                'customer': customer,
                'instance': instance,
                'reactivation_deadline': instance.cancelled_at + timedelta(days=90),
            }
        )
    except Exception as e:
        logger.error(f'Failed to send read-only notification to {customer.billing_email}: {e}')


def _send_deletion_warning(instance):
    """
    Send warning email 75 days after cancellation (15 days before deletion).

    Args:
        instance: Instance object
    """
    customer = instance.customer
    deletion_date = instance.cancelled_at + timedelta(days=90)

    try:
        MailService.send_template(
            to=customer.billing_email,
            subject='Zenico Data Deletion Warning - 15 Days Remaining',
            template_name='mail/deletion_warning',
            context={
                'customer': customer,
                'instance': instance,
                'deletion_date': deletion_date,
                'days_remaining': 15,
            }
        )
    except Exception as e:
        logger.error(f'Failed to send deletion warning to {customer.billing_email}: {e}')


def _archive_and_delete(instance):
    """
    Archive instance data and mark as deprovisioned.

    Args:
        instance: Instance object
    """
    # In a production environment, you would:
    # 1. Create a backup/archive of the instance data
    # 2. Store it securely for compliance purposes
    # 3. Delete the actual data from production systems

    # For now, we'll just mark the instance as deprovisioned
    instance.status = 'deprovisioned'
    instance.save(update_fields=['status', 'updated_at'])

    # Send final notification
    customer = instance.customer
    try:
        MailService.send_template(
            to=customer.billing_email,
            subject='Zenico Data Deletion Completed',
            template_name='mail/deletion_completed',
            context={
                'customer': customer,
                'instance': instance,
            }
        )
    except Exception as e:
        logger.error(f'Failed to send deletion confirmation to {customer.billing_email}: {e}')

