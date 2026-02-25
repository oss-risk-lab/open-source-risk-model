# Query API Quick Start (Dev Mode)

Test the query API without needing an OpenAI API key!

## Step 1: Start the API Server

```bash
uvicorn api.app:app --reload
```

The server will start at `http://localhost:8000`

## Step 2: Choose Your Testing Method

### Option A: Interactive Shell Script (Recommended)

```bash
./demo_query_api.sh
```

This walks you through 8 example queries with formatted output.

### Option B: Python Test Script

```bash
python test_query_api_live.py
```

Runs all 8 queries automatically and shows results.

### Option C: Manual curl Commands

```bash
# Dataset statistics
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show stats",
    "intent": "dataset_stats",
    "parameters": {}
  }' | python -m json.tool

# List dependencies
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "List dependencies",
    "intent": "list_dependencies",
    "parameters": {"repo_full_name": "pallets/flask"}
  }' | python -m json.tool
```

## Available Intents

All 11 intents work in dev mode:

| Intent | Parameters | Description |
|--------|-----------|-------------|
| `dataset_stats` | none | Overall dataset statistics |
| `list_dependencies` | `repo_full_name` (required) | List direct dependencies |
| `find_dependents` | `package_name` (required), `registry_type` (optional) | Find who depends on a package |
| `get_dependency_tree` | `repo_full_name` (required), `max_depth` (optional, default: 3) | Get dependency tree |
| `check_resolution` | `package_name` (required), `registry_type` (required) | Check package-to-repo resolution |
| `list_unresolved` | `repo_full_name` (optional) | List unresolved dependencies |
| `list_manifests` | `repo_full_name` (required) | List manifest files |
| `count_by_manifest_type` | none | Count manifests by type |
| `repo_stats` | `repo_full_name` (required) | Repository statistics |
| `search_repos` | `pattern` (required) | Search repositories by name |
| `search_packages` | `pattern` (required), `registry_type` (optional) | Search packages by name |

## Response Format

All queries return this structure:

```json
{
  "intent": "dataset_stats",
  "parameters": {},
  "confidence": 1.0,
  "results": [...],
  "result_count": 1,
  "execution_time_ms": 11.3,
  "metadata": {...}
}
```

## Example Queries

### 1. Get Dataset Overview
```json
{
  "intent": "dataset_stats",
  "parameters": {}
}
```

### 2. List Dependencies for Flask
```json
{
  "intent": "list_dependencies",
  "parameters": {
    "repo_full_name": "pallets/flask"
  },
  "max_results": 10
}
```

### 3. Find Who Uses Flask
```json
{
  "intent": "find_dependents",
  "parameters": {
    "package_name": "flask",
    "registry_type": "pypi"
  }
}
```

### 4. Get Dependency Tree (depth=2)
```json
{
  "intent": "get_dependency_tree",
  "parameters": {
    "repo_full_name": "pallets/flask",
    "max_depth": 2
  },
  "max_results": 20
}
```

### 5. Search for Django Repos
```json
{
  "intent": "search_repos",
  "parameters": {
    "pattern": "%django%"
  }
}
```

### 6. Find Flask-Related Packages
```json
{
  "intent": "search_packages",
  "parameters": {
    "pattern": "flask%",
    "registry_type": "pypi"
  }
}
```

## Tips

- **Dev mode is production-ready** - you don't need natural language for many use cases
- Use `max_results` to limit response size (default: 100)
- SQL wildcards work in patterns: `%` (any chars), `_` (single char)
- All queries are < 100ms on the 51-repo dataset
- Confidence is always 1.0 in dev mode (you specified the intent)

## Troubleshooting

**Connection refused?**
- Make sure the API server is running: `uvicorn api.app:app --reload`

**Empty results?**
- Check that you have data: `sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_graphs;"`
- Verify repo names match exactly: `pallets/flask` not `flask`

**Invalid intent error?**
- Check spelling - intent names are case-sensitive
- See list of 11 valid intents above

## Next Steps

- See `WEEK_2_PROGRESS.md` for detailed parameter specs
- See `test/test_query_api.py` for more examples
- Add OpenAI API key to `.env` to enable natural language queries
