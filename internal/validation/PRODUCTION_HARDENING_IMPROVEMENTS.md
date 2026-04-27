# Production Hardening Improvements

**Status**: Architecture approved (9/10), ready for small production improvements
**Priority**: Implement before adding Anthropic provider
**Estimated Time**: 2-3 hours

---

## Current State

### Models (src/open_source_risk_model/llm/models.py)

```python
@dataclass
class CompletionRequest:
    messages: List[Message]
    model: str
    temperature: float = 0.0
    max_tokens: int = 500
    response_format: Optional[Literal["json"]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    prompt_name: Optional[str] = None
    # ❌ Missing: timeout_seconds
```

```python
@dataclass
class CompletionResponse:
    content: str
    model: str
    finish_reason: str
    usage: Dict[str, int]  # ⚠️ Can be None from some providers
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Any] = None
```

### Exceptions (src/open_source_risk_model/llm/exceptions.py)

```python
class ProviderError(LLMError):
    def __init__(
        self,
        message: str,
        provider: str,
        is_transient: bool = False,
        retry_after: Optional[int] = None  # ✅ Good
    ):
        ...
```

---

## Improvements

### 1. Add Timeout to CompletionRequest ⭐ HIGH PRIORITY

**Problem**: `timeout` is stored in LLMClient but never passed to providers.

**Fix**: Add `timeout_seconds` to CompletionRequest so providers can honor it consistently.

```python
@dataclass
class CompletionRequest:
    messages: List[Message]
    model: str
    temperature: float = 0.0
    max_tokens: int = 500
    response_format: Optional[Literal["json"]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    prompt_name: Optional[str] = None
    timeout_seconds: Optional[int] = None  # ✅ NEW
```

**Update LLMClient.complete()**:

```python
def complete(
    self,
    prompt_name: str,
    prompt_params: Dict[str, Any],
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 500,
    response_format: Optional[str] = None,
    timeout_seconds: Optional[int] = None  # ✅ NEW parameter
) -> CompletionResponse:
    # ... render prompt ...
    
    request = CompletionRequest(
        messages=messages,
        model=model or self._get_default_model(),
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        prompt_name=prompt_name,
        timeout_seconds=timeout_seconds or self.timeout  # ✅ Use provided or default
    )
    
    return self._execute_with_retry(request)
```

**Update OpenAIProvider.complete()**:

```python
def complete(self, request: CompletionRequest) -> CompletionResponse:
    try:
        response = self.client.chat.completions.create(
            model=request.model,
            messages=self._translate_messages(request.messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_format=self._translate_response_format(request.response_format),
            timeout=request.timeout_seconds or self.timeout  # ✅ Honor request timeout
        )
        # ...
```

**Benefits**:
- Consistent timeout behavior across providers
- Per-request timeout overrides
- Easier to test timeout scenarios

---

### 2. Add Jitter to Retry Backoff ⭐ HIGH PRIORITY

**Problem**: Exponential backoff without jitter can cause thundering herd under rate limits.

**Fix**: Add randomization to backoff delay.

```python
import random

def _execute_with_retry(self, request: CompletionRequest) -> CompletionResponse:
    # ... existing code ...
    
    # Calculate backoff delay with jitter
    base_delay = self.backoff_factor ** attempt
    if e.retry_after:
        base_delay = max(base_delay, e.retry_after)
    
    # Add jitter (±20%)
    delay = base_delay * random.uniform(0.8, 1.2)  # ✅ NEW
    
    logger.warning(
        f"Transient provider error, retrying in {delay:.2f}s: {e}",
        extra={
            "provider": self.provider.name,
            "attempt": attempt + 1,
            "delay": delay,
            "base_delay": base_delay  # ✅ Log both for debugging
        }
    )
    
    time.sleep(delay)
```

**Benefits**:
- Prevents thundering herd
- Better behavior under rate limits
- More resilient in production

---

### 3. Fix Logging Style 🔧 LOW PRIORITY

**Problem**: Unnecessary f-strings and unsafe dict access.

**Fix**: Clean up logging calls.

```python
# Before
logger.info(f"LLMClient initialized", extra={...})
tokens = response.usage.get("total_tokens", 0)

# After
logger.info("LLMClient initialized", extra={...})  # ✅ No f-string needed
tokens = (response.usage or {}).get("total_tokens", 0)  # ✅ Guard against None
```

**All logging fixes**:

```python
# In __init__
logger.info(
    "LLMClient initialized",  # ✅ No f-string
    extra={
        "provider": self.provider.name,
        "max_retries": self.max_retries,
        "timeout": self.timeout
    }
)

# In _execute_with_retry (success)
logger.info(
    "LLM request succeeded",  # ✅ No f-string
    extra={
        "provider": self.provider.name,
        "model": response.model,
        "tokens": (response.usage or {}).get("total_tokens", 0),  # ✅ Guard None
        "attempt": attempt + 1
    }
)

# In _execute_with_retry (error)
logger.error(
    f"Permanent provider error: {e}",  # ✅ f-string needed here
    extra={"provider": self.provider.name}
)
```

---

### 4. Standardize validate_config() Contract 🔧 MEDIUM PRIORITY

**Problem**: Signature is ambiguous (return bool OR raise exception).

**Fix**: Pick one convention and enforce consistently.

**Recommended: Option A (Fail Fast)**

```python
class LLMProvider(ABC):
    @abstractmethod
    def validate_config(self) -> None:  # ✅ Changed from bool
        """
        Validate that the provider is properly configured.
        
        This should check:
        - API keys are present
        - Credentials are valid (optional: can make test call)
        - Provider is reachable (optional)
        
        Returns:
            None: Configuration is valid
        
        Raises:
            ConfigurationError: If configuration is invalid (with reason)
        """
        pass
```

**Update OpenAIProvider**:

```python
def validate_config(self) -> None:  # ✅ Changed from bool
    """Validate OpenAI configuration."""
    if not self.api_key:
        raise ConfigurationError("OpenAI API key is required")
    
    # Optional: Make test call to verify credentials
    try:
        # Minimal test call
        self.client.models.list(timeout=5)
    except Exception as e:
        raise ConfigurationError(f"OpenAI API key validation failed: {e}")
    
    # ✅ No return needed (None is implicit)
```

**Update MockProvider**:

```python
def validate_config(self) -> None:  # ✅ Changed from bool
    """Mock provider is always valid."""
    pass  # ✅ No return needed
```

**Benefits**:
- Clear contract (raise on invalid, return on valid)
- Better error messages (exception includes reason)
- Consistent across all providers

---

### 5. Document Streaming Contract 📝 LOW PRIORITY

**Problem**: `stream()` signature is vague about what it returns.

**Fix**: Document expectations clearly (can implement later).

```python
class LLMProvider(ABC):
    @abstractmethod
    def stream(self, request: CompletionRequest) -> Iterator[str]:
        """
        Stream a completion (future enhancement).
        
        CURRENT BEHAVIOR (MVP):
        - Returns Iterator[str] of content chunks only
        - Each chunk is a string fragment of the completion
        - No metadata, tool calls, or usage info in stream
        
        FUTURE ENHANCEMENT:
        - May return Iterator[StreamEvent] for structured events
        - Would include: delta tokens, tool calls, usage updates
        - Required for tool calling / MCP integration
        
        Args:
            request: Standardized completion request
        
        Yields:
            str: Chunks of the completion content as they arrive
        
        Raises:
            ProviderError: If the provider API call fails
            NotImplementedError: If streaming not yet implemented (MVP)
        
        Example:
            >>> for chunk in provider.stream(request):
            ...     print(chunk, end="", flush=True)
        """
        pass
```

**Benefits**:
- Clear expectations for MVP
- Documented path for future enhancement
- Prevents confusion when implementing

---

### 6. Tighten Intent Allowlist Check ⭐ MEDIUM PRIORITY

**Problem**: LLM can output "unknown" and it passes allowlist validation.

**Fix**: Only allow "unknown" as fallback, not as LLM-selected intent.

```python
def classify(self, query: str) -> ClassificationResult:
    # ... call LLM ...
    
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
    
    # Validate intent is in allowlist (excluding UNKNOWN)
    allowed_intents = [e.value for e in IntentType if e != IntentType.UNKNOWN]  # ✅ NEW
    if result.intent not in allowed_intents:  # ✅ Changed
        logger.warning(f"Invalid intent from LLM: {result.intent}")
        return ClassificationResult(
            intent="unknown",
            parameters={},
            confidence=0.0,
            reasoning=f"Intent '{result.intent}' not in allowlist"
        )
    
    # ✅ If we reach here, intent is valid and confidence is high
    logger.info(
        "Classified query",
        extra={
            "query": query,
            "intent": result.intent,
            "confidence": result.confidence
        }
    )
    
    return result
```

**Benefits**:
- Stronger signal (LLM must pick real intent)
- "unknown" only used for our fallbacks
- Easier to debug classification issues

---

### 7. Add Per-Intent Parameter Schema Validation 🔧 MEDIUM PRIORITY

**Problem**: `parameters` dict is unbounded - LLM can return weird extra keys.

**Fix**: Add lightweight schema validation per intent.

```python
# Add to IntentClassifier class
INTENT_SCHEMAS = {
    "list_dependencies": {
        "required": ["repo_full_name"],
        "optional": ["dependency_group"],
        "types": {
            "repo_full_name": str,
            "dependency_group": str
        }
    },
    "find_dependents": {
        "required": ["package_name"],
        "optional": ["registry_type"],
        "types": {
            "package_name": str,
            "registry_type": str
        }
    },
    "get_dependency_tree": {
        "required": ["repo_full_name"],
        "optional": ["max_depth"],
        "types": {
            "repo_full_name": str,
            "max_depth": int
        }
    },
    # ... other intents ...
}

def _validate_parameters(
    self,
    intent: str,
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate parameters against intent schema.
    
    Args:
        intent: The classified intent
        parameters: Parameters extracted by LLM
    
    Returns:
        Dict[str, Any]: Validated parameters (extra keys removed)
    
    Raises:
        ValidationError: If required parameters missing or wrong type
    """
    if intent not in self.INTENT_SCHEMAS:
        # No schema defined, return as-is
        return parameters
    
    schema = self.INTENT_SCHEMAS[intent]
    validated = {}
    
    # Check required parameters
    for param in schema["required"]:
        if param not in parameters:
            raise ValidationError(
                f"Missing required parameter '{param}' for intent '{intent}'"
            )
        
        # Type check
        expected_type = schema["types"].get(param)
        if expected_type and not isinstance(parameters[param], expected_type):
            raise ValidationError(
                f"Parameter '{param}' must be {expected_type.__name__}, "
                f"got {type(parameters[param]).__name__}"
            )
        
        validated[param] = parameters[param]
    
    # Check optional parameters
    for param in schema.get("optional", []):
        if param in parameters:
            # Type check
            expected_type = schema["types"].get(param)
            if expected_type and not isinstance(parameters[param], expected_type):
                logger.warning(
                    f"Optional parameter '{param}' has wrong type, skipping",
                    extra={"intent": intent, "param": param}
                )
                continue
            
            validated[param] = parameters[param]
    
    # Log if extra parameters were provided
    extra_params = set(parameters.keys()) - set(validated.keys())
    if extra_params:
        logger.warning(
            f"Extra parameters ignored: {extra_params}",
            extra={"intent": intent}
        )
    
    return validated
```

**Use in classify()**:

```python
def classify(self, query: str) -> ClassificationResult:
    # ... existing code ...
    
    result = self._parse_response(response.content)
    
    # ... confidence and allowlist checks ...
    
    # Validate parameters against schema
    try:
        validated_params = self._validate_parameters(result.intent, result.parameters)
        result.parameters = validated_params  # ✅ Use validated params
    except ValidationError as e:
        logger.error(f"Parameter validation failed: {e}")
        return ClassificationResult(
            intent="unknown",
            parameters={},
            confidence=0.0,
            reasoning=f"Parameter validation failed: {e}"
        )
    
    logger.info(
        "Classified query",
        extra={
            "query": query,
            "intent": result.intent,
            "confidence": result.confidence
        }
    )
    
    return result
```

**Benefits**:
- Prevents weird parameters from breaking executors
- Type safety for parameters
- Clear error messages
- Removes unexpected keys

---

## Implementation Priority

### Before Adding Anthropic (Must Do)

1. ✅ **Add timeout to CompletionRequest** - Critical for consistent behavior
2. ✅ **Add jitter to retry backoff** - Prevents thundering herd
3. ✅ **Standardize validate_config()** - Consistent error handling

### Before Production (Should Do)

4. ✅ **Tighten intent allowlist** - Better classification signal
5. ✅ **Add parameter schema validation** - Prevents executor errors
6. ✅ **Fix logging style** - Code quality

### Nice to Have (Can Wait)

7. ✅ **Document streaming contract** - Future-proofing

---

## Testing Strategy

### For Each Improvement

1. **Update unit tests** to cover new behavior
2. **Update integration tests** if needed
3. **Run full test suite** to ensure no regressions
4. **Update documentation** to reflect changes

### Specific Tests Needed

**Timeout**:
- Test timeout is passed to provider
- Test timeout override works
- Test default timeout is used when not specified

**Jitter**:
- Test retry delays have randomization
- Test jitter range is correct (±20%)
- Test base delay is logged

**validate_config()**:
- Test raises ConfigurationError on invalid
- Test returns None on valid
- Test error messages are clear

**Intent allowlist**:
- Test LLM cannot output "unknown" directly
- Test "unknown" only from our fallbacks
- Test all valid intents still work

**Parameter validation**:
- Test required parameters enforced
- Test optional parameters allowed
- Test extra parameters removed
- Test type checking works
- Test error messages are clear

---

## Estimated Impact

### Code Changes
- **Files to modify**: 4
  - `src/open_source_risk_model/llm/models.py`
  - `src/open_source_risk_model/llm/client.py`
  - `src/open_source_risk_model/llm/providers/base.py`
  - `src/open_source_risk_model/query/intent_classifier.py`

- **Tests to update**: ~10 test files
- **New tests to add**: ~15 test cases

### Time Estimate
- Implementation: 2-3 hours
- Testing: 1-2 hours
- Documentation: 30 minutes
- **Total**: 3.5-5.5 hours

### Risk
- **Low**: All changes are additive or refinements
- **No breaking changes** to existing API
- **Backward compatible** (timeout is optional)

---

## Next Steps

1. **Validate MVP first** (don't implement improvements yet)
2. **If validation passes**, implement improvements in this order:
   - Timeout (30 min)
   - Jitter (15 min)
   - validate_config() (30 min)
   - Intent allowlist (15 min)
   - Parameter validation (1 hour)
   - Logging fixes (15 min)
   - Streaming docs (15 min)
3. **Run full test suite** after each change
4. **Then add Anthropic provider** with confidence

---

## Summary

These improvements make the architecture "production-proof":

✅ **Timeout enforcement** - Consistent behavior across providers
✅ **Retry jitter** - Better resilience under load
✅ **Clear contracts** - validate_config() is unambiguous
✅ **Stronger validation** - Intent allowlist and parameter schemas
✅ **Better logging** - Clean style and safe dict access
✅ **Future-ready** - Streaming contract documented

**Architecture remains 9/10**, these just make it bulletproof for production.
