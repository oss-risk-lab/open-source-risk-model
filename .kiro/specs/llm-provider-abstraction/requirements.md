# Requirements: LLM Provider Abstraction Layer

## Overview

Create a provider-agnostic LLM integration layer that decouples the application from specific LLM providers (currently OpenAI). The abstraction layer centralizes prompts, defines clear interfaces, and prepares for future multi-provider support while maintaining current functionality.

## Functional Requirements

### FR1: Provider Abstraction Interface

**Requirement**: Define an abstract `LLMProvider` interface that all provider implementations must conform to.

**Details**:
- Abstract base class with `complete()`, `stream()`, `validate_config()` methods
- Standardized `CompletionRequest` and `CompletionResponse` data models
- Provider-agnostic message format with role enumeration
- Support for temperature, max_tokens, response_format parameters

**Acceptance Criteria**:
- `LLMProvider` abstract base class exists in `src/open_source_risk_model/llm/providers/base.py`
- All required methods are abstract and documented
- Data models defined in `src/open_source_risk_model/llm/models.py`

---

### FR2: OpenAI Provider Implementation

**Requirement**: Implement concrete OpenAI provider that wraps the OpenAI API.

**Details**:
- Translate `CompletionRequest` to OpenAI Chat Completions API format
- Translate OpenAI responses to standardized `CompletionResponse`
- Handle OpenAI-specific authentication (API key, organization)
- Support OpenAI-specific features (response_format, function calling)
- Handle OpenAI-specific errors (rate limits, authentication failures)

**Acceptance Criteria**:
- `OpenAIProvider` class exists in `src/open_source_risk_model/llm/providers/openai_provider.py`
- Implements all `LLMProvider` abstract methods
- Successfully makes OpenAI API calls
- Handles errors gracefully with appropriate exceptions

---

### FR3: LLMClient Facade

**Requirement**: Provide a unified client interface for all LLM operations.

**Details**:
- Single entry point for LLM interactions
- Accepts provider instance at initialization
- Integrates with PromptManager for prompt rendering
- Implements retry logic with exponential backoff
- Provides `complete()` method that accepts prompt name and parameters

**Acceptance Criteria**:
- `LLMClient` class exists in `src/open_source_risk_model/llm/client.py`
- Accepts `LLMProvider` and `PromptManager` at initialization
- Implements retry logic with configurable max_retries and backoff
- All existing IntentClassifier functionality works through LLMClient

---

### FR4: Centralized Prompt Management

**Requirement**: Move all prompts from code to YAML files with template rendering.

**Details**:
- Store prompts in `src/open_source_risk_model/llm/prompts/*.yaml`
- YAML format includes: name, version, description, system_template, user_template, required_params
- Template rendering with parameter substitution
- Validation of required parameters
- Detection of unresolved placeholders

**Acceptance Criteria**:
- `PromptManager` class exists in `src/open_source_risk_model/llm/prompt_manager.py`
- Intent classification prompt extracted to `intent_classification.yaml`
- `render()` method substitutes all parameters correctly
- Raises `PromptNotFoundError` for missing prompts
- Raises `TemplateRenderError` for missing parameters

---

### FR5: Mock Provider for Testing

**Requirement**: Implement mock provider for testing without API calls.

**Details**:
- Accepts canned responses at initialization
- Returns predefined responses based on prompt content
- No external API calls
- Deterministic behavior for testing

**Acceptance Criteria**:
- `MockProvider` class exists in `src/open_source_risk_model/llm/providers/mock_provider.py`
- Implements all `LLMProvider` abstract methods
- Can be configured with response mappings
- All unit tests use MockProvider (no API keys required)

---

### FR6: IntentClassifier Migration

**Requirement**: Refactor IntentClassifier to use LLMClient instead of direct OpenAI calls.

**Details**:
- Remove direct `openai` imports from IntentClassifier
- Accept `LLMClient` at initialization
- Use `client.complete()` instead of `_call_llm()`
- Maintain exact same classification behavior
- Preserve strict JSON response format
- Keep temperature=0.0 default

**Acceptance Criteria**:
- IntentClassifier no longer imports `openai` directly
- Accepts `LLMClient` in `__init__()`
- All existing tests pass without modification
- Classification results identical to previous implementation

---

### FR7: Configuration-Driven Provider Selection

**Requirement**: Select LLM provider via configuration, not code changes.

**Details**:
- Environment variable `LLM_PROVIDER` (default: "openai")
- Configuration file support (`config/llm_config.yaml`)
- Provider factory pattern for instantiation
- No provider-specific imports outside `llm/providers/` directory

**Acceptance Criteria**:
- `ProviderFactory.from_env()` creates provider from environment variables
- `LLM_PROVIDER=openai` works by default
- Provider-specific code isolated in `llm/providers/` directory
- Application code never imports `openai`, `anthropic`, etc. directly

---

### FR8: Error Handling and Transparency

**Requirement**: Preserve error information for informed retry/fallback decisions.

**Details**:
- Custom exception hierarchy: `LLMError`, `ProviderError`, `ConfigurationError`, `ValidationError`
- `ProviderError` includes: provider name, is_transient flag, retry_after
- Distinguish between transient (retry) and permanent (fail fast) errors
- Log all errors with context

**Acceptance Criteria**:
- Exception classes defined in `src/open_source_risk_model/llm/exceptions.py`
- `ProviderError` includes `is_transient` and `retry_after` attributes
- Transient errors (503, timeout) marked appropriately
- Permanent errors (401, 400) marked as non-transient

---

## Non-Functional Requirements

### NFR1: Backward Compatibility

**Requirement**: Existing functionality must work without changes.

**Details**:
- All existing tests pass without modification
- Intent classification behavior unchanged
- Response format identical
- No breaking API changes

**Acceptance Criteria**:
- All tests in `test/test_intent_classifier.py` pass
- All tests in `test/test_intent_executor.py` pass
- Classification accuracy unchanged
- Response times within 10% of baseline

---

### NFR2: Performance

**Requirement**: Abstraction layer adds minimal overhead.

**Details**:
- Request/response translation: <5ms overhead
- Retry logic: configurable timeout and backoff
- No unnecessary object copies or serialization

**Acceptance Criteria**:
- Abstraction overhead <5ms per request
- Total request time within 10% of direct OpenAI calls
- Memory usage unchanged

---

### NFR3: Testability

**Requirement**: All components testable without external API calls.

**Details**:
- MockProvider for unit tests
- No API keys required for unit tests
- Integration tests skipped unless `OPENAI_API_KEY` present
- 100% code coverage achievable without API calls

**Acceptance Criteria**:
- All unit tests use MockProvider
- `pytest` runs without API keys
- Integration tests marked with `@pytest.mark.integration`
- Integration tests skipped when `OPENAI_API_KEY` not set

---

### NFR4: Maintainability

**Requirement**: Code is well-organized and documented.

**Details**:
- Clear separation of concerns
- Comprehensive docstrings
- Type hints throughout
- Logging at appropriate levels

**Acceptance Criteria**:
- All public methods have docstrings
- All classes have type hints
- Logging uses appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Code passes linting (flake8, mypy)

---

## Invariants (Correctness Properties)

### INV1: Provider Abstraction Invariant

**Property**: Application code never directly imports provider-specific libraries (openai, anthropic, etc.), only abstraction layer interfaces.

**Validation**: 
```bash
# Should return no results
grep -r "import openai" src/open_source_risk_model/query/
grep -r "from openai" src/open_source_risk_model/query/
```

**Rationale**: True abstraction requires complete isolation of provider-specific code.

---

### INV2: Request/Response Standardization

**Property**: For any provider implementation, calling `provider.complete(request)` with a valid `CompletionRequest` must return a `CompletionResponse` with all required fields populated.

**Validation**: Property-based test with Hypothesis generating random requests

**Rationale**: Ensures all providers conform to the same contract.

---

### INV3: Prompt Template Completeness

**Property**: For any prompt template, rendering with all required parameters must produce a valid prompt with no unresolved placeholders (except escaped `{{}}` patterns).

**Validation**: 
```python
rendered = prompt_manager.render(prompt_name, params)
assert "{" not in rendered["system"] or "{{" in rendered["system"]
assert "{" not in rendered["user"] or "{{" in rendered["user"]
```

**Rationale**: Unresolved placeholders will confuse the LLM and produce incorrect results.

---

### INV4: Configuration Validation

**Property**: For any provider configuration, calling `provider.validate_config()` must return True if and only if the provider can successfully make API calls.

**Validation**: Test with valid and invalid configurations

**Rationale**: Invalid configurations should be detected early at initialization.

---

### INV5: Retry Idempotency

**Property**: For any completion request with temperature=0.0, retrying after a transient failure must produce an equivalent result (same intent/classification).

**Validation**: Test with MockProvider simulating transient failures

**Rationale**: Retries should be safe and not change semantic meaning of results.

---

### INV6: Error Transparency

**Property**: For any provider error, the abstraction layer must preserve enough information (error type, provider name, transient flag) for the application to make informed retry/fallback decisions.

**Validation**: Test error handling with various error scenarios

**Rationale**: Generic errors are not actionable; applications need context.

---

## MVP Scope

### In Scope for MVP

1. ✅ `LLMProvider` abstract interface
2. ✅ `OpenAIProvider` implementation
3. ✅ `LLMClient` facade with retry logic
4. ✅ `PromptManager` with YAML templates
5. ✅ `MockProvider` for testing
6. ✅ IntentClassifier migration to use LLMClient
7. ✅ Configuration-driven provider selection
8. ✅ Exception hierarchy
9. ✅ Unit tests using MockProvider
10. ✅ Integration test (skipped without API key)

### Out of Scope for MVP (Future)

1. ❌ `ToolRegistry` (stub only)
2. ❌ `AnthropicProvider` (stub only)
3. ❌ `MCPProvider` (stub only)
4. ❌ Streaming support (method exists but not implemented)
5. ❌ Embedding support
6. ❌ Caching layer
7. ❌ Cost tracking
8. ❌ A/B testing for prompts
9. ❌ Multi-model routing

---

## Dependencies

### New Dependencies

- `pyyaml ^6.0` - YAML parsing for prompt templates
- `openai ^1.0` - OpenAI API client (already exists)

### Testing Dependencies

- `pytest ^7.4` - Test framework (already exists)
- `pytest-mock ^3.12` - Mocking for unit tests (already exists)

### No Breaking Changes

- All existing dependencies remain
- No version upgrades required
- No new external services

---

## Success Criteria

### Functional Success

- [ ] All existing tests pass
- [ ] IntentClassifier uses LLMClient
- [ ] No direct OpenAI imports in application code
- [ ] Prompts stored in YAML files
- [ ] MockProvider works for testing
- [ ] Configuration-driven provider selection works

### Quality Success

- [ ] 100% code coverage for new code
- [ ] All unit tests use MockProvider
- [ ] Integration test exists (skipped without API key)
- [ ] All docstrings complete
- [ ] Type hints throughout
- [ ] Linting passes

### Performance Success

- [ ] Abstraction overhead <5ms
- [ ] Total request time within 10% of baseline
- [ ] Memory usage unchanged

---

## Future Enhancements

1. **ToolRegistry**: Function calling support
2. **AnthropicProvider**: Claude integration
3. **MCPProvider**: Model Context Protocol support
4. **Streaming**: Real-time response streaming
5. **Caching**: Response caching for identical requests
6. **Cost Tracking**: Token usage and cost monitoring
7. **Multi-Model Routing**: Automatic model selection based on complexity
