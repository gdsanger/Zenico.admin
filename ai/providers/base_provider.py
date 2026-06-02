"""
Base Provider Class

Abstract base class for AI providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from .schemas import ProviderResponse


class BaseProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, api_key: str, **kwargs):
        """
        Initialize provider.

        Args:
            api_key: Provider API key
            **kwargs: Additional provider-specific configuration
        """
        self.api_key = api_key
        self.config = kwargs

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Return provider type identifier."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ProviderResponse:
        """
        Perform a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model_id: Model identifier
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Returns:
            ProviderResponse with text, tokens, and raw response
        """
        pass
