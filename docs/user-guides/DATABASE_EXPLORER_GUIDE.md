# Database Explorer Guide

## Quick Access Methods

### 1. Command-Line Explorer Script (Recommended)

We've created a Python script for easy database exploration:

```bash
# Show database statistics
python scripts/explore_database.py stats

# List all repositories
python scripts/explore_database.py list-repos

# List repos with dependency counts (sorted by most dependencies)
python scripts/explore_database.py list-repos-with-deps

# Show dependencies for a specific repo
python scripts/explore_database.py show-deps django/django

# Show top 20 most used packages
python scripts/explore_database.py top-packages 20

# Search for repos containing a term
python scripts/explore_database.py search react
```

### 2. Direct SQLite Commands

```bash
# Open interactive SQLite shell
sqlite3 data/graphs.db

# Run a quick query
sqlite3 data/graphs.db "SELECT repo_full_name FROM repo_graphs ORDER BY repo_full_name;"

# Export to CSV
sqlite3 data/graphs.db -csv -header "SELECT * FROM repo_graphs;" > repos.csv
```

### 3. GUI Database Browser (DB Browser for SQLite)

**Install:**
```bash
# macOS
brew install --cask db-browser-for-sqlite

# Or download from: https://sqlitebrowser.org/
```

**Usage:**
1. Open DB Browser for SQLite
2. Click "Open Database"
3. Navigate to `data/graphs.db`
4. Browse tables, run queries, export data

### 4. Query API (Web Interface)

The query interface at `http://localhost:8000` provides:
- Dataset stats button
- Natural language queries
- Dependency lookups

Start the API:
```bash
python api/app.py
```

Then open `ui/query.html` in your browser.

## Database Schema

### Main Tables

**repo_graphs** - Repository metadata
- `repo_full_name` (PRIMARY KEY) - e.g., "django/django"
- `graph_json` - Full supply chain graph
- `node_count`, `edge_count` - Graph size
- `created_at`, `updated_at` - Timestamps

**repo_dependencies** - Dependency relationships
- `repo_full_name` - Repository name
- `package_name` - Dependency package name
- `registry_type` - npm, pypi, etc.
- `specifier` - Version constraint
- `dependency_group` - prod, dev, test, etc.
- `is_direct` - Direct vs transitive
- `resolved_repo` - Resolved GitHub repo (if found)
- `manifest_path` - Source manifest file

**package_mappings** - Package to repo mappings
- Maps package names to GitHub repositories

**repo_cves** - CVE/GHSA security advisories
- Security vulnerabilities for packages

**repo_registries** - Registry detection results
- Detected package registries per repo

**repo_maintainers** - Repository maintainers
- Maintainer information

## Useful Queries

### List all repos
```sql
SELECT repo_full_name, node_count, edge_count 
FROM repo_graphs 
ORDER BY repo_full_name;
```

### Repos with most dependencies
```sql
SELECT 
    rd.repo_full_name,
    COUNT(DISTINCT rd.package_name) as dep_count
FROM repo_dependencies rd
GROUP BY rd.repo_full_name
ORDER BY dep_count DESC
LIMIT 20;
```

### Most popular packages
```sql
SELECT 
    package_name,
    registry_type,
    COUNT(DISTINCT repo_full_name) as repo_count
FROM repo_dependencies
GROUP BY package_name, registry_type
ORDER BY repo_count DESC
LIMIT 20;
```

### Dependencies for a specific repo
```sql
SELECT 
    package_name,
    registry_type,
    specifier,
    dependency_group,
    resolved_repo
FROM repo_dependencies
WHERE repo_full_name = 'django/django'
ORDER BY is_direct DESC, package_name;
```

### Resolution rate by registry
```sql
SELECT 
    registry_type,
    COUNT(*) as total,
    SUM(CASE WHEN resolved_repo IS NOT NULL THEN 1 ELSE 0 END) as resolved,
    ROUND(100.0 * SUM(CASE WHEN resolved_repo IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
FROM repo_dependencies
GROUP BY registry_type;
```

### Repos added today
```sql
SELECT 
    repo_full_name,
    datetime(created_at) as added
FROM repo_graphs
WHERE date(created_at) = date('now')
ORDER BY created_at DESC;
```

## Current Database Stats

- **Total Repositories:** 145
- **Total Dependencies:** 10,396
- **Unique Packages:** 3,936
- **Resolution Rate:** 86.5%
- **Registries:** npm (6,170 deps), pypi (4,226 deps)

## Export Options

### Export full repo list
```bash
sqlite3 data/graphs.db -csv -header \
  "SELECT repo_full_name, node_count, edge_count, created_at FROM repo_graphs;" \
  > repos_export.csv
```

### Export dependency data
```bash
sqlite3 data/graphs.db -csv -header \
  "SELECT * FROM repo_dependencies;" \
  > dependencies_export.csv
```

### Export as JSON
```bash
sqlite3 data/graphs.db \
  "SELECT json_group_array(json_object(
    'repo', repo_full_name,
    'nodes', node_count,
    'edges', edge_count
  )) FROM repo_graphs;" \
  > repos.json
```

## Tips

1. **Use the explorer script** for quick lookups - it's formatted nicely
2. **Use DB Browser** for visual exploration and complex queries
3. **Use the Query API** for natural language queries
4. **Export to CSV** for analysis in Excel/Google Sheets
5. **Check manifest.json** in `data/manifest.json` for ingestion metadata
