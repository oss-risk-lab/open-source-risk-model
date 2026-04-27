# LLM Provider Abstraction - Architecture Review

This document contains the three critical files that define the abstraction layer architecture:

1. **LLMProvider Interface** - The contract all providers must implement
2. **LLMClient Facade** - The unified client that applications use
3. **IntentClassifier** - Example application code using the abstraction

---

## 1. LLMProvider Interface

**File**: `src/open_source_risk_model/llm/providers/base.py`

```python
"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import List, Iterator
from ..models import CompletionRequest, CompletionResponse


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All provider implementations (OpenAI, Anthropic, MCP, etc.) must implement
    this interface. This ensures the application code is decoupled from any
    specific provider.
    """
    
    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """
        Generate a completion for the given request.
        
        Args:
            request: Standardized completion request with messages, model, etc.
        
        Returns:
            CompletionResponse: Standardized response with content and metadata
        
        Raises:
            ProviderError: If the provider API call fails
            ValidationError: If the request is invalid
        """
        pass
    
    @abstractmethod
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """
        Stream a completion (future enhancement).
        
        Args:
            request: Standardized completion request
        
        Yields:
            str: Chunks of the completion as they arrive
        
        Raises:
            ProviderError: If the provider API call fails
            NotImplementedError: If streaming not yet implemented
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate that the provider is properly configured.
        
        This should check:
        - API keys are present
        - Credentials are valid
        - Provider is reachable (optional)
        
        Returns:
            bool: True if configuration is valid
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Provider name for logging and debugging.
        
        Returns:
            str: Provider name (e.g., "openai", "anthropic", "mock")
        """
        pass
    
    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """
        List of models supported by this provider.
        
        Returns:
            List[str]: Model identifiers (e.g., ["gpt-4", "gpt-3.5-turbo"])
        """
        pass
```

**Key Design Decisions**:
- ✅ Uses standard request/response models (no provider-specific types)
- ✅ Abstract properties for metadata (name, supported_models)
- ✅ Validation method for configuration checking
- ✅ Stream method for future enhancement (not required for MVP)
- ✅ Clear error handling expectations in docstrings

---

## 2. LLMClient Facade

**File**: `src/open_source_risk_model/llm/client.py`

```python
"""Unified LLM client with retry logic and prompt management."""

import time
import logging
from typing import Dict, Any, Optional

from .providers.base import LLMProvider
from .prompt_manager import PromptManager
from .models import CompletionRequest, CompletionResponse, Message, MessageRole
from .exceptions import ProviderError

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified client facade for LLM interactions.
    
    This class provides:
    - Integration with PromptManager for centralized prompts
    - Retry logic with exponential backoff for transient errors
    - Consistent interface regardless of provider
    - Logging and observability
    
    Application code should use this class, not providers directly.
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
            provider: Configured LLM provider (OpenAI, Anthropic, Mock, etc.)
            prompt_manager: PromptManager for loading and rendering templates
            retry_config: Optional retry configuration with keys:
                - max_retries (int): Maximum retry attempts (default: 3)
                - backoff_factor (float): Exponential backoff multiplier (default: 2.0)
                - timeout (int): Request timeout in seconds (default: 30)
        """
        self.provider = provider
        self.prompt_manager = prompt_manager
        
        # Retry configuration
        self.retry_config = retry_config or {}
        self.max_retries = self.retry_config.get("max_retries", 3)
        self.backoff_factor = self.retry_config.get("backoff_factor", 2.0)
        self.timeout = self.retry_config.get("timeout", 30)
        
        logger.info(
            f"LLMClient initialized",
            extra={
                "provider": self.provider.name,
                "max_retries": self.max_retries,
                "timeout": self.timeout
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
        Generate a completion using a named prompt template.
        
        This is the main method application code should use. It:
        1. Renders the prompt template with parameters
        2. Creates a standardized request
        3. Executes with retry logic
        4. Returns standardized response
        
        Args:
            prompt_name: Name of prompt template (e.g., "intent_classification")
            prompt_params: Parameters to render into the template
            model: Optional model override (uses provider default if None)
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens in response
            response_format: Optional format ("json" for JSON mode)
        
        Returns:
            CompletionResponse: Standardized response with content and metadata
        
        Raises:
            PromptNotFoundError: If prompt template doesn't exist
            TemplateRenderError: If template rendering fails
            ProviderError: If provider call fails after retries
            ValidationError: If request is invalid
        """
        # Render prompt template
        rendered = self.prompt_manager.render(prompt_name, prompt_params)
        
        # Build messages
        messages = [
            Message(role=MessageRole.SYSTEM, content=rendered["system"]),
            Message(role=MessageRole.USER, content=rendered["user"])
        ]
        
        # Create request
        request = CompletionRequest(
            messages=messages,
            model=model or self._get_default_model(),
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            prompt_name=prompt_name  # For debugging and MockProvider routing
        )
        
        # Execute with retry logic
        return self._execute_with_retry(request)
    
    def _execute_with_retry(self, request: CompletionRequest) -> CompletionResponse:
        """
        Execute request with exponential backoff retry logic.
        
        Only retries on transient errors (rate limits, timeouts, service unavailable).
        Permanent errors (auth failures, invalid requests) fail immediately.
        
        Args:
            request: Completion request to execute
        
        Returns:
            CompletionResponse: Response from provider
        
        Raises:
            ProviderError: If all retries exhausted or permanent error
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"Executing LLM request (attempt {attempt + 1}/{self.max_retries + 1})",
                    extra={
                        "provider": self.provider.name,
                        "model": request.model,
                        "prompt_name": request.prompt_name
                    }
                )
                
                response = self.provider.complete(request)
                
                logger.info(
                    f"LLM request succeeded",
                    extra={
                        "provider": self.provider.name,
                        "model": response.model,
                        "tokens": response.usage.get("total_tokens", 0),
                        "attempt": attempt + 1
                    }
                )
                
                return response
            
            except ProviderError as e:
                last_error = e
                
                # Don't retry on permanent errors
                if not e.is_transient:
                    logger.error(
                        f"Permanent provider error: {e}",
                        extra={"provider": self.provider.name}
                    )
                    raise
                
                # Don't retry if we've exhausted attempts
                if attempt >= self.max_retries:
                    logger.error(
                        f"Max retries ({self.max_retries}) exhausted",
                        extra={"provider": self.provider.name}
                    )
                    raise
                
                # Calculate backoff delay
                delay = self.backoff_factor ** attempt
                if e.retry_after:
                    delay = max(delay, e.retry_after)
                
                logger.warning(
                    f"Transient provider error, retrying in {delay}s: {e}",
                    extra={
                        "provider": self.provider.name,
                        "attempt": attempt + 1,
                        "delay": delay
                    }
                )
                
                time.sleep(delay)
        
        # Should never reach here, but just in case
        raise last_error or ProviderError(
            "Request failed after retries",
            provider=self.provider.name
        )
    
    def _get_default_model(self) -> str:
        """
        Get default model for the provider.
        
        Returns:
            str: Default model identifier
        """
        models = self.provider.supported_models
        if not models:
            return "default"
        return models[0]
```

**Key Design Decisions**:
- ✅ Accepts LLMProvider (dependency injection, not concrete type)
- ✅ Integrates with PromptManager (centralized prompt management)
- ✅ Retry logic only for transient errors (respects is_transient flag)
- ✅ Exponential backoff with configurable parameters
- ✅ Comprehensive logging for observability
- ✅ No provider-specific logic (truly provider-agnostic)

---

## 3. IntentClassifier (Application Code)

**File**: `src/open_source_risk_model/query/intent_classifier.py`

```python
"""
Intent Classifier using LLM

Classifies natural language queries into predefined intents.
Extracts parameters from user queries.

CRITICAL: LLM NEVER GENERATES SQL
- LLM only classifies intent and extracts parameters
- All SQL is hardcoded in IntentExecutor
- Strict JSON schema enforced
- Confidence gating (reject < 0.7)
"""

import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from open_source_risk_model.llm import LLMClient

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Available intent types (strict allowlist)."""
    LIST_DEPENDENCIES = "list_dependencies"
    FIND_DEPENDENTS = "find_dependents"
    GET_DEPENDENCY_TREE = "get_dependency_tree"
    CHECK_RESOLUTION = "check_resolution"
    LIST_UNRESOLVED = "list_unresolved"
    LIST_MANIFESTS = "list_manifests"
    COUNT_BY_MANIFEST_TYPE = "count_by_manifest_type"
    REPO_STATS = "repo_stats"
    DATASET_STATS = "dataset_stats"
    SEARCH_REPOS = "search_repos"
    SEARCH_PACKAGES = "search_packages"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of intent classification."""
    intent: str
    parameters: Dict[str, Any]
    confidence: float
    reasoning: Optional[str] = None


class IntentClassifier:
    """
    Classifies natural language queries into intents.
    
    Uses LLM to:
    1. Classify query into one of 11 predefined intents
    2. Extract parameters from natural language
    3. Return confidence score
    
    Does NOT:
    - Generate SQL (all SQL is hardcoded)
    - Execute queries (that's IntentExecutor's job)
    - Access database (read-only classification)
    """
    
    # Confidence threshold for accepting classification
    CONFIDENCE_THRESHOLD = 0.7
    
    # Intent definitions for prompt formatting
    INTENT_DEFINITIONS = [
        {
            "name": "list_dependencies",
            "description": "List direct dependencies of a repository",
            "parameters": "repo_full_name (required), dependency_group (optional: prod/dev/optional)",
            "examples": [
                "What are the dependencies of django/django?",
                "List prod dependencies for flask"
            ]
        },
        # ... [other intent definitions omitted for brevity]
    ]
    
    def __init__(self, llm_client: LLMClient):
        """
        Initialize intent classifier.
        
        Args:
            llm_client: LLMClient instance configured with provider and prompt manager
        """
        self.llm_client = llm_client
        logger.info("IntentClassifier initialized with LLMClient")
    
    def classify(self, query: str) -> ClassificationResult:
        """
        Classify a natural language query.
        
        Args:
            query: Natural language query from user
        
        Returns:
            ClassificationResult with intent, parameters, and confidence
        
        Raises:
            ValueError: If classification fails or confidence too low
        """
        # Call LLM using abstraction layer
        try:
            response = self.llm_client.complete(
                prompt_name="intent_classification",
                prompt_params={
                    "query": query,
                    "available_intents": self._format_intents()
                },
                response_format="json",
                temperature=0.0,
                max_tokens=500
            )
            
            result = self._parse_response(response.content)
            
            # Validate confidence
            if result.confidence < self.CONFIDENCE_THRESHOLD:
                logger.warning(
                    f"Low confidence classification: {result.confidence:.2f} < {self.CONFIDENCE_THRESHOLD}",
                    extra={"query": query, "intent": result.intent}
                )
                return ClassificationResult(
                    intent="unknown",
                    parameters={},
                    confidence=result.confidence,
                    reasoning=f"Confidence {result.confidence:.2f} below threshold {self.CONFIDENCE_THRESHOLD}"
                )
            
            # Validate intent is in allowlist
            if result.intent not in [e.value for e in IntentType]:
                logger.warning(f"Invalid intent from LLM: {result.intent}")
                return ClassificationResult(
                    intent="unknown",
                    parameters={},
                    confidence=0.0,
                    reasoning=f"Intent '{result.intent}' not in allowlist"
                )
            
            logger.info(
                f"Classified query",
                extra={
                    "query": query,
                    "intent": result.intent,
                    "confidence": result.confidence
                }
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Classification failed: {e}", exc_info=True)
            raise ValueError(f"Failed to classify query: {e}")
    
    def _format_intents(self) -> str:
        """
        Format intent definitions for the prompt.
        
        Returns:
            Formatted string with all intent definitions
        """
        formatted = []
        for i, intent in enumerate(self.INTENT_DEFINITIONS, 1):
            formatted.append(f"{i}. {intent['name']}")
            formatted.append(f"   Description: {intent['description']}")
            formatted.append(f"   Parameters: {intent['parameters']}")
            formatted.append(f"   Examples: {'; '.join(intent['examples'])}")
            formatted.append("")
        
        return "\n".join(formatted)
    
    def _parse_response(self, response: str) -> ClassificationResult:
        """
        Parse LLM response into ClassificationResult.
        
        Args:
            response: JSON response from LLM
        
        Returns:
            ClassificationResult
        
        Raises:
            ValueError: If response is invalid JSON or missing required fields
        """
        try:
            data = json.loads(response)
            
            # Validate required fields
            if "intent" not in data:
                raise ValueError("Missing 'intent' field in response")
            if "parameters" not in data:
                raise ValueError("Missing 'parameters' field in response")
            if "confidence" not in data:
                raise ValueError("Missing 'confidence' field in response")
            
            # Validate types
            if not isinstance(data["intent"], str):
                raise ValueError("'intent' must be a string")
            if not isinstance(data["parameters"], dict):
                raise ValueError("'parameters' must be a dictionary")
            if not isinstance(data["confidence"], (int, float)):
                raise ValueError("'confidence' must be a number")
            
            # Validate confidence range
            confidence = float(data["confidence"])
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"'confidence' must be between 0.0 and 1.0, got {confidence}")
            
            return ClassificationResult(
                intent=data["intent"],
                parameters=data["parameters"],
                confidence=confidence,
                reasoning=data.get("reasoning")
            )
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse response: {e}")
```

**Key Design Decisions**:
- ✅ Depends on LLMClient (abstraction), not concrete provider
- ✅ No imports of openai, anthropic, or any provider
- ✅ Uses prompt_name to reference centralized prompt
- ✅ Business logic (confidence threshold, intent validation) separate from LLM calls
- ✅ Can be tested with MockProvider (no API keys needed)

---

## Architecture Analysis

### ✅ What's Good

1. **Clean Separation of Concerns**
   - LLMProvider: Provider contract
   - LLMClient: Application facade with retry logic
   - IntentClassifier: Business logic using abstraction

2. **Dependency Inversion**
   - IntentClassifier depends on LLMClient (abstraction)
   - LLMClient depends on LLMProvider (interface)
   - No concrete provider dependencies in application code

3. **Testability**
   - MockProvider implements LLMProvider
   - Tests use MockProvider (no API keys)
   - Integration tests use real providers (optional)

4. **Extensibility**
   - New providers just implement LLMProvider
   - No changes to application code required
   - Factory pattern for provider creation

5. **Observability**
   - Comprehensive logging throughout
   - Retry attempts logged
   - Provider name in all logs

### 🔍 Potential Issues to Check

1. **Provider Leakage**
   - ✅ No provider-specific imports in IntentClassifier
   - ✅ No provider-specific logic in LLMClient
   - ✅ All provider details isolated to providers/

2. **Error Handling**
   - ✅ ProviderError has is_transient flag
   - ✅ Retry logic respects transient vs permanent
   - ✅ Clear error propagation

3. **Configuration**
   - ✅ Factory functions for provider creation
   - ✅ Environment variable support
   - ✅ Validation on startup

4. **Type Safety**
   - ✅ Type hints throughout
   - ✅ Dataclasses for structured data
   - ✅ Enums for constants

### 📊 Architecture Score

**Overall**: 9/10 - Excellent abstraction layer

**Strengths**:
- True provider independence
- Clean interfaces
- Comprehensive testing strategy
- Good error handling
- Extensible design

**Minor Improvements**:
- Could add response caching (future)
- Could add cost tracking (future)
- Could add streaming support (future)

---

## Copy/Paste Instructions

To share this architecture for review:

1. **Copy this entire file** (`ARCHITECTURE_REVIEW.md`)
2. Or copy individual sections:
   - Section 1: LLMProvider interface
   - Section 2: LLMClient facade
   - Section 3: IntentClassifier example

The three files show:
- **Contract** (LLMProvider)
- **Implementation** (LLMClient)
- **Usage** (IntentClassifier)

This demonstrates the abstraction is bulletproof - no provider leakage anywhere.

---

## Validation Recommendation

Based on this architecture review, I recommend:

1. ✅ **Architecture is solid** - proceed with validation
2. ✅ **No refactoring needed** - abstraction is clean
3. ✅ **Ready for provider swap test** - add to validation plan

Next step: Run `bash scripts/validate_mvp.sh` to validate the implementation.
