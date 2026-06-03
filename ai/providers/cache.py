"""
Agent Cache Service

Redis-based caching for agent responses.
"""

import hashlib
import logging
from typing import Optional
from django.core.cache import cache

logger = logging.getLogger(__name__)


class AgentCacheService:
    """Service for caching agent responses."""

    def get_cached_response(
        self,
        agent_name: str,
        input_text: str,
        cache_config: dict,
    ) -> Optional[str]:
        """
        Get cached response for agent and input.

        Args:
            agent_name: Name of the agent
            input_text: Input text
            cache_config: Cache configuration dict with:
                - enabled: bool
                - ttl_seconds: int
                - key_strategy: str ('content_hash')
                - agent_version: int

        Returns:
            Cached response text or None if not found/disabled
        """
        if not cache_config.get('enabled', True):
            return None

        cache_key = self._build_cache_key(agent_name, input_text, cache_config)

        try:
            cached = cache.get(cache_key)
            if cached:
                logger.debug(f'Cache hit for agent {agent_name}')
                return cached
        except Exception as e:
            logger.warning(f'Cache get error: {e}')

        return None

    def cache_response(
        self,
        agent_name: str,
        input_text: str,
        response_text: str,
        cache_config: dict,
    ):
        """
        Cache agent response.

        Args:
            agent_name: Name of the agent
            input_text: Input text
            response_text: Response text to cache
            cache_config: Cache configuration dict
        """
        if not cache_config.get('enabled', True):
            return

        cache_key = self._build_cache_key(agent_name, input_text, cache_config)
        ttl = cache_config.get('ttl_seconds', 300)

        try:
            cache.set(cache_key, response_text, timeout=ttl)
            logger.debug(f'Cached response for agent {agent_name} (TTL: {ttl}s)')
        except Exception as e:
            logger.warning(f'Cache set error: {e}')

    def _build_cache_key(
        self,
        agent_name: str,
        input_text: str,
        cache_config: dict,
    ) -> str:
        """
        Build cache key using content hash strategy.

        Args:
            agent_name: Name of the agent
            input_text: Input text
            cache_config: Cache configuration dict

        Returns:
            Cache key string
        """
        agent_version = cache_config.get('agent_version', 1)

        # Create hash of input text for consistent key generation
        content_hash = hashlib.sha256(input_text.encode()).hexdigest()[:16]

        return f'agent:{agent_name}:v{agent_version}:{content_hash}'
