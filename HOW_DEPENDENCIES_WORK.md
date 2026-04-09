# How Dependencies Work - Important Info! 📚

## Why Only Some Repos Show Dependencies

You've discovered an important aspect of how the dependency system works:

**Dependencies are only available for repositories that have been previously ingested with dependency parsing enabled.**

## Current State

Your database currently has dependency data for only these repositories:
- ✅ `pallets/flask` - Has dependencies
- ✅ `django/django` - Has dependencies  
- ✅ `psf/requests` - Has dependencies (and is a dependent of flask)
- ✅ `test/test-repo` - Test data

That's why:
- ✅ `pallets/flask` shows dependencies (Werkzeug, Jinja2, etc.)
- ✅ `requests` shows dependents (flask depends on it)
- ❌ Other repos show "No dependencies found"

## How to Add More Repositories

### Option 1: Use the Graph API (Automatic)

When you generate a graph with dependency parsing enabled, it automatically parses and stores dependencies:

```bash
# This will parse dependencies and store them
curl "http://localhost:8000/api/graph?repo=numpy/numpy"
```

The graph endpoint will:
1. Fetch the repository
2. Parse manifest files (requirements.txt, package.json, etc.)
3. Store dependencies in the database
4. Return the graph

After this, you can query dependencies:
```bash
curl "http://localhost:8000/api/repos/numpy/numpy/dependencies"
```

### Option 2: Batch Ingestion (Recommended for Multiple Repos)

Use the batch ingestion API to process multiple repositories:

```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "repos": [
      "numpy/numpy",
      "scipy/scipy",
      "pandas-dev/pandas",
      "scikit-learn/scikit-learn"
    ]
  }'
```

This will:
1. Create a background job
2. Process each repository
3. Parse dependencies
4. Store in database

Check job status:
```bash
curl "http://localhost:8000/api/jobs/{job_id}"
```

### Option 3: Manual Testing Script

Run the test script that populates sample data:

```bash
python test_dependency_api.py
```

This inserts test data for flask and requests.

## Why This Design?

The dependency system works this way because:

1. **Performance**: Parsing dependencies on-demand would be slow
2. **GitHub API Limits**: We can't fetch manifests for every query
3. **Caching**: Once parsed, dependencies are cached in the database
4. **Batch Processing**: Allows efficient processing of many repos

## Workflow

```
1. Ingest Repository
   ↓
2. Parse Manifest Files (requirements.txt, package.json, etc.)
   ↓
3. Extract Dependencies
   ↓
4. Resolve Package Names to Repos
   ↓
5. Store in Database
   ↓
6. Query via API ✅
```

## Quick Test

To test with a new repository:

```bash
# 1. Generate graph (this parses dependencies)
curl "http://localhost:8000/api/graph?repo=fastapi/fastapi"

# 2. Wait a moment for processing

# 3. Query dependencies
curl "http://localhost:8000/api/repos/fastapi/fastapi/dependencies"
```

## Checking What's in the Database

```bash
# See all repos with dependencies
sqlite3 data/graphs.db "SELECT DISTINCT repo_full_name FROM repo_dependencies;"

# Count dependencies per repo
sqlite3 data/graphs.db "
SELECT repo_full_name, COUNT(*) as dep_count 
FROM repo_dependencies 
GROUP BY repo_full_name;
"

# See all dependencies for a specific repo
sqlite3 data/graphs.db "
SELECT package_name, registry_type, specifier 
FROM repo_dependencies 
WHERE repo_full_name = 'pallets/flask';
"
```

## Adding Popular Repositories

Here's a script to populate common Python repositories:

```bash
# Popular Python projects
for repo in "numpy/numpy" "scipy/scipy" "pandas-dev/pandas" "scikit-learn/scikit-learn" "matplotlib/matplotlib"; do
  echo "Processing $repo..."
  curl -s "http://localhost:8000/api/graph?repo=$repo" > /dev/null
  sleep 2  # Be nice to GitHub API
done

# Popular JavaScript projects  
for repo in "facebook/react" "expressjs/express" "lodash/lodash" "axios/axios"; do
  echo "Processing $repo..."
  curl -s "http://localhost:8000/api/graph?repo=$repo" > /dev/null
  sleep 2
done
```

## Understanding the UI Behavior

When you use the Dependency Explorer UI:

- **"No dependencies found"** = Repository hasn't been ingested yet
- **Shows dependencies** = Repository was previously ingested
- **404 error** = Repository doesn't exist or API issue

## Next Steps

1. **Populate more data**: Use the graph API or batch ingestion
2. **Test with known repos**: Use pallets/flask, django/django, psf/requests
3. **Monitor ingestion**: Check job status for batch operations
4. **Query after ingestion**: Dependencies available immediately after parsing

## Summary

✅ **The system IS working correctly!**

It just needs repositories to be ingested first. Think of it like a search engine - you can only search for pages that have been indexed.

**To see dependencies for any repo:**
1. First: Generate its graph (this indexes it)
2. Then: Query its dependencies

This is by design for performance and efficiency! 🚀

