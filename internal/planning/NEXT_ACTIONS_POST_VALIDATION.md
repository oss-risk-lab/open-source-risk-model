# Next Actions - Post Validation

**Date**: 2026-03-04  
**Context**: MVP validation complete, system is production-ready

## Immediate Actions (Today)

### 1. Review Validation Results (5 minutes)
Read these files to understand what was validated:
- `VALIDATION_SUMMARY.md` - Quick overview
- `POST_MVP_VALIDATION_COMPLETE.md` - Full summary
- `PHASE4_DEMO_INSIGHTS.md` - Demo talking points

### 2. Optional: Run Phase 3 Provider Swap Test (10 minutes)
If you want to formally validate provider swap:
```bash
# Follow instructions in:
cat PHASE3_PROVIDER_SWAP_TEST.md

# Quick test:
# 1. Verify OpenAI works (already tested)
# 2. Switch to mock: sed -i.bak 's/LLM_PROVIDER=openai/LLM_PROVIDER=mock/' .env
# 3. Restart: ./restart_server.sh
# 4. Test one query
# 5. Switch back: sed -i.bak 's/LLM_PROVIDER=mock/LLM_PROVIDER=openai/' .env
```

### 3. Decide Next Feature (15 minutes)
Based on validation results, choose your next priority:

**Option A: Expand Dataset** (Recommended - High Value, Low Risk)
- Target: 200-500 repos
- Time: 2-4 hours
- Value: More compelling demos, better insights
- Risk: Low (ingestion pipeline proven)

**Option B: Improve PyPI Resolution** (Quick Win - Medium Value, Low Risk)
- Target: 95% resolution (currently 89%)
- Time: 4-8 hours
- Value: Reduce supply chain blind spots
- Risk: Low (isolated to package mapping)

**Option C: Add Transitive Dependencies** (High Impact - High Value, Medium Risk)
- Target: Full dependency trees with depth
- Time: 1-2 weeks
- Value: True supply chain risk analysis
- Risk: Medium (complexity, performance)

**Option D: Dependency Risk Propagation** (Core Feature - High Value, High Risk)
- Target: Risk scores through dependency tree
- Time: 2-4 weeks
- Value: Core value proposition
- Risk: High (requires risk model, CVE integration)

---

## Recommended Path: Expand Dataset First

### Why?
1. **Low risk**: Ingestion pipeline already proven
2. **High value**: More data = more compelling demos
3. **Fast**: Can complete in 2-4 hours
4. **Validates scale**: Tests system with 4-10x more data
5. **Enables better decisions**: More data reveals patterns

### How?
```bash
# Option 1: Use existing popular repos list
python scripts/populate_popular_repos.py --count 200

# Option 2: Ingest specific repos
python -m open_source_risk_model.cli.ingest batch repos.txt

# Option 3: Ingest by topic
# Create repos_security.txt with security-focused repos
# Then: python -m open_source_risk_model.cli.ingest batch repos_security.txt
```

### Success Metrics
- Target: 200-500 repos
- Target: 15,000-50,000 dependencies
- Target: >85% resolution rate (maintain quality)
- Target: <5 second query response times (test performance)

### After Dataset Expansion
Re-run validation to see new patterns:
```bash
# Re-run Phase 1 data quality
sqlite3 data/graphs.db < /tmp/phase1_data_quality.sql

# Re-run Phase 4 demo insights
sqlite3 data/graphs.db < /tmp/phase4_demo_insights.sql

# Re-run Phase 2 query tests
./run_query_tests.sh
```

---

## Alternative Path: Improve PyPI Resolution

### Why?
1. **Quick win**: Can complete in 4-8 hours
2. **Reduces blind spots**: All unresolved are Python packages
3. **Improves quality**: 89% → 95% resolution
4. **Low risk**: Isolated to package mapping

### How?
1. **Analyze unresolved patterns**
   ```sql
   SELECT package_name, COUNT(*) as occurrences
   FROM repo_dependencies
   WHERE resolved_repo IS NULL AND registry_type = 'pypi'
   GROUP BY package_name
   ORDER BY occurrences DESC
   LIMIT 20;
   ```

2. **Add manual mappings** for top failures
   - pytest-cov → pytest-dev/pytest-cov
   - colorama → tartley/colorama
   - numpy → numpy/numpy
   - pandas → pandas-dev/pandas

3. **Improve PyPI API integration**
   - Use PyPI JSON API to get GitHub URLs
   - Add fallback to package homepage parsing

4. **Test resolution improvements**
   ```bash
   # Re-ingest one repo to test
   python -m open_source_risk_model.cli.ingest repo PyCQA/pylint
   
   # Check resolution rate
   sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_dependencies WHERE resolved_repo IS NULL"
   ```

---

## Alternative Path: Add Transitive Dependencies

### Why?
1. **High impact**: Enables true supply chain analysis
2. **Differentiator**: Most tools only show direct deps
3. **Enables risk propagation**: Required for next phase

### How?
1. **Design transitive resolution**
   - Recursive resolution with depth limits
   - Cycle detection
   - Performance optimization (caching, batching)

2. **Update schema**
   - Add `depth` column to repo_dependencies
   - Add `parent_package` column for tree structure
   - Add indexes for tree queries

3. **Implement resolver**
   - Start with direct dependencies
   - For each resolved dependency, fetch its dependencies
   - Continue until max depth or no more dependencies
   - Handle cycles (mark and skip)

4. **Update queries**
   - Add depth filtering to all queries
   - Add tree traversal queries
   - Update UI to show tree structure

### Risks
- **Performance**: Recursive resolution is slow
- **Storage**: Transitive deps can be 10-100x more data
- **Complexity**: Cycle detection, depth limits, caching

---

## Don't Do Yet

### ❌ Add Anthropic Provider
- **Why not**: Low value, abstraction already proven
- **When**: After dataset expansion and risk propagation
- **Effort**: 2-4 hours (low)

### ❌ Build UI/Visualization
- **Why not**: Data layer needs more features first
- **When**: After transitive deps and risk propagation
- **Effort**: 1-2 weeks (medium)

### ❌ Add More Registries (Maven, RubyGems, etc.)
- **Why not**: Current registries (npm, pypi) not fully optimized
- **When**: After PyPI resolution improved
- **Effort**: 1-2 weeks per registry (high)

---

## Decision Framework

Ask yourself:
1. **What delivers most value to users?** → Dataset expansion or risk propagation
2. **What proves the concept fastest?** → Dataset expansion
3. **What reduces risk?** → Dataset expansion (validates scale)
4. **What enables future features?** → Transitive dependencies
5. **What's the quickest win?** → PyPI resolution improvement

**Recommendation**: Start with dataset expansion (200-500 repos), then decide between transitive dependencies or risk propagation based on what patterns emerge.

---

## Summary

**Immediate**: Review validation results (5 min)  
**Optional**: Run Phase 3 provider swap test (10 min)  
**Next Feature**: Expand dataset to 200-500 repos (2-4 hours)  
**After That**: Re-validate and decide next priority

**Key Insight**: You're past the "does it work?" phase. Now it's "what should it do next?" The validation proved the foundation is solid. Build on it.

---

**Created**: 2026-03-04  
**Status**: Ready for next phase
