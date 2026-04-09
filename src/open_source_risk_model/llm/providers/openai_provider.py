"""OpenAI provider implementation."""

import logging
from typing import List, Iterator, Optional

try:
    import openai
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "OpenAI package not installed. Install with: pip install openai>=1.0"
    )

from .base import LLMProvider
from ..models import CompletionRequest, CompletionResponse, Message, MessageRole
from ..exceptions import ProviderError, ConfigurationError, ValidationError

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation.
    
    This provider wraps the OpenAI Chat Completions API and translates between
    the standardized CompletionRequest/CompletionResponse format and OpenAI's
    native format.
    
    Attributes:
        api_key: OpenAI API key for authentication
        base_url: Optional custom base URL for OpenAI API
        organization: Optional OpenAI organization ID
        timeout: Request timeout in seconds
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        timeout: int = 30
    ):
        """Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key
            base_url: Optional custom base URL (for Azure OpenAI, etc.)
            organization: Optional OpenAI organization ID
            timeout: Request timeout in seconds (default: 30)
        
        Raises:
            ConfigurationError: If API key is missing or invalid
        """
        if not api_key:
            raise ConfigurationError("OpenAI API key is required")
        
        self.api_key = api_key
        self.base_url = base_url
        self.organization = organization
        self.timeout = timeout
        
        # Initialize OpenAI client
        client_kwargs = {
            "api_key": api_key,
            "timeout": timeout,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        if organization:
            client_kwargs["organization"] = organization
        
        self.client = OpenAI(**client_kwargs)
        
        logger.info(
            "OpenAI provider initialized",
            extra={"base_url": base_url, "has_organization": bool(organization)}
        )
    
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion using OpenAI Chat Completions API.
        
        Args:
            request: Standardized completion request
        
        Returns:
            CompletionResponse: Standardized completion response
        
        Raises:
            ProviderError: If OpenAI API call fails
            ValidationError: If request is invalid
        """
        # Validate request
        if not request.messages:
            raise ValidationError("Request must contain at least one message")
        
        if request.model not in self.supported_models:
            logger.warning(
                f"Model {request.model} not in supported models list, "
                f"but attempting anyway"
            )
        
        # Translate request to OpenAI format
        openai_request = self._translate_to_openai(request)
        
        try:
            # Call OpenAI API
            logger.debug(
                "Calling OpenAI API",
                extra={
                    "model": request.model,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens
                }
            )
            
            response = self.client.chat.completions.create(**openai_request)
            
            # Translate response from OpenAI format
            completion_response = self._translate_from_openai(response)
            
            logger.info(
                "OpenAI completion successful",
                extra={
                    "model": completion_response.model,
                    "tokens": completion_response.usage.get("total_tokens", 0),
                    "finish_reason": completion_response.finish_reason
                }
            )
            
            return completion_response
            
        except openai.AuthenticationError as e:
            logger.error("OpenAI authentication failed", extra={"error": str(e)})
            raise ConfigurationError(
                f"OpenAI authentication failed: {str(e)}"
            ) from e
        
        except openai.RateLimitError as e:
            # Extract retry_after from headers if available
            retry_after = None
            if hasattr(e, 'response') and e.response:
                retry_after = e.response.headers.get('retry-after')
                if retry_after:
                    try:
                        retry_after = int(retry_after)
                    except (ValueError, TypeError):
                        retry_after = None
            
            logger.warning(
                "OpenAI rate limit exceeded",
                extra={"retry_after": retry_after, "error": str(e)}
            )
            raise ProviderError(
                f"OpenAI rate limit exceeded: {str(e)}",
                provider="openai",
                is_transient=True,
                retry_after=retry_after
            ) from e
        
        except openai.APIConnectionError as e:
            logger.error("OpenAI connection error", extra={"error": str(e)})
            raise ProviderError(
                f"OpenAI connection error: {str(e)}",
                provider="openai",
                is_transient=True
            ) from e
        
        except openai.APITimeoutError as e:
            logger.error("OpenAI request timeout", extra={"error": str(e)})
            raise ProviderError(
                f"OpenAI request timeout: {str(e)}",
                provider="openai",
                is_transient=True
            ) from e
        
        except openai.APIStatusError as e:
            # Handle various HTTP status codes
            is_transient = e.status_code in [500, 502, 503, 504]
            
            logger.error(
                "OpenAI API error",
                extra={
                    "status_code": e.status_code,
                    "is_transient": is_transient,
                    "error": str(e)
                }
            )
            
            raise ProviderError(
                f"OpenAI API error (status {e.status_code}): {str(e)}",
                provider="openai",
                is_transient=is_transient
            ) from e
        
        except Exception as e:
            logger.error(
                "Unexpected error calling OpenAI",
                extra={"error": str(e), "error_type": type(e).__name__}
            )
            raise ProviderError(
                f"Unexpected OpenAI error: {str(e)}",
                provider="openai",
                is_transient=False
            ) from e
    
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """Stream a completion from OpenAI (future enhancement).
        
        Args:
            request: Standardized completion request
        
        Yields:
            str: Content chunks as they arrive
        
        Raises:
            NotImplementedError: Streaming not yet implemented
        """
        raise NotImplementedError("Streaming support not yet implemented for OpenAI provider")
    
    def validate_config(self) -> bool:
        """Validate OpenAI provider configuration.
        
        This method attempts a minimal API call to verify that the API key
        is valid and the service is reachable.
        
        Returns:
            bool: True if configuration is valid
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            # Make a minimal API call to verify credentials
            # Use the models endpoint which is lightweight
            self.client.models.list()
            logger.info("OpenAI configuration validated successfully")
            return True
            
        except openai.AuthenticationError as e:
            raise ConfigurationError(
                f"OpenAI API key is invalid: {str(e)}"
            ) from e
        
        except openai.APIConnectionError as e:
            raise ConfigurationError(
                f"Cannot connect to OpenAI API: {str(e)}"
            ) from e
        
        except Exception as e:
            raise ConfigurationError(
                f"OpenAI configuration validation failed: {str(e)}"
            ) from e
    
    @property
    def name(self) -> str:
        """Provider name for logging and debugging.
        
        Returns:
            str: "openai"
        """
        return "openai"
    
    @property
    def supported_models(self) -> List[str]:
        """List of OpenAI models supported by this provider.
        
        Returns:
            List[str]: List of supported model identifiers
        """
        return [
            "gpt-5-mini",  # Default model (most affordable, widely available)
            "gpt-5.2",
            "gpt-5.2-pro",
            "gpt-4o-mini",  # Legacy but still available
            "gpt-4o",
            "gpt-3.5-turbo",  # Deprecated but may still work for some accounts
            "gpt-3.5-turbo-16k",
            "gpt-3.5-turbo-1106",
        ]
    
    def _translate_to_openai(self, request: CompletionRequest) -> dict:
        """Translate CompletionRequest to OpenAI API format.
        
        Args:
            request: Standardized completion request
        
        Returns:
            dict: OpenAI API request parameters
        """
        # Convert messages to OpenAI format
        openai_messages = []
        for msg in request.messages:
            openai_msg = {
                "role": msg.role.value,  # Convert enum to string
                "content": msg.content
            }
            
            # Add optional fields if present
            if msg.name:
                openai_msg["name"] = msg.name
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
            
            openai_messages.append(openai_msg)
        
        # Build OpenAI request
        openai_request = {
            "model": request.model,
            "messages": openai_messages,
        }
        
        # GPT-5 models only support default temperature (1), don't send it
        if not request.model.startswith("gpt-5"):
            openai_request["temperature"] = request.temperature
        
        # GPT-5 models use max_completion_tokens, older models use max_tokens
        if request.model.startswith("gpt-5"):
            openai_request["max_completion_tokens"] = request.max_tokens
        else:
            openai_request["max_tokens"] = request.max_tokens
        
        # Add response_format if JSON mode requested
        if request.response_format == "json":
            openai_request["response_format"] = {"type": "json_object"}
        
        # Add tools if present
        if request.tools:
            openai_request["tools"] = request.tools
        
        # Add tool_choice if present
        if request.tool_choice:
            openai_request["tool_choice"] = request.tool_choice
        
        return openai_request
    
    def _translate_from_openai(self, response) -> CompletionResponse:
        """Translate OpenAI API response to CompletionResponse.
        
        Args:
            response: OpenAI API response object
        
        Returns:
            CompletionResponse: Standardized completion response
        """
        # Extract the first choice (OpenAI can return multiple, we use first)
        choice = response.choices[0]
        message = choice.message
        
        # Extract content (may be None for tool calls)
        content = message.content or ""
        
        # Extract tool calls if present
        tool_calls = None
        if hasattr(message, 'tool_calls') and message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in message.tool_calls
            ]
        
        # Extract usage statistics
        usage = {
            "total_tokens": response.usage.total_tokens,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
        
        return CompletionResponse(
            content=content,
            model=response.model,
            finish_reason=choice.finish_reason,
            usage=usage,
            tool_calls=tool_calls,
            raw_response=response  # Preserve raw response for debugging
        )
