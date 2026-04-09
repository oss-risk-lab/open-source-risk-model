# Requirements Document

## Introduction

The current dependency ingestion pipeline parses manifest files (requirements.txt, package.json, etc.) and stores only direct, manifest-declared dependencies in the `repo_dependencies` table. Every stored row has `is_direct = 1` and no parent-child relationship is recorded. The dependency tree API consequently returns a flat list (max_depth=1) under the repository root.

This feature adds transitive dependency resolution to the ingestion pipeline. A new resolution layer queries ecosystem registries (PyPI, npm for MVP) to discover each direct dependency's own dependencies, recursively building a parent-child graph up to a configurable depth. The resolved graph is stored in a new `resolved_dependencies` table and consumed by the existing tree API to render multi-level dependency trees.

## MVP Boundaries

This section defines what the MVP explicitly includes and excludes, to prevent scope creep and set correct expectations for consumers of the resolved data.

**MVP includes:**
- PyPI and npm registry clients only.
- Resolution of install-time production dependencies only (no dev, test, optional, or peer dependencies).
- Storage of a useful transitive dependency graph with provenance metadata and partial-coverage tolerance.
- Graceful handling of resolution failures, cycles, and depth limits as first-class edge statuses.

**MVP does not include:**
- Universal lockfile-accurate resolution across all ecosystems. The resolver uses registry metadata, not lockfiles.
- Full semver constraint solving. Version selection uses documented heuristics (latest version for PyPI, latest dist-tag for npm), not a complete constraint solver.
- Cross-ecosystem graph normalization beyond storing edges with ecosystem labels.
- Exact environment-specific resolution for Python environment markers, pip extras, or npm peer dependency semantics. The resolver applies conservative documented rules, not full environment reproduction.
- Support for ecosystems beyond PyPI and npm (RubyGems, crates.io, Maven Central, pkg.go.dev are post-MVP).
- Automatic background resolution after ingestion (post-MVP).

**Interpretation guidance:** The resolved graph is an approximation of the transitive dependency structure, suitable for risk analysis and tree visualization. It is not a substitute for a package manager's resolver output. Users should not interpret the resolved graph as the exact set of packages that would be installed in a specific environment.

## Non-Goals

The following are explicitly out of scope for this feature (including post-MVP):
- Lockfile-perfect reproduction of installed dependency sets.
- Full semver solver behavior matching pip, npm, or any other package manager.
- Organization-wide dependency graph analytics or cross-repo aggregation.
- Frontend graph visualization changes as part of this backend feature.
- Dependency license detection or compliance analysis.
- Vulnerability scanning integration (handled by existing CVE/GHSA infrastructure).

## Glossary

- **Resolver**: The component that recursively walks dependency relationships by querying ecosystem registries, producing a parent-child dependency graph.
- **Registry_Client**: An abstraction that fetches package metadata (including dependency lists) from an ecosystem registry such as PyPI or npm.
- **PyPI_Client**: A Registry_Client implementation that fetches metadata from the PyPI JSON API (`https://pypi.org/pypi/{package}/json`).
- **Npm_Client**: A Registry_Client implementation that fetches metadata from the npm registry API (`https://registry.npmjs.org/{package}`).
- **Registry_Factory**: A factory component that returns the appropriate Registry_Client for a given ecosystem identifier.
- **Resolution_Cache**: A two-tier cache (in-memory session cache and database-backed cache with TTL) that stores previously fetched Normalized_Package_Metadata to avoid redundant registry calls.
- **Resolved_Dependency_Storage**: The persistence component that reads and writes parent-child dependency edges in the `resolved_dependencies` table.
- **Tree_Service**: The existing service that builds dependency tree responses; it will be extended to prefer resolved transitive data when available.
- **Ingestion_Pipeline**: The existing `DependencyIngestionService` that discovers manifests, parses them, and stores direct dependencies.
- **Resolution_Edge**: A data record representing a single parent→child dependency relationship, including depth, resolution status, provenance, and both declared specifier and resolved version.
- **Cycle**: A situation where package A depends on package B which (directly or transitively) depends back on package A, detected within a single branch path from root to leaf.
- **Error_Edge**: A Resolution_Edge with `resolution_status="error"`, representing a failed registry lookup. The tree service derives an error TreeNode from an Error_Edge.
- **Resolution_Provenance**: Metadata recording how and when a dependency was resolved (source registry, timestamp, depth level).
- **CLI_Resolve_Command**: A command-line interface entry point that triggers transitive resolution for one or more repositories.
- **Declared_Specifier**: The version constraint string as declared by the parent package's metadata (e.g., `>=1.0,<2.0`, `^3.2.1`, `*`). This is what the parent says it requires. May be None if the parent declares no version constraint.
- **Resolved_Version**: The concrete version string selected by the resolver when fetching package metadata from the registry (e.g., `2.31.0`, `4.18.2`). For MVP, this is the latest available version (PyPI) or the version tagged as `latest` dist-tag (npm). May be None if the package could not be resolved.
- **Normalized_Package_Metadata**: The structured result of a registry lookup: package name, resolved version, ecosystem, list of declared dependencies (each with name and Declared_Specifier), source URL, and fetch timestamp. This is what the Resolution_Cache stores.
- **Package_Identity**: The canonical tuple `(ecosystem, package_name)` that uniquely identifies a package within a resolution context. Used for cache keys and cycle detection. Version is not part of identity for MVP because the resolver always resolves to the latest version.
- **Branch_Path**: The ordered sequence of Package_Identity values from the repository root to the current node being resolved. Used for cycle detection. A cycle exists when a Package_Identity appears twice in the same Branch_Path.
- **Node_Depth**: The distance from the repository root to a node in the dependency tree. The repository root is depth 0. Direct dependencies are depth 1. First-level transitive dependencies are depth 2. This matches the existing TreeNode.depth convention.

## Requirements

### Requirement 1: Registry Client Abstraction

**User Story:** As a developer, I want a common interface for fetching package metadata from ecosystem registries, so that the Resolver can work uniformly across ecosystems.

#### Acceptance Criteria

1. THE Registry_Client SHALL define an abstract method that accepts a package name and an optional Declared_Specifier, and returns Normalized_Package_Metadata or None (if the package is not found).
2. THE Registry_Client SHALL define an abstract property that returns the ecosystem identifier string (e.g., "pypi", "npm").
3. WHEN a concrete Registry_Client implementation is instantiated, THE Registry_Factory SHALL return the correct implementation for the ecosystem identifier ("pypi" or "npm").
4. IF an unsupported ecosystem identifier is provided, THEN THE Registry_Factory SHALL return None (not raise an exception), allowing the Resolver to handle unsupported ecosystems as leaf nodes.

### Requirement 2: PyPI Registry Client

**User Story:** As a developer, I want to fetch dependency metadata from PyPI, so that the Resolver can discover transitive dependencies for Python packages.

#### Acceptance Criteria

1. WHEN a valid Python package name is provided, THE PyPI_Client SHALL fetch metadata from `https://pypi.org/pypi/{package}/json` and return Normalized_Package_Metadata with dependencies extracted from the `info.requires_dist` field.
2. THE PyPI_Client SHALL set the Resolved_Version to the latest available version as reported by the `info.version` field of the JSON response. This is an MVP simplification; the resolver does not attempt to solve version constraints against the specifier.
3. THE PyPI_Client SHALL store the original Declared_Specifier from the parent on the Resolution_Edge, separately from the Resolved_Version.
4. WHEN the `requires_dist` field contains entries with `extra ==` markers, THE PyPI_Client SHALL exclude those entries and return only default install-time dependencies.
5. WHEN the `requires_dist` field contains entries with environment markers (e.g., `sys_platform`, `python_version`), THE PyPI_Client SHALL include those dependencies conservatively (include them rather than exclude them). This is an MVP simplification; the resolver does not evaluate environment markers.
6. IF the PyPI API returns HTTP 404, THEN THE PyPI_Client SHALL return None.
7. IF the PyPI API returns any other non-200 HTTP status, THEN THE PyPI_Client SHALL return None and log the status code and package name at WARNING level.
8. IF the PyPI API request times out or a network error occurs, THEN THE PyPI_Client SHALL return None and log the error at WARNING level.
9. THE PyPI_Client SHALL NOT retry failed requests. MVP performs no retries. This is an explicit simplification; bounded retry with backoff is a post-MVP enhancement.

### Requirement 3: npm Registry Client

**User Story:** As a developer, I want to fetch dependency metadata from npm, so that the Resolver can discover transitive dependencies for JavaScript packages.

#### Acceptance Criteria

1. WHEN a valid npm package name is provided, THE Npm_Client SHALL fetch metadata from `https://registry.npmjs.org/{package}` and return Normalized_Package_Metadata with dependencies extracted from the `dependencies` field of the version pointed to by the `dist-tags.latest` tag. This is an MVP simplification; the resolver does not attempt to solve semver ranges against the specifier.
2. THE Npm_Client SHALL set the Resolved_Version to the version string pointed to by `dist-tags.latest`.
3. THE Npm_Client SHALL store the original Declared_Specifier from the parent on the Resolution_Edge, separately from the Resolved_Version.
4. THE Npm_Client SHALL exclude `devDependencies`, `peerDependencies`, and `optionalDependencies` from the returned dependency list.
5. THE Npm_Client SHALL handle scoped packages (names starting with `@`) by URL-encoding the package name in the registry request.
6. IF the npm registry returns HTTP 404, THEN THE Npm_Client SHALL return None.
7. IF the npm registry returns any other non-200 HTTP status, THEN THE Npm_Client SHALL return None and log the status code and package name at WARNING level.
8. IF the npm registry request times out or a network error occurs, THEN THE Npm_Client SHALL return None and log the error at WARNING level.
9. THE Npm_Client SHALL NOT retry failed requests. MVP performs no retries.

### Requirement 4: Recursive Transitive Resolver

**User Story:** As a developer, I want the system to recursively resolve transitive dependencies, so that the full dependency graph is captured beyond direct manifest declarations.

#### Acceptance Criteria

1. WHEN resolution is triggered for a repository, THE Resolver SHALL retrieve the repository's direct dependencies from the `repo_dependencies` table and recursively resolve each dependency's sub-dependencies using the appropriate Registry_Client.
2. THE Resolver SHALL produce a list of Resolution_Edge records. Each edge SHALL contain: parent Package_Identity fields, child package name, child ecosystem, Declared_Specifier (from parent metadata), Resolved_Version (from registry lookup), Node_Depth of the child, resolution_status, error_reason (nullable), source_registry, and resolved_at timestamp.
3. THE Resolver SHALL enforce a configurable maximum Node_Depth with a default value of 5. WHEN a child node would exceed the maximum depth, THE Resolver SHALL stop recursion for that branch and record the edge with resolution_status="max_depth_reached".
4. Node_Depth is defined as the distance from the repository root: the root is depth 0 (not stored as an edge), direct dependencies are depth 1, first transitive children are depth 2, and so on. This matches the existing TreeNode.depth convention.
5. THE Resolver SHALL detect cycles using Branch_Path tracking: for each recursive call, the Resolver maintains the ordered set of Package_Identity values from root to the current node. IF the child's Package_Identity already appears in the current Branch_Path, THE Resolver SHALL stop recursion for that branch and record the edge with resolution_status="cycle_detected".
6. Cycle detection SHALL be branch-local. The same package MAY appear in multiple branches of the tree and SHALL be resolved independently in each branch. Session-level fetch deduplication is handled by the Resolution_Cache, not by the cycle detector.
7. THE Resolver SHALL allow the same package to produce separate Resolution_Edge records in different branches. A package that appears as a transitive dependency of both package A and package B SHALL produce edges under both parents.

### Requirement 5: Partial Failure Handling

**User Story:** As a developer, I want the resolver to handle failures gracefully, so that a single package lookup failure does not abort the entire resolution.

#### Acceptance Criteria

1. IF a Registry_Client returns None for a specific package, THEN THE Resolver SHALL record a Resolution_Edge for that package with resolution_status="error" and an appropriate error_reason string, and continue resolving remaining packages.
2. IF the Registry_Factory returns None for an unsupported ecosystem, THEN THE Resolver SHALL record the direct dependency as a leaf edge with resolution_status="unsupported_ecosystem" and SHALL NOT attempt recursion for that branch.
3. WHEN resolution completes, THE Resolver SHALL return the complete list of Resolution_Edge records including all statuses: "resolved", "error", "cycle_detected", "max_depth_reached", "unsupported_ecosystem", and "budget_exhausted".
4. THE resolution_status field SHALL use exactly one of the following values: "resolved", "error", "cycle_detected", "max_depth_reached", "unsupported_ecosystem", "budget_exhausted".

### Requirement 6: Resolution Cache

**User Story:** As a developer, I want resolved package metadata to be cached, so that repeated resolutions do not make redundant registry API calls.

#### Acceptance Criteria

1. THE Resolution_Cache SHALL store Normalized_Package_Metadata keyed by the tuple (ecosystem, package_name). Version is not part of the cache key for MVP because the resolver always fetches the latest version.
2. WHEN the Resolver requests metadata for a package, THE Resolution_Cache SHALL first check the in-memory session cache. IF a hit is found, THE Resolution_Cache SHALL return the cached Normalized_Package_Metadata without making a registry API call.
3. IF the session cache misses, THE Resolution_Cache SHALL check the database-backed cache. IF a non-expired entry is found, THE Resolution_Cache SHALL return it and populate the session cache.
4. IF both caches miss, THE Resolution_Cache SHALL invoke the Registry_Client, store the result in both the session cache and the database-backed cache, and return it.
5. THE database-backed cache SHALL have a configurable TTL with a default of 168 hours (7 days). WHEN an entry's `fetched_at` timestamp plus TTL is before the current time, the entry SHALL be treated as expired.
6. THE Resolution_Cache SHALL also cache negative results (package not found / error). Negative cache entries SHALL use a shorter TTL of 1 hour to allow recovery from transient failures.
7. Cache hits SHALL NOT count against the rate-limit budget (Requirement 9). Only actual registry API calls count.
8. FOR ALL packages, fetching metadata then caching then fetching again within the TTL SHALL return an equivalent Normalized_Package_Metadata result (round-trip property).

### Requirement 7: Resolved Dependency Storage

**User Story:** As a developer, I want resolved parent-child dependency edges stored in the database, so that the tree API can serve multi-level trees without re-resolving.

#### Acceptance Criteria

1. WHEN resolution completes for a repository, THE Resolved_Dependency_Storage SHALL write all Resolution_Edge records to the `resolved_dependencies` table in a single transaction.
2. Each stored edge SHALL contain: repo_full_name, parent_ecosystem, parent_package, child_ecosystem, child_package, declared_specifier (nullable), resolved_version (nullable), depth, resolution_status, error_reason (nullable), source_registry (nullable), resolved_at.
3. Parent identity in stored edges SHALL include both ecosystem and package name. For direct dependencies (depth=1), the parent_package SHALL be the repo_full_name and parent_ecosystem SHALL be NULL. For transitive dependencies (depth>1), parent_package SHALL be the parent's package name and parent_ecosystem SHALL be the parent's ecosystem.
4. WHEN resolution is re-run for a repository, THE Resolved_Dependency_Storage SHALL delete all previously stored edges for that repository and insert the new edges, within a single transaction.
5. THE Resolved_Dependency_Storage SHALL provide a method to retrieve all resolved edges for a given repository, ordered by depth then by parent_ecosystem then by parent_package then by child_package.
6. THE Resolved_Dependency_Storage SHALL provide a method `has_resolved_data(repo_full_name) -> bool` that returns True if any resolved edges exist for the repository.
7. FOR ALL stored Resolution_Edge records, writing then reading SHALL return equivalent records (round-trip property).

### Requirement 8: Resolution Provenance

**User Story:** As a developer, I want each resolved dependency to carry provenance metadata, so that I can audit when and how each dependency was resolved.

#### Acceptance Criteria

1. THE Resolver SHALL record the source registry name (e.g., "pypi", "npm") on each Resolution_Edge where the package was successfully fetched from a registry.
2. THE Resolver SHALL record an ISO 8601 timestamp (resolved_at) on each Resolution_Edge indicating when resolution occurred.
3. THE Resolver SHALL record the Node_Depth on each Resolution_Edge, where depth 1 = direct dependency, depth 2 = first transitive level, etc.
4. FOR edges resolved from cache, the source_registry SHALL still reflect the original registry that produced the cached data. The distinction between fresh fetch, session cache hit, and DB cache hit is NOT stored on individual edges for MVP. This information MAY be included in run-level diagnostics (logged at INFO level) but is not persisted per-edge.

### Requirement 9: Rate Limiting for Registry Requests

**User Story:** As a developer, I want registry API requests to be rate-limited, so that the resolver does not overwhelm external registries or get blocked.

#### Acceptance Criteria

1. THE Resolver SHALL enforce a configurable maximum number of actual registry API calls per resolution run (default: 200). Cache hits do not count against this budget.
2. Failed API calls (non-200 responses, timeouts, network errors) DO count against the budget.
3. WHEN the registry call budget is exhausted during a resolution run, THE Resolver SHALL stop making new registry requests and mark all remaining unresolved packages with resolution_status="budget_exhausted".
4. THE Resolver SHALL support per-ecosystem budgets. If per-ecosystem budgets are configured, they apply independently. If only a global budget is configured, it applies across all ecosystems. Per-ecosystem budgets, when set, override the global budget for that ecosystem.
5. THE Resolver SHALL insert a configurable minimum delay between consecutive registry API calls to the same ecosystem (default: 100 milliseconds).

### Requirement 10: Tree Service Integration

**User Story:** As a developer, I want the existing tree API to use resolved transitive data when available, so that the frontend can display multi-level dependency trees.

#### Acceptance Criteria

1. WHEN the Tree_Service builds a dependency tree for a repository, it SHALL first check whether the `resolved_dependencies` table contains any edges for that repository with resolution_status="resolved" (at least one successfully resolved edge must exist).
2. IF resolved data exists (per criterion 1), THE Tree_Service SHALL construct the tree from the `resolved_dependencies` table, producing a multi-level parent-child hierarchy by: (a) selecting edges where parent_package=repo_full_name as direct children at depth 1, (b) recursively attaching children by matching child_package to parent_package of deeper edges, (c) handling shared transitive dependencies by creating separate TreeNode instances in each branch where they appear.
3. IF no resolved data exists, THE Tree_Service SHALL fall back to the existing flat tree built from the `repo_dependencies` table. This preserves backward compatibility.
4. THE Tree_Service SHALL map resolution_status values from stored edges to TreeNode fields: "resolved" → resolution_status="resolved"; "error" → resolution_status="error" with error_reason populated; "cycle_detected" → resolution_status="cycle_detected" (leaf node, no children); "max_depth_reached" → resolution_status="max_depth_reached" (leaf node); "unsupported_ecosystem" → resolution_status="unsupported_ecosystem" with error_reason="Ecosystem not supported for resolution" (leaf node, visible terminal state — NOT mapped to "resolved"); "budget_exhausted" → resolution_status="budget_exhausted" with error_reason="Resolution budget exhausted" (leaf node).
5. THE Tree_Service SHALL set the `max_depth` field in SummaryMetrics to reflect the actual maximum Node_Depth present in the resolved tree.
6. THE Tree_Service SHALL populate the `specifier` field on TreeNode from the stored declared_specifier, and the `version` field from the stored resolved_version. Both may be None.
7. THE Tree_Service SHALL NOT consider staleness of resolved data for MVP. If resolved edges exist, they are used regardless of age. Freshness enforcement is a post-MVP concern. The resolved_at timestamp is stored for future use but not evaluated by the Tree_Service.

### Requirement 11: CLI Resolution Command

**User Story:** As a developer, I want a CLI command to trigger transitive dependency resolution, so that I can resolve dependencies for repositories on demand.

#### Acceptance Criteria

1. THE CLI_Resolve_Command SHALL accept a repository name (in "owner/repo" format) as a required argument.
2. THE CLI_Resolve_Command SHALL accept an optional `--max-depth` flag to override the default maximum recursion depth.
3. THE CLI_Resolve_Command SHALL accept an optional `--ecosystems` flag to limit resolution to specific ecosystems (e.g., "pypi", "npm").
4. THE CLI_Resolve_Command SHALL accept an optional `--budget` flag to override the default API call budget.
5. WHEN resolution completes, THE CLI_Resolve_Command SHALL print a summary including: total edges resolved, error count, cycle count, max_depth_reached count, budget_exhausted count, unsupported_ecosystem count, maximum depth reached, and elapsed time.
6. IF the specified repository has no ingested direct dependencies, THEN THE CLI_Resolve_Command SHALL print a descriptive message and exit with a non-zero status code.
7. THE CLI_Resolve_Command SHALL exit with status code 0 when resolution completes, even if some packages failed to resolve, cycles were detected, or the budget was exhausted. These are normal operational outcomes, not command failures.
8. THE CLI_Resolve_Command SHALL exit with a non-zero status code only for infrastructure failures: repository not found, database errors, or invalid arguments.

### Requirement 12: Database Schema for Resolved Dependencies

**User Story:** As a developer, I want a dedicated database table for resolved dependency edges, so that transitive relationships are stored separately from manifest-declared direct dependencies.

#### Acceptance Criteria

1. THE Resolved_Dependency_Storage SHALL create a `resolved_dependencies` table with columns:
   - `id` INTEGER PRIMARY KEY AUTOINCREMENT — surrogate key for each edge
   - `repo_full_name` TEXT NOT NULL — the repository this edge belongs to
   - `parent_ecosystem` TEXT — ecosystem of the parent package (NULL for direct deps where parent is the repo)
   - `parent_package` TEXT NOT NULL — parent package name, or repo_full_name for direct deps
   - `child_ecosystem` TEXT — ecosystem of the child package
   - `child_package` TEXT NOT NULL — child package name
   - `declared_specifier` TEXT — the Declared_Specifier from the parent's metadata (nullable)
   - `resolved_version` TEXT — the Resolved_Version from the registry lookup (nullable)
   - `depth` INTEGER NOT NULL — Node_Depth of the child (1 = direct, 2 = first transitive, etc.)
   - `resolution_status` TEXT NOT NULL DEFAULT 'resolved' — one of: resolved, error, cycle_detected, max_depth_reached, unsupported_ecosystem, budget_exhausted
   - `error_reason` TEXT — human-readable error description (nullable)
   - `source_registry` TEXT — registry that produced the data (nullable)
   - `resolved_at` TEXT NOT NULL — ISO 8601 timestamp
2. THE table SHALL use a surrogate integer primary key (`id`) rather than a composite natural key, because the same parent-child pair may appear at different depths, under different branches, or with different resolved versions. A UNIQUE constraint SHALL NOT be applied on (repo_full_name, parent_package, child_package) because duplicate parent-child pairs across branches are valid.
3. THE Resolved_Dependency_Storage SHALL create the following indexes:
   - `idx_resolved_deps_repo` ON (repo_full_name) — for bulk retrieval and deletion by repo
   - `idx_resolved_deps_parent` ON (repo_full_name, parent_ecosystem, parent_package) — for ecosystem-qualified tree reconstruction (finding children of a parent)
   - `idx_resolved_deps_depth` ON (repo_full_name, depth) — for depth-ordered queries
4. THE `resolved_dependencies` table SHALL be completely independent of the `repo_dependencies` table. Direct dependency ingestion remains the source of truth for declared dependencies. Transitive resolution is an augmentation layer and SHALL NOT modify or overwrite `repo_dependencies`.

### Requirement 13: Integration with Existing Ingestion Pipeline

**User Story:** As a developer, I want transitive resolution to integrate with the existing ingestion pipeline, so that resolution can optionally run as part of the standard ingestion flow.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL accept an optional `resolve_transitive` flag (default: False) that triggers transitive resolution after direct dependency ingestion completes.
2. WHEN `resolve_transitive` is True and direct dependency ingestion succeeds, THE Ingestion_Pipeline SHALL invoke the Resolver for the ingested repository.
3. IF transitive resolution fails (unhandled exception), THEN THE Ingestion_Pipeline SHALL log the error at ERROR level and return the ingestion result with direct dependencies intact. The overall ingestion SHALL NOT be aborted by a resolution failure.
4. THE Ingestion_Pipeline SHALL NOT modify the `repo_dependencies` table based on resolution results. Direct dependency ingestion and transitive resolution are independent data flows writing to independent tables.

### Requirement 14: Deterministic Resolution Output

**User Story:** As a developer, I want repeated resolution runs to produce stable results, so that tests are reliable and tree output is predictable.

#### Acceptance Criteria

1. WHEN the Resolver is run twice against the same repository with equivalent direct dependencies, unchanged cache contents, and unchanged registry responses, THE Resolver SHALL produce an equivalent set of Resolution_Edge records.
2. THE Resolved_Dependency_Storage SHALL store and retrieve edges in a deterministic order: ordered by depth ascending, then by parent_ecosystem ascending (NULLs first), then by parent_package ascending, then by child_package ascending.
3. THE Tree_Service SHALL render children within each parent node in a deterministic order (alphabetical by package name) when no explicit sort_by is specified.

### Requirement 15: Freshness and Staleness

**User Story:** As a developer, I want resolved data to carry timestamps so that staleness can be evaluated in the future, even though MVP does not enforce freshness.

#### Acceptance Criteria

1. Every Resolution_Edge SHALL carry a resolved_at ISO 8601 timestamp.
2. THE Resolution_Cache database entries SHALL carry fetched_at and expires_at timestamps.
3. FOR MVP, the Tree_Service SHALL NOT enforce freshness on resolved edges. Resolved data is used regardless of age.
4. FOR MVP, the CLI_Resolve_Command SHALL accept an optional `--force` flag that re-resolves even if resolved data already exists for the repository. Without `--force`, the CLI SHALL skip resolution if resolved data exists and print a message indicating the data age.
