# Requirements Document: Dependency Tree View

## Introduction

The Dependency Tree View feature provides a hierarchical visualization of repository dependencies to help users understand and assess supply chain risk. The system displays a repository as the root node with direct and transitive dependencies as child nodes, enriched with risk metadata and summary metrics. This enables users to identify high-risk dependency branches and make informed decisions about their software supply chain.

## Glossary

- **Repository**: The software project being analyzed, serving as the root of the dependency tree
- **Dependency_Tree**: A hierarchical data structure representing the repository and its dependencies
- **Direct_Dependency**: A package explicitly declared in the repository's manifest files (depth 1)
- **Transitive_Dependency**: A package required by a direct or transitive dependency (depth 2+)
- **Node**: A single element in the dependency tree representing either a repository or a dependency
- **Risk_Metadata**: Quantitative and qualitative data about security and maintenance risks for a node
- **Risk_Score**: A numerical value (0-100) indicating the overall risk level of a node
- **Vulnerability_Count**: The number of known security vulnerabilities affecting a node
- **Depth**: The distance of a node from the repository root (repository = 0, direct = 1, transitive = 2+)
- **Tree_API**: The REST endpoint that returns dependency tree data
- **Summary_Metrics**: Aggregate statistics about the entire dependency tree
- **Provenance**: Metadata indicating the data source and completeness status
- **High_Risk_Node**: A node with a risk score above a defined threshold
- **Truncation**: The process of limiting child nodes displayed for performance reasons
- **Dependency_Branch**: A path from the repository root through one or more dependencies

## Requirements

### Requirement 1: Tree Data Model Construction [MVP]

**User Story:** As a developer, I want the system to build a dependency tree from repository data, so that I can see the complete dependency structure.

#### Acceptance Criteria

1. THE Tree_Builder SHALL construct a Dependency_Tree with the Repository as the root node at depth 0
2. WHEN a repository has declared dependencies, THE Tree_Builder SHALL add them as Direct_Dependency nodes at depth 1
3. WHEN a Direct_Dependency has its own dependencies, THE Tree_Builder SHALL add them as Transitive_Dependency nodes at depth 2 or greater
4. THE Tree_Builder SHALL assign a unique identifier to each Node
5. THE Tree_Builder SHALL record the depth value for each Node
6. THE Tree_Builder SHALL detect cycles and prevent infinite recursion by tracking visited nodes
7. FOR ALL nodes in the tree, the depth value SHALL equal the shortest path length from the repository root

### Requirement 2: Risk Metadata Attachment [MVP]

**User Story:** As a security analyst, I want each dependency to show risk information, so that I can identify problematic dependencies.

#### Acceptance Criteria

1. WHEN risk data is available for a Node, THE Tree_Builder SHALL attach Risk_Metadata to that Node
2. THE Risk_Metadata SHALL include Risk_Score, Vulnerability_Count, release recency in days, and maintainer health status
3. WHEN a Node has a Risk_Score above 70, THE Tree_Builder SHALL classify it as a High_Risk_Node
4. THE Risk_Metadata SHALL include the dependency type (direct or transitive)
5. THE Risk_Metadata SHALL include the package ecosystem and version
6. WHEN risk data is unavailable for a Node, THE Tree_Builder SHALL indicate missing data in the Provenance field

### Requirement 3: Summary Metrics Calculation [MVP]

**User Story:** As a developer, I want to see aggregate statistics about my dependencies, so that I can understand the overall risk profile at a glance.

#### Acceptance Criteria

1. THE Tree_Builder SHALL calculate the total count of Direct_Dependency nodes
2. THE Tree_Builder SHALL calculate the total count of Transitive_Dependency nodes
3. THE Tree_Builder SHALL calculate the count of High_Risk_Node entries
4. THE Tree_Builder SHALL calculate the count of nodes with Vulnerability_Count greater than zero
5. THE Tree_Builder SHALL determine the maximum depth value in the Dependency_Tree
6. THE Tree_Builder SHALL identify the Dependency_Branch with the highest cumulative Risk_Score
7. THE Tree_Builder SHALL include all calculated metrics in the Summary_Metrics object

### Requirement 4: Tree API Endpoint [MVP]

**User Story:** As a frontend developer, I want a REST API to fetch dependency tree data, so that I can render the visualization.

#### Acceptance Criteria

1. THE Tree_API SHALL expose a GET endpoint at /repos/{repo_id}/dependency-tree
2. WHEN a valid repo_id is provided, THE Tree_API SHALL return a JSON response containing the Dependency_Tree
3. WHEN an invalid repo_id is provided, THE Tree_API SHALL return a 404 status code with an error message
4. THE Tree_API SHALL include Summary_Metrics in the response
5. THE Tree_API SHALL include Provenance information indicating data source and completeness
6. WHEN the Tree_API encounters an internal error, THE Tree_API SHALL return a 500 status code with an error message
7. THE Tree_API SHALL return responses within 5 seconds for repositories with up to 1000 total dependencies

### Requirement 5: Depth Limiting [MVP]

**User Story:** As a user, I want to limit how deep the tree goes, so that I can focus on the most relevant dependencies.

#### Acceptance Criteria

1. THE Tree_API SHALL accept an optional max_depth query parameter
2. WHEN max_depth is provided, THE Tree_Builder SHALL exclude all nodes with depth greater than max_depth
3. WHEN max_depth is provided, THE Tree_Builder SHALL preserve the tree structure up to the specified depth
4. WHEN a Node at max_depth has children, THE Tree_Builder SHALL set children_truncated to true and include child_count
5. WHEN max_depth is not provided, THE Tree_Builder SHALL include all nodes regardless of depth
6. THE max_depth parameter SHALL accept integer values between 1 and 10

### Requirement 6: Risk-Based Filtering [MVP]

**User Story:** As a security analyst, I want to filter the tree to show only high-risk dependencies, so that I can prioritize remediation efforts.

#### Acceptance Criteria

1. THE Tree_API SHALL accept an optional high_risk_only query parameter
2. WHEN high_risk_only is true, THE Tree_Builder SHALL include only High_Risk_Node entries and their ancestor paths
3. Ancestor nodes required to preserve the path from the repository root to a matching node SHALL be included in the returned tree even if they do not independently satisfy the filter criteria
4. THE Tree_API SHALL accept an optional vulnerable_only query parameter
5. WHEN vulnerable_only is true, THE Tree_Builder SHALL include only nodes with Vulnerability_Count greater than zero and their ancestor paths
6. THE Tree_API SHALL accept an optional direct_only query parameter
7. WHEN direct_only is true, THE Tree_Builder SHALL include only the Repository and Direct_Dependency nodes
8. WHEN multiple filter parameters are provided, THE Tree_Builder SHALL apply all filters using AND logic

### Requirement 7: Large Tree Handling [MVP]

**User Story:** As a user analyzing a large repository, I want the system to handle thousands of dependencies gracefully, so that the interface remains responsive.

#### Acceptance Criteria

1. THE Tree_API SHALL accept an optional truncate_after_children query parameter
2. WHEN a Node has more children than truncate_after_children, THE Tree_Builder SHALL include only the first N children sorted by Risk_Score descending
3. WHEN children are truncated, THE Tree_Builder SHALL set children_truncated to true
4. WHEN children are truncated, THE Tree_Builder SHALL set child_count to the total number of children before truncation
5. FOR cached or database-backed repositories with up to 5000 total dependencies, tree assembly SHALL complete within 10 seconds under normal operating conditions
6. WHEN tree construction exceeds the timeout, THE Tree_API SHALL return a 503 status code with a timeout message

### Requirement 8: Deterministic Tree Structure [MVP]

**User Story:** As a developer, I want the same repository to produce the same tree structure, so that results are reproducible.

#### Acceptance Criteria

1. WHEN the Tree_Builder processes the same repository data twice, THE Tree_Builder SHALL produce identical tree structures
2. THE Tree_Builder SHALL sort sibling nodes by a deterministic ordering (name, then version)
3. WHEN a Transitive_Dependency appears in multiple branches, THE Tree_Builder SHALL include it in each branch independently
4. THE Tree_Builder SHALL use consistent node identifiers for the same package and version across multiple builds
5. FOR ALL nodes at the same depth with the same parent, the ordering SHALL remain stable across API calls

### Requirement 9: Provenance Tracking [MVP]

**User Story:** As a user, I want to know where the dependency data came from, so that I can assess data quality and completeness.

#### Acceptance Criteria

1. THE Tree_API SHALL include a Provenance object in the response
2. THE Provenance object SHALL indicate whether data came from database, cache, or live ingestion
3. WHEN some dependencies lack risk data, THE Provenance object SHALL indicate partial coverage
4. WHEN all dependencies have complete risk data, THE Provenance object SHALL indicate full coverage
5. THE Provenance object SHALL include a timestamp of when the data was last updated
6. WHEN live ingestion is used, THE Provenance object SHALL indicate which dependencies were fetched in real-time

### Requirement 10: Dependency Parser Integration [Post-MVP]

**User Story:** As a developer, I want the system to parse my manifest files correctly, so that the dependency tree reflects my actual dependencies.

#### Acceptance Criteria

1. THE Manifest_Parser SHALL support the ecosystems already supported by the existing ingestion pipeline
2. Additional ecosystems MAY be phased in incrementally
3. THE Manifest_Parser SHALL distinguish between production and development dependencies
4. WHEN a manifest file is malformed, THE Manifest_Parser SHALL return an error message indicating the parsing failure

**Note:** This requirement is marked Post-MVP if parsing infrastructure does not already exist in the ingestion pipeline. If parsing is already in place, this becomes MVP.

### Requirement 11: Dependency Resolution [Post-MVP]

**User Story:** As a user, I want transitive dependencies to be resolved accurately, so that I see the complete dependency chain.

#### Acceptance Criteria

1. WHEN a Direct_Dependency is identified, THE Dependency_Resolver SHALL fetch its manifest file
2. WHEN a manifest file is fetched, THE Dependency_Resolver SHALL parse it to identify transitive dependencies
3. THE Dependency_Resolver SHALL recursively resolve dependencies up to the configured max_depth
4. WHEN a dependency version uses a range specifier, THE Dependency_Resolver SHALL resolve dependencies using the best available version source, preferring lockfile-resolved or explicitly pinned versions when available; otherwise mark the version as inferred or unresolved
5. WHEN a dependency cannot be resolved, THE Dependency_Resolver SHALL mark it as unresolved in the Node metadata
6. THE Dependency_Resolver SHALL cache resolved dependency information to avoid redundant lookups

**Note:** This requirement is marked Post-MVP if dependency resolution is not reliable across all supported ecosystems. The weakened version criterion (AC 4) avoids misleading "latest compatible" semantics that vary across npm/Python/Maven/Go with different lockfile behaviors.

### Requirement 12: Pretty Printer for Tree Export [Post-MVP]

**User Story:** As a developer, I want to export the dependency tree in a readable format, so that I can share it with my team.

#### Acceptance Criteria

1. THE Tree_Printer SHALL format the Dependency_Tree as indented text with depth-based indentation
2. THE Tree_Printer SHALL include Node name, version, and Risk_Score in each line
3. THE Tree_Printer SHALL use visual indicators (└──, ├──) to show tree structure
4. THE Tree_Printer SHALL mark High_Risk_Node entries with a warning symbol
5. THE Tree_Printer SHALL include Summary_Metrics at the top of the output
6. THE printed output SHALL preserve enough structural information to be human-readable and auditable

**Note:** Round-trip parsing requirement removed as it is too heavy for an export feature. This is marked Post-MVP to focus on core tree visualization first.

### Requirement 13: API Response Sorting [MVP - Simplified]

**User Story:** As a user, I want to sort dependencies by risk level, so that I can focus on the most critical issues first.

#### Acceptance Criteria

1. THE Tree_API SHALL accept an optional sort_by query parameter
2. WHEN sort_by is "risk_score", THE Tree_Builder SHALL sort sibling nodes by Risk_Score descending
3. WHEN sort_by is "name", THE Tree_Builder SHALL sort sibling nodes alphabetically by name
4. WHEN sort_by is "vulnerability_count", THE Tree_Builder SHALL sort sibling nodes by Vulnerability_Count descending
5. WHEN sort_by is not provided, THE Tree_Builder SHALL use the default sort order (name, then version)
6. THE sort order SHALL apply to all levels of the tree consistently
7. WHEN sort_by is provided, truncation SHALL occur after applying that sort order
8. WHEN sort_by is absent, truncation SHALL use risk score descending for selecting which children to include, then apply deterministic default sort to the included children

### Requirement 14: Error Handling and Partial Results [MVP - Simplified]

**User Story:** As a user, I want to see partial results when some dependencies fail to load, so that I can still gain value from available data.

#### Acceptance Criteria

1. WHEN some dependencies fail to resolve, THE Tree_Builder SHALL include successfully resolved dependencies in the tree
2. WHEN a dependency resolution fails, THE Tree_Builder SHALL include a normal dependency node with resolution_status="error" and error_reason field
3. Error nodes SHALL use node_type="package" with resolution_status="error", NOT a separate node_type="error"
4. THE Tree_API SHALL return a 200 status code with partial results when at least the repository root is available
5. THE Provenance object SHALL list which dependencies encountered errors
6. WHEN all dependencies fail to resolve, THE Tree_API SHALL return a 503 status code with an error message
7. THE Tree_Builder SHALL continue processing remaining dependencies after encountering an error

**Example Error Node Schema:**
```json
{
  "id": "pkg:npm/foo@unknown",
  "node_type": "package",
  "name": "foo",
  "resolution_status": "error",
  "error_reason": "Manifest fetch failed"
}
```

### Requirement 15: Summary Metrics Accuracy [MVP]

**User Story:** As a product manager, I want accurate aggregate statistics, so that I can make data-driven decisions about dependency management.

#### Acceptance Criteria

1. FOR ALL Dependency_Tree objects, the sum of direct and transitive dependency counts SHALL equal the total node count minus one (the repository root)
2. FOR ALL Dependency_Tree objects, the High_Risk_Node count SHALL equal the number of nodes with Risk_Score above 70
3. FOR ALL Dependency_Tree objects, the vulnerable node count SHALL equal the number of nodes with Vulnerability_Count greater than zero
4. FOR ALL Dependency_Tree objects, the maximum depth SHALL equal the depth of the deepest node
5. THE riskiest branch score SHALL be greater than or equal to the Risk_Score of any individual node
6. WHEN filters are applied, THE Summary_Metrics SHALL reflect only the filtered subset of nodes
7. WHEN filters preserve ancestor paths, the treatment of preserved ancestors in filtered metrics SHALL be clearly documented (whether they count toward totals or not)

## Phase Labels Summary

### MVP Requirements
The following requirements are essential for the initial release:

- **Requirement 1**: Tree Data Model Construction
- **Requirement 2**: Risk Metadata Attachment
- **Requirement 3**: Summary Metrics Calculation
- **Requirement 4**: Tree API Endpoint
- **Requirement 5**: Depth Limiting
- **Requirement 6**: Risk-Based Filtering (with ancestor path preservation)
- **Requirement 7**: Large Tree Handling (with cached/live distinction)
- **Requirement 8**: Deterministic Tree Structure
- **Requirement 9**: Provenance Tracking
- **Requirement 13**: API Response Sorting (simplified, with sort/truncation precedence)
- **Requirement 14**: Error Handling and Partial Results (simplified, with clear error node schema)
- **Requirement 15**: Summary Metrics Accuracy (with filter clarification)

### Post-MVP Requirements
The following requirements are deferred to later phases:

- **Requirement 10**: Dependency Parser Integration (if parsing infrastructure doesn't exist)
- **Requirement 11**: Dependency Resolution (weakened to use best available version source)
- **Requirement 12**: Pretty Printer for Tree Export (simplified, no round-trip requirement)

## Notes

This requirements document focuses on the core functionality needed for the MVP. Future iterations may include cross-repository dependency graphs, maintainer relationship views, and portfolio-wide analysis. The current design intentionally duplicates shared transitive dependencies across branches for simplicity, with the understanding that a future graph-based model will deduplicate these nodes.

### Key Design Decisions

1. **Requirement 11 Weakening**: Changed from "resolve to latest compatible version" to "use best available version source" to avoid misleading semantics across different ecosystems (npm/Python/Maven/Go) with varying lockfile behaviors.

2. **Requirement 12 Simplification**: Removed round-trip parsing requirement as it's too heavy for an export feature. Focus is on human-readable output.

3. **Requirement 14 Error Schema**: Error nodes use normal package nodes with `resolution_status="error"` rather than a separate `node_type="error"` to maintain schema consistency.

4. **Requirement 7 Performance**: Clarified that 10-second target applies to cached/database-backed repositories, distinguishing from live ingestion scenarios.

5. **Requirement 6 Ancestor Paths**: Explicitly stated that ancestor nodes are preserved when filtering to maintain tree structure from root to matching nodes.

6. **Requirement 13 Sort/Truncation**: Defined precedence rules - when sort_by is provided, truncation occurs after sorting; when absent, truncation uses risk score for selection, then applies default sort to included children.
