# Spec Updates Based on Feedback

## Critical Updates to Apply Before Implementation

### 1. OpenAI API Surface (Task 4.1)

**Issue**: Tasks reference "Chat Completions API" but need to match existing repo pattern.

**Current State** (from code review):
- Uses `openai.OpenAI(api_key=...)` client (OpenAI SDK v1.0+)
- Uses Chat Completions API: `client.chat.completions.create()`
- JSON mode: `response_format={"type": "json_object"}`
- Model: `gpt-4` (default)
- Temperature: `0.0`
- Max tokens: `500`

**Action**: Update Task 4.1
- Change "Call OpenAI Chat Completions API" → "Call OpenAI via existing SDK pattern (client.chat.completions.create)"
- Match exact API surface currently in IntentClassifier
- No migration needed - already using modern SDK

**Updated Task 4.1 Text**:
```
Create OpenAIProvider that wraps the existing OpenAI SDK pattern:
- Uses openai.OpenAI(api_key=...) client
- Calls client.chat.completions.create()
- Matches current IntentClassifier implementation exactly
- No SDK migration required
```

---

### 2. response_format Precision (Models + OpenAIProvider)

**Issue**: `response_format` type is too vague and needs provider-specific mapping.

**Current State**:
- IntentClassifier uses: `response_format={"type": "json_object"}`
- This is OpenAI-specific format

**Action**: Update CompletionRequest model
```python
@dataclass
class CompletionRequest:
    messages: List[Message]
    model: str
    temperature: float = 0.0
    max_tokens: int = 500
    response_format: Optional[Literal["json"]] = None  # Simplified API
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    prompt_name: Optional[str] = None  # NEW: For MockProvider routing
```

**Action**: Update OpenAIProvider to map response_format
```python
def complete(self, request: CompletionRequest) -> CompletionResponse:
    # Map simplified format to OpenAI format
    openai_response_format = None
    if request.response_format == "json":
        openai_response_format = {"type": "json_object"}
    
    response = self.client.chat.completions.create(
        model=request.model,
        messages=[...],
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        response_format=openai_response_format
    )
    
    # Validate JSON response
    if request.response_format == "json":
        try:
            json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            raise ValidationError("Response is not valid JSON")
    
    return CompletionResponse(...)
```

**Action**: Add JSON validation in OpenAIProvider
- After getting response, if `response_format="json"`, validate it's valid JSON
- Raise `ValidationError` if not valid JSON
- Check for required keys (intent, parameters, confidence) in IntentClassifier context

---

### 3. Prompt Placeholder Validation (PromptManager)

**Issue**: Current invariant check `assert "{" not in rendered` is too naive.

**Problem**:
- False positives on legitimate braces (JSON examples, etc.)
- False negatives on some edge cases

**Action**: Update PromptManager validation

**Better Approach 1** (Recommended): Validate before rendering
```python
def render(self, prompt_name: str, params: Dict[str, Any]) -> Dict[str, str]:
    """Render prompt with parameter validation."""
    if prompt_name not in self.prompts:
        raise PromptNotFoundError(f"Prompt '{prompt_name}' not found")
    
    prompt = self.prompts[prompt_name]
    required_params = prompt.get("required_params", [])
    
    # Validate all required params present
    missing = [p for p in required_params if p not in params]
    if missing:
        raise TemplateRenderError(f"Missing required parameters: {missing}")
    
    # Render templates
    try:
        system = prompt["system_template"].format(**params)
        user = prompt["user_template"].format(**params)
    except KeyError as e:
        raise TemplateRenderError(f"Missing parameter in template: {e}")
    
    # Validate no unresolved placeholders (regex check)
    import re
    unresolved_pattern = r'\{[a-zA-Z_][a-zA-Z0-9_]*\}'
    
    system_unresolved = re.findall(unresolved_pattern, system)
    user_unresolved = re.findall(unresolved_pattern, user)
    
    if system_unresolved or user_unresolved:
        raise TemplateRenderError(
            f"Unresolved placeholders found: {system_unresolved + user_unresolved}"
        )
    
    return {"system": system, "user": user}
```

**Update INV3 in requirements.md**:
```
Property: For any prompt template, rendering with all required parameters must 
produce a valid prompt with no unresolved placeholders matching pattern {variable_name}.

Validation: Regex check for r'\{[a-zA-Z_][a-zA-Z0-9_]*\}' after rendering

Rationale: Unresolved placeholders will confuse the LLM. Regex avoids false 
positives on legitimate braces (JSON, escaped braces, etc.)
```

---

### 4. MockProvider Keying Strategy (MockProvider + CompletionRequest)

**Issue**: Keying on "first 50 chars of system message" is fragile.

**Problem**:
- Breaks on prompt changes (whitespace, versioning, etc.)
- Hard to maintain tests

**Action**: Add `prompt_name` to CompletionRequest (already done above)

**Action**: Update MockProvider to key on prompt_name
```python
class MockProvider(LLMProvider):
    """Mock provider for testing without API calls."""
    
    def __init__(self, canned_responses: Dict[str, str]):
        """
        Initialize with canned responses.
        
        Args:
            canned_responses: Dict mapping prompt_name to response JSON
        """
        self.canned_responses = canned_responses
    
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return canned response based on prompt_name."""
        # Use prompt_name if available, fallback to content hash
        key = request.prompt_name or self._hash_content(request)
        
        content = self.canned_responses.get(
            key,
            '{"intent": "unknown", "parameters": {}, "confidence": 0.0}'
        )
        
        return CompletionResponse(
            content=content,
            model="mock-model",
            finish_reason="stop",
            usage={"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50}
        )
    
    def _hash_content(self, request: CompletionRequest) -> str:
        """Generate stable hash from request content."""
        import hashlib
        content = "".join(m.content for m in request.messages)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
```

**Action**: Update LLMClient to set prompt_name
```python
def complete(
    self,
    prompt_name: str,
    prompt_params: Dict[str, Any],
    ...
) -> CompletionResponse:
    """Generate completion with prompt_name set."""
    rendered = self.prompt_manager.render(prompt_name, prompt_params)
    
    request = CompletionRequest(
        messages=[...],
        model=model or self.provider.supported_models[0],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        prompt_name=prompt_name  # Set for MockProvider routing
    )
    
    return self._execute_with_retry(request)
```

**Action**: Update test examples
```python
def test_classify_list_dependencies():
    # Setup mock with prompt_name keying
    mock_provider = MockProvider({
        "intent_classification": '{"intent": "list_dependencies", "parameters": {"repo_full_name": "django/django"}, "confidence": 0.95}'
    })
    
    prompt_manager = PromptManager(Path("src/open_source_risk_model/llm/prompts"))
    client = LLMClient(mock_provider, prompt_manager)
    classifier = IntentClassifier(client)
    
    result = classifier.classify("What are the dependencies of django/django?")
    assert result.intent == "list_dependencies"
```

---

### 5. Configuration: YAML vs Env-Only (FR7 + Tasks)

**Issue**: Requirements mention `config/llm_config.yaml` but tasks only implement env factory.

**Decision**: Keep MVP env-only, YAML config is post-MVP.

**Action**: Update FR7 in requirements.md
```
FR7: Configuration-Driven Provider Selection

Requirement: Select LLM provider via environment variables (MVP).

Details:
- Environment variable `LLM_PROVIDER` (default: "openai")
- Environment variable `OPENAI_API_KEY` (required for OpenAI)
- Optional: `OPENAI_BASE_URL`, `OPENAI_ORGANIZATION`
- Provider factory pattern for instantiation
- No provider-specific imports outside `llm/providers/` directory

MVP Scope: Environment variables only
Post-MVP: YAML configuration file support

Acceptance Criteria:
- `create_provider_from_env()` creates provider from environment variables
- `LLM_PROVIDER=openai` works by default
- Provider-specific code isolated in `llm/providers/` directory
- Application code never imports `openai`, `anthropic`, etc. directly
```

**Action**: Remove YAML config references from Phase 7 tasks

---

### 6. validate_config() Network Calls (OpenAIProvider + Tests)

**Issue**: `validate_config()` should not require network calls in unit tests.

**Action**: Update OpenAIProvider.validate_config()
```python
def validate_config(self) -> bool:
    """
    Validate provider configuration.
    
    Fast-fail checks:
    - API key is present
    - API key format is valid (starts with 'sk-')
    
    Does NOT make network calls (use integration tests for that).
    
    Returns:
        True if configuration appears valid
        
    Raises:
        ConfigurationError: If configuration is invalid
    """
    if not self.api_key:
        raise ConfigurationError("OpenAI API key is required")
    
    if not self.api_key.startswith("sk-"):
        raise ConfigurationError("OpenAI API key must start with 'sk-'")
    
    return True
```

**Action**: Add integration test for actual API connectivity
```python
@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="No API key")
def test_openai_provider_connectivity():
    """Test actual OpenAI API connectivity."""
    provider = create_provider_from_env()
    
    # Make a minimal API call to verify connectivity
    request = CompletionRequest(
        messages=[Message(role=MessageRole.USER, content="test")],
        model="gpt-4",
        max_tokens=5
    )
    
    response = provider.complete(request)
    assert response.content
    assert response.usage["total_tokens"] > 0
```

---

### 7. Performance NFRs (NFR2)

**Issue**: "Overhead <5ms" and "within 10% baseline" are hard to measure in CI.

**Action**: Update NFR2 to be more practical
```
NFR2: Performance

Requirement: Abstraction layer adds minimal overhead.

Details:
- No additional database calls
- No extra serialization loops beyond provider requirements
- No logging of full prompts by default (only metadata)
- Request/response translation is in-memory only
- Retry logic uses exponential backoff (not busy-wait)

Acceptance Criteria:
- No database calls in abstraction layer
- No unnecessary JSON serialization (only what provider requires)
- Logging uses DEBUG level for full content, INFO for metadata only
- Memory usage: No large object copies
- Optional: Micro-benchmark script for overhead measurement (not gating CI)

Performance Targets (informational, not gating):
- Abstraction overhead: <5ms per request
- Total request time: Within 10% of direct OpenAI calls
```

**Action**: Add optional micro-benchmark script (not in MVP tasks)
```python
# scripts/benchmark_llm_overhead.py
"""
Optional micro-benchmark for LLM abstraction overhead.
Not required for CI, just for performance validation.
"""
import time
from open_source_risk_model.llm import create_provider_from_env, LLMClient, PromptManager

def benchmark_overhead():
    # Measure direct OpenAI call
    # Measure via abstraction layer
    # Report difference
    pass
```

---

### 8. Add openai to pyproject.toml

**Issue**: `openai` is not in dependencies yet.

**Action**: Add to Phase 1, Task 1.1
```
**Additional Setup**:
Add openai to pyproject.toml dependencies:

```toml
dependencies = [
    "requests",
    "fastapi",
    "uvicorn",
    "pyyaml",
    "python-dotenv",
    "packaging",
    "tomli; python_version < '3.11'",
    "openai>=1.0.0",  # NEW: LLM provider abstraction
]
```

Then run:
```bash
pip install -e .
```
```

---

## Summary of Changes

### Models (Task 1.2)
- ✅ Add `prompt_name: Optional[str]` to CompletionRequest
- ✅ Change `response_format` to `Optional[Literal["json"]]`

### OpenAIProvider (Task 4.1)
- ✅ Match existing SDK pattern (client.chat.completions.create)
- ✅ Map `response_format="json"` to `{"type": "json_object"}`
- ✅ Add JSON validation after response
- ✅ Fast-fail validate_config() (no network calls)

### PromptManager (Task 3.1)
- ✅ Use regex for unresolved placeholder detection
- ✅ Validate required params before rendering
- ✅ Better error messages

### MockProvider (Task 5.1)
- ✅ Key on `request.prompt_name` instead of content hash
- ✅ Fallback to content hash if prompt_name not set
- ✅ More stable test behavior

### LLMClient (Task 6.1)
- ✅ Set `prompt_name` in CompletionRequest
- ✅ Pass through to provider

### Configuration (Task 7.1)
- ✅ Remove YAML config from MVP
- ✅ Env-only for MVP
- ✅ Update requirements.md

### Performance (NFR2)
- ✅ More practical acceptance criteria
- ✅ Remove hard-to-measure metrics from gating
- ✅ Optional benchmark script

### Dependencies
- ✅ Add `openai>=1.0.0` to pyproject.toml

---

## Implementation Order

1. Apply Phase 0 (sanity check) - DONE via code review
2. Update models with prompt_name and response_format
3. Implement PromptManager with better validation
4. Implement OpenAIProvider matching existing pattern
5. Implement MockProvider with prompt_name keying
6. Implement LLMClient setting prompt_name
7. Update all tests to use new patterns
8. Add integration test for connectivity
9. Update documentation

---

## Files to Update

1. `.kiro/specs/llm-provider-abstraction/requirements.md`
   - Update FR7 (remove YAML config from MVP)
   - Update NFR2 (practical performance criteria)
   - Update INV3 (regex-based placeholder validation)

2. `.kiro/specs/llm-provider-abstraction/tasks.md`
   - Add Phase 0 (sanity check)
   - Update Task 1.2 (models with prompt_name)
   - Update Task 3.1 (PromptManager validation)
   - Update Task 4.1 (OpenAIProvider matching existing pattern)
   - Update Task 5.1 (MockProvider keying)
   - Update Task 6.1 (LLMClient setting prompt_name)
   - Update Task 7.1 (remove YAML config)

3. `pyproject.toml`
   - Add `openai>=1.0.0` to dependencies

---

## Ready to Implement

All critical issues addressed. Spec is now implementation-ready with:
- ✅ Matches existing OpenAI integration pattern
- ✅ Precise response_format handling
- ✅ Robust placeholder validation
- ✅ Stable MockProvider keying
- ✅ Practical performance criteria
- ✅ Clear MVP scope (env-only config)
- ✅ Fast validate_config() for unit tests
- ✅ Dependencies specified
