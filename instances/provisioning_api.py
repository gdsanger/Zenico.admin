"""
Provisioning API endpoints consumed by the zenico-provisioner agent.

Authentication: Authorization: Bearer <PROVISIONING_AGENT_TOKEN>
All endpoints return JSON. The agent is a single internal service, not a
per-instance client, so there is no session or instance-key auth here.
"""

import logging
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from instances.models import Instance
from instances.provisioning_permissions import IsProvisioningAgent

logger = logging.getLogger(__name__)


def _pending_payload(instance):
    return {
        'id': str(instance.id),
        'slug': instance.slug,
        'customer_id': str(instance.customer.id),
        'customer_slug': instance.customer.slug,
        'fqdn': instance.fqdn,
        'image_tag': instance.image_tag,
        'user_seats': instance.user_seats,
        'ai_addon_active': instance.ai_addon_active,
        'api_key': instance.api_key,
    }


class PendingInstancesView(APIView):
    """
    GET /api/instances/pending/

    Returns all instances that are waiting to be provisioned:
    status='provisioning' AND claimed_at IS NULL.
    """

    authentication_classes = []
    permission_classes = [IsProvisioningAgent]

    def get(self, request):
        instances = (
            Instance.objects
            .filter(status='provisioning', claimed_at__isnull=True)
            .select_related('customer')
        )
        return Response([_pending_payload(i) for i in instances])


class ClaimInstanceView(APIView):
    """
    POST /api/instances/{id}/claim/

    Atomically marks an unclaimed provisioning instance as claimed.
    Returns 409 if already claimed, wrong status, or not found.
    """

    authentication_classes = []
    permission_classes = [IsProvisioningAgent]

    def post(self, request, instance_id):
        if not Instance.objects.filter(pk=instance_id).exists():
            return Response(
                {'error': 'Instance not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        updated = Instance.objects.filter(
            pk=instance_id,
            status='provisioning',
            claimed_at__isnull=True,
        ).update(claimed_at=timezone.now())

        if updated == 0:
            return Response(
                {'error': 'Instance already claimed or not in provisioning status.'},
                status=status.HTTP_409_CONFLICT,
            )

        instance = Instance.objects.select_related('customer').get(pk=instance_id)
        logger.info('Provisioning agent claimed instance %s', instance_id)
        return Response(_pending_payload(instance))


class CompleteInstanceView(APIView):
    """
    POST /api/instances/{id}/complete/

    Marks a claimed provisioning instance as active and stores the
    deployment details reported by the agent.

    Request body:
    {
        "django_secret_key": "...",
        "db_name": "zenico_acme",
        "db_user": "zenico_acme",
        "server_host": "docker-host-01"
    }
    """

    authentication_classes = []
    permission_classes = [IsProvisioningAgent]

    def post(self, request, instance_id):
        try:
            instance = Instance.objects.get(pk=instance_id)
        except Instance.DoesNotExist:
            return Response(
                {'error': 'Instance not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if instance.status != 'provisioning' or instance.claimed_at is None:
            return Response(
                {'error': 'Instance is not in a claimable provisioning state.'},
                status=status.HTTP_409_CONFLICT,
            )

        data = request.data
        instance.status = 'active'
        instance.provisioned_at = timezone.now()
        instance.django_secret_key = data.get('django_secret_key', '')
        instance.db_name = data.get('db_name', '')
        instance.db_user = data.get('db_user', '')
        instance.server_host = data.get('server_host', '')
        instance.save(update_fields=[
            'status', 'provisioned_at', 'django_secret_key',
            'db_name', 'db_user', 'server_host', 'updated_at',
        ])

        logger.info('Instance %s provisioned successfully on %s', instance_id, instance.server_host)
        return Response({'status': 'active', 'provisioned_at': instance.provisioned_at.isoformat()})


class FailInstanceView(APIView):
    """
    POST /api/instances/{id}/fail/

    Marks a claimed provisioning instance as failed and records the error.

    Request body:
    { "error_message": "Health-Check failed after 120s" }
    """

    authentication_classes = []
    permission_classes = [IsProvisioningAgent]

    def post(self, request, instance_id):
        try:
            instance = Instance.objects.get(pk=instance_id)
        except Instance.DoesNotExist:
            return Response(
                {'error': 'Instance not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if instance.status != 'provisioning' or instance.claimed_at is None:
            return Response(
                {'error': 'Instance is not in a claimable provisioning state.'},
                status=status.HTTP_409_CONFLICT,
            )

        instance.status = 'failed'
        instance.provisioning_error = request.data.get('error_message', '')
        instance.save(update_fields=['status', 'provisioning_error', 'updated_at'])

        logger.warning(
            'Instance %s provisioning failed: %s',
            instance_id,
            instance.provisioning_error,
        )
        return Response({'status': 'failed'})
