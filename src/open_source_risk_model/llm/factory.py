"""Factory functions for creating LLM providers from configuration."""

import os
import logging
from typing import Dict, Any

from .providers import LLMProvider, OpenAIProvider, MockProvider
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def create_provider(config: Dict[str, Any]) -> LLMProvider:
    """Create provider from configuration dict.
    
    This factory function creates and configures an LLM provider based on
    the provided configuration dictionary. It supports multiple provider types
    and validates that all required configuration is present.
    
    Args:
        config: Provider configuration dictionary with the following keys:
            - provider_type (str): Type of provider ("openai", etc.)
            - api_key (str): API key for the provider (required for most providers)
            - base_url (str, optional): Custom base URL for API endpoint
            - organization (str, optional): Organization ID (provider-specific)
            - timeout (int, optional): Request timeout in seconds (default: 30)
    
    Returns:
        LLMProvider: Configured provider instance ready to use
    
    Raises:
        ConfigurationError: If provider_type is unknown or required config is missing
    
    Example:
        >>> config = {
        ...     "provider_type": "openai",
        ...     "api_key": "sk-...",
        ...     "timeout": 60
        ... }
        >>> provider = create_provider(config)
        >>> provider.name
        'openai'
    """
    provider_type = config.get("provider_type")
    
    if not provider_type:
        raise ConfigurationError(
            "Configuration must include 'provider_type' field"
        )
    
    logger.info(f"Creating provider of type: {provider_type}")
    
    if provider_type == "openai":
        # Validate required fields for OpenAI
        api_key = config.get("api_key")
        if not api_key:
            raise ConfigurationError(
                "OpenAI provider requires 'api_key' in configuration"
            )
        
        # Create OpenAI provider with all config options
        provider = OpenAIProvider(
            api_key=api_key,
            base_url=config.get("base_url"),
            organization=config.get("organization"),
            timeout=config.get("timeout", 30)
        )
        
        logger.info(
            "OpenAI provider created successfully",
            extra={
                "has_base_url": bool(config.get("base_url")),
                "has_organization": bool(config.get("organization")),
                "timeout": config.get("timeout", 30)
            }
        )
        
        return provider
    
    elif provider_type == "mock":
        # Create MockProvider with default intent classification responses
        # These responses match common query patterns
        canned_responses = {
            "intent_classification": '{"intent": "dataset_stats", "parameters": {}, "confidence": 0.85, "reasoning": "Query asks for dataset statistics"}'
        }
        
        provider = MockProvider(canned_responses)
        
        logger.info("MockProvider created successfully")
        
        return provider
    
    else:
        # Unknown provider type
        raise ConfigurationError(
            f"Unknown provider type: '{provider_type}'. "
            f"Supported types: openai, mock"
        )


def create_provider_from_env() -> LLMProvider:
    """Create provider from environment variables.
    
    This convenience function reads provider configuration from environment
    variables, making it easy to configure the LLM provider without hardcoding
    credentials in code.
    
    Environment Variables:
        LLM_PROVIDER: Provider type (default: "openai")
            Supported values: "openai"
        
        For OpenAI provider:
            OPENAI_API_KEY: OpenAI API key (required)
            OPENAI_BASE_URL: Optional custom base URL (e.g., for Azure OpenAI)
            OPENAI_ORGANIZATION: Optional organization ID
    
    Returns:
        LLMProvider: Configured provider instance ready to use
    
    Raises:
        ConfigurationError: If required environment variables are missing or
                          if provider type is unknown
    
    Example:
        >>> import os
        >>> os.environ["LLM_PROVIDER"] = "openai"
        >>> os.environ["OPENAI_API_KEY"] = "sk-..."
        >>> provider = create_provider_from_env()
        >>> provider.name
        'openai'
    """
    provider_type = os.environ.get("LLM_PROVIDER", "openai")
    
    logger.info(f"Creating provider from environment: {provider_type}")
    
    if provider_type == "openai":
        # Get OpenAI configuration from environment
        api_key = os.environ.get("OPENAI_API_KEY")
        
        if not api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY environment variable is required for OpenAI provider. "
                "Please set it to your OpenAI API key."
            )
        
        base_url = os.environ.get("OPENAI_BASE_URL")
        organization = os.environ.get("OPENAI_ORGANIZATION")
        
        # Create OpenAI provider
        provider = OpenAIProvider(
            api_key=api_key,
            base_url=base_url,
            organization=organization
        )
        
        logger.info(
            "OpenAI provider created from environment",
            extra={
                "has_base_url": bool(base_url),
                "has_organization": bool(organization)
            }
        )
        
        return provider
    
    elif provider_type == "mock":
        # Create MockProvider with default intent classification responses
        # These responses match common query patterns
        canned_responses = {
            "intent_classification": '{"intent": "dataset_stats", "parameters": {}, "confidence": 0.85, "reasoning": "Query asks for dataset statistics"}'
        }
        
        provider = MockProvider(canned_responses)
        
        logger.info("MockProvider created from environment")
        
        return provider
    
    else:
        # Unknown provider type
        raise ConfigurationError(
            f"Unknown provider type in LLM_PROVIDER: '{provider_type}'. "
            f"Supported types: openai, mock"
        )
