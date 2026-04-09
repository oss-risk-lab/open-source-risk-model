# Design Document: Dependency Tree View

## Overview

The Dependency Tree View feature provides a hierarchical visualization of repository dependencies enriched with risk metadata. The system exposes a REST API endpoint that returns a tree structure with the repository as the root node and its direct and transitive dependencies as child nodes. Each node includes risk scores, vulnerability counts, and other security metadata to help users identify high-risk dependency branches.

**This is an MVP focused on single-repository risk explanation using already-ingested dependency data.** The design intentionally avoids universal live recursive resolution, cross-repository intelligence, and portfolio-wide analysis in favor of a focused, reliable implementation.

### Key Design Goals

1. **Performance**: Handle repositories with thousands of dependencies efficiently (5s for <1000 deps database-backed, 10s for <5000 deps database-backed)
2. **Flexibility**: Support multiple filtering, sorting, and truncation options for different use cases
3. **Reliability**: Provide partial results when some dependencies fail to resolve
4. **Integration**: Leverage existing ingestion pipeline and database schema
5. **Provenance**: Track data sources and completeness for transparency
6. **Graph-Readiness**: Use canonical package identifiers internally to enable future graph-based evolution

### Architecture Context

This feature integrates with the existing system architecture:
- **Database Layer**: Uses existing `repo_dependencies` and `package_mappings` tables
- **Ingestion Pipeline**: Leverages existing dependency ingestion for data population
- **Risk Scoring**: Integrates with existing risk scoring system from `repo_graphs` table
- **API Layer**: Adds new endpoint to existing FastAPI application

### MVP Boundaries

This MVP explicitly does NOT attempt to solve:
- **Full global graph exploration**: Focus is on single-repository trees
- **Cross-repository dependency intelligence**: No portfolio-wide blast radius analysis
- **Universal exact version resolution**: Relies on already-ingested dependency relationships
- **Advanced graph visualization**: Returns simple tree-shaped JSON for frontend rendering
- **Live recursive resolution across all ecosystems**: Limited to ecosystems already supported by ingestion pipeline

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                     │
│  GET /repos/{repo_id}/dependency-tree                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   TreeService (Orchestrator)                 │
│  Phase 1: Canonical Tree Assembly                           │
│    - Retrieve dependency relationships                       │
│    - Build unfiltered canonical tree                         │
│    - Enrich nodes with risk metadata                         │
│  Phase 2: Response Transformation                            │
│    - Apply filters with ancestor preservation                │
│    - Apply sorting                                           │
│    - Apply truncation                                        │
│    - Calculate summary metrics for returned tree             │
│    - Assemble provenance and API response                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  RiskMetadataEnricher                        │
│  - Attach risk scores to nodes                              │
│  - Fetch vulnerability counts from repo_graphs              │
│  - Map package nodes to repository risk data                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer                             │
│  - repo_dependencies (dependency relationships)              │
│  - package_mappings (package-to-repo resolution)            │
│  - repo_graphs (risk scores, CVEs)                          │
└─────────────────────────────────────────────────────────────┘
```

### Build Pipeline Order

**This ordering is intentional and should be preserved unless there is a strong reason to change it.**

The dependency tree construction follows a strict two-phase pipeline:

#### Phase 1: Canonical Tree Assembly
1. **Retrieve canonical dependency relationships** from the best available source (database → cache → live ingestion)
2. **Build the unfiltered canonical tree** with all dependencies and their relationships
3. **Enrich nodes with risk metadata** by mapping package identifiers to repository risk data

#### Phase 2: Response Transformation
4. **Apply filters with ancestor preservation** (high_risk_only, vulnerable_only, direct_only, max_depth)
5. **Apply sorting** to sibling nodes according to sort_by parameter
6. **Apply truncation** to limit children per node if specified
7. **Calculate summary metrics** for the returned (filtered) tree
8. **Assemble provenance and API response** with tree, metrics, and data source information

**Rationale**: This separation ensures that:
- Canonical tree assembly is independent of presentation concerns
- Filtering preserves complete paths from root to matching nodes
- Summary metrics accurately reflect what the user sees (filtered tree)
- The system can evolve to cache canonical trees separately from transformed views

### Tree vs Graph Design Note

The API response is tree-shaped: shared transitive dependencies may appear multiple times in the returned JSON, once per branch that depends on them. This is intentional for MVP simplicity and frontend rendering.

However, internal identifiers and references preserve canonical package identity. Each package+version combination receives a deterministic canonical ID (e.g., `pkg:npm/lodash@4.17.21`) regardless of which branch it appears in. This means:
- The same package appearing in multiple branches uses the same `id` value
- Risk metadata is resolved once per canonical ID and shared across appearances
- The system can evolve into a graph-based supply-chain model later without major refactoring, because canonical identity is already established

### Data Source Precedence

The system retrieves dependency data using the following precedence, applied deterministically:

1. **Database** (primary): Query `repo_dependencies` and `package_mappings` tables for already-ingested dependency relationships. This is the expected path for most requests.
2. **Live ingestion** (fallback): If the repository exists but has no dependency data in the database, and live ingestion is available, attempt to ingest dependencies for ecosystems supported by the current ingestion pipeline. Live ingestion is limited to ecosystems already supported; the system does not attempt universal resolution.
3. **Partial coverage**: If some dependencies cannot be resolved (e.g., unsupported ecosystem, network failure), return what is available with error nodes for unresolved dependencies. Provenance indicates partial coverage.
4. **Repository not found**: If the repository itself cannot be located in the database and live ingestion cannot resolve it, return 404.

**Provenance by path**:
- Database path: `data_source="database"`, `data_completeness` based on risk metadata coverage
- Live ingestion path: `data_source="live"`, `live_fetched_nodes` lists which dependencies were fetched in real-time
- Mixed path: `data_source="mixed"`, provenance indicates which nodes came from which source

### Dependency Resolution Scope (MVP)

The MVP relies primarily on already-ingested dependency relationship data from the database. This means:
- Direct dependencies come from parsed manifest files already stored in `repo_dependencies`
- Transitive dependencies come from previously resolved dependency chains in the database
- Live recursive resolution is limited to ecosystems already supported by the current ingestion pipeline
- When exact resolution is unavailable, the system returns partial coverage with appropriate provenance rather than pretending to know the exact resolved tree
- The system does not attempt to resolve version ranges or lockfile semantics at query time; it uses whatever version information was captured during ingestion

### Performance Strategy

**Performance targets by retrieval mode**:

| Scenario | Target | Applies To |
|---|---|---|
| <1000 dependencies, database-backed | 5 seconds | Repos with pre-ingested data |
| <5000 dependencies, database-backed | 10 seconds | Large repos with pre-ingested data |
| Live ingestion | Best effort, no SLA | Repos requiring real-time ingestion |
| Timeout exceeded | 503 response | All modes |

**Note**: Performance SLAs apply only to database-backed/cached trees. Live ingestion scenarios are best-effort and may exceed these targets. The API returns a 503 with a timeout message if construction exceeds 10 seconds regardless of mode.

**Query Optimization**:
- Use indexed queries on `repo_dependencies` table
- Batch fetch risk metadata for all nodes in a single query
- Limit tree depth to prevent exponential growth
- Apply truncation to reduce response size

## Components and Interfaces

### 1. TreeService (Orchestrator)

**Responsibility**: Orchestrate the two-phase pipeline. This is the single entry point called by the API endpoint.

**Interface**:
```python
class TreeService:
    def get_dependency_tree(
        self,
        repo_full_name: str,
        max_depth: Optional[int] = None,
        high_risk_only: bool = False,
        vulnerable_only: bool = False,
        direct_only: bool = False,
        sort_by: Optional[str] = None,
        truncate_after_children: Optional[int] = None
    ) -> DependencyTreeResponse:
        """
        Build and transform a dependency tree for the given repository.
        
        Executes the two-phase pipeline:
          Phase 1: build_canonical_tree (assembly + enrichment)
          Phase 2: transform_for_response (filter, sort, truncate, metrics, provenance)
        
        Args:
            repo_full_name: Repository identifier (owner/repo)
            max_depth: Maximum tree depth (None = unlimited, range 1-10)
            high_risk_only: Include only high-risk nodes (score > 70) and ancestors
            vulnerable_only: Include only nodes with vulnerabilities and ancestors
            direct_only: Include only direct dependencies
            sort_by: Sort order (risk_score, name, vulnerability_count)
            truncate_after_children: Max children per node
            
        Returns:
            DependencyTreeResponse with tree, summary_metrics, and provenance
        """
```

**Internal phases** (modeled as separate methods, not separate classes):

```python
    def _build_canonical_tree(self, repo_full_name: str) -> CanonicalTree:
        """
        Phase 1: Canonical Tree Assembly.
        
        1. Retrieve dependency relationships from best available source
        2. Build unfiltered tree with all dependencies
        3. Enrich nodes with risk metadata
        
        Returns the complete, unfiltered, enriched tree.
        """

    def _transform_for_response(
        self,
        canonical_tree: CanonicalTree,
        filters: FilterConfig,
        sort_by: Optional[str],
        truncate_after_children: Optional[int]
    ) -> DependencyTreeResponse:
        """
        Phase 2: Response Transformation.
        
        4. Apply filters with ancestor preservation
        5. Apply sorting
        6. Apply truncation
        7. Calculate summary metrics for the returned tree
        8. Assemble provenance and response
        """
```

**Key methods**:
- `_fetch_dependencies(repo: str) -> List[Dependency]`: Query database for dependency relationships
- `_build_node(dep: Dependency, depth: int, visited: Set[str]) -> TreeNode`: Create tree node, detect cycles
- `_detect_cycles(visited: Set[str], canonical_id: str) -> bool`: Prevent infinite recursion
- `_apply_filters(tree: TreeNode, filters: FilterConfig) -> TreeNode`: Apply all filters with ancestor preservation
- `_preserve_ancestor_paths(tree: TreeNode, matching_ids: Set[str]) -> TreeNode`: Keep ancestors for filtered nodes
- `_sort_siblings(node: TreeNode, sort_by: Optional[str]) -> TreeNode`: Sort children recursively
- `_truncate_children(node: TreeNode, limit: int) -> TreeNode`: Limit children per node

### 2. RiskMetadataEnricher

**Responsibility**: Attach risk metadata to tree nodes by mapping package identifiers to repository risk data.

**Interface**:
```python
class RiskMetadataEnricher:
    def enrich_nodes(
        self,
        nodes: List[TreeNode],
        db_path: str
    ) -> List[TreeNode]:
        """
        Enrich nodes with risk metadata.
        
        For each node, attempts to resolve risk data using the following hierarchy:
        1. Look up the package in package_mappings to find the mapped repository
        2. Fetch risk score and CVE data from repo_graphs for that repository
        3. If no mapping exists, mark risk metadata as unavailable
        
        Args:
            nodes: List of tree nodes to enrich
            db_path: Path to database
            
        Returns:
            Nodes with risk_metadata populated (or marked as unavailable)
        """
```

**Key methods**:
- `_fetch_risk_scores(package_ids: List[str]) -> Dict[str, float]`: Batch fetch risk scores via package→repo mapping
- `_fetch_vulnerability_counts(package_ids: List[str]) -> Dict[str, int]`: Batch fetch CVE counts
- `_classify_risk_level(score: float) -> str`: Classify as low/medium/high risk

### 3. SummaryMetricsCalculator

**Responsibility**: Calculate aggregate statistics for the tree. Called after all transformations (filtering, sorting, truncation) are complete.

**Important**: Summary metrics are calculated on the final returned tree, not the unfiltered canonical tree. This means metrics reflect exactly what the user sees. If filters are applied, the metrics describe the filtered subset.

**Interface**:
```python
class SummaryMetricsCalculator:
    def calculate_metrics(
        self,
        tree_root: TreeNode,
        filters_applied: List[str]
    ) -> SummaryMetrics:
        """
        Calculate summary metrics for the given tree.
        
        Metrics are computed on the tree as-is (post-filter, post-sort, post-truncation).
        Preserved ancestor nodes (included to maintain paths under filtering) ARE counted
        in total dependency counts but are NOT counted in high_risk_count or vulnerable_count
        unless they independently satisfy those criteria.
        
        Args:
            tree_root: Root node of the (possibly filtered) tree
            filters_applied: List of filter names that were applied
            
        Returns:
            SummaryMetrics with aggregate statistics
        """
```

**Key methods**:
- `_count_by_type(root: TreeNode) -> Tuple[int, int]`: Count direct and transitive dependencies
- `_count_high_risk(root: TreeNode) -> int`: Count nodes with risk_score > 70
- `_count_vulnerable(root: TreeNode) -> int`: Count nodes with vulnerability_count > 0
- `_find_riskiest_branch(root: TreeNode) -> Tuple[List[str], float]`: Identify highest cumulative risk path
- `_calculate_max_depth(root: TreeNode) -> int`: Find deepest node

### 4. API Endpoint Handler

**Responsibility**: Handle HTTP requests and responses

**Interface**:
```python
@app.get("/repos/{repo_id}/dependency-tree")
async def get_dependency_tree(
    repo_id: str,
    max_depth: Optional[int] = Query(None, ge=1, le=10),
    high_risk_only: bool = Query(False),
    vulnerable_only: bool = Query(False),
    direct_only: bool = Query(False),
    sort_by: Optional[str] = Query(None, regex="^(risk_score|name|vulnerability_count)$"),
    truncate_after_children: Optional[int] = Query(None, ge=1)
) -> DependencyTreeResponse:
    """
    Get dependency tree for a repository.
    
    Returns:
        200: JSON response with tree, summary_metrics, and provenance
        404: Repository not found (cannot be located in database or via live ingestion)
        503: Timeout or all dependencies failed to resolve
        500: Internal server error
    """
```

### Behavior for Special Cases

#### Repositories with Zero Dependencies
A repository that exists in the database but has no declared dependencies is NOT an error. The API returns:
- **Status**: 200
- **Tree**: Repository root node with empty children array
- **Summary metrics**: All counts at zero, max_depth at 0
- **Provenance**: `data_source="database"`, `data_completeness="full"`

Reserve 404 exclusively for cases where the repository itself cannot be located.

#### Repositories Not in the Database
When a repository is not found in stored dependency data:
1. If live ingestion is available and the repository can be resolved, attempt live ingestion for supported ecosystems
2. Return the tree with `data_source="live"` in provenance
3. If live ingestion is not available or fails to locate the repository, return 404 with a message indicating the repository was not found
4. If live ingestion partially succeeds (some ecosystems resolved, others not), return 200 with partial coverage and appropriate provenance

## Data Models

### Canonical Field Names

The following field names are authoritative and must be used consistently throughout the codebase:

| Field | Used On | Description |
|---|---|---|
| `id` | TreeNode | Canonical package identifier (e.g., `pkg:npm/lodash@4.17.21`) |
| `node_type` | TreeNode | `"repository"` or `"package"` |
| `name` | TreeNode | Package or repository name |
| `version` | TreeNode | Package version (null for repository nodes) |
| `depth` | TreeNode | Distance from root (0 = repository) |
| `dependency_type` | TreeNode | `"direct"` or `"transitive"` |
| `ecosystem` | TreeNode | Package ecosystem: `"pypi"`, `"npm"`, `"maven"`, `"go"`, etc. |
| `resolution_status` | TreeNode | `"resolved"` or `"error"` |
| `error_reason` | TreeNode | Error message (only when resolution_status="error") |
| `risk_score` | RiskMetadata | 0-100 risk score (repo-level, mapped from package) |
| `risk_level` | RiskMetadata | `"low"`, `"medium"`, `"high"` |
| `vulnerability_count` | RiskMetadata | Number of known CVEs |
| `data_source` | ProvenanceInfo | `"database"`, `"live"`, `"mixed"` |
| `data_completeness` | ProvenanceInfo | `"full"`, `"partial"` |

### TreeNode

Represents a single node in the dependency tree. Resolution failures are represented as normal package nodes with `resolution_status="error"`, not as a separate node type.

```python
@dataclass
class TreeNode:
    """A node in the dependency tree."""
    
    # Identity (canonical - preserves package identity across branches)
    id: str  # Canonical identifier (e.g., "pkg:npm/lodash@4.17.21")
    node_type: str  # "repository" or "package"
    name: str  # Package or repository name
    version: Optional[str] = None  # Package version (null for repository)
    
    # Tree structure
    depth: int = 0  # Distance from root (0 = repository)
    children: List['TreeNode'] = field(default_factory=list)
    children_truncated: bool = False  # True if children were limited
    child_count: Optional[int] = None  # Total children before truncation
    
    # Dependency metadata
    dependency_type: str = "direct"  # "direct" or "transitive"
    ecosystem: Optional[str] = None  # "pypi", "npm", "maven", "go", etc.
    specifier: Optional[str] = None  # Version specifier from manifest
    
    # Risk metadata (attached during enrichment phase)
    risk_metadata: Optional['RiskMetadata'] = None
    
    # Resolution status (error nodes use node_type="package", not a separate type)
    resolution_status: str = "resolved"  # "resolved" or "error"
    error_reason: Optional[str] = None  # Error message if resolution failed
```

### RiskMetadata

Risk information attached to each node during the enrichment phase.

```python
@dataclass
class RiskMetadata:
    """Risk metadata for a dependency node."""
    
    # Authoritative fields (always populated when risk data is available)
    risk_score: Optional[float] = None  # 0-100 risk score
    risk_level: Optional[str] = None  # "low" (<= 30), "medium" (31-70), "high" (> 70)
    vulnerability_count: int = 0  # Number of known CVEs
    
    # Optional fields (populated when data is available, None otherwise)
    release_recency_days: Optional[int] = None  # Days since last release
    maintainer_count: Optional[int] = None  # Number of active maintainers
    
    # Provenance for this node's risk data
    score_source: str = "unavailable"  # "repo_graph", "inferred", "unavailable"
    score_completeness: str = "missing"  # "full", "partial", "missing"
```

### Risk Score Sourcing

This is the explicit hierarchy for how a dependency node gets its risk metadata:

1. **Package → Repository mapping**: Look up the package in `package_mappings` to find the mapped repository (e.g., `npm/lodash` → `lodash/lodash`)
2. **Repository risk data**: Fetch risk score, CVE count, and other metadata from `repo_graphs` for the mapped repository
3. **Score level**: Risk scores are repo-level, not package-level or version-level. A package inherits the risk score of its mapped repository.
4. **Partial data**: If the repository exists in `repo_graphs` but some fields are missing (e.g., no CVE data), populate what is available and set `score_completeness="partial"`
5. **No mapping**: If no package→repo mapping exists, set `score_source="unavailable"`, `score_completeness="missing"`, and leave `risk_score=None`
6. **Inferred scores**: Not used in MVP. Future versions may infer scores from ecosystem-level statistics.

**Field authority**:
- `risk_score`: Authoritative when `score_source="repo_graph"`. Null when unavailable.
- `vulnerability_count`: Authoritative when sourced from repo_graphs CVE data. Defaults to 0.
- `risk_level`: Derived from risk_score. Null when risk_score is null.
- `release_recency_days`, `maintainer_count`: Optional. Populated when available, null otherwise.

### SummaryMetrics

Aggregate statistics for the returned (filtered) tree.

```python
@dataclass
class SummaryMetrics:
    """Summary metrics for the returned dependency tree."""
    
    total_dependencies: int  # Total nodes excluding root
    direct_dependencies: int  # Depth 1 nodes
    transitive_dependencies: int  # Depth 2+ nodes
    high_risk_count: int  # Nodes with risk_score > 70
    vulnerable_count: int  # Nodes with vulnerability_count > 0
    max_depth: int  # Maximum depth in returned tree
    riskiest_branch: Optional[Dict[str, Any]] = None  # Highest-risk path
    
    # Filter context
    filters_applied: List[str] = field(default_factory=list)
```

**Summary metrics scope**: Metrics are calculated on the final returned tree (after filtering, sorting, and truncation). They reflect exactly what the user sees. Preserved ancestor nodes (included to maintain paths under filtering) ARE counted in `total_dependencies`, `direct_dependencies`, and `transitive_dependencies`, but are NOT counted in `high_risk_count` or `vulnerable_count` unless they independently satisfy those criteria.

**Future consideration**: A `raw_total_dependencies` field may be added later to show the unfiltered count for context, but this is not part of MVP.

### ProvenanceInfo

Data source and completeness tracking at the response level.

```python
@dataclass
class ProvenanceInfo:
    """Provenance information for the tree response."""
    
    # Response-level provenance
    data_source: str  # "database", "live", "mixed"
    data_completeness: str  # "full", "partial"
    last_updated: str  # ISO timestamp of most recent data
    
    # Coverage details
    total_nodes: int = 0  # Total nodes in returned tree
    nodes_with_risk_data: int = 0  # Nodes with risk_score populated
    nodes_with_missing_risk: int = 0  # Nodes without risk data
    nodes_with_errors: int = 0  # Nodes with resolution_status="error"
    error_details: List[Dict[str, str]] = field(default_factory=list)
    
    # Live ingestion details (populated only when data_source is "live" or "mixed")
    live_fetched_nodes: List[str] = field(default_factory=list)
    
    # Performance
    construction_time_ms: Optional[int] = None
```

**Provenance semantics by scenario**:

| Scenario | data_source | data_completeness | Notes |
|---|---|---|---|
| All data from database, all risk data present | `"database"` | `"full"` | Ideal case |
| All data from database, some risk data missing | `"database"` | `"partial"` | `nodes_with_missing_risk > 0` |
| Some nodes live-fetched | `"mixed"` | `"partial"` | `live_fetched_nodes` populated |
| All nodes live-fetched | `"live"` | varies | Depends on risk data availability |
| Some nodes unresolved | varies | `"partial"` | `nodes_with_errors > 0`, `error_details` populated |
| Zero dependencies | `"database"` | `"full"` | Valid response, all counts zero |

### API Response Schema

```json
{
  "repo": "owner/repo",
  "tree": {
    "id": "owner/repo",
    "node_type": "repository",
    "name": "owner/repo",
    "depth": 0,
    "dependency_type": "direct",
    "children": [
      {
        "id": "pkg:npm/lodash@4.17.21",
        "node_type": "package",
        "name": "lodash",
        "version": "4.17.21",
        "depth": 1,
        "dependency_type": "direct",
        "ecosystem": "npm",
        "resolution_status": "resolved",
        "risk_metadata": {
          "risk_score": 45.2,
          "risk_level": "medium",
          "vulnerability_count": 2,
          "release_recency_days": 180,
          "maintainer_count": 5,
          "score_source": "repo_graph",
          "score_completeness": "full"
        },
        "children": []
      }
    ]
  },
  "summary_metrics": {
    "total_dependencies": 150,
    "direct_dependencies": 25,
    "transitive_dependencies": 125,
    "high_risk_count": 8,
    "vulnerable_count": 12,
    "max_depth": 4,
    "riskiest_branch": {
      "path": ["owner/repo", "pkg:npm/express@4.18.0", "pkg:npm/body-parser@1.20.0"],
      "cumulative_risk": 185.5
    },
    "filters_applied": []
  },
  "provenance": {
    "data_source": "database",
    "data_completeness": "full",
    "last_updated": "2024-01-15T10:30:00Z",
    "total_nodes": 151,
    "nodes_with_risk_data": 145,
    "nodes_with_missing_risk": 6,
    "nodes_with_errors": 0,
    "error_details": [],
    "live_fetched_nodes": [],
    "construction_time_ms": 245
  }
}
```

## Filtering, Sorting, and Truncation Semantics

### Ancestor Preservation Under Filtering

When filters are applied (high_risk_only, vulnerable_only, direct_only, max_depth), the system preserves complete paths from the root to matching nodes:

1. **Matching nodes**: Nodes that satisfy the filter criteria are included
2. **Ancestor preservation**: Ancestors needed to form a complete path from the repository root to each matching node are also included
3. **Preserved ancestors do not need to independently satisfy the filter criteria**: For example, under `high_risk_only=true`, a low-risk node may be included if it is an ancestor of a high-risk node
4. **Summary metrics treatment**: Preserved ancestors ARE counted in `total_dependencies`, `direct_dependencies`, and `transitive_dependencies`, but are NOT counted in `high_risk_count` or `vulnerable_count` unless they independently satisfy those criteria

**Example**: If package A (low risk) depends on package B (high risk), and `high_risk_only=true` is applied:
- Package B is included (matches filter)
- Package A is included (ancestor of B)
- Repository root is included (ancestor of A)
- `high_risk_count = 1` (only B)
- `total_dependencies = 2` (A and B)

### Sort and Truncation Precedence

The system applies sorting and truncation in a deterministic order:

1. **If sort_by is provided**: Sort all sibling groups by the specified criterion (risk_score descending, name ascending, or vulnerability_count descending), then apply truncation to the sorted list
2. **If sort_by is not provided**: Use the default deterministic sort order (name ascending, then version ascending), then apply truncation to the sorted list

**There is no separate "risk-first truncation" mode.** If you want to truncate by risk, explicitly set `sort_by=risk_score`.

**Truncation behavior**:
- When a node has more children than `truncate_after_children`, keep only the first N children from the sorted list
- Set `children_truncated=true` and `child_count` to the total number of children before truncation
- Apply truncation recursively at every level of the tree

**Example**:
- `sort_by=risk_score`, `truncate_after_children=10`: Sort siblings by risk score descending, keep top 10
- `sort_by` not provided, `truncate_after_children=10`: Sort siblings by name, keep first 10 alphabetically
- `sort_by=name`, `truncate_after_children=10`: Sort siblings by name, keep first 10 alphabetically (same as default)


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, I identified several opportunities to consolidate redundant properties:

**Consolidations Made**:
1. Properties 1.2 and 1.3 (depth assignment for direct and transitive deps) can be combined into a single property about correct depth assignment based on dependency chain length
2. Properties 1.4 and 1.5 (unique IDs and depth recording) are both structural invariants that can be verified together
3. Properties 2.2, 2.4, and 2.5 (risk metadata fields) can be combined into one property about complete risk metadata structure
4. Properties 3.1, 3.2, 3.3, 3.4, 3.5 (various counts) and 15.1-15.4 (metric accuracy) are all testing the same thing: that summary metrics accurately reflect the tree. These can be consolidated into comprehensive metric accuracy properties
5. Properties 4.2, 4.4, 4.5 (response structure) can be combined into one property about complete API response structure
6. Properties 5.2 and 5.3 (max_depth filtering) can be combined into one property about depth-based filtering
7. Properties 6.2 and 6.3 (high_risk filtering with ancestors) can be combined
8. Properties 7.2, 7.3, 7.4 (truncation behavior) can be combined into one comprehensive truncation property
9. Properties 8.2, 8.4, 8.5 (deterministic ordering) can be combined into one property about determinism
10. Properties 9.2, 9.3, 9.4 (provenance content) can be combined into one property about accurate provenance tracking

### Property 1: Tree Structure Correctness

*For any* repository with dependencies, the constructed tree SHALL have the repository as root at depth 0, direct dependencies at depth 1, and transitive dependencies at depth equal to their shortest path length from the root.

**Validates: Requirements 1.1, 1.2, 1.3, 1.7**

### Property 2: Node Identity and Structure Invariants

*For any* dependency tree, all nodes SHALL have unique identifiers and recorded depth values, with the same package+version receiving consistent IDs across multiple builds.

**Validates: Requirements 1.4, 1.5, 8.4**

### Property 3: Cycle Detection Termination

*For any* dependency graph containing cycles, the tree builder SHALL terminate without infinite recursion by tracking visited nodes.

**Validates: Requirements 1.6**

### Property 4: Risk Metadata Completeness

*For any* node with available risk data (score_source="repo_graph"), the risk metadata SHALL include risk_score, vulnerability_count, and risk_level. Optional fields (release_recency_days, maintainer_count) are populated when available. The node itself SHALL include dependency_type, ecosystem, and version.

**Validates: Requirements 2.1, 2.2, 2.4, 2.5**

### Property 5: Risk Classification Accuracy

*For any* node with a risk_score above 70, the node SHALL be classified as high-risk; nodes with risk_score ≤ 70 SHALL NOT be classified as high-risk.

**Validates: Requirements 2.3**

### Property 6: Missing Data Provenance

*For any* node without available risk data, the provenance field SHALL indicate missing or partial data completeness.

**Validates: Requirements 2.6**

### Property 7: Summary Metrics Accuracy

*For any* dependency tree, the summary metrics SHALL satisfy:
- total_dependencies = direct_dependencies + transitive_dependencies = (total nodes - 1)
- high_risk_count = count of nodes with risk_score > 70
- vulnerable_count = count of nodes with vulnerability_count > 0
- max_depth = depth of deepest node

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 15.1, 15.2, 15.3, 15.4**

### Property 8: Riskiest Branch Identification

*For any* dependency tree, the riskiest branch cumulative score SHALL be greater than or equal to the risk_score of any individual node in the tree.

**Validates: Requirements 3.6, 15.5**

### Property 9: API Response Structure Completeness

*For any* valid repository request, the API response SHALL include a tree structure, summary_metrics object, and provenance object with all required fields.

**Validates: Requirements 4.2, 4.4, 4.5, 9.1**

### Property 10: Depth Filtering Correctness

*For any* tree with max_depth parameter, all returned nodes SHALL have depth ≤ max_depth, and all nodes with depth ≤ max_depth SHALL be included unless filtered by other criteria.

**Validates: Requirements 5.2, 5.3**

### Property 11: Truncation Metadata Accuracy

*For any* node at max_depth with children, the node SHALL have children_truncated=true and child_count equal to the total number of children before truncation.

**Validates: Requirements 5.4**

### Property 12: Unfiltered Tree Completeness

*For any* tree built without max_depth parameter, all dependencies SHALL be included regardless of depth.

**Validates: Requirements 5.5**

### Property 13: Risk-Based Filtering with Ancestor Preservation

*For any* tree with high_risk_only=true, all returned nodes SHALL either have risk_score > 70 OR be ancestors of nodes with risk_score > 70, forming a complete path from root to each high-risk node.

**Validates: Requirements 6.2, 6.3**

### Property 14: Vulnerability Filtering with Ancestor Preservation

*For any* tree with vulnerable_only=true, all returned nodes SHALL either have vulnerability_count > 0 OR be ancestors of vulnerable nodes, forming complete paths from root to each vulnerable node.

**Validates: Requirements 6.5**

### Property 15: Direct-Only Filtering

*For any* tree with direct_only=true, all returned nodes SHALL have depth ≤ 1 (repository root and direct dependencies only).

**Validates: Requirements 6.7**

### Property 16: Filter Combination Logic

*For any* tree with multiple filter parameters, a node SHALL be included only if it satisfies ALL filter criteria OR is an ancestor of a node that satisfies all criteria.

**Validates: Requirements 6.8**

### Property 17: Truncation with Sorting

*For any* node with more children than truncate_after_children limit, the included children SHALL be the first N from the current sort order (explicit sort_by or default name+version), and children_truncated SHALL be true with child_count reflecting the pre-truncation total.

**Validates: Requirements 7.2, 7.3, 7.4, 13.7, 13.8**

### Property 18: Deterministic Tree Construction

*For any* repository, building the tree twice with identical parameters SHALL produce identical tree structures with the same node ordering.

**Validates: Requirements 8.1, 8.2, 8.5**

### Property 19: Shared Dependency Duplication

*For any* transitive dependency appearing in multiple branches, the dependency SHALL appear as a separate node in each branch.

**Validates: Requirements 8.3**

### Property 20: Sorting Consistency

*For any* tree with sort_by parameter, all sibling groups at every depth SHALL be sorted according to the specified criterion (risk_score, name, or vulnerability_count).

**Validates: Requirements 13.2, 13.3, 13.4, 13.6**

### Property 21: Default Sort Order

*For any* tree without sort_by parameter, sibling nodes SHALL be sorted by name, then version, in deterministic order.

**Validates: Requirements 13.5**

### Property 22: Partial Results on Errors

*For any* tree where some dependencies fail to resolve, successfully resolved dependencies SHALL be included in the tree, and error nodes SHALL have resolution_status="error" with node_type="package".

**Validates: Requirements 14.1, 14.2, 14.3**

### Property 23: Error Resilience

*For any* tree construction encountering errors, the builder SHALL continue processing remaining dependencies rather than halting.

**Validates: Requirements 14.7**

### Property 24: Error Tracking in Provenance

*For any* tree with resolution errors, the provenance object SHALL list all dependencies that encountered errors in the error_details field.

**Validates: Requirements 14.5**

### Property 25: Provenance Accuracy

*For any* tree, the provenance object SHALL accurately indicate data_source (database/cache/live), data_completeness (full/partial), and include a last_updated timestamp.

**Validates: Requirements 9.2, 9.3, 9.4, 9.5, 9.6**

### Property 26: Filtered Metrics Accuracy

*For any* tree with filters applied, the summary_metrics SHALL reflect only the filtered subset of nodes, not the complete unfiltered tree.

**Validates: Requirements 15.6**

## Error Handling

### Error Categories and HTTP Status Codes

**1. Invalid Input Errors (400 Bad Request)**
- Invalid repository format (e.g., missing owner or repo name)
- Invalid query parameter values (e.g., `max_depth=15` when max is 10)
- Invalid `sort_by` value (not one of: risk_score, name, vulnerability_count)

**2. Repository Not Found (404 Not Found)**
- Repository cannot be located in the database AND live ingestion cannot resolve it
- This is the ONLY case for 404. Repositories with zero dependencies return 200.

**3. Partial Resolution (200 OK with error nodes)**
- Some dependencies failed to resolve (network error, unsupported ecosystem, etc.)
- Some risk metadata is missing
- Response includes error nodes with `resolution_status="error"` and `error_reason`
- Provenance indicates `data_completeness="partial"` and lists errors in `error_details`

**4. Complete Failure (503 Service Unavailable)**
- All dependencies failed to resolve (cannot build even a partial tree)
- Database connection failure
- Timeout exceeded during tree construction (>10 seconds)

**5. Internal Errors (500 Internal Server Error)**
- Unexpected exceptions during tree building
- Data corruption or schema violations

### Error Node Representation

Dependency resolution failures are represented as normal package nodes with error metadata, NOT as a separate node type.

**Error node schema**:
```json
{
  "id": "pkg:npm/unknown-package@unknown",
  "node_type": "package",
  "name": "unknown-package",
  "version": null,
  "depth": 1,
  "dependency_type": "direct",
  "ecosystem": "npm",
  "resolution_status": "error",
  "error_reason": "Package not found in registry",
  "risk_metadata": null,
  "children": []
}
```

**Key points**:
- `node_type` is still `"package"`, not `"error"`
- `resolution_status="error"` indicates the failure
- `error_reason` provides a human-readable message
- `risk_metadata` is null (cannot enrich unresolved nodes)
- `children` is empty (cannot traverse unresolved dependencies)

### Graceful Degradation Strategy

The system continues processing after individual dependency failures:

1. **Attempt to resolve each dependency**: Query database, attempt live ingestion if needed
2. **On failure**: Create an error node with `resolution_status="error"`
3. **Continue with siblings**: Process remaining dependencies at the same level
4. **Track errors**: Add error details to `provenance.error_details`
5. **Return partial results**: If at least the repository root is available, return 200 with partial tree
6. **Complete failure only if**: Cannot build even the root node, or all dependencies fail

**Timeout handling**:
- Set 10-second timeout for entire tree construction (all phases)
- If timeout is exceeded, return 503 with message: "Tree construction exceeded timeout"
- Log timeout events for monitoring and performance tuning

## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests for comprehensive coverage:

**Unit Tests** focus on:
- Specific examples demonstrating correct behavior
- Edge cases (empty trees, single-node trees, maximum depth, zero dependencies)
- Error conditions (invalid input, missing data, timeouts, 404 vs 200 with zero deps)
- API endpoint integration (request/response handling, status codes)
- Database query correctness
- Phase separation (canonical tree assembly vs response transformation)

**Property-Based Tests** focus on:
- Universal properties that hold for all inputs
- Comprehensive input coverage through randomization
- Invariants that must always be true (e.g., metrics accuracy, ancestor preservation)
- Relationship properties between components

### Property-Based Testing Configuration

**Framework**: Use `hypothesis` for Python property-based testing

**Test Configuration**:
- Minimum 100 iterations per property test
- Each test references its design document property
- Tag format: `# Feature: dependency-tree-view, Property N: [property text]`

**Example Property Test Structure**:
```python
from hypothesis import given, strategies as st
import pytest

# Feature: dependency-tree-view, Property 1: Tree Structure Correctness
@given(
    repo=st.text(min_size=1),
    dependencies=st.lists(st.text(min_size=1), min_size=0, max_size=50)
)
@pytest.mark.property_test
def test_tree_structure_correctness(repo, dependencies):
    """
    For any repository with dependencies, the constructed tree SHALL have
    the repository as root at depth 0, direct dependencies at depth 1.
    """
    tree_service = TreeService()
    response = tree_service.get_dependency_tree(repo)
    
    # Root is at depth 0
    assert response.tree.depth == 0
    assert response.tree.name == repo
    
    # Direct dependencies are at depth 1
    for child in response.tree.children:
        assert child.depth == 1
        assert child.dependency_type == "direct"
```

### Unit Test Coverage

**Phase 1: Canonical Tree Assembly Tests**:
- Dependency retrieval from database (database → live fallback)
- Tree construction with various dependency structures (linear, branching, cycles)
- Cycle detection prevents infinite recursion
- Risk metadata enrichment (package→repo mapping, score sourcing)
- Canonical ID assignment and consistency

**Phase 2: Response Transformation Tests**:
- Filtering (depth, high_risk_only, vulnerable_only, direct_only)
- Ancestor preservation under filtering
- Sorting (risk_score, name, vulnerability_count, default)
- Truncation with various limits
- Summary metrics calculation on filtered tree
- Provenance assembly

**API Integration Tests**:
- Endpoint availability and routing
- Query parameter parsing and validation
- Response format and schema validation
- Error response codes (400, 404, 503, 500)
- Zero-dependency repositories return 200
- Repositories not in database attempt live ingestion before 404
- Performance under load

**Edge Case Tests**:
- Empty dependency tree (repository with no dependencies) → 200 with zero counts
- Repository not in database, live ingestion unavailable → 404
- Repository not in database, live ingestion succeeds → 200 with data_source="live"
- Single-level tree (only direct dependencies)
- Deep tree (maximum depth)
- Wide tree (many siblings)
- Circular dependencies
- Missing risk data for all nodes
- All dependencies fail to resolve → 503
- Some dependencies fail to resolve → 200 with error nodes

**Error Handling Tests**:
- Invalid repository ID format → 400
- Invalid query parameters → 400
- Database connection failures → 503
- Timeout scenarios → 503
- Partial resolution failures → 200 with error nodes and partial provenance

### Test Data Strategy

**Synthetic Test Data**:
- Generate test repositories with known dependency structures
- Create test data with controlled risk scores and vulnerability counts
- Use deterministic random seeds for reproducibility
- Test canonical ID consistency across multiple appearances of same package

**Real-World Test Data**:
- Test against actual repositories in the database
- Validate performance with large dependency trees
- Verify behavior with real risk metadata
- Test zero-dependency repositories (e.g., leaf packages)

### Performance Testing

**Load Testing**:
- Test with repositories of varying sizes (10, 100, 1000, 5000 dependencies)
- Measure response times for database-backed vs live-ingested trees
- Identify bottlenecks in Phase 1 vs Phase 2
- Verify timeout handling under load

**Stress Testing**:
- Test with maximum depth and no truncation
- Test with complex filtering combinations
- Verify memory usage stays within bounds
- Test concurrent requests

**Benchmark Targets**:
- <1000 dependencies (database-backed): 5 seconds
- <5000 dependencies (database-backed): 10 seconds
- Live ingestion: Best effort, no SLA
- API overhead: <100ms for cached results

### Integration Testing

**Database Integration**:
- Verify correct queries against repo_dependencies table
- Test package_mappings lookup for risk metadata
- Test repo_graphs queries for risk scores and CVE counts
- Validate index usage for performance

**Risk Scoring Integration**:
- Verify package→repo mapping logic
- Test CVE count aggregation
- Validate score_source and score_completeness fields
- Test behavior when mappings are missing

**API Integration**:
- Test endpoint with various query parameter combinations
- Verify response schema compliance with all field names
- Test error handling across the stack (400, 404, 503, 500)
- Verify provenance accuracy for different data sources

