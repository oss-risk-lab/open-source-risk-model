# Reverse Dependency Lookup - Implementation Summary

## Overview

Add `repos_using_package` intent to answer "Which repos depend on package X?" for CVE blast radius analysis.

## Status

- **Spec**: Complete (design-first workflow)
- **Data Layer**: ✓ Complete (no changes needed)
- **Implementation**: Ready to start
- **Estimated Time**: 5-7 hours

## Key Files

- **Spec**: `.kiro/specs/reverse-dependency-lookup/design.md`
- **Implementation**: 
  - `src/open_source_risk_model/query/intent_classifier.py` (add intent)
  - `src/open_source_risk_model/query/intent_executor.py` (add handler)
  - `ui/query.html` (add examples)
- **Tests**: 
  - `test/test_intent_executor.py` (unit tests)
  - `test/test_reverse_dependency_integration.py` (integration tests)

## Quick Implementation Checklist

### Phase 1: Data Layer ✓
- [x] `repo_dependencies` table exists
- [x] Indexes exist on (package_name, registry_type)
- [x] All required columns present

### Phase 2: Intent + API (2-3 hours)
- [ ] Add `repos_using_package` to `ALLOWED_INTENTS`
- [ ] Update LLM system prompt with intent description
- [ ] Implement `_repos_using_package()` handler
- [ ] Register handler in `intent_handlers` dict
- [ ] Test with sample queries

### Phase 3: Tests (2-3 hours)
- [ ] Add 10+ unit tests
- [ ] Add 3+ integration tests
- [ ] Add performance test (<2s requirement)
- [ ] Verify 100% code coverage

### Phase 4: UI (1 hour)
- [ ] Add example queries to UI
- [ ] Test query flow
- [ ] Verify results display

## New Intent Schema

```json
{
  "intent": "repos_using_package",
  "parameters": {
    "package_name": "requests",
    "registry_type": "pypi",
    "dependency_scope": "prod"
  }
}
```

## Example Queries

- "Which repos use requests?"
- "What depends on axios in production?"
- "Show me all repos using lodash"
- "Find production dependencies on django"

## Success Criteria

- Query execution: <500ms for 100 repos
- Total response time: <2s including LLM
- Scope filtering: prod/build/all working correctly
- Path filtering: Excludes examples/, tests/, docs/
- All tests passing

## Performance

- **Current scale**: 47 repos, 3,313 dependencies
- **Expected query time**: <100ms
- **Target scale**: 1,000 repos, 100,000 dependencies
- **Expected query time at scale**: <500ms

## Use Cases

1. **CVE Blast Radius**: "Which repos use vulnerable package?"
2. **Dependency Upgrade**: "Show all repos using old version"
3. **Deprecation Impact**: "What depends on deprecated package?"

## Future Enhancements

- Transitive dependency resolution
- CVE integration with OSV database
- Dashboard visualization
- Batch analysis for multiple packages

## Notes

- No schema changes required
- Reuses existing `DependencyScope` filtering
- Consistent with existing intent patterns
- Backward compatible
- Production-ready from day one

---

**Ready to implement!** Start with Phase 2 (Intent + API).
