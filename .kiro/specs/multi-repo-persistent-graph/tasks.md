# Implementation Plan: Multi-Repo Persistent Graph

## Overview

This implementation plan evolves the single-repo supply chain graph system into a multi-repo persistent graph storage system. The approach follows a phased strategy: (1) Add persistence layer with backward compatibility, (2) Add batch ingestion system, (3) Add cross-repo query endpoints, (4) Production hardening.

## Tasks

- [x] 1. Phase 0: Environment and Configuration Setup
  - Add `data/graphs.db` to `.gitignore`
  - Add environment variable support to configuration
  - Create `src/open_source_risk_model/persistence/` directory structure
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 2. Phase 1: Database Schema and Core Persistence Layer
  - [x] 2.1 Create database initialization module
    - Create `src/open_source_risk_model/persistence/db.py`
    - Implement database connection with SQLite pragmas (WAL, busy_timeout)
    - Implement schema creation with all tables (repo_graphs, ingestion_jobs, indexes, schema_version)
    - Add schema version tracking with INSERT OR IGNORE
    - _Requirements: 1.3, 5.1, 5.2_
  
  - [x] 2.2 Create custom exception classes
    - Create `src/open_source_risk_model/persistence/errors.py`
    - Define DatabaseError, ValidationError, and other persistence exceptions
    - _Requirements: 9.1, 9.2_
  
  - [x] 2.3 Implement GraphRepository
    - Create `src/open_source_risk_model/persistence/graph_repo.py`
    - Implement `save_graph()` with transaction support and validation
    - Implement `_update_indexes()` with node_by_id dict for O(1) lookups
    - Implement `get_graph()` returning exact /api/graph format
    - Implement `delete_graph()` with cascade deletion
    - Implement `list_repos()` with pagination and filtering
    - Implement `get_repo_count()`
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 7.1, 7.2, 8.4, 8.5_
  
  - [x] 2.4 Write property test for GraphRepository
    - **Property 1: Graph Storage Round-Trip**
    - **Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.6**
  
  - [x] 2.5 Write property test for database persistence
    - **Property 2: Database Persistence Across Restarts**
    - **Validates: Requirements 1.3**
  
  - [x] 2.6 Write property test for update idempotency
    - **Property 3: Update Idempotency**
    - **Validates: Requirements 2.6, 7.4**
  
  - [x] 2.7 Write unit tests for GraphRepository
    - Test transaction rollback on errors
    - Test cascade deletion
    - Test pagination
    - Test age-based filtering
    - _Requirements: 9.2, 8.5_

- [x] 3. Checkpoint - Verify persistence layer works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Phase 2: Enhance /api/graph Endpoint with Database Caching
  - [x] 4.1 Initialize GraphRepository in FastAPI startup
    - Add database initialization to `api/app.py` startup event
    - Add environment variable checks (GRAPH_DB_ENABLED)
    - Add startup hook to mark interrupted jobs
    - _Requirements: 6.1, 6.2_
  
  - [x] 4.2 Update /api/graph endpoint to use database
    - Modify existing `/api/graph` endpoint to check database first
    - Implement TTL logic with GRAPH_AUTO_REFRESH_STALE support
    - Implement fallback to dynamic generation on database errors
    - Implement best-effort save after dynamic generation
    - Ensure response format matches exactly (cache_hit, is_stale flags)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.5, 9.3_
  
  - [x] 4.3 Write property test for API backward compatibility
    - **Property 13: API Response Schema Compatibility**
    - **Validates: Requirements 6.1, 6.4**
  
  - [x] 4.4 Write property test for cache behavior
    - **Property 14: Cache Behavior Correctness**
    - **Validates: Requirements 6.2, 6.5**
  
  - [x] 4.5 Write property test for fallback behavior
    - **Property 15: Fallback to Dynamic Generation**
    - **Validates: Requirements 6.3, 9.3**
  
  - [x] 4.6 Write unit tests for /api/graph endpoint
    - Test cache hit path
    - Test cache miss path
    - Test refresh=true forces regeneration
    - Test TTL expiration with auto_refresh_stale=false
    - Test TTL expiration with auto_refresh_stale=true
    - Test database unavailable fallback
    - _Requirements: 6.2, 6.3, 6.5, 7.5, 9.3_

- [x] 5. Checkpoint - Verify backward compatibility
  - Ensure all existing tests still pass, ask the user if questions arise.

- [x] 6. Phase 3: Job Management System
  - [x] 6.1 Implement JobRepository
    - Create `src/open_source_risk_model/persistence/job_repo.py`
    - Implement `create_job()` with UUID generation
    - Implement `get_job()` for status queries
    - Implement `update_job_status()` for progress tracking
    - Implement `list_jobs()` with status filtering and pagination
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 8.2, 8.3_
  
  - [x] 6.2 Write property test for job state persistence
    - **Property 7: Job State Persistence**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.6**
  
  - [x] 6.3 Write unit tests for JobRepository
    - Test job creation
    - Test status updates
    - Test progress tracking
    - Test filtering by status
    - _Requirements: 3.2, 3.3, 3.4_
  
  - [x] 6.4 Implement IngestionWorker
    - Create `src/open_source_risk_model/persistence/worker.py`
    - Implement polling loop with configurable interval
    - Implement `_process_job()` with per-repo error handling
    - Implement `_ingest_repository()` (verify import paths for score_repo and build_graph)
    - Implement progress updates every 10 repos
    - Implement graceful shutdown
    - _Requirements: 2.1, 2.3, 2.4, 3.1, 9.1, 9.4_
  
  - [x] 6.5 Write property test for batch completeness
    - **Property 4: Batch Completeness**
    - **Validates: Requirements 2.1, 2.4**
  
  - [x] 6.6 Write property test for ingestion resilience
    - **Property 5: Ingestion Resilience**
    - **Validates: Requirements 2.3, 9.4**
  
  - [x] 6.7 Write property test for transaction atomicity
    - **Property 6: Transaction Atomicity**
    - **Validates: Requirements 9.2**
  
  - [x] 6.8 Write unit tests for IngestionWorker
    - Test job pickup from queue
    - Test per-repo error handling
    - Test progress updates
    - Test job completion with mixed success/failure
    - Test graceful shutdown
    - _Requirements: 2.3, 3.4, 9.4_
  
  - [x] 6.9 Add worker startup to FastAPI
    - Add worker initialization to `api/app.py` startup event
    - Add worker shutdown to shutdown event
    - Add environment variable check (GRAPH_WORKER_ENABLED)
    - _Requirements: 3.1, 3.5_

- [x] 7. Phase 4: Ingestion API Endpoints
  - [x] 7.1 Implement POST /api/ingest endpoint
    - Create endpoint to submit batch ingestion jobs
    - Validate request (non-empty repo list, max 1000 repos)
    - Create job via JobRepository
    - Return 202 Accepted with job_id
    - _Requirements: 2.5, 3.1, 8.1_
  
  - [x] 7.2 Implement GET /api/jobs/{job_id} endpoint
    - Create endpoint to query job status
    - Return job details including progress and errors
    - Return 404 if job not found
    - _Requirements: 3.2, 3.4, 8.2_
  
  - [x] 7.3 Implement GET /api/jobs endpoint
    - Create endpoint to list jobs with optional status filter
    - Support pagination (limit, offset)
    - _Requirements: 8.3_
  
  - [x] 7.4 Write property test for async job creation
    - **Property 8: Async Job Creation**
    - **Validates: Requirements 3.1**
  
  - [x] 7.5 Write integration tests for ingestion endpoints
    - Test job creation returns quickly
    - Test job status tracking
    - Test job list filtering
    - Test batch ingestion with 10 repos
    - Test error reporting for invalid repos
    - _Requirements: 2.1, 2.3, 2.4, 3.1, 3.2, 3.4_

- [x] 8. Checkpoint - Verify ingestion system works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Phase 5: Cross-Repo Query System
  - [x] 9.1 Implement IndexRepository
    - Create `src/open_source_risk_model/persistence/index_repo.py`
    - Implement `find_repos_by_maintainer()`
    - Implement `find_repos_by_cve()`
    - Implement `find_repo_by_package()`
    - Implement `find_repos_sharing_maintainer()`
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  
  - [x] 9.2 Write property test for multi-repo query completeness
    - **Property 9: Multi-Repo Query Completeness**
    - **Validates: Requirements 4.1, 4.5**
  
  - [x] 9.3 Write property test for query pagination
    - **Property 10: Query Pagination Consistency**
    - **Validates: Requirements 4.4**
  
  - [x] 9.4 Write property test for filter correctness
    - **Property 11: Filter Correctness**
    - **Validates: Requirements 4.2, 7.3, 10.1, 10.2, 10.3, 10.4**
  
  - [x] 9.5 Write property test for index consistency
    - **Property 12: Index-Based Lookup Consistency**
    - **Validates: Requirements 5.5, 10.1, 10.2, 10.3**
  
  - [x] 9.6 Write unit tests for IndexRepository
    - Test maintainer queries
    - Test CVE queries
    - Test package queries
    - Test shared maintainer queries
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 10. Phase 6: Cross-Repo Query API Endpoints
  - [x] 10.1 Implement GET /api/repos endpoint
    - Create endpoint to list stored repositories
    - Support pagination (limit, offset)
    - Support filtering by age (older_than parameter)
    - Return repository metadata (node_count, updated_at, etc.)
    - _Requirements: 4.1, 4.3, 4.4, 7.2, 7.3, 8.4_
  
  - [x] 10.2 Implement GET /api/repos/by-maintainer/{username} endpoint
    - Create endpoint to find repos by maintainer
    - Return repos with contribution details
    - Include provenance and confidence metadata
    - _Requirements: 10.1, 10.5_
  
  - [x] 10.3 Implement GET /api/repos/by-cve/{cve_id} endpoint
    - Create endpoint to find repos by CVE
    - Return repos with severity and affected releases
    - Include provenance and confidence metadata
    - _Requirements: 10.2, 10.5_
  
  - [x] 10.4 Implement GET /api/repos/by-package endpoint
    - Create endpoint to find repo by package name
    - Support query parameters: registry, package
    - Include provenance and confidence metadata
    - _Requirements: 10.3, 10.5_
  
  - [x] 10.5 Implement DELETE /api/repos/{repo_full_name} endpoint
    - Create endpoint to delete repository data
    - Return 204 No Content on success
    - Return 404 if repo not found
    - _Requirements: 8.5_
  
  - [x] 10.6 Write property test for metadata completeness
    - **Property 17: Metadata Completeness**
    - **Validates: Requirements 4.3, 7.2, 10.5**
  
  - [x] 10.7 Write property test for cascade deletion
    - **Property 19: Cascade Deletion Completeness**
    - **Validates: Requirements 8.5**
  
  - [x] 10.8 Write integration tests for cross-repo endpoints
    - Test /api/repos with pagination
    - Test /api/repos with age filtering
    - Test /api/repos/by-maintainer
    - Test /api/repos/by-cve
    - Test /api/repos/by-package
    - Test DELETE /api/repos/{repo}
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 7.3, 8.5, 10.1, 10.2, 10.3_

- [x] 11. Checkpoint - Verify cross-repo queries work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Phase 7: Data Quality and Validation
  - [x] 12.1 Add graph validation before storage
    - Enhance `save_graph()` to validate graph structure
    - Check for required fields, valid references, unique IDs
    - Raise ValidationError for invalid graphs
    - _Requirements: 9.5_
  
  - [x] 12.2 Write property test for graph validation
    - **Property 16: Graph Validation Before Storage**
    - **Validates: Requirements 9.5**
  
  - [x] 12.3 Write property test for TTL enforcement
    - **Property 18: TTL Enforcement**
    - **Validates: Requirements 7.5**
  
  - [x] 12.4 Write unit tests for validation
    - Test invalid graph rejection (missing fields)
    - Test invalid graph rejection (orphaned edges)
    - Test invalid graph rejection (duplicate IDs)
    - Test invalid graph rejection (multiple repo nodes)
    - _Requirements: 9.5_

- [x] 13. Phase 8: End-to-End Integration Testing
  - [x] 13.1 Write end-to-end integration test: Full ingestion cycle
    - Submit batch job with 10 repos
    - Wait for completion
    - Verify all repos in database
    - Query via /api/graph
    - Verify response format
    - _Requirements: 2.1, 2.4, 6.1, 6.2_
  
  - [x] 13.2 Write end-to-end integration test: Cache hit/miss behavior
    - Query repo not in database (miss)
    - Query same repo again (hit)
    - Query with refresh=true (regenerate)
    - Verify database updated
    - _Requirements: 6.2, 6.3, 6.5_
  
  - [x] 13.3 Write end-to-end integration test: Cross-repo exploration
    - Ingest repos with shared maintainers
    - Query by maintainer
    - Verify all repos returned
    - Verify index consistency
    - _Requirements: 10.1, 10.4_
  
  - [x] 13.4 Write end-to-end integration test: Error recovery
    - Submit job with mix of valid and invalid repos
    - Verify job completes
    - Verify valid repos processed
    - Verify errors reported
    - _Requirements: 2.3, 9.4_
  
  - [x] 13.5 Write end-to-end integration test: Server restart handling
    - Create running job
    - Simulate restart (mark jobs interrupted)
    - Verify job marked interrupted
    - Verify database intact
    - _Requirements: 3.6_

- [x] 14. Phase 9: Documentation and Deployment
  - [x] 14.1 Update API documentation
    - Document new endpoints in docs/API.md
    - Add examples for ingestion endpoints
    - Add examples for cross-repo query endpoints
    - Document environment variables
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [x] 14.2 Create deployment guide
    - Document database setup
    - Document environment configuration
    - Document backup/restore procedures
    - Document monitoring recommendations
    - _Requirements: 1.3_
  
  - [x] 14.3 Add database maintenance utilities
    - Create script to backup database
    - Create script to restore database
    - Create script to clean up stale data
    - Create script to rebuild indexes
    - _Requirements: 7.3_

- [x] 15. Final checkpoint - Verify complete system
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property-based and integration tests that can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation throughout implementation
- Property tests validate universal correctness properties with minimum 100 iterations
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end workflows
- The phased approach ensures backward compatibility is maintained throughout
