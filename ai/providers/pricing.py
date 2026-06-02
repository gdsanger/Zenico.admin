"""
Pricing Calculator

Calculate costs for AI API usage.
"""

from decimal import Decimal
from typing import Optional
from ai.models import AIModel


def calculate_cost(
    model: AIModel,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
) -> Decimal:
    """
    Calculate cost in USD for token usage.

    Args:
        model: AIModel instance with pricing information
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used

    Returns:
        Cost in USD as Decimal
    """
    return model.calculate_cost(input_tokens or 0, output_tokens or 0)
