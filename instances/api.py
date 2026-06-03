"""
REST API endpoints for Zenico instances.

These endpoints are called by Zenico.app instances and require API key authentication.
"""

import logging
from datetime import date
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from instances.authentication import ApiKeyAuthentication
from instances.models import Instance, InstanceHeartbeat, AITokenUsage, get_week_start
from ai.models import AITokenBudget
from core.services.audit import AuditService, AuditAction
from datetime import timezone as dt_timezone
from ai.models import AIAgent, AITokenBudget
from ai.agent_service import AgentService

logger = logging.getLogger(__name__)


class InstanceRegisterView(APIView):
    """
    POST /api/instance/register/

    Phone-home endpoint for Zenico instances.
    Called on app start, user changes, or version updates.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Handle instance registration / phone-home.

        Request body:
        {
            "customer_id": "uuid",
            "instance_id": "uuid",
            "url": "https://gds.zenico.app",
            "version": "1.4.2",
            "active_users": 12
        }
        """
        instance = request.user  # ApiKeyAuthentication sets this

        # Extract data
        data = request.data
        customer_id = data.get('customer_id', '').strip()
        instance_id = data.get('instance_id', '').strip()
        url = data.get('url', '').strip()
        version = data.get('version', '').strip()
        active_users = data.get('active_users', 0)

        # Validate required fields
        if not all([customer_id, instance_id, url, version]):
            return Response(
                {'error': 'customer_id, instance_id, url, and version are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify that the customer_id and instance_id match the authenticated instance
        if str(instance.customer.id) != customer_id:
            logger.warning(
                f'Customer ID mismatch for instance {instance.id}: '
                f'provided {customer_id}, expected {instance.customer.id}'
            )
            return Response(
                {'error': 'customer_id does not match authenticated instance'},
                status=status.HTTP_403_FORBIDDEN
            )

        if str(instance.id) != instance_id:
            logger.warning(
                f'Instance ID mismatch: provided {instance_id}, expected {instance.id}'
            )
            return Response(
                {'error': 'instance_id does not match authenticated instance'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get IP address
        ip_address = request.META.get('REMOTE_ADDR')

        # Check if version changed
        version_changed = instance.reported_version and instance.reported_version != version

        # Update instance fields
        instance.reported_url = url
        instance.reported_version = version
        instance.reported_active_users = active_users
        instance.last_heartbeat = timezone.now()

        # Set status to active if currently provisioning
        if instance.status == 'provisioning':
            instance.status = 'active'
            instance.provisioned_at = timezone.now()

        instance.save(update_fields=[
            'reported_url', 'reported_version', 'reported_active_users',
            'last_heartbeat', 'status', 'provisioned_at', 'updated_at'
        ])

        # Create heartbeat entry
        InstanceHeartbeat.objects.create(
            instance=instance,
            url=url,
            version=version,
            active_users=active_users,
            ip_address=ip_address,
        )

        # Log audit entry if version changed
        if version_changed:
            AuditService.log(
                action=AuditAction.INSTANCE_VERSION_CHANGED,
                resource_type='Instance',
                resource_id=str(instance.id),
                actor_email='system',
                actor_ip=ip_address,
                customer=instance.customer,
                instance_id=instance.id,
                before={'version': instance.reported_version},
                after={'version': version},
                note=f'Instance version changed from {instance.reported_version} to {version}'
            )

        # Prepare license and AI budget response
        subscription = instance.subscription
        plan = subscription.plan if subscription else None

        # Get or create AI token budget
        budget, _ = AITokenBudget.objects.get_or_create(instance=instance)
        budget._reset_week_if_needed()

        # Calculate week reset time (next Monday at 00:00:00 UTC)
        week_start_date = get_week_start()
        next_monday = week_start_date + timezone.timedelta(days=7)
        week_resets_at = timezone.datetime.combine(
            next_monday,
            timezone.datetime.min.time()
        ).replace(tzinfo=dt_timezone.utc)

        response_data = {
            'plan': plan.name if plan else 'unknown',
            'user_seats': instance.user_seats,
            'instance_status': instance.status,
            'ai_addon': subscription.ai_addon_active if subscription else False,
            'ai_weekly_limit': budget.weekly_limit,
            'ai_tokens_used_this_week': budget.tokens_used_week,
            'ai_tokens_remaining_this_week': budget.tokens_remaining,
            'week_resets_at': week_resets_at.isoformat(),
        }

        return Response(response_data, status=status.HTTP_200_OK)


class InstanceLicenseView(APIView):
    """
    GET /api/instance/license/

    Returns license and subscription information for the authenticated instance.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Return license information for the authenticated instance.
        """
        instance = request.user  # ApiKeyAuthentication sets this
        customer = instance.customer
        subscription = instance.subscription
        plan = subscription.plan if subscription else None

        # Calculate AI token usage
        week_start_date = get_week_start()
        ai_tokens_used_this_week = AITokenUsage.objects.filter(
            instance=instance,
            week_start=week_start_date
        ).aggregate(
            total=Sum('tokens_in') + Sum('tokens_out')
        )['total'] or 0

        # Get AI weekly limit
        ai_weekly_limit = 200000 if subscription and subscription.ai_addon_active else 0
        ai_tokens_remaining = max(0, ai_weekly_limit - ai_tokens_used_this_week)

        # Calculate week reset time
        next_monday = week_start_date + timezone.timedelta(days=7)
        week_resets_at = timezone.datetime.combine(
            next_monday,
            timezone.datetime.min.time()
        ).replace(tzinfo=timezone.utc)

        # Get monthly usage (last 2 months)
        monthly_usage = []
        today = date.today()
        for i in range(2):
            # Calculate first day of month (going back i months)
            if today.month - i <= 0:
                month_date = date(today.year - 1, 12 + (today.month - i), 1)
            else:
                month_date = date(today.year, today.month - i, 1)

            usage = AITokenUsage.objects.filter(
                instance=instance,
                month=month_date
            ).aggregate(
                tokens_in_sum=Sum('tokens_in'),
                tokens_out_sum=Sum('tokens_out')
            )

            if usage['tokens_in_sum'] or usage['tokens_out_sum']:
                monthly_usage.append({
                    'month': month_date.strftime('%Y-%m'),
                    'tokens_in': usage['tokens_in_sum'] or 0,
                    'tokens_out': usage['tokens_out_sum'] or 0,
                })

        response_data = {
            'customer': {
                'id': str(customer.id),
                'company_name': customer.company_name,
                'slug': customer.slug,
            },
            'instance': {
                'id': str(instance.id),
                'slug': instance.slug,
                'fqdn': instance.fqdn,
                'is_master': instance.is_master,
                'status': instance.status,
                'version': instance.reported_version or instance.version,
            },
            'subscription': {
                'plan': plan.name if plan else 'unknown',
                'stripe_status': subscription.stripe_status if subscription else 'unknown',
                'user_seats': subscription.user_seats_total if subscription else 0,
                'instance_seats': subscription.instance_seats_total if subscription else 0,
                'current_period_end': subscription.current_period_end.isoformat() if subscription and subscription.current_period_end else None,
            },
            'ai': {
                'addon_active': subscription.ai_addon_active if subscription else False,
                'weekly_limit': ai_weekly_limit,
                'tokens_used_this_week': ai_tokens_used_this_week,
                'tokens_remaining_this_week': ai_tokens_remaining,
                'week_resets_at': week_resets_at.isoformat(),
                'monthly_usage': monthly_usage,
            },
        }

        return Response(response_data, status=status.HTTP_200_OK)


class AIAgentListView(APIView):
    """
    GET /api/instance/ai/agents/?context=task
    Authorization: Api-Key {key}

    Gibt alle aktiven Agenten für den angegebenen Kontext zurück.
    Wird von Zenico.app beim Laden von Task/Projekt/Anhang aufgerufen.

    Query Params:
        context: task | project | attachment (default: task)

    Response 200:
    [
        {
            "name": "text-optimization-agent",
            "display_name": "Beschreibung verbessern",
            "display_description": "Verbessert Formulierung...",
            "button_icon": "bi-magic"
        },
        ...
    ]
    """
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from ai.models import AIAgent

        context = request.GET.get('context', 'task')

        # Nur gültige Kontexte erlauben
        valid_contexts = ['task', 'project', 'attachment']
        if context not in valid_contexts:
            return Response(
                {'error': f'Ungültiger Kontext. Erlaubt: {valid_contexts}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        agents = AIAgent.objects.filter(
            active=True,
            context_type=context,
        ).order_by('sort_order', 'name')

        return Response([
            {
                'name':                agent.name,
                'display_name':        agent.display_name or agent.name,
                'display_description': agent.display_description,
                'button_icon':         agent.button_icon or 'bi-stars',
            }
            for agent in agents
        ], status=status.HTTP_200_OK)

class AICompleteView(APIView):
    """
    POST /api/instance/ai/complete/
    Authorization: Api-Key {key}

    Request:
    {
        "agent": "project-status-report",
        "input": "Task-Titel und Beschreibung..."
    }

    Response:
    {
        "text": "KI-Antwort...",
        "from_cache": false,
        "tokens_remaining": 156800
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        instance   = request.user
        agent_name = request.data.get('agent')
        input_text = request.data.get('input', '')

        if not agent_name:
            return Response(
                {'error': 'agent ist erforderlich.'},
                status=400
            )

        # Budget prüfen
        budget, _ = AITokenBudget.objects.get_or_create(
            instance=instance
        )
        budget._reset_week_if_needed()

        if budget.is_exhausted:
            return Response(
                {
                    'error':            'Wöchentliches Token-Budget erschöpft.',
                    'tokens_remaining': 0,
                },
                status=429
            )

        # Agent ausführen
        try:
            service = AgentService()
            text, from_cache = service.execute(
                agent_name = agent_name,
                input_text = input_text,
                instance   = instance,
            )
            budget.refresh_from_db()
            return Response({
                'text':             text,
                'from_cache':       from_cache,
                'tokens_remaining': budget.tokens_remaining,
            })

        except AIAgent.DoesNotExist:
            return Response(
                {'error': f'Agent "{agent_name}" nicht gefunden.'},
                status=404
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=500
            )