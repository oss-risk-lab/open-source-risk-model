# Phase 3: Provider Swap Validation

**Date**: 2026-03-04  
**Status**: ⏳ READY TO RUN

## Objective

Verify that the LLM provider abstraction works correctly by testing the same queries with different providers (OpenAI and Mock). This proves the application doesn't care which provider is used.

## Test Procedure

### Step 1: Test with OpenAI Provider

1. Ensure `.env` has `LLM_PROVIDER=openai`
2. Restart server: `./restart_server.sh`
3. Run test queries and record results

### Step 2: Test with Mock Provider

1. Change `.env` to `LLM_PROVIDER=mock`
2. Restart server: `./restart_server.sh`
3. Run same test queries and record results

### Step 3: Compare Results

Verify that:
- Both providers return valid responses
- Intent classification works (may differ between providers)
- No provider-specific errors or leakage
- Application code doesn't know which provider is used

## Test Queries

Run these 5 queries with each provider:

```bash
# Query 1: Dataset stats
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How many repos do we have?"}'

# Query 2: Repo stats
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show stats for django/django"}'

# Query 3: List dependencies
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the dependencies of django?"}'

# Query 4: Find dependents
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What repos depend on requests?"}'

# Query 5: Search packages
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Search for packages named express"}'
```

## Expected Results

### OpenAI Provider
- Should use GPT-5-mini model
- Should return real AI classifications
- Confidence scores: 0.95-0.98
- Response times: <5ms

### Mock Provider
- Should use canned responses
- Should return predefined classifications
- Confidence scores: 1.0 (mock always confident)
- Response times: <1ms (no API calls)

## Success Criteria

✅ Both providers work without errors  
✅ No provider-specific code in application layer  
✅ Seamless swap between providers  
✅ Results are valid (may differ in classification)  
✅ No OpenAI-specific exceptions when using Mock  

## Automated Test Script

Run this script to test both providers automatically:

```bash
chmod +x run_provider_swap_test.sh
./run_provider_swap_test.sh
```

**Note**: This script requires manual server restart between provider changes.

## Manual Test (Recommended)

Since server restart is required, manual testing is more reliable:

1. **Test OpenAI** (current configuration)
   ```bash
   # Verify provider
   grep LLM_PROVIDER .env
   
   # Run one test query
   curl -X POST http://localhost:8000/api/query \
     -H "Content-Type: application/json" \
     -d '{"query": "How many repos do we have?"}' | python3 -m json.tool
   ```

2. **Switch to Mock**
   ```bash
   # Update .env
   sed -i.bak 's/LLM_PROVIDER=openai/LLM_PROVIDER=mock/' .env
   
   # Restart server
   ./restart_server.sh
   
   # Wait for server to start (check http://localhost:8000)
   
   # Run same query
   curl -X POST http://localhost:8000/api/query \
     -H "Content-Type: application/json" \
     -d '{"query": "How many repos do we have?"}' | python3 -m json.tool
   ```

3. **Switch back to OpenAI**
   ```bash
   sed -i.bak 's/LLM_PROVIDER=mock/LLM_PROVIDER=openai/' .env
   ./restart_server.sh
   ```

## Results Template

Record results in `PHASE3_PROVIDER_SWAP_RESULTS.md`:

```markdown
## OpenAI Results
- Query 1: intent=dataset_stats, confidence=0.98, rows=1
- Query 2: intent=repo_stats, confidence=0.95, rows=1
- Query 3: intent=list_dependencies, confidence=0.95, rows=3
- Query 4: intent=find_dependents, confidence=0.95, rows=8
- Query 5: intent=search_packages, confidence=0.95, rows=5

## Mock Results
- Query 1: intent=dataset_stats, confidence=1.0, rows=1
- Query 2: intent=repo_stats, confidence=1.0, rows=1
- Query 3: intent=list_dependencies, confidence=1.0, rows=3
- Query 4: intent=find_dependents, confidence=1.0, rows=8
- Query 5: intent=search_packages, confidence=1.0, rows=5

## Verdict
✅ Provider swap works seamlessly
✅ No provider leakage
✅ Both providers return valid results
```

## Next Steps

After completing Phase 3, proceed to **Phase 4: Extract Demo Insights**.
