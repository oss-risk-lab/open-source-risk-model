# Implementation Tasks: LLM Provider Abstraction Layer

## Overview

This document outlines the concrete implementation steps for the LLM Provider Abstraction Layer MVP. Tasks are organized into phases with clear checkpoints and acceptance criteria.

**MVP Scope**: OpenAIProvider + LLMClient + PromptManager + MockProvider + IntentClassifier migration

**Out of Scope**: ToolRegistry, MCPProvider, AnthropicProvider (stubs only)

---

## Phase 0: Pre-Implementation Sanity Check

**Goal**: Understand existing OpenAI integration before building abstraction.

**Estimated Time**: 15 minutes

### Task 0.1: Identify Existing OpenAI Integration

**Action**: Document current OpenAI usage pattern.

**Investigation**:
```bash
# Check OpenAI SDK version
grep -i openai pyproject.toml requirements.txt 2>/dev/null || echo "Not in dependencies yet"

# Find current OpenAI calls
grep -r "openai\." src/open_source_risk_model/query/

# Check current model and settings
grep -r "chat.completions.create" src/
```

**Document**:
- [ ] Current OpenAI SDK version (if installed): `openai ^1.0` (needs to be added to pyproject.toml)
- [ ] Current API surface: `client.chat.completions.create()` (Chat Completions API)
- [ ] Current model: `gpt-4` (default)
- [ ] Current JSON mode: `response_format={"type": "json_object"}`
- [ ] Current temperature: `0.0` (deterministic)
- [ ] Current max_tokens: `500`

**Findings from Code Review**:
- IntentClassifier uses `openai.OpenAI(api_key=...)` client
- Uses Chat Completions API: `client.chat.completions.create()`
- Forces JSON with `response_format={"type": "json_object"}`
- System message: "You are a precise query classifier. Return only valid JSON."
- User message: Contains full prompt with intent descriptions
- Temperature: 0.0 for deterministic results
- Max tokens: 500

**Done When**:
- [ ] Current integration pattern documented
- [ ] OpenAI SDK version confirmed
- [ ] JSON mode format confirmed
- [ ] No surprises during implementation

---

## Phase 1: Scaffold and Core Models

**Goal**: Create directory structure, data models, and exception hierarchy.

**Estimated Time**: 1 hour

### Task 1.1: Create Directory Structure

**Action**: Create the `llm` module directory structure.

```bash
mkdir -p src/open_source_risk_model/llm/providers
mkdir -p src/open_source_risk_model/llm/prompts
touch src/open_source_risk_model/llm/__init__.py
touch src/open_source_risk_model/llm/providers/__init__.py
```

**Files to Create**:
- `src/open_source_risk_model/llm/__init__.py`
- `src/open_source_risk_model/llm/providers/__init__.py`
- `src/open_source_risk_model/llm/prompts/` (directory)

**Done When**:
- [ ] Directory structure exists
- [ ] All `__init__.py` files created
- [ ] `prompts/` directory exists

---

### Task 1.2: Define Data Models

**Action**: Create standardized data models for requests and responses.

**File**: `src/open_source_risk_model/llm/models.py`

**Implementation**:
```python
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class CompletionRequest:
    messages: List[Message]
    model: str
    temperature: float = 0.0
    max_tokens: int = 500
    response_format: Optional[Literal["json"]] = None  # Simplified: "json" or None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    prompt_name: Optional[str] = None  # For MockProvider routing and debugging


@dataclass
class CompletionResponse:
    content: str
    model: str
    finish_reason: str
    usage: Dict[str, int]
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Any] = None
```

**Done When**:
- [ ] `models.py` file created
- [ ] All data classes defined with type hints
- [ ] Docstrings added
- [ ] File imports without errors



---

### Task 1.3: Define Exception Hierarchy

**Action**: Create custom exceptions for error handling.

**File**: `src/open_source_risk_model/llm/exceptions.py`

**Implementation**:
```python
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
```

**Done When**:
- [ ] `exceptions.py` file created
- [ ] All exception classes defined
- [ ] `ProviderError` includes transient flag and retry_after
- [ ] Docstrings added

---

### Task 1.4: Update Module Exports

**Action**: Export public API from `__init__.py` files.

**File**: `src/open_source_risk_model/llm/__init__.py`

```python
"""LLM Provider Abstraction Layer."""

from .models import Message, MessageRole, CompletionRequest, CompletionResponse
from .exceptions import (
    LLMError,
    ConfigurationError,
    ProviderError,
    ValidationError,
    PromptNotFoundError,
    TemplateRenderError
)

__all__ = [
    "Message",
    "MessageRole",
    "CompletionRequest",
    "CompletionResponse",
    "LLMError",
    "ConfigurationError",
    "ProviderError",
    "ValidationError",
    "PromptNotFoundError",
    "TemplateRenderError",
]
```

**Done When**:
- [ ] Public API exported from `__init__.py`
- [ ] Imports work: `from open_source_risk_model.llm import CompletionRequest`

---

## Phase 1 Checkpoint

**Verification**:
```bash
python -c "from open_source_risk_model.llm import CompletionRequest, ProviderError"
python -c "from open_source_risk_model.llm.models import Message, MessageRole"
python -c "from open_source_risk_model.llm.exceptions import LLMError"
```

**Done When**:
- [ ] All imports work without errors
- [ ] Directory structure complete
- [ ] Data models defined
- [ ] Exception hierarchy defined



---

## Phase 2: Provider Interface and Base Classes

**Goal**: Define abstract provider interface.

**Estimated Time**: 30 minutes

### Task 2.1: Create LLMProvider Abstract Base Class

**Action**: Define the provider interface that all implementations must follow.

**File**: `src/open_source_risk_model/llm/providers/base.py`

**Implementation**:
```python
from abc import ABC, abstractmethod
from typing import List, Iterator
from ..models import CompletionRequest, CompletionResponse


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion."""
        pass
    
    @abstractmethod
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """Stream a completion (future enhancement)."""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate provider configuration."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and debugging."""
        pass
    
    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """List of models supported by this provider."""
        pass
```

**Done When**:
- [ ] `base.py` file created
- [ ] `LLMProvider` abstract class defined
- [ ] All methods marked as `@abstractmethod`
- [ ] Docstrings added
- [ ] Type hints complete

---

### Task 2.2: Update Provider Module Exports

**Action**: Export provider base class.

**File**: `src/open_source_risk_model/llm/providers/__init__.py`

```python
"""LLM Provider implementations."""

from .base import LLMProvider

__all__ = ["LLMProvider"]
```

**Done When**:
- [ ] Provider exports configured
- [ ] Import works: `from open_source_risk_model.llm.providers import LLMProvider`

---

## Phase 2 Checkpoint

**Verification**:
```bash
python -c "from open_source_risk_model.llm.providers import LLMProvider"
python -c "from open_source_risk_model.llm.providers.base import LLMProvider"
```

**Done When**:
- [ ] `LLMProvider` abstract class exists
- [ ] All abstract methods defined
- [ ] Imports work without errors



---

## Phase 3: PromptManager Implementation

**Goal**: Implement centralized prompt management with YAML templates.

**Estimated Time**: 1.5 hours

### Task 3.1: Create PromptManager Class

**Action**: Implement prompt loading and rendering.

**File**: `src/open_source_risk_model/llm/prompt_manager.py`

**Implementation**: See design.md for full implementation

**Key Methods**:
- `__init__(prompts_dir: Path)`: Load prompts from directory
- `_load_prompts()`: Load all YAML files
- `render(prompt_name: str, params: Dict) -> Dict[str, str]`: Render template
- `validate_prompt(prompt_name: str) -> bool`: Validate prompt structure

**Done When**:
- [ ] `prompt_manager.py` file created
- [ ] `PromptManager` class implemented
- [ ] YAML loading works
- [ ] Template rendering works
- [ ] Error handling for missing prompts
- [ ] Error handling for missing parameters
- [ ] Docstrings and type hints complete

---

### Task 3.2: Extract Intent Classification Prompt to YAML

**Action**: Move hardcoded prompt from IntentClassifier to YAML file.

**File**: `src/open_source_risk_model/llm/prompts/intent_classification.yaml`

**Implementation**:
```yaml
name: intent_classification
version: "1.0"
description: "Classify user queries into predefined intents"

required_params:
  - query
  - available_intents

system_template: |
  You are a query intent classifier for a dependency graph database.
  
  Your job is to classify user queries into predefined intents and extract parameters.
  
  AVAILABLE INTENTS:
  {available_intents}
  
  RULES:
  1. intent MUST be one of the intents listed above
  2. confidence MUST be a number between 0.0 and 1.0
  3. If unsure (confidence < 0.7), use intent "unknown"
  4. Extract ALL relevant parameters from the query
  5. Return ONLY valid JSON

user_template: |
  USER QUERY: "{query}"
  
  Classify the query and extract parameters. Return ONLY valid JSON in this exact format:
  
  {{
    "intent": "<intent_name>",
    "parameters": {{"param1": "value1"}},
    "confidence": 0.95,
    "reasoning": "Brief explanation"
  }}

metadata:
  author: "engineering-team"
  created_at: "2024-02-13"
  tags: ["classification", "intent", "query"]
```

**Done When**:
- [ ] YAML file created in `prompts/` directory
- [ ] Prompt structure matches PromptManager expectations
- [ ] Required parameters listed
- [ ] Templates use `{parameter}` syntax for substitution

---

### Task 3.3: Add PromptManager Tests

**Action**: Create unit tests for PromptManager.

**File**: `test/llm/test_prompt_manager.py`

**Test Cases**:
- `test_load_prompts()`: Verify prompts load from directory
- `test_render_with_valid_params()`: Verify template rendering
- `test_render_missing_prompt()`: Verify PromptNotFoundError
- `test_render_missing_params()`: Verify TemplateRenderError
- `test_no_unresolved_placeholders()`: Verify all placeholders substituted

**Done When**:
- [ ] Test file created
- [ ] All test cases implemented
- [ ] Tests pass
- [ ] Coverage >90%

---

## Phase 3 Checkpoint

**Verification**:
```bash
pytest test/llm/test_prompt_manager.py -v
python -c "from open_source_risk_model.llm.prompt_manager import PromptManager"
```

**Done When**:
- [ ] PromptManager implemented
- [ ] Intent classification prompt in YAML
- [ ] All tests pass
- [ ] Prompt rendering works correctly



---

## Phase 4: OpenAI Provider Implementation

**Goal**: Implement concrete OpenAI provider.

**Estimated Time**: 2 hours

### Task 4.1: Create OpenAIProvider Class

**Action**: Implement OpenAI-specific provider.

**File**: `src/open_source_risk_model/llm/providers/openai_provider.py`

**Implementation**: See design.md for full implementation

**Key Methods**:
- `__init__(api_key, base_url, organization, timeout)`: Initialize with config
- `complete(request)`: Call OpenAI Chat Completions API
- `stream(request)`: Stub for future (raise NotImplementedError)
- `validate_config()`: Verify API key and connectivity
- `_translate_to_openai(request)`: Convert to OpenAI format
- `_translate_from_openai(response)`: Convert from OpenAI format

**Error Handling**:
- 401 Unauthorized → ConfigurationError
- 429 Rate Limit → ProviderError(is_transient=True, retry_after=X)
- 503 Service Unavailable → ProviderError(is_transient=True)
- Network timeout → ProviderError(is_transient=True)

**Done When**:
- [ ] `openai_provider.py` file created
- [ ] `OpenAIProvider` class implements `LLMProvider`
- [ ] All abstract methods implemented
- [ ] Request/response translation works
- [ ] Error handling complete
- [ ] Docstrings and type hints complete

---

### Task 4.2: Add OpenAI Provider Tests

**Action**: Create unit tests for OpenAIProvider.

**File**: `test/llm/test_openai_provider.py`

**Test Cases**:
- `test_translate_request()`: Verify request translation
- `test_translate_response()`: Verify response translation
- `test_complete_success()`: Mock successful API call
- `test_complete_rate_limit()`: Mock 429 error
- `test_complete_auth_error()`: Mock 401 error
- `test_complete_timeout()`: Mock timeout
- `test_validate_config_valid()`: Valid API key
- `test_validate_config_invalid()`: Invalid API key

**Mocking Strategy**: Use `pytest-mock` to mock `openai.OpenAI` client

**Done When**:
- [ ] Test file created
- [ ] All test cases implemented
- [ ] Tests use mocking (no real API calls)
- [ ] Tests pass
- [ ] Coverage >90%

---

### Task 4.3: Update Provider Module Exports

**Action**: Export OpenAIProvider.

**File**: `src/open_source_risk_model/llm/providers/__init__.py`

```python
from .base import LLMProvider
from .openai_provider import OpenAIProvider

__all__ = ["LLMProvider", "OpenAIProvider"]
```

**Done When**:
- [ ] OpenAIProvider exported
- [ ] Import works: `from open_source_risk_model.llm.providers import OpenAIProvider`

---

## Phase 4 Checkpoint

**Verification**:
```bash
pytest test/llm/test_openai_provider.py -v
python -c "from open_source_risk_model.llm.providers import OpenAIProvider"
```

**Done When**:
- [ ] OpenAIProvider implemented
- [ ] All tests pass
- [ ] No real API calls in unit tests
- [ ] Error handling works correctly



---

## Phase 5: Mock Provider Implementation

**Goal**: Implement mock provider for testing.

**Estimated Time**: 1 hour

### Task 5.1: Create MockProvider Class

**Action**: Implement mock provider with canned responses.

**File**: `src/open_source_risk_model/llm/providers/mock_provider.py`

**Implementation**:
```python
from typing import Dict, List, Iterator
from .base import LLMProvider
from ..models import CompletionRequest, CompletionResponse


class MockProvider(LLMProvider):
    """Mock provider for testing without API calls."""
    
    def __init__(self, canned_responses: Dict[str, str]):
        """
        Initialize with canned responses.
        
        Args:
            canned_responses: Dict mapping prompt prefix to response
        """
        self.canned_responses = canned_responses
    
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return canned response based on prompt."""
        # Use first 50 chars of system message as key
        key = request.messages[0].content[:50] if request.messages else ""
        content = self.canned_responses.get(key, '{"intent": "unknown"}')
        
        return CompletionResponse(
            content=content,
            model="mock-model",
            finish_reason="stop",
            usage={"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50}
        )
    
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """Stream canned response."""
        yield self.complete(request).content
    
    def validate_config(self) -> bool:
        """Always valid."""
        return True
    
    @property
    def name(self) -> str:
        return "mock"
    
    @property
    def supported_models(self) -> List[str]:
        return ["mock-model"]
```

**Done When**:
- [ ] `mock_provider.py` file created
- [ ] `MockProvider` class implements `LLMProvider`
- [ ] Accepts canned responses at initialization
- [ ] Returns deterministic responses
- [ ] Docstrings and type hints complete

---

### Task 5.2: Add MockProvider Tests

**Action**: Create unit tests for MockProvider.

**File**: `test/llm/test_mock_provider.py`

**Test Cases**:
- `test_complete_returns_canned_response()`: Verify canned response returned
- `test_complete_with_multiple_responses()`: Verify key matching
- `test_validate_config_always_true()`: Verify always valid
- `test_supported_models()`: Verify model list

**Done When**:
- [ ] Test file created
- [ ] All test cases implemented
- [ ] Tests pass
- [ ] Coverage 100%

---

### Task 5.3: Update Provider Module Exports

**Action**: Export MockProvider.

**File**: `src/open_source_risk_model/llm/providers/__init__.py`

```python
from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .mock_provider import MockProvider

__all__ = ["LLMProvider", "OpenAIProvider", "MockProvider"]
```

**Done When**:
- [ ] MockProvider exported
- [ ] Import works: `from open_source_risk_model.llm.providers import MockProvider`

---

## Phase 5 Checkpoint

**Verification**:
```bash
pytest test/llm/test_mock_provider.py -v
python -c "from open_source_risk_model.llm.providers import MockProvider"
```

**Done When**:
- [ ] MockProvider implemented
- [ ] All tests pass
- [ ] Can be used in other tests



---

## Phase 6: LLMClient Implementation

**Goal**: Implement unified client facade with retry logic.

**Estimated Time**: 2 hours

### Task 6.1: Create LLMClient Class

**Action**: Implement client facade with retry logic.

**File**: `src/open_source_risk_model/llm/client.py`

**Implementation**: See design.md for full implementation

**Key Methods**:
- `__init__(provider, prompt_manager, retry_config)`: Initialize client
- `complete(prompt_name, prompt_params, model, temperature, max_tokens, response_format)`: Generate completion
- `_execute_with_retry(request)`: Execute with exponential backoff

**Retry Logic**:
- Max retries: 3 (configurable)
- Backoff factor: 2.0 (configurable)
- Timeout: 30 seconds (configurable)
- Only retry on transient errors (is_transient=True)

**Done When**:
- [ ] `client.py` file created
- [ ] `LLMClient` class implemented
- [ ] Retry logic with exponential backoff
- [ ] Integrates with PromptManager
- [ ] Integrates with LLMProvider
- [ ] Docstrings and type hints complete

---

### Task 6.2: Add LLMClient Tests

**Action**: Create unit tests for LLMClient.

**File**: `test/llm/test_client.py`

**Test Cases**:
- `test_complete_success()`: Verify successful completion
- `test_complete_with_retry()`: Verify retry on transient error
- `test_complete_max_retries_exceeded()`: Verify max retries enforced
- `test_complete_no_retry_on_permanent_error()`: Verify no retry on 401
- `test_exponential_backoff()`: Verify backoff timing
- `test_prompt_rendering_integration()`: Verify PromptManager integration

**Mocking Strategy**: Use MockProvider for provider, real PromptManager

**Done When**:
- [ ] Test file created
- [ ] All test cases implemented
- [ ] Tests use MockProvider
- [ ] Tests pass
- [ ] Coverage >90%

---

### Task 6.3: Update Module Exports

**Action**: Export LLMClient.

**File**: `src/open_source_risk_model/llm/__init__.py`

```python
from .client import LLMClient
from .prompt_manager import PromptManager
# ... existing exports ...

__all__ = [
    "LLMClient",
    "PromptManager",
    # ... existing exports ...
]
```

**Done When**:
- [ ] LLMClient exported
- [ ] Import works: `from open_source_risk_model.llm import LLMClient`

---

## Phase 6 Checkpoint

**Verification**:
```bash
pytest test/llm/test_client.py -v
python -c "from open_source_risk_model.llm import LLMClient, PromptManager"
```

**Done When**:
- [ ] LLMClient implemented
- [ ] Retry logic works
- [ ] All tests pass
- [ ] Integrates with PromptManager and providers



---

## Phase 7: Configuration and Provider Factory

**Goal**: Implement configuration-driven provider selection.

**Estimated Time**: 1 hour

### Task 7.1: Create Provider Factory

**Action**: Implement factory for creating providers from configuration.

**File**: `src/open_source_risk_model/llm/factory.py`

**Implementation**:
```python
import os
from typing import Dict, Any
from .providers import LLMProvider, OpenAIProvider
from .exceptions import ConfigurationError


def create_provider(config: Dict[str, Any]) -> LLMProvider:
    """
    Create provider from configuration dict.
    
    Args:
        config: Provider configuration
        
    Returns:
        Configured LLMProvider instance
        
    Raises:
        ConfigurationError: If config is invalid
    """
    provider_type = config.get("provider_type")
    
    if provider_type == "openai":
        return OpenAIProvider(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
            organization=config.get("organization"),
            timeout=config.get("timeout", 30)
        )
    else:
        raise ConfigurationError(f"Unknown provider type: {provider_type}")


def create_provider_from_env() -> LLMProvider:
    """
    Create provider from environment variables.
    
    Environment variables:
        LLM_PROVIDER: Provider type (default: openai)
        OPENAI_API_KEY: OpenAI API key
        OPENAI_BASE_URL: Optional base URL
        OPENAI_ORGANIZATION: Optional organization
        
    Returns:
        Configured LLMProvider instance
        
    Raises:
        ConfigurationError: If required env vars missing
    """
    provider_type = os.environ.get("LLM_PROVIDER", "openai")
    
    if provider_type == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError("OPENAI_API_KEY environment variable required")
        
        return OpenAIProvider(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL"),
            organization=os.environ.get("OPENAI_ORGANIZATION")
        )
    else:
        raise ConfigurationError(f"Unknown provider type: {provider_type}")
```

**Done When**:
- [ ] `factory.py` file created
- [ ] `create_provider()` function implemented
- [ ] `create_provider_from_env()` function implemented
- [ ] Error handling for missing config
- [ ] Docstrings and type hints complete

---

### Task 7.2: Add Factory Tests

**Action**: Create unit tests for factory functions.

**File**: `test/llm/test_factory.py`

**Test Cases**:
- `test_create_provider_openai()`: Verify OpenAI provider creation
- `test_create_provider_unknown_type()`: Verify error on unknown type
- `test_create_provider_from_env()`: Verify env-based creation
- `test_create_provider_from_env_missing_key()`: Verify error on missing API key

**Done When**:
- [ ] Test file created
- [ ] All test cases implemented
- [ ] Tests pass
- [ ] Coverage >90%

---

### Task 7.3: Update Module Exports

**Action**: Export factory functions.

**File**: `src/open_source_risk_model/llm/__init__.py`

```python
from .factory import create_provider, create_provider_from_env
# ... existing exports ...

__all__ = [
    "create_provider",
    "create_provider_from_env",
    # ... existing exports ...
]
```

**Done When**:
- [ ] Factory functions exported
- [ ] Import works: `from open_source_risk_model.llm import create_provider`

---

## Phase 7 Checkpoint

**Verification**:
```bash
pytest test/llm/test_factory.py -v
python -c "from open_source_risk_model.llm import create_provider, create_provider_from_env"
```

**Done When**:
- [ ] Factory functions implemented
- [ ] All tests pass
- [ ] Configuration-driven provider selection works



---

## Phase 8: IntentClassifier Migration

**Goal**: Refactor IntentClassifier to use LLMClient.

**Estimated Time**: 2 hours

### Task 8.1: Refactor IntentClassifier

**Action**: Replace direct OpenAI calls with LLMClient.

**File**: `src/open_source_risk_model/query/intent_classifier.py`

**Changes**:
1. Remove `import openai` (move to OpenAIProvider only)
2. Add `from open_source_risk_model.llm import LLMClient`
3. Update `__init__()` to accept `LLMClient` instead of API key
4. Replace `_call_llm()` with `client.complete()`
5. Update prompt to use PromptManager format
6. Maintain exact same classification behavior

**Before**:
```python
class IntentClassifier:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
    
    def _call_llm(self, prompt: str) -> str:
        response = self.client.chat.completions.create(...)
        return response.choices[0].message.content
```

**After**:
```python
class IntentClassifier:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
    
    def classify(self, query: str) -> ClassificationResult:
        response = self.llm_client.complete(
            prompt_name="intent_classification",
            prompt_params={
                "query": query,
                "available_intents": self._format_intents()
            },
            response_format="json",
            temperature=0.0
        )
        # Parse response.content as JSON
        ...
```

**Done When**:
- [ ] IntentClassifier refactored
- [ ] No direct `openai` imports
- [ ] Uses `LLMClient.complete()`
- [ ] Maintains same classification behavior
- [ ] Docstrings updated

---

### Task 8.2: Update IntentClassifier Initialization

**Action**: Update places where IntentClassifier is instantiated.

**Files to Update**:
- `api/app.py` (if applicable)
- `src/open_source_risk_model/query/` (any other files)
- Test files

**Changes**:
```python
# Before
classifier = IntentClassifier(api_key=os.environ["OPENAI_API_KEY"])

# After
from open_source_risk_model.llm import create_provider_from_env, LLMClient, PromptManager
from pathlib import Path

provider = create_provider_from_env()
prompts_dir = Path("src/open_source_risk_model/llm/prompts")
prompt_manager = PromptManager(prompts_dir)
client = LLMClient(provider, prompt_manager)
classifier = IntentClassifier(client)
```

**Done When**:
- [ ] All instantiation sites updated
- [ ] No direct API key passing
- [ ] Uses factory functions

---

### Task 8.3: Update Existing Tests

**Action**: Update existing IntentClassifier tests to use MockProvider.

**File**: `test/test_intent_classifier.py`

**Changes**:
1. Replace real OpenAI calls with MockProvider
2. Configure MockProvider with expected responses
3. Verify tests still pass
4. Remove API key requirements

**Example**:
```python
def test_classify_list_dependencies():
    # Setup mock provider
    mock_provider = MockProvider({
        "You are a query intent classifier": '{"intent": "list_dependencies", "parameters": {"repo_full_name": "django/django"}, "confidence": 0.95}'
    })
    
    # Create client with mock
    prompt_manager = PromptManager(Path("src/open_source_risk_model/llm/prompts"))
    client = LLMClient(mock_provider, prompt_manager)
    classifier = IntentClassifier(client)
    
    # Test classification
    result = classifier.classify("What are the dependencies of django/django?")
    assert result.intent == "list_dependencies"
    assert result.parameters["repo_full_name"] == "django/django"
```

**Done When**:
- [ ] All existing tests updated
- [ ] Tests use MockProvider
- [ ] No API keys required
- [ ] All tests pass

---

## Phase 8 Checkpoint

**Verification**:
```bash
pytest test/test_intent_classifier.py -v
# Should pass without OPENAI_API_KEY
```

**Done When**:
- [ ] IntentClassifier refactored
- [ ] All existing tests pass
- [ ] No direct OpenAI imports in application code
- [ ] Tests use MockProvider



---

## Phase 9: Integration Tests

**Goal**: Add integration test with real OpenAI API (skipped without API key).

**Estimated Time**: 1 hour

### Task 9.1: Create Integration Test

**Action**: Add end-to-end integration test.

**File**: `test/llm/test_integration.py`

**Implementation**:
```python
import os
import pytest
from pathlib import Path
from open_source_risk_model.llm import (
    create_provider_from_env,
    LLMClient,
    PromptManager
)
from open_source_risk_model.query.intent_classifier import IntentClassifier


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
def test_intent_classification_with_real_openai():
    """Integration test with real OpenAI API."""
    # Create real provider
    provider = create_provider_from_env()
    
    # Create client
    prompts_dir = Path("src/open_source_risk_model/llm/prompts")
    prompt_manager = PromptManager(prompts_dir)
    client = LLMClient(provider, prompt_manager)
    
    # Create classifier
    classifier = IntentClassifier(client)
    
    # Test classification
    result = classifier.classify("What are the dependencies of django/django?")
    
    # Verify result
    assert result.intent == "list_dependencies"
    assert result.confidence >= 0.7
    assert "repo_full_name" in result.parameters
    assert result.parameters["repo_full_name"] == "django/django"


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
def test_retry_on_transient_error():
    """Test retry logic with real provider."""
    # This test would need to simulate transient errors
    # For now, just verify provider works
    provider = create_provider_from_env()
    assert provider.validate_config()
```

**Done When**:
- [ ] Integration test file created
- [ ] Tests marked with `@pytest.mark.integration`
- [ ] Tests skipped without `OPENAI_API_KEY`
- [ ] Tests pass when API key provided

---

### Task 9.2: Update pytest Configuration

**Action**: Configure pytest to handle integration tests.

**File**: `pytest.ini` or `pyproject.toml`

**Configuration**:
```ini
[pytest]
markers =
    integration: marks tests as integration tests (deselect with '-m "not integration"')
```

**Done When**:
- [ ] pytest markers configured
- [ ] Can run unit tests only: `pytest -m "not integration"`
- [ ] Can run integration tests: `pytest -m integration`

---

## Phase 9 Checkpoint

**Verification**:
```bash
# Run without API key - should skip integration tests
pytest test/llm/test_integration.py -v

# Run with API key - should execute integration tests
OPENAI_API_KEY=sk-... pytest test/llm/test_integration.py -v
```

**Done When**:
- [ ] Integration tests created
- [ ] Tests skipped without API key
- [ ] Tests pass with API key
- [ ] pytest markers configured



---

## Phase 10: Documentation and Cleanup

**Goal**: Add documentation and verify everything works.

**Estimated Time**: 1 hour

### Task 10.1: Add Module Documentation

**Action**: Create README for LLM module.

**File**: `src/open_source_risk_model/llm/README.md`

**Content**:
- Overview of abstraction layer
- Quick start guide
- Provider configuration examples
- Prompt management guide
- Testing guide
- Future enhancements

**Done When**:
- [ ] README created
- [ ] Examples included
- [ ] Configuration documented

---

### Task 10.2: Update Project Documentation

**Action**: Update main project docs to reference LLM abstraction.

**Files to Update**:
- `README.md`: Add section on LLM configuration
- `docs/SETUP.md`: Add LLM setup instructions
- `.env.example`: Add LLM environment variables

**Changes to `.env.example`:
```bash
# LLM Provider Configuration
LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key-here
# OPENAI_BASE_URL=https://api.openai.com/v1  # Optional
# OPENAI_ORGANIZATION=your-org-id  # Optional
```

**Done When**:
- [ ] Main README updated
- [ ] Setup docs updated
- [ ] `.env.example` updated

---

### Task 10.3: Verify Provider Abstraction Invariant

**Action**: Verify no provider-specific imports in application code.

**Verification Script**:
```bash
#!/bin/bash
# verify_abstraction.sh

echo "Checking for provider-specific imports in application code..."

# Should return no results
grep -r "import openai" src/open_source_risk_model/query/ && echo "FAIL: Found openai import" || echo "PASS: No openai imports"
grep -r "from openai" src/open_source_risk_model/query/ && echo "FAIL: Found openai import" || echo "PASS: No openai imports"
grep -r "import anthropic" src/open_source_risk_model/query/ && echo "FAIL: Found anthropic import" || echo "PASS: No anthropic imports"

# Provider imports should only be in llm/providers/
echo ""
echo "Provider imports should only be in llm/providers/:"
grep -r "import openai" src/open_source_risk_model/llm/providers/
```

**Done When**:
- [ ] Verification script created
- [ ] Script passes (no provider imports in application code)
- [ ] Provider imports only in `llm/providers/`

---

### Task 10.4: Run Full Test Suite

**Action**: Verify all tests pass.

**Commands**:
```bash
# Run all unit tests (no API key required)
pytest -m "not integration" -v

# Run with coverage
pytest -m "not integration" --cov=src/open_source_risk_model/llm --cov-report=html

# Run integration tests (requires API key)
OPENAI_API_KEY=sk-... pytest -m integration -v

# Run all tests
OPENAI_API_KEY=sk-... pytest -v
```

**Done When**:
- [ ] All unit tests pass without API key
- [ ] Coverage >90% for new code
- [ ] Integration tests pass with API key
- [ ] No regressions in existing tests

---

## Phase 10 Checkpoint

**Verification**:
```bash
pytest -m "not integration" -v --cov=src/open_source_risk_model/llm
./verify_abstraction.sh
```

**Done When**:
- [ ] Documentation complete
- [ ] All tests pass
- [ ] Provider abstraction verified
- [ ] Coverage >90%



---

## Phase 11: Future Stubs (Out of MVP Scope)

**Goal**: Create placeholder stubs for future enhancements.

**Estimated Time**: 30 minutes

### Task 11.1: Create ToolRegistry Stub

**Action**: Create placeholder for future tool/function calling support.

**File**: `src/open_source_risk_model/llm/tool_registry.py`

**Implementation**:
```python
"""
Tool Registry for LLM function calling.

FUTURE ENHANCEMENT - NOT IMPLEMENTED IN MVP
"""

from typing import Dict, Any, Callable, List


class ToolRegistry:
    """
    Registry for LLM tools/functions.
    
    STUB: This is a placeholder for future implementation.
    """
    
    def __init__(self):
        """Initialize tool registry."""
        raise NotImplementedError("ToolRegistry not yet implemented")
    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        handler: Callable
    ) -> None:
        """Register a tool (not implemented)."""
        raise NotImplementedError("ToolRegistry not yet implemented")
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions (not implemented)."""
        raise NotImplementedError("ToolRegistry not yet implemented")
```

**Done When**:
- [ ] Stub file created
- [ ] All methods raise NotImplementedError
- [ ] Docstrings indicate future enhancement

---

### Task 11.2: Create AnthropicProvider Stub

**Action**: Create placeholder for Anthropic provider.

**File**: `src/open_source_risk_model/llm/providers/anthropic_provider.py`

**Implementation**:
```python
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
```

**Done When**:
- [ ] Stub file created
- [ ] All methods raise NotImplementedError
- [ ] Docstrings indicate future enhancement

---

### Task 11.3: Create MCPProvider Stub

**Action**: Create placeholder for MCP provider.

**File**: `src/open_source_risk_model/llm/providers/mcp_provider.py`

**Implementation**:
```python
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
```

**Done When**:
- [ ] Stub file created
- [ ] All methods raise NotImplementedError
- [ ] Docstrings indicate future enhancement

---

## Phase 11 Checkpoint

**Verification**:
```bash
python -c "from open_source_risk_model.llm.tool_registry import ToolRegistry"
python -c "from open_source_risk_model.llm.providers.anthropic_provider import AnthropicProvider"
python -c "from open_source_risk_model.llm.providers.mcp_provider import MCPProvider"
```

**Done When**:
- [ ] All stub files created
- [ ] Imports work
- [ ] All methods raise NotImplementedError
- [ ] Clearly marked as future enhancements



---

## Final Verification and Acceptance

### MVP Acceptance Criteria

**Functional Requirements**:
- [ ] `LLMProvider` abstract interface exists
- [ ] `OpenAIProvider` implemented and working
- [ ] `LLMClient` facade with retry logic working
- [ ] `PromptManager` loads and renders YAML templates
- [ ] `MockProvider` works for testing
- [ ] IntentClassifier uses LLMClient (no direct OpenAI imports)
- [ ] Configuration-driven provider selection works
- [ ] All existing tests pass

**Quality Requirements**:
- [ ] 100% of unit tests use MockProvider (no API keys)
- [ ] Integration test exists (skipped without API key)
- [ ] Code coverage >90% for new code
- [ ] All docstrings complete
- [ ] Type hints throughout
- [ ] Linting passes (flake8, mypy)

**Invariants Verified**:
- [ ] No provider-specific imports in application code
- [ ] All providers return standardized responses
- [ ] Prompt templates have no unresolved placeholders
- [ ] Configuration validation works
- [ ] Retry logic is idempotent
- [ ] Errors preserve context for retry decisions

**Performance**:
- [ ] Abstraction overhead <5ms per request
- [ ] Total request time within 10% of baseline
- [ ] Memory usage unchanged

**Documentation**:
- [ ] LLM module README complete
- [ ] Main project docs updated
- [ ] `.env.example` updated
- [ ] Configuration examples provided

---

## Summary

### Total Estimated Time: 12-14 hours

**Phase Breakdown**:
1. Scaffold and Core Models: 1 hour
2. Provider Interface: 30 minutes
3. PromptManager: 1.5 hours
4. OpenAIProvider: 2 hours
5. MockProvider: 1 hour
6. LLMClient: 2 hours
7. Configuration/Factory: 1 hour
8. IntentClassifier Migration: 2 hours
9. Integration Tests: 1 hour
10. Documentation: 1 hour
11. Future Stubs: 30 minutes

### Implementation Order

1. ✅ Phase 1: Scaffold (foundation)
2. ✅ Phase 2: Provider Interface (contracts)
3. ✅ Phase 3: PromptManager (prompt management)
4. ✅ Phase 4: OpenAIProvider (concrete implementation)
5. ✅ Phase 5: MockProvider (testing support)
6. ✅ Phase 6: LLMClient (facade and retry)
7. ✅ Phase 7: Configuration (provider selection)
8. ✅ Phase 8: IntentClassifier Migration (integration)
9. ✅ Phase 9: Integration Tests (validation)
10. ✅ Phase 10: Documentation (completeness)
11. ✅ Phase 11: Future Stubs (placeholders)

### Key Success Metrics

- **Backward Compatibility**: All existing tests pass ✓
- **Abstraction**: No provider imports in application code ✓
- **Testability**: Unit tests work without API keys ✓
- **Performance**: <5ms overhead ✓
- **Quality**: >90% code coverage ✓

---

## Post-MVP Roadmap

### Phase 12: ToolRegistry (Future)
- Implement function calling support
- Add tool schema validation
- Add tool execution routing

### Phase 13: AnthropicProvider (Future)
- Implement Anthropic Claude integration
- Handle Anthropic-specific message format
- Add Anthropic error handling

### Phase 14: MCPProvider (Future)
- Implement MCP server integration
- Add tool discovery from MCP
- Add context management

### Phase 15: Advanced Features (Future)
- Response caching
- Cost tracking and budgets
- Multi-model routing
- A/B testing for prompts
- Streaming support
