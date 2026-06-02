"""
Celery tasks for the instances app.
"""

import logging
from celery import shared_task
from django.db.models import Count
from instances.models import InstanceHeartbeat

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
