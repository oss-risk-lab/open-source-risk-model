# LLM Provider Abstraction - Spec Review Complete

## Status: ✅ Ready to Implement (with updates)

Your feedback identified 7 critical issues that would have caused problems during implementation. All have been addressed.

## Critical Issues Fixed

### 1. ✅ OpenAI API Surface
- **Issue**: Tasks referenced generic "Chat Completions API"
- **Fix**: Confirmed existing pattern uses `client.chat.completions.create()` (OpenAI SDK v1.0+)
- **Action**: Updated Task 4.1 to match exact existing pattern

### 2. ✅ response_format Precision
- **Issue**: Vague `Dict[str, str]` type, unclear provider mapping
- **Fix**: Changed to `Literal["json"]` with provider-specific mapping
- **Action**: OpenAIProvider maps "json" → `{"type": "json_object"}` + validates response

### 3. ✅ Prompt Placeholder Validation
- **Issue**: Naive `assert "{" not in rendered` causes false positives
- **Fix**: Regex-based validation `r'\{[a-zA-Z_][a-zA-Z0-9_]*\}'`
- **Action**: Updated PromptManager to validate before and after rendering

### 4. ✅ MockProvider Keying
- **Issue**: Keying on "first 50 chars" is fragile
- **Fix**: Added `prompt_name` field to CompletionRequest
- **Action**: MockProvider keys on prompt_name, fallback to content hash

### 5. ✅ Config: YAML vs Env
- **Issue**: Requirements mentioned YAML but tasks only had env
- **Fix**: Clarified MVP is env-only, YAML is post-MVP
- **Action**: Updated FR7 and removed YAML from Phase 7

### 6. ✅ validate_config() Network Calls
- **Issue**: Unit tests shouldn't require network
- **Fix**: Fast-fail validation (API key format check only)
- **Action**: Network connectivity test moved to integration tests

### 7. ✅ Performance NFRs
- **Issue**: "<5ms overhead" hard to measure in CI
- **Fix**: Practical criteria (no extra DB calls, no extra serialization)
- **Action**: Updated NFR2 with measurable acceptance criteria

### 8. ✅ Phase 0 Added
- **Issue**: No pre-implementation sanity check
- **Fix**: Added Phase 0 to document existing integration
- **Action**: Prevents "wrong SDK surface" problem

## Files Created

1. **SPEC_UPDATES.md** - Detailed updates for all 8 issues
2. **SPEC_REVIEW_COMPLETE.md** - This summary

## Key Changes to Apply

### CompletionRequest Model
```python
@dataclass
class CompletionRequest:
    messages: List[Message]
    model: str
    temperature: float = 0.0
    max_tokens: int = 500
    response_format: Optional[Literal["json"]] = None  # NEW: Simplified
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    prompt_name: Optional[str] = None  # NEW: For MockProvider routing
```

### OpenAIProvider Pattern
```python
# Map response_format
if request.response_format == "json":
    openai_response_format = {"type": "json_object"}

# Validate JSON response
if request.response_format == "json":
    json.loads(response.choices[0].message.content)  # Raises if invalid
```

### MockProvider Keying
```python
def complete(self, request: CompletionRequest) -> CompletionResponse:
    # Use prompt_name for stable keying
    key = request.prompt_name or self._hash_content(request)
    content = self.canned_responses.get(key, default_response)
    ...
```

### PromptManager Validation
```python
# Regex check for unresolved placeholders
unresolved_pattern = r'\{[a-zA-Z_][a-zA-Z0-9_]*\}'
if re.findall(unresolved_pattern, rendered_text):
    raise TemplateRenderError("Unresolved placeholders found")
```

## Dependencies to Add

```toml
# pyproject.toml
dependencies = [
    # ... existing ...
    "openai>=1.0.0",  # NEW
]
```

## Implementation Checklist

Before starting implementation:
- [ ] Read SPEC_UPDATES.md for detailed changes
- [ ] Add `openai>=1.0.0` to pyproject.toml
- [ ] Run Phase 0 sanity check (already done via code review)
- [ ] Apply model changes (prompt_name, response_format)
- [ ] Follow updated tasks.md sequentially

## What's Solid

✅ MVP scope boundaries clear (ToolRegistry/MCP/Anthropic out)
✅ Concrete file paths + acceptance criteria
✅ MockProvider-first testing strategy
✅ Integration tests gated by OPENAI_API_KEY
✅ "Provider imports only in providers/" invariant maintained
✅ Matches existing OpenAI integration pattern
✅ Practical, measurable acceptance criteria

## Next Steps

1. Review SPEC_UPDATES.md for implementation details
2. Start with Phase 0 (sanity check) - already done
3. Apply model updates (Task 1.2)
4. Follow tasks.md sequentially with updates applied
5. All critical issues are now addressed

---

**Spec is implementation-ready!** All feedback incorporated.
