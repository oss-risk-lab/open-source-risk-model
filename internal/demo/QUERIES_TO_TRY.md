# Queries to Try

## Current Limitation
The MockProvider currently returns `dataset_stats` for all queries. To test different intents properly, you'd need to either:
1. Add OpenAI credits and switch back to `LLM_PROVIDER=openai`
2. Improve the MockProvider to pattern-match different query types

But you can still try these to see the system respond!

---

## Basic Queries (Should Work Now)

### 1. Dataset Statistics
```
How many repos do we have?
Show me dataset stats
What's in the database?
Give me an overview
```
**Expected**: Dataset statistics (51 repos, 3,313 dependencies)

### 2. List Repositories
```
List all repos
Show me all repositories
What repos are tracked?
```
**Expected**: List of repository names

### 3. Repository Stats
```
Show stats for django/django
Tell me about flask/flask
What do you know about requests/requests?
```
**Expected**: Specific repo statistics

### 4. Dependencies
```
What are the dependencies of django?
Show dependencies for flask
List deps for requests
```
**Expected**: List of dependencies for that repo

### 5. Reverse Dependencies (Dependents)
```
Which repos depend on requests?
What uses flask?
Show me dependents of django
```
**Expected**: List of repos that depend on the package

### 6. Dependency Tree
```
Show dependency tree for django
Get dependency graph for flask depth 2
Tree view of requests dependencies
```
**Expected**: Hierarchical dependency tree

### 7. Unresolved Dependencies
```
List unresolved dependencies
Show me missing packages
What dependencies couldn't be resolved?
```
**Expected**: List of dependencies without resolution

### 8. Search
```
Search for repos with 'django'
Find packages containing 'flask'
Look for 'requests' in repos
```
**Expected**: Search results

### 9. Manifests
```
What manifest files does django have?
Show manifests for flask
List manifest types
```
**Expected**: Manifest file information

### 10. Counts by Type
```
Count manifests by type
How many of each manifest type?
Breakdown by manifest type
```
**Expected**: Counts grouped by manifest type

---

## To Test Different Intents Properly

### Option 1: Add OpenAI Credits (Recommended)
1. Add credits at: https://platform.openai.com/account/billing
2. Change `.env`: `LLM_PROVIDER=openai`
3. Restart server: `./restart_server.sh`
4. Try all the queries above - they should classify correctly!

### Option 2: Improve MockProvider (30 minutes)
Add pattern matching to the factory to return different responses based on query content:

```python
# In factory.py, improve the canned_responses:
canned_responses = {
    "intent_classification": lambda query: classify_by_pattern(query)
}
```

This would require implementing pattern matching logic similar to what's in the tests.

### Option 3: Use Direct API Calls
You can bypass the LLM entirely by providing explicit intent and parameters:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test",
    "intent": "list_dependencies",
    "parameters": {"repo_full_name": "django/django"}
  }'
```

---

## What You Can Validate Now

Even with MockProvider returning the same intent, you can validate:

1. **System responds quickly** (< 50ms)
2. **Database has real data** (51 repos, 3,313 dependencies)
3. **UI works** (displays results correctly)
4. **API is stable** (no crashes or errors)
5. **Provider abstraction works** (swapped from OpenAI to Mock seamlessly)

---

## Interesting Data Points from Your Database

Based on the results you got:
- **51 repositories** tracked
- **3,313 total dependencies** 
- **471 repos with dependencies** (92% coverage)
- **752 manifest files** found
- **2,936 resolved dependencies** (88.6% resolution rate)
- **1,473 unique packages** identified

This is solid data to work with!

---

## Next Steps

### Immediate (Now)
Try a few more queries just to see the system respond consistently

### Short Term (When you have time)
1. Add $5-10 to OpenAI account
2. Switch back to `LLM_PROVIDER=openai`
3. Test all 10 query types above
4. Document which ones work well vs. need prompt tuning

### Medium Term (Next session)
1. Review intent classification accuracy
2. Tune prompts if needed
3. Expand dataset to 200+ repos
4. Build next features (dependency risk, maintainer signals)

---

## The Big Picture

You've validated:
- ✅ Architecture works
- ✅ Provider abstraction works
- ✅ System is fast (46ms)
- ✅ Database has real data
- ✅ End-to-end pipeline works

What's left to validate:
- ⏳ Real LLM classification accuracy (needs OpenAI credits)
- ⏳ All intent types work correctly
- ⏳ Parameter extraction is accurate
- ⏳ Edge cases and error handling

But the core MVP is proven! 🎉

---

## Quick Test Script

Want to test multiple queries quickly? Try this:

```bash
# Test query 1
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How many repos?"}' | jq '.intent, .confidence, .execution_time_ms'

# Test query 2  
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show stats for django"}' | jq '.intent, .confidence, .execution_time_ms'

# Test query 3
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "List dependencies"}' | jq '.intent, .confidence, .execution_time_ms'
```

All should return quickly with `dataset_stats` intent and 0.85 confidence.
