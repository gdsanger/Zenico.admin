"""
OpenAI Provider

Provider implementation for OpenAI API.
"""

import openai
from typing import List, Dict, Optional
from .base_provider import BaseProvider
from .schemas import ProviderResponse


class OpenAIProvider(BaseProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self.client = openai.OpenAI(api_key=self.api_key)

    @property
    def provider_type(self) -> str:
        return 'OpenAI'

    def chat(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ProviderResponse:
        """
        Perform OpenAI chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model_id: OpenAI model ID (e.g., 'gpt-4o', 'gpt-4-turbo')
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with completion text and token usage
        """
        request_params = {
            'model': model_id,
            'messages': messages,
        }

        if temperature is not None:
            request_params['temperature'] = temperature

        # Fix for new OpenAI models
        # Newer models (o1, o3, gpt-4o, gpt-4-turbo) use max_completion_tokens
        # instead of max_tokens
        if max_tokens is not None:
            NEW_MODELS = ('o1', 'o3', 'gpt-4o', 'gpt-4-turbo')
            if any(model_id.startswith(m) for m in NEW_MODELS):
                request_params['max_completion_tokens'] = max_tokens
            else:
                request_params['max_tokens'] = max_tokens

        # Add any additional kwargs
        request_params.update(kwargs)

        # Call OpenAI API
        response = self.client.chat.completions.create(**request_params)

        # Extract response data
        text = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens if response.usage else None
        output_tokens = response.usage.completion_tokens if response.usage else None

        return ProviderResponse(
            text=text,
            raw=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
