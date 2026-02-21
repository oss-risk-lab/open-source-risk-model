# Multi-Repo Persistent Graph - Requirements Document

## Introduction

This feature evolves the current single-repo supply chain graph system into a multi-repo persistent graph storage system. The current system generates graphs dynamically for individual repositories on demand, with data living in memory and disappearing after each request. This intermediate step introduces batch ingestion of multiple repositories with persistent storage, laying the foundation for a future global supply chain knowledge graph with risk propagation analysis.

This is Step 1 of a multi-phase evolution:
- **Step 1 (This Spec):** Multi-repo ingestion with persistent storage
- **Step 2 (Future):** Add dependency edges between repos
- **Step 3 (Future):** Add transitive risk scoring and propagation

## Glossary

- **Repository_Graph**: The complete supply chain graph for a single repository, including nodes (repo, releases, maintainers, CVEs, registries, risk factors) and edges representing relationships
- **Graph_Database**: Persistent storage system for graph data across multiple repositories
- **Ingestion_Job**: Background process that fetches repository data and stores it in the Graph_Database
- **Batch_Ingestion**: Process of ingesting multiple repositories in a single operation
- **Cross_Repo_Query**: Query that spans data from multiple repositories
- **Graph_Schema**: The structure definition for nodes and edges (already defined in current system)
- **Persistence_Layer**: The database and storage infrastructure for graph data
- **Migration_Path**: Strategy for transitioning from in-memory to persistent storage

## Requirements

### Requirement 1: Persistent Graph Storage

**User Story:** As a system architect, I want graph data to persist across requests, so that I can build a knowledge base of supply chain relationships without regenerating data on every query.

#### Acceptance Criteria

1. WHEN a repository graph is generated, THE System SHALL store it in the Graph_Database
2. WHEN querying for a stored repository graph, THE System SHALL retrieve it from the Graph_Database without regenerating
3. WHEN the Graph_Database is restarted, THE System SHALL retain all previously stored graph data
4. THE System SHALL store node data including id, type, label, metadata, and provenance
5. THE System SHALL store edge data including source, target, relationship_type, metadata, and provenance
6. WHEN storing a graph, THE System SHALL preserve the complete graph schema including all node types (repo, release, maintainer, cve, registry, risk_factor) and edge types

### Requirement 2: Batch Repository Ingestion

**User Story:** As a data engineer, I want to ingest multiple repositories in batch, so that I can populate the graph database efficiently without manual per-repo operations.

#### Acceptance Criteria

1. WHEN provided with a list of repository identifiers, THE System SHALL ingest all repositories in the list
2. WHEN ingesting a batch of repositories, THE System SHALL process them concurrently to minimize total time
3. WHEN a single repository fails during batch ingestion, THE System SHALL continue processing remaining repositories
4. WHEN batch ingestion completes, THE System SHALL report success count, failure count, and error details
5. THE System SHALL support batch sizes of at least 100 repositories
6. WHEN ingesting a repository that already exists, THE System SHALL update the existing data rather than creating duplicates

### Requirement 3: Background Job Processing

**User Story:** As an API consumer, I want ingestion to happen in the background, so that I can submit ingestion requests without blocking on long-running operations.

#### Acceptance Criteria

1. WHEN an ingestion request is submitted, THE System SHALL return immediately with a job identifier
2. WHEN an ingestion job is running, THE System SHALL allow querying job status (pending, running, completed, failed)
3. WHEN an ingestion job completes, THE System SHALL persist the completion status and results
4. WHEN querying job status, THE System SHALL return progress information (repositories processed, remaining, errors)
5. THE System SHALL support multiple concurrent ingestion jobs
6. WHEN the server restarts, THE System SHALL persist job status and results (jobs may be marked 'interrupted' and must be re-submitted rather than automatically resumed)

### Requirement 4: Multi-Repo Query API

**User Story:** As an API consumer, I want to query graph data across multiple repositories, so that I can analyze supply chain relationships at scale.

#### Acceptance Criteria

1. WHEN querying for multiple repositories, THE System SHALL return graph data for all requested repositories
2. WHEN querying with filters (e.g., by maintainer, by CVE, by registry), THE System SHALL return only matching repositories
3. WHEN querying for repositories, THE System SHALL return metadata including last_updated timestamp and data_confidence
4. THE System SHALL support pagination for large result sets
5. WHEN a requested repository is not in the database, THE System SHALL indicate which repositories are missing

### Requirement 5: Database Technology Selection

**User Story:** As a system architect, I want to choose an appropriate database technology, so that the system is maintainable, scalable, and pragmatic for the current scope.

#### Acceptance Criteria

1. THE System SHALL use a database technology that supports storing and querying graph-shaped data efficiently (nodes and edges)
2. THE System SHALL use a database that can be embedded or run locally without complex infrastructure
3. THE System SHALL use a database with Python client libraries
4. THE System SHALL support storing at least 1000 repositories with their complete graphs
5. THE System SHALL support querying by node properties via indexed lookups (e.g., find all repos with a specific CVE)

### Requirement 6: Backward Compatibility

**User Story:** As an API consumer, I want the existing single-repo API to continue working, so that current integrations are not broken.

#### Acceptance Criteria

1. WHEN calling the existing `/api/graph` endpoint, THE System SHALL return graph data in the same format as before
2. WHEN the requested repository is in the database, THE System SHALL return cached data
3. WHEN the requested repository is not in the database, THE System SHALL generate the graph dynamically as before
4. THE System SHALL maintain the same response schema for the `/api/graph` endpoint
5. WHEN using the `refresh=true` parameter, THE System SHALL regenerate the graph and update the database

### Requirement 7: Data Freshness Management

**User Story:** As a data engineer, I want to manage data freshness, so that stale data can be identified and refreshed.

#### Acceptance Criteria

1. WHEN storing a graph, THE System SHALL record the ingestion timestamp
2. WHEN querying for repositories, THE System SHALL return the last_updated timestamp for each repository
3. THE System SHALL support querying for repositories older than a specified age
4. WHEN re-ingesting a repository, THE System SHALL update the timestamp
5. THE System SHALL support configurable TTL (time-to-live) for cached graph data

### Requirement 8: Ingestion API Endpoints

**User Story:** As a developer, I want API endpoints for ingestion operations, so that I can programmatically populate and manage the graph database.

#### Acceptance Criteria

1. THE System SHALL provide an endpoint to submit batch ingestion jobs
2. THE System SHALL provide an endpoint to query job status by job identifier
3. THE System SHALL provide an endpoint to list all ingestion jobs with filtering by status
4. THE System SHALL provide an endpoint to query repository metadata (last_updated, node_count, edge_count)
5. THE System SHALL provide an endpoint to delete repository data from the database

### Requirement 9: Error Handling and Resilience

**User Story:** As a system operator, I want robust error handling, so that partial failures don't corrupt the database or crash the system.

#### Acceptance Criteria

1. WHEN a repository ingestion fails, THE System SHALL log the error with context (repo, error message, timestamp)
2. WHEN a database write fails, THE System SHALL roll back the transaction for that repository
3. WHEN the database is unavailable, THE System SHALL fall back to dynamic graph generation
4. WHEN an ingestion job encounters errors, THE System SHALL continue processing and report all errors at completion
5. THE System SHALL validate graph data before storing to prevent invalid data in the database

### Requirement 10: Cross-Repo Exploration (Index-Based)

**User Story:** As an analyst, I want to explore relationships across repositories using indexed lookups, so that I can identify shared maintainers, common vulnerabilities, and ecosystem patterns without complex graph traversal.

#### Acceptance Criteria

1. WHEN querying by maintainer username, THE System SHALL return all repositories maintained by that user via indexed lookup
2. WHEN querying by CVE identifier, THE System SHALL return all repositories affected by that vulnerability via indexed lookup
3. WHEN querying by registry and package name, THE System SHALL return the associated repository via indexed lookup
4. THE System SHALL support querying for repositories sharing the same maintainer via indexed lookup
5. THE System SHALL return results with provenance and confidence metadata
6. THE System SHALL NOT perform multi-hop graph traversal or complex graph analytics (reserved for future steps)

## Non-Functional Requirements

### Performance

- Batch ingestion: Process 100 repositories in under 30 minutes (average 18 seconds per repo)
- Single repo query: Database fetch + serialization < 150ms for single repository graph
- Multi-repo query: < 500ms for up to 50 repositories
- Database startup: < 5 seconds

### Scalability

- Support storing 1000+ repositories initially
- Design for future scale to 10,000+ repositories
- Support concurrent ingestion jobs (at least 3 simultaneous jobs)
- Handle graphs with up to 200 nodes per repository

### Reliability

- Database writes are transactional (all-or-nothing per repository)
- Graceful degradation when database is unavailable (fall back to dynamic generation)
- No data loss on system restart
- Ingestion job state persisted across restarts

### Maintainability

- Clear separation between persistence layer and graph building logic
- Database schema versioning for future migrations
- Comprehensive logging for debugging ingestion issues
- Database can be backed up and restored

## Out of Scope (Future Versions)

- Dependency edges between repositories (Step 2)
- Transitive risk scoring and propagation (Step 3)
- Real-time graph updates via webhooks
- Distributed database deployment
- Graph query language (e.g., Cypher, Gremlin)
- Full-text search across graph data
- Graph analytics (centrality, clustering, etc.)
- Multi-tenancy and access control
- Historical graph snapshots and versioning

## Technical Constraints

- Must work with Python 3.10+ (modern typing and tooling support)
- Must not break existing `/api/score` and `/api/graph` endpoints
- Must use existing GitHub token authentication
- Must reuse existing graph schema and builder logic
- Database should be embeddable or simple to deploy (avoid complex infrastructure)
- Must support local development without external services
- Graph storage strategy: Store complete graph as JSON blob per repository with separate index tables for cross-repo lookups (maintainers, CVEs, registries)
- Repository identity: `repo_full_name` (owner/repo) is the primary key; updates overwrite existing data

## Success Metrics

- Successfully ingest and store 100+ repositories
- Query response time < 50ms for cached repository graphs
- Batch ingestion completes without system crashes
- Zero data corruption or loss during ingestion
- Existing API endpoints continue to work without modification
- Cross-repo queries return results in < 500ms

## Database Technology Recommendation

Based on the requirements, the recommended database options are:

1. **SQLite with JSON columns** (Simplest)
   - Pros: Zero configuration, embedded, excellent Python support, sufficient for 1000s of repos
   - Cons: Limited concurrent writes, no native graph queries
   - Best for: MVP, local development, simple deployment

2. **PostgreSQL with JSONB** (Balanced)
   - Pros: Robust, excellent JSON support, good performance, widely known
   - Cons: Requires separate database server
   - Best for: Production deployment, team familiarity

3. **Neo4j** (Most powerful)
   - Pros: Native graph database, powerful query language (Cypher), excellent for graph analytics
   - Cons: More complex setup, heavier resource usage, learning curve
   - Best for: Future scale, complex graph queries

**Recommendation for Step 1:** Start with SQLite for simplicity and speed. The persistence layer should be abstracted so we can migrate to PostgreSQL or Neo4j in future steps without rewriting application logic.

## Dependencies

- Existing: Graph schema, GraphBuilder, GitHub client, CVE fetcher, registry detector
- New: Database client library (sqlite3 built-in for SQLite, psycopg2 for PostgreSQL, or neo4j for Neo4j)
- New: Background job system (database-backed job table + polling worker, no external queue required)
- New: Database migration tooling (Alembic for SQL databases)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Database choice limits future scale | High | Abstract persistence layer, design for migration |
| Batch ingestion overwhelms GitHub API rate limits | High | Implement rate limiting, respect GitHub quotas |
| Database corruption from concurrent writes | Medium | Use transactions, implement locking |
| Ingestion jobs consume too much memory | Medium | Process repos sequentially within jobs, limit concurrent jobs |
| Migration from in-memory breaks existing code | High | Maintain backward compatibility, comprehensive testing |

## Open Questions

1. Should we use SQLite, PostgreSQL, or Neo4j? (Recommendation: SQLite for Step 1)
2. How should we handle GitHub API rate limits during batch ingestion? (Recommendation: Respect rate limits, add delays between requests)
3. Should ingestion jobs be persistent across server restarts? (Recommendation: Yes, store job state in database)
4. What should be the default TTL for cached graph data? (Recommendation: 24 hours, configurable)
5. Should we support incremental updates (only changed data) or full re-ingestion? (Recommendation: Full re-ingestion for Step 1, incremental in future)

## Next Steps

1. Review and approve requirements
2. Create design document with:
   - Database schema design
   - Persistence layer architecture
   - Ingestion job system design
   - API endpoint specifications
   - Migration strategy from in-memory to persistent storage
3. Break into implementation tasks
4. Implement incrementally with testing
