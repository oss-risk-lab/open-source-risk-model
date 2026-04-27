# Week 2-3: Intent-Based Query API Design

**Status**: 🚧 IN PROGRESS  
**Started**: 2026-02-25

## North Star Constraints

1. **LLM never generates raw SQL** - Only classifies intent and extracts parameters
2. **Strict allowlist** - Only predefined query patterns allowed
3. **Database is source of truth** - No network calls in GET endpoints
4. **Compute on-the-fly** - No precomputed transitive edges or depth columns

## Architecture

```
User Query (Natural Language)
    ↓
Intent Classifier (LLM)
    ↓
Intent + Parameters
    ↓
Intent Executor (Hardcoded SQL)
    ↓
Results
```

## Intent Allowlist

### 1. Dependency Queries

**list_dependencies**
- Description: List direct dependencies of a repository
- Parameters: `repo_full_name`, `dependency_group` (optional)
- SQL: `SELECT * FROM repo_dependencies WHERE repo_full_name = ? AND is_direct = 1`
- Example: "What are the dependencies of django/django?"

**find_dependents**
- Description: Find repositories that depend on a package
- Parameters: `package_name`, `registry_type`
- SQL: `SELECT DISTINCT repo_full_name FROM repo_dependencies WHERE package_name = ? AND registry_type = ?`
- Example: "Which repos depend on requests?"

**get_dependency_tree**
- Description: Get dependency tree for a repository (computed on-the-fly)
- Parameters: `repo_full_name`, `max_depth` (default: 3)
- Algorithm: BFS traversal using resolved_repo links
- Example: "Show me the dependency tree for flask"

### 2. Resolution Queries

**check_resolution**
- Description: Check if a package resolves to a GitHub repo
- Parameters: `package_name`, `registry_type`
- SQL: `SELECT * FROM package_mappings WHERE package_name = ? AND registry_type = ?`
- Example: "Does numpy resolve to a GitHub repo?"

**list_unresolved**
- Description: List dependencies that couldn't be resolved
- Parameters: `repo_full_name` (optional)
- SQL: `SELECT * FROM repo_dependencies WHERE resolved_repo IS NULL`
- Example: "Show unresolved dependencies"

### 3. Manifest Queries

**list_manifests**
- Description: List manifest files for a repository
- Parameters: `repo_full_name`
- SQL: `SELECT DISTINCT manifest_path FROM repo_dependencies WHERE repo_full_name = ?`
- Example: "What manifest files does react have?"

**count_by_manifest_type**
- Description: Count dependencies by manifest type
- Parameters: None
- SQL: Aggregate query grouping by manifest file extension
- Example: "How many package.json vs requirements.txt files?"

### 4. Statistics Queries

**repo_stats**
- Description: Get statistics for a repository
- Parameters: `repo_full_name`
- SQL: Aggregate counts from repo_dependencies
- Example: "Give me stats for django/django"

**dataset_stats**
- Description: Get overall dataset statistics
- Parameters: None
- SQL: Aggregate across all repos
- Example: "How many repos and dependencies do we have?"

### 5. Search Queries

**search_repos**
- Description: Search repositories by name pattern
- Parameters: `pattern`
- SQL: `SELECT DISTINCT repo_full_name FROM repo_graphs WHERE repo_full_name LIKE ?`
- Example: "Find all repos with 'django' in the name"

**search_packages**
- Description: Search packages by name pattern
- Parameters: `pattern`, `registry_type` (optional)
- SQL: `SELECT DISTINCT package_name FROM repo_dependencies WHERE package_name LIKE ?`
- Example: "Find all packages starting with 'pytest'"

## Intent Classification

### LLM Prompt Template

```
You are a query intent classifier for a dependency graph database.

Available intents:
- list_dependencies: List direct dependencies of a repo
- find_dependents: Find repos that depend on a package
- get_dependency_tree: Get full dependency tree (max depth 3)
- check_resolution: Check if package resolves to GitHub repo
- list_unresolved: List unresolved dependencies
- list_manifests: List manifest files for a repo
- count_by_manifest_type: Count manifests by type
- repo_stats: Get repository statistics
- dataset_stats: Get overall dataset statistics
- search_repos: Search repositories by name
- search_packages: Search packages by name

User query: "{query}"

Classify the intent and extract parameters as JSON:
{
  "intent": "<intent_name>",
  "parameters": {
    "param1": "value1",
    ...
  },
  "confidence": 0.0-1.0
}

If confidence < 0.7, return intent "unknown".
```

### Example Classifications

| User Query | Intent | Parameters |
|------------|--------|------------|
| "What depends on flask?" | find_dependents | `{"package_name": "flask", "registry_type": "pypi"}` |
| "Show dependencies of django/django" | list_dependencies | `{"repo_full_name": "django/django"}` |
| "Dependency tree for react" | get_dependency_tree | `{"repo_full_name": "facebook/react"}` |
| "How many repos do we have?" | dataset_stats | `{}` |
| "Find repos with 'test' in name" | search_repos | `{"pattern": "%test%"}` |

## API Endpoint

### POST /api/query

**Request:**
```json
{
  "query": "What are the dependencies of django/django?",
  "max_results": 100
}
```

**Response:**
```json
{
  "intent": "list_dependencies",
  "parameters": {
    "repo_full_name": "django/django"
  },
  "confidence": 0.95,
  "results": [
    {
      "package_name": "asgiref",
      "registry_type": "pypi",
      "specifier": ">=3.6.0",
      "resolved_repo": "django/asgiref",
      "manifest_path": "pyproject.toml"
    },
    ...
  ],
  "result_count": 40,
  "execution_time_ms": 15
}
```

**Error Response:**
```json
{
  "error": "unknown_intent",
  "message": "Could not classify query intent",
  "confidence": 0.45,
  "suggestion": "Try rephrasing your query or use one of: list_dependencies, find_dependents, ..."
}
```

## Implementation Plan

### Phase 1: Intent Executor (No LLM)
1. Create `src/open_source_risk_model/query/intent_executor.py`
2. Implement each intent as a method with hardcoded SQL
3. Add tree computation algorithm (BFS)
4. Write unit tests for each intent

### Phase 2: Intent Classifier (LLM)
1. Create `src/open_source_risk_model/query/intent_classifier.py`
2. Implement LLM prompt template
3. Add confidence thresholding
4. Write tests with example queries

### Phase 3: API Endpoint
1. Add POST `/api/query` to `api/app.py`
2. Wire classifier → executor
3. Add error handling and validation
4. Write integration tests

### Phase 4: Testing & Refinement
1. Test with real queries against 51-repo dataset
2. Tune confidence thresholds
3. Add more intents based on usage patterns
4. Document query patterns

## Security Considerations

1. **SQL Injection**: All queries use parameterized SQL
2. **Resource Limits**: Max depth for trees, max results per query
3. **Rate Limiting**: Consider adding rate limits to API
4. **Input Validation**: Validate repo names, package names match expected patterns

## Future Enhancements (Post-Week 3)

- Query result caching
- Query history and analytics
- More complex intents (e.g., "compare dependencies of X and Y")
- Natural language result formatting
- Query suggestions based on dataset
