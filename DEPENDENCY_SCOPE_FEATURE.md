# Dependency Scope Feature

## Overview

Added `dependency_scope` parameter to `list_dependencies` intent to control which dependencies are returned based on their purpose (production, build/CI, or all).

## Motivation

Users need visibility into non-production dependencies (dev, test, build tooling) because they matter for CI/build supply-chain risk. Previously, only production dependencies were shown.

## Implementation

### 1. Scope Enum

Created `DependencyScope` enum with three values:
- `prod`: Production/runtime dependencies only (default)
- `build`: Production + dev/test/build dependencies
- `all`: Everything including optional extras

### 2. Filtering Logic

Implemented `filter_dependencies_by_scope()` function that:
- Maps dependency groups to scopes
- Respects `is_optional` flag
- Handles case-insensitive group matching
- Ensures prod ⊆ build ⊆ all

### 3. Group Mappings

**Production groups:**
- prod, runtime, standard, peer, "" (empty)

**Build groups:**
- dev, test, lint, docs, ci, build, tooling, github-actions, typing

**Optional groups:**
- async, dotenv, speedups, cli, brotli, jupyter, argon2, bcrypt, colorama, completion, http2, i18n, socks, uvloop, watchdog, zstd

### 4. API Changes

Updated `IntentExecutor._list_dependencies()` to:
- Accept `dependency_scope` parameter (default: "prod")
- Validate scope value
- Apply scope filtering after path filtering
- Return scope metadata

### 5. UI Changes

Added dropdown to `ui/query.html`:
- Options: Production, Build/CI, All
- Default: Production
- Automatically passed to `list_dependencies` queries
- Shows scope badge in results

### 6. Documentation

Updated `QUERY_API_QUICK_START.md` with:
- Parameter description
- Scope semantics
- Example queries for each scope
- Metadata fields

## Usage Examples

### Production Dependencies Only (Default)

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "list_dependencies",
    "parameters": {
      "repo_full_name": "pallets/flask"
    }
  }'
```

Returns: 8 production dependencies

### Build/CI Dependencies

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "list_dependencies",
    "parameters": {
      "repo_full_name": "pallets/flask",
      "dependency_scope": "build"
    }
  }'
```

Returns: Production + dev/test dependencies

### All Dependencies

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "list_dependencies",
    "parameters": {
      "repo_full_name": "pallets/flask",
      "dependency_scope": "all"
    }
  }'
```

Returns: Everything including optional extras

## Response Metadata

The response includes additional metadata:

```json
{
  "metadata": {
    "repo_full_name": "pallets/flask",
    "dependency_scope": "prod",
    "dependency_scope_description": "Production/runtime dependencies only",
    "direct_only": true,
    "total_before_scope_filter": 12,
    "total_after_scope_filter": 8
  }
}
```

## Testing

### Unit Tests

`test/test_dependency_scope.py` (27 tests):
- Enum validation
- Scope descriptions
- Filtering logic
- Subset relationships (prod ⊆ build ⊆ all)
- Group mappings
- Edge cases

### Integration Tests

`test/test_intent_executor.py::TestDependencyScope` (8 tests):
- Default scope is prod
- Explicit scope parameters
- Scope ordering
- Invalid scope handling
- Metadata validation

All tests pass ✅

## Backward Compatibility

- Default behavior unchanged (scope="prod")
- Existing clients without `dependency_scope` parameter work as before
- Response schema unchanged (only metadata added)
- No breaking changes

## Files Changed

1. `src/open_source_risk_model/query/dependency_scope.py` - New file with scope logic
2. `src/open_source_risk_model/query/intent_executor.py` - Updated `_list_dependencies()`
3. `ui/query.html` - Added scope dropdown and badge
4. `test/test_dependency_scope.py` - New unit tests
5. `test/test_intent_executor.py` - Added integration tests
6. `QUERY_API_QUICK_START.md` - Updated documentation

## Future Enhancements

Potential improvements:
1. Add scope parameter to `get_dependency_tree` intent
2. Add scope parameter to `repo_stats` intent
3. Support custom scope definitions
4. Add scope-based filtering to other intents

## Demo Impact

For the demo with your dad:
- Can now show "Flask has 8 production dependencies"
- Can demonstrate build/CI dependencies separately
- Shows understanding of different dependency types
- Demonstrates clean API design with sensible defaults

## Summary

The dependency scope feature provides fine-grained control over which dependencies are returned, enabling users to analyze production, build, and optional dependencies separately. The implementation is clean, well-tested, and backward-compatible.

**Status:** ✅ Complete and tested
