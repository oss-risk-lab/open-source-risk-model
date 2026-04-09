# Query Interface Guide

**Status**: ✅ Running at http://localhost:8000
**UI**: ui/query.html (should be open in your browser)

## Quick Start

The query interface is now running! You can use it to explore your dependency graph data.

### Available Features

1. **Dev Mode** (checked by default)
   - No API key needed
   - Use the example buttons to run predefined queries
   - Direct intent execution

2. **Dependency Scope Filter**
   - **Production**: Only production dependencies (default)
   - **Build/CI**: Only build/development dependencies
   - **All**: All dependencies (production + build)

### Example Queries

Click these buttons in the UI to try them out:

1. **Dataset Stats**: Get overall statistics about your dataset
2. **Flask Dependencies**: List all dependencies for pallets/flask
3. **Who uses requests?**: Find all repos that depend on the requests package
4. **Search Django**: Search for repositories with "django" in the name
5. **Search pytest***: Search for packages starting with "pytest"

### Available Intents

The system supports these query intents:

#### Dependency Queries
- `list_dependencies`: List direct dependencies of a repo
  - Parameters: `repo_full_name`, `dependency_scope` (prod/build/all)
- `find_dependents`: Find repos that depend on a package
  - Parameters: `package_name`, `registry_type` (optional)
- `get_dependency_tree`: Compute dependency tree (BFS)
  - Parameters: `repo_full_name`, `max_depth` (default: 3)

#### Resolution Queries
- `check_resolution`: Check if a package resolves to a GitHub repo
  - Parameters: `package_name`, `registry_type`
- `list_unresolved`: List dependencies that couldn't be resolved
  - Parameters: `repo_full_name` (optional)

#### Manifest Queries
- `list_manifests`: List manifest files for a repo
  - Parameters: `repo_full_name`
- `count_by_manifest_type`: Count manifests by type
  - Parameters: none

#### Statistics Queries
- `repo_stats`: Get statistics for a repository
  - Parameters: `repo_full_name`
- `dataset_stats`: Get overall dataset statistics
  - Parameters: none

#### Search Queries
- `search_repos`: Search repositories by name pattern
  - Parameters: `pattern` (SQL LIKE syntax)
- `search_packages`: Search packages by name pattern
  - Parameters: `pattern`, `registry_type` (optional)

#### New Query Coverage Intents (from completed spec)
- `repo_lookup`: Look up maintenance risk score for a single repository
  - Parameters: `repo_identifier`, `ingestion_mode` (provisional/full), `persistence_mode` (temporary/cache/database)
- `repo_comparison`: Compare maintenance risk scores for multiple repositories
  - Parameters: `repo_identifiers` (list), `ingestion_mode`, `persistence_mode`
- `missing_repo_handling`: Force live ingestion for a repository not in database
  - Parameters: `repo_identifier`, `ingestion_mode`, `persistence_mode`

## API Endpoints

### POST /api/query
Execute a query with intent and parameters.

**Request**:
```json
{
  "query": "List dependencies for pallets/flask",
  "intent": "list_dependencies",
  "parameters": {
    "repo_full_name": "pallets/flask",
    "dependency_scope": "prod"
  },
  "max_results": 100
}
```

**Response**:
```json
{
  "intent": "list_dependencies",
  "parameters": {...},
  "results": [...],
  "result_count": 42,
  "execution_time_ms": 15.3,
  "metadata": {
    "repo_full_name": "pallets/flask",
    "dependency_scope": "prod",
    "dependency_scope_description": "Production dependencies only"
  }
}
```

## Dependency Scope Feature

The dependency scope filter allows you to focus on different types of dependencies:

- **Production** (`prod`): Only dependencies needed to run the application
  - Excludes: dev, test, build, optional dependencies
  - Use case: Understanding production runtime dependencies

- **Build/CI** (`build`): Only dependencies needed for development and testing
  - Includes: dev, test, build dependencies
  - Use case: Understanding development tooling

- **All** (`all`): All dependencies regardless of type
  - Use case: Complete dependency analysis

## Testing the New Query Coverage Features

To test the new maintenance risk score features:

1. **Single Repo Lookup**:
   ```json
   {
     "intent": "repo_lookup",
     "parameters": {
       "repo_identifier": "django/django",
       "ingestion_mode": "provisional",
       "persistence_mode": "cache"
     }
   }
   ```

2. **Multi-Repo Comparison**:
   ```json
   {
     "intent": "repo_comparison",
     "parameters": {
       "repo_identifiers": ["django/django", "pallets/flask"],
       "ingestion_mode": "provisional",
       "persistence_mode": "cache"
     }
   }
   ```

3. **Force Live Ingestion**:
   ```json
   {
     "intent": "missing_repo_handling",
     "parameters": {
       "repo_identifier": "some-new-repo/name",
       "ingestion_mode": "full",
       "persistence_mode": "database"
     }
   }
   ```

## Stopping the Server

To stop the API server:
```bash
# Find the process
lsof -ti:8000

# Kill it
kill $(lsof -ti:8000)
```

Or use Kiro to stop the background process.

## Troubleshooting

### Server Not Running
```bash
# Start the server
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000
```

### CORS Issues
The server should allow CORS from localhost. If you see CORS errors, check the API configuration.

### Database Not Found
Make sure `data/graphs.db` exists. If not, you may need to run ingestion first:
```bash
python -m open_source_risk_model.cli.ingest --help
```

## Next Steps

1. Try the example queries in the UI
2. Experiment with different dependency scopes
3. Test the new query coverage features (repo_lookup, repo_comparison)
4. Explore the API documentation at http://localhost:8000/docs

---

**Status**: ✅ Ready to use
**API**: http://localhost:8000
**UI**: ui/query.html
**Docs**: http://localhost:8000/docs
