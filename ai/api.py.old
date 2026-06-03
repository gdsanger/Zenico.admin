"""
AI Proxy API for Zenico instances.

Proxies AI requests to OpenAI or Anthropic, with token tracking and budget enforcement.
"""

import logging
import requests
from datetime import date
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from instances.authentication import ApiKeyAuthentication
from instances.models import AITokenUsage, get_week_start
from core.services.audit import AuditService, AuditAction

logger = logging.getLogger(__name__)


class AICompleteView(APIView):
    """
    POST /api/ai/complete/

    Proxy endpoint for AI completion requests.
    Enforces token budgets and tracks usage.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Handle AI completion request.

        Request body:
        {
            "provider": "anthropic",  # or "openai"
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "..."}],
            "max_tokens": 1000,
            "system": "You are an assistant."  # optional
        }
        """
        instance = request.user  # ApiKeyAuthentication sets this
        subscription = instance.subscription

        # Check if AI addon is active
        if not subscription or not subscription.ai_addon_active:
            logger.warning(f'AI request rejected for instance {instance.id}: AI addon not active')
            return Response(
                {
                    'error': 'ki_addon_not_active',
                    'message': 'KI-Addon ist für diese Instanz nicht gebucht.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # Check weekly token budget
        week_start_date = get_week_start()
        ai_weekly_limit = 200000  # Default limit, should be configurable per plan

        tokens_used_this_week = AITokenUsage.objects.filter(
            instance=instance,
            week_start=week_start_date
        ).aggregate(
            total=Sum('tokens_in') + Sum('tokens_out')
        )['total'] or 0

        if tokens_used_this_week >= ai_weekly_limit:
            # Calculate reset time
            next_monday = week_start_date + timezone.timedelta(days=7)
            week_resets_at = timezone.datetime.combine(
                next_monday,
                timezone.datetime.min.time()
            ).replace(tzinfo=timezone.utc)

            logger.warning(
                f'AI request rejected for instance {instance.id}: '
                f'weekly token limit exceeded ({tokens_used_this_week}/{ai_weekly_limit})'
            )

            return Response(
                {
                    'error': 'token_limit_exceeded',
                    'message': 'Wöchentliches KI-Token-Budget erschöpft.',
                    'resets_at': week_resets_at.isoformat()
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Extract request data
        data = request.data
        provider = data.get('provider', 'anthropic').lower()
        model = data.get('model', '')
        messages = data.get('messages', [])
        max_tokens = data.get('max_tokens', 1000)
        system_prompt = data.get('system', '')

        # Validate required fields
        if not model or not messages:
            return Response(
                {'error': 'model and messages are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Call the appropriate provider API
        try:
            if provider == 'anthropic':
                response_data, tokens_in, tokens_out = self._call_anthropic(
                    model, messages, max_tokens, system_prompt
                )
            elif provider == 'openai':
                response_data, tokens_in, tokens_out = self._call_openai(
                    model, messages, max_tokens, system_prompt
                )
            else:
                return Response(
                    {'error': f'Unsupported provider: {provider}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            logger.exception(f'AI provider API error for instance {instance.id}')
            AuditService.log(
                action=AuditAction.AI_REQUEST_FAILED,
                resource_type='Instance',
                resource_id=str(instance.id),
                actor_email='system',
                customer=instance.customer,
                instance_id=instance.id,
                note=f'AI request failed: {str(e)}'
            )
            return Response(
                {'error': 'Provider API error', 'message': str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # Log token usage
        month_start = date.today().replace(day=1)
        AITokenUsage.objects.create(
            instance=instance,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            week_start=week_start_date,
            month=month_start,
        )

        # Log successful request
        AuditService.log(
            action=AuditAction.AI_REQUEST_SUCCESS,
            resource_type='Instance',
            resource_id=str(instance.id),
            actor_email='system',
            customer=instance.customer,
            instance_id=instance.id,
            note=f'AI request: {model}, {tokens_in} in, {tokens_out} out'
        )

        return Response(response_data, status=status.HTTP_200_OK)

    def _call_anthropic(self, model, messages, max_tokens, system_prompt):
        """
        Call the Anthropic API.

        Returns:
            tuple: (response_data, tokens_in, tokens_out)
        """
        api_key = settings.ANTHROPIC_API_KEY if hasattr(settings, 'ANTHROPIC_API_KEY') else None
        if not api_key:
            raise ValueError('ANTHROPIC_API_KEY not configured')

        headers = {
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }

        payload = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
        }

        if system_prompt:
            payload['system'] = system_prompt

        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            raise Exception(f'Anthropic API error: {response.status_code} - {response.text}')

        data = response.json()

        # Extract token usage from response
        usage = data.get('usage', {})
        tokens_in = usage.get('input_tokens', 0)
        tokens_out = usage.get('output_tokens', 0)

        return data, tokens_in, tokens_out

    def _call_openai(self, model, messages, max_tokens, system_prompt):
        """
        Call the OpenAI API.

        Returns:
            tuple: (response_data, tokens_in, tokens_out)
        """
        api_key = settings.OPENAI_API_KEY if hasattr(settings, 'OPENAI_API_KEY') else None
        if not api_key:
            raise ValueError('OPENAI_API_KEY not configured')

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        # Prepend system message if provided
        api_messages = messages.copy()
        if system_prompt:
            api_messages.insert(0, {'role': 'system', 'content': system_prompt})

        payload = {
            'model': model,
            'messages': api_messages,
            'max_tokens': max_tokens,
        }

        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            raise Exception(f'OpenAI API error: {response.status_code} - {response.text}')

        data = response.json()

        # Extract token usage from response
        usage = data.get('usage', {})
        tokens_in = usage.get('prompt_tokens', 0)
        tokens_out = usage.get('completion_tokens', 0)

        return data, tokens_in, tokens_out
