# API Documentation

The Open Source Risk Model provides a REST API for scoring GitHub repositories.

## Base URL

```
http://localhost:8000
```

## Endpoints

### Health Check

Check if the API is running.

**Endpoint:** `GET /api/health`

**Response:**
```json
{
  "status": "ok"
}
```

---

### Score Repository

Compute risk scores for a GitHub repository.

**Endpoint:** `GET /api/score`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `repo` | string | Yes | - | GitHub repository in `owner/repo` format or full GitHub URL |
| `refresh` | boolean | No | `false` | Force refresh from GitHub API and overwrite cached snapshot |
| `fetch_issues` | boolean | No | `true` | Fetch issues and compute issue-based metrics |

**Example Requests:**

```bash
# Basic request
curl "http://localhost:8000/api/score?repo=numpy/numpy"

# Force refresh
curl "http://localhost:8000/api/score?repo=numpy/numpy&refresh=true"

# Skip issue fetching (faster)
curl "http://localhost:8000/api/score?repo=numpy/numpy&fetch_issues=false"

# Using full GitHub URL
curl "http://localhost:8000/api/score?repo=https://github.com/numpy/numpy"
```

**Success Response (200):**

```json
{
  "repo": "numpy/numpy",
  "maintenance_risk": 0.197,
  "maintenance_label": "low",
  "maintenance_uncertainty": 0.197,
  "maintenance_coverage": 1.0,
  "maintenance_confidence": "high",
  "license_risk": 0.0,
  "license_label": "low",
  "feature_risks": {
    "days_since_last_push": 0.004,
    "days_since_last_release": 0.074,
    "fraction_issues_closed_12mo": 0.398,
    "stars_count": 0.062,
    "contributors_count": 0.593,
    "archived": 0.0
  },
  "raw_features": {
    "days_since_last_push": 0.5,
    "stars_count": 28500,
    "archived": false
  },
  "snapshot_meta": {
    "fetched_at": "2026-02-13T10:30:00Z",
    "source": "github_api"
  }
}
```

**Error Responses:**

**400 Bad Request** - Invalid repository format:
```json
{
  "detail": "Invalid repository format. Use 'owner/repo' or GitHub URL"
}
```

**500 Internal Server Error** - API or processing error:
```json
{
  "detail": "Internal error: Repository not found"
}
```

---

## Risk Score Interpretation

### Maintenance Risk

A composite score from 0 (low risk) to 1 (high risk) based on:
- Activity recency
- Contributor diversity
- Issue resolution rates
- Release frequency

**Risk Bands:**
- `0.0 - 0.25`: Low risk
- `0.25 - 0.50`: Medium risk
- `0.50 - 0.75`: High risk
- `0.75 - 1.0`: Critical risk

### License Risk

Binary score based on license compatibility:
- `0.0`: Permissive license (MIT, Apache, BSD)
- `1.0`: Restrictive or missing license

### Confidence Levels

Based on feature coverage:
- `high`: 90%+ features available
- `medium`: 70-90% features available
- `low`: <70% features available

---

## Rate Limiting

The API respects GitHub's rate limits:
- Authenticated: 5,000 requests/hour
- Unauthenticated: 60 requests/hour

Use the `refresh=false` parameter to use cached data when possible.

---

## Running the API

Start the development server:

```bash
uvicorn api.app:app --reload --port 8000
```

For production:

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Interactive Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc


---

### Graph Visualization

Retrieve a graph representation of repository supply chain risk.

**Endpoint:** `GET /api/graph`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `repo` | string | Yes | - | GitHub repository in `owner/repo` format or full GitHub URL |
| `refresh` | boolean | No | `false` | Force refresh from external APIs and bypass cache |
| `include_cves` | boolean | No | `true` | Include CVE (vulnerability) nodes in the graph |
| `max_releases` | integer | No | `10` | Maximum number of release nodes to include |
| `max_maintainers` | integer | No | `5` | Maximum number of maintainer nodes to include |

**Example Requests:**

```bash
# Basic request
curl "http://localhost:8000/api/graph?repo=numpy/numpy"

# Force refresh with custom limits
curl "http://localhost:8000/api/graph?repo=numpy/numpy&refresh=true&max_releases=5"

# Skip CVE fetching for faster response
curl "http://localhost:8000/api/graph?repo=psf/requests&include_cves=false"

# Using full GitHub URL
curl "http://localhost:8000/api/graph?repo=https://github.com/django/django"
```

**Success Response (200):**

```json
{
  "repo": "numpy/numpy",
  "schema_version": "1.0",
  "generated_at": "2026-02-18T10:30:00Z",
  "graph": {
    "nodes": [
      {
        "id": "repo:numpy/numpy",
        "type": "repo",
        "label": "numpy/numpy",
        "metadata": {
          "url": "https://github.com/numpy/numpy",
          "maintenance_risk": 0.197,
          "maintenance_label": "low",
          "coverage": 1.0,
          "confidence": "high",
          "stars": 28500,
          "archived": false
        },
        "provenance": {
          "source": "github_api",
          "fetched_at": "2026-02-18T10:30:00Z",
          "data_confidence": 1.0
        }
      },
      {
        "id": "release:numpy/numpy:v1.26.0",
        "type": "release",
        "label": "v1.26.0",
        "metadata": {
          "tag_name": "v1.26.0",
          "published_at": "2024-09-16T10:00:00Z",
          "days_ago": 150,
          "is_latest": true,
          "is_prerelease": false
        },
        "provenance": {
          "source": "github_api",
          "fetched_at": "2026-02-18T10:30:00Z",
          "data_confidence": 1.0
        }
      },
      {
        "id": "maintainer:numpy/numpy:charris",
        "type": "maintainer",
        "label": "charris",
        "metadata": {
          "username": "charris",
          "contribution_fraction": 0.23,
          "commit_count": 5234,
          "type": "individual"
        },
        "provenance": {
          "source": "github_api",
          "fetched_at": "2026-02-18T10:30:00Z",
          "data_confidence": 0.9
        }
      },
      {
        "id": "cve:CVE-2024-1234",
        "type": "cve",
        "label": "CVE-2024-1234",
        "metadata": {
          "cve_id": "CVE-2024-1234",
          "severity": "HIGH",
          "cvss_score": 7.5,
          "summary": "Buffer overflow vulnerability",
          "published": "2024-01-15T10:00:00Z",
          "source": "osv"
        },
        "provenance": {
          "source": "osv",
          "fetched_at": "2026-02-18T10:30:00Z",
          "match_confidence": 0.92,
          "data_confidence": 0.95
        }
      },
      {
        "id": "registry:pypi:numpy",
        "type": "registry",
        "label": "PyPI: numpy",
        "metadata": {
          "registry_type": "pypi",
          "package_name": "numpy",
          "latest_version": "1.26.0"
        },
        "provenance": {
          "source": "heuristic",
          "fetched_at": "2026-02-18T10:30:00Z",
          "match_confidence": 0.95,
          "data_confidence": 0.8
        }
      },
      {
        "id": "risk:numpy/numpy:days_since_last_release",
        "type": "risk_factor",
        "label": "Days Since Last Release",
        "metadata": {
          "key": "days_since_last_release",
          "label": "Days Since Last Release",
          "raw_value": 150,
          "risk_score": 0.074,
          "contribution": 0.074,
          "weight": 1.0,
          "category": "activity"
        },
        "provenance": {
          "source": "score_model",
          "fetched_at": "2026-02-18T10:30:00Z",
          "data_confidence": 1.0
        }
      }
    ],
    "edges": [
      {
        "source": "repo:numpy/numpy",
        "target": "release:numpy/numpy:v1.26.0",
        "relationship_type": "has_release",
        "metadata": {
          "days_ago": 150,
          "is_latest": true
        },
        "provenance": {
          "source": "github_api",
          "established_at": "2026-02-18T10:30:00Z",
          "confidence": 1.0
        }
      },
      {
        "source": "maintainer:numpy/numpy:charris",
        "target": "repo:numpy/numpy",
        "relationship_type": "maintained_by",
        "metadata": {
          "contribution_fraction": 0.23,
          "commit_count": 5234
        },
        "provenance": {
          "source": "github_api",
          "established_at": "2026-02-18T10:30:00Z",
          "confidence": 0.9
        }
      },
      {
        "source": "release:numpy/numpy:v1.26.0",
        "target": "cve:CVE-2024-1234",
        "relationship_type": "has_cve",
        "metadata": {
          "severity": "HIGH"
        },
        "provenance": {
          "source": "osv",
          "established_at": "2026-02-18T10:30:00Z",
          "match_confidence": 0.92,
          "confidence": 0.85
        }
      },
      {
        "source": "repo:numpy/numpy",
        "target": "registry:pypi:numpy",
        "relationship_type": "published_as",
        "metadata": {
          "package_name": "numpy",
          "latest_version": "1.26.0"
        },
        "provenance": {
          "source": "heuristic",
          "established_at": "2026-02-18T10:30:00Z",
          "match_confidence": 0.95,
          "confidence": 0.8
        }
      },
      {
        "source": "repo:numpy/numpy",
        "target": "risk:numpy/numpy:days_since_last_release",
        "relationship_type": "has_risk_factor",
        "metadata": {
          "contribution": 0.074
        },
        "provenance": {
          "source": "score_model",
          "established_at": "2026-02-18T10:30:00Z",
          "confidence": 1.0
        }
      }
    ]
  },
  "metadata": {
    "node_count": 15,
    "edge_count": 18,
    "data_sources": ["github_api", "osv", "heuristic", "score_model"],
    "cache_hit": true,
    "generation_time_ms": 245,
    "warnings": []
  }
}
```

**Node Types:**

The graph contains six types of nodes:

| Type | Description | ID Format |
|------|-------------|-----------|
| `repo` | The analyzed repository | `repo:{owner}/{name}` |
| `release` | Tagged releases/versions | `release:{owner}/{name}:{tag}` |
| `maintainer` | Key contributors | `maintainer:{owner}/{name}:{username}` |
| `cve` | Security vulnerabilities | `cve:{CVE-ID}` |
| `registry` | Package registries (PyPI, npm, etc.) | `registry:{type}:{package}` |
| `risk_factor` | Significant risk drivers | `risk:{owner}/{name}:{metric}` |

**Edge Types:**

Edges represent relationships between nodes:

| Type | Direction | Description |
|------|-----------|-------------|
| `has_release` | REPO → RELEASE | Repository has published this release |
| `maintained_by` | MAINTAINER → REPO | Maintainer contributes to repository |
| `has_cve` | RELEASE → CVE | Release is affected by vulnerability |
| `published_as` | REPO → REGISTRY | Repository is published to registry |
| `has_risk_factor` | REPO → RISK_FACTOR | Repository exhibits this risk factor |

**Provenance Metadata:**

Every node and edge includes provenance information for trust and traceability:

- `source`: Data source identifier (e.g., "github_api", "osv", "heuristic")
- `fetched_at` / `established_at`: ISO timestamp when data was obtained
- `data_confidence` / `confidence`: Numeric confidence score (0.0-1.0)
- `match_confidence`: (For CVE and Registry) Confidence in matching logic

**Confidence Levels:**
- **1.0**: Authoritative source (GitHub API for releases)
- **0.95**: Highly reliable (OSV.dev CVE data)
- **0.9**: Reliable with minor uncertainty (GitHub contributor stats)
- **0.85**: Good but some uncertainty (CVE-to-version mapping)
- **0.8**: Heuristic-based (registry detection from files)

**Error Responses:**

**400 Bad Request** - Invalid repository format:
```json
{
  "detail": "Invalid repository format. Use 'owner/repo' or GitHub URL"
}
```

**404 Not Found** - Repository does not exist:
```json
{
  "detail": "Repository not found: owner/repo"
}
```

**500 Internal Server Error** - Graph generation failed:
```json
{
  "detail": "Failed to generate graph: Internal error"
}
```

**503 Service Unavailable** - External API unavailable (returns partial graph when possible):
```json
{
  "repo": "numpy/numpy",
  "schema_version": "1.0",
  "generated_at": "2026-02-18T10:30:00Z",
  "graph": {
    "nodes": [...],
    "edges": [...]
  },
  "metadata": {
    "node_count": 8,
    "edge_count": 10,
    "data_sources": ["github_api", "score_data"],
    "warnings": [
      {
        "source": "osv",
        "error": "Connection timeout after 5s",
        "impact": "CVE nodes not included"
      }
    ]
  }
}
```

**Response Guarantees:**

1. Always returns valid JSON (never null)
2. Empty graphs have empty arrays, not null values
3. Partial data returned on external API failure (with warnings in metadata)
4. Validation errors logged but don't break response
5. All nodes and edges include provenance metadata

**Performance:**

- **Cached data**: < 100ms response time
- **Fresh build**: 1-3 seconds (depends on external APIs)
- **Graph size**: Supports up to 200 nodes efficiently

**Caching:**

- Graph data cached for 1 hour by default
- Use `refresh=false` (default) to use cached data
- Use `refresh=true` to force fresh data from external APIs
- Cache metadata included in response (`cache_hit` field)

---

## Graph Visualization

An interactive web-based visualization is available for exploring supply chain graphs.

**Access:** Open `ui/graph.html` in your browser after starting the API server.

**Features:**
- Interactive node-edge visualization using vis.js
- Click nodes to see detailed information
- Filter by node type and confidence level
- Search for specific nodes
- Export as JSON or PNG
- Toggle provenance information display

**See:** [Graph Visualization Guide](GRAPH_VISUALIZATION.md) for detailed usage instructions.

---

## Multi-Repo Persistent Graph API

The following endpoints support batch ingestion, persistent storage, and cross-repo queries for supply chain graphs.

### Environment Configuration

Configure the persistent graph system using environment variables:

```bash
# Database configuration
GRAPH_DB_PATH=data/graphs.db              # Path to SQLite database file
GRAPH_DB_ENABLED=true                     # Enable/disable persistence layer
GRAPH_TTL_HOURS=24                        # Cache TTL in hours
GRAPH_AUTO_REFRESH_STALE=false            # Auto-regenerate stale data

# Job worker configuration
GRAPH_WORKER_POLL_INTERVAL=5              # Seconds between job queue polls
GRAPH_WORKER_ENABLED=true                 # Enable/disable background worker
```

**Configuration Behavior:**
- `GRAPH_DB_ENABLED=false`: Disables persistence, falls back to dynamic generation
- `GRAPH_AUTO_REFRESH_STALE=false`: Returns stale cached data with `is_stale: true` flag
- `GRAPH_AUTO_REFRESH_STALE=true`: Automatically regenerates data when TTL exceeded

---

### Submit Batch Ingestion Job

Submit a batch job to ingest multiple repositories into the persistent graph database.

**Endpoint:** `POST /api/ingest`

**Request Body:**

```json
{
  "repos": [
    "numpy/numpy",
    "django/django",
    "psf/requests"
  ],
  "config": {
    "include_cves": true,
    "max_releases": 10,
    "max_maintainers": 5
  }
}
```

**Request Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repos` | array[string] | Yes | List of repository identifiers (owner/repo format) |
| `config` | object | No | Graph configuration options (same as /api/graph parameters) |

**Example Requests:**

```bash
# Basic batch ingestion
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "repos": ["numpy/numpy", "django/django", "psf/requests"]
  }'

# With custom configuration
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "repos": ["numpy/numpy", "scipy/scipy"],
    "config": {
      "include_cves": true,
      "max_releases": 5,
      "max_maintainers": 10
    }
  }'
```

**Success Response (202 Accepted):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "total_repos": 3,
  "message": "Ingestion job created successfully"
}
```

**Error Responses:**

**400 Bad Request** - Invalid request:
```json
{
  "detail": "repos list cannot be empty"
}
```

**400 Bad Request** - Too many repositories:
```json
{
  "detail": "Maximum 1000 repositories per batch"
}
```

---

### Query Job Status

Get the status and progress of an ingestion job.

**Endpoint:** `GET /api/jobs/{job_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | Yes | Job identifier (UUID) |

**Example Requests:**

```bash
# Query job status
curl "http://localhost:8000/api/jobs/550e8400-e29b-41d4-a716-446655440000"
```

**Success Response (200):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "total_repos": 3,
  "processed_repos": 2,
  "successful_repos": 2,
  "failed_repos": 0,
  "created_at": "2026-02-20T10:00:00Z",
  "started_at": "2026-02-20T10:00:05Z",
  "completed_at": null,
  "errors": []
}
```

**Job Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Job created, waiting to be processed |
| `running` | Job is currently being processed |
| `completed` | Job finished processing all repositories |
| `failed` | Job-level failure prevented completion |
| `interrupted` | Server restarted during job execution |

**Completed Job Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "total_repos": 3,
  "processed_repos": 3,
  "successful_repos": 2,
  "failed_repos": 1,
  "created_at": "2026-02-20T10:00:00Z",
  "started_at": "2026-02-20T10:00:05Z",
  "completed_at": "2026-02-20T10:02:30Z",
  "errors": [
    {
      "repo": "invalid/repo",
      "error": "Repository not found",
      "timestamp": "2026-02-20T10:01:15Z"
    }
  ]
}
```

**Error Responses:**

**404 Not Found** - Job does not exist:
```json
{
  "detail": "Job not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

---

### List Ingestion Jobs

List all ingestion jobs with optional filtering.

**Endpoint:** `GET /api/jobs`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `status` | string | No | - | Filter by job status (pending, running, completed, failed, interrupted) |
| `limit` | integer | No | `100` | Maximum number of results |
| `offset` | integer | No | `0` | Pagination offset |

**Example Requests:**

```bash
# List all jobs
curl "http://localhost:8000/api/jobs"

# Filter by status
curl "http://localhost:8000/api/jobs?status=completed"

# Pagination
curl "http://localhost:8000/api/jobs?limit=10&offset=20"
```

**Success Response (200):**

```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "total_repos": 3,
      "processed_repos": 3,
      "successful_repos": 2,
      "failed_repos": 1,
      "created_at": "2026-02-20T10:00:00Z",
      "completed_at": "2026-02-20T10:02:30Z"
    },
    {
      "job_id": "660e8400-e29b-41d4-a716-446655440001",
      "status": "running",
      "total_repos": 10,
      "processed_repos": 5,
      "successful_repos": 5,
      "failed_repos": 0,
      "created_at": "2026-02-20T11:00:00Z",
      "started_at": "2026-02-20T11:00:05Z"
    }
  ],
  "total": 2,
  "limit": 100,
  "offset": 0
}
```

---

### List Stored Repositories

List all repositories stored in the persistent graph database.

**Endpoint:** `GET /api/repos`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | `100` | Maximum number of results |
| `offset` | integer | No | `0` | Pagination offset |
| `older_than` | string | No | - | ISO timestamp - filter repos updated before this time |

**Example Requests:**

```bash
# List all repositories
curl "http://localhost:8000/api/repos"

# Pagination
curl "http://localhost:8000/api/repos?limit=50&offset=100"

# Find stale repositories (older than 7 days)
curl "http://localhost:8000/api/repos?older_than=2026-02-13T00:00:00Z"
```

**Success Response (200):**

```json
{
  "repos": [
    {
      "repo_full_name": "numpy/numpy",
      "node_count": 45,
      "edge_count": 52,
      "schema_version": "1.0",
      "created_at": "2026-02-15T10:00:00Z",
      "updated_at": "2026-02-20T08:30:00Z",
      "data_sources": ["github_api", "osv", "heuristic"],
      "generation_time_ms": 2450
    },
    {
      "repo_full_name": "django/django",
      "node_count": 38,
      "edge_count": 44,
      "schema_version": "1.0",
      "created_at": "2026-02-18T14:20:00Z",
      "updated_at": "2026-02-18T14:20:00Z",
      "data_sources": ["github_api", "osv"],
      "generation_time_ms": 1890
    }
  ],
  "total": 2,
  "limit": 100,
  "offset": 0
}
```

---

### Find Repositories by Maintainer

Find all repositories maintained by a specific user.

**Endpoint:** `GET /api/repos/by-maintainer/{username}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `username` | string | Yes | GitHub username |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | `100` | Maximum number of results |

**Example Requests:**

```bash
# Find repos by maintainer
curl "http://localhost:8000/api/repos/by-maintainer/guido"

# With limit
curl "http://localhost:8000/api/repos/by-maintainer/guido?limit=50"
```

**Success Response (200):**

```json
{
  "username": "guido",
  "repos": [
    {
      "repo_full_name": "python/cpython",
      "contribution_fraction": 0.15,
      "commit_count": 2340,
      "node_count": 52,
      "updated_at": "2026-02-20T08:00:00Z",
      "provenance": {
        "source": "github_api",
        "data_confidence": 0.9
      }
    },
    {
      "repo_full_name": "python/peps",
      "contribution_fraction": 0.08,
      "commit_count": 450,
      "node_count": 28,
      "updated_at": "2026-02-19T12:00:00Z",
      "provenance": {
        "source": "github_api",
        "data_confidence": 0.9
      }
    }
  ],
  "total": 2
}
```

---

### Find Repositories by CVE

Find all repositories affected by a specific CVE.

**Endpoint:** `GET /api/repos/by-cve/{cve_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cve_id` | string | Yes | CVE identifier (e.g., CVE-2024-1234) |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | `100` | Maximum number of results |

**Example Requests:**

```bash
# Find repos affected by CVE
curl "http://localhost:8000/api/repos/by-cve/CVE-2024-1234"

# With limit
curl "http://localhost:8000/api/repos/by-cve/CVE-2024-1234?limit=50"
```

**Success Response (200):**

```json
{
  "cve_id": "CVE-2024-1234",
  "repos": [
    {
      "repo_full_name": "numpy/numpy",
      "severity": "HIGH",
      "cvss_score": 7.5,
      "affected_releases": ["v1.25.0", "v1.25.1", "v1.26.0"],
      "node_count": 45,
      "updated_at": "2026-02-20T08:30:00Z",
      "provenance": {
        "source": "osv",
        "match_confidence": 0.92,
        "data_confidence": 0.95
      }
    },
    {
      "repo_full_name": "scipy/scipy",
      "severity": "HIGH",
      "cvss_score": 7.5,
      "affected_releases": ["v1.11.0"],
      "node_count": 38,
      "updated_at": "2026-02-19T15:00:00Z",
      "provenance": {
        "source": "osv",
        "match_confidence": 0.88,
        "data_confidence": 0.95
      }
    }
  ],
  "total": 2
}
```

---

### Find Repository by Package

Find the repository associated with a package in a registry.

**Endpoint:** `GET /api/repos/by-package`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `registry` | string | Yes | Registry type (pypi, npm, maven, etc.) |
| `package` | string | Yes | Package name |

**Example Requests:**

```bash
# Find repo for PyPI package
curl "http://localhost:8000/api/repos/by-package?registry=pypi&package=numpy"

# Find repo for npm package
curl "http://localhost:8000/api/repos/by-package?registry=npm&package=express"
```

**Success Response (200):**

```json
{
  "registry_type": "pypi",
  "package_name": "numpy",
  "repo": {
    "repo_full_name": "numpy/numpy",
    "latest_version": "1.26.0",
    "node_count": 45,
    "updated_at": "2026-02-20T08:30:00Z",
    "provenance": {
      "source": "heuristic",
      "match_confidence": 0.95,
      "data_confidence": 0.8
    }
  }
}
```

**Error Responses:**

**404 Not Found** - Package not found:
```json
{
  "detail": "Package not found: pypi/unknown-package"
}
```

---

### Delete Repository

Delete a repository and all associated data from the persistent graph database.

**Endpoint:** `DELETE /api/repos/{repo_full_name}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_full_name` | string | Yes | Repository identifier (owner/repo format, URL-encoded) |

**Example Requests:**

```bash
# Delete repository
curl -X DELETE "http://localhost:8000/api/repos/numpy%2Fnumpy"

# Alternative with proper encoding
curl -X DELETE "http://localhost:8000/api/repos/$(echo 'numpy/numpy' | jq -sRr @uri)"
```

**Success Response (204 No Content):**

No response body. HTTP status 204 indicates successful deletion.

**Error Responses:**

**404 Not Found** - Repository not in database:
```json
{
  "detail": "Repository not found: numpy/numpy"
}
```

---

## Backward Compatibility

The `/api/graph` endpoint maintains full backward compatibility while leveraging the persistent graph database:

**Cache Behavior:**
- If repository exists in database and is fresh (within TTL): Returns cached data with `cache_hit: true`
- If repository exists but is stale: 
  - With `GRAPH_AUTO_REFRESH_STALE=false`: Returns stale data with `is_stale: true`
  - With `GRAPH_AUTO_REFRESH_STALE=true`: Regenerates and updates database
- If repository not in database: Generates dynamically and saves to database (best-effort)
- If database unavailable: Falls back to dynamic generation without caching

**Response Format:**

The response format is identical to the original `/api/graph` endpoint, with additional metadata fields:

```json
{
  "repo": "numpy/numpy",
  "schema_version": "1.0",
  "generated_at": "2026-02-20T10:30:00Z",
  "graph": { ... },
  "metadata": {
    "node_count": 45,
    "edge_count": 52,
    "data_sources": ["github_api", "osv"],
    "cache_hit": true,
    "is_stale": false,
    "created_at": "2026-02-15T10:00:00Z",
    "updated_at": "2026-02-20T08:30:00Z",
    "generation_time_ms": 2450,
    "warnings": []
  }
}
```

**New Metadata Fields:**
- `cache_hit` (boolean): True if data came from database cache
- `is_stale` (boolean): True if cached data exceeded TTL (only when auto_refresh_stale=false)
- `created_at` (string): ISO timestamp when graph was first stored
- `updated_at` (string): ISO timestamp when graph was last updated

