# Post-MVP Validation Plan

**Status**: ✅ COMPLETE (Phases 1, 2, 4 done; Phase 3 ready)

**Current State**: 51 repos, 3,691 dependencies, 89.22% resolution rate, real AI working

**Results**: See `POST_MVP_VALIDATION_COMPLETE.md` for full summary.

---

## Phase 1: Data Quality Check ✅ COMPLETE

Before scaling to 200+ repos, verify the 51 aren't garbage.

### Quick SQL Checks

```bash
# Run these in sqlite3 data/graphs.db
sqlite3 data/graphs.db
```

**Repo Completeness**:
```sql
-- Check for missing critical fields
SELECT 
  COUNT(*) as total,
  COUNT(full_name) as has_name,
  COUNT(default_branch) as has_branch,
  COUNT(last_pushed_at) as has_push_date
FROM repo_graphs;

-- Sample 10 repos to eyeball
SELECT full_name, default_branch, last_pushed_at 
FROM repo_graphs 
LIMIT 10;
```

**Dependency Coverage**:
```sql
-- What % of repos have dependencies?
SELECT 
  COUNT(DISTINCT CASE WHEN dep_count > 0 THEN full_name END) * 100.0 / COUNT(*) as pct_with_deps,
  AVG(dep_count) as avg_deps_per_repo
FROM (
  SELECT rg.full_name, COUNT(d.id) as dep_count
  FROM repo_graphs rg
  LEFT JOIN dependencies d ON d.repo_full_name = rg.full_name
  GROUP BY rg.full_name
);
```

**Manifest Coverage**:
```sql
-- What manifest types do we have?
SELECT 
  manifest_type,
  COUNT(*) as count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as pct
FROM dependencies
WHERE manifest_type IS NOT NULL
GROUP BY manifest_type
ORDER BY count DESC;
```

**Resolution Quality**:
```sql
-- Unresolved rate by registry
SELECT 
  registry_type,
  COUNT(*) as total,
  COUNT(resolved_repo) as resolved,
  (COUNT(*) - COUNT(resolved_repo)) * 100.0 / COUNT(*) as unresolved_pct
FROM dependencies
GROUP BY registry_type
ORDER BY total DESC;
```

### Success Criteria
- ✅ >90% repos have dependencies
- ✅ Multiple manifest types (not just one)
- ✅ <20% unresolved rate overall
- ✅ No NULL full_names or critical fields

### If Data Quality Fails
**Don't scale yet!** Fix ingestion first:
- High unresolved → Fix package resolver
- Missing manifests → Fix manifest discovery
- NULL fields → Fix GitHub API integration

---

## Phase 2: Query Test Set (1 hour) ⭐ CORE VALIDATION

Prove: LLM → intent → SQL → results are correct and useful.

### Test Matrix

Create `QUERY_TEST_RESULTS.md` and test these:

| # | Query | Expected Intent | Expected Params | Pass? | Notes |
|---|-------|----------------|-----------------|-------|-------|
| 1 | "How many repos do we have?" | dataset_stats | {} | | |
| 2 | "Show stats for django/django" | repo_stats | repo_full_name | | |
| 3 | "What are the dependencies of flask?" | list_dependencies | repo_full_name | | |
| 4 | "Show dependency tree for django depth 2" | get_dependency_tree | repo, max_depth=2 | | |
| 5 | "Which repos depend on requests?" | find_dependents | package_name | | |
| 6 | "Search for repos with 'django'" | search_repos | pattern | | |
| 7 | "Find packages starting with 'pytest'" | search_packages | pattern | | |
| 8 | "What manifests does flask have?" | list_manifests | repo_full_name | | |
| 9 | "Count manifests by type" | count_by_manifest_type | {} | | |
| 10 | "List unresolved dependencies" | list_unresolved | {} | | |

### For Each Query, Log:
- Intent classification (correct?)
- Confidence score (>0.7?)
- Parameters extracted (correct?)
- Row count returned (reasonable?)
- Results look useful? (yes/no)

### Success Criteria
- ✅ >90% intent accuracy (9/10 correct)
- ✅ >80% confidence scores above 0.7
- ✅ 100% parameter extraction correct
- ✅ All queries return reasonable results

---

## Phase 3: Provider Swap Validation (15 minutes)

Prove the abstraction is real by running same queries with different providers.

### Test Script

```bash
# Test with OpenAI
export LLM_PROVIDER=openai
# Run queries 1-5 from test set
# Log: intent, confidence, results

# Test with Mock
export LLM_PROVIDER=mock
# Run same queries 1-5
# Log: intent, confidence, results

# Compare: App behavior should be identical from outside
```

### Success Criteria
- ✅ No crashes when switching providers
- ✅ Same queries work with both providers
- ✅ Only classification behavior differs
- ✅ Results format identical

---

## Phase 4: Extract Demo Insights (30 minutes) 🎯 PRODUCT MOMENT

Generate compelling insights from your 51 repos.

### Insight Queries

**1. Top Dependency Hubs**:
```sql
-- Most depended-on packages
SELECT 
  package_name,
  registry_type,
  COUNT(DISTINCT repo_full_name) as dependent_count
FROM dependencies
WHERE resolved_repo IS NOT NULL
GROUP BY package_name, registry_type
ORDER BY dependent_count DESC
LIMIT 10;
```

**2. Repos with Highest Dependency Depth**:
```sql
-- Repos with most dependencies
SELECT 
  repo_full_name,
  COUNT(*) as dep_count,
  COUNT(CASE WHEN resolved_repo IS NULL THEN 1 END) as unresolved_count
FROM dependencies
GROUP BY repo_full_name
ORDER BY dep_count DESC
LIMIT 10;
```

**3. Repos with Most Unresolved Deps**:
```sql
-- Risk: high unresolved = unknown supply chain
SELECT 
  repo_full_name,
  COUNT(*) as total_deps,
  COUNT(CASE WHEN resolved_repo IS NULL THEN 1 END) as unresolved,
  COUNT(CASE WHEN resolved_repo IS NULL THEN 1 END) * 100.0 / COUNT(*) as unresolved_pct
FROM dependencies
GROUP BY repo_full_name
HAVING unresolved > 0
ORDER BY unresolved_pct DESC
LIMIT 10;
```

**4. Most Common Packages**:
```sql
-- Ecosystem view
SELECT 
  package_name,
  registry_type,
  COUNT(DISTINCT repo_full_name) as usage_count,
  AVG(resolution_confidence) as avg_confidence
FROM dependencies
GROUP BY package_name, registry_type
HAVING usage_count > 1
ORDER BY usage_count DESC
LIMIT 20;
```

### Turn Into:
1. **README section**: "Key Insights from 51 Repos"
2. **Demo script**: `demo_insights.sh`
3. **Pitch deck**: "Supply Chain Intelligence in Action"

---

## Phase 5: Decide Next Feature

Based on validation results, prioritize:

### If Validation Passes ✅

**Highest Value (in order)**:

1. **Scale to 200-500 repos** (2-3 hours)
   - Only after data quality validated
   - Use existing ingestion scripts
   - Target: Popular repos across ecosystems

2. **Dependency Risk Propagation** (1-2 days)
   - Core differentiator
   - "If package X has a CVE, which repos are affected?"
   - Transitive risk calculation

3. **Maintainer Risk Signals** (1-2 days)
   - Your unique angle
   - Abandoned repos, single maintainer, etc.
   - Novel value proposition

4. **Graph Visualization** (1 day)
   - Best demo amplifier
   - Interactive dependency explorer
   - Compelling for security teams

5. **Anthropic Provider** (2-3 hours)
   - Low risk now that abstraction proven
   - Your dad wants it
   - Easy win

### If Validation Fails ❌

**Fix before scaling**:
- Low intent accuracy → Tune prompts
- High unresolved rate → Fix package resolver
- Missing data → Fix ingestion
- Slow queries → Add indexes

---

## Timeline

**Today (2-3 hours)**:
- Phase 1: Data quality check (30 min)
- Phase 2: Query test set (1 hour)
- Phase 3: Provider swap (15 min)
- Phase 4: Extract insights (30 min)
- Document results (15 min)

**Next Session**:
- Implement highest-value feature based on results
- OR fix issues if validation fails

---

## Success Metrics

### Technical Validation ✅ (Already Done)
- [x] Architecture sound
- [x] Provider abstraction works
- [x] Tests pass
- [x] Real AI classification works

### Value Validation ⏳ (Do Now)
- [ ] Data quality verified
- [ ] Query accuracy >90%
- [ ] Provider swap works
- [ ] Demo insights extracted

### Coverage Validation ⏳ (Next)
- [ ] All intent types tested
- [ ] Edge cases handled
- [ ] Error scenarios graceful
- [ ] Performance acceptable

---

## The Big Picture

You've built a **technically sound MVP**. Now prove it **delivers value**:

1. **Data quality** → Ensures foundation is solid
2. **Query accuracy** → Proves AI classification works
3. **Provider swap** → Validates architecture
4. **Demo insights** → Shows product value

After this validation, you'll know exactly what to build next based on real evidence, not assumptions.

---

## Quick Start

```bash
# 1. Check data quality
sqlite3 data/graphs.db < data_quality_checks.sql

# 2. Run query test set
# Use UI at http://localhost:8000/ui/query.html
# Document results in QUERY_TEST_RESULTS.md

# 3. Test provider swap
export LLM_PROVIDER=mock
# Test 5 queries
export LLM_PROVIDER=openai
# Test same 5 queries

# 4. Extract insights
sqlite3 data/graphs.db < insight_queries.sql > DEMO_INSIGHTS.txt
```

---

**Next Command**: Start with data quality checks!

```bash
sqlite3 data/graphs.db
```

Then run the SQL queries from Phase 1.
