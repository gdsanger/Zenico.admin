"""
Provider Response Schemas

Data classes for AI provider responses.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ProviderResponse:
    """Response from an AI provider."""

    text: str
    raw: Any
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class AIResponse:
    """Standardized AI response."""

    text: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    raw: Optional[Any] = None
