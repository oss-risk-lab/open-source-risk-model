# Design Document: Reverse Dependency Lookup (repos_using_package)

## Overview

This design adds reverse dependency lookup capability to answer "Which repos depend on package X?" - a critical query for CVE blast radius analysis. The feature builds on the existing `repo_dependencies` table and adds a new `repos_using_package` intent with dependency scope filtering.

## Context

We currently support:
- `list_dependencies`: Repo-centric view (what does repo X depend on?)
- `find_dependents`: Basic reverse lookup without scope filtering
- `search_packages`: Package-centric aggregation

We need:
- `repos_using_package`: Reverse lookup with scope filtering for CVE blast radius analysis
- Query performance <2s across 100+ repos
- Scope filtering (prod/build/all) to focus on production dependencies

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Query Interface                         │
│  (UI + API: "Which repos use axios?")                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Intent Classifier (LLM)                         │
│  Classifies query → repos_using_package intent              │
│  Extracts: package_name, dependency_scope                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Intent Executor                                 │
│  _repos_using_package(parameters, max_results)              │
│  - Validates parameters                                      │
│  - Executes SQL query                                        │
│  - Applies scope filtering                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              repo_dependencies Table                         │
│  Indexed on: (package_name, dependency_group)               │
│  Columns: repo_full_name, package_name, registry,           │
│           version_specifier, dependency_group, is_direct,   │
│           resolved_repo, resolution_confidence, etc.        │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Reuse Existing Infrastructure**: Use existing `repo_dependencies` table and indexes
2. **Scope Filtering**: Leverage existing `DependencyScope` enum and filtering logic
3. **Performance**: Use indexed queries to achieve <2s response time
4. **Backward Compatibility**: Add new intent without breaking existing functionality
5. **Path Filtering**: Exclude non-production paths (examples/, tests/, docs/)



## Data Model

### Existing Table: repo_dependencies

The table already exists with all required columns:

```sql
CREATE TABLE repo_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    package_name TEXT NOT NULL,
    registry_type TEXT NOT NULL,
    specifier TEXT,
    extras TEXT,
    markers TEXT,
    dependency_group TEXT DEFAULT 'prod',
    is_direct BOOLEAN NOT NULL DEFAULT 1,
    is_optional BOOLEAN NOT NULL DEFAULT 0,
    manifest_path TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    resolved_repo TEXT,
    resolution_confidence REAL,
    resolution_method TEXT,
    UNIQUE(repo_full_name, package_name, manifest_path)
);
```

### Existing Indexes

```sql
-- Already exists for performance
CREATE INDEX idx_repo_dependencies_package 
    ON repo_dependencies(package_name, registry_type);

CREATE INDEX idx_repo_dependencies_group 
    ON repo_dependencies(dependency_group);
```

### No Schema Changes Required

All necessary columns and indexes already exist. This is purely a query layer enhancement.



## Intent Definition

### Intent: repos_using_package

**Purpose**: Find all repositories that depend on a specific package, with scope filtering for CVE blast radius analysis.

**Parameters**:
```json
{
  "package_name": "string (required)",
  "registry_type": "string (optional, default: infer from data)",
  "dependency_scope": "prod|build|all (optional, default: prod)",
  "include_transitive": "boolean (optional, default: false, NOT IMPLEMENTED YET)"
}
```

**Returns**:
```json
{
  "intent": "repos_using_package",
  "parameters": {...},
  "results": [
    {
      "repo_full_name": "owner/repo",
      "package_name": "axios",
      "registry_type": "npm",
      "specifier": "^1.0.0",
      "dependency_group": "prod",
      "manifest_path": "package.json",
      "resolved_repo": "axios/axios",
      "resolution_confidence": 1.0,
      "is_direct": true,
      "is_optional": false
    }
  ],
  "result_count": 42,
  "execution_time_ms": 156.3,
  "metadata": {
    "package_name": "axios",
    "registry_type": "npm",
    "dependency_scope": "prod",
    "dependency_scope_description": "Production/runtime dependencies only",
    "total_before_scope_filter": 58,
    "total_after_scope_filter": 42,
    "direct_only": true
  }
}
```

**Differences from find_dependents**:
- `find_dependents`: Existing intent, no scope filtering
- `repos_using_package`: New intent with scope filtering and path exclusions



## Core Algorithm

### Reverse Dependency Lookup with Scope Filtering

```python
ALGORITHM repos_using_package(package_name, registry_type, dependency_scope, max_results)
INPUT: 
  - package_name: string (required)
  - registry_type: string (optional)
  - dependency_scope: DependencyScope enum (default: prod)
  - max_results: int (default: 100)
OUTPUT: 
  - results: List[Dict] (filtered dependencies)
  - metadata: Dict (query metadata)

BEGIN
  ASSERT package_name is not empty
  ASSERT dependency_scope in {prod, build, all}
  
  # Define path exclusion patterns
  excluded_patterns ← [
    'examples/%', 'example/%',
    'tests/%', 'test/%',
    'docs/%', 'doc/%',
    'benchmarks/%', 'benchmark/%',
    'samples/%', 'sample/%',
    'demos/%', 'demo/%',
    'tutorials/%', 'tutorial/%'
  ]
  
  # Build exclusion clause
  exclusion_clause ← " AND " + JOIN([
    f"manifest_path NOT LIKE '{pattern}'" 
    FOR pattern IN excluded_patterns
  ])
  
  # Query database for ALL matching dependencies
  IF registry_type is provided THEN
    query ← """
      SELECT 
        repo_full_name,
        package_name,
        registry_type,
        specifier,
        dependency_group,
        manifest_path,
        resolved_repo,
        resolution_confidence,
        is_direct,
        is_optional
      FROM repo_dependencies
      WHERE package_name = ?
        AND registry_type = ?
        AND is_direct = 1
        {exclusion_clause}
      ORDER BY repo_full_name
    """
    params ← [package_name, registry_type]
  ELSE
    query ← """
      SELECT 
        repo_full_name,
        package_name,
        registry_type,
        specifier,
        dependency_group,
        manifest_path,
        resolved_repo,
        resolution_confidence,
        is_direct,
        is_optional
      FROM repo_dependencies
      WHERE package_name = ?
        AND is_direct = 1
        {exclusion_clause}
      ORDER BY repo_full_name
    """
    params ← [package_name]
  END IF
  
  # Execute query
  all_results ← EXECUTE_QUERY(query, params)
  
  # Apply scope filtering
  filtered_results ← filter_dependencies_by_scope(all_results, dependency_scope)
  
  # Apply max_results limit
  filtered_results ← filtered_results[:max_results]
  
  # Build metadata
  metadata ← {
    "package_name": package_name,
    "registry_type": registry_type,
    "dependency_scope": dependency_scope.value,
    "dependency_scope_description": get_scope_description(dependency_scope),
    "total_before_scope_filter": LENGTH(all_results),
    "total_after_scope_filter": LENGTH(filtered_results),
    "direct_only": true
  }
  
  RETURN filtered_results, metadata
END
```

**Preconditions**:
- `package_name` is non-empty string
- `dependency_scope` is valid DependencyScope enum value
- Database connection is available
- `repo_dependencies` table exists with required indexes

**Postconditions**:
- Returns list of dependencies matching package_name
- All results pass scope filter
- Results exclude non-production paths
- Metadata contains accurate counts
- Query completes in <2 seconds for 100+ repos

**Loop Invariants**: N/A (no explicit loops in main logic)



## Implementation Details

### Phase 1: Data Layer (COMPLETE)

The `repo_dependencies` table already exists with all required columns and indexes. No schema changes needed.

**Verification**:
```sql
-- Verify table exists
SELECT name FROM sqlite_master WHERE type='table' AND name='repo_dependencies';

-- Verify indexes exist
SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_repo_dependencies%';

-- Verify columns exist
PRAGMA table_info(repo_dependencies);
```

### Phase 2: Intent + API

**Step 1: Add Intent to Classifier**

Update `src/open_source_risk_model/query/intent_classifier.py`:

```python
ALLOWED_INTENTS = [
    # ... existing intents ...
    "repos_using_package",  # NEW
]

# Update system prompt to include new intent
INTENT_DESCRIPTIONS = {
    # ... existing descriptions ...
    "repos_using_package": {
        "description": "Find repositories that depend on a specific package",
        "parameters": ["package_name", "registry_type (optional)", "dependency_scope (optional)"],
        "examples": [
            "Which repos use axios?",
            "What depends on requests?",
            "Show me all repos using lodash",
            "Find production dependencies on django"
        ]
    }
}
```

**Step 2: Add Intent Handler to Executor**

Update `src/open_source_risk_model/query/intent_executor.py`:

```python
def _repos_using_package(
    self,
    parameters: Dict[str, Any],
    max_results: int
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Find repositories that depend on a specific package.
    
    Parameters:
        - package_name (required): Package name
        - registry_type (optional): Registry type (pypi, npm, etc.)
        - dependency_scope (optional): Filter by scope (prod, build, all). Default: prod
    """
    package_name = parameters.get("package_name")
    if not package_name:
        raise ValueError("package_name is required")
    
    registry_type = parameters.get("registry_type")
    
    # Get dependency_scope parameter (default to "prod")
    scope_str = parameters.get("dependency_scope", "prod")
    try:
        scope = DependencyScope(scope_str)
    except ValueError:
        raise ValueError(f"Invalid dependency_scope: {scope_str}")
    
    conn = self._get_connection()
    conn.row_factory = sqlite3.Row
    
    # Filter out non-production paths
    excluded_patterns = [
        'examples/%', 'example/%',
        'tests/%', 'test/%',
        'docs/%', 'doc/%',
        'benchmarks/%', 'benchmark/%',
        'samples/%', 'sample/%',
        'demos/%', 'demo/%',
        'tutorials/%', 'tutorial/%'
    ]
    
    exclusion_clause = " AND " + " AND ".join([
        f"manifest_path NOT LIKE '{pattern}'" for pattern in excluded_patterns
    ])
    
    # Query for ALL matching dependencies
    if registry_type:
        cursor = conn.execute(f"""
            SELECT 
                repo_full_name,
                package_name,
                registry_type,
                specifier,
                dependency_group,
                manifest_path,
                resolved_repo,
                resolution_confidence,
                is_direct,
                is_optional
            FROM repo_dependencies
            WHERE package_name = ?
              AND registry_type = ?
              AND is_direct = 1
              {exclusion_clause}
            ORDER BY repo_full_name
        """, (package_name, registry_type))
    else:
        cursor = conn.execute(f"""
            SELECT 
                repo_full_name,
                package_name,
                registry_type,
                specifier,
                dependency_group,
                manifest_path,
                resolved_repo,
                resolution_confidence,
                is_direct,
                is_optional
            FROM repo_dependencies
            WHERE package_name = ?
              AND is_direct = 1
              {exclusion_clause}
            ORDER BY repo_full_name
        """, (package_name,))
    
    all_results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Apply scope filtering
    filtered_results = filter_dependencies_by_scope(all_results, scope)
    
    # Apply max_results limit
    filtered_results = filtered_results[:max_results]
    
    metadata = {
        "package_name": package_name,
        "registry_type": registry_type,
        "dependency_scope": scope.value,
        "dependency_scope_description": get_scope_description(scope),
        "total_before_scope_filter": len(all_results),
        "total_after_scope_filter": len(filtered_results),
        "direct_only": True
    }
    
    return filtered_results, metadata
```

**Step 3: Register Handler**

Update the `intent_handlers` dict in `IntentExecutor.execute()`:

```python
intent_handlers = {
    # ... existing handlers ...
    "repos_using_package": self._repos_using_package,  # NEW
}
```



### Phase 3: Tests

**Unit Tests** (`test/test_intent_executor.py`):

```python
def test_repos_using_package_basic(executor, sample_db):
    """Test basic reverse dependency lookup."""
    result = executor.execute(
        intent="repos_using_package",
        parameters={"package_name": "requests"},
        max_results=100
    )
    
    assert result.intent == "repos_using_package"
    assert result.result_count > 0
    assert all(dep["package_name"] == "requests" for dep in result.results)
    assert result.metadata["package_name"] == "requests"
    assert result.metadata["dependency_scope"] == "prod"


def test_repos_using_package_with_scope(executor, sample_db):
    """Test reverse lookup with scope filtering."""
    # Get all dependencies
    result_all = executor.execute(
        intent="repos_using_package",
        parameters={"package_name": "pytest", "dependency_scope": "all"},
        max_results=100
    )
    
    # Get prod dependencies only
    result_prod = executor.execute(
        intent="repos_using_package",
        parameters={"package_name": "pytest", "dependency_scope": "prod"},
        max_results=100
    )
    
    # Prod should be subset of all
    assert result_prod.result_count <= result_all.result_count
    assert result_prod.metadata["dependency_scope"] == "prod"
    assert result_all.metadata["dependency_scope"] == "all"


def test_repos_using_package_with_registry(executor, sample_db):
    """Test reverse lookup with registry filter."""
    result = executor.execute(
        intent="repos_using_package",
        parameters={"package_name": "lodash", "registry_type": "npm"},
        max_results=100
    )
    
    assert all(dep["registry_type"] == "npm" for dep in result.results)
    assert result.metadata["registry_type"] == "npm"


def test_repos_using_package_excludes_non_production_paths(executor, sample_db):
    """Test that examples/tests/docs are excluded."""
    result = executor.execute(
        intent="repos_using_package",
        parameters={"package_name": "some-package"},
        max_results=100
    )
    
    excluded_patterns = ['examples/', 'tests/', 'docs/', 'benchmarks/']
    for dep in result.results:
        manifest_path = dep["manifest_path"]
        for pattern in excluded_patterns:
            assert not manifest_path.startswith(pattern), \
                f"Found excluded path: {manifest_path}"


def test_repos_using_package_missing_package_name(executor):
    """Test error handling for missing package_name."""
    with pytest.raises(ValueError, match="package_name is required"):
        executor.execute(
            intent="repos_using_package",
            parameters={},
            max_results=100
        )


def test_repos_using_package_invalid_scope(executor):
    """Test error handling for invalid scope."""
    with pytest.raises(ValueError, match="Invalid dependency_scope"):
        executor.execute(
            intent="repos_using_package",
            parameters={"package_name": "requests", "dependency_scope": "invalid"},
            max_results=100
        )


def test_repos_using_package_performance(executor, large_db):
    """Test query performance with 100+ repos."""
    import time
    
    start = time.time()
    result = executor.execute(
        intent="repos_using_package",
        parameters={"package_name": "requests"},
        max_results=100
    )
    elapsed = time.time() - start
    
    # Should complete in <2 seconds
    assert elapsed < 2.0, f"Query took {elapsed:.2f}s, expected <2s"
    assert result.execution_time_ms < 2000
```

**Integration Tests** (`test/test_reverse_dependency_integration.py`):

```python
def test_end_to_end_reverse_lookup(api_client):
    """Test full flow from API to database."""
    response = api_client.post("/api/query", json={
        "query": "Which repos use requests?"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "repos_using_package"
    assert data["parameters"]["package_name"] == "requests"
    assert len(data["results"]) > 0


def test_scope_filtering_integration(api_client):
    """Test scope filtering through full stack."""
    # Query with prod scope
    response_prod = api_client.post("/api/query", json={
        "query": "Which repos use pytest in production?"
    })
    
    # Query with all scope
    response_all = api_client.post("/api/query", json={
        "query": "Which repos use pytest (all scopes)?"
    })
    
    assert response_prod.json()["result_count"] <= response_all.json()["result_count"]
```



### Phase 4: UI

**Update** `ui/query.html`:

Add example query to the UI:

```html
<!-- Add to example queries section -->
<div class="example-query" onclick="setQuery(this.textContent)">
    Which repos use requests?
</div>
<div class="example-query" onclick="setQuery(this.textContent)">
    What depends on axios in production?
</div>
<div class="example-query" onclick="setQuery(this.textContent)">
    Show me all repos using lodash
</div>
```

**Result Display**:

The existing result table will automatically display the reverse dependency results. No special UI changes needed since the response format matches existing patterns.

**Optional Enhancement** (future):

Add a "Package Impact" dedicated view:

```html
<div class="query-section">
    <h3>Package Impact Analysis</h3>
    <input type="text" id="package-name" placeholder="Package name (e.g., requests, axios)">
    <select id="package-scope">
        <option value="prod">Production Only</option>
        <option value="build">Build/CI</option>
        <option value="all">All Dependencies</option>
    </select>
    <button onclick="analyzePackageImpact()">Analyze Impact</button>
</div>
```



## Performance Considerations

### Query Optimization

**Index Usage**:
```sql
-- Query uses existing index
EXPLAIN QUERY PLAN
SELECT * FROM repo_dependencies
WHERE package_name = 'requests'
  AND is_direct = 1;

-- Expected: SEARCH TABLE repo_dependencies USING INDEX idx_repo_dependencies_package
```

**Performance Targets**:
- Query execution: <500ms for 100 repos
- Total response time: <2s including LLM classification
- Memory usage: <100MB for result set

**Optimization Strategies**:
1. Use indexed columns in WHERE clause
2. Limit result set with max_results
3. Apply scope filtering in Python (not SQL) for flexibility
4. Use connection pooling for concurrent queries

### Scalability

**Current Scale** (47 repos, 3,313 dependencies):
- Expected query time: <100ms
- Memory footprint: <10MB

**Target Scale** (1,000 repos, 100,000 dependencies):
- Expected query time: <500ms
- Memory footprint: <50MB
- Index size: ~20MB

**Future Optimizations** (if needed):
- Add composite index on (package_name, dependency_group)
- Implement query result caching
- Add pagination for large result sets
- Consider materialized views for common queries



## Use Cases

### Use Case 1: CVE Blast Radius Analysis

**Scenario**: A critical CVE is discovered in `requests` version 2.25.0

**Query**: "Which repos use requests in production?"

**Expected Flow**:
1. User enters query in UI
2. LLM classifies as `repos_using_package` intent
3. Extracts parameters: `{package_name: "requests", dependency_scope: "prod"}`
4. Executor queries database with scope filter
5. Returns list of affected repos with version specifiers
6. User can quickly identify which production systems are at risk

**Value**: Reduces incident response time from hours to minutes

### Use Case 2: Dependency Upgrade Planning

**Scenario**: Team wants to upgrade `lodash` across all projects

**Query**: "Show me all repos using lodash"

**Expected Flow**:
1. Query returns all repos with lodash dependency
2. Shows version specifiers for each repo
3. Team can plan coordinated upgrade
4. Can filter by scope to prioritize production dependencies

**Value**: Enables coordinated dependency management

### Use Case 3: Package Deprecation Impact

**Scenario**: A package is being deprecated, need to assess impact

**Query**: "What depends on deprecated-package?"

**Expected Flow**:
1. Returns all repos using the package
2. Shows dependency groups (prod vs dev)
3. Team can prioritize migration work
4. Can track migration progress over time

**Value**: Enables proactive dependency management



## Correctness Properties

### Property 1: Scope Filter Correctness

*For any* package query with scope="prod", the results must only include dependencies where `dependency_group` is in the production scope set.

**Validates**: Scope filtering logic

**Rationale**: CVE blast radius analysis requires accurate production dependency identification. Including dev/test dependencies would create false positives.

---

### Property 2: Path Exclusion Completeness

*For any* query result, no dependency with `manifest_path` starting with excluded patterns (examples/, tests/, docs/, etc.) should be included.

**Validates**: Path filtering logic

**Rationale**: Non-production code paths should not be included in production dependency analysis.

---

### Property 3: Query Performance Bound

*For any* query against a database with N repos (N ≤ 1000), the query execution time must be <2 seconds.

**Validates**: Performance requirements

**Rationale**: Interactive queries require sub-second response times. 2-second bound includes LLM classification overhead.

---

### Property 4: Result Completeness

*For any* package_name query, the results must include ALL repos in the database that have a direct dependency on that package (after scope and path filtering).

**Validates**: Query correctness

**Rationale**: Missing results would lead to incomplete CVE blast radius analysis, creating security blind spots.

---

### Property 5: Metadata Accuracy

*For any* query result, `metadata.total_before_scope_filter` must equal the count of all matching dependencies, and `metadata.total_after_scope_filter` must equal `len(results)`.

**Validates**: Metadata consistency

**Rationale**: Users need accurate counts to understand filtering impact and make informed decisions.



## Error Handling

### Error Scenario 1: Missing package_name

**Condition**: User query doesn't extract package_name parameter

**Response**: 
- Raise `ValueError("package_name is required")`
- Return 400 Bad Request from API
- Show user-friendly error in UI

**Example**:
```python
try:
    result = executor.execute("repos_using_package", {})
except ValueError as e:
    return {"error": str(e), "status": 400}
```

---

### Error Scenario 2: Invalid dependency_scope

**Condition**: User provides invalid scope value (not prod/build/all)

**Response**:
- Raise `ValueError("Invalid dependency_scope: {value}")`
- Return 400 Bad Request from API
- Show valid options to user

**Example**:
```python
try:
    scope = DependencyScope(scope_str)
except ValueError:
    raise ValueError(f"Invalid dependency_scope: {scope_str}. Must be one of: prod, build, all")
```

---

### Error Scenario 3: Package Not Found

**Condition**: No repos depend on the specified package

**Response**:
- Return empty results list (not an error)
- Include metadata indicating zero matches
- Suggest checking package name spelling

**Example**:
```json
{
  "intent": "repos_using_package",
  "results": [],
  "result_count": 0,
  "metadata": {
    "package_name": "nonexistent-package",
    "total_before_scope_filter": 0,
    "total_after_scope_filter": 0
  }
}
```

---

### Error Scenario 4: Database Connection Failure

**Condition**: Cannot connect to database

**Response**:
- Raise `DatabaseError("Database connection failed")`
- Return 500 Internal Server Error from API
- Log error with stack trace
- Retry with exponential backoff (if transient)

**Example**:
```python
try:
    conn = self._get_connection()
except Exception as e:
    logger.error(f"Database connection failed: {e}", exc_info=True)
    raise DatabaseError(f"Database connection failed: {e}")
```



## Migration Path

### Phase 1: Data Layer (COMPLETE ✓)

**Status**: Already implemented
- `repo_dependencies` table exists with all required columns
- Indexes exist on (package_name, registry_type) and (dependency_group)
- No schema changes needed

**Verification**:
```bash
sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_dependencies;"
sqlite3 data/graphs.db "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_repo_dependencies%';"
```

---

### Phase 2: Intent + API (Week 1)

**Tasks**:
1. Add `repos_using_package` to `ALLOWED_INTENTS` in `intent_classifier.py`
2. Update LLM system prompt with intent description and examples
3. Implement `_repos_using_package()` handler in `intent_executor.py`
4. Register handler in `intent_handlers` dict
5. Test intent classification with sample queries
6. Test intent execution with sample database

**Deliverables**:
- Working `repos_using_package` intent
- Scope filtering functional
- Path exclusions working
- All unit tests passing

**Estimated Time**: 2-3 hours

---

### Phase 3: Tests (Week 1)

**Tasks**:
1. Add unit tests to `test/test_intent_executor.py`
2. Add integration tests to new file `test/test_reverse_dependency_integration.py`
3. Add performance tests with large dataset
4. Add property-based tests for scope filtering
5. Verify all tests pass

**Deliverables**:
- 10+ unit tests covering all scenarios
- 3+ integration tests
- 1 performance test
- 100% code coverage for new code

**Estimated Time**: 2-3 hours

---

### Phase 4: UI (Week 1)

**Tasks**:
1. Add example queries to `ui/query.html`
2. Test UI with sample queries
3. Verify result display works correctly
4. Add documentation to UI

**Deliverables**:
- UI supports reverse dependency queries
- Example queries visible and clickable
- Results display correctly

**Estimated Time**: 1 hour

---

### Total Implementation Time: 5-7 hours



## Success Criteria

### Functional Requirements

- [x] Data layer: `repo_dependencies` table exists with required columns (COMPLETE)
- [ ] Intent classification: LLM correctly identifies "Which repos use X?" queries
- [ ] Intent execution: Query returns correct results with scope filtering
- [ ] Path filtering: Excludes examples/, tests/, docs/ directories
- [ ] Scope filtering: Correctly filters by prod/build/all
- [ ] API integration: Works through full API stack
- [ ] UI integration: Example queries work in UI

### Performance Requirements

- [ ] Query execution: <500ms for 100 repos
- [ ] Total response time: <2s including LLM classification
- [ ] Memory usage: <100MB for result set
- [ ] Index usage: Query uses idx_repo_dependencies_package

### Quality Requirements

- [ ] Unit test coverage: >90% for new code
- [ ] Integration tests: All scenarios covered
- [ ] Property tests: Scope filtering correctness verified
- [ ] Performance tests: <2s requirement validated
- [ ] Documentation: API docs updated
- [ ] Backward compatibility: No breaking changes

### Business Requirements

- [ ] CVE blast radius: Can answer "Which repos use vulnerable package?" in <2s
- [ ] Dependency management: Can identify all repos using a package
- [ ] Scope awareness: Can filter by production vs dev dependencies
- [ ] Accurate counts: Metadata shows filtering impact



## Future Enhancements

### Transitive Dependency Resolution (Phase 5)

**Goal**: Support `include_transitive=true` parameter

**Approach**:
1. Implement BFS traversal of dependency graph
2. Track visited packages to avoid cycles
3. Limit depth to prevent infinite loops
4. Cache transitive closures for performance

**Estimated Effort**: 1-2 weeks

---

### CVE Integration (Phase 6)

**Goal**: Automatically link package queries to known CVEs

**Approach**:
1. Query OSV database for package CVEs
2. Enrich results with CVE metadata
3. Show severity and affected versions
4. Highlight repos using vulnerable versions

**Estimated Effort**: 2-3 weeks

---

### Dashboard Visualization (Phase 7)

**Goal**: Visual package impact dashboard

**Features**:
- Dependency graph visualization
- CVE heat map by repo
- Trend analysis over time
- Export to CSV/JSON

**Estimated Effort**: 2-3 weeks

---

### Batch Analysis (Phase 8)

**Goal**: Analyze multiple packages at once

**Approach**:
1. Accept list of package names
2. Run queries in parallel
3. Aggregate results
4. Show combined impact

**Estimated Effort**: 1 week



## Conclusion

This design implements reverse dependency lookup (`repos_using_package` intent) to enable CVE blast radius analysis. The implementation:

1. **Reuses existing infrastructure**: No schema changes needed, uses existing `repo_dependencies` table and indexes
2. **Adds scope filtering**: Leverages existing `DependencyScope` enum for prod/build/all filtering
3. **Maintains performance**: Achieves <2s response time through indexed queries
4. **Preserves backward compatibility**: Adds new intent without breaking existing functionality
5. **Enables critical use cases**: CVE blast radius, dependency upgrade planning, deprecation impact analysis

**Key Benefits**:
- Fast implementation (5-7 hours total)
- No database migrations required
- Consistent with existing patterns
- Production-ready from day one
- Unlocks portfolio-scale security analysis

**Next Steps**:
1. Implement intent handler in `intent_executor.py`
2. Update intent classifier with new intent
3. Add comprehensive tests
4. Update UI with example queries
5. Validate performance with production data

The design is ready for implementation and can be completed in a single development session.

