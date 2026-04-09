# Open Source Risk Model - Project Structure

## Overview
Python-based system for analyzing open source software supply chain risks. Fetches data from GitHub, OSV.dev (CVEs), PyPI/npm registries, and builds risk graphs with dependency tracking.

## Core Architecture

### 1. API Layer (`api/`)
- **`app.py`** - FastAPI application with REST endpoints
  - `/api/graph/{repo}` - Get risk graph for a repository
  - `/api/repos/{repo}/dependencies` - Get dependencies for a repo
  - `/api/packages/{package}/dependents` - Get repos that depend on a package
  - `/api/ingest` - Batch ingestion endpoint
  - `/api/search/*` - Search endpoints for repos, CVEs, packages

### 2. Source Code (`src/open_source_risk_model/`)

#### Graph Module (`graph/`)
Builds risk graphs by fetching and combining data from multiple sources:

- **`builder.py`** - Main `GraphBuilder` class, orchestrates graph construction
- **`schema.py`** - Graph data structures (Node, Edge, Graph, GraphConfig)
- **`github_client.py`** - Fetches releases, contributors from GitHub API
- **`cve_fetcher.py`** - Fetches CVEs from OSV.dev API
- **`registry_detector.py`** - Detects package registries (PyPI, npm, etc.)
- **`cache.py`** - Caches generated graphs to avoid re-fetching

**Node Types**: repository, release, maintainer, cve, registry
**Edge Types**: AUTHORED_BY, HAS_CVE, PUBLISHED_AS, etc.

#### Dependencies Module (`dependencies/`)
NEW feature for parsing and resolving package dependencies:

- **`ingestion_service.py`** - Main service for ingesting repo dependencies
- **`manifest_discovery.py`** - Finds manifest files (requirements.txt, package.json, etc.)
- **`parsers.py`** - Parses different manifest formats (Python, npm, Java, Go)
- **`package_resolver.py`** - Resolves package names to GitHub repos (PyPI→GitHub, npm→GitHub)
- **`manifest_cache.py`** - Caches manifest files
- **`rate_limiter.py`** - Rate limiting for API calls

**Flow**: Discover manifests → Parse dependencies → Resolve to GitHub repos → Store in DB

#### Persistence Layer (`persistence/`)
Database operations using SQLite:

- **`db.py`** - Database connection management
- **`graph_repo.py`** - CRUD for graphs (save/load/delete)
- **`dependency_repo.py`** - CRUD for dependencies and package mappings
- **`job_repo.py`** - Job queue for async ingestion
- **`index_repo.py`** - Search indexes (maintainers, CVEs, registries)
- **`worker.py`** - Background worker for processing jobs

#### Service Layer (`service/`)
- **`score_repo.py`** - Scores repositories using GitHub API (stars, forks, activity)

#### Utils (`utils/`)
- **`logging_utils.py`** - Structured logging
- **`metrics.py`** - Performance metrics

### 3. Database (`data/graphs.db`)
SQLite database with tables:

```sql
-- Core tables
repo_graphs          -- Stored graph JSON + metadata
repo_dependencies    -- Dependencies with resolved GitHub repos
package_mappings     -- Cache: package name → GitHub repo
repo_cves            -- CVEs affecting repos (with CVE + GHSA IDs)
repo_maintainers     -- Maintainer index
repo_registries      -- Registry index
ingestion_jobs       -- Job queue
schema_version       -- DB version tracking
```

**Key Schema Details**:
- `repo_dependencies` has `resolved_repo`, `resolution_confidence`, `resolution_method` columns
- `repo_cves` has both `cve_id` (CVE-2025-xxx) and `ghsa_id` (GHSA-xxx) columns
- `package_mappings` caches PyPI/npm → GitHub resolution

### 4. UI (`ui/`)
Static HTML/JS interfaces:

- **`graph.html`** - Main graph visualization (D3.js force-directed graph)
- **`dependency-explorer.html`** - NEW: Explore dependencies interactively
- **`graph-viz.js`** - Visualization logic

### 5. Scripts (`scripts/`)
Utility scripts:

- **`ingest_with_dependencies.py`** - CLI for ingesting repos with dependencies
- **`populate_dependencies.sh`** - Batch populate multiple repos
- **`rebuild_indexes.py`** - Rebuild search indexes
- **`backup_database.py`** / **`restore_database.py`** - DB backup/restore
- **`cleanup_stale_data.py`** - Remove old cached data

### 6. Tests (`test/`)
Comprehensive test suite (76+ tests):

- **Graph tests**: `test_graph_*.py` - Graph building, CVE fetching, caching
- **Dependency tests**: `test_dependency_*.py` - Parsing, resolution, integration
- **API tests**: `test_api_*.py` - Endpoint testing
- **Persistence tests**: `test_*_repository.py` - Database operations
- **Property-based tests**: `test_*_properties.py` - Using Hypothesis library
- **E2E tests**: `test_e2e_integration.py`, `test_end_to_end_validation.py`

### 7. Documentation (`docs/`)
- **`API.md`** - API endpoint documentation
- **`SETUP.md`** - Setup instructions
- **`DATA_GUIDE.md`** - Data model documentation
- **`DEPLOYMENT.md`** - Deployment guide
- **`DEPENDENCY_GRAPH_GUIDE.md`** - NEW: Dependency feature guide
- **`SUPPLY_CHAIN_USER_GUIDE.md`** - User guide

### 8. Specs (`.kiro/specs/`)
Design documents and requirements:

- **`dependency-graph/`** - Dependency feature spec (requirements, design, tasks)
- **`supply-chain-graph/`** - Original supply chain spec
- **`multi-repo-persistent-graph/`** - Multi-repo feature spec

## Key Data Flows

### Flow 1: Generate Risk Graph
```
User requests /api/graph/owner/repo
  ↓
GraphBuilder.build_graph()
  ↓
Fetch from GitHub API (releases, contributors)
Fetch from OSV.dev (CVEs)
Detect registries (PyPI, npm)
  ↓
Build Graph (nodes + edges)
  ↓
Save to repo_graphs table
Extract indexes (CVEs, maintainers, registries)
  ↓
Return JSON graph
```

### Flow 2: Ingest Dependencies (NEW)
```
User calls DependencyIngestionService.ingest_repo()
  ↓
ManifestDiscovery.discover_manifests()
  → Scan repo tree for requirements.txt, package.json, etc.
  ↓
Parse each manifest
  → Extract package names + versions
  ↓
PackageResolver.resolve()
  → Query PyPI/npm API for GitHub URL
  → Extract owner/repo from URL
  ↓
Save to repo_dependencies table
  → Store: package_name, resolved_repo, confidence, method
  ↓
Cache in package_mappings table
```

### Flow 3: Query Dependencies
```
User requests /api/repos/owner/repo/dependencies
  ↓
DependencyRepository.get_dependencies()
  ↓
SELECT * FROM repo_dependencies WHERE repo_full_name = ?
  ↓
Return list with resolved GitHub repos
```

## Important Implementation Details

### Dependency Resolution
- **PyPI packages** → Query `https://pypi.org/pypi/{package}/json`
  - Check `project_urls` for "Source", "Repository", "GitHub"
  - Fallback to `home_page`
  - Extract GitHub URL, parse to owner/repo
  - Confidence: 0.95 (project_urls) or 0.75 (homepage)

- **npm packages** → Query `https://registry.npmjs.org/{package}`
  - Check `repository.url` field
  - Extract GitHub URL
  - Confidence: 0.90

### CVE Data
- Fetched from **OSV.dev API**: `https://api.osv.dev/v1/query`
- Each CVE has:
  - Primary ID (GHSA-xxx or CVE-xxx)
  - `cve_id` - CVE identifier (CVE-2025-47278)
  - `ghsa_id` - GitHub Security Advisory ID (GHSA-4grg-w6v8-c28g)
  - `aliases` - All alternate identifiers
  - Severity, CVSS score, affected versions

### Caching Strategy
- **Graph cache**: File-based, TTL 1 hour
- **Manifest cache**: File-based, TTL 24 hours
- **Package mappings**: Database, permanent (until refresh)
- **CVE cache**: File-based, TTL 24 hours

## Configuration

### Environment Variables (`.env`)
```bash
GITHUB_TOKEN=ghp_xxx              # GitHub API token (required)
GRAPH_INCLUDE_CVES=true           # Include CVE nodes
GRAPH_MAX_RELEASES=10             # Max release nodes
GRAPH_MAX_MAINTAINERS=5           # Max maintainer nodes
GRAPH_PARSE_DEPENDENCIES=false    # Parse deps during graph build
```

### Database Location
- Default: `data/graphs.db`
- Configurable via `db_path` parameter

## Recent Changes (What's New)

### Dependency Resolution Storage (JUST FIXED)
- **Problem**: Resolution data wasn't being stored
- **Fix**: Added `resolved_repo`, `resolution_confidence`, `resolution_method` columns
- **Status**: ✅ Working, 92% resolution rate for Flask

### CVE/GHSA Dual Identifiers (JUST IMPLEMENTED)
- **Problem**: Only stored GHSA IDs, not CVE IDs
- **Fix**: Added `ghsa_id` and `cve_aliases` columns, extract from OSV aliases
- **Status**: ✅ Tested, all 4 tests pass

## How to Use (Quick Start)

### 1. Start API Server
```bash
pip install -e .
uvicorn api.app:app --reload
```

### 2. Ingest a Repository with Dependencies
```python
from src.open_source_risk_model.dependencies.ingestion_service import DependencyIngestionService

service = DependencyIngestionService('data/graphs.db')
result = service.ingest_repo('pallets/flask', refresh=True, resolve_packages=True)
print(f"Found {result.dependencies_found} dependencies")
print(f"Resolved {result.dependencies_resolved} ({result.resolution_rate:.0%})")
```

### 3. Query Dependencies
```bash
curl "http://localhost:8000/api/repos/pallets/flask/dependencies"
```

### 4. Generate Risk Graph
```bash
curl "http://localhost:8000/api/graph/pallets/flask?include_cves=true"
```

## Technology Stack
- **Language**: Python 3.8+
- **Web Framework**: FastAPI
- **Database**: SQLite
- **Testing**: pytest, Hypothesis (property-based)
- **APIs**: GitHub REST API, OSV.dev, PyPI, npm registry
- **Frontend**: Vanilla JS, D3.js for visualization

## Current State
- ✅ Core graph generation working
- ✅ CVE fetching working
- ✅ Dependency parsing working (Python, npm, Java, Go)
- ✅ Package resolution working (92% success rate)
- ✅ Dependency storage working
- ✅ CVE/GHSA dual identifiers working
- ⚠️ Only 1 repo fully populated (pallets/flask)
- 📝 Need to populate more repos for demo

## Key Files to Understand

If you need to understand the codebase, start with these files in order:

1. **`src/open_source_risk_model/graph/schema.py`** - Data structures
2. **`src/open_source_risk_model/graph/builder.py`** - Graph construction
3. **`src/open_source_risk_model/dependencies/ingestion_service.py`** - Dependency ingestion
4. **`src/open_source_risk_model/persistence/dependency_repo.py`** - Dependency storage
5. **`api/app.py`** - API endpoints

## Common Issues & Solutions

### Issue: "No dependencies found"
- **Cause**: Repository hasn't been ingested yet
- **Solution**: Run `DependencyIngestionService.ingest_repo()` first

### Issue: "Resolution rate is low"
- **Cause**: Packages don't have GitHub URLs in metadata
- **Solution**: Normal - not all packages are on GitHub

### Issue: "Rate limit exceeded"
- **Cause**: Too many GitHub API calls
- **Solution**: Set `GITHUB_TOKEN` environment variable

This should give ChatGPT a complete understanding of the project structure!
