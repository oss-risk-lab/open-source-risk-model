"""
Anthropic Claude Provider.

FUTURE ENHANCEMENT - NOT IMPLEMENTED IN MVP
"""

from typing import List, Iterator
from .base import LLMProvider
from ..models import CompletionRequest, CompletionResponse


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider.
    
    STUB: This is a placeholder for future implementation.
    """
    
    def __init__(self, api_key: str, timeout: int = 30):
        """Initialize Anthropic provider (not implemented)."""
        raise NotImplementedError("AnthropicProvider not yet implemented")
    
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate completion (not implemented)."""
        raise NotImplementedError("AnthropicProvider not yet implemented")
    
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """Stream completion (not implemented)."""
        raise NotImplementedError("AnthropicProvider not yet implemented")
    
    def validate_config(self) -> bool:
        """Validate config (not implemented)."""
        raise NotImplementedError("AnthropicProvider not yet implemented")
    
    @property
    def name(self) -> str:
        return "anthropic"
    
    @property
    def supported_models(self) -> List[str]:
        return []
