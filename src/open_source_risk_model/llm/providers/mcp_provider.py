"""
Model Context Protocol (MCP) Provider.

FUTURE ENHANCEMENT - NOT IMPLEMENTED IN MVP
"""

from typing import List, Iterator, Optional
from .base import LLMProvider
from ..models import CompletionRequest, CompletionResponse


class MCPProvider(LLMProvider):
    """
    MCP server provider.
    
    STUB: This is a placeholder for future implementation.
    """
    
    def __init__(
        self,
        server_url: str,
        auth_token: Optional[str] = None,
        timeout: int = 30
    ):
        """Initialize MCP provider (not implemented)."""
        raise NotImplementedError("MCPProvider not yet implemented")
    
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate completion (not implemented)."""
        raise NotImplementedError("MCPProvider not yet implemented")
    
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """Stream completion (not implemented)."""
        raise NotImplementedError("MCPProvider not yet implemented")
    
    def validate_config(self) -> bool:
        """Validate config (not implemented)."""
        raise NotImplementedError("MCPProvider not yet implemented")
    
    @property
    def name(self) -> str:
        return "mcp"
    
    @property
    def supported_models(self) -> List[str]:
        return []
