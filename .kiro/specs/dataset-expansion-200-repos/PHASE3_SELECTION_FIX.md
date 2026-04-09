# Phase 3 Selection Criteria Fix - Complete

## Problem

The repository selection was returning "0 candidates" after the recency filter, preventing progress on dataset expansion.

## Root Cause

The issue was with timezone-aware datetime comparison in the `_filter_by_recency` method. The GitHub API returns timezone-aware datetimes (with 'Z' suffix), but we were comparing them against naive datetimes, causing all comparisons to fail.

## Changes Implemented

### 1. Updated SelectionCriteria Model (`src/open_source_risk_model/expansion/models.py`)

**Changed:**
- Renamed `min_commit_age_days` → `max_days_since_commit` (365 days)
- Updated from 180 days to 365 days for broader selection pool
- Improved parameter naming for clarity

**Rationale:** The new name `max_days_since_commit` is clearer - it represents the maximum number of days since the last commit (i.e., repos must have been active within the last N days).

### 2. Implemented Two-Pass Fallback (`src/open_source_risk_model/expansion/repo_selector.py`)

**Added `_apply_two_pass_fallback()` method:**
- **Pass A**: stars >= 1000, recency <= 180 days (high quality, recent)
- **Pass B**: stars >= 1000, recency <= 365 days (high quality, less recent)
- **Pass C**: stars >= 500, recency <= 365 days (lower quality bar)

**Rationale:** This guarantees we find enough candidates while preserving quality. Each pass relaxes constraints progressively.

### 3. Fixed Recency Filter Logic (`_filter_by_recency()`)

**Fixed:**
- Proper timezone handling: convert timezone-aware datetimes to naive for comparison
- Added detailed logging to show cutoff date and filter results
- Verified logic: `pushed_at >= cutoff_date` correctly keeps recent repos

**Before:**
```python
pushed_at = datetime.fromisoformat(candidate['pushed_at'].replace('Z', '+00:00'))
if pushed_at >= cutoff_date:  # Comparison failed due to timezone mismatch
```

**After:**
```python
pushed_at = datetime.fromisoformat(candidate['pushed_at'].replace('Z', '+00:00'))
pushed_at_naive = pushed_at.replace(tzinfo=None)
if pushed_at_naive >= cutoff_date:  # Now works correctly
```

### 4. Enhanced Logging

**Added:**
- Query-level logging showing results per GitHub search query
- Pass-level logging showing candidate counts after each fallback pass
- Recency filter logging showing cutoff date and kept/total counts

**Example output:**
```
INFO - Querying GitHub: stars:>1000 language:python
INFO -   Found 200 repos for query: stars:>1000 language:python
INFO - Total repos from all queries: 1200
INFO - Unique repos after deduplication: 1200
INFO - Pass A: Trying stars >= 1000, recency <= 180 days
INFO - Recency filter: keeping repos pushed after 2025-09-06T15:36:35
INFO - Recency filter: kept 954/1200 repos
INFO - Pass A: 954 candidates
INFO - Pass A succeeded with 954 candidates
```

### 5. Updated Scripts

**Updated `scripts/select_expansion_repos.py`:**
- Changed `min_commit_age_days` → `max_days_since_commit`
- Updated default from 180 to 365 days

**Updated `scripts/expand_dataset.py`:**
- Changed output JSON to use `max_days_since_commit`

### 6. Fixed Test Fixtures

**Updated `test/expansion/test_repo_selector.py`:**
- Added `repo_dependencies` table to test database fixture
- Prevents `sqlite3.OperationalError: no such table` errors

## Validation Results

### Test Results
All unit tests passing:
```
test/expansion/test_repo_selector.py::TestRepositorySelection::test_selection_produces_exact_count PASSED
test/expansion/test_repo_selector.py::TestRepositorySelection::test_ecosystem_quotas_are_met PASSED
test/expansion/test_repo_selector.py::TestRepositorySelection::test_excludes_existing_repos PASSED
test/expansion/test_repo_selector.py::TestRepositorySelection::test_priority_ordering PASSED
test/expansion/test_repo_selector.py::TestRepositorySelection::test_duplicate_exclusion PASSED
test/expansion/test_repo_selector.py::TestRepositorySelection::test_error_handling PASSED
```

### Live GitHub API Test
Verified with real GitHub API:
- Queried 1200 repos across 6 languages
- Pass A (180 days): **954 candidates** ✅
- After fork filter: **954 candidates** ✅
- After existing repo filter: **922 candidates** ✅

**Result:** Selection now finds 900+ candidates (target: 149), ensuring sufficient pool for ecosystem distribution.

## Next Steps

### Immediate: Phase 3 Checkpoint - Preflight Validation

Before running the full 149-repo expansion, we should:

1. **Run preflight validation on 10 repos** from the selected list:
   ```bash
   # Select 10 repos
   python scripts/select_expansion_repos.py --count 10 --output data/preflight_repos.json
   
   # Ingest them
   python scripts/expand_dataset.py --repos-file data/preflight_repos.json --db-path data/graphs_preflight.db
   
   # Validate
   python scripts/validate_expansion.py --db-path data/graphs_preflight.db --expected-repo-count 10
   ```

2. **Verify:**
   - Resolution rate >= 85%
   - Ecosystem classification works correctly
   - Basic query patterns work
   - No unexpected errors

3. **If preflight passes:** Proceed with full 149-repo selection and ingestion

### Phase 8: Production Expansion

Once preflight validation passes:

1. Generate full 149-repo selection list
2. Create production database backup
3. Execute batch ingestion (allow 24 hours)
4. Run full validation suite
5. Run signal quality analysis
6. Generate expansion report

## Files Changed

- `src/open_source_risk_model/expansion/models.py` - Updated SelectionCriteria
- `src/open_source_risk_model/expansion/repo_selector.py` - Two-pass fallback + fixed recency filter
- `scripts/select_expansion_repos.py` - Updated parameter name
- `scripts/expand_dataset.py` - Updated output JSON
- `test/expansion/test_repo_selector.py` - Fixed test fixture

## Summary

The "0 candidates" issue is **RESOLVED**. The selection now successfully finds 900+ candidates with the two-pass fallback strategy, ensuring we can select 149 high-quality repositories for dataset expansion.

**Key improvements:**
- ✅ Fixed timezone handling in date comparisons
- ✅ Implemented progressive fallback strategy
- ✅ Enhanced logging for debugging
- ✅ All tests passing
- ✅ Verified with live GitHub API

**Ready for:** Phase 3 Checkpoint - Preflight Validation (10-repo test run)
