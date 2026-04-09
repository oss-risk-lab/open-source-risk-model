"""Custom exceptions for LLM provider abstraction layer."""

from typing import Optional


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class ConfigurationError(LLMError):
    """Configuration is invalid or incomplete."""
    pass


class ProviderError(LLMError):
    """Provider API call failed."""
    
    def __init__(
        self,
        message: str,
        provider: str,
        is_transient: bool = False,
        retry_after: Optional[int] = None
    ):
        """
        Initialize ProviderError.
        
        Args:
            message: Error message describing what went wrong
            provider: Name of the provider that failed (e.g., "openai", "anthropic")
            is_transient: Whether the error is transient and can be retried
            retry_after: Optional number of seconds to wait before retrying
        """
        super().__init__(message)
        self.provider = provider
        self.is_transient = is_transient
        self.retry_after = retry_after


class ValidationError(LLMError):
    """Request or response validation failed."""
    pass


class PromptNotFoundError(LLMError):
    """Requested prompt template not found."""
    pass


class TemplateRenderError(LLMError):
    """Prompt template rendering failed."""
    pass
