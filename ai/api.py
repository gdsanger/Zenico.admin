"""
AI Proxy API for Zenico instances.

Provides agent-based AI completion with token tracking and budget enforcement.
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from instances.authentication import ApiKeyAuthentication
from instances.models import get_week_start
from ai.models import AIAgent, AITokenBudget
from ai.agent_service import AgentService

logger = logging.getLogger(__name__)


class AICompleteView(APIView):
    """
    POST /api/ai/complete/

    Agent-based AI completion endpoint with token tracking.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Handle AI completion request using agents.

        Request body:
        {
            "agent": "task-summarizer",
            "input": "Task text to summarize..."
        }

        Response:
        {
            "text": "AI response...",
            "from_cache": false,
            "tokens_remaining": 156800
        }
        """
        instance = request.user  # ApiKeyAuthentication sets this
        subscription = instance.subscription

        # Check if AI addon is active
        if not subscription or not subscription.ai_addon_active:
            logger.warning(f'AI request rejected for instance {instance.id}: AI addon not active')
            return Response(
                {
                    'error': 'ai_addon_not_active',
                    'message': 'KI-Addon ist für diese Instanz nicht aktiviert.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # Extract request data
        agent_name = request.data.get('agent')
        input_text = request.data.get('input', '')

        if not agent_name:
            return Response(
                {'error': 'agent ist erforderlich.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check token budget
        budget, _ = AITokenBudget.objects.get_or_create(instance=instance)
        budget._reset_week_if_needed()

        if budget.is_exhausted:
            # Calculate reset time
            week_start_date = get_week_start()
            next_monday = week_start_date + timedelta(days=7)
            week_resets_at = datetime.combine(
                next_monday,
                datetime.min.time()
            ).replace(tzinfo=timezone.utc)

            logger.warning(
                f'AI request rejected for instance {instance.id}: '
                f'weekly token limit exceeded ({budget.tokens_used_week}/{budget.weekly_limit})'
            )

            return Response(
                {
                    'error': 'token_limit_exceeded',
                    'message': 'Wöchentliches Token-Budget erschöpft.',
                    'tokens_remaining': 0,
                    'week_resets_at': week_resets_at.isoformat(),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Execute agent
        try:
            service = AgentService()
            text, from_cache = service.execute(
                agent_name=agent_name,
                input_text=input_text,
                instance=instance,
            )

            # Refresh budget to get updated values
            budget.refresh_from_db()

            return Response({
                'text': text,
                'from_cache': from_cache,
                'tokens_remaining': budget.tokens_remaining,
            })

        except AIAgent.DoesNotExist:
            logger.warning(f'Agent "{agent_name}" not found for instance {instance.id}')
            return Response(
                {'error': f'Agent "{agent_name}" nicht gefunden.'},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            logger.exception(f'AI agent execution failed for instance {instance.id}')
            return Response(
                {'error': 'Agent execution failed', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
