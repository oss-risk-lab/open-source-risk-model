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

---

## Dependency Graph API

The following endpoints provide supply chain dependency analysis, enabling you to discover what packages a repository depends on and which repositories depend on specific packages.

### Get Repository Dependencies

Get all dependencies for a repository.

**Endpoint:** `GET /api/repos/{owner}/{repo}/dependencies`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_dev` | boolean | No | `false` | Include development dependencies |

**Example Requests:**

```bash
# Get production dependencies
curl "http://localhost:8000/api/repos/pallets/flask/dependencies"

# Include development dependencies
curl "http://localhost:8000/api/repos/pallets/flask/dependencies?include_dev=true"
```

**Success Response (200):**

```json
{
  "repo": "pallets/flask",
  "dependencies": [
    {
      "package_name": "werkzeug",
      "registry_type": "pypi",
      "specifier": ">=3.0.0",
      "is_direct": true,
      "is_dev": false,
      "is_optional": false,
      "dependency_group": "prod",
      "manifest_path": "requirements/requirements.txt",
      "resolved_repo": "pallets/werkzeug",
      "resolution_confidence": 0.95,
      "resolution_method": "pypi_project_urls"
    },
    {
      "package_name": "jinja2",
      "registry_type": "pypi",
      "specifier": ">=3.1.2",
      "is_direct": true,
      "is_dev": false,
      "is_optional": false,
      "dependency_group": "prod",
      "manifest_path": "requirements/requirements.txt",
      "resolved_repo": "pallets/jinja",
      "resolution_confidence": 0.95,
      "resolution_method": "pypi_project_urls"
    },
    {
      "package_name": "pytest",
      "registry_type": "pypi",
      "specifier": ">=7.0.0",
      "is_direct": true,
      "is_dev": true,
      "is_optional": false,
      "dependency_group": "dev",
      "manifest_path": "requirements/requirements-dev.txt",
      "resolved_repo": "pytest-dev/pytest",
      "resolution_confidence": 0.95,
      "resolution_method": "pypi_project_urls"
    }
  ],
  "total": 3,
  "metadata": {
    "include_dev": true,
    "manifest_files": ["requirements/requirements.txt", "requirements/requirements-dev.txt"],
    "parsed_at": "2026-02-23T10:00:00Z"
  }
}
```

**Dependency Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `package_name` | string | Package name in registry |
| `registry_type` | string | Registry type (pypi, npm, maven, etc.) |
| `specifier` | string | Version constraint (e.g., ">=3.0.0", "^18.2.0") |
| `is_direct` | boolean | True if direct dependency (not transitive) |
| `is_dev` | boolean | True if development dependency |
| `is_optional` | boolean | True if optional dependency |
| `dependency_group` | string | Dependency group (prod, dev, test, docs, optional) |
| `manifest_path` | string | Path to manifest file in repository |
| `resolved_repo` | string | Source repository (if resolved) |
| `resolution_confidence` | float | Confidence score (0.0-1.0) |
| `resolution_method` | string | Resolution method used |

**Resolution Confidence:**

| Confidence | Method | Description |
|-----------|--------|-------------|
| 0.95 | pypi_project_urls | Explicit Source/Repository link in PyPI |
| 0.90 | npm_repository | Explicit repository field in package.json |
| 0.75 | pypi_home_page | Homepage field (might be docs site) |
| 0.70 | npm_homepage | Homepage field (might be docs site) |
| 0.00 | unresolved | Could not resolve to repository |

**Error Responses:**

**404 Not Found** - Repository not found or no dependencies:
```json
{
  "detail": "No dependencies found for repository: pallets/flask"
}
```

---

### Get Package Dependents

Get all repositories that depend on a specific package.

**Endpoint:** `GET /api/packages/{package}/dependents`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `package` | string | Yes | Package name |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `registry` | string | Yes | - | Registry type (pypi, npm, maven, etc.) |
| `limit` | integer | No | `100` | Maximum number of results |
| `offset` | integer | No | `0` | Pagination offset |

**Example Requests:**

```bash
# Get dependents for PyPI package
curl "http://localhost:8000/api/packages/requests/dependents?registry=pypi"

# Get dependents for npm package with pagination
curl "http://localhost:8000/api/packages/react/dependents?registry=npm&limit=50&offset=0"
```

**Success Response (200):**

```json
{
  "package_name": "requests",
  "registry_type": "pypi",
  "resolved_repo": "psf/requests",
  "resolution_confidence": 0.95,
  "dependents": [
    {
      "repo_full_name": "pallets/flask",
      "specifier": ">=2.31.0",
      "is_direct": true,
      "is_dev": false,
      "dependency_group": "prod",
      "manifest_path": "requirements.txt",
      "confidence": 0.9
    },
    {
      "repo_full_name": "django/django",
      "specifier": ">=2.25.0",
      "is_direct": true,
      "is_dev": false,
      "dependency_group": "prod",
      "manifest_path": "requirements/base.txt",
      "confidence": 0.9
    }
  ],
  "total": 2,
  "limit": 100,
  "offset": 0
}
```

**Error Responses:**

**404 Not Found** - Package not found:
```json
{
  "detail": "Package not found: pypi/unknown-package"
}
```

**400 Bad Request** - Missing registry parameter:
```json
{
  "detail": "registry parameter is required"
}
```

---

### Dependency Graph Configuration

Configure dependency parsing using environment variables:

```bash
# Enable/disable dependency parsing
GRAPH_PARSE_DEPENDENCIES=true

# Maximum dependencies to parse per repository
GRAPH_MAX_DEPENDENCIES=100

# Include development dependencies
GRAPH_INCLUDE_DEV_DEPENDENCIES=false

# Enable package resolution
GRAPH_RESOLVE_PACKAGES=true

# Manifest cache TTL (hours)
MANIFEST_CACHE_TTL_HOURS=24

# Package resolution cache TTL (hours)
PACKAGE_RESOLUTION_CACHE_TTL_HOURS=168

# API rate limits
MANIFEST_DISCOVERY_MAX_API_CALLS=10
MANIFEST_FETCH_MAX_API_CALLS=20
```

**Supported Ecosystems:**

| Ecosystem | Manifest Files | Status |
|-----------|---------------|--------|
| Python | requirements.txt, pyproject.toml | ✅ Supported |
| JavaScript | package.json | ✅ Supported |
| Java | pom.xml | 🔄 Planned |
| Go | go.mod | 🔄 Planned |
| Ruby | Gemfile | 🔄 Planned |
| Rust | Cargo.toml | 🔄 Planned |

**See Also:**
- [Dependency Graph User Guide](DEPENDENCY_GRAPH_GUIDE.md) - Complete documentation
- [Quick Reference](DEPENDENCY_QUICK_REFERENCE.md) - Quick reference card



---

### Query API

Execute structured queries against the dependency graph database.

**Endpoint:** `POST /api/query`

**Request Body:**

```json
{
  "query": "Natural language query or description",
  "intent": "intent_name",  // Optional in natural language mode, required in dev mode
  "parameters": {},          // Intent-specific parameters
  "max_results": 100         // Optional, default: 100
}
```

**Modes:**

1. **Dev Mode** (no API key needed): Specify `intent` and `parameters` explicitly
2. **Natural Language Mode** (requires OPENAI_API_KEY): Omit `intent`, LLM classifies automatically

**Available Intents:**

| Intent | Parameters | Description |
|--------|-----------|-------------|
| `dataset_stats` | none | Overall dataset statistics |
| `list_dependencies` | `repo_full_name` (required), `dependency_group` (optional) | List direct dependencies |
| `find_dependents` | `package_name` (required), `registry_type` (optional) | Find who depends on a package |
| `get_dependency_tree` | `repo_full_name` (required), `max_depth` (optional, default: 3) | Get dependency tree |
| `check_resolution` | `package_name` (required), `registry_type` (required) | Check package-to-repo resolution |
| `list_unresolved` | `repo_full_name` (optional) | List unresolved dependencies |
| `list_manifests` | `repo_full_name` (required) | List manifest files |
| `count_by_manifest_type` | none | Count manifests by type |
| `repo_stats` | `repo_full_name` (required) | Repository statistics |
| `search_repos` | `pattern` (required) | Search repositories by name |
| `search_packages` | `pattern` (required), `registry_type` (optional) | Search packages by name |

**Example Requests:**

```bash
# Dev Mode: Dataset statistics
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show dataset stats",
    "intent": "dataset_stats",
    "parameters": {}
  }'

# Dev Mode: List dependencies
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "List dependencies",
    "intent": "list_dependencies",
    "parameters": {"repo_full_name": "pallets/flask"},
    "max_results": 10
  }'

# Dev Mode: Find dependents
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who uses requests?",
    "intent": "find_dependents",
    "parameters": {"package_name": "requests", "registry_type": "pypi"}
  }'

# Natural Language Mode (requires OPENAI_API_KEY)
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the dependencies of Flask?",
    "max_results": 20
  }'
```

**Response Format:**

```json
{
  "intent": "list_dependencies",
  "parameters": {"repo_full_name": "pallets/flask"},
  "confidence": 1.0,
  "results": [
    {
      "package_name": "click",
      "registry_type": "pypi",
      "specifier": ">=8.1.3",
      "dependency_group": "prod",
      "manifest_path": "pyproject.toml",
      "resolved_repo": "pallets/click",
      "resolution_confidence": 0.95,
      "is_optional": 0
    }
  ],
  "result_count": 35,
  "execution_time_ms": 4.75,
  "metadata": {
    "repo_full_name": "pallets/flask",
    "dependency_group": null,
    "direct_only": true
  }
}
```

**Error Responses:**

```json
// Invalid intent
{
  "detail": "Unknown intent: invalid_intent"
}

// Missing required parameter
{
  "detail": "repo_full_name is required"
}

// Natural language mode without API key
{
  "detail": "Natural language queries require OPENAI_API_KEY"
}
```

**Performance:**
- Dev mode queries: < 100ms
- Natural language mode: 1-3s (LLM classification + query execution)
- All queries use parameterized SQL (SQL injection protected)
- Results cached in database (no network calls during queries)

**Security:**
- LLM never generates SQL (only classifies intent)
- Intent allowlist enforced (11 predefined intents)
- Parameterized queries prevent SQL injection
- Confidence threshold (0.7) for LLM classifications

**See Also:**
- `QUERY_API_QUICK_START.md` - Quick start guide with examples
- `WEEK_2_PROGRESS.md` - Implementation details and architecture
