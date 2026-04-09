# Implementation Plan: Dependency Tree View

## Overview

This plan implements the dependency tree visualization API as defined in the refined design document. The implementation follows the two-phase pipeline architecture (Phase 1: Canonical Tree Assembly, Phase 2: Response Transformation) and builds on the existing database schema (`repo_dependencies`, `package_mappings`, `repo_graphs`).

## Non-Goals During Implementation

The implementation must not expand scope into:
- UI work or frontend rendering logic
- Graph visualization or interactive tree rendering
- Cross-repository analytics or portfolio-wide blast-radius analysis
- Universal resolver expansion beyond ecosystems already supported by the ingestion pipeline
- Version-range resolution or lockfile semantics at query time

## Canonical Field Names

The following names are authoritative. Use them everywhere — models, serialization, tests, API responses. Do not introduce synonyms.

| Field | Used On | Notes |
|---|---|---|
| `id` | TreeNode | Canonical package ID: `pkg:{ecosystem}/{name}@{version}` |
| `node_type` | TreeNode | `"repository"` or `"package"` |
| `name` | TreeNode | Package or repository name |
| `version` | TreeNode | Package version, `None` for repository nodes |
| `depth` | TreeNode | Distance from root (0 = repository) |
| `dependency_type` | TreeNode | `"direct"` or `"transitive"` — not `dependency_kind` |
| `ecosystem` | TreeNode | `"pypi"`, `"npm"`, `"maven"`, `"go"` — not `registry_type` |
| `resolution_status` | TreeNode | `"resolved"` or `"error"` |
| `error_reason` | TreeNode | Only when `resolution_status="error"` |
| `risk_score` | RiskMetadata | 0–100, repo-level, mapped from package |
| `risk_level` | RiskMetadata | `"low"` (≤30), `"medium"` (31–70), `"high"` (>70) |
| `vulnerability_count` | RiskMetadata | Number of known CVEs |
| `score_source` | RiskMetadata | `"repo_graph"`, `"unavailable"` |
| `score_completeness` | RiskMetadata | `"full"`, `"partial"`, `"missing"` |
| `data_source` | ProvenanceInfo | `"database"`, `"live"`, `"mixed"` |
| `data_completeness` | ProvenanceInfo | `"full"`, `"partial"` |

## Unresolved Version Handling

When version information is missing or ambiguous during canonical ID construction:

| Scenario | Canonical ID Format | Notes |
|---|---|---|
| Version known | `pkg:npm/lodash@4.17.21` | Normal case |
| Version missing entirely | `pkg:npm/lodash@unknown` | Use literal `unknown` |
| Only specifier exists (e.g., `^4.0.0`) | `pkg:npm/lodash@unknown` | Do not embed specifier in ID; store specifier in `specifier` field |
| Version resolution failed | `pkg:npm/lodash@unknown` | Set `resolution_status="error"` |

The `specifier` field on TreeNode preserves the original version constraint from the manifest for informational purposes.

## Exception Classes

Define in `src/open_source_risk_model/tree/exceptions.py`:

```python
class RepositoryNotFoundError(Exception):
    """Repository cannot be located in database or via live ingestion. → 404"""

class TreeConstructionTimeoutError(Exception):
    """Tree construction exceeded the 10-second timeout. → 503"""

class AllDependenciesFailedError(Exception):
    """Every dependency failed to resolve; cannot build even a partial tree. → 503"""

class DependencyResolutionError(Exception):
    """A single dependency failed to resolve. Internal only — converted to error node, never propagated to API."""
```

**Propagation rules**:
- `RepositoryNotFoundError` → API returns 404
- `TreeConstructionTimeoutError` → API returns 503
- `AllDependenciesFailedError` → API returns 503
- `DependencyResolutionError` → caught inside Phase 1, converted to an error node with `resolution_status="error"`. Never reaches the API layer.
- Any other unexpected exception → API returns 500

## TreeService Public Method Contract

```python
class TreeService:
    def get_dependency_tree(
        self,
        repo_full_name: str,
        max_depth: Optional[int] = None,       # 1–10 or None
        high_risk_only: bool = False,
        vulnerable_only: bool = False,
        direct_only: bool = False,
        sort_by: Optional[str] = None,          # "risk_score" | "name" | "vulnerability_count"
        truncate_after_children: Optional[int] = None,  # ≥1 or None
        timeout_seconds: float = 10.0
    ) -> DependencyTreeResponse:
        ...
```

**Inputs**: Repository identifier and optional transformation parameters.

**Return type**: `DependencyTreeResponse` containing `repo` (str), `tree` (TreeNode), `summary_metrics` (SummaryMetrics), `provenance` (ProvenanceInfo).

**Raised exceptions**:
- `RepositoryNotFoundError` — repo not in database and live ingestion cannot locate it
- `TreeConstructionTimeoutError` — wall-clock time exceeded `timeout_seconds`
- `AllDependenciesFailedError` — every dependency resolution failed

**Timeout ownership**: The timeout is enforced inside `get_dependency_tree()` using a wall-clock check. The API layer catches the resulting `TreeConstructionTimeoutError` and returns 503. The API layer itself does not enforce a separate timeout.

**Metrics scope**: Always returns filtered metrics only. Summary metrics describe the returned (post-filter, post-sort, post-truncation) tree.

**Immutability guarantee**: Phase 2 transformations operate on a deep clone of the canonical tree. The canonical tree built in Phase 1 is never mutated by Phase 2.

## Summary Metrics Rules

These rules apply everywhere metrics are calculated. Define once, enforce everywhere.

1. **total_dependencies** = count of all nodes in the returned tree except the root
2. **direct_dependencies** = count of nodes at depth 1 in the returned tree
3. **transitive_dependencies** = count of nodes at depth ≥ 2 in the returned tree
4. **Invariant**: total_dependencies = direct_dependencies + transitive_dependencies
5. **high_risk_count** = count of nodes with `risk_score > 70` that independently qualify. Preserved ancestors included only for path continuity do NOT count unless they independently have `risk_score > 70`.
6. **vulnerable_count** = count of nodes with `vulnerability_count > 0` that independently qualify. Same ancestor rule as above.
7. **max_depth** = depth of the deepest node in the returned tree
8. **riskiest_branch** = path from root with highest cumulative `risk_score`. Nodes with `risk_score=None` contribute 0 to cumulative score.
9. **filters_applied** = list of filter names that were active (e.g., `["high_risk_only", "max_depth"]`)

## Null Handling and Sort Stability

Sorting must handle missing values deterministically:

| sort_by | Primary | Nulls | Tie-breaker 1 | Tie-breaker 2 |
|---|---|---|---|---|
| `risk_score` | risk_score DESC | Nulls last | name ASC | version ASC (unknown last) |
| `name` | name ASC | — | version ASC (unknown last) | — |
| `vulnerability_count` | vulnerability_count DESC | Nulls treated as 0 | name ASC | version ASC (unknown last) |
| Default (no sort_by) | name ASC | — | version ASC (unknown last) | — |

`version=None` sorts after all known versions within the same name.

## Truncation Rules

1. Truncation is applied per parent node independently.
2. `child_count` reflects the number of children after filtering and sorting but before truncation.
3. `children_truncated=true` is set only when actual truncation occurred (i.e., original child count > limit).
4. Truncation always follows the current sort order. There is no implicit risk-first truncation mode.
5. Truncation is applied recursively at every level of the tree.

## Filter Ordering and Semantics

Filters are applied in this order during Phase 2. The order is semantically meaningful:

1. **direct_only**: If true, remove all nodes with depth > 1. This is NOT equivalent to `max_depth=1` because `max_depth=1` sets `children_truncated=true` on depth-1 nodes that have children, while `direct_only` does not.
2. **max_depth**: Remove nodes deeper than max_depth. Set `children_truncated=true` and `child_count` on boundary nodes.
3. **high_risk_only**: Keep only nodes with `risk_score > 70` and their ancestors from root.
4. **vulnerable_only**: Keep only nodes with `vulnerability_count > 0` and their ancestors from root.
5. When multiple filters are active, AND logic applies: a leaf node must satisfy all active criteria to be a "matching" node. Ancestors are preserved if they lead to any matching node.

**Root inclusion**: The repository root is always included in the returned tree regardless of filters.

**Preserved ancestors**: Ancestors included for path continuity are exempt from filter criteria. They are included because a descendant matched, not because they matched themselves.

## Ancestor Preservation Implementation Note

Because shared dependencies can appear in multiple branches with the same canonical ID, ancestor preservation must NOT rely solely on canonical IDs to identify paths. It must use tree-occurrence context (parent→child traversal) rather than flat ID sets. Otherwise, preserving a canonical ID may accidentally include or merge the wrong branch.

Implementation approach: walk the tree depth-first, mark matching leaf occurrences, then propagate "keep" flags up to root through parent references. Do not collect matching IDs into a flat set and then re-walk.

## Transformation Immutability Rule

Filtering, sorting, and truncation are response-view operations only. They must not:
- Change stored dependency relationships in the database
- Mutate the canonical tree built in Phase 1
- Affect subsequent requests or cached data

Phase 2 must deep-clone the canonical tree before applying any transformations.

## Repository Existence Decision Tree

Used in Phase 1 (`_retrieve_dependency_relationships`):

```
Query repo_dependencies for repo_full_name
  ├─ Rows found → repo exists with dependencies → build tree from rows
  ├─ No rows found → query repo_graphs or repo metadata table for repo_full_name
  │   ├─ Repo record exists → repo exists with zero dependencies
  │   │   → return empty dependency list (root node, no children, 200)
  │   ├─ No repo record → repo not in local data at all
  │   │   ├─ Live ingestion available for this ecosystem?
  │   │   │   ├─ Yes → attempt synchronous live ingestion (request-scoped)
  │   │   │   │   ├─ Ingestion succeeds → build tree, data_source="live"
  │   │   │   │   │   Live-ingested data is request-scoped only (not persisted to DB in MVP)
  │   │   │   │   ├─ Ingestion partially succeeds → build partial tree, data_source="live", data_completeness="partial"
  │   │   │   │   └─ Ingestion fails entirely → raise RepositoryNotFoundError
  │   │   │   └─ No → raise RepositoryNotFoundError
  │   │   └─ (no live ingestion configured) → raise RepositoryNotFoundError
```

**Live ingestion details**:
- Happens synchronously inside the request path (within the timeout budget)
- Only supported ecosystems are attempted
- Produces `data_source="live"` (all nodes live) or `"mixed"` (some DB, some live)
- If partially succeeds: return 200 with partial tree and error nodes for failed portions
- Live-ingested data is request-scoped in MVP. It is NOT persisted to the database or cached. Future versions may persist.

## Depth: Computed, Not Stored

Node depth is computed during tree assembly, not read from the database. The tree builder assigns depth based on the recursive traversal from root:
- Root = 0
- Each child = parent.depth + 1
- When a package appears in multiple branches, it may have different depths in different occurrences

Requirement 1.7 (shortest path) applies to the canonical identity of a package, not to individual tree occurrences. In the tree-shaped output, each occurrence has its own depth based on its position in that branch.

## Node Instance vs Canonical Identity

Two nodes in different branches may share the same canonical `id` (e.g., `pkg:npm/lodash@4.17.21`). They are still separate tree occurrences:
- Each is a distinct `TreeNode` instance with its own `depth`, `children`, `children_truncated`, etc.
- Risk metadata is resolved once per canonical ID and shared (same values), but each node instance holds its own `RiskMetadata` object
- Ancestor preservation, truncation, and filtering operate on tree occurrences, not canonical IDs
- Serialization emits each occurrence independently in the JSON tree

## Risk Score Sourcing: MVP Approximation

The MVP maps package nodes to repository-level risk scores via `package_mappings` → `repo_graphs`. This is an approximation:
- Risk scores are repo-level, not package-level or version-level
- A package inherits the risk profile of its mapped repository
- This does not capture version-specific vulnerabilities or package-specific risk
- Future versions may introduce package-version-native scoring

This approximation is acceptable for MVP because the primary goal is risk explanation, not precise per-version scoring.

## Response-Level vs Node-Level Provenance

Two levels of provenance exist and may differ:

**Response-level** (`ProvenanceInfo`): Describes the overall tree response. Fields: `data_source`, `data_completeness`, `total_nodes`, `nodes_with_risk_data`, etc.

**Node-level** (`RiskMetadata.score_source`, `RiskMetadata.score_completeness`): Describes how risk data was obtained for a specific node.

They may differ: a response may have `data_completeness="partial"` while individual nodes have `score_completeness="full"` (because some other nodes have `score_completeness="missing"`). The response-level provenance is an aggregate summary; node-level provenance is per-node detail.

## Provenance Field Derivation Rules

| Field | Source | Rule |
|---|---|---|
| `total_nodes` | Returned tree | Count all nodes including root |
| `nodes_with_risk_data` | Returned tree | Count nodes where `risk_metadata` is not None and `score_completeness != "missing"` |
| `nodes_with_missing_risk` | Returned tree | Count nodes where `risk_metadata` is None or `score_completeness == "missing"` |
| `nodes_with_errors` | Returned tree | Count nodes where `resolution_status == "error"` |
| `last_updated` | Database | Most recent `updated_at` timestamp from `repo_graphs` rows used in enrichment. If no DB data used, use current request timestamp. |
| `construction_time_ms` | Timer | Wall-clock ms from start of Phase 1 to end of Phase 2 |
| `data_source` | Retrieval path | `"database"` if all from DB, `"live"` if all live, `"mixed"` if both |
| `data_completeness` | Derived | `"full"` if `nodes_with_missing_risk == 0` AND `nodes_with_errors == 0`; else `"partial"` |

## Performance Testing Scope

Benchmark targets apply to:
- **Database-backed trees only** (pre-ingested dependency data)
- **End-to-end API timing** (from HTTP request receipt to JSON response)
- **Representative test environment** (local development machine or CI runner)
- Targets: <5s for <1000 deps, <10s for <5000 deps
- Live ingestion is best-effort with no SLA

## Tasks

- [x] 1. Create tree module structure, exceptions, data models, and tree utilities
  - Create `src/open_source_risk_model/tree/__init__.py` with module exports
  - Create `src/open_source_risk_model/tree/exceptions.py` with `RepositoryNotFoundError`, `TreeConstructionTimeoutError`, `AllDependenciesFailedError`, `DependencyResolutionError`
  - Create `src/open_source_risk_model/tree/models.py` with all dataclasses:
    - `TreeNode` with canonical field names (id, node_type, name, version, depth, children, children_truncated, child_count, dependency_type, ecosystem, specifier, risk_metadata, resolution_status, error_reason)
    - `RiskMetadata` with score_source and score_completeness fields
    - `SummaryMetrics` with filters_applied list
    - `ProvenanceInfo` with all coverage and performance fields
    - `DependencyTreeResponse` with repo, tree, summary_metrics, provenance
    - `FilterConfig` helper dataclass
  - Add `to_dict()` serialization on TreeNode and DependencyTreeResponse:
    - Recursively serialize nested trees
    - Omit optional fields that are None (except version, which is always included)
    - Error nodes include resolution_status and error_reason
    - Stable JSON field ordering
  - Create `src/open_source_risk_model/tree/tree_utils.py` with traversal helpers:
    - `walk_tree(root) -> Iterator[TreeNode]`: Yield all nodes depth-first
    - `clone_tree(root) -> TreeNode`: Deep copy preserving all fields
    - `collect_nodes(root, predicate) -> List[TreeNode]`: Collect nodes matching a predicate
    - `map_tree(root, fn) -> TreeNode`: Apply fn to each node in a cloned tree
    - `count_nodes(root) -> int`: Count all nodes including root
  - Write unit tests in `test/tree/test_models.py`:
    - Test dataclass construction with defaults
    - Test nested tree serialization (root → children → grandchildren)
    - Test error node serialization (resolution_status="error", node_type="package")
    - Test omission of None optional fields
    - Test stable JSON field names match Canonical Field Names table
    - Test canonical ID format: `pkg:{ecosystem}/{name}@{version}` and `pkg:{ecosystem}/{name}@unknown`
  - Write unit tests in `test/tree/test_tree_utils.py`:
    - Test walk_tree visits all nodes depth-first
    - Test clone_tree produces independent copy (mutating clone does not affect original)
    - Test collect_nodes with various predicates
    - Test map_tree applies function to all nodes
  - _Requirements: 1.4, 1.5, 2.2, 2.4, 2.5, 3.7, 9.1, 14.3_
  - _Design: Data Models, Canonical Field Names table, Exception Classes_

- [x] 2. Implement RiskMetadataEnricher
  - Create `src/open_source_risk_model/tree/enricher.py`
  - Implement `RiskMetadataEnricher.enrich_nodes(nodes, db_path)`:
    - Collect all canonical package IDs from the node list
    - Batch query `package_mappings` to resolve package→repository mappings
    - Batch query `repo_graphs` for mapped repositories to get risk_score, vulnerability_count, and optional fields
    - For each node, apply the Risk Score Sourcing hierarchy:
      - Mapping exists + repo_graphs has full data → score_source="repo_graph", score_completeness="full"
      - Mapping exists + repo_graphs has partial data → score_source="repo_graph", score_completeness="partial"
      - Mapping exists + no repo_graphs data → score_source="unavailable", score_completeness="missing"
      - No mapping → score_source="unavailable", score_completeness="missing", risk_score=None
    - `_classify_risk_level(score)`: low (≤30), medium (31–70), high (>70); None if score is None
    - release_recency_days and maintainer_count: populate from repo_graphs if available, None otherwise
    - This is an MVP approximation: risk scores are repo-level, not package-version-native
  - Write unit tests in `test/tree/test_enricher.py`:
    - Test batch enrichment with full risk data
    - Test enrichment when package_mappings has no entry
    - Test enrichment when repo_graphs has partial data
    - Test risk_level classification at boundaries (30, 31, 70, 71)
    - Test with empty node list
    - Test that score_source and score_completeness are set correctly in each scenario
    - Test that same canonical ID enriched once and shared across multiple node instances
  - _Requirements: 2.1–2.6_
  - _Design: RiskMetadataEnricher, Risk Score Sourcing hierarchy_

- [x] 2.1 Write property tests for risk metadata enrichment (REQUIRED)
  - Create `test/tree/test_enricher_properties.py`
  - **Property 5**: Risk Classification Accuracy — risk_level matches risk_score thresholds for all scores 0–100 and None
  - **Property 4**: Risk Metadata Completeness — when score_source="repo_graph", risk_score and vulnerability_count are populated
  - **Property 6**: Missing Data Provenance — nodes without risk data have score_source="unavailable"
  - _Validates: Requirements 2.1–2.6_

- [x] 3. Implement SummaryMetricsCalculator
  - Create `src/open_source_risk_model/tree/metrics.py`
  - Implement `SummaryMetricsCalculator.calculate_metrics(tree_root, filters_applied)`:
    - Use `walk_tree()` to traverse the post-transformation tree
    - Apply the Summary Metrics Rules defined above (totals, high_risk, vulnerable, max_depth, riskiest_branch)
    - Preserved ancestors count in totals but NOT in high_risk_count or vulnerable_count unless independently qualifying
    - Nodes with risk_score=None contribute 0 to riskiest_branch cumulative score
  - Implement `_find_riskiest_branch(root)`: DFS to find path with highest cumulative risk_score
  - Write unit tests in `test/tree/test_metrics.py`:
    - Test total = direct + transitive invariant
    - Test high_risk_count only counts nodes with score > 70
    - Test preserved ancestor not counted in high_risk_count
    - Test riskiest branch identification
    - Test zero-dependency tree (root only, all counts zero)
    - Test with nodes having risk_score=None
    - Test filters_applied is populated correctly
  - _Requirements: 3.1–3.7, 15.1–15.6_
  - _Design: SummaryMetricsCalculator, Summary Metrics Rules_

- [x] 3.1 Write property tests for summary metrics (REQUIRED)
  - Create `test/tree/test_metrics_properties.py`
  - **Property 7**: Summary Metrics Accuracy — total = direct + transitive = nodes - 1
  - **Property 8**: Riskiest Branch Identification — cumulative score ≥ any individual node score
  - _Validates: Requirements 3.1–3.7, 15.1–15.5_

- [x] 3.2 Write property test for filtered metrics accuracy
  - **Property 26**: Filtered Metrics Accuracy — metrics reflect filtered subset
  - _Validates: Requirements 15.6_

- [x] 4. Checkpoint — Verify enricher, metrics, models, and utilities
  - Run all tests in `test/tree/`. Ensure 100% pass rate.
  - Verify field names match Canonical Field Names table.
  - Verify clone_tree produces independent copies.
  - Document assumptions and continue with the best-grounded implementation.

- [x] 5. Implement TreeService Phase 1: Canonical Tree Assembly
  - Create `src/open_source_risk_model/tree/service.py`
  - Implement `TreeService.__init__(self, db_path)`
  - Implement `TreeService._retrieve_dependency_relationships(self, repo_full_name) -> Tuple[List[Dependency], str]`:
    - This is the canonical dependency-retrieval adapter. It encapsulates DB lookup + fallback logic.
    - Returns (dependency_list, data_source) where data_source is "database", "live", or "mixed"
    - Follow the Repository Existence Decision Tree defined above:
      1. Query `repo_dependencies` for repo_full_name
      2. If rows found → return (rows, "database")
      3. If no rows → check repo existence in `repo_graphs` or metadata
      4. If repo exists with zero deps → return ([], "database")
      5. If repo not in local data → attempt live ingestion if available
      6. If live ingestion succeeds → return (live_deps, "live")
      7. If live ingestion partially succeeds → return (partial_deps, "live") with DependencyResolutionError for failures
      8. If live ingestion fails or unavailable → raise RepositoryNotFoundError
    - Live ingestion is synchronous, request-scoped (not persisted), limited to supported ecosystems
  - Implement `TreeService._build_canonical_tree(self, repo_full_name) -> Tuple[TreeNode, str]`:
    - Step 1: Call `_retrieve_dependency_relationships()` to get deps and data_source
    - Step 2: Create root TreeNode with node_type="repository", depth=0, id=repo_full_name
    - Step 3: Build tree recursively:
      - Direct deps → depth=1, dependency_type="direct"
      - Transitive deps → depth=parent.depth+1, dependency_type="transitive"
      - Depth is computed during assembly, not read from database
      - Assign canonical IDs: `pkg:{ecosystem}/{name}@{version}` (use `@unknown` when version missing)
      - Track visited canonical IDs per branch path to detect cycles; on cycle, stop recursion for that branch
      - Shared deps: separate TreeNode instances per branch, same canonical `id` value
      - On DependencyResolutionError: create error node (node_type="package", resolution_status="error"), continue with siblings
    - Step 4: Collect all nodes via walk_tree(), call RiskMetadataEnricher.enrich_nodes()
    - If every dependency raised DependencyResolutionError → raise AllDependenciesFailedError
    - Return (root_node, data_source)
  - Write unit tests in `test/tree/test_service_phase1.py`:
    - Test tree construction from database with direct + transitive deps
    - Test zero-dependency repository returns root with empty children (not an error)
    - Test repo exists but deps not yet extracted (check metadata table) — returns root with empty children or triggers live ingestion depending on config
    - Test repo not in database at all → RepositoryNotFoundError
    - Test cycle detection terminates recursion
    - Test canonical ID assignment: same package in two branches gets same `id`, different TreeNode instances
    - Test depth is computed (not stored): verify depth values match traversal position
    - Test single dependency failure creates error node, siblings still resolved
    - Test all dependencies fail → AllDependenciesFailedError
    - Test canonical ID uses `@unknown` when version is missing
    - Test data_source is "database" for DB path, "live" for live path
  - _Requirements: 1.1–1.7, 8.1, 8.3, 8.4, 14.1–14.3, 14.7_
  - _Design: TreeService Phase 1, Repository Existence Decision Tree, Data Source Precedence_

- [x] 5.1 Write property tests for Phase 1 (REQUIRED)
  - Create `test/tree/test_service_phase1_properties.py`
  - **Property 1**: Tree Structure Correctness — root at depth 0, direct at depth 1, transitive at depth = parent+1
  - **Property 18**: Deterministic Construction — same input → same output (same tree structure, same node ordering)
  - **Property 3**: Cycle Detection Termination — always terminates for any dependency graph
  - **Property 19**: Shared Dependency Duplication — appears in each branch independently with same canonical ID
  - _Validates: Requirements 1.1–1.7, 8.1–8.5_

- [x] 5.2 Write property test for node identity invariants
  - **Property 2**: Node Identity — unique canonical IDs per package+version, consistent across builds
  - _Validates: Requirements 1.4, 1.5, 8.4_

- [x] 6. Implement TreeService Phase 2: Response Transformation
  - Add to `src/open_source_risk_model/tree/service.py`
  - Implement `TreeService._transform_for_response(canonical_tree, data_source, filters, sort_by, truncate_after_children) -> DependencyTreeResponse`:
    - **Step 0**: Deep-clone the canonical tree via `clone_tree()`. All subsequent operations work on the clone.
    - **Step 4**: Apply filters in defined order (direct_only → max_depth → high_risk_only → vulnerable_only):
      - `_filter_direct_only(tree)`: remove nodes with depth > 1. Does NOT set children_truncated on depth-1 nodes (unlike max_depth).
      - `_filter_by_depth(tree, max_depth)`: remove nodes deeper than max_depth. Set children_truncated=true and child_count on boundary nodes that had children.
      - `_filter_by_risk(tree)`: if high_risk_only, identify matching nodes (risk_score > 70), then preserve ancestor paths using tree-occurrence traversal (not flat ID sets). Root always included.
      - `_filter_by_vulnerability(tree)`: if vulnerable_only, same approach with vulnerability_count > 0.
      - AND logic for combined filters: a leaf must satisfy all active criteria to be a matching node.
      - Ancestor preservation uses depth-first walk with parent→child propagation of "keep" flags, not flat canonical ID sets.
    - **Step 5**: Apply sorting via `_sort_siblings(node, sort_by)`:
      - Follow Null Handling and Sort Stability rules (nulls last for risk_score, tie-breakers as defined)
      - Apply recursively to all levels
    - **Step 6**: Apply truncation via `_truncate_children(node, limit)`:
      - Per parent node independently
      - child_count = number of children after filtering and sorting, before truncation
      - children_truncated=true only when actual truncation occurred
      - Keep first N from sorted list
      - Apply recursively
    - **Step 7**: Calculate summary metrics via SummaryMetricsCalculator on the transformed tree
    - **Step 8**: Assemble ProvenanceInfo using Provenance Field Derivation Rules
    - Return DependencyTreeResponse
  - Write unit tests in `test/tree/test_service_phase2.py`:
    - Test direct_only removes depth > 1 nodes, does NOT set children_truncated
    - Test max_depth removes deep nodes, DOES set children_truncated on boundary
    - Test direct_only vs max_depth=1 difference
    - Test high_risk_only preserves ancestor paths (low-risk ancestor of high-risk node included)
    - Test vulnerable_only preserves ancestor paths
    - Test AND logic for combined filters
    - Test root is always included regardless of filters
    - Test sorting by each criterion with null handling and tie-breakers
    - Test truncation keeps first N from sorted order, sets child_count and children_truncated
    - Test truncation with default sort (name+version, not risk-first)
    - Test summary metrics reflect filtered tree, not canonical tree
    - Test preserved ancestors count in totals but not in high_risk_count
    - **Copy-safety tests**:
      - Test applying filters does not mutate the original canonical tree
      - Test sorting does not mutate sibling order on the original tree
      - Test truncation does not mutate original child lists
    - Test ancestor preservation uses tree-occurrence context (two branches with same canonical ID preserved independently)
  - _Requirements: 5.2–5.5, 6.2–6.8, 7.2–7.4, 13.2–13.8, 15.6_
  - _Design: Phase 2, Filter Ordering, Sort/Truncation Precedence, Ancestor Preservation_

- [x] 6.1 Write property tests for Phase 2 (includes REQUIRED tests)
  - Create `test/tree/test_service_phase2_properties.py`
  - **Property 20**: Sorting Consistency — all sibling groups sorted by specified criterion at every depth (REQUIRED)
  - **Property 21**: Default Sort Order — name then version when no sort_by (REQUIRED)
  - **Property 10**: Depth Filtering Correctness
  - **Property 11**: Truncation Metadata Accuracy
  - **Property 12**: Unfiltered Tree Completeness
  - **Property 13**: Risk-Based Filtering with Ancestor Preservation
  - **Property 14**: Vulnerability Filtering with Ancestor Preservation
  - **Property 15**: Direct-Only Filtering
  - **Property 16**: Filter Combination Logic
  - **Property 17**: Truncation with Sorting
  - _Validates: Requirements 5.2–5.5, 6.2–6.8, 7.2–7.4, 13.2–13.8_

- [x] 7. Implement error handling and provenance tracking
  - Add to `src/open_source_risk_model/tree/service.py`
  - Error handling in Phase 1 (`_build_canonical_tree`):
    - Catch `DependencyResolutionError` per dependency → create error node (node_type="package", resolution_status="error", error_reason=message, risk_metadata=None, children=[])
    - Continue processing remaining siblings
    - Track errors in a list for provenance
    - If all deps failed → raise AllDependenciesFailedError
  - Provenance assembly in Phase 2 (`_transform_for_response`):
    - Apply Provenance Field Derivation Rules exactly as defined above
    - data_source from retrieval path
    - data_completeness: "full" only if nodes_with_missing_risk=0 AND nodes_with_errors=0
    - last_updated: most recent `updated_at` from `repo_graphs` rows used in enrichment; if no DB data, use request timestamp
    - construction_time_ms: wall-clock from Phase 1 start to Phase 2 end
    - Node-level provenance (score_source, score_completeness) set during enrichment; response-level provenance is an aggregate summary
  - Write unit tests in `test/tree/test_error_handling.py`:
    - Test single dependency failure creates error node, siblings resolved
    - Test error node has node_type="package", resolution_status="error", risk_metadata=None
    - Test all dependencies fail → AllDependenciesFailedError
    - Test provenance data_completeness="partial" when errors exist
    - Test provenance data_completeness="full" when no errors and all risk data present
    - Test provenance error_details lists all error nodes with id and error_reason
    - Test provenance data_source for database, live, mixed scenarios
    - Test zero-dependency repo provenance: data_source="database", data_completeness="full"
    - Test construction_time_ms is populated and > 0
    - Test last_updated uses repo_graphs timestamp when available
    - Test response-level vs node-level provenance can differ (response partial, some nodes full)
  - _Requirements: 9.2–9.6, 14.1–14.7_
  - _Design: Error Handling, Provenance semantics table, Provenance Field Derivation Rules_

- [x] 7.1 Write property tests for error handling and provenance
  - Create `test/tree/test_error_provenance_properties.py`
  - **Property 22**: Partial Results on Errors
  - **Property 23**: Error Resilience
  - **Property 24**: Error Tracking in Provenance
  - **Property 25**: Provenance Accuracy
  - _Validates: Requirements 9.2–9.6, 14.1–14.7_

- [x] 8. Checkpoint — Verify TreeService end-to-end
  - Run all tests in `test/tree/`. Ensure 100% pass rate.
  - Verify the two-phase pipeline order is preserved: retrieve → build → enrich → clone → filter → sort → truncate → metrics → provenance.
  - Verify canonical IDs use `pkg:{ecosystem}/{name}@{version}` format (or `@unknown`).
  - Verify clone_tree is called before Phase 2 transformations.
  - Verify copy-safety tests pass (original tree not mutated).
  - Document assumptions and continue with the best-grounded implementation.

- [x] 9. Implement API endpoint and TreeService.get_dependency_tree()
  - Implement `TreeService.get_dependency_tree()` as the public entry point:
    - Start wall-clock timer
    - Call `_build_canonical_tree()` (Phase 1)
    - Call `_transform_for_response()` (Phase 2)
    - Check elapsed time against timeout_seconds; raise TreeConstructionTimeoutError if exceeded
    - Timeout is enforced inside this method. API layer catches the exception.
  - Add to `api/app.py`:
    - GET `/repos/{repo_id}/dependency-tree` endpoint
    - Query parameters: max_depth (int 1–10), high_risk_only (bool), vulnerable_only (bool), direct_only (bool), sort_by (enum), truncate_after_children (int ≥1)
    - Instantiate TreeService, call get_dependency_tree()
    - Return JSON response matching API Response Schema (validate against Pydantic model or equivalent)
    - Exception → HTTP status mapping:
      - RepositoryNotFoundError → 404
      - TreeConstructionTimeoutError → 503
      - AllDependenciesFailedError → 503
      - Unexpected exception → 500
    - Zero-dependency repos → 200 with root node, zero counts, full provenance
  - Create `src/open_source_risk_model/tree/response_schema.py` (or add to models.py):
    - Define Pydantic response model matching the API Response Schema
    - Use for automatic response validation in tests
  - Write unit tests in `test/tree/test_api_endpoint.py`:
    - Test valid repo returns 200 with complete response schema
    - Test zero-dependency repo returns 200 (not 404)
    - Test unknown repo returns 404
    - Test invalid max_depth (0, 11) returns 400
    - Test invalid sort_by returns 400
    - Test timeout returns 503
    - Test all deps failed returns 503
    - Test partial failure returns 200 with error nodes
    - Test each query parameter is passed through correctly
    - **Response schema validation tests**:
      - Validate response against Pydantic model
      - Verify all canonical field names present
      - Verify nested tree serialization is correct
      - Verify error node serialization in response
  - _Requirements: 4.1–4.7, 5.1, 5.6, 6.1, 7.1, 7.6, 13.1, 14.4, 14.6_
  - _Design: API Endpoint Handler, Behavior for Special Cases, TreeService Public Method Contract_

- [x] 9.1 Write property test for API response structure
  - **Property 9**: API Response Structure Completeness
  - _Validates: Requirements 4.2, 4.4, 4.5, 9.1_

- [x] 10. Smoke tests against known repositories
  - Create `test/tree/test_smoke.py`:
    - Test a normal repository with dependencies → 200, tree has children, metrics populated
    - Test a zero-dependency repository → 200, empty children, all counts zero
    - Test a filtered request (high_risk_only=true) → 200, only high-risk nodes and ancestors
    - Test a repository with intentionally missing dependency data → 200 with error nodes, partial provenance
    - These tests exercise the actual endpoint with real or realistic test data
    - Purpose: fast signal before full integration coverage
  - _Requirements: 4.2, 4.7, 14.4_

- [x] 11. Write integration tests
  - Create `test/tree/test_tree_integration.py`:
    - Test complete flow: API request → TreeService → database queries → JSON response
    - Test with a real repository from the database (if available)
    - Test filter combinations produce correct results end-to-end
    - Test error handling with intentionally missing data
    - Test performance: <5s for repos with <1000 deps (database-backed, end-to-end API timing)
    - Test zero-dependency repository end-to-end
    - Test provenance accuracy across different data source scenarios
    - Test canonical ID consistency: same package in two branches has same ID in response JSON
    - Test deterministic output: same request twice produces identical JSON
    - Test response validates against Pydantic response schema
  - _Requirements: 4.7, 7.5, 14.4, 14.6_
  - _Design: Performance targets table, Integration Testing section_

- [x] 12. Final checkpoint — End-to-end validation
  - Run full test suite. Ensure all tests pass.
  - Verify the following explicitly:
    - **Pipeline order preserved**: retrieve → build → enrich → clone → filter → sort → truncate → metrics → provenance
    - **No mutation of canonical tree**: copy-safety tests pass; Phase 2 operates on clone only
    - **Deterministic JSON output**: same request with same data produces byte-identical JSON on repeated runs
    - **Zero-dependency repo semantics**: returns 200 with root, zero counts, full provenance
    - **Partial-result semantics**: error nodes present, provenance partial, 200 status
    - **Live/database provenance semantics**: data_source correctly reflects retrieval path
    - **Field name consistency**: no instances of `registry_type`, `dependency_kind`, or `maintainer_health` in source or tests
    - **Response schema validation**: all responses validate against Pydantic model
  - Document assumptions and continue with the best-grounded implementation.

## Notes

### Required vs Optional Property Tests

The following property tests are REQUIRED (not optional) because they validate core invariants:
- **Property 1**: Tree Structure Correctness (Task 5.1)
- **Property 5**: Risk Classification Accuracy (Task 2.1)
- **Property 7**: Summary Metrics Accuracy (Task 3.1)
- **Property 8**: Riskiest Branch Identification (Task 3.1)
- **Property 18**: Deterministic Construction (Task 5.1)
- **Property 20**: Sorting Consistency (Task 6.1)
- **Property 21**: Default Sort Order (Task 6.1)

Tasks marked with `*` that are not in the above list are optional and can be deferred for faster MVP delivery.

### Implementation Reminders

- Follow the strict two-phase pipeline. Do not reorder steps without a strong reason.
- Phase 2 must clone the canonical tree before any transformation.
- Summary metrics are always calculated on the post-transformation tree.
- Sort then truncate. No implicit risk-first truncation.
- Error nodes always use node_type="package" with resolution_status="error".
- Zero-dependency repositories return 200, not 404.
- Performance SLAs apply to database-backed trees only.
- Ancestor preservation uses tree-occurrence traversal, not flat canonical ID sets.
- Risk scores are repo-level approximations via package_mappings. This is documented and intentional for MVP.
- Checkpoints do not pause for user input. Document assumptions and continue.
