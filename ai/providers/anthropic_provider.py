"""
Anthropic Provider

Provider implementation for Anthropic Claude API.
"""

import anthropic
from typing import List, Dict, Optional
from .base_provider import BaseProvider
from .schemas import ProviderResponse


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self.client = anthropic.Anthropic(api_key=self.api_key)

    @property
    def provider_type(self) -> str:
        return 'Anthropic'

    def chat(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ProviderResponse:
        """
        Perform Anthropic chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model_id: Anthropic model ID (e.g., 'claude-sonnet-4-5')
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters

        Returns:
            ProviderResponse with completion text and token usage
        """
        # System Message extrahieren
        system = ''
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system = msg['content']
            else:
                chat_messages.append(msg)

        params = {
            'model': model_id,
            'messages': chat_messages,
            'max_tokens': max_tokens or 1000,
        }

        if system:
            params['system'] = system

        if temperature is not None:
            params['temperature'] = temperature

        # Add any additional kwargs
        params.update(kwargs)

        # Call Anthropic API
        response = self.client.messages.create(**params)

        # Extract response data
        text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        return ProviderResponse(
            text=text,
            raw=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
