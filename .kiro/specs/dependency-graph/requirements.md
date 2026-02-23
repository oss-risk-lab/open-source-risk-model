# Dependency Graph - Requirements Document

## Introduction

This feature adds dependency edges between repositories, transforming isolated repository graphs into a connected supply chain network. Currently, each repository graph exists in isolation - we have nodes for releases, maintainers, CVEs, etc., but no connections between different repositories. This step adds the critical "depends_on" relationships that enable true supply chain analysis.

This is Step 2 of the multi-phase evolution:
- **Step 1 (COMPLETED):** Multi-repo ingestion with persistent storage ✅
- **Step 2 (This Spec):** Add dependency edges between repos
- **Step 3 (Future):** Add transitive risk scoring and propagation

## Problem Statement

**Current State:**
- Repository graphs exist in isolation
- No visibility into what packages a repo depends on
- No way to trace supply chain relationships
- Cannot answer: "What repos depend on this package?"

**Desired State:**
- Dependency edges connect repos through package dependencies
- Can trace supply chain: Repo A → depends on → Package B → published by → Repo B
- Can query: "Show me all repos that depend on requests"
- Foundation for transitive risk analysis

## Glossary

- **Dependency**: A package that a repository requires to function (declared in requirements.txt, package.json, etc.)
- **Dependency_Edge**: Graph edge connecting a repository to a package it depends on
- **Package_Node**: Node representing a package in a registry (e.g., "requests" in PyPI)
- **Dependency_Parser**: Component that extracts dependencies from manifest files
- **Dependency_Resolution**: Process of matching package names to repository graphs
- **Transitive_Dependency**: Indirect dependency (A depends on B, B depends on C, so A transitively depends on C)
- **Dependency_Manifest**: File declaring dependencies (requirements.txt, package.json, pom.xml, etc.)

## User Stories

### US-1: Dependency Parsing
**As a** system  
**I want** to parse dependency manifests from repositories  
**So that** I can identify what packages each repo depends on

**Acceptance Criteria:**
- System parses requirements.txt (Python)
- System parses package.json (JavaScript/Node)
- System parses pom.xml (Java/Maven)
- System parses go.mod (Go)
- System extracts package names and version constraints
- System handles missing or malformed manifests gracefully

### US-2: Dependency Edges in Graph
**As a** developer  
**I want** dependency relationships represented as graph edges  
**So that** I can visualize and query supply chain connections

**Acceptance Criteria:**
- New edge type: DEPENDS_ON
- Edges connect Repository → Package nodes
- Package nodes include: name, registry, version_constraint
- Edges include: declared_version, resolved_version, is_direct
- Graph schema updated to include dependency edges

### US-3: Package-to-Repo Resolution
**As a** system  
**I want** to resolve package names to their source repositories  
**So that** I can connect repos through their dependencies

**Acceptance Criteria:**
- System matches PyPI packages to GitHub repos (via metadata)
- System matches npm packages to GitHub repos (via package.json repository field)
- System matches Maven packages to GitHub repos (via pom.xml scm)
- System handles packages without known source repos
- System stores resolution confidence score

### US-4: Dependency Graph API
**As a** API consumer  
**I want** to query dependency relationships  
**So that** I can analyze supply chain connections

**Acceptance Criteria:**
- Endpoint: GET /api/repos/{repo}/dependencies (direct dependencies)
- Endpoint: GET /api/repos/{repo}/dependents (repos that depend on this)
- Endpoint: GET /api/packages/{package}/repos (repos that publish this package)
- Endpoint: GET /api/packages/{package}/dependents (repos that depend on this package)
- Responses include dependency metadata and confidence scores

### US-5: Dependency Visualization
**As a** user  
**I want** to see dependency relationships in the graph visualization  
**So that** I can understand supply chain connections visually

**Acceptance Criteria:**
- Package nodes displayed in graph (distinct color/shape)
- Dependency edges displayed with arrows
- Clicking package node shows dependents
- Graph layout handles dependency edges
- Can toggle dependency visibility

### US-6: Transitive Dependency Discovery
**As a** analyst  
**I want** to discover transitive dependencies  
**So that** I can understand the full dependency tree

**Acceptance Criteria:**
- Endpoint: GET /api/repos/{repo}/dependencies?transitive=true
- System traverses dependency graph to depth N (configurable)
- Response includes dependency depth/distance
- System detects circular dependencies
- Performance: < 2 seconds for depth 3

## Requirements

### Requirement 1: Dependency Manifest Parsing

**User Story:** As a system, I want to parse dependency manifests, so that I can extract package dependencies from repositories.

#### Acceptance Criteria

1. THE System SHALL parse requirements.txt files (Python)
2. THE System SHALL parse package.json files (JavaScript/Node)
3. THE System SHALL parse pom.xml files (Java/Maven)
4. THE System SHALL parse go.mod files (Go)
5. WHEN parsing a manifest, THE System SHALL extract package names and version constraints
6. WHEN a manifest is missing or malformed, THE System SHALL log a warning and continue
7. THE System SHALL support common version constraint formats (==, >=, ~=, ^, etc.)

### Requirement 2: Dependency Graph Schema

**User Story:** As a developer, I want dependency relationships in the graph schema, so that I can represent supply chain connections.

#### Acceptance Criteria

1. THE System SHALL add a new node type: PACKAGE
2. THE System SHALL add a new edge type: DEPENDS_ON
3. PACKAGE nodes SHALL include: name, registry_type, version_constraint, resolved_version
4. DEPENDS_ON edges SHALL include: declared_version, is_direct, confidence
5. WHEN building a graph, THE System SHALL include dependency nodes and edges
6. THE System SHALL preserve backward compatibility with existing graph schema

### Requirement 3: Package-to-Repository Resolution

**User Story:** As a system, I want to resolve package names to repositories, so that I can connect repos through dependencies.

#### Acceptance Criteria

1. THE System SHALL resolve PyPI package names to GitHub repositories using PyPI metadata
2. THE System SHALL resolve npm package names to GitHub repositories using package.json repository field
3. THE System SHALL resolve Maven packages to GitHub repositories using pom.xml scm
4. WHEN a package cannot be resolved, THE System SHALL create an unresolved package node
5. THE System SHALL store resolution confidence (0.0-1.0)
6. THE System SHALL cache package-to-repo mappings in the database

### Requirement 4: Dependency Query API

**User Story:** As an API consumer, I want to query dependency relationships, so that I can analyze supply chain connections.

#### Acceptance Criteria

1. THE System SHALL provide GET /api/repos/{repo}/dependencies endpoint
2. THE System SHALL provide GET /api/repos/{repo}/dependents endpoint
3. THE System SHALL provide GET /api/packages/{package}/repos endpoint
4. THE System SHALL provide GET /api/packages/{package}/dependents endpoint
5. WHEN querying dependencies, THE System SHALL support transitive=true parameter
6. WHEN querying dependencies, THE System SHALL support max_depth parameter (default: 1)
7. THE System SHALL return dependency metadata including version constraints and confidence

### Requirement 5: Dependency Database Storage

**User Story:** As a system architect, I want dependency data persisted, so that I can query relationships efficiently.

#### Acceptance Criteria

1. THE System SHALL store package nodes in the database
2. THE System SHALL store dependency edges in the database
3. THE System SHALL create indexes for efficient dependency queries
4. THE System SHALL support querying by package name
5. THE System SHALL support querying by repository
6. THE System SHALL update dependency data when re-ingesting a repository

### Requirement 6: Dependency Ingestion

**User Story:** As a data engineer, I want dependencies ingested automatically, so that I don't need manual intervention.

#### Acceptance Criteria

1. WHEN ingesting a repository, THE System SHALL automatically parse dependency manifests
2. WHEN ingesting a repository, THE System SHALL resolve package names to repos
3. WHEN ingesting a repository, THE System SHALL create dependency edges
4. WHEN a dependency resolution fails, THE System SHALL log the failure and continue
5. THE System SHALL support disabling dependency ingestion via configuration

### Requirement 7: Circular Dependency Detection

**User Story:** As an analyst, I want to detect circular dependencies, so that I can identify problematic dependency chains.

#### Acceptance Criteria

1. WHEN querying transitive dependencies, THE System SHALL detect circular dependencies
2. WHEN a circular dependency is detected, THE System SHALL include it in the response
3. THE System SHALL mark circular dependencies with a flag
4. THE System SHALL limit traversal depth to prevent infinite loops

### Requirement 8: Dependency Confidence Scoring

**User Story:** As an analyst, I want confidence scores for dependencies, so that I can assess data quality.

#### Acceptance Criteria

1. THE System SHALL assign confidence scores to package-to-repo resolutions
2. THE System SHALL assign confidence scores to dependency edges
3. Confidence scores SHALL range from 0.0 (low) to 1.0 (high)
4. THE System SHALL document confidence scoring methodology
5. WHEN displaying dependencies, THE System SHALL include confidence scores

## Non-Functional Requirements

### Performance

- Dependency parsing: < 2 seconds per repository
- Package resolution: < 500ms per package (with caching)
- Transitive dependency query (depth 3): < 2 seconds
- Dependency ingestion: < 5 seconds additional overhead per repo

### Scalability

- Support repositories with 100+ direct dependencies
- Support transitive queries to depth 5
- Handle 10,000+ package-to-repo mappings
- Efficient indexes for dependency queries

### Reliability

- Graceful handling of missing manifests
- Graceful handling of unresolvable packages
- No failures due to malformed manifests
- Transactional updates for dependency data

### Maintainability

- Pluggable parsers for new ecosystems
- Clear separation between parsing and resolution
- Comprehensive logging for debugging
- Well-documented confidence scoring

## Out of Scope (Future Versions)

- Transitive risk scoring (Step 3)
- Risk propagation analysis (Step 3)
- Dependency version conflict detection
- Automated dependency updates
- Security advisory matching to dependencies
- License compatibility analysis
- Dependency graph optimization recommendations

## Technical Constraints

- Must work with existing graph schema (backward compatible)
- Must use existing database (SQLite)
- Must not break existing API endpoints
- Must handle rate limits for package registry APIs
- Dependency parsing must be fast (no external API calls during parsing)

## Success Metrics

- Successfully parse dependencies for 90%+ of repositories
- Resolve 70%+ of packages to source repositories
- Dependency queries return in < 500ms
- Transitive queries (depth 3) return in < 2 seconds
- Zero failures due to dependency parsing errors

## Dependencies

- Existing: Graph schema, GraphBuilder, GraphRepository
- Existing: Package registry detection (from Step 1)
- New: Dependency manifest parsers (requirements.txt, package.json, etc.)
- New: Package-to-repo resolution service
- New: Dependency query endpoints

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Package resolution accuracy | High | Use multiple data sources, confidence scores |
| API rate limits for package registries | Medium | Cache aggressively, batch requests |
| Circular dependencies cause infinite loops | High | Depth limits, cycle detection |
| Dependency parsing errors break ingestion | Medium | Graceful error handling, continue on failure |
| Performance degradation with large graphs | Medium | Efficient indexes, query optimization |

## Open Questions

1. Should we support all ecosystems or start with Python/JavaScript? (Recommendation: Start with Python, add others incrementally)
2. How should we handle version ranges (e.g., ">=1.0,<2.0")? (Recommendation: Store as-is, resolve to latest compatible)
3. Should we fetch transitive dependencies from package registries? (Recommendation: No, only parse direct dependencies from manifests)
4. How deep should transitive queries go by default? (Recommendation: depth=1 default, max=5)
5. Should we support private package registries? (Recommendation: Not in Step 2, add in future)

## Next Steps

1. Review and approve requirements
2. Create design document with:
   - Dependency parser architecture
   - Package resolution strategy
   - Database schema updates
   - API endpoint specifications
   - Graph schema updates
3. Break into implementation tasks
4. Implement incrementally with testing
