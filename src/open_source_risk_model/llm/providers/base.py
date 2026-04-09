"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import List, Iterator

from ..models import CompletionRequest, CompletionResponse


class LLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    All concrete provider implementations (OpenAI, Anthropic, MCP, etc.) must
    inherit from this class and implement all abstract methods and properties.
    
    This interface defines the contract that all providers must follow, enabling
    the application to work with any LLM provider without code changes.
    """
    
    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion from the LLM provider.
        
        Args:
            request: Standardized completion request containing messages, model,
                    temperature, and other parameters.
        
        Returns:
            CompletionResponse: Standardized response containing the generated
                              content, token usage, and metadata.
        
        Raises:
            ProviderError: If the provider API call fails (network error, rate limit, etc.)
            ValidationError: If the request is invalid or malformed
            ConfigurationError: If the provider is not properly configured
        """
        pass
    
    @abstractmethod
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """Stream a completion from the LLM provider (future enhancement).
        
        This method enables real-time streaming of the completion as it's generated,
        rather than waiting for the entire response.
        
        Args:
            request: Standardized completion request containing messages, model,
                    temperature, and other parameters.
        
        Yields:
            str: Content chunks as they arrive from the provider.
        
        Raises:
            ProviderError: If the provider API call fails
            ValidationError: If the request is invalid
            NotImplementedError: If streaming is not yet implemented for this provider
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate that the provider is properly configured.
        
        This method checks that all required configuration (API keys, endpoints, etc.)
        is present and valid. It should be called during initialization to fail fast
        if the provider cannot be used.
        
        Returns:
            bool: True if the configuration is valid and the provider can make API calls.
        
        Raises:
            ConfigurationError: If the configuration is invalid or incomplete,
                              with details about what is missing or wrong.
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and debugging.
        
        Returns:
            str: A unique identifier for this provider (e.g., "openai", "anthropic", "mcp").
        """
        pass
    
    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """List of models supported by this provider.
        
        Returns:
            List[str]: List of model identifiers that can be used with this provider.
                      For example: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"] for OpenAI.
        """
        pass
