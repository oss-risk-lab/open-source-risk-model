# OpenAI Integration Findings - Task 0.1

**Date**: 2024-02-13  
**Task**: Phase 0, Task 0.1 - Identify Existing OpenAI Integration  
**Status**: ✅ Complete

---

## Executive Summary

The codebase currently uses OpenAI's Chat Completions API directly in the `IntentClassifier` class. The OpenAI SDK is **not yet listed as a dependency** in `pyproject.toml` or `requirements.txt`, but is imported dynamically at runtime. The integration is minimal, focused, and well-structured for migration to the abstraction layer.

---

## Current OpenAI SDK Status

### Dependency Management
- **Status**: ❌ **NOT in pyproject.toml dependencies**
- **Status**: ❌ **NOT in requirements.txt**
- **Import Method**: Dynamic import (`import openai` inside `_call_llm()` method)
- **Recommended Version**: `openai>=1.0.0` (based on API usage pattern)

**Action Required**: Add to `pyproject.toml`:
```toml
dependencies = [
    # ... existing dependencies ...
    "openai>=1.0.0",
]
```

---

## Current Integration Pattern

### Location
- **Primary File**: `src/open_source_risk_model/query/intent_classifier.py`
- **Class**: `IntentClassifier`
- **Method**: `_call_llm(prompt: str) -> str`

### API Surface

**Client Initialization**:
```python
import openai
client = openai.OpenAI(api_key=self.api_key)
```

**API Call Pattern**:
```python
response = client.chat.completions.create(
    model=self.model,
    messages=[
        {
            "role": "system",
            "content": "You are a precise query classifier. Return only valid JSON."
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0.0,
    max_tokens=500,
    response_format={"type": "json_object"}
)

return response.choices[0].message.content
```

---

## Configuration Details

### Model Settings
| Parameter | Value | Purpose |
|-----------|-------|---------|
| **model** | `"gpt-4"` (default) | Configurable via constructor |
| **temperature** | `0.0` | Deterministic output for classification |
| **max_tokens** | `500` | Sufficient for JSON response |
| **response_format** | `{"type": "json_object"}` | Forces JSON output (OpenAI JSON mode) |

### Message Structure
- **System Message**: `"You are a precise query classifier. Return only valid JSON."`
- **User Message**: Contains full prompt with:
  - Available intents (11 predefined intents)
  - Intent descriptions and examples
  - Parameter extraction rules
  - JSON schema specification
  - User query to classify

### API Key Management
- **Source**: Constructor parameter or `OPENAI_API_KEY` environment variable
- **Validation**: Checked at initialization, warning logged if missing
- **Error Handling**: Raises `ValueError` if missing when `classify()` is called

---

## Current Usage in IntentClassifier

### Class Structure
```python
class IntentClassifier:
    CONFIDENCE_THRESHOLD = 0.7
    
    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
    
    def classify(self, query: str) -> ClassificationResult:
        # 1. Build prompt with strict JSON schema
        prompt = self._build_prompt(query)
        
        # 2. Call LLM
        response = self._call_llm(prompt)
        
        # 3. Parse and validate response
        result = self._parse_response(response)
        
        # 4. Validate confidence threshold
        # 5. Validate intent is in allowlist
        
        return result
```

### Prompt Construction
- **Method**: `_build_prompt(query: str) -> str`
- **Content**: 
  - Hardcoded prompt template with 11 intent descriptions
  - Examples for each intent
  - Strict JSON schema specification
  - Classification rules
- **Size**: ~200 lines of formatted text

### Response Parsing
- **Method**: `_parse_response(response: str) -> ClassificationResult`
- **Expected Format**:
```json
{
  "intent": "<intent_name>",
  "parameters": {"param1": "value1"},
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}
```
- **Validation**:
  - Required fields: `intent`, `parameters`, `confidence`
  - Type checking for each field
  - Confidence range validation (0.0-1.0)
  - Intent allowlist validation

---

## Error Handling

### Current Error Handling in `_call_llm()`
```python
try:
    import openai
    client = openai.OpenAI(api_key=self.api_key)
    response = client.chat.completions.create(...)
    return response.choices[0].message.content

except ImportError:
    raise ValueError("openai package not installed. Run: pip install openai")
except Exception as e:
    raise ValueError(f"LLM API call failed: {e}")
```

### Error Types
- **ImportError**: OpenAI package not installed
- **Generic Exception**: Catches all API errors (auth, rate limit, network, etc.)
- **No Specific Handling**: Does not distinguish between transient and permanent errors

---

## Testing Approach

### Test File
- **Location**: `test/test_intent_classifier.py`
- **Strategy**: Mix of real API calls and mocked calls

### Test Categories

**1. Real API Tests** (skipped without API key):
```python
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
def test_list_dependencies_classification(classifier):
    result = classifier.classify("What are the dependencies of django/django?")
    assert result.intent == "list_dependencies"
```

**2. Mocked Tests**:
```python
def test_extract_repo_name(mock_classifier):
    mock_response = {
        "intent": "list_dependencies",
        "parameters": {"repo_full_name": "django/django"},
        "confidence": 0.95
    }
    
    with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
        result = mock_classifier.classify("What are the dependencies of django/django?")
        assert result.parameters["repo_full_name"] == "django/django"
```

### Test Coverage
- Classification accuracy for each intent type
- Parameter extraction
- Confidence thresholding
- Invalid intent handling
- JSON schema validation
- Error handling

---

## Environment Configuration

### .env.example
```bash
# OpenAI API Key (optional - only needed for natural language queries)
# Required for: POST /api/query with natural language (without explicit intent)
# Get your API key at: https://platform.openai.com/api-keys
# If not set, you can still use dev mode by providing explicit intent + parameters
# OPENAI_API_KEY=sk-...
```

### Configuration Notes
- API key is **optional** for the application
- Only required for natural language query classification
- Application can work without it using explicit intent + parameters
- No other OpenAI configuration options exposed

---

## Migration Implications

### What Needs to Change
1. **Add OpenAI SDK to dependencies** (`pyproject.toml`)
2. **Move OpenAI client creation** to `OpenAIProvider`
3. **Extract prompt template** to YAML file (`intent_classification.yaml`)
4. **Replace `_call_llm()` method** with `LLMClient.complete()`
5. **Update constructor** to accept `LLMClient` instead of API key
6. **Update all instantiation sites** to use factory pattern
7. **Update tests** to use `MockProvider` instead of mocking OpenAI directly

### What Stays the Same
- Classification logic and validation
- Confidence thresholding (0.7)
- Intent allowlist validation
- JSON schema validation
- Response parsing logic
- `ClassificationResult` dataclass
- Public API (`classify()` method signature can remain similar)

### Compatibility Considerations
- **JSON Mode**: OpenAI's `response_format={"type": "json_object"}` must be preserved
- **Temperature**: Must remain 0.0 for deterministic classification
- **Max Tokens**: 500 is sufficient, can be made configurable
- **Model**: Currently hardcoded to "gpt-4", should remain configurable

---

## Key Findings Summary

✅ **Clean Integration**: Only one file directly uses OpenAI  
✅ **Well-Structured**: Clear separation of concerns (build prompt, call LLM, parse response)  
✅ **Good Error Handling**: Validates responses thoroughly  
✅ **Testable**: Already has mocking strategy in tests  

⚠️ **Missing Dependency**: OpenAI SDK not in `pyproject.toml`  
⚠️ **Hardcoded Prompt**: 200-line prompt template in code  
⚠️ **Generic Error Handling**: Doesn't distinguish transient vs permanent errors  
⚠️ **No Retry Logic**: Single API call, no automatic retries  

---

## Recommendations for Implementation

### Priority 1: Core Migration
1. Add `openai>=1.0.0` to `pyproject.toml`
2. Extract prompt to `intent_classification.yaml`
3. Implement `OpenAIProvider` with proper error handling
4. Refactor `IntentClassifier` to use `LLMClient`

### Priority 2: Enhanced Error Handling
1. Distinguish transient errors (429, 503, timeout) from permanent (401)
2. Add retry logic with exponential backoff
3. Preserve `retry_after` header from rate limit responses

### Priority 3: Testing
1. Update tests to use `MockProvider`
2. Add integration test with real OpenAI API (skipped without key)
3. Test retry logic with simulated transient errors

---

## No Surprises Confirmed ✅

- OpenAI SDK version: Modern (1.x) based on API usage
- API surface: Standard Chat Completions API
- JSON mode: Uses OpenAI's native JSON mode
- Configuration: Simple (API key only)
- Integration points: Single class (`IntentClassifier`)
- Migration path: Clear and straightforward

**Ready to proceed with implementation!**
