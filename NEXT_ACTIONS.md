# Next Actions: MVP Product Validation

**Status**: Technical validation ✅ PASSED | Product validation ⏳ PENDING
**Blocker**: Database is empty (0 repos, 0 dependencies)

---

## The Key Insight

✅ **Technical validation passed** - Architecture is solid, tests work
❌ **Product validation hasn't started** - No data to query

**Priority**: Populate database → Test real queries → Validate value

---

## Action Plan (Most Efficient Order)

### 1. Populate Database (30-60 minutes) ⭐ HIGHEST PRIORITY

**Goal**: Minimum viable dataset to exercise all intents

**Target**:
- 20-50 repositories
- Mix of ecosystems (npm, pypi, go, maven if supported)
- Include repos with known dependency depth
- Include popular packages (django, flask, react, express)

**Commands**:
```bash
# Check what ingestion scripts exist
ls scripts/ingest*.sh scripts/populate*.sh

# Use existing ingestion (you have these scripts)
bash scripts/populate_dependencies.sh  # If this exists
# OR
python scripts/populate_popular_repos.py  # If this exists
# OR
bash scripts/ingest_dataset.sh  # Your batch ingestion

# Verify data loaded
sqlite3 data/graphs.db "SELECT COUNT(*) FROM repositories;"
sqlite3 data/graphs.db "SELECT COUNT(*) FROM dependencies;"
sqlite3 data/graphs.db "SELECT full_name FROM repositories LIMIT 10;"
```

**Success Criteria**:
- At least 20 repos in database
- At least 50 dependencies
- Mix of ecosystems represented

---

### 2. Test Real Queries with OpenAI (30 minutes) ⭐ HIGH PRIORITY

**Goal**: Validate intent classification works end-to-end

**Setup**:
```bash
# Add API key to .env
echo "OPENAI_API_KEY=sk-your-key-here" >> .env

# Start server
python -m uvicorn api.app:app --reload
```

**Test Queries** (via UI at http://localhost:8000/ui/query.html):

```
1. "How many repos do we have?"
   Expected: dataset_stats, confidence ≥0.7

2. "Show me stats for django/django"
   Expected: repo_stats, repo_full_name="django/django"

3. "What are the dependencies of flask?"
   Expected: list_dependencies, repo_full_name contains "flask"

4. "Which repos depend on requests?"
   Expected: find_dependents, package_name="requests"

5. "Show dependency tree for react depth 2"
   Expected: get_dependency_tree, repo_full_name contains "react", max_depth=2

6. "List unresolved dependencies"
   Expected: list_unresolved

7. "Search for repos with 'django'"
   Expected: search_repos, pattern="django"

8. "Find packages starting with 'pytest'"
   Expected: search_packages, pattern="pytest"

9. "What manifest files does express have?"
   Expected: list_manifests, repo_full_name contains "express"

10. "Count manifests by type"
    Expected: count_by_manifest_type
```

**What to Validate**:
- ✅ Intent classification accuracy (>90% correct)
- ✅ Parameter extraction works
- ✅ Confidence mostly ≥0.7 for clear queries
- ✅ Graceful "unknown" for ambiguous queries
- ✅ Results returned from DB match expectations
- ✅ Latency feels acceptable (<2 seconds)

**Document Results**:
- Create a simple table: Query | Intent | Confidence | Params Correct? | Results Valid?
- Note any surprises or issues

---

### 3. Run Integration Tests (5 minutes)

**Goal**: Prove provider works against real API

```bash
# With API key set
pytest -m integration -v

# Should see:
# test_intent_classification_with_real_openai PASSED
# test_provider_validation PASSED
```

**Success Criteria**:
- Both integration tests pass
- No errors or timeouts

---

### 4. Provider Swap Validation (15 minutes) ⭐ KEY PROOF

**Goal**: Prove abstraction is real by swapping providers

**Test A: With OpenAI**
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# Run query: "How many repos?"
# Note: intent, confidence, results
```

**Test B: With Mock (for comparison)**
```bash
export LLM_PROVIDER=mock  # If you add this to factory
# OR just run unit tests
pytest test/test_intent_classifier.py -v
# Should still pass (uses MockProvider)
```

**What to Validate**:
- App behaves the same from outside
- Only classification behavior differs
- No crashes or errors when switching
- This proves: abstraction is real, not just theoretical

---

### 5. Cold Start Test (30 minutes) 🎯 REAL MVP TEST

**Goal**: Can someone else run this from scratch?

**Steps**:
```bash
# In a fresh directory
cd ~/test-validation
git clone <your-repo-url> .

# Follow docs/SETUP.md exactly
# Document any missing steps or unclear instructions

# Add API keys
cp .env.example .env
# Edit .env with real keys

# Install dependencies
pip install -e .

# Ingest sample data
bash scripts/ingest_dataset.sh  # Or whatever works

# Start server
python -m uvicorn api.app:app --reload

# Test 5 queries via UI
# Document: time to first query, any issues
```

**Success Criteria**:
- Can get from clone to working queries in <30 minutes
- No undocumented steps required
- No "works on my machine" issues

---

## Quick Fixes

### Fix pytest Warning (2 minutes)

**Issue**: `PytestConfigWarning: Unknown config option: asyncio_mode`

**Fix**: Remove from `pyproject.toml`

```toml
# In pyproject.toml, remove this line:
asyncio_mode = "auto"

# Keep only:
[tool.pytest.ini_options]
testpaths = ["test"]
pythonpath = ["src"]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
]
```

---

## Test Query Script Template

Create `scripts/test_queries.sh` for quick validation:

```bash
#!/bin/bash
# Quick query validation script

API_URL="http://localhost:8000/api/query"

echo "Testing query API..."
echo ""

# Test 1: Dataset stats
echo "1. Dataset stats"
curl -s -X POST $API_URL \
  -H "Content-Type: application/json" \
  -d '{"query": "How many repos do we have?"}' | jq '.intent, .confidence, .result_count'
echo ""

# Test 2: Repo stats
echo "2. Repo stats"
curl -s -X POST $API_URL \
  -H "Content-Type: application/json" \
  -d '{"query": "Show stats for django/django"}' | jq '.intent, .confidence, .parameters'
echo ""

# Test 3: List dependencies
echo "3. List dependencies"
curl -s -X POST $API_URL \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the dependencies of flask?"}' | jq '.intent, .confidence, .result_count'
echo ""

# Add more tests...
```

---

## Success Metrics

### Technical Validation ✅
- [x] 118 tests passing
- [x] Provider abstraction verified
- [x] No API key required for unit tests

### Product Validation (TODO)
- [ ] Database populated (20+ repos)
- [ ] 10 real queries tested
- [ ] >90% intent classification accuracy
- [ ] Results are useful and accurate
- [ ] Latency <2 seconds
- [ ] Provider swap works
- [ ] Cold start works

---

## Decision Tree

```
Populate database
    ↓
Test 10 real queries
    ↓
Classification accuracy >90%?
    ↓ YES                    ↓ NO
    ↓                        Improve prompts → Retest
    ↓
Results are useful?
    ↓ YES                    ↓ NO
    ↓                        Fix executors → Retest
    ↓
Provider swap works?
    ↓ YES                    ↓ NO
    ↓                        Debug abstraction
    ↓
Cold start works?
    ↓ YES                    ↓ NO
    ↓                        Improve docs
    ↓
✅ MVP VALIDATED
    ↓
Implement production improvements
    ↓
Add Anthropic provider
```

---

## Timeline

- **Database population**: 30-60 min
- **Real query testing**: 30 min
- **Integration tests**: 5 min
- **Provider swap**: 15 min
- **Cold start test**: 30 min
- **Documentation**: 15 min

**Total**: 2-3 hours to fully validate MVP

---

## After Validation

### If Validation Passes ✅

1. **Document results** in `VALIDATION_RESULTS.md`
2. **Implement production improvements** (3-5 hours)
   - Timeout enforcement
   - Retry jitter
   - validate_config() standardization
   - Intent allowlist tightening
   - Parameter schema validation
3. **Add Anthropic provider** (1-2 hours)
4. **Expand dataset** (200-1000 repos)
5. **Build next features** (dependency risk propagation, maintainer signals)

### If Validation Fails ❌

1. **Diagnose root cause**
2. **Fix critical issues**
3. **Re-run validation**
4. **Don't build new features until MVP works**

---

## Key Files

- `VALIDATION_RESULTS_TEMPLATE.md` - Template for documenting results
- `scripts/validate_mvp.sh` - Automated technical validation (already passed)
- `scripts/test_queries.sh` - Quick query testing (create this)
- `PRODUCTION_HARDENING_IMPROVEMENTS.md` - Improvements to implement after validation

---

## The Bottom Line

**You have a technically sound MVP. Now prove it delivers value.**

1. Add data
2. Test queries
3. Document results
4. Make go/no-go decision

Don't build more features until you've validated the MVP actually works and delivers value.

---

**Next Command**: Check what ingestion scripts you have:
```bash
ls -la scripts/ingest*.sh scripts/populate*.sh
```

Then populate the database and start testing!
