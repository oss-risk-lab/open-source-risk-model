# Tasks Document Improvements Applied

## Summary

Applied 7 critical improvements to the dataset expansion spec based on user feedback. These changes reduce risk of expensive failures, prevent API rate explosion, and make the implementation more practical and reproducible.

## Improvements Applied

### 1. Property Number Corrections ✅

**Issue**: Tasks referenced incorrect property numbers (27/28 vs 29/30 for backup, 30 vs 32 for report)

**Fix**: Verified design document has correct property numbers:
- Property 27: Backup Creation
- Property 28: Backup Timestamp Naming  
- Property 29: Rollback Round-Trip
- Property 30: Expansion Report Completeness

Tasks now reference correct property numbers matching the design.

### 2. Ecosystem Inference - Bounded + Cached ✅

**Issue**: Scanning repo contents via GitHub Contents API can explode API rate usage in large repos/monorepos

**Fix**: Implemented 3-phase bounded approach with caching:
- **Phase 1**: Check root-level manifests only (fast, 1 API call)
- **Phase 2**: If none found, check common subpaths allowlist (/frontend, /backend, /packages, /apps, /src - max 5 paths)
- **Phase 3**: Only if still none found, do deeper scan with hard cap (max 10 API calls)
- **Cache**: Store results in `data/ecosystem_cache.json` to avoid re-hitting API on reruns

**Updated Files**:
- `tasks.md` - Task 1.5 now includes bounded approach
- `design.md` - Ecosystem Inference Algorithm section rewritten with full implementation

### 3. Explicit Quota Definitions ✅

**Issue**: "Quota-based selection" was ambiguous about minimum counts

**Fix**: Made quotas explicit for 149 new repos (to reach 200 total):
- npm: 38-60 repos (25-40% of 200 total)
- pypi: 38-60 repos (25-40% of 200 total)
- go: ≥15 repos (≥10% of 200 total)
- maven: ≥15 repos (≥10% of 200 total)
- rubygems: ≥8 repos (≥5% of 200 total)

Computed as `ceil(min_pct * target_total)` to ensure integer counts.

**Updated Files**:
- `tasks.md` - Task 1.10 includes explicit quotas
- `design.md` - Repository Selection Algorithm includes explicit quotas with comment

### 4. Test Priorities Documented ✅

**Issue**: Property tests are great but can slow shipping; need to focus on tests that prevent expensive failures

**Fix**: Added "Test Priorities" section to Notes with top 5 priorities:
1. Selection exact count + ecosystem quotas + excludes existing repos
2. Backoff logic with fake clock (unit test, not property test)
3. Orchestrator "backup happens before ingest"
4. Validator correctness for counts/resolution/distribution
5. Report generator "doesn't crash" and contains key sections

**Updated Files**:
- `tasks.md` - Notes section includes test priorities
- `tasks.md` - Priority tests marked with "(PRIORITY: prevents expensive failures)" or "(PRIORITY: prevents crashes)"

### 5. Preflight Validation Added ✅

**Issue**: Burning 10+ hours on full 149-repo ingestion only to discover a bad assumption

**Fix**: Added preflight validation step:
- Run ingestion on 10 repos from selected list
- Validate resolution rate, ecosystem classification, basic query patterns
- If preflight passes, proceed with full 149-repo run
- Prevents wasting hours on bad assumptions

**Updated Files**:
- `tasks.md` - Checkpoint 3 now includes preflight validation
- `design.md` - Phase 2 deliverables and validation include preflight

### 6. Resolution Definition Clarified ✅

**Issue**: Need to confirm what "metadata retrieved" means and verify SQL query is correct

**Fix**: Clarified resolution definition with THREE criteria:
1. `registry_type IS NOT NULL AND registry_type != ''`
2. `specifier IS NOT NULL`
3. `resolved_repo IS NOT NULL AND resolution_confidence IS NOT NULL`

**Note**: `resolved_repo` column stores the GitHub repository that provides the package (e.g., "facebook/react" for npm package "react"). This proves the package was matched to the registry and metadata was retrieved.

**Verified Against Schema**: Checked `src/open_source_risk_model/persistence/db.py` - `repo_dependencies` table has all required fields.

**Updated Files**:
- `tasks.md` - Task 4.5 includes three-criteria definition with note about resolved_repo
- `tasks.md` - Notes section clarifies resolution definition
- `design.md` - Resolution Rate Calculation algorithm already had correct SQL

### 7. Stable + Reproducible Selection Output ✅

**Issue**: Need to reproduce exact repository list later for debugging/analysis

**Fix**: Enhanced populate_popular_repos.py to include:
- Deterministic seed/sorting key for reproducible selection
- Output file includes `generated_at` timestamp
- Output file includes selection criteria used
- Filename format: `repos_YYYYMMDD_HHMMSS.json`

**Updated Files**:
- `tasks.md` - Task 1.12 includes stability requirements

## Impact Assessment

### Risk Reduction
- **API Rate Explosion**: Bounded ecosystem inference prevents hitting rate limits during selection
- **Expensive Failures**: Preflight validation catches issues before 10+ hour ingestion
- **Test Velocity**: Prioritized tests focus on high-impact failure modes

### Reproducibility
- **Selection Output**: Deterministic seed + timestamp + criteria enable exact reproduction
- **Ecosystem Cache**: Cached results prevent re-hitting API on reruns

### Clarity
- **Explicit Quotas**: No ambiguity about minimum ecosystem counts
- **Resolution Definition**: Three-criteria definition with schema verification
- **Test Priorities**: Clear guidance on which tests matter most

## Files Modified

1. `.kiro/specs/dataset-expansion-200-repos/tasks.md` - 10 task updates + notes section
2. `.kiro/specs/dataset-expansion-200-repos/design.md` - 3 algorithm updates + phase 2 deliverables
3. `.kiro/specs/dataset-expansion-200-repos/TASKS_IMPROVEMENTS.md` - This summary document

## Next Steps

The spec is now ready for implementation. Start with Phase 1 (Repository Selection) and follow the test priorities to maximize confidence while minimizing rework.

Key implementation order:
1. Bounded ecosystem inference with caching (Task 1.5)
2. Quota-based selection with explicit quotas (Task 1.10)
3. Priority tests (Tasks 1.14, 1.4, 2.4, 4.6, 7.2)
4. Preflight validation before full run (Checkpoint 3)
