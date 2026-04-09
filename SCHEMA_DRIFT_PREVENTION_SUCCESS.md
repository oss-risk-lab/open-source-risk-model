# ✅ Schema Drift Prevention - COMPLETE

## Problem Solved

**Critical Issue**: The dependency resolution feature worked on the existing database (after manual `ALTER TABLE` commands) but would fail on fresh installations because `init_database()` didn't create the resolution columns.

This is a classic "works on my machine" problem that leads to:
- Fresh installs failing with "no such column" errors
- Manual database surgery required for new setups
- Schema drift between development and production
- Broken CI/CD pipelines

## Solution Implemented

### 1. Updated Schema Definition
Added resolution columns to the canonical schema in `init_database()`:

```sql
CREATE TABLE repo_dependencies (
    ...
    resolved_repo TEXT,
    resolution_confidence REAL,
    resolution_method TEXT,
    ...
);

CREATE INDEX idx_repo_dependencies_resolved 
    ON repo_dependencies(resolved_repo);
```

### 2. Added Schema Migration Logic
Implemented `_migrate_schema()` function that:
- Runs BEFORE `CREATE TABLE IF NOT EXISTS` statements
- Checks if tables exist before attempting migrations
- Checks which columns exist before adding new ones
- Is completely idempotent (safe to run multiple times)
- Handles both fresh installs and existing databases

### 3. Refactored Service Layer
Updated `DependencyIngestionService` to use repository methods instead of direct DB access:

**Before** (Direct DB access):
```python
conn = get_connection(self.db_path)
conn.execute("UPDATE repo_dependencies SET resolved_repo = ? ...")
```

**After** (Repository pattern):
```python
self.dep_repo.update_resolution(
    repo_full_name, package_name, registry_type,
    resolved_repo, confidence, method
)
```

### 4. Created Drift Prevention Tests
Four comprehensive tests that fail if drift returns:

1. **T1: Fresh DB Resolution Updates** - Verifies fresh database supports resolution writes
2. **T2: Multi-Manifest Preservation** - Ensures saving one manifest doesn't delete others
3. **T3: Schema Has Resolution Columns** - Verifies columns exist in fresh schema
4. **T4: Schema Migration** - Tests that existing databases are upgraded automatically

## Test Results

```
============================================================
TEST SUMMARY
============================================================
Fresh DB Resolution Updates.................. ✅ PASSED
Multi-Manifest Preservation.................. ✅ PASSED
Schema Has Resolution Columns................ ✅ PASSED
Schema Migration............................. ✅ PASSED

Total: 4/4 tests passed

🎉 All tests passed! Schema is coherent and portable.
```

## Files Modified

1. **src/open_source_risk_model/persistence/db.py**
   - Added resolution columns to `CREATE TABLE repo_dependencies`
   - Added `idx_repo_dependencies_resolved` index
   - Implemented `_migrate_schema()` function
   - Reordered initialization to run migrations first

2. **src/open_source_risk_model/persistence/dependency_repo.py**
   - Added `update_resolution()` method
   - Proper separation of concerns (no raw SQL in services)

3. **src/open_source_risk_model/dependencies/ingestion_service.py**
   - Updated `_update_dependency_resolution()` to use repository method
   - Removed direct database access

4. **test_schema_drift_prevention.py** (NEW)
   - Comprehensive test suite to prevent future drift
   - Tests fresh installs, migrations, and multi-manifest behavior

## What This Prevents

### Before (Broken)
```bash
# Fresh install
$ python3 -c "from src...ingestion_service import *; service.ingest_repo(...)"
ERROR: no such column: resolved_repo

# Manual fix required
$ sqlite3 data/graphs.db "ALTER TABLE repo_dependencies ADD COLUMN resolved_repo TEXT"
$ sqlite3 data/graphs.db "ALTER TABLE repo_dependencies ADD COLUMN resolution_confidence REAL"
$ sqlite3 data/graphs.db "ALTER TABLE repo_dependencies ADD COLUMN resolution_method TEXT"
```

### After (Works)
```bash
# Fresh install - just works!
$ python3 -c "from src...ingestion_service import *; service.ingest_repo(...)"
✓ Success: 35 dependencies found, 32 resolved (91%)
```

## Key Principles Applied

1. **Single Source of Truth** - Schema defined once in `init_database()`
2. **Idempotent Migrations** - Safe to run multiple times
3. **Fail-Safe Design** - Checks before altering
4. **Repository Pattern** - Services use repositories, not raw SQL
5. **Test Coverage** - Tests that fail if drift returns

## Definition of Done

✅ Running ingestion on a brand new DB works without manual DB edits
✅ Tests T1-T4 all pass
✅ Schema migrations are idempotent
✅ Services use repository methods (no direct DB access)
✅ Multi-manifest preservation verified

## Impact

- **Fresh installs work** - No manual database surgery required
- **CI/CD friendly** - Tests run on clean databases
- **Production safe** - Existing databases migrate automatically
- **Developer friendly** - New team members can start immediately
- **Drift prevented** - Tests catch schema mismatches

## Next Steps (Optional Improvements)

1. Add schema version checking to warn about outdated databases
2. Create migration history table to track which migrations ran
3. Add rollback capability for migrations
4. Extend tests to cover more edge cases
5. Document migration process in DEPLOYMENT.md

## Conclusion

The schema drift issue has been completely resolved. The system now has:
- ✅ Portable schema that works on fresh installs
- ✅ Automatic migrations for existing databases
- ✅ Clean separation between services and persistence
- ✅ Comprehensive tests to prevent regression

**Status: ✅ COMPLETE AND TESTED**

All 4 drift prevention tests pass!
