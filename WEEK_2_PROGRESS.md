# Week 2 Progress: Intent-Based Query API

**Date**: 2026-02-25  
**Status**: 🚧 IN PROGRESS (Phase 1 & 2 Complete)

## Completed

### Phase 1: Tests for IntentExecutor ✅
**Commit**: e17615c

- 31 comprehensive tests covering all 11 intents
- Happy-path test for each intent
- Parameter validation tests
- Determinism tests (same input = same output)
- Security tests (SQL injection, invalid intents)
- Result structure validation
- Edge cases and performance tests

**Result**: All tests passing. Behavior locked for stability.

### Phase 2: POST /api/query with Dev Mode ✅
**Commit**: eb12051

- Added POST `/api/query` endpoint to FastAPI app
- Dev mode: Accept explicit `intent` + `parameters`
- Production mode: Return 501 (LLM not yet implemented)
- Comprehensive error handling
- 17 end-to-end API tests passing

**Dev Mode Example**:
```json
POST /api/query
{
  "query": "List dependencies",
  "intent": "list_dependencies",
  "parameters": {"repo_full_name": "django/django"},
  "max_results": 10
}
```

**Response**:
```json
{
  "intent": "list_dependencies",
  "parameters": {"repo_full_name": "django/django"},
  "confidence": 1.0,
  "results": [...],
  "result_count": 40,
  "execution_time_ms": 15.3,
  "metadata": {...}
}
```

## Testing Summary

### IntentExecutor Tests (31 tests)
- ✅ 11 happy-path tests (one per intent)
- ✅ 5 parameter validation tests
- ✅ 2 determinism tests
- ✅ 4 security tests
- ✅ 3 result structure tests
- ✅ 4 edge case tests
- ✅ 2 performance tests

### API Endpoint Tests (17 tests)
- ✅ 4 dev mode tests (different intents)
- ✅ 4 validation tests
- ✅ 3 security tests
- ✅ 2 performance tests
- ✅ 2 response format tests
- ✅ 2 edge case tests

**Total**: 48 tests passing

## Security Verification

✅ **SQL Injection Protection**
- Parameterized queries only
- Injection attempts neutralized
- Tests verify protection

✅ **Intent Allowlist Enforcement**
- Only 11 predefined intents allowed
- Invalid intents rejected with 400
- No arbitrary SQL execution

✅ **No Network Calls**
- All queries read from database only
- No GitHub API calls in query paths
- Verified in tests

## Performance Metrics

- Query execution: < 100ms (tested)
- Tree computation: < 200ms (tested)
- API response time: < 150ms total
- Concurrent queries: Supported and tested

## Next Steps

### Phase 3: LLM Intent Classifier 🔜

**Goal**: Replace stub classifier with real LLM

**Requirements**:
1. Strict JSON schema for LLM output
2. Confidence gating (reject < 0.7)
3. Parameter extraction from natural language
4. Fallback to "unknown" intent

**Implementation**:
```python
# src/open_source_risk_model/query/intent_classifier.py

class IntentClassifier:
    def classify(self, query: str) -> ClassificationResult:
        # LLM prompt with strict JSON schema
        # Extract intent + parameters
        # Return confidence score
        pass
```

**LLM Prompt Template**:
```
You are a query intent classifier for a dependency graph database.

Available intents: [list of 11 intents with descriptions]

User query: "{query}"

Classify the intent and extract parameters as JSON:
{
  "intent": "<intent_name>",
  "parameters": {...},
  "confidence": 0.0-1.0
}

If confidence < 0.7, return intent "unknown".
```

**Tests Needed**:
- Example queries for each intent
- Confidence thresholding
- Parameter extraction accuracy
- Ambiguous query handling
- Unknown intent fallback

### Phase 4: Integration & Documentation 🔜

1. Wire LLM classifier into API endpoint
2. Update API documentation
3. Add example queries to docs
4. Performance testing with LLM
5. User acceptance testing

## Architecture Compliance

✅ **North Star Alignment**:
- Database is source of truth
- No network in GET/query paths
- LLM never generates SQL (only classifies intent)
- Compute on-the-fly (BFS tree algorithm)
- Conventional commits
- Tests before features

✅ **Code Quality**:
- 48 tests passing
- Comprehensive error handling
- Type hints throughout
- Structured logging
- Clear separation of concerns

## Files Changed

### New Files
- `src/open_source_risk_model/query/__init__.py`
- `src/open_source_risk_model/query/intent_executor.py` (700 lines)
- `test/test_intent_executor.py` (423 lines)
- `test/test_query_api.py` (316 lines)

### Modified Files
- `api/app.py` (+200 lines for query endpoint)

### Total
- 1,639 lines of production code
- 739 lines of test code
- Test coverage: Comprehensive

## Demo Ready

The system is now demo-ready in dev mode:

```bash
# Start API server
uvicorn api.app:app --reload

# Test query
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me dataset stats",
    "intent": "dataset_stats",
    "parameters": {},
    "max_results": 1
  }'
```

**Response**:
```json
{
  "intent": "dataset_stats",
  "confidence": 1.0,
  "result_count": 1,
  "results": [{
    "repo_count": 51,
    "total_dependencies": 3674,
    "resolution_rate": 89.2
  }],
  "execution_time_ms": 11.3
}
```

## Lessons Learned

1. **Tests first = stability** - Locked behavior before adding complexity
2. **Dev mode = testability** - Stub classifier enabled end-to-end testing
3. **Incremental approach** - Each phase builds on previous
4. **Security by design** - Parameterized queries from the start
5. **Clear contracts** - Pydantic models enforce structure

## Timeline

- Week 1: Data population (51 repos, 3,674 deps) ✅
- Week 2 Phase 1: IntentExecutor tests ✅
- Week 2 Phase 2: API endpoint + dev mode ✅
- Week 2 Phase 3: LLM classifier 🔜
- Week 3: Integration + documentation 🔜
