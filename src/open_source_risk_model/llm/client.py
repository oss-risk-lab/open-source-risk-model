"""LLM Client facade with retry logic."""

import logging
import time
from typing import Dict, Any, Optional

from .providers.base import LLMProvider
from .prompt_manager import PromptManager
from .models import CompletionRequest, CompletionResponse, Message, MessageRole
from .exceptions import ProviderError

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Facade for LLM interactions.
    
    Provides a unified interface for all LLM operations, abstracting away
    provider-specific details. Includes retry logic with exponential backoff
    for handling transient errors.
    
    Attributes:
        provider: LLM provider implementation (OpenAI, Anthropic, etc.)
        prompt_manager: Centralized prompt manager for template rendering
        retry_config: Configuration for retry behavior
    """
    
    def __init__(
        self,
        provider: LLMProvider,
        prompt_manager: PromptManager,
        retry_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize LLM client.
        
        Args:
            provider: LLM provider implementation
            prompt_manager: Centralized prompt manager
            retry_config: Optional retry configuration with keys:
                - max_retries: Maximum number of retry attempts (default: 3)
                - backoff_factor: Exponential backoff multiplier (default: 2.0)
                - timeout_seconds: Request timeout in seconds (default: 30)
        """
        self.provider = provider
        self.prompt_manager = prompt_manager
        self.retry_config = retry_config or {
            "max_retries": 3,
            "backoff_factor": 2.0,
            "timeout_seconds": 30
        }
        
        logger.info(
            "LLMClient initialized",
            extra={
                "provider": self.provider.name,
                "max_retries": self.retry_config["max_retries"],
                "backoff_factor": self.retry_config["backoff_factor"]
            }
        )
    
    def complete(
        self,
        prompt_name: str,
        prompt_params: Dict[str, Any],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 500,
        response_format: Optional[str] = None
    ) -> CompletionResponse:
        """
        Generate a completion using a named prompt.
        
        This method:
        1. Renders the prompt template with provided parameters
        2. Builds a standardized completion request
        3. Executes the request with retry logic
        4. Returns the standardized response
        
        Args:
            prompt_name: Name of prompt template to use
            prompt_params: Parameters for prompt rendering
            model: Optional model override (uses provider default if None)
            temperature: Sampling temperature (0.0 = deterministic, higher = more random)
            max_tokens: Maximum tokens to generate
            response_format: Optional response format ("json" for JSON mode, None for text)
            
        Returns:
            CompletionResponse: Standardized completion response with content,
                              usage statistics, and metadata
        
        Raises:
            PromptNotFoundError: If prompt_name doesn't exist
            TemplateRenderError: If prompt rendering fails
            ProviderError: If provider API fails after all retries
            ValidationError: If request is invalid
        """
        # Render prompt template
        logger.debug(
            "Rendering prompt",
            extra={"prompt_name": prompt_name, "params": list(prompt_params.keys())}
        )
        
        rendered_prompt = self.prompt_manager.render(prompt_name, prompt_params)
        
        # Build standardized request
        request = CompletionRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=rendered_prompt["system"]),
                Message(role=MessageRole.USER, content=rendered_prompt["user"])
            ],
            model=model or self.provider.supported_models[0],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            prompt_name=prompt_name  # For debugging and MockProvider routing
        )
        
        logger.info(
            "Executing completion request",
            extra={
                "prompt_name": prompt_name,
                "model": request.model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format
            }
        )
        
        # Execute with retry logic
        return self._execute_with_retry(request)
    
    def _execute_with_retry(self, request: CompletionRequest) -> CompletionResponse:
        """
        Execute request with exponential backoff retry logic.
        
        This method implements a robust retry strategy:
        - Only retries on transient errors (is_transient=True)
        - Uses exponential backoff between retries
        - Respects retry_after header from rate limits
        - Logs all retry attempts for debugging
        - Fails fast on permanent errors (auth failures, validation errors)
        
        Args:
            request: Standardized completion request
            
        Returns:
            CompletionResponse: Standardized completion response
            
        Raises:
            ProviderError: If all retries are exhausted or error is not transient
            ValidationError: If request is invalid (no retry)
            ConfigurationError: If provider config is invalid (no retry)
        """
        max_retries = self.retry_config["max_retries"]
        backoff_factor = self.retry_config["backoff_factor"]
        
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Attempt completion
                response = self.provider.complete(request)
                
                # Log success
                if retry_count > 0:
                    logger.info(
                        "Completion succeeded after retries",
                        extra={
                            "retry_count": retry_count,
                            "model": response.model,
                            "tokens": response.usage.get("total_tokens", 0)
                        }
                    )
                else:
                    logger.debug(
                        "Completion succeeded on first attempt",
                        extra={
                            "model": response.model,
                            "tokens": response.usage.get("total_tokens", 0)
                        }
                    )
                
                return response
                
            except ProviderError as error:
                # Check if error is transient and we have retries left
                if not error.is_transient:
                    logger.error(
                        "Permanent provider error, not retrying",
                        extra={
                            "provider": error.provider,
                            "error": str(error),
                            "retry_count": retry_count
                        }
                    )
                    raise
                
                if retry_count >= max_retries:
                    logger.error(
                        "Max retries exceeded",
                        extra={
                            "provider": error.provider,
                            "max_retries": max_retries,
                            "error": str(error)
                        }
                    )
                    raise
                
                # Calculate wait time
                # If provider specifies retry_after, use it; otherwise use exponential backoff
                if error.retry_after:
                    wait_time = error.retry_after
                    logger.info(
                        "Using provider-specified retry_after",
                        extra={"retry_after": wait_time}
                    )
                else:
                    wait_time = backoff_factor ** retry_count
                
                retry_count += 1
                
                logger.warning(
                    "Transient error, retrying",
                    extra={
                        "provider": error.provider,
                        "retry_count": retry_count,
                        "max_retries": max_retries,
                        "wait_time": wait_time,
                        "error": str(error)
                    }
                )
                
                # Wait before retrying
                time.sleep(wait_time)
        
        # Should never reach here, but just in case
        raise RuntimeError("Unexpected completion failure: exceeded retry loop")
