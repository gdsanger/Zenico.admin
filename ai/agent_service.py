"""
Agent Service

Execute DB-based AI agents with caching and routing.
"""

import logging
from typing import Tuple
from ai.models import AIAgent, AIJobsHistory, AIJobStatus
from ai.router import AIRouter
from ai.providers.cache import AgentCacheService

logger = logging.getLogger(__name__)


class AgentService:
    """
    Service for executing AI agents.
    Agents are stored in DB (not YAML files).
    """

    def __init__(self):
        self.router = AIRouter()
        self.cache_service = AgentCacheService()

    def execute(
        self,
        agent_name: str,
        input_text: str,
        instance,
    ) -> Tuple[str, bool]:
        """
        Execute an agent.

        Args:
            agent_name: Name of the agent to execute
            input_text: Input text for the agent
            instance: Instance object (from authentication)

        Returns:
            Tuple of (response_text, from_cache)

        Raises:
            AIAgent.DoesNotExist: If agent not found
            Exception: If agent execution fails
        """
        # Load agent from DB
        agent = AIAgent.objects.select_related(
            'provider', 'model'
        ).get(name=agent_name, active=True)

        # Build cache config
        cache_config = {
            'enabled': agent.cache_enabled,
            'ttl_seconds': agent.cache_ttl_seconds,
            'key_strategy': 'content_hash',
            'agent_version': agent.cache_version,
        }

        # Check cache
        cached_response = self.cache_service.get_cached_response(
            agent_name=agent_name,
            input_text=input_text,
            cache_config=cache_config,
        )

        if cached_response is not None:
            # Log cached job
            AIJobsHistory.objects.create(
                agent=agent_name,
                instance=instance,
                provider=agent.provider,
                model=agent.model,
                status=AIJobStatus.CACHED,
                from_cache=True,
            )
            return cached_response, True

        # Build messages
        messages = []
        if agent.role:
            messages.append({'role': 'system', 'content': agent.role})

        # Combine task template with input
        user_message = f'{agent.task}\n\nInput:\n{input_text}'
        messages.append({'role': 'user', 'content': user_message})

        # Execute via router
        response = self.router.chat(
            messages=messages,
            instance=instance,
            agent=agent_name,
            provider_type=agent.provider.provider_type if agent.provider else None,
            model_id=agent.model.model_id if agent.model else None,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )

        # Cache response
        self.cache_service.cache_response(
            agent_name=agent_name,
            input_text=input_text,
            response_text=response.text,
            cache_config=cache_config,
        )

        return response.text, False
