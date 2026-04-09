# MVP Validation Quick Start

**Goal**: Validate the LLM Provider Abstraction Layer MVP works before building more features.

---

## 5-Minute Quick Validation

Run this to get immediate feedback:

```bash
# 1. Run automated validation
bash scripts/validate_mvp.sh

# 2. Check test results
pytest test/llm/ -v --tb=short

# 3. Verify abstraction
bash scripts/verify_abstraction.sh

# 4. Check dataset
sqlite3 data/graphs.db "SELECT COUNT(*) FROM repositories;"
```

**If all pass**: MVP is technically sound ✅

---

## 30-Minute Full Validation

### Step 1: Automated Checks (5 min)
```bash
bash scripts/validate_mvp.sh
```

### Step 2: Start Server (2 min)
```bash
python -m uvicorn api.app:app --reload
```

### Step 3: Test Real Queries (15 min)

Open http://localhost:8000/ui/query.html and test:

**Basic Queries**:
1. "How many repos do we have?"
2. "What are the dependencies of django/django?"
3. "Which repos depend on flask?"

**Advanced Queries**:
4. "Show dependency tree for react"
5. "Which dependencies are unresolved?"
6. "Search for packages with 'test'"

**Document**:
- Did classification work? (Y/N)
- Were parameters extracted correctly? (Y/N)
- Did query execute? (Y/N)
- Were results useful? (Y/N)

### Step 4: Provider Switching (5 min)

```bash
# Test with OpenAI
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# Run a query

# Test without API key (unit tests)
unset OPENAI_API_KEY
pytest test/llm/ -m "not integration" -v
# Should still pass
```

### Step 5: Document Results (3 min)

Copy `VALIDATION_RESULTS_TEMPLATE.md` to `VALIDATION_RESULTS.md` and fill in:
- Test results
- Query accuracy
- Issues found
- Go/No-Go decision

---

## What Success Looks Like

✅ **Technical Success**:
- All tests pass (100/100)
- Abstraction verification passes
- Queries classify correctly (>90%)
- Server starts without errors
- Provider switching works

✅ **Value Success**:
- Queries return useful results
- Insights are actionable
- Someone would pay for this

✅ **Usability Success**:
- Setup docs are clear
- System runs in <30 min from clone
- No "works on my machine" issues

---

## What Failure Looks Like

❌ **Technical Failure**:
- Tests fail
- Abstraction violations found
- Classification accuracy <70%
- Server crashes
- Provider switching breaks

❌ **Value Failure**:
- Results are not useful
- No actionable insights
- Nobody would pay for this

❌ **Usability Failure**:
- Setup docs incomplete
- Takes >1 hour to get running
- Requires undocumented steps

---

## Quick Decision Tree

```
Run validation
    ↓
All technical checks pass?
    ↓ YES                    ↓ NO
    ↓                        Fix issues → Re-validate
    ↓
Queries work correctly?
    ↓ YES                    ↓ NO
    ↓                        Improve prompts → Re-validate
    ↓
Results are valuable?
    ↓ YES                    ↓ NO
    ↓                        Rethink product → Pivot
    ↓
GO → Build next features
```

---

## Next Steps After Validation

### If Validation Passes ✅

**Immediate Priorities** (in order):

1. **Expand Dataset** (Highest ROI)
   - Ingest 200-1000 repos
   - Focus on popular packages
   - Improves all queries immediately

2. **Dependency Risk Propagation** (Core Value)
   - Show how risk flows through dependencies
   - This is the differentiator

3. **Maintainer Risk Signals** (Novel Value)
   - Single maintainer detection
   - Inactivity analysis
   - Concentration metrics

4. **Graph Visualization** (Demo Value)
   - Visualize relationships
   - Makes intelligence tangible

5. **Anthropic Provider** (Quick Win)
   - Proves abstraction works
   - 1-2 hour implementation

### If Validation Fails ❌

**Fix Issues First**:
1. Identify root cause
2. Fix critical issues
3. Re-run validation
4. Don't build new features until MVP works

---

## Key Questions to Answer

After validation, you should be able to answer:

1. **Does it work?** (Technical validation)
   - Yes/No: [Answer]

2. **Does it deliver value?** (Product validation)
   - Yes/No: [Answer]

3. **Can others use it?** (Usability validation)
   - Yes/No: [Answer]

4. **What should we build next?** (Roadmap)
   - Answer: [Priority list]

5. **What's the strategic direction?** (Vision)
   - Repo analysis tool?
   - Supply chain risk platform?
   - Answer: [Direction]

---

## Time Investment

- **Quick validation**: 5 minutes
- **Full validation**: 30 minutes
- **Value validation**: 1-2 hours
- **Documentation**: 30 minutes

**Total**: Half day to fully validate MVP

**ROI**: Prevents weeks of building wrong features

---

## Files Created for You

1. `MVP_VALIDATION_PLAN.md` - Detailed validation plan
2. `scripts/validate_mvp.sh` - Automated validation script
3. `VALIDATION_RESULTS_TEMPLATE.md` - Template for documenting results
4. `VALIDATION_QUICK_START.md` - This file (quick reference)

---

## Commands Cheat Sheet

```bash
# Run automated validation
bash scripts/validate_mvp.sh

# Run all tests
pytest -v

# Run LLM tests only
pytest test/llm/ -v

# Run without API key
unset OPENAI_API_KEY && pytest test/llm/ -m "not integration" -v

# Verify abstraction
bash scripts/verify_abstraction.sh

# Check dataset
sqlite3 data/graphs.db "SELECT COUNT(*) FROM repositories;"

# Start server
python -m uvicorn api.app:app --reload

# Test query via curl
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How many repos do we have?"}'
```

---

## Ready to Validate?

1. Run: `bash scripts/validate_mvp.sh`
2. Review output
3. If pass: Test real queries
4. Document results in `VALIDATION_RESULTS.md`
5. Make go/no-go decision

**Let's validate before we build more!** 🚀
