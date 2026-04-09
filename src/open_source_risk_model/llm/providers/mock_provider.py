"""Mock LLM provider for testing without API calls."""

from typing import Dict, List, Iterator

from .base import LLMProvider
from ..models import CompletionRequest, CompletionResponse


class MockProvider(LLMProvider):
    """Mock provider for testing without API calls.
    
    This provider returns deterministic, pre-configured responses based on
    prompt content or prompt name. It's designed for unit testing and does
    not make any external API calls.
    
    Response Mapping Strategy:
    1. If request.prompt_name is set, use it as the lookup key
    2. Otherwise, use the first 50 characters of the system message as the key
    3. If no match is found, return a default response
    
    Example:
        >>> mock_provider = MockProvider({
        ...     "intent_classification": '{"intent": "list_dependencies", "confidence": 0.95}'
        ... })
        >>> request = CompletionRequest(
        ...     messages=[Message(role=MessageRole.SYSTEM, content="...")],
        ...     model="mock-model",
        ...     prompt_name="intent_classification"
        ... )
        >>> response = mock_provider.complete(request)
        >>> print(response.content)
        {"intent": "list_dependencies", "confidence": 0.95}
    """
    
    def __init__(self, canned_responses: Dict[str, str]):
        """Initialize mock provider with canned responses.
        
        Args:
            canned_responses: Dictionary mapping prompt identifiers to response strings.
                            Keys can be prompt names or prompt content prefixes.
                            Values should be the complete response content.
        
        Example:
            >>> canned_responses = {
            ...     "intent_classification": '{"intent": "list_dependencies"}',
            ...     "You are a query classifier": '{"intent": "unknown"}'
            ... }
            >>> provider = MockProvider(canned_responses)
        """
        self.canned_responses = canned_responses
    
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return canned response based on prompt name or content.
        
        The response is selected using the following priority:
        1. If request.prompt_name is set, look it up in canned_responses
        2. Otherwise, use the first 50 chars of the system message as the key
        3. If no match found, return default response: '{"intent": "unknown"}'
        
        Args:
            request: Standardized completion request
        
        Returns:
            CompletionResponse with the canned content and mock metadata
        """
        # Determine lookup key
        if request.prompt_name:
            key = request.prompt_name
        elif request.messages:
            # Use first 50 chars of system message as fallback key
            key = request.messages[0].content[:50]
        else:
            key = ""
        
        # Look up canned response
        content = self.canned_responses.get(key, '{"intent": "unknown"}')
        
        return CompletionResponse(
            content=content,
            model="mock-model",
            finish_reason="stop",
            usage={
                "total_tokens": 100,
                "prompt_tokens": 50,
                "completion_tokens": 50
            }
        )
    
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """Stream canned response (simple implementation).
        
        This is a simple implementation that yields the entire canned response
        at once. In a real streaming implementation, this would yield chunks
        as they arrive from the API.
        
        Args:
            request: Standardized completion request
        
        Yields:
            str: The complete canned response content
        """
        yield self.complete(request).content
    
    def validate_config(self) -> bool:
        """Validate configuration (always returns True for mock provider).
        
        The mock provider has no external dependencies or configuration
        requirements, so it's always valid.
        
        Returns:
            bool: Always True
        """
        return True
    
    @property
    def name(self) -> str:
        """Provider name for logging and debugging.
        
        Returns:
            str: "mock"
        """
        return "mock"
    
    @property
    def supported_models(self) -> List[str]:
        """List of models supported by this provider.
        
        Returns:
            List[str]: ["mock-model"]
        """
        return ["mock-model"]
