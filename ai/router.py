"""
AI Router

Central router for AI requests with provider management and job tracking.
"""

import time
import logging
from typing import Optional, List, Dict
from django.db import transaction
from ai.models import (
    AIProvider,
    AIModel,
    AIJobsHistory,
    AITokenBudget,
    AIJobStatus,
)
from ai.providers.schemas import AIResponse
from ai.providers.openai_provider import OpenAIProvider
from ai.providers.anthropic_provider import AnthropicProvider
from ai.providers.pricing import calculate_cost

logger = logging.getLogger(__name__)


class AIRouter:
    """
    Central router for AI API calls.
    Handles provider selection, job tracking, and budget management.
    """

    PROVIDER_CLASSES = {
        'OpenAI': OpenAIProvider,
        'Anthropic': AnthropicProvider,
    }

    def chat(
        self,
        messages: List[Dict[str, str]],
        instance,
        agent: str = 'zenico.ai',
        model_id: Optional[str] = None,
        provider_type: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AIResponse:
        """
        Perform a chat completion through the appropriate provider.

        Args:
            messages: List of message dicts with 'role' and 'content'
            instance: Instance object (from authentication)
            agent: Agent name for tracking
            model_id: Model ID to use (optional)
            provider_type: Provider type (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters

        Returns:
            AIResponse with text, tokens, and metadata

        Raises:
            Exception: If provider call fails
        """
        # Select provider and model
        provider, model = self._select_model(provider_type, model_id)

        # Create pending job
        job = self._create_job(provider, model, instance, agent)

        start_time = time.time()

        try:
            # Get provider instance and make API call
            provider_instance = self._get_provider_instance(provider)

            response = provider_instance.chat(
                messages=messages,
                model_id=model.model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Complete job with success
            self._complete_job(
                job,
                response.input_tokens,
                response.output_tokens,
                duration_ms
            )

            # Update token budget
            budget, _ = AITokenBudget.objects.get_or_create(
                instance=instance
            )
            budget.add_tokens(
                response.input_tokens or 0,
                response.output_tokens or 0
            )

            return AIResponse(
                text=response.text,
                raw=response.raw,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model=model.model_id,
                provider=provider.provider_type,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._complete_job(
                job,
                None,
                None,
                duration_ms,
                error_message=str(e)
            )
            raise

    def _select_model(
        self,
        provider_type: Optional[str],
        model_id: Optional[str],
    ) -> tuple[AIProvider, AIModel]:
        """
        Select provider and model.

        Args:
            provider_type: Provider type (optional)
            model_id: Model ID (optional)

        Returns:
            Tuple of (AIProvider, AIModel)

        Raises:
            ValueError: If provider or model not found
        """
        # If model_id is specified, find it
        if model_id:
            try:
                model = AIModel.objects.select_related('provider').get(
                    model_id=model_id,
                    active=True
                )
                return model.provider, model
            except AIModel.DoesNotExist:
                raise ValueError(f'Model {model_id} not found or not active')

        # If provider_type is specified, get default model for that provider
        if provider_type:
            try:
                provider = AIProvider.objects.get(
                    provider_type=provider_type,
                    active=True
                )
                model = AIModel.objects.filter(
                    provider=provider,
                    active=True,
                    is_default=True
                ).first()

                if not model:
                    # Fallback to any active model for this provider
                    model = AIModel.objects.filter(
                        provider=provider,
                        active=True
                    ).first()

                if not model:
                    raise ValueError(f'No active model found for provider {provider_type}')

                return provider, model

            except AIProvider.DoesNotExist:
                raise ValueError(f'Provider {provider_type} not found or not active')

        # No provider or model specified, use default
        model = AIModel.objects.select_related('provider').filter(
            active=True,
            is_default=True
        ).first()

        if not model:
            raise ValueError('No default model configured')

        return model.provider, model

    def _get_provider_instance(self, provider: AIProvider):
        """
        Get provider instance.

        Args:
            provider: AIProvider model instance

        Returns:
            Provider instance (OpenAIProvider or AnthropicProvider)

        Raises:
            ValueError: If provider type is unsupported
        """
        provider_class = self.PROVIDER_CLASSES.get(provider.provider_type)
        if not provider_class:
            raise ValueError(f'Unsupported provider type: {provider.provider_type}')

        api_key = provider.get_api_key()
        if not api_key:
            raise ValueError(f'API key not configured for provider {provider.name}')

        return provider_class(
            api_key=api_key,
            organization_id=provider.organization_id or None
        )

    def _create_job(
        self,
        provider: AIProvider,
        model: AIModel,
        instance,
        agent: str,
    ) -> AIJobsHistory:
        """Create a pending job entry."""
        return AIJobsHistory.objects.create(
            agent=agent,
            instance=instance,
            provider=provider,
            model=model,
            status=AIJobStatus.PENDING,
        )

    def _complete_job(
        self,
        job: AIJobsHistory,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        duration_ms: int,
        error_message: str = '',
    ):
        """Complete a job with success or error status."""
        if error_message:
            job.status = AIJobStatus.ERROR
            job.error_message = error_message
        else:
            job.status = AIJobStatus.COMPLETED

        job.input_tokens = input_tokens
        job.output_tokens = output_tokens
        job.duration_ms = duration_ms

        # Calculate costs
        if input_tokens or output_tokens:
            job.costs = calculate_cost(job.model, input_tokens, output_tokens)

        job.save()
