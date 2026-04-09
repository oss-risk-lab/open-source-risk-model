# Production Dependencies Filter

## What Changed

Added filtering to exclude non-production dependencies from query results.

## Why

The ingestion was picking up dependencies from `examples/`, `tests/`, `docs/`, and other non-production directories. For example:
- Flask showed 39 dependencies (including examples)
- After filtering: 8 production dependencies

This gives a more accurate picture of actual production dependencies.

## What's Filtered Out

Dependencies from these paths are excluded:
- `examples/` and `example/`
- `tests/` and `test/`
- `docs/` and `doc/`
- `benchmarks/` and `benchmark/`
- `samples/` and `sample/`
- `demos/` and `demo/`
- `tutorials/` and `tutorial/`

## Impact

**Before filtering:**
- 3,691 total dependencies

**After filtering:**
- 3,313 production dependencies
- 378 non-production dependencies filtered out (10.2%)

## Where Applied

The filter is applied in these query intents:
1. `list_dependencies` - Lists direct dependencies
2. `repo_stats` - Repository statistics
3. `dataset_stats` - Overall dataset statistics

## Future Improvements

**Option A: Re-ingest with filtering**
- Update `manifest_discovery.py` to skip these paths during ingestion
- Re-run ingestion for all repos
- Cleaner data at the source

**Option B: Keep query-time filtering**
- Current approach (what we did)
- Faster to implement
- Can adjust filters without re-ingestion
- Good for demo purposes

**Recommendation:** Use Option B for demo, then do Option A for production.

## Testing

All tests pass with the new filtering:
```bash
pytest test/test_intent_executor.py -v
# 31 passed
```

## Demo Impact

The demo now shows more accurate numbers:
- "47 repos with 3,313 production dependencies"
- Flask example shows 8 deps instead of 39
- More credible and professional

## Code Changes

1. **manifest_discovery.py** - Added `EXCLUDED_PATHS` and `_is_excluded_path()` method
2. **intent_executor.py** - Added filtering to `_list_dependencies()`, `_repo_stats()`, and `_dataset_stats()`

## Example

**Flask dependencies before:**
```
39 dependencies (including examples/celery/*, examples/javascript/*, etc.)
```

**Flask dependencies after:**
```
8 production dependencies:
- asgiref
- blinker
- click
- itsdangerous
- jinja2
- markupsafe
- python-dotenv
- werkzeug
```

Much cleaner and more accurate! ✅
