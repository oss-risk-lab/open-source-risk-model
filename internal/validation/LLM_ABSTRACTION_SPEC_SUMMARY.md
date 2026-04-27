# LLM Provider Abstraction - Spec Summary

## Status

- **Spec Type**: Feature (Design-First Workflow)
- **Phase**: Requirements and Tasks Complete
- **Ready to Implement**: ✅ Yes
- **Estimated Time**: 12-14 hours

## Files Created

1. `.kiro/specs/llm-provider-abstraction/design.md` - Complete technical design
2. `.kiro/specs/llm-provider-abstraction/requirements.md` - Functional and non-functional requirements
3. `.kiro/specs/llm-provider-abstraction/tasks.md` - Concrete implementation tasks

## MVP Scope

### In Scope ✅
- `LLMProvider` abstract interface
- `OpenAIProvider` implementation
- `LLMClient` facade with retry logic
- `PromptManager` with YAML templates
- `MockProvider` for testing
- IntentClassifier migration
- Configuration-driven provider selection
- Exception hierarchy
- Unit tests (no API keys required)
- Integration test (skipped without API key)

### Out of Scope ❌
- `ToolRegistry` (stub only)
- `AnthropicProvider` (stub only)
- `MCPProvider` (stub only)
- Streaming support
- Caching layer
- Cost tracking

## Key Requirements

### Functional
1. **Provider Abstraction**: No provider-specific imports in application code
2. **OpenAI Provider**: Wraps OpenAI API with standardized interface
3. **LLMClient Facade**: Unified interface with retry logic
4. **Prompt Management**: YAML-based templates with parameter substitution
5. **Mock Provider**: Testing without API calls
6. **IntentClassifier Migration**: Use LLMClient instead of direct OpenAI
7. **Configuration**: Environment variable driven (LLM_PROVIDER=openai)
8. **Error Handling**: Transparent errors with retry context

### Non-Functional
1. **Backward Compatibility**: All existing tests pass
2. **Performance**: <5ms abstraction overhead
3. **Testability**: 100% unit tests use MockProvider
4. **Maintainability**: Comprehensive docs and type hints

## Implementation Phases

1. **Phase 1**: Scaffold and Core Models (1 hour)
2. **Phase 2**: Provider Interface (30 min)
3. **Phase 3**: PromptManager (1.5 hours)
4. **Phase 4**: OpenAIProvider (2 hours)
5. **Phase 5**: MockProvider (1 hour)
6. **Phase 6**: LLMClient (2 hours)
7. **Phase 7**: Configuration/Factory (1 hour)
8. **Phase 8**: IntentClassifier Migration (2 hours)
9. **Phase 9**: Integration Tests (1 hour)
10. **Phase 10**: Documentation (1 hour)
11. **Phase 11**: Future Stubs (30 min)

## Acceptance Criteria

### Must Have
- [ ] All existing tests pass without modification
- [ ] IntentClassifier uses LLMClient (no direct OpenAI imports)
- [ ] Unit tests work without API keys (use MockProvider)
- [ ] Integration test exists (skipped without OPENAI_API_KEY)
- [ ] Provider selection via LLM_PROVIDER environment variable
- [ ] Prompts stored in YAML files
- [ ] Code coverage >90% for new code

### Verification Commands

```bash
# Verify no provider imports in application code
grep -r "import openai" src/open_source_risk_model/query/  # Should be empty

# Run unit tests (no API key required)
pytest -m "not integration" -v

# Run with coverage
pytest -m "not integration" --cov=src/open_source_risk_model/llm

# Run integration tests (requires API key)
OPENAI_API_KEY=sk-... pytest -m integration -v
```

## Key Invariants

1. **Provider Abstraction**: Application code never imports provider-specific libraries
2. **Request/Response Standardization**: All providers return CompletionResponse
3. **Prompt Completeness**: No unresolved placeholders in rendered prompts
4. **Configuration Validation**: validate_config() returns true iff provider works
5. **Retry Idempotency**: Retries produce equivalent results (temperature=0)
6. **Error Transparency**: Errors include context for retry decisions

## File Structure

```
src/open_source_risk_model/llm/
├── __init__.py                      # Public API exports
├── client.py                        # LLMClient facade
├── prompt_manager.py                # PromptManager
├── tool_registry.py                 # ToolRegistry (stub)
├── factory.py                       # Provider factory
├── exceptions.py                    # Error hierarchy
├── models.py                        # Data models
├── providers/
│   ├── __init__.py
│   ├── base.py                      # LLMProvider interface
│   ├── openai_provider.py           # OpenAI implementation
│   ├── anthropic_provider.py        # Stub
│   ├── mcp_provider.py              # Stub
│   └── mock_provider.py             # Mock for testing
└── prompts/
    └── intent_classification.yaml   # Intent prompt

test/llm/
├── test_client.py
├── test_prompt_manager.py
├── test_openai_provider.py
├── test_mock_provider.py
├── test_factory.py
└── test_integration.py
```

## Dependencies

### New
- `pyyaml ^6.0` - YAML parsing for prompts

### Existing
- `openai ^1.0` - OpenAI API client
- `pytest ^7.4` - Testing framework
- `pytest-mock ^3.12` - Mocking

## Next Steps

1. Review requirements.md and tasks.md
2. Start with Phase 1 (Scaffold)
3. Follow tasks.md sequentially
4. Verify each phase checkpoint before proceeding
5. Run full test suite at end

## Notes

- MVP focuses on OpenAI provider only
- Future providers (Anthropic, MCP) are stubs
- ToolRegistry is stub (function calling future)
- Streaming support not implemented (stub exists)
- All unit tests must use MockProvider
- Integration tests skipped without API key
- Maintain current behavior (temperature=0, strict JSON)

---

**Ready to implement!** Start with Phase 1 in tasks.md.
