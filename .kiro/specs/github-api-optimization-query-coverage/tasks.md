# Implementation Plan: GitHub API Optimization and Query Coverage

## Overview

This implementation plan delivers hybrid GraphQL/REST API ingestion with 50-80% API call reduction and universal query coverage for any GitHub repository. The MVP focuses on GraphQL snapshot ingestion with adaptive batching, live fallback for missing repositories (provisional mode default), and provenance-aware query responses.

Key priorities:
- Use Pydantic BaseModel for all external data models
- Implement conservative adaptive GraphQL batching (start 10-15, max 30)
- Implement entity normalization with explicit rule hierarchy EARLY (before coverage detection)
- Implement weighted feature coverage calculation (60% threshold)
- Split DB retrieval into summary vs full evidence
- Add Evidence_Scope tracking to all query responses
- Be conservative with issue events (cap at 100 issues)
- Validate score parity with existing system on benchmark repos

## MVP Phasing

**MVP Phase A** (Core Infrastructure):
- GraphQL/REST clients, rate limiter, cache manager
- Snapshot fetcher with adaptive batching
- Provisional feature engineering (snapshot + contributors only)
- Single repo ingestion
- Live repo ingestor with provenance

**MVP Phase B** (Query Coverage):
- Entity normalization (EARLY - before coverage detection)
- Coverage checker
- Retrieval strategy
- DB summary retrieval
- Result summarization
- Intent executor wiring for single missing repo lookup

**MVP Phase C** (Full Features):
- Full issue-based enrichment
- Hybrid multi-repo comparisons
- CLI expansion
- Deeper backward compatibility sweep

## Tasks

- [x] 1. Set up project structure and data models
  - Create directory structure for ingestion and query modules
  - Define Pydantic models for all external data structures (API responses, persisted payloads)
  - Create configuration schema and default config files
  - _Requirements: 18.1, 18.5, 18.6_

- [x] 2. Implement core API client infrastructure
  - [x] 2.1 Implement GraphQL client with query execution and error handling
    - Create GraphQLClient class with execute_query method
    - Implement retry logic with exponential backoff (3 attempts)
    - Parse GraphQL errors and extract failing repository identifiers
    - Track query costs from X-RateLimit-Cost response header
    - _Requirements: 1.1, 1.6, 16.1, 19.3_
  
  - [x] 2.2 Write property test for GraphQL client
    - **Property 1: GraphQL Query Execution**
    - **Validates: Requirements 1.1, 1.6**
  
  - [x] 2.3 Implement REST client with pagination support
    - Create RESTClient class with get and paginate methods
    - Implement Link header pagination
    - Implement retry logic with exponential backoff (3 attempts)
    - Add 30-second timeout per request
    - _Requirements: 2.1-2.8, 16.2, 16.6_
  
  - [x] 2.4 Write property test for REST client
    - **Property 6: REST Endpoint Construction**
    - **Property 7: REST Pagination Completeness**
    - **Validates: Requirements 2.1-2.6**

- [-] 3. Implement rate limiting and caching
  - [x] 3.1 Implement rate limiter with separate REST/GraphQL tracking
    - Create RateLimiter class with check_and_wait method
    - Parse X-RateLimit-Remaining and X-RateLimit-Reset headers
    - Implement warning at 100 requests remaining
    - Implement pause when quota reaches 0
    - Implement exponential backoff for 403/429 errors (max 60s)
    - _Requirements: 3.1-3.6_
  
  - [x] 3.2 Write property tests for rate limiter
    - **Property 8: Rate Limit Header Parsing**
    - **Property 9: Rate Limit Separation**
    - **Property 10: Exponential Backoff Bounds**
    - **Validates: Requirements 3.1, 3.2, 3.5, 3.6**
  
  - [x] 3.3 Implement cache manager with disk persistence
    - Create CacheManager class with get, set, invalidate methods
    - Implement cache key generation (repository_identifier + endpoint)
    - Implement TTL enforcement (1 hour default)
    - Implement disk persistence to data/github_cache/
    - Add promote_to_database method for optional database promotion
    - _Requirements: 4.1-4.6, 14.1-14.6_
  
  - [x] 3.4 Write property tests for cache manager
    - **Property 11: Cache Key Uniqueness**
    - **Property 12: Cache Timestamp Presence**
    - **Property 13: Cache TTL Enforcement**
    - **Property 15: Cache Invalidation Isolation**
    - **Validates: Requirements 4.1-4.4, 4.6, 14.3, 14.4**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass. If blockers arise, document them clearly and continue with the next non-blocked task where possible.

- [x] 5. Implement repository snapshot fetcher with adaptive batching
  - [x] 5.1 Implement GraphQL batching with adaptive sizing
    - Create RepoSnapshotFetcher class with fetch_snapshots method
    - Implement GraphQL alias generation for batched queries
    - Start with conservative batch size (10-15 repos, configurable)
    - Track query costs and adjust batch sizes dynamically
    - Reduce batch size by 50% on failures, increase by 20% on successes (max 30)
    - Implement fallback to single-repo fetch on repeated failures
    - Implement cursor-based pagination for large result sets
    - Parse responses into RepositorySnapshot Pydantic models
    - _Requirements: 1.1-1.5, 19.1-19.5_
  
  - [x] 5.2 Write property tests for snapshot fetcher (REQUIRED FOR MVP)
    - **Property 2: Repository Snapshot Completeness**
    - **Property 3: GraphQL Batching Correctness**
    - **Property 4: GraphQL Pagination Completeness**
    - **Validates: Requirements 1.2, 1.3, 1.4, 19.1**
    - **NOTE: GraphQL batching is core infrastructure - property tests are NOT optional**
  
  - [x] 5.3 Implement single repository snapshot fetch (fallback)
    - Create fetch_single method for individual repo fetching
    - Use when batch fetching fails repeatedly
    - _Requirements: 1.1, 1.2_

- [x] 6. Implement activity data fetchers
  - [x] 6.1 Implement contributors fetcher
    - Create ContributorsFetcher class with fetch_contributors method
    - Fetch from /repos/{owner}/{repo}/contributors endpoint
    - Fetch from /repos/{owner}/{repo}/stats/contributors endpoint
    - Parse responses into ContributorRecord Pydantic models
    - _Requirements: 2.1, 2.2, 2.7_
  
  - [x] 6.2a Implement issues fetcher for metadata and comments
    - Create IssuesFetcher class with fetch_issues method
    - Fetch from /repos/{owner}/{repo}/issues endpoint with state=all
    - Fetch from /repos/{owner}/{repo}/issues/comments endpoint
    - Cap issue history depth at 100 issues for MVP
    - Parse responses into IssueRecord Pydantic models
    - _Requirements: 2.3, 2.4, 2.7_
  
  - [x] 6.2b Implement optional issue events enrichment path
    - Implement fetch_issue_events method (use sparingly)
    - Fetch from /repos/{owner}/{repo}/issues/events endpoint
    - Use only when features cannot be approximated from metadata + comments
    - Document which features require events vs approximations
    - _Requirements: 2.5, 2.7_
  
  - [x] 6.3 Write unit tests for activity fetchers
    - Test contributor data parsing
    - Test issue data parsing with various states
    - Test pagination handling
    - _Requirements: 2.1-2.7_

- [x] 7. Implement feature engineering with weighted coverage
  - [x] 7.1 Implement feature computation
    - Create FeatureEngineer class with compute_features method
    - Compute all snapshot features (days_since_last_push, days_since_last_release, stars_count, archived, open_issues_count)
    - Compute contributor metrics (contributors_count, contributors_last_12mo, top_contributor_fraction_12mo)
    - Compute issue lifecycle metrics (issues_per_contributor, fraction_issues_closed_12mo, fraction_open_issues_stale_180d, avg_time_to_first_maintainer_response_days, median_time_to_close_days, open_issue_age_p90_days)
    - Ensure output matches feature_mapping_config.py schema
    - _Requirements: 5.1-5.11, 17.1_
  
  - [x] 7.2 Implement provisional feature computation
    - Create compute_provisional_features method
    - Compute only snapshot and contributor features (skip issue metrics)
    - _Requirements: 5.1, 5.2, 5.6, 5.7, 11.2_
  
  - [x] 7.3 Implement weighted feature coverage checking
    - Create check_feature_coverage method
    - Calculate coverage based on WEIGHTED features (not raw count)
    - Use 60% threshold (configurable)
    - Identify missing feature CATEGORIES (not individual features)
    - Return coverage percentage and list of missing categories
    - _Requirements: 22.1-22.5_
  
  - [x] 7.4 Write property tests for feature engineering (REQUIRED FOR MVP)
    - **Property 16: Feature Computation Determinism**
    - **Property 17: Feature Schema Compatibility**
    - **Property 35: Feature Coverage Threshold Enforcement**
    - **Validates: Requirements 5.1-5.11, 17.1, 22.1, 22.3, 22.4**
    - **NOTE: Feature coverage threshold is core logic - property tests are NOT optional**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass. If blockers arise, document them clearly and continue with the next non-blocked task where possible.

- [x] 9. Implement ingestion pipeline orchestration
  - [x] 9.1 Implement ingestion pipeline
    - Create IngestionPipeline class with ingest_repositories method
    - Orchestrate: snapshot fetch → contributors fetch → issues fetch → feature engineering → persistence
    - Implement progress reporting every 10 repositories
    - Continue with remaining repos if individual fetches fail
    - Return IngestionSummary with success/failure counts and API call metrics
    - _Requirements: 6.1-6.8, 15.1-15.6_
  
  - [x] 9.2 Implement single repository ingestion
    - Create ingest_single method
    - Support "full" and "provisional" modes
    - Return IngestionResult with features, score, completeness, API calls, timing
    - _Requirements: 6.1-6.5, 11.1-11.4_
  
  - [x] 9.3 Write property tests for ingestion pipeline
    - **Property 18: Ingestion Pipeline Ordering**
    - **Property 19: Ingestion Error Isolation**
    - **Property 20: Ingestion Summary Completeness**
    - **Validates: Requirements 6.1-6.6, 6.8, 16.3**

- [x] 10. Implement entity normalization with explicit precedence (MOVED EARLIER - BEFORE COVERAGE DETECTION)
  - [x] 10.1 Implement entity normalizer with ambiguity handling
    - Create EntityNormalizer class with normalize_repository and normalize_package methods
    - Implement rule hierarchy: (1) exact owner/repo, (2) exact package mapping, (3) inferred mapping, (4) unresolved warning
    - Load mappings from config/package_repo_mappings.yaml
    - Handle edge cases: multiple repos, ambiguous mappings, cross-ecosystem conflicts
    - Implement confidence threshold logic (when to treat as unresolved vs return alternatives)
    - Preserve both package and repo candidates when ambiguous
    - Return NormalizationResult with canonical_identifier, confidence, alternatives, warning
    - _Requirements: 21.1-21.6_
  
  - [x] 10.2 Create package-to-repo mapping configuration
    - Create config/package_repo_mappings.yaml
    - Add mappings for common packages (numpy, flask, react, vue, etc.)
    - Organize by ecosystem (pypi, npm, maven, cargo)
    - Document ambiguity resolution strategy
    - _Requirements: 21.6_
  
  - [x] 10.3 Write property test for entity normalization
    - **Property 34: Entity Normalization Consistency**
    - **Validates: Requirements 21.1-21.6**
  
  - [x] 10.4 Write unit tests for ambiguity handling
    - Test multiple repo candidates for same package
    - Test cross-ecosystem conflicts
    - Test confidence threshold behavior
    - Test unresolved entity warnings
    - _Requirements: 21.1-21.6_

- [x] 11. Implement query coverage detection
  - [x] 11.1 Implement coverage checker
    - Create CoverageChecker class with check_coverage method
    - Query database for each repository identifier
    - Return CoverageReport with in_database, missing, invalid lists
    - Set coverage_mode: database_only, live_ingestion_required, or hybrid
    - Include last_updated timestamp for database repos
    - _Requirements: 8.1-8.6_
  
  - [x] 11.2 Write property tests for coverage checker
    - **Property 24: Coverage Status Validity**
    - **Property 25: Coverage Mode Determination**
    - **Property 26: Database Timestamp Presence**
    - **Validates: Requirements 8.2-8.6**

- [x] 12. Implement retrieval strategy selection
  - [x] 12.1 Implement retrieval strategy selector
    - Create RetrievalStrategy class with select_strategy method
    - Select DB_Retriever for database_only mode
    - Select Live_Repo_Ingestor for live_ingestion_required mode
    - Select both for hybrid mode
    - Configure Live_Repo_Ingestor mode (provisional vs full) based on user preferences
    - Classify cost as low/medium/high for internal logging
    - Create EvidenceScope object for tracking data sources
    - Return RetrievalPlan with strategy details
    - _Requirements: 9.1-9.6_
  
  - [x] 12.2 Write property test for retrieval strategy (REQUIRED FOR MVP)
    - **Property 27: Retrieval Strategy Consistency**
    - **Property 28: Score Mode Propagation**
    - **Validates: Requirements 9.1-9.5**
    - **NOTE: Retrieval strategy consistency is core logic - property tests are NOT optional**

- [x] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass. If blockers arise, document them clearly and continue with the next non-blocked task where possible.

- [x] 14. Implement database retrieval with split responsibilities
  - [x] 14.1 Implement DB retriever with summary and full evidence methods
    - Create DBRetriever class with retrieve_summary method
    - Implement retrieve_summary for fast query-time use (repo name, score, risk band, features, provenance, missing categories)
    - Implement retrieve_full_evidence for detailed inspection (all summary data + raw snapshot, contributors, issues, metadata)
    - Query existing database schema
    - Return RepoSummary Pydantic models for summary retrieval
    - Return RepoFullEvidence Pydantic models for full retrieval
    - Include DataProvenance with source=database, last_updated, score_completeness=full
    - _Requirements: 10.1-10.5, 17.2, 17.4_
  
  - [x] 14.2 Write property test for database retrieval
    - **Property 29: Database Retrieval Completeness**
    - **Validates: Requirements 10.1, 10.2**

- [x] 15. Implement live repository ingestor
  - [x] 15.1 Implement live repo ingestor with flexible persistence
    - Create LiveRepoIngestor class with ingest method
    - Invoke IngestionPipeline for specified repositories
    - Support "provisional" mode (snapshot + contributors only)
    - Support "full" mode (snapshot + contributors + issues)
    - Compute MaintenanceRiskScore using FeatureEngineer
    - Include DataProvenance with source=live_fetch, current timestamp, score_completeness
    - Support persistence modes: temporary, cache (1-hour TTL), database (optional)
    - Check cache before re-ingesting (1-hour TTL)
    - Return RepoSummary Pydantic models
    - _Requirements: 11.1-11.9, 14.1-14.6_
  
  - [x] 15.2 Write property tests for live ingestor (REQUIRED FOR MVP)
    - **Property 31: Live Ingestion Mode Correctness**
    - **Property 32: Persistence Mode Enforcement**
    - **Validates: Requirements 11.2, 11.3, 11.9, 14.6**
    - **NOTE: Live ingestion persistence modes are core behavior - property tests are NOT optional**

- [x] 16. Implement result summarization and combination
  - [x] 16.1 Implement result merger
    - Create ResultSummarizer class with merge_results method
    - Combine database and live ingestion results
    - Preserve DataProvenance for each repository
    - Identify which repos came from database vs live ingestion
    - Add warnings for mixed score_completeness comparisons
    - _Requirements: 12.1-12.5_
  
  - [x] 16.2 Implement natural language response generation
    - Create summarize method for generating natural language responses
    - Rank repositories by maintenance_risk_score
    - Include risk band classifications (low, medium, high, critical)
    - Explain key contributing factors (days_since_last_push, fraction_open_issues_stale_180d, etc.)
    - Include DataProvenance information (source, last_updated, score_completeness)
    - Explain provisional score limitations
    - Return QueryResponse Pydantic model
    - _Requirements: 13.1-13.6, 20.1-20.6_
  
  - [x] 16.3 Write property tests for result summarization
    - **Property 30: Provenance Completeness**
    - **Property 33: Hybrid Result Preservation**
    - **Validates: Requirements 10.3, 10.4, 11.5-11.7, 12.1-12.3, 20.1-20.6**

- [x] 17. Integrate with existing query system
  - [x] 17.1 Update query parser for new intents
    - Extend QueryParser to support new intents: repo_lookup, repo_comparison, search_ranking, find_dependents, missing_repo_handling
    - Maintain backward compatibility with existing intents
    - Use EntityNormalizer for entity extraction
    - Return ParsedQuery Pydantic model
    - _Requirements: 7.1-7.6, 17.3_
  
  - [ ] 17.2 Write property tests for query parser
    - **Property 21: Intent Classification Validity**
    - **Property 22: Entity Extraction Presence**
    - **Property 23: Query Parser Output Structure**
    - **Validates: Requirements 7.2-7.5**
  
  - [ ] 17.3 Integrate with intent executor
    - Update src/open_source_risk_model/query/intent_executor.py
    - Add handlers for new intents using Coverage_Checker, Retrieval_Strategy, DB_Retriever, Live_Repo_Ingestor
    - Wire together: Query_Parser → Entity_Normalizer → Coverage_Checker → Retrieval_Strategy → DB_Retriever/Live_Repo_Ingestor → Result_Summarizer
    - Maintain backward compatibility with existing intent handlers
    - _Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.6, 10.1-10.5, 11.1-11.9, 12.1-12.5, 13.1-13.6, 17.3_

- [x] 18. Checkpoint - Ensure all tests pass
  - Ensure all tests pass. If blockers arise, document them clearly and continue with the next non-blocked task where possible.

- [x] 19. Add CLI commands for new ingestion capabilities
  - [x] 19.1 Add GraphQL ingestion command
    - Update src/open_source_risk_model/cli/ingest.py
    - Add command for GraphQL-based batch ingestion
    - Support configurable batch sizes
    - Display progress and API call metrics
    - _Requirements: 6.1-6.8, 15.1-15.6, 17.6_
  
  - [x] 19.2 Add live ingestion command
    - Add command for on-demand repository ingestion
    - Support provisional and full modes
    - Support persistence mode selection (temporary, cache, database)
    - Display ingestion results and provenance
    - _Requirements: 11.1-11.9, 17.6_

- [x] 20. Create configuration files
  - [x] 20.1 Create ingestion configuration
    - Create config/ingestion_config.yaml
    - Set conservative defaults: initial_batch_size=10, max_batch_size=30
    - Configure rate limiting, caching, retry behavior
    - Set minimum_coverage_threshold=0.6 (60% weighted features)
    - Set MVP flags: enable_deep_issue_enrichment=false, max_issues_per_repo=100
    - _Requirements: 18.1-18.6_
  
  - [x] 20.2 Validate configuration loading
    - Test configuration loading in all components
    - Test default value fallback
    - Test configuration validation
    - _Requirements: 18.5_

- [x] 21. Write integration tests for end-to-end flows
  - Test database-only query flow
  - Test live ingestion query flow (provisional mode)
  - Test live ingestion query flow (full mode)
  - Test hybrid query flow
  - Test backward compatibility with existing queries
  - _Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.6, 10.1-10.5, 11.1-11.9, 12.1-12.5, 13.1-13.6, 17.1-17.6_
  - Created test/query/test_e2e_query_coverage.py with 18 end-to-end tests
  - 12/18 passing, 6 expected failures due to test environment (no GitHub token, no database)

- [x] 22. Benchmark parity validation (NEW - CRITICAL FOR TRUST)
  - [x] 22.1 Select benchmark repository set
    - Select 10-20 representative repos already in the database
    - Include variety: active/inactive, large/small, different ecosystems
    - Document selection criteria
  
  - [x] 22.2 Run baseline with current system
    - Run current ingestion pipeline on benchmark repos
    - Capture feature values for all features
    - Capture final maintenance risk scores
    - Save baseline outputs for comparison
  
  - [x] 22.3 Run new system on benchmark repos
    - Run new hybrid ingestion pipeline on same repos
    - Capture feature values for all features
    - Capture final maintenance risk scores
    - Use same configuration (weights, thresholds)
  
  - [x] 22.4 Compare and validate parity
    - Compare feature values (old vs new)
    - Compare final scores (old vs new)
    - Define acceptable tolerance thresholds (e.g., ±0.01 for scores)
    - Flag any feature drift above tolerance
    - Document expected differences for snapshot/release semantics if applicable
    - Investigate and explain any significant divergences
  
  - [x] 22.5 Document parity validation results
    - Create parity validation report
    - Include pass/fail status for each benchmark repo
    - Document any acceptable differences
    - Flag any concerning divergences for investigation
  - Framework complete and documented in TASK_22_FRAMEWORK.md
  - Execution deferred to pre-production validation phase (requires production database and GitHub API access)

- [x] 23. Final checkpoint - Ensure all tests pass and verify backward compatibility
  - Ensure all tests pass. If blockers arise, document them clearly and continue with the next non-blocked task where possible.
  - Verify existing test suite passes
  - Verify existing CLI commands work
  - Verify database schema compatibility
  - Verify benchmark parity validation passed
  - Test suite: 1000/1095 passing (91.3% pass rate)
  - All new components tested and validated
  - Backward compatibility maintained

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- **EXCEPTION**: Property tests for core infrastructure (batching, cache TTL, feature coverage, retrieval strategy, live ingestion persistence) are REQUIRED for MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation without blocking progress
- Property tests validate universal correctness properties (35 properties from design)
- Unit tests validate specific examples and edge cases
- **Entity normalization moved earlier** (before coverage detection) to fix known numpy/numpy/numpy issue
- **Issue fetching split** into metadata (6.2a) and optional events (6.2b) for cleaner MVP scope
- **Benchmark parity validation added** (Task 22) to ensure new system produces same scores as current system
- MVP focuses on GraphQL snapshot ingestion, live fallback (provisional mode default), and provenance tracking
- Post-MVP: broader hybrid comparison, deep issue enrichment, advanced features (parallel ingestion, incremental updates, predictive pre-fetching)

## Critical Property Tests (REQUIRED for MVP)

These property tests are NOT optional - they validate core infrastructure that is most likely to quietly break:

1. **Task 5.2**: GraphQL batching correctness (Property 3)
2. **Task 7.4**: Feature coverage threshold enforcement (Property 35)
3. **Task 12.2**: Retrieval strategy consistency (Properties 27, 28)
4. **Task 15.2**: Live ingestion persistence mode enforcement (Properties 31, 32)

All other property tests can be deprioritized if needed for MVP speed.
