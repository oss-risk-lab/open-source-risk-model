# Tasks: Transitive Dependency Resolution

## Phase 1: Foundation — Data Models, Storage, and Cache

### Task 1: Resolution Data Models
- [x] Create `src/open_source_risk_model/resolution/__init__.py` (empty package init)
- [x] Create `src/open_source_risk_model/resolution/models.py` with:
  - `RESOLUTION_STATUSES` frozenset: `{"resolved", "error", "cycle_detected", "max_depth_reached", "unsupported_ecosystem", "budget_exhausted"}` (Req 5.4)
  - `PackageIdentity(frozen=True)` dataclass: `ecosystem: str`, `name: str` — available for typed contexts; version excluded per MVP semantics (Req 6.1)
  - `make_node_key(ecosystem, name, version=None) -> tuple` — centralized identity key factory. MVP returns `(ecosystem, name)`, ignoring version. All call sites (cycle detection, cache keys, tree reconstruction grouping, branch_visited guards) MUST use this function instead of raw tuples. When post-MVP adds version-aware resolution, this single function is the only place that changes.
  - `DependencyDeclaration` dataclass: `name: str`, `specifier: Optional[str]` — represents a single dependency as declared by a parent
  - `NormalizedPackageMetadata` dataclass: `name`, `version`, `ecosystem`, `dependencies: list[DependencyDeclaration]`, `source_url`, `fetched_at` — what the cache stores (Req 6.1)
  - `ResolutionEdge` dataclass with all fields per design: `repo_full_name`, `parent_ecosystem` (nullable), `parent_package`, `child_ecosystem` (nullable), `child_package`, `declared_specifier` (nullable), `resolved_version` (nullable), `depth`, `resolution_status` (default "resolved"), `error_reason` (nullable), `source_registry` (nullable — stores exclusively ecosystem name like "pypi", never a URL), `resolved_at` (Req 4.2, 7.2, 7.3, 8.1-8.3)
  - `ResolutionSummary` dataclass with `edges_per_depth: dict[int, int]` field and `from_edges()` classmethod that counts statuses via match/case and populates `edges_per_depth` histogram (Req 11.5)
- [x] Create `test/resolution/__init__.py`
- [x] Create `test/resolution/test_models.py` with tests:
  - `PackageIdentity` is frozen and hashable (usable in sets)
  - `PackageIdentity` equality: same ecosystem+name → equal; different ecosystem → not equal
  - `make_node_key("pypi", "requests")` returns `("pypi", "requests")` — version ignored in MVP
  - `make_node_key("pypi", "requests", "2.31.0")` returns `("pypi", "requests")` — version ignored in MVP
  - `make_node_key(None, "owner/repo")` returns `(None, "owner/repo")` — works for repo-as-parent
  - `RESOLUTION_STATUSES` contains exactly the 6 defined values
  - `ResolutionEdge` defaults: `resolution_status="resolved"`, `error_reason=None`, `source_registry=None`
  - `ResolutionSummary.from_edges()` correctly counts each status type
  - `ResolutionSummary.from_edges()` computes `actual_max_depth` from edge depths
  - `ResolutionSummary.from_edges()` populates `edges_per_depth` histogram correctly
  - `ResolutionSummary.from_edges()` with empty edge list returns zero counts and empty histogram

**Requirements**: Req 4.2, 5.4, 6.1, 7.2, 7.3, 8.1-8.3, 11.5

---

### Task 2: Resolved Dependency Storage
- [x] Create `src/open_source_risk_model/resolution/storage.py` with `ResolvedDependencyStorage`:
  - `__init__(self, db_path)` — stores db_path, calls `ensure_tables()`
  - `ensure_tables()` — creates `resolved_dependencies` table with surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT` and all columns per design schema (Req 12.1, 12.2); creates three indexes: `idx_resolved_deps_repo` on `(repo_full_name)`, `idx_resolved_deps_parent` on `(repo_full_name, parent_ecosystem, parent_package)`, `idx_resolved_deps_depth` on `(repo_full_name, depth)` (Req 12.3)
  - `store_edges(repo_full_name, edges)` — DELETE + INSERT in single transaction (Req 7.1, 7.4)
  - `get_edges(repo_full_name)` — SELECT ordered by `depth, parent_ecosystem, parent_package, child_package` — ordering matches reconstruction key (Req 7.5, 14.2)
  - `has_resolved_data(repo_full_name)` — returns True if any edge with `resolution_status='resolved'` exists (Req 7.6, 10.1)
  - `get_oldest_resolved_at(repo_full_name)` — returns `MIN(resolved_at)` for staleness display (Req 15)
  - `delete_resolved(repo_full_name)` — deletes all edges, returns count
  - `_row_to_edge(row)` — converts sqlite3.Row to ResolutionEdge
- [x] Create `test/resolution/test_storage.py` with tests:
  - `ensure_tables()` creates table and indexes without error (idempotent)
  - `store_edges()` then `get_edges()` round-trips all fields correctly (Req 7.7)
  - `store_edges()` replaces previous edges for same repo (Req 7.4)
  - `store_edges()` with empty list clears existing edges
  - `get_edges()` returns deterministic order: depth ASC, parent_ecosystem ASC (NULLs first), parent_package ASC, child_package ASC (Req 14.2)
  - `has_resolved_data()` returns True when resolved edges exist, False when only error edges exist, False when no edges exist
  - `get_oldest_resolved_at()` returns earliest timestamp
  - `delete_resolved()` removes all edges and returns correct count
  - Duplicate parent-child pairs across branches are allowed (no UNIQUE constraint) (Req 12.2)
  - `parent_ecosystem` is NULL for depth-1 edges, non-NULL for deeper edges (Req 7.3)

**Requirements**: Req 7, 12, 14.2, 15

---

### Task 3: Resolution Cache
- [x] Create `src/open_source_risk_model/resolution/cache.py` with `ResolutionCache`:
  - `__init__(self, db_path, ttl_hours=168)` — stores config, initializes empty session dict `_session: dict[tuple[str,str], NormalizedPackageMetadata | None]`, calls `_ensure_table()` (Req 6.5)
  - `_ensure_table()` — creates `package_metadata_cache` table with PK `(ecosystem, package_name)`, columns: `metadata_json`, `fetched_at`, `expires_at`
  - `lookup(ecosystem, name) -> tuple[NormalizedPackageMetadata | None, bool]` — checks session cache first (Req 6.2), then DB cache with expiry check (Req 6.3); returns `(metadata, True)` on hit, `(None, False)` on miss; promotes DB hits to session cache
  - `store(ecosystem, name, metadata)` — writes to both session and DB cache (Req 6.4); positive results use 168h TTL (Req 6.5), negative results (`metadata=None`) use 1h TTL (Req 6.6); serializes `NormalizedPackageMetadata` to JSON for DB storage
  - `_read_db_cache(key)` — reads from `package_metadata_cache` with `expires_at > datetime('now')` check
  - `_write_db_cache(key, metadata)` — INSERT OR REPLACE with computed `expires_at`
  - `_CACHE_MISS` sentinel for distinguishing "not found" from "found None"
  - HARD INVARIANT: Cache is a pure lookup/store layer — MUST NEVER trigger external API calls. No `get_or_fetch` method. All registry calls originate from the resolver after budget checks. Any method that makes a registry call inside this class violates the architectural contract.
- [x] Create `test/resolution/test_cache.py` with tests:
  - Session cache hit returns `(metadata, True)` without DB access
  - DB cache hit returns `(metadata, True)` and populates session cache
  - Cache miss returns `(None, False)`
  - `store()` then `lookup()` round-trips `NormalizedPackageMetadata` correctly (Req 6.8)
  - Negative cache: `store(eco, name, None)` then `lookup()` returns `(None, True)` — cache hit with None metadata
  - Expired positive entries are treated as misses (TTL=168h) (Req 6.5)
  - Expired negative entries are treated as misses (TTL=1h) (Req 6.6)
  - Session cache is checked before DB cache (verify with mock)
  - `_ensure_table()` is idempotent
  - Cache key is `(ecosystem, package_name)` — same name in different ecosystems are separate entries

**Requirements**: Req 6, 15.2

---

## Phase 2: Registry Clients, Factory, and Budget Tracker

### Task 4: Registry Client ABC
- [x] Create `src/open_source_risk_model/resolution/registry_client.py` with `RegistryClient(ABC)`:
  - Abstract property `ecosystem -> str` (Req 1.2)
  - Abstract method `get_package_metadata(name: str, specifier: str | None = None) -> NormalizedPackageMetadata | None` (Req 1.1) — specifier accepted but not used for version selection in MVP; returns None on any failure
- [x] Create `test/resolution/test_registry_client.py` with tests:
  - Cannot instantiate `RegistryClient` directly (ABC enforcement)
  - Concrete subclass must implement both `ecosystem` and `get_package_metadata`

**Requirements**: Req 1.1, 1.2

---

### Task 5: PyPI Registry Client
- [x] Create `src/open_source_risk_model/resolution/pypi_client.py` with `PyPIClient(RegistryClient)`:
  - `ecosystem` property returns `"pypi"` (Req 1.2)
  - `get_package_metadata(name, specifier=None)` — fetches `https://pypi.org/pypi/{name}/json`, extracts `info.version` as Resolved_Version (Req 2.2), parses `info.requires_dist` via `_parse_requires_dist()` (Req 2.1), returns `NormalizedPackageMetadata`; returns None on 404 (Req 2.6), non-200 (Req 2.7), timeout/network error (Req 2.8); logs warnings on failures; no retries (Req 2.9); timeout=10s
  - `_parse_requires_dist(requires_dist: list[str]) -> list[DependencyDeclaration]` — excludes entries with `extra ==` markers (Req 2.4); includes entries with environment markers like `sys_platform`, `python_version` conservatively (Req 2.5); uses `packaging.Requirement` if available, else regex fallback
  - Helper `_parse_pep508_entry(entry: str) -> tuple[str, str | None]` — extracts name and specifier from a PEP 508 string
- [x] Create `test/resolution/test_pypi_client.py` with tests:
  - `ecosystem` returns `"pypi"`
  - Successful fetch returns `NormalizedPackageMetadata` with correct name, version, ecosystem, dependencies
  - HTTP 404 returns None (Req 2.6)
  - HTTP 500 returns None and logs warning (Req 2.7)
  - Network timeout returns None and logs warning (Req 2.8)
  - `_parse_requires_dist` excludes `extra ==` entries (Req 2.4)
  - `_parse_requires_dist` includes environment-marker entries (Req 2.5)
  - `_parse_requires_dist` with empty list returns empty list
  - `_parse_requires_dist` extracts name and specifier correctly from PEP 508 strings
  - `specifier` parameter is accepted but does not affect version selection (MVP)
  - `source_url` is set to the PyPI JSON API URL
  - `fetched_at` is a valid ISO 8601 timestamp
  - (Use `unittest.mock.patch` or `responses` library to mock HTTP calls)

**Requirements**: Req 2

---

### Task 6: npm Registry Client
- [x] Create `src/open_source_risk_model/resolution/npm_client.py` with `NpmClient(RegistryClient)`:
  - `ecosystem` property returns `"npm"` (Req 1.2)
  - `get_package_metadata(name, specifier=None)` — fetches `https://registry.npmjs.org/{encoded_name}` with URL-encoded name for scoped packages (Req 3.5); extracts `dist-tags.latest` as version tag (Req 3.1, 3.2); reads `versions[latest].dependencies` only — excludes devDependencies, peerDependencies, optionalDependencies (Req 3.4); sorts dependencies by name for determinism; returns `NormalizedPackageMetadata`; returns None on 404 (Req 3.6), non-200 (Req 3.7), timeout/network error (Req 3.8); no retries (Req 3.9); timeout=10s
- [x] Create `test/resolution/test_npm_client.py` with tests:
  - `ecosystem` returns `"npm"`
  - Successful fetch returns correct metadata with dependencies from `dependencies` only
  - Scoped package names (`@scope/name`) are URL-encoded correctly (Req 3.5)
  - `devDependencies`, `peerDependencies`, `optionalDependencies` are excluded (Req 3.4)
  - HTTP 404 returns None (Req 3.6)
  - HTTP 500 returns None and logs warning (Req 3.7)
  - Network timeout returns None (Req 3.8)
  - Missing `dist-tags.latest` returns None
  - Dependencies are sorted by name in the returned metadata
  - `specifier` parameter is accepted but does not affect version selection (MVP)

**Requirements**: Req 3

---

### Task 7: Registry Factory
- [x] Create `src/open_source_risk_model/resolution/registry_factory.py` with:
  - `_CLIENTS` dict mapping `"pypi"` → `PyPIClient`, `"npm"` → `NpmClient`
  - `get_registry_client(ecosystem: str) -> RegistryClient | None` — returns instantiated client or None for unsupported ecosystems (Req 1.3, 1.4)
- [x] Create `test/resolution/test_registry_factory.py` with tests:
  - `get_registry_client("pypi")` returns `PyPIClient` instance (Req 1.3)
  - `get_registry_client("npm")` returns `NpmClient` instance (Req 1.3)
  - `get_registry_client("rubygems")` returns None (Req 1.4)
  - `get_registry_client("unknown")` returns None (Req 1.4)
  - Returned clients have correct `ecosystem` property values

**Requirements**: Req 1.3, 1.4

---

### Task 8: Budget Tracker
- [x] Create `src/open_source_risk_model/resolution/budget_tracker.py` with:
  - `BudgetConfig` dataclass: `global_budget: int = 200` (Req 9.1), `per_ecosystem: dict[str, int] = field(default_factory=dict)` (Req 9.4), `min_delay_ms: int = 100` (Req 9.5)
  - `BudgetTracker`:
    - `__init__(self, config: BudgetConfig)` — initializes counters and last-call timestamps
    - `can_make_call(ecosystem: str) -> bool` — checks per-ecosystem budget if configured, else global budget (Req 9.1, 9.4)
    - `record_call(ecosystem: str)` — increments both global and per-ecosystem counters; counts even for failed calls (Req 9.2)
    - `wait_if_needed(ecosystem: str)` — enforces minimum delay between calls to same ecosystem using `time.monotonic()` and `time.sleep()` (Req 9.5)
    - `api_calls_made` property — returns global counter
- [x] Create `test/resolution/test_budget_tracker.py` with tests:
  - `can_make_call()` returns True when under budget
  - `can_make_call()` returns False when global budget exhausted (Req 9.1)
  - `can_make_call()` returns False when per-ecosystem budget exhausted (Req 9.4)
  - Per-ecosystem budget overrides global budget for that ecosystem
  - `record_call()` increments both global and per-ecosystem counters (Req 9.2)
  - `api_calls_made` reflects total calls across all ecosystems
  - `wait_if_needed()` sleeps when calls are too close together (mock `time.sleep` and `time.monotonic`) (Req 9.5)
  - `wait_if_needed()` does not sleep when enough time has elapsed
  - Default config: global_budget=200, min_delay_ms=100

**Requirements**: Req 9

---

## Phase 3: Transitive Resolver (Core Algorithm)

### Task 9: Transitive Resolver
- [x] Create `src/open_source_risk_model/resolution/resolver.py` with `TransitiveResolver`:
  - `__init__(self, db_path, max_depth=5, budget_config=None, ecosystem_filter=None)` — initializes `BudgetTracker`, `ResolutionCache`, stores config; `_cache_hits` counter
  - `resolve_repo(repo_full_name) -> tuple[list[ResolutionEdge], ResolutionSummary]` (Req 4.1):
    - Reads direct deps from `repo_dependencies` via `_get_direct_deps()`
    - Sorts direct deps by `package_name` for determinism (Req 14.1)
    - Applies `ecosystem_filter` if set
    - Calls `_resolve_recursive()` for each direct dep with `depth=1`, `parent_ecosystem=None`, `parent_package=repo_full_name`, fresh `branch_path=set()`
    - Returns `(edges, ResolutionSummary.from_edges(...))`
  - `_resolve_recursive(repo_full_name, parent_ecosystem, parent_package, child_name, child_ecosystem, declared_specifier, depth, branch_path, edges)`:
    - Check 1: `depth > max_depth` → append `max_depth_reached` edge, return (Req 4.3)
    - Check 2: `make_node_key(child_ecosystem, child_name) in branch_path` → append `cycle_detected` edge, return (Req 4.5, 4.6) — uses `make_node_key()` for ecosystem-qualified identity
    - Check 3: `get_registry_client(child_ecosystem) is None` → append `unsupported_ecosystem` edge, return (Req 5.2)
    - Step 4: `cache.lookup()` — if hit, increment `_cache_hits`, skip budget (Req 6.7)
    - Step 5: If cache miss, `budget.can_make_call()` — if False, append `budget_exhausted` edge, return (Req 9.3)
    - Step 6: `budget.wait_if_needed()`, `client.get_package_metadata()`, `budget.record_call()`, `cache.store()` (authoritative flow)
    - Check 7: metadata is None → append `error` edge with reason, return (Req 5.1)
    - Success: append `resolved` edge (Req 4.2, 8.1-8.3)
    - Recurse: `new_branch_path = branch_path | {make_node_key(child_ecosystem, child_name)}`, iterate sorted sub-deps, call `_resolve_recursive()` with `depth+1`, `parent_ecosystem=child_ecosystem`, `parent_package=child_name`, `child_ecosystem=child_ecosystem` (same ecosystem inheritance) (Req 4.7)
  - `_make_edge()` static helper — constructs `ResolutionEdge` from parameters
  - `_get_direct_deps(repo_full_name)` — queries `repo_dependencies` table ordered by `package_name`
- [x] Create `test/resolution/test_resolver.py` with tests:
  - Resolves direct deps at depth 1 with `parent_ecosystem=None`, `parent_package=repo_full_name`
  - Resolves transitive deps at depth 2+ with correct parent identity (ecosystem-qualified)
  - Cycle detection: A→B→A produces `cycle_detected` edge on second A (Req 4.5)
  - Cycle detection is branch-local: same package in different branches is resolved independently (Req 4.6)
  - Max depth: stops recursion and records `max_depth_reached` (Req 4.3)
  - Unsupported ecosystem: records `unsupported_ecosystem` edge (Req 5.2)
  - Budget exhaustion: records `budget_exhausted` edge when budget runs out (Req 9.3)
  - Cache hit skips budget check and API call (Req 6.7)
  - Failed API call (None return) records `error` edge with reason (Req 5.1)
  - Authoritative flow order: cache lookup → budget check → delay → fetch → record → store
  - Deterministic output: sorted direct deps, sorted sub-deps (Req 14.1)
  - `ResolutionSummary` has correct counts for all status types
  - `source_registry` is set to ecosystem name for resolved/error edges, None for cycle/depth/budget edges
  - `resolved_at` is set on all edges
  - `declared_specifier` flows through from parent metadata (Req 2.3, 3.3)
  - `resolved_version` is set from registry metadata for resolved edges, None for non-resolved
  - Empty direct deps returns empty edges list
  - Ecosystem filter excludes non-matching ecosystems
  - Sub-dependencies inherit parent's ecosystem (no cross-ecosystem deps in MVP)
  - (Mock registry clients, cache, and budget tracker for unit isolation)

**Requirements**: Req 4, 5, 8, 9, 14

---

## Phase 4: Tree Service Integration

### Task 10: Tree Service — Resolved Data Path
- [x] Modify `src/open_source_risk_model/tree/service.py`:
  - Import `ResolvedDependencyStorage` and `ResolutionEdge` from `resolution` package
  - Modify `_build_canonical_tree()`: before existing flat-tree logic, check `storage.has_resolved_data(repo_full_name)` (Req 10.1); if True, call `storage.get_edges()`, build tree via `_build_tree_from_resolved()`, enrich nodes, return `(root, "database")` (Req 10.2); if False, fall through to existing flat-tree logic unchanged (Req 10.3)
  - Add `_build_tree_from_resolved(repo_full_name, edges) -> TreeNode` (Req 10.2):
    - Create root `TreeNode` with `depth=0`, `node_type="repository"`
    - Group edges by `make_node_key(parent_ecosystem, parent_package)` into `children_by_parent` dict — uses `make_node_key()` for centralized identity
    - Direct children: lookup key `make_node_key(None, repo_full_name)`, sorted by `child_package` (Req 14.3)
    - For each direct edge, call `_edge_to_node()` recursively
  - Add `_edge_to_node(edge, children_by_parent, branch_visited) -> TreeNode` (Req 10.2):
    - Creates NEW `TreeNode` per edge — no deduplication across branches (Req 4.7, 10.2c)
    - Maps `resolution_status` via `_map_resolution_status()` (Req 10.4)
    - Sets `dependency_type` = "direct" if depth==1, else "transitive"
    - Sets `version` from `resolved_version`, `specifier` from `declared_specifier` (Req 10.6)
    - Terminal statuses (error, cycle_detected, max_depth_reached, budget_exhausted, unsupported_ecosystem) → return leaf node, no children
    - Safety guard: `branch_visited` set of `make_node_key()` tuples prevents reconstruction loops — uses `make_node_key(edge.child_ecosystem, edge.child_package, edge.resolved_version)` for consistency with resolver identity
    - Finds children via `children_by_parent[make_node_key(edge.child_ecosystem, edge.child_package)]` — ecosystem-qualified key via `make_node_key()`
    - Sorts child edges by `child_package` for determinism (Req 14.3)
  - Add `_map_resolution_status(edge) -> tuple[str, str | None]` (Req 10.4):
    - `"resolved"` → `("resolved", None)`
    - `"error"` → `("error", edge.error_reason)`
    - `"cycle_detected"` → `("cycle_detected", None)`
    - `"max_depth_reached"` → `("max_depth_reached", None)`
    - `"unsupported_ecosystem"` → `("unsupported_ecosystem", "Ecosystem not supported for resolution")` — visible terminal state, NOT mapped to "resolved"
    - `"budget_exhausted"` → `("budget_exhausted", "Resolution budget exhausted")`
- [x] Create `test/tree/test_resolved_tree.py` with tests:
  - Resolved data present → multi-level tree built from edges (Req 10.1, 10.2)
  - No resolved data → falls back to flat tree from `repo_dependencies` (Req 10.3)
  - Tree reconstruction uses ecosystem-qualified parent keys — no cross-ecosystem name collision
  - Separate node occurrences: same package under different parents → separate TreeNode instances (Req 4.7)
  - `_map_resolution_status` maps all 6 statuses correctly (Req 10.4)
  - `unsupported_ecosystem` maps to visible `"unsupported_ecosystem"` status, NOT `"resolved"`
  - `budget_exhausted` maps to `"budget_exhausted"` with reason string
  - Terminal statuses produce leaf nodes with no children
  - `version` populated from `resolved_version`, `specifier` from `declared_specifier` (Req 10.6)
  - Children sorted alphabetically by package name (Req 14.3)
  - Depth-1 edges produce `dependency_type="direct"`, deeper edges produce `"transitive"`
  - Root node has `depth=0`, `node_type="repository"`
  - Reconstruction safety guard prevents infinite loops from inconsistent data
  - Reconstruction safety guard uses `make_node_key()` for identity — ecosystem-qualified
  - Unsupported ecosystem propagation: edges with `unsupported_ecosystem` status appear as terminal leaf nodes in the tree, are included in `ResolutionSummary.unsupported_ecosystem_count`, and do NOT trigger recursion into children
  - `SummaryMetrics.max_depth` reflects actual max depth in resolved tree (Req 10.5)

**Requirements**: Req 10, 14.3

---

## Phase 5: CLI Command and Ingestion Integration

### Task 11: CLI Resolution Command
- [x] Create `src/open_source_risk_model/cli/resolve.py` with `main() -> int`:
  - `argparse` with required `--repo` and optional `--max-depth` (default 5), `--ecosystems` (comma-separated), `--budget` (default 200), `--force`, `--db-path` (default "data/graphs.db") (Req 11.1-11.4)
  - Without `--force`: check `storage.has_resolved_data()`, if exists print age from `get_oldest_resolved_at()` and exit 0 (Req 15.4)
  - Check direct deps exist via `resolver._get_direct_deps()` — if empty, print error to stderr and exit 1 (Req 11.6)
  - Create `TransitiveResolver` with parsed config, call `resolve_repo()`
  - Store edges via `storage.store_edges()` (Req 7.1)
  - Print summary: total edges, resolved, errors, cycles, max_depth_reached, budget_exhausted, unsupported_ecosystem, max depth seen, API calls, cache hits, elapsed time (Req 11.5)
  - Exit 0 on completion even with partial failures (Req 11.7)
  - Exit 1 only for infrastructure failures: no direct deps, DB errors, invalid args (Req 11.8)
  - `if __name__ == "__main__": sys.exit(main())`
- [x] Create `test/resolution/test_cli_resolve.py` with tests:
  - `--repo` is required
  - Successful resolution prints summary and exits 0
  - No direct deps prints error to stderr and exits 1 (Req 11.6)
  - `--force` re-resolves even when data exists (Req 15.4)
  - Without `--force`, existing data prints skip message and exits 0
  - `--ecosystems pypi` filters to PyPI only
  - `--budget 50` overrides default budget
  - `--max-depth 3` overrides default depth
  - Partial failures (some errors) still exit 0 (Req 11.7)
  - (Use `unittest.mock.patch` to mock resolver and storage)

**Requirements**: Req 11, 15.4

---

### Task 12: Ingestion Pipeline Integration
- [x] Modify `src/open_source_risk_model/dependencies/ingestion_service.py`:
  - Add `resolve_transitive: bool = False` parameter to `ingest_repo()` (Req 13.1)
  - After successful ingestion (when `resolve_transitive=True` and `result.success` and `result.dependencies_found > 0`): import `TransitiveResolver` and `ResolvedDependencyStorage`, resolve, store edges (Req 13.2)
  - Wrap resolution in try/except: on failure, log at ERROR level and continue — do not abort ingestion (Req 13.3)
  - Resolution never modifies `repo_dependencies` (Req 13.4, 12.4)
- [x] Create `test/resolution/test_ingestion_integration.py` with tests:
  - `resolve_transitive=False` (default) does not trigger resolution
  - `resolve_transitive=True` with successful ingestion triggers resolution
  - `resolve_transitive=True` with failed ingestion (`success=False`) does not trigger resolution
  - `resolve_transitive=True` with zero dependencies does not trigger resolution
  - Resolution failure is caught and logged, ingestion result still returned (Req 13.3)
  - `repo_dependencies` table is not modified by resolution (Req 13.4)
  - (Mock TransitiveResolver and ResolvedDependencyStorage)

**Requirements**: Req 13

---

## Phase 6: Property-Based Tests

### Task 13: Resolver Property-Based Tests
- [x] Create `test/resolution/test_resolver_properties.py` with Hypothesis-based tests:
  - **Determinism property** (Req 14.1): For any generated set of direct deps and mocked registry responses, running `resolve_repo()` twice produces identical edge lists
  - **Edge count property**: Total edges ≥ number of direct deps (every direct dep produces at least one edge)
  - **Depth bounds property** (Req 4.3): No edge has `depth > max_depth`; edges at `depth == max_depth + 1` are impossible
  - **Status completeness property** (Req 5.3, 5.4): Every edge has a `resolution_status` in `RESOLUTION_STATUSES`
  - **Branch-local cycle property** (Req 4.5, 4.6): If a cycle exists on one branch, the same package can still be resolved on a different branch
  - **Summary consistency property** (Req 11.5): `summary.total_edges == len(edges)` and status counts sum to `total_edges`
  - **Provenance property** (Req 8.1-8.3): Every edge has non-empty `resolved_at`; resolved edges have `source_registry` set; depth ≥ 1
  - **Cache idempotency property** (Req 6.8): Storing then looking up metadata returns equivalent result
  - **Budget monotonicity property** (Req 9.2): `budget.api_calls_made` never decreases; after N `record_call()` invocations, `api_calls_made == N`
  - **MVP resolution semantics property**: Different declared specifiers for the same package result in the same `resolved_version` (latest), confirming MVP always-latest semantics are enforced as a contract
  - **edges_per_depth consistency property**: `sum(summary.edges_per_depth.values()) == summary.total_edges` and all depth keys are ≥ 1
  - **source_registry invariant property**: For every edge, `source_registry` is either None or a short ecosystem identifier string (e.g., "pypi", "npm") — never a URL
  - Use `@given(st.lists(st.text(...)))` strategies for package names, `st.integers(min_value=1, max_value=10)` for depths
  - Mock registry clients to return controlled `NormalizedPackageMetadata` or None

**Requirements**: Req 4, 5, 6, 8, 9, 14
