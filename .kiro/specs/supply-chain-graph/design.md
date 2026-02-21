# Supply Chain Risk Graph - Design Document

## Overview

This design transforms the flat risk scoring model into a graph-based supply chain risk intelligence engine. The graph represents relationships between repositories, releases, vulnerabilities, maintainers, and risk factors, enabling visual exploration and contextual risk analysis.

**Core Philosophy:** Practical, demo-focused implementation that demonstrates enterprise-grade thinking without over-engineering. Build incrementally with clear extension points.

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│  /api/score (existing)    /api/graph (new)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Graph Builder                            │
│  • Orchestrates data collection                              │
│  • Constructs graph from multiple sources                    │
│  • Validates graph structure                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│  Score Data      │ │  CVE Data    │ │  Registry    │
│  (existing)      │ │  (OSV.dev)   │ │  Detection   │
└──────────────────┘ └──────────────┘ └──────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Graph Schema                              │
│  Nodes: Repo, Release, Maintainer, CVE, Registry, RiskFactor│
│  Edges: Relationships between nodes                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Frontend Visualization                      │
│  vis.js network graph with interactive exploration           │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Graceful Degradation:** Missing data produces partial graphs, not failures
2. **Incremental Complexity:** Start with core nodes, add enrichment progressively
3. **Performance First:** Cache aggressively, limit node counts, async where beneficial
4. **Extensibility:** Clear interfaces for adding new node/edge types
5. **Testability:** Property-based tests for graph invariants


## Graph Schema

### Node Types

The graph schema extends the existing `schema.py` implementation with clear semantics:

**1. REPO (Repository)**
- **Purpose:** Central node representing the analyzed repository
- **ID Format:** `repo:{owner}/{name}`
- **Metadata:**
  - `url`: GitHub URL
  - `maintenance_risk`: Overall risk score (0-1)
  - `maintenance_label`: Risk band (low/medium/high/critical)
  - `coverage`: Feature coverage percentage
  - `confidence`: Confidence level (high/medium/low)
  - `stars`: Star count
  - `archived`: Boolean flag
- **Provenance:**
  - `source`: "github_api"
  - `fetched_at`: ISO timestamp
  - `data_confidence`: 0.0-1.0 (based on feature coverage)

**2. RELEASE (Software Release)**
- **Purpose:** Represents a tagged release/version
- **ID Format:** `release:{owner}/{name}:{tag}`
- **Metadata:**
  - `tag_name`: Release tag (e.g., "v1.2.3")
  - `published_at`: ISO timestamp
  - `days_ago`: Days since release
  - `is_latest`: Boolean flag
  - `is_prerelease`: Boolean flag
- **Provenance:**
  - `source`: "github_api"
  - `fetched_at`: ISO timestamp
  - `data_confidence`: 1.0 (GitHub API is authoritative)

**3. MAINTAINER (Contributor)**
- **Purpose:** Key contributors to the repository
- **ID Format:** `maintainer:{owner}/{name}:{username}` or `maintainer:{owner}/{name}:aggregate`
- **Metadata:**
  - `username`: GitHub username (or "aggregate" for summary node)
  - `contribution_fraction`: Percentage of commits (0-1)
  - `commit_count`: Number of commits
  - `last_activity`: ISO timestamp of last commit
  - `type`: "individual" or "aggregate"
- **Provenance:**
  - `source`: "github_api"
  - `fetched_at`: ISO timestamp
  - `data_confidence`: 0.9 (GitHub API is reliable but may have incomplete history)

**4. CVE (Vulnerability)**
- **Purpose:** Known security vulnerabilities
- **ID Format:** `cve:{CVE-ID}` (e.g., `cve:CVE-2024-1234`)
- **Metadata:**
  - `cve_id`: Official CVE identifier
  - `severity`: CVSS severity (LOW/MEDIUM/HIGH/CRITICAL)
  - `cvss_score`: Numeric score (0-10)
  - `summary`: Brief description
  - `published`: ISO timestamp
  - `fixed_in`: Version that fixes the vulnerability (if known)
  - `source`: Data source (osv, github_advisory)
- **Provenance:**
  - `source`: "osv" or "github_advisory"
  - `fetched_at`: ISO timestamp
  - `match_confidence`: 0.0-1.0 (confidence in version matching)
  - `data_confidence`: 0.95 (OSV.dev is highly reliable but may have false positives)

**5. REGISTRY (Package Registry)**
- **Purpose:** Distribution channels (PyPI, npm, Maven, etc.)
- **ID Format:** `registry:{type}:{package_name}`
- **Metadata:**
  - `registry_type`: "pypi", "npm", "maven", "rubygems", etc.
  - `package_name`: Name in registry
  - `latest_version`: Latest published version
  - `download_count`: Monthly downloads (if available)
  - `registry_url`: Link to package page
- **Provenance:**
  - `source`: "heuristic" (file detection) or "registry_api" (future)
  - `fetched_at`: ISO timestamp
  - `match_confidence`: 0.0-1.0 (confidence in package name extraction)
  - `data_confidence`: 0.8 (heuristic detection has some uncertainty)

**6. RISK_FACTOR (Risk Metric)**
- **Purpose:** Significant risk drivers from scoring model
- **ID Format:** `risk:{owner}/{name}:{metric_key}`
- **Metadata:**
  - `key`: Metric identifier (e.g., "days_since_last_release")
  - `label`: Human-readable name
  - `raw_value`: Actual measured value
  - `risk_score`: Normalized risk (0-1)
  - `contribution`: Contribution to overall score
  - `weight`: Feature weight in model
  - `category`: Metric category (activity/community/quality)
- **Provenance:**
  - `source`: "score_model"
  - `fetched_at`: ISO timestamp
  - `data_confidence`: Inherited from repo node confidence


### Edge Types

Edges represent relationships between nodes. Each edge includes provenance metadata to establish trust and traceability.

**1. HAS_RELEASE**
- **Direction:** REPO → RELEASE
- **Meaning:** Repository has published this release
- **Metadata:**
  - `days_ago`: Days since release
  - `is_latest`: Boolean flag
- **Provenance:**
  - `source`: "github_api"
  - `established_at`: ISO timestamp
  - `confidence`: 1.0 (GitHub API is authoritative)

**2. MAINTAINED_BY**
- **Direction:** MAINTAINER → REPO
- **Meaning:** Maintainer contributes to repository
- **Metadata:**
  - `contribution_fraction`: Percentage of commits
  - `commit_count`: Number of commits
- **Provenance:**
  - `source`: "github_api"
  - `established_at`: ISO timestamp
  - `confidence`: 0.9 (based on GitHub's contribution tracking)

**3. HAS_CVE**
- **Direction:** RELEASE → CVE
- **Meaning:** Release is affected by this vulnerability
- **Metadata:**
  - `severity`: Vulnerability severity
  - `fixed_in`: Version that fixes it (if known)
- **Provenance:**
  - `source`: "osv" or "github_advisory"
  - `established_at`: ISO timestamp
  - `match_confidence`: 0.0-1.0 (confidence in version range matching)
  - `confidence`: 0.85 (CVE-to-version mapping has some uncertainty)

**4. PUBLISHED_AS**
- **Direction:** REPO → REGISTRY
- **Meaning:** Repository is published to this registry
- **Metadata:**
  - `package_name`: Name in registry
  - `latest_version`: Latest version
- **Provenance:**
  - `source`: "heuristic" or "registry_api"
  - `established_at`: ISO timestamp
  - `match_confidence`: 0.0-1.0 (confidence in package name extraction)
  - `confidence`: 0.8 (heuristic detection has uncertainty)

**5. HAS_RISK_FACTOR**
- **Direction:** REPO → RISK_FACTOR
- **Meaning:** Repository exhibits this risk factor
- **Metadata:**
  - `contribution`: Contribution to overall risk score
- **Provenance:**
  - `source`: "score_model"
  - `established_at`: ISO timestamp
  - `confidence`: Inherited from repo confidence

### Graph Invariants

These properties MUST hold for all valid graphs:

1. **Single Root:** Exactly one REPO node exists per graph
2. **Valid References:** All edge source/target IDs reference existing nodes
3. **Unique IDs:** No duplicate node IDs within a graph
4. **Type Safety:** Node types match NodeType enum, edge types match EdgeType enum
5. **Acyclic Relationships:** No cycles in the graph (DAG structure)
6. **Metadata Completeness:** Required metadata fields present for each node type
7. **Provenance Completeness:** All nodes and edges include provenance metadata (source, timestamp, confidence)

### Provenance and Confidence

Every node and edge includes provenance metadata to establish trust and traceability:

**Provenance Fields:**
- `source`: Data source identifier (e.g., "github_api", "osv", "heuristic")
- `fetched_at` or `established_at`: ISO timestamp when data was obtained
- `confidence` or `data_confidence`: Numeric confidence score (0.0-1.0)
- `match_confidence`: (For CVE and Registry) Confidence in matching/detection logic

**Confidence Levels:**
- **1.0:** Authoritative source (GitHub API for releases)
- **0.95:** Highly reliable (OSV.dev CVE data)
- **0.9:** Reliable with minor uncertainty (GitHub contributor stats)
- **0.85:** Good but some uncertainty (CVE-to-version mapping)
- **0.8:** Heuristic-based (registry detection from files)
- **< 0.8:** Low confidence, should be flagged to user

**Why This Matters:**
- **Trust:** Users can assess reliability of each data point
- **Debugging:** Trace where data came from and when
- **Filtering:** Filter graph by confidence threshold
- **Auditing:** Establish data lineage for compliance
- **Transparency:** Show users what's certain vs. inferred

**Example Node with Provenance:**
```json
{
  "id": "cve:CVE-2024-1234",
  "type": "cve",
  "label": "CVE-2024-1234",
  "metadata": {
    "severity": "HIGH",
    "cvss_score": 7.5,
    "summary": "Buffer overflow vulnerability"
  },
  "provenance": {
    "source": "osv",
    "fetched_at": "2026-02-13T10:30:00Z",
    "match_confidence": 0.92,
    "data_confidence": 0.95
  }
}
```


## API Design

### New Endpoint: GET /api/graph

**Purpose:** Return graph representation of repository supply chain risk

**URL:** `/api/graph`

**Method:** `GET`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `repo` | string | Yes | - | Repository in `owner/repo` format or GitHub URL |
| `refresh` | boolean | No | `false` | Force refresh from external APIs |
| `include_cves` | boolean | No | `true` | Include CVE nodes (may be slow) |
| `max_releases` | integer | No | `10` | Maximum number of release nodes |
| `max_maintainers` | integer | No | `5` | Maximum number of maintainer nodes |

**Example Request:**

```bash
curl "http://localhost:8000/api/graph?repo=numpy/numpy"
curl "http://localhost:8000/api/graph?repo=numpy/numpy&include_cves=false&max_releases=5"
```

**Success Response (200):**

```json
{
  "repo": "numpy/numpy",
  "schema_version": "1.0",
  "generated_at": "2026-02-13T10:30:00Z",
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
          "stars": 28500,
          "archived": false
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
          "is_latest": true
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
        }
      }
    ]
  },
  "metadata": {
    "node_count": 15,
    "edge_count": 18,
    "data_sources": ["github_api", "osv"],
    "cache_hit": true,
    "generation_time_ms": 245
  }
}
```

**Error Responses:**

- **400 Bad Request:** Invalid repository format
- **404 Not Found:** Repository does not exist
- **500 Internal Server Error:** Graph generation failed
- **503 Service Unavailable:** External API unavailable (with partial graph if possible)

**Response Guarantees:**

1. Always returns valid JSON (never null)
2. Empty graph has empty arrays, not null values
3. Partial data on external API failure (with warning in metadata)
4. Validation errors logged but don't break response


## Data Source Integration

### 1. Repository Score Data (Existing)

**Source:** Existing `score_repo()` function
**Data Provided:**
- Repository metadata (stars, archived status, URL)
- Risk scores and labels
- Feature values and risk contributions
- Maintainer statistics (contributor count, top contributor fraction)
- Release timing (days since last release)

**Integration:**
- Already implemented in `GraphBuilder._add_repo_node()`
- Extend to extract more granular data for Release and Maintainer nodes

### 2. CVE Data (New - OSV.dev)

**Source:** [OSV.dev API](https://osv.dev/) - Open Source Vulnerabilities database

**Why OSV.dev:**
- Free, no authentication required
- Comprehensive coverage (GitHub Advisory, PyPI, npm, etc.)
- Simple REST API
- Structured JSON responses
- Actively maintained by Google

**API Endpoint:**
```
POST https://api.osv.dev/v1/query
Content-Type: application/json

{
  "package": {
    "name": "numpy",
    "ecosystem": "PyPI"
  }
}
```

**Response Format:**
```json
{
  "vulns": [
    {
      "id": "GHSA-xxxx-yyyy-zzzz",
      "summary": "Buffer overflow in numpy.array",
      "severity": [
        {
          "type": "CVSS_V3",
          "score": "7.5 HIGH"
        }
      ],
      "affected": [
        {
          "package": {"name": "numpy", "ecosystem": "PyPI"},
          "ranges": [
            {
              "type": "ECOSYSTEM",
              "events": [
                {"introduced": "0"},
                {"fixed": "1.22.0"}
              ]
            }
          ]
        }
      ],
      "published": "2024-01-15T10:00:00Z"
    }
  ]
}
```

**Integration Strategy:**

1. **Ecosystem Detection:**
   - Detect package ecosystem from repo files:
     - `setup.py`, `pyproject.toml` → PyPI
     - `package.json` → npm
     - `pom.xml` → Maven
     - `Gemfile` → RubyGems
   - Extract package name from manifest files

2. **CVE Fetching:**
   - Query OSV.dev with detected package/ecosystem
   - Parse vulnerability records
   - Map CVEs to release versions using `affected.ranges`

3. **Caching:**
   - Cache CVE data in `data/cve/{ecosystem}__{package}.json`
   - TTL: 24 hours (vulnerabilities don't change frequently)
   - Refresh on `refresh=true` parameter

4. **Error Handling:**
   - Network timeout: 5 seconds
   - Rate limiting: Exponential backoff
   - API unavailable: Return graph without CVE nodes, log warning
   - No CVEs found: Valid state, empty CVE list

**Implementation Module:**
```python
# src/open_source_risk_model/graph/cve_fetcher.py

class CVEFetcher:
    def fetch_cves(self, package_name: str, ecosystem: str) -> List[CVERecord]:
        """Fetch CVEs from OSV.dev with caching"""
        
    def map_cves_to_releases(self, cves: List[CVERecord], releases: List[str]) -> Dict[str, List[CVERecord]]:
        """Map which CVEs affect which releases"""
```


### 3. Release Data (GitHub API)

**Source:** GitHub Releases API (already authenticated)

**API Endpoint:**
```
GET https://api.github.com/repos/{owner}/{repo}/releases
```

**Response Format:**
```json
[
  {
    "tag_name": "v1.26.0",
    "name": "NumPy 1.26.0",
    "published_at": "2024-09-16T10:00:00Z",
    "prerelease": false,
    "draft": false
  }
]
```

**Integration Strategy:**

1. **Fetching:**
   - Use existing GitHub client
   - Fetch latest N releases (default: 10, configurable via `max_releases`)
   - Sort by `published_at` descending

2. **Caching:**
   - Cache in `data/releases/{owner}__{repo}.json`
   - TTL: 1 hour (releases are relatively stable)
   - Include in existing snapshot refresh logic

3. **Node Creation:**
   - Create RELEASE node for each release
   - Mark most recent as `is_latest: true`
   - Calculate `days_ago` from `published_at`

**Implementation:**
```python
# Extend existing GitHub client in src/open_source_risk_model/github_client.py

def fetch_releases(self, owner: str, repo: str, max_count: int = 10) -> List[Dict]:
    """Fetch recent releases from GitHub API"""
```

### 4. Package Registry Detection (Heuristic)

**Source:** Repository file analysis (no external API initially)

**Detection Logic:**

| File Present | Registry Type | Package Name Extraction |
|--------------|---------------|-------------------------|
| `setup.py` or `pyproject.toml` | PyPI | Parse `name` field |
| `package.json` | npm | Parse `name` field |
| `pom.xml` | Maven | Parse `<artifactId>` |
| `Gemfile` or `*.gemspec` | RubyGems | Parse `spec.name` |
| `Cargo.toml` | crates.io | Parse `[package] name` |

**Implementation Strategy:**

1. **File Detection:**
   - Check for manifest files in repo root
   - Use GitHub Contents API: `GET /repos/{owner}/{repo}/contents/`
   - Cache file list with snapshot data

2. **Package Name Parsing:**
   - Download manifest file content
   - Parse using language-specific logic:
     - Python: `ast.parse()` for setup.py, `toml.load()` for pyproject.toml
     - JavaScript: `json.loads()` for package.json
     - XML: `xml.etree.ElementTree` for pom.xml

3. **Registry Node Creation:**
   - Create REGISTRY node with detected info
   - Initially: No download stats (requires external API)
   - Future enhancement: Query registry APIs for stats

**Implementation:**
```python
# src/open_source_risk_model/graph/registry_detector.py

class RegistryDetector:
    def detect_registries(self, repo_files: List[str]) -> List[RegistryInfo]:
        """Detect package registries from repo files"""
        
    def extract_package_name(self, file_content: str, file_type: str) -> Optional[str]:
        """Extract package name from manifest file"""
```


### 5. Maintainer Data (GitHub API)

**Source:** GitHub Contributors API

**API Endpoint:**
```
GET https://api.github.com/repos/{owner}/{repo}/contributors
```

**Response Format:**
```json
[
  {
    "login": "charris",
    "contributions": 5234,
    "avatar_url": "https://avatars.githubusercontent.com/u/...",
    "type": "User"
  }
]
```

**Integration Strategy:**

1. **Fetching:**
   - Use existing GitHub client
   - Fetch top N contributors (default: 5, configurable via `max_maintainers`)
   - Sort by contribution count descending

2. **Caching:**
   - Cache in `data/contributors/{owner}__{repo}.json`
   - TTL: 24 hours (contributor data changes slowly)

3. **Node Creation:**
   - Create MAINTAINER node for each top contributor
   - Calculate `contribution_fraction` = contributor_commits / total_commits
   - Optionally create aggregate node for "other contributors"

**Implementation:**
```python
# Extend existing GitHub client

def fetch_contributors(self, owner: str, repo: str, max_count: int = 5) -> List[Dict]:
    """Fetch top contributors from GitHub API"""
```


## Graph Builder Architecture

### Enhanced GraphBuilder

Extend the existing `GraphBuilder` class to orchestrate all data sources:

```python
class GraphBuilder:
    """Builds supply chain risk graph from multiple data sources"""
    
    def __init__(
        self,
        full_name: str,
        score_data: Dict[str, Any],
        github_client: GitHubClient,
        cve_fetcher: CVEFetcher,
        registry_detector: RegistryDetector,
        config: GraphConfig
    ):
        self.full_name = full_name
        self.score_data = score_data
        self.github_client = github_client
        self.cve_fetcher = cve_fetcher
        self.registry_detector = registry_detector
        self.config = config
        self.graph = Graph()
    
    def build(self) -> Graph:
        """Build complete graph with all enrichments"""
        # Core nodes (always present)
        self._add_repo_node()
        self._add_risk_factor_nodes()
        
        # Enrichment nodes (may fail gracefully)
        try:
            self._add_release_nodes()
        except Exception as e:
            self._log_error("release_nodes", e)
        
        try:
            self._add_maintainer_nodes()
        except Exception as e:
            self._log_error("maintainer_nodes", e)
        
        if self.config.include_cves:
            try:
                self._add_cve_nodes()
            except Exception as e:
                self._log_error("cve_nodes", e)
        
        try:
            self._add_registry_nodes()
        except Exception as e:
            self._log_error("registry_nodes", e)
        
        # Validate and return
        self._validate_graph()
        return self.graph
```

### Configuration

```python
@dataclass
class GraphConfig:
    """Configuration for graph generation"""
    include_cves: bool = True
    max_releases: int = 10
    max_maintainers: int = 5
    max_risk_factors: int = 5
    cve_timeout_seconds: int = 5
    cache_ttl_hours: int = 24
```

### Error Handling Strategy

**Principle:** Never fail the entire graph due to one data source failure

**Implementation:**
1. Wrap each enrichment step in try-except
2. Log errors with context (data source, repo, error message)
3. Add error info to graph metadata
4. Return partial graph with warning

**Example Metadata on Partial Failure:**
```json
{
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


## Visualization Design

### Technology Choice: vis.js

**Selected Library:** [vis.js Network](https://visjs.github.io/vis-network/docs/network/)

**Rationale:**
- No build step required (CDN-hosted)
- Rich interactive features (zoom, pan, drag)
- Good performance for graphs up to 200 nodes
- Extensive customization options
- Active community and documentation
- MIT licensed

**Alternatives Considered:**
- D3.js: Too complex for this use case, requires significant custom code
- Cytoscape.js: Excellent but heavier, overkill for our node count
- Sigma.js: Good but less interactive features

### Visual Design

**Node Styling by Type:**

| Node Type | Color | Shape | Icon |
|-----------|-------|-------|------|
| REPO | Blue (#2563eb) | Box | 📦 |
| RELEASE | Green (#16a34a) | Diamond | 🏷️ |
| MAINTAINER | Purple (#9333ea) | Circle | 👤 |
| CVE | Red (#dc2626) | Triangle | ⚠️ |
| REGISTRY | Orange (#ea580c) | Hexagon | 📚 |
| RISK_FACTOR | Yellow (#ca8a04) | Ellipse | ⚡ |

**Edge Styling:**

- Default: Gray (#6b7280), width 2
- High-risk relationships (CVE, high-contribution risk factors): Red (#dc2626), width 3
- Low-confidence edges (confidence < 0.8): Dashed line
- Arrows indicate directionality
- Edge opacity reflects confidence (0.5 + 0.5 * confidence)

**Confidence Indicators:**

- High confidence (≥ 0.9): Solid border, full opacity
- Medium confidence (0.8-0.9): Solid border, 90% opacity
- Low confidence (< 0.8): Dashed border, 80% opacity, warning icon
- Hover shows provenance details (source, timestamp, confidence)

**Layout Algorithm:**

- **Primary:** Hierarchical layout with REPO at center
- **Fallback:** Force-directed (physics simulation) for complex graphs
- **Levels:**
  - Level 0: REPO (center)
  - Level 1: RELEASE, MAINTAINER, REGISTRY
  - Level 2: CVE, RISK_FACTOR

### Interactive Features

1. **Node Click:** Show detailed metadata in side panel, including provenance
2. **Node Hover:** Tooltip with key information and confidence indicator
3. **Zoom/Pan:** Mouse wheel zoom, drag to pan
4. **Filter:** Toggle node types on/off, filter by confidence threshold
5. **Search:** Find nodes by label
6. **Export:** Download graph as PNG or JSON
7. **Provenance View:** Toggle to show/hide provenance metadata
8. **Confidence Filter:** Slider to filter nodes/edges by minimum confidence

### HTML Structure

```html
<!DOCTYPE html>
<html>
<head>
    <title>Supply Chain Risk Graph</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        #graph-container {
            width: 100%;
            height: 600px;
            border: 1px solid #e5e7eb;
        }
        #details-panel {
            width: 300px;
            padding: 1rem;
            border-left: 1px solid #e5e7eb;
        }
    </style>
</head>
<body>
    <div style="display: flex;">
        <div id="graph-container"></div>
        <div id="details-panel">
            <h3>Node Details</h3>
            <div id="node-info">Click a node to see details</div>
        </div>
    </div>
    <script src="/static/graph-viz.js"></script>
</body>
</html>
```

### JavaScript Implementation

```javascript
// static/graph-viz.js

async function loadGraph(repo) {
    const response = await fetch(`/api/graph?repo=${repo}`);
    const data = await response.json();
    renderGraph(data.graph);
}

function renderGraph(graphData) {
    const nodes = new vis.DataSet(
        graphData.nodes.map(n => ({
            id: n.id,
            label: n.label,
            shape: getNodeShape(n.type),
            color: getNodeColor(n.type),
            title: getNodeTooltip(n)
        }))
    );
    
    const edges = new vis.DataSet(
        graphData.edges.map(e => ({
            from: e.source,
            to: e.target,
            arrows: 'to',
            label: e.relationship_type,
            color: getEdgeColor(e)
        }))
    );
    
    const container = document.getElementById('graph-container');
    const network = new vis.Network(
        container,
        { nodes, edges },
        {
            layout: { hierarchical: { direction: 'UD', sortMethod: 'directed' } },
            physics: { enabled: false },
            interaction: { hover: true, zoomView: true }
        }
    );
    
    network.on('click', (params) => {
        if (params.nodes.length > 0) {
            showNodeDetails(params.nodes[0], graphData);
        }
    });
}
```


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Graph Structure Properties

**Property 1: Graph Validity Invariant**

*For any* generated graph, all edges must reference existing node IDs, all node IDs must be unique, and exactly one REPO node must exist.

**Validates: Requirements US-1.2, US-1.5**

**Rationale:** This is a fundamental invariant that ensures graph structural integrity. A graph with orphaned edges or duplicate IDs is invalid and will cause visualization and analysis failures.

---

**Property 2: Node Schema Completeness**

*For any* node in a graph, it must have the required fields (id, type, label, metadata) and the metadata must contain type-specific required fields based on the node type.

**Validates: Requirements US-1.3, US-3.3, US-4.4, US-5.3, US-7.3**

**Rationale:** This ensures all nodes conform to their schema contracts. Missing required fields will cause serialization errors and visualization failures.

---

**Property 3: Edge Schema Completeness**

*For any* edge in a graph, it must have source, target, and relationship_type fields, and the relationship type must be valid for the source and target node types.

**Validates: Requirements US-1.4, US-3.4, US-4.3, US-5.2, US-7.2**

**Rationale:** This ensures edges are well-formed and semantically valid. Invalid edge types or connections will cause confusion in visualization and analysis.

---

**Property 4: Graph Serialization Round-Trip**

*For any* valid graph, serializing to JSON and then deserializing should produce an equivalent graph structure.

**Validates: Requirements US-2.2**

**Rationale:** This is a round-trip property that ensures our serialization logic is correct. The API must reliably serialize graphs to JSON without data loss.

---

### Node Creation Properties

**Property 5: CVE Node Creation**

*For any* repository with known vulnerabilities in the CVE database, the generated graph must include CVE nodes for those vulnerabilities (unless CVE fetching is disabled).

**Validates: Requirements US-3.1**

**Rationale:** CVE nodes are critical for security analysis. Missing CVE data when it exists represents a failure in data integration.

---

**Property 6: Registry Node Creation**

*For any* repository containing package manifest files (setup.py, package.json, pom.xml, etc.), the generated graph must include a registry node for the detected package ecosystem.

**Validates: Requirements US-4.1, US-4.2**

**Rationale:** Registry detection is key to understanding distribution channels. The detection logic must reliably identify package ecosystems from manifest files.

---

**Property 7: Maintainer Node Creation**

*For any* repository with contributor data, the generated graph must include maintainer nodes for the top contributors (up to the configured limit).

**Validates: Requirements US-5.1**

**Rationale:** Maintainer nodes provide governance context. Missing maintainer data when contributors exist represents incomplete graph construction.

---

**Property 8: Risk Factor Node Creation**

*For any* repository with risk factors having contribution > 0.05, the generated graph must include risk factor nodes for those high-impact factors.

**Validates: Requirements US-7.1, US-7.4**

**Rationale:** Risk factor nodes explain the risk score. Only significant factors (contribution > 0.05) should be included to avoid graph clutter.

---

### API Response Properties

**Property 9: API Response Structure**

*For any* valid API request to /api/graph, the response must include repo, schema_version, generated_at, graph.nodes, graph.edges, and metadata fields.

**Validates: Requirements US-2.2**

**Rationale:** Consistent response structure is essential for API consumers. Missing fields will break client code.

---

**Property 10: Error Response Status Codes**

*For any* API request that results in an error, the response must return an appropriate HTTP status code (400 for bad requests, 404 for not found, 500 for server errors, 503 for service unavailable).

**Validates: Requirements US-2.5**

**Rationale:** Proper status codes enable clients to handle errors appropriately. Incorrect status codes violate HTTP semantics.

---

### Configuration and Limits Properties

**Property 11: Node Count Limits**

*For any* generated graph, the number of nodes of each type must not exceed the configured limits (max_releases, max_maintainers, max_risk_factors).

**Validates: Requirements US-5.4**

**Rationale:** Node limits prevent graph explosion and ensure reasonable visualization performance. Exceeding limits indicates a failure in filtering logic.

---

### Graceful Degradation Properties

**Property 12: Partial Graph Validity**

*For any* graph generation where one or more data sources fail, the resulting graph must still be valid (pass all structural invariants) and include nodes from successful data sources.

**Validates: Requirements US-3.5**

**Rationale:** External API failures should not break the entire graph. Graceful degradation ensures users get partial data rather than complete failure.

---

**Property 13: Provenance Completeness**

*For any* node or edge in a graph, it must include provenance metadata with source, timestamp, and confidence fields.

**Validates: Requirements US-1.3, US-1.4** (extended with provenance)

**Rationale:** Provenance transforms the graph from "cool visualization" into a trustworthy risk artifact. Users must be able to trace where data came from, when it was fetched, and how confident we are in it. This is essential for enterprise adoption and compliance.


## Error Handling

### Error Categories

**1. Input Validation Errors (400 Bad Request)**
- Invalid repository format
- Invalid query parameters (negative max_releases, etc.)
- Malformed repository name

**Handling:**
- Validate inputs before processing
- Return clear error messages
- Log validation failures

**2. Resource Not Found (404 Not Found)**
- Repository does not exist on GitHub
- Repository is private and token lacks access

**Handling:**
- Check GitHub API response
- Return 404 with helpful message
- Suggest checking repository name/permissions

**3. External API Failures (503 Service Unavailable)**
- OSV.dev timeout or unavailable
- GitHub API rate limit exceeded
- Network connectivity issues

**Handling:**
- Implement timeouts (5s for CVE, 10s for GitHub)
- Return partial graph with warning in metadata
- Log external API errors with context
- Include retry-after header if rate limited

**4. Internal Processing Errors (500 Internal Server Error)**
- Graph validation failures
- Serialization errors
- Unexpected exceptions

**Handling:**
- Catch all exceptions at API boundary
- Log full stack trace
- Return generic error message (don't leak internals)
- Include request ID for debugging

### Error Response Format

```json
{
  "error": {
    "code": "INVALID_REPO_FORMAT",
    "message": "Invalid repository format. Use 'owner/repo' or GitHub URL",
    "details": {
      "provided": "invalid-format",
      "expected": "owner/repo"
    }
  }
}
```

### Logging Strategy

**Log Levels:**
- ERROR: External API failures, validation errors, unexpected exceptions
- WARNING: Partial data, missing optional fields, rate limit approaching
- INFO: Graph generation started/completed, cache hits/misses
- DEBUG: Detailed data source responses, node/edge creation

**Log Context:**
- Request ID (for tracing)
- Repository name
- User/token (hashed)
- Timestamp
- Duration

**Example Log Entry:**
```
[2026-02-13 10:30:15] ERROR [request_id=abc123] [repo=numpy/numpy]
CVE fetch failed: Connection timeout after 5s (source=osv.dev)
Returning partial graph without CVE nodes
```


## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests for comprehensive coverage:

- **Unit tests:** Verify specific examples, edge cases, and integration points
- **Property tests:** Verify universal properties across all inputs through randomization

Both approaches are complementary and necessary. Unit tests catch concrete bugs in specific scenarios, while property tests verify general correctness across a wide input space.

### Property-Based Testing

**Library:** [Hypothesis](https://hypothesis.readthedocs.io/) for Python

**Configuration:**
- Minimum 100 iterations per property test (due to randomization)
- Each test must reference its design document property
- Tag format: `# Feature: supply-chain-graph, Property {number}: {property_text}`

**Test Organization:**
```
tests/
├── property/
│   ├── test_graph_structure_properties.py
│   ├── test_node_creation_properties.py
│   ├── test_api_response_properties.py
│   └── test_graceful_degradation_properties.py
└── unit/
    ├── test_graph_builder.py
    ├── test_cve_fetcher.py
    ├── test_registry_detector.py
    └── test_api_endpoint.py
```

**Example Property Test:**

```python
from hypothesis import given, strategies as st
import pytest

# Feature: supply-chain-graph, Property 1: Graph Validity Invariant
@given(graph=st.builds(generate_random_graph))
def test_graph_validity_invariant(graph):
    """
    For any generated graph, all edges must reference existing node IDs,
    all node IDs must be unique, and exactly one REPO node must exist.
    """
    # Check unique node IDs
    node_ids = [n.id for n in graph.nodes]
    assert len(node_ids) == len(set(node_ids)), "Node IDs must be unique"
    
    # Check exactly one REPO node
    repo_nodes = [n for n in graph.nodes if n.type == NodeType.REPO]
    assert len(repo_nodes) == 1, "Graph must have exactly one REPO node"
    
    # Check all edges reference valid nodes
    node_id_set = set(node_ids)
    for edge in graph.edges:
        assert edge.source in node_id_set, f"Edge source {edge.source} not in graph"
        assert edge.target in node_id_set, f"Edge target {edge.target} not in graph"
```

**Hypothesis Strategies:**

```python
# Custom strategies for generating test data

@st.composite
def generate_random_graph(draw):
    """Generate a random but valid graph structure"""
    # Always include one repo node
    repo_node = Node(
        id=f"repo:{draw(st.text(min_size=1))}",
        type=NodeType.REPO,
        label=draw(st.text(min_size=1)),
        metadata={}
    )
    
    nodes = [repo_node]
    
    # Add random number of other nodes
    num_nodes = draw(st.integers(min_value=0, max_value=20))
    for _ in range(num_nodes):
        node_type = draw(st.sampled_from([
            NodeType.RELEASE, NodeType.MAINTAINER,
            NodeType.CVE, NodeType.REGISTRY, NodeType.RISK_FACTOR
        ]))
        nodes.append(Node(
            id=draw(st.text(min_size=1)),
            type=node_type,
            label=draw(st.text(min_size=1)),
            metadata={}
        ))
    
    # Generate edges between nodes
    edges = []
    if len(nodes) > 1:
        num_edges = draw(st.integers(min_value=0, max_value=len(nodes) * 2))
        for _ in range(num_edges):
            source = draw(st.sampled_from(nodes))
            target = draw(st.sampled_from(nodes))
            if source.id != target.id:  # No self-loops
                edges.append(Edge(
                    source=source.id,
                    target=target.id,
                    relationship_type=draw(st.sampled_from(list(EdgeType)))
                ))
    
    return Graph(nodes=nodes, edges=edges)
```

### Unit Testing

**Focus Areas:**
1. **Specific Examples:** Test known repositories (numpy, requests, etc.)
2. **Edge Cases:** Empty graphs, repos with no releases, private repos
3. **Integration Points:** API endpoint, data source integration
4. **Error Conditions:** Timeouts, invalid inputs, API failures

**Example Unit Test:**

```python
def test_graph_builder_with_numpy():
    """Test graph building with numpy repository (known good case)"""
    score_data = load_fixture("numpy_score_data.json")
    builder = GraphBuilder("numpy/numpy", score_data, mock_clients())
    
    graph = builder.build()
    
    # Verify core structure
    assert len(graph.nodes) > 0
    assert any(n.type == NodeType.REPO for n in graph.nodes)
    
    # Verify specific nodes exist
    repo_node = next(n for n in graph.nodes if n.type == NodeType.REPO)
    assert repo_node.label == "numpy/numpy"
    assert "maintenance_risk" in repo_node.metadata

def test_empty_graph_structure():
    """Test that empty graph returns valid structure (edge case)"""
    response = client.get("/api/graph?repo=empty/repo")
    
    assert response.status_code == 200
    data = response.json()
    
    # Empty arrays, not null
    assert data["graph"]["nodes"] == []
    assert data["graph"]["edges"] == []
    assert data["schema_version"] is not None
```

### Integration Testing

**Scenarios:**
1. End-to-end graph generation with real GitHub API
2. CVE fetching with real OSV.dev API (rate-limited)
3. Frontend visualization rendering
4. Cache behavior (hit/miss scenarios)

**Test Environment:**
- Use test repositories with known characteristics
- Mock external APIs for fast tests
- Use real APIs for integration tests (separate test suite)

### Performance Testing

**Benchmarks:**
- Graph generation: < 500ms for cached data
- API response: < 2s total
- Visualization rendering: < 1s for 100 nodes

**Tools:**
- pytest-benchmark for Python performance tests
- Browser DevTools for frontend performance

### Test Coverage Goals

- Line coverage: > 80%
- Branch coverage: > 70%
- Property tests: All 12 properties implemented
- Unit tests: All critical paths and edge cases
- Integration tests: All external API integrations


## Implementation Phases

### Phase 1: Core Graph Infrastructure (MVP)

**Goal:** Basic graph generation with existing data

**Components:**
- Enhance existing `GraphBuilder` with better error handling
- Implement graph validation
- Create `/api/graph` endpoint
- Basic JSON response

**Deliverables:**
- Graph with REPO, RISK_FACTOR nodes
- API endpoint returning valid JSON
- Unit tests for core functionality

**Success Criteria:**
- Can generate graph for any scored repository
- API returns valid graph structure
- All graph invariants hold

---

### Phase 2: Release and Maintainer Enrichment

**Goal:** Add temporal and governance context

**Components:**
- GitHub Releases API integration
- GitHub Contributors API integration
- RELEASE and MAINTAINER node creation
- Caching for release/contributor data

**Deliverables:**
- RELEASE nodes with version history
- MAINTAINER nodes with contribution data
- Enhanced graph builder with new data sources

**Success Criteria:**
- Graphs include release timeline
- Top contributors visible
- Cache reduces API calls

---

### Phase 3: CVE Integration

**Goal:** Add security vulnerability context

**Components:**
- OSV.dev API client
- CVE data fetching and caching
- CVE node creation
- CVE-to-release mapping

**Deliverables:**
- CVE nodes with severity data
- Edges connecting CVEs to affected releases
- Graceful handling of CVE API failures

**Success Criteria:**
- Known vulnerabilities appear in graph
- CVE data cached appropriately
- Partial graphs on API failure

---

### Phase 4: Registry Detection

**Goal:** Add distribution channel context

**Components:**
- Package manifest detection
- Registry type identification
- Package name extraction
- REGISTRY node creation

**Deliverables:**
- REGISTRY nodes for detected packages
- Support for PyPI, npm, Maven, RubyGems
- Edges connecting repos to registries

**Success Criteria:**
- Correctly detects package ecosystems
- Extracts package names accurately
- Handles repos without packages

---

### Phase 5: Visualization

**Goal:** Interactive graph exploration

**Components:**
- vis.js integration
- HTML/CSS/JS for graph rendering
- Interactive features (click, hover, zoom)
- Node details panel

**Deliverables:**
- Interactive graph visualization page
- Color-coded nodes by type
- Clickable nodes with details
- Export functionality

**Success Criteria:**
- Graph renders in < 1s for typical repos
- All node types visually distinct
- Interactive features work smoothly

---

### Phase 6: Polish and Optimization

**Goal:** Production-ready quality

**Components:**
- Performance optimization
- Comprehensive error handling
- Enhanced caching strategy
- Documentation

**Deliverables:**
- Optimized graph generation
- Complete error handling
- API documentation
- User guide

**Success Criteria:**
- Meets all performance targets
- Handles all error scenarios gracefully
- Complete documentation


## Data Models

### Python Classes

**Graph Configuration:**

```python
@dataclass
class GraphConfig:
    """Configuration for graph generation"""
    include_cves: bool = True
    include_releases: bool = True
    include_maintainers: bool = True
    include_registries: bool = True
    max_releases: int = 10
    max_maintainers: int = 5
    max_risk_factors: int = 5
    cve_timeout_seconds: int = 5
    cache_ttl_hours: int = 24
```

**CVE Record:**

```python
@dataclass
class CVERecord:
    """Represents a CVE vulnerability"""
    cve_id: str
    summary: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    cvss_score: Optional[float]
    published: str  # ISO timestamp
    affected_versions: List[str]
    fixed_in: Optional[str]
    source: str  # osv, github_advisory
```

**Registry Info:**

```python
@dataclass
class RegistryInfo:
    """Detected package registry information"""
    registry_type: str  # pypi, npm, maven, rubygems, crates
    package_name: str
    detected_from: str  # filename that indicated registry
    latest_version: Optional[str] = None
    download_count: Optional[int] = None
```

**Contributor Info:**

```python
@dataclass
class ContributorInfo:
    """GitHub contributor information"""
    username: str
    contributions: int
    avatar_url: str
    last_activity: Optional[str]  # ISO timestamp
```

### API Response Schema

**Success Response:**

```python
{
    "repo": str,                    # Repository full name
    "schema_version": str,          # Graph schema version (e.g., "1.0")
    "generated_at": str,            # ISO timestamp
    "graph": {
        "nodes": List[Dict],        # List of node objects
        "edges": List[Dict]         # List of edge objects
    },
    "metadata": {
        "node_count": int,
        "edge_count": int,
        "data_sources": List[str],  # ["github_api", "osv", "score_data"]
        "cache_hit": bool,
        "generation_time_ms": int,
        "warnings": List[Dict]      # Optional warnings about partial data
    }
}
```

**Error Response:**

```python
{
    "error": {
        "code": str,                # Error code (e.g., "INVALID_REPO_FORMAT")
        "message": str,             # Human-readable error message
        "details": Dict             # Additional error context
    }
}
```

### Database Schema (Future)

Currently using in-memory + JSON cache. Future versions may use a graph database:

**Neo4j Schema (Future Consideration):**

```cypher
// Nodes
CREATE (r:Repo {id: string, name: string, risk_score: float})
CREATE (rel:Release {id: string, tag: string, published_at: datetime})
CREATE (m:Maintainer {id: string, username: string, contributions: int})
CREATE (c:CVE {id: string, severity: string, cvss_score: float})
CREATE (reg:Registry {id: string, type: string, package_name: string})
CREATE (rf:RiskFactor {id: string, key: string, value: float})

// Relationships
CREATE (r)-[:HAS_RELEASE]->(rel)
CREATE (m)-[:MAINTAINS]->(r)
CREATE (rel)-[:HAS_CVE]->(c)
CREATE (r)-[:PUBLISHED_AS]->(reg)
CREATE (r)-[:HAS_RISK_FACTOR]->(rf)
```


## Caching Strategy

### Cache Layers

**1. Repository Snapshot Cache (Existing)**
- Location: `data/raw_snapshots/{owner}__{repo}.json`
- TTL: Until `refresh=true`
- Contains: Basic repo metadata from GitHub API

**2. Release Cache (New)**
- Location: `data/releases/{owner}__{repo}.json`
- TTL: 1 hour
- Contains: List of releases with metadata

**3. Contributor Cache (New)**
- Location: `data/contributors/{owner}__{repo}.json`
- TTL: 24 hours
- Contains: Top contributors with stats

**4. CVE Cache (New)**
- Location: `data/cve/{ecosystem}__{package}.json`
- TTL: 24 hours
- Contains: CVE records from OSV.dev

**5. Graph Cache (New)**
- Location: `data/graphs/{owner}__{repo}.json`
- TTL: 1 hour
- Contains: Complete serialized graph

### Cache Invalidation

**Triggers:**
- `refresh=true` parameter: Invalidate all caches for repo
- TTL expiration: Automatic refresh on next request
- Manual: Delete cache files

**Strategy:**
- Lazy invalidation (check TTL on read)
- Write-through (update cache on fetch)
- Partial refresh (only refresh expired components)

### Cache Key Format

```python
def get_cache_key(cache_type: str, identifier: str) -> str:
    """Generate cache key for a given resource"""
    # Examples:
    # get_cache_key("graph", "numpy/numpy") -> "data/graphs/numpy__numpy.json"
    # get_cache_key("cve", "pypi__numpy") -> "data/cve/pypi__numpy.json"
    safe_id = identifier.replace("/", "__")
    return f"data/{cache_type}/{safe_id}.json"
```

### Cache Metadata

Each cache file includes metadata:

```json
{
  "__meta__": {
    "cached_at": "2026-02-13T10:30:00Z",
    "ttl_hours": 24,
    "expires_at": "2026-02-14T10:30:00Z",
    "source": "osv.dev"
  },
  "data": { ... }
}
```

### Performance Impact

**Without Cache:**
- GitHub API: ~500ms per request
- OSV.dev API: ~1000ms per request
- Total: ~2-3s per graph

**With Cache:**
- Disk read: ~10ms per file
- Total: ~50ms per graph

**Cache Hit Rate Target:** > 80% for typical usage


## Security Considerations

### API Security

**1. Input Validation**
- Sanitize repository names (prevent path traversal)
- Validate query parameters (type, range)
- Limit request size and complexity

**2. Rate Limiting**
- Respect GitHub API rate limits
- Implement client-side rate limiting for OSV.dev
- Return 429 Too Many Requests when appropriate

**3. Authentication**
- Use existing GitHub token authentication
- Don't expose tokens in logs or responses
- Support both authenticated and unauthenticated requests

**4. Data Exposure**
- Only expose public repository data
- Don't leak internal system information in errors
- Sanitize error messages

### CVE Data Security

**1. Data Integrity**
- Verify CVE data source (OSV.dev is trusted)
- Validate CVE record structure
- Handle malformed CVE data gracefully

**2. False Positives**
- CVE data may have false positives
- Display CVE source and confidence
- Allow users to verify CVEs independently

### Caching Security

**1. Cache Poisoning**
- Validate data before caching
- Use secure file permissions (600)
- Don't cache sensitive data

**2. Disk Space**
- Implement cache size limits
- Automatic cleanup of old caches
- Monitor disk usage

### Dependency Security

**New Dependencies:**
- `requests` or `httpx`: HTTP client (already used)
- `hypothesis`: Property testing (dev dependency)
- vis.js: Frontend library (CDN-hosted)

**Security Practices:**
- Pin dependency versions
- Regular security audits (Dependabot)
- Use trusted package sources


## Monitoring and Observability

### Metrics to Track

**1. API Performance**
- Graph generation time (p50, p95, p99)
- API response time
- Cache hit rate
- Error rate by type

**2. Data Source Health**
- GitHub API success rate
- OSV.dev API success rate
- Average response time per source
- Rate limit consumption

**3. Graph Characteristics**
- Average node count per graph
- Average edge count per graph
- Node type distribution
- Graph generation failures

### Logging

**Log Aggregation:**
- Structured JSON logs
- Include request ID for tracing
- Log levels: DEBUG, INFO, WARNING, ERROR

**Key Events to Log:**
- Graph generation started/completed
- External API calls (with timing)
- Cache hits/misses
- Validation failures
- Errors and exceptions

**Example Log Entry:**

```json
{
  "timestamp": "2026-02-13T10:30:15Z",
  "level": "INFO",
  "request_id": "abc123",
  "repo": "numpy/numpy",
  "event": "graph_generated",
  "duration_ms": 245,
  "node_count": 15,
  "edge_count": 18,
  "cache_hit": true,
  "data_sources": ["github_api", "osv", "score_data"]
}
```

### Alerting

**Alert Conditions:**
- Error rate > 5% for 5 minutes
- API response time > 5s for 5 minutes
- External API failure rate > 20%
- Cache hit rate < 50%
- Disk space > 90% full

### Health Checks

**Endpoint:** `GET /api/health`

**Enhanced Response:**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "services": {
    "github_api": "ok",
    "osv_api": "degraded",
    "cache": "ok"
  },
  "metrics": {
    "cache_hit_rate": 0.85,
    "avg_response_time_ms": 245
  }
}
```


## Future Enhancements

### Short-term (Next 3-6 months)

**1. Enhanced Registry Integration**
- Query registry APIs for download stats
- Show package popularity metrics
- Display latest version information

**2. Dependency Graph**
- Parse dependency files (requirements.txt, package-lock.json)
- Create dependency nodes
- Show transitive dependencies (limited depth)

**3. Historical Snapshots**
- Store graph snapshots over time
- Show risk evolution
- Compare current vs. historical state

**4. Advanced Visualization**
- Multiple layout algorithms
- Graph filtering by node type
- Subgraph extraction
- Export to various formats (PNG, SVG, GraphML)

### Medium-term (6-12 months)

**1. Graph Database Backend**
- Migrate to Neo4j or similar
- Enable complex graph queries
- Support cross-repository analysis

**2. Risk Propagation Analysis**
- Calculate risk flow through graph
- Identify critical paths
- Highlight high-risk clusters

**3. Deployment Context**
- Link to deployment environments
- Show production usage
- Calculate business impact

**4. External Integrations**
- Snyk vulnerability scanning
- Dependabot alerts
- SBOM (Software Bill of Materials) generation

### Long-term (12+ months)

**1. Multi-Repository Graphs**
- Link related repositories
- Show ecosystem-wide risk
- Identify shared dependencies

**2. Predictive Analytics**
- Predict future risk trends
- Identify emerging vulnerabilities
- Recommend preventive actions

**3. Automated Remediation**
- Suggest dependency updates
- Generate pull requests
- Automate security patches

**4. Enterprise Features**
- Role-based access control
- Custom risk policies
- Compliance reporting
- Audit trails


## Open Questions and Decisions

### Resolved Decisions

**Q1: Which CVE database to use?**
- **Decision:** OSV.dev
- **Rationale:** Free, comprehensive, simple API, actively maintained

**Q2: How many releases to include?**
- **Decision:** Latest 10 (configurable)
- **Rationale:** Balances completeness with performance

**Q3: Should we cache graphs separately from scores?**
- **Decision:** Yes, with 1-hour TTL
- **Rationale:** Graphs are more expensive to generate, separate TTL makes sense

**Q4: Which graph visualization library?**
- **Decision:** vis.js
- **Rationale:** No build step, good features, adequate performance

**Q5: How to handle repos with no releases?**
- **Decision:** Show repo + maintainers + risk factors only
- **Rationale:** Still provides value, graceful degradation

### Open Questions

**Q6: Should we implement graph query language?**
- **Status:** Deferred to future version
- **Consideration:** Would enable powerful filtering but adds complexity

**Q7: How to handle very large repositories (1000+ releases)?**
- **Status:** Use sampling/pagination
- **Consideration:** Need to test with large repos to determine limits

**Q8: Should CVE severity affect visual styling?**
- **Status:** Yes, use color intensity
- **Consideration:** High-severity CVEs should be visually prominent

**Q9: How to handle private repositories?**
- **Status:** Require authentication, same as /api/score
- **Consideration:** Need to respect GitHub permissions

**Q10: Should we support graph export formats?**
- **Status:** Start with JSON, add PNG/SVG later
- **Consideration:** JSON is sufficient for MVP, visual exports are nice-to-have

## References

### External APIs

- [OSV.dev API Documentation](https://osv.dev/docs/)
- [GitHub REST API - Releases](https://docs.github.com/en/rest/releases/releases)
- [GitHub REST API - Contributors](https://docs.github.com/en/rest/repos/repos#list-repository-contributors)

### Libraries

- [vis.js Network Documentation](https://visjs.github.io/vis-network/docs/network/)
- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### Standards

- [CVSS v3.1 Specification](https://www.first.org/cvss/v3.1/specification-document)
- [SBOM Formats](https://www.cisa.gov/sbom)
- [Graph Data Formats](https://en.wikipedia.org/wiki/Graph_Modelling_Language)

