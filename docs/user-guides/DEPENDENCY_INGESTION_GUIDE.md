# Dependency Ingestion Guide 📚

## Overview

This guide explains the best processes for populating real dependency and package data into your system.

## The Problem

Currently, your database only has test data (9 dependencies for 4 repos). To make the dependency features useful, you need to ingest real repositories with their actual dependencies.

## Best Processes (Ranked)

### 🥇 Option 1: Automated Ingestion Script (RECOMMENDED)

**Best for**: Populating many repositories efficiently

**How it works**:
1. Fetches repository from GitHub
2. Discovers manifest files (requirements.txt, package.json, etc.)
3. Parses all dependencies
4. Resolves packages to source repositories
5. Stores everything in database

**Usage**:

```bash
# Make script executable
chmod +x scripts/ingest_with_dependencies.py

# Ingest single repository
python scripts/ingest_with_dependencies.py numpy/numpy

# Ingest multiple repositories
python scripts/ingest_with_dependencies.py numpy/numpy scipy/scipy pandas-dev/pandas

# Ingest from file
python scripts/ingest_with_dependencies.py --file repos_to_ingest.txt

# With custom delay (be nice to GitHub API)
python scripts/ingest_with_dependencies.py --file repos_to_ingest.txt --delay 3
```

**Pros**:
- ✅ Complete and accurate data
- ✅ Handles all manifest types
- ✅ Resolves packages automatically
- ✅ Batch processing
- ✅ Progress tracking

**Cons**:
- ⏱️ Takes time (2-5 seconds per repo)
- 🔑 Requires GitHub token for many repos

---

### 🥈 Option 2: Graph API (Automatic on Query)

**Best for**: On-demand ingestion when viewing graphs

**How it works**:
When you request a graph, it automatically parses dependencies if `parse_dependencies=True`.

**Usage**:

```bash
# Via API
curl "http://localhost:8000/api/graph?repo=numpy/numpy"

# Via UI
# Just use the Graph Visualization UI - it calls this automatically
```

**Pros**:
- ✅ Automatic - no extra steps
- ✅ Works with existing workflow
- ✅ Data stored for future queries

**Cons**:
- ⏱️ Slower first request (parsing happens then)
- 🔄 One repo at a time

---

### 🥉 Option 3: Batch Ingestion API

**Best for**: Background processing of many repos

**How it works**:
Submit a batch job that processes repositories in the background.

**Usage**:

```bash
# Submit batch job
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "repos": [
      "numpy/numpy",
      "scipy/scipy",
      "pandas-dev/pandas"
    ]
  }'

# Returns job_id
# {"job_id": "550e8400-...", "status": "pending", ...}

# Check status
curl "http://localhost:8000/api/jobs/550e8400-..."

# List all jobs
curl "http://localhost:8000/api/jobs"
```

**Pros**:
- ✅ Background processing
- ✅ Doesn't block
- ✅ Job tracking
- ✅ Good for large batches

**Cons**:
- 🔄 Requires worker to be running
- ⏱️ Not immediate

---

## Recommended Workflow

### For Development/Testing

```bash
# 1. Set GitHub token (optional but recommended)
export GITHUB_TOKEN=your_token_here

# 2. Ingest a few popular repos
python scripts/ingest_with_dependencies.py \
  numpy/numpy \
  pandas-dev/pandas \
  fastapi/fastapi \
  facebook/react

# 3. Test in UI
open ui/dependency-explorer.html
```

### For Production

```bash
# 1. Create a list of repositories you care about
cat > my_repos.txt << EOF
numpy/numpy
scipy/scipy
pandas-dev/pandas
scikit-learn/scikit-learn
matplotlib/matplotlib
EOF

# 2. Ingest them all
python scripts/ingest_with_dependencies.py --file my_repos.txt --delay 3

# 3. Set up periodic re-ingestion (cron job)
# Add to crontab:
# 0 2 * * * cd /path/to/project && python scripts/ingest_with_dependencies.py --file my_repos.txt
```

### For Continuous Operation

```bash
# 1. Enable automatic dependency parsing
export GRAPH_PARSE_DEPENDENCIES=true

# 2. Start API server
uvicorn api.app:app --host 0.0.0.0 --port 8000

# 3. Dependencies are parsed automatically when graphs are generated
# No manual ingestion needed!
```

---

## Understanding the Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    1. INGESTION                              │
│  Script/API fetches repo → Discovers manifests              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    2. PARSING                                │
│  Parse requirements.txt, package.json, etc.                  │
│  Extract: package names, versions, groups                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    3. RESOLUTION                             │
│  Resolve package names to GitHub repos                       │
│  requests → psf/requests (confidence: 0.95)                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    4. STORAGE                                │
│  Store in database:                                          │
│  - repo_dependencies (dependency edges)                      │
│  - package_mappings (resolution cache)                       │
│  - repo_graphs (full graph with PACKAGE nodes)              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    5. QUERY                                  │
│  API endpoints return data instantly from database           │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start: Populate Sample Data

```bash
# Quick test with 5 popular repos
python scripts/ingest_with_dependencies.py \
  numpy/numpy \
  django/django \
  fastapi/fastapi \
  facebook/react \
  expressjs/express

# This will take ~15-20 seconds
# Then you can query any of these repos in the UI!
```

---

## Checking What's Ingested

```bash
# See all repos with dependencies
sqlite3 data/graphs.db "
SELECT repo_full_name, COUNT(*) as dep_count 
FROM repo_dependencies 
GROUP BY repo_full_name;
"

# See all dependencies for a specific repo
sqlite3 data/graphs.db "
SELECT package_name, registry_type, specifier, dependency_group
FROM repo_dependencies 
WHERE repo_full_name = 'numpy/numpy'
ORDER BY package_name;
"

# Check resolution success rate
sqlite3 data/graphs.db "
SELECT 
  registry_type,
  COUNT(*) as total,
  SUM(CASE WHEN resolved_repo IS NOT NULL THEN 1 ELSE 0 END) as resolved,
  ROUND(100.0 * SUM(CASE WHEN resolved_repo IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate
FROM repo_dependencies
GROUP BY registry_type;
"
```

---

## Performance Considerations

### GitHub API Rate Limits

**Without token**: 60 requests/hour
**With token**: 5,000 requests/hour

Each repository ingestion uses:
- 1 request for repository info
- 1 request for tree (manifest discovery)
- 1-5 requests for manifest files
- **Total**: ~3-7 requests per repo

**Recommendation**: Set `GITHUB_TOKEN` for production use.

### Processing Time

- **Simple repo** (few dependencies): 2-3 seconds
- **Complex repo** (many dependencies): 5-10 seconds
- **Batch of 10 repos**: 30-60 seconds

### Database Size

- **Per dependency**: ~500 bytes
- **1000 dependencies**: ~500 KB
- **10,000 dependencies**: ~5 MB

Very manageable!

---

## Troubleshooting

### "No dependencies found"

**Cause**: Repository hasn't been ingested yet

**Solution**: Ingest it first
```bash
python scripts/ingest_with_dependencies.py owner/repo
```

### "Rate limit exceeded"

**Cause**: Too many GitHub API requests

**Solutions**:
1. Set `GITHUB_TOKEN` environment variable
2. Increase `--delay` between repos
3. Wait for rate limit to reset

### "Failed to parse manifest"

**Cause**: Unsupported manifest format or malformed file

**Solution**: Check which formats are supported:
- Python: requirements.txt, pyproject.toml
- JavaScript: package.json
- Others: Coming soon

### "Package resolution failed"

**Cause**: Package doesn't have GitHub URL in metadata

**Solution**: This is normal - not all packages can be resolved. Check confidence scores.

---

## Best Practices

1. **Set GitHub Token**: Avoid rate limits
   ```bash
   export GITHUB_TOKEN=your_token_here
   ```

2. **Use Delays**: Be nice to GitHub API
   ```bash
   --delay 3  # 3 seconds between repos
   ```

3. **Batch Processing**: Ingest multiple repos at once
   ```bash
   --file repos_to_ingest.txt
   ```

4. **Monitor Progress**: Watch the output for errors

5. **Periodic Updates**: Re-ingest repos to get latest dependencies
   ```bash
   # Cron job: daily at 2 AM
   0 2 * * * cd /path/to/project && python scripts/ingest_with_dependencies.py --file repos.txt
   ```

6. **Check Results**: Verify data was stored
   ```bash
   sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_dependencies;"
   ```

---

## Summary

**Recommended approach for you**:

1. **Right now** (testing):
   ```bash
   python scripts/ingest_with_dependencies.py numpy/numpy fastapi/fastapi facebook/react
   ```

2. **For production** (ongoing):
   - Create `repos_to_ingest.txt` with your important repos
   - Run ingestion script periodically
   - Or enable automatic parsing via `GRAPH_PARSE_DEPENDENCIES=true`

3. **For scale** (many repos):
   - Use batch ingestion API
   - Set up background worker
   - Monitor job status

The ingestion script (`scripts/ingest_with_dependencies.py`) is the most reliable and complete method! 🚀

