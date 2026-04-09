# LLM Provider Abstraction Layer

## Overview

The LLM Provider Abstraction Layer provides a provider-agnostic interface for LLM interactions, decoupling the application from specific LLM providers (OpenAI, Anthropic, etc.). This abstraction enables:

- **Provider Independence**: Switch between LLM providers without changing application code
- **Centralized Prompts**: Manage all prompts in YAML files with versioning and templating
- **Testability**: Mock providers for testing without API calls or costs
- **Retry Logic**: Built-in exponential backoff for transient failures
- **Configuration-Driven**: Select providers via environment variables or config files

## Quick Start

### Basic Usage

```python
from pathlib import Path
from open_source_risk_model.llm import (
    create_provider_from_env,
    LLMClient,
    PromptManager
)

# Create provider from environment variables
provider = create_provider_from_env()

# Initialize prompt manager
prompts_dir = Path("src/open_source_risk_model/llm/prompts")
prompt_manager = PromptManager(prompts_dir)

# Create client
client = LLMClient(provider, prompt_manager)

# Generate completion
response = client.complete(
    prompt_name="intent_classification",
    prompt_params={"query": "What are the dependencies of django?"},
    response_format="json",
    temperature=0.0
)

print(response.content)
```

### Using in Application Code

```python
from open_source_risk_model.llm import LLMClient

class IntentClassifier:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
    
    def classify(self, query: str):
        response = self.llm_client.complete(
            prompt_name="intent_classification",
            prompt_params={
                "query": query,
                "available_intents": self._format_intents()
            },
            response_format="json",
            temperature=0.0
        )
        return json.loads(response.content)
```

## Provider Configuration

### OpenAI Provider

Set environment variables:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-your-api-key-here
# Optional:
# export OPENAI_BASE_URL=https://api.openai.com/v1
# export OPENAI_ORGANIZATION=org-your-org-id
```

Or configure programmatically:

```python
from open_source_risk_model.llm import create_provider

config = {
    "provider_type": "openai",
    "api_key": "sk-your-api-key-here",
    "base_url": "https://api.openai.com/v1",  # Optional
    "organization": "org-your-org-id",  # Optional
    "timeout": 30
}

provider = create_provider(config)
```

### Mock Provider (Testing)

```python
from open_source_risk_model.llm.providers import MockProvider

# Configure with canned responses
mock_provider = MockProvider({
    "You are a query intent classifier": '{"intent": "list_dependencies", "confidence": 0.95}'
})

client = LLMClient(mock_provider, prompt_manager)
```

## Prompt Management

### Prompt File Format

Prompts are stored in `src/open_source_risk_model/llm/prompts/*.yaml`:

```yaml
name: intent_classification
version: "1.0"
description: "Classify user queries into predefined intents"

required_params:
  - query
  - available_intents

system_template: |
  You are a query intent classifier.
  
  AVAILABLE INTENTS:
  {available_intents}

user_template: |
  USER QUERY: "{query}"
  
  Classify the query and return JSON.

metadata:
  author: "engineering-team"
  created_at: "2024-02-13"
  tags: ["classification", "intent"]
```

### Using Prompts

```python
# Render a prompt with parameters
rendered = prompt_manager.render(
    "intent_classification",
    {
        "query": "What are the dependencies?",
        "available_intents": "list_dependencies, search_packages"
    }
)

# Returns: {"system": "...", "user": "..."}
```

### Template Syntax

- Use `{parameter}` for substitution
- Use `{{escaped}}` for literal braces
- All `required_params` must be provided

## Testing Guide

### Unit Tests (No API Key Required)

All unit tests use `MockProvider` and require no API keys:

```bash
# Run all unit tests
pytest -m "not integration" -v

# Run with coverage
pytest -m "not integration" --cov=src/open_source_risk_model/llm
```

### Integration Tests (API Key Required)

Integration tests use real providers and are skipped without API keys:

```bash
# Run integration tests
OPENAI_API_KEY=sk-... pytest -m integration -v
```

### Writing Tests

```python
import pytest
from pathlib import Path
from open_source_risk_model.llm import LLMClient, PromptManager
from open_source_risk_model.llm.providers import MockProvider

def test_classification():
    # Setup mock provider
    mock_provider = MockProvider({
        "You are a query intent classifier": '{"intent": "list_dependencies"}'
    })
    
    # Create client
    prompts_dir = Path("src/open_source_risk_model/llm/prompts")
    prompt_manager = PromptManager(prompts_dir)
    client = LLMClient(mock_provider, prompt_manager)
    
    # Test
    response = client.complete(
        prompt_name="intent_classification",
        prompt_params={"query": "test", "available_intents": "test"}
    )
    
    assert "intent" in response.content
```

## Architecture

### Components

- **LLMProvider**: Abstract interface for all providers
- **OpenAIProvider**: Concrete OpenAI implementation
- **MockProvider**: Mock provider for testing
- **LLMClient**: Unified client facade with retry logic
- **PromptManager**: Centralized prompt management
- **Factory Functions**: Configuration-driven provider creation

### Error Handling

Custom exception hierarchy:

- `LLMError`: Base exception
- `ConfigurationError`: Invalid configuration
- `ProviderError`: Provider API failure (includes `is_transient` flag)
- `ValidationError`: Request/response validation failure
- `PromptNotFoundError`: Prompt template not found
- `TemplateRenderError`: Template rendering failure

### Retry Logic

`LLMClient` includes exponential backoff retry:

- Max retries: 3 (configurable)
- Backoff factor: 2.0 (configurable)
- Only retries transient errors (rate limits, timeouts)
- Permanent errors (auth failures) fail immediately

## Future Enhancements

### Planned Features

1. **ToolRegistry**: Function calling support for structured tool use
2. **AnthropicProvider**: Claude integration
3. **MCPProvider**: Model Context Protocol support
4. **Streaming**: Real-time response streaming
5. **Caching**: Response caching for identical requests
6. **Cost Tracking**: Token usage and cost monitoring
7. **Multi-Model Routing**: Automatic model selection based on task complexity

### Provider Stubs

Placeholder implementations exist for future providers:

- `AnthropicProvider` (stub)
- `MCPProvider` (stub)
- `ToolRegistry` (stub)

All stubs raise `NotImplementedError` and are clearly marked as future enhancements.

## API Reference

### LLMClient

```python
class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        prompt_manager: PromptManager,
        retry_config: Optional[Dict[str, Any]] = None
    )
    
    def complete(
        self,
        prompt_name: str,
        prompt_params: Dict[str, Any],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 500,
        response_format: Optional[str] = None
    ) -> CompletionResponse
```

### PromptManager

```python
class PromptManager:
    def __init__(self, prompts_dir: Path)
    
    def render(
        self,
        prompt_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, str]
```

### Factory Functions

```python
def create_provider(config: Dict[str, Any]) -> LLMProvider

def create_provider_from_env() -> LLMProvider
```

## Contributing

When adding new prompts:

1. Create YAML file in `src/open_source_risk_model/llm/prompts/`
2. Follow the standard format (name, version, description, templates)
3. List all `required_params`
4. Add tests for prompt rendering
5. Document in this README

When adding new providers:

1. Implement `LLMProvider` abstract interface
2. Handle provider-specific authentication
3. Translate requests/responses to standard format
4. Add comprehensive error handling
5. Add unit tests with mocking
6. Add integration tests (skipped without credentials)
7. Update factory functions
8. Document configuration in this README
