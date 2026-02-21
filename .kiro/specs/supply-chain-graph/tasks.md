# Implementation Plan: Supply Chain Risk Graph

## Overview

This plan implements a graph-based supply chain risk intelligence engine that transforms flat risk scores into a visual, contextualized graph representation. The implementation follows an incremental approach, building core infrastructure first, then adding enrichments progressively.

**Key Principles:**
- Build incrementally with validation at each step
- Graceful degradation when data sources fail
- Property-based testing for graph invariants
- Provenance and confidence tracking for trust

## Tasks

- [x] 1. Enhance graph schema with provenance support
  - Update Node and Edge classes to include provenance field
  - Add provenance validation to graph validator
  - Update serialization to include provenance in JSON output
  - _Requirements: US-1.3, US-1.4_

- [x] 1.1 Write property test for provenance completeness
  - **Property 13: Provenance Completeness**
  - **Validates: Requirements US-1.3, US-1.4**

- [x] 2. Implement enhanced graph validation
  - [x] 2.1 Add validation for provenance fields
    - Ensure source, timestamp, and confidence fields present
    - Validate confidence values are in range 0.0-1.0
    - _Requirements: US-1.5_
  
  - [x] 2.2 Enhance existing validation logic
    - Keep existing checks (unique IDs, valid references, single repo)
    - Add provenance completeness check
    - _Requirements: US-1.5_
  
  - [x] 2.3 Write property test for graph validity invariant
    - **Property 1: Graph Validity Invariant**
    - **Validates: Requirements US-1.2, US-1.5**

- [x] 3. Create graph configuration system
  - Implement GraphConfig dataclass with all configuration options
  - Add default values for max_releases, max_maintainers, etc.
  - Support configuration from environment variables
  - _Requirements: US-5.4, US-7.4_


- [x] 4. Enhance GraphBuilder with error handling and provenance
  - [x] 4.1 Add provenance tracking to node creation methods
    - Update _add_repo_node to include provenance
    - Update _add_risk_factor_nodes to include provenance
    - Add timestamp and confidence to all nodes
    - _Requirements: US-1.3, US-7.1_
  
  - [x] 4.2 Implement graceful error handling
    - Wrap each enrichment step in try-except
    - Log errors with context
    - Add warnings to graph metadata on partial failure
    - _Requirements: US-3.5_
  
  - [x] 4.3 Add edge provenance tracking
    - Include source and confidence in all edges
    - Add established_at timestamp
    - _Requirements: US-1.4_
  
  - [x] 4.4 Write property test for partial graph validity
    - **Property 12: Partial Graph Validity**
    - **Validates: Requirements US-3.5**

- [x] 5. Checkpoint - Ensure enhanced schema works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement GitHub Releases integration
  - [x] 6.1 Add fetch_releases method to GitHub client
    - Query GitHub Releases API
    - Parse release data (tag, published_at, prerelease)
    - Implement caching with 1-hour TTL
    - _Requirements: US-2.1_
  
  - [x] 6.2 Create _add_release_nodes method in GraphBuilder
    - Create RELEASE nodes from GitHub data
    - Add HAS_RELEASE edges from repo to releases
    - Include provenance (source: github_api, confidence: 1.0)
    - Limit to max_releases (default 10)
    - _Requirements: US-2.1_
  
  - [x] 6.3 Write property test for release node creation
    - **Property 5 (adapted): Release nodes created when releases exist**
    - **Validates: Requirements US-2.1**
  
  - [x] 6.4 Write unit tests for release integration
    - Test with known repositories (numpy, requests)
    - Test edge case: repo with no releases
    - Test caching behavior

- [x] 7. Implement GitHub Contributors integration
  - [x] 7.1 Add fetch_contributors method to GitHub client
    - Query GitHub Contributors API
    - Parse contributor data (username, contributions)
    - Implement caching with 24-hour TTL
    - _Requirements: US-5.1_
  
  - [x] 7.2 Create _add_maintainer_nodes method in GraphBuilder
    - Create MAINTAINER nodes for top contributors
    - Add MAINTAINED_BY edges from maintainers to repo
    - Include provenance (source: github_api, confidence: 0.9)
    - Limit to max_maintainers (default 5)
    - Calculate contribution_fraction
    - _Requirements: US-5.1, US-5.2, US-5.3_
  
  - [x] 7.3 Write property test for maintainer node creation
    - **Property 7: Maintainer Node Creation**
    - **Validates: Requirements US-5.1**
  
  - [x] 7.4 Write property test for node count limits
    - **Property 11: Node Count Limits**
    - **Validates: Requirements US-5.4**


- [x] 8. Checkpoint - Ensure GitHub integrations work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement CVE data fetching from OSV.dev
  - [x] 9.1 Create CVEFetcher class
    - Implement fetch_cves method to query OSV.dev API
    - Parse CVE records (id, severity, cvss_score, summary)
    - Handle timeouts (5 seconds)
    - Implement exponential backoff for rate limiting
    - _Requirements: US-3.1, US-3.3_
  
  - [x] 9.2 Implement CVE caching
    - Cache CVE data in data/cve/{ecosystem}__{package}.json
    - TTL: 24 hours
    - Include cache metadata (fetched_at, expires_at)
    - _Requirements: US-3.1_
  
  - [x] 9.3 Implement CVE-to-release mapping
    - Parse affected version ranges from OSV data
    - Match CVEs to release nodes
    - Calculate match_confidence based on version matching
    - _Requirements: US-3.4_
  
  - [x] 9.4 Write unit tests for CVE fetching
    - Test with mock OSV.dev responses
    - Test timeout handling
    - Test cache behavior
    - Test version range parsing

- [x] 10. Integrate CVE data into GraphBuilder
  - [x] 10.1 Create _add_cve_nodes method
    - Detect package ecosystem from repo files
    - Fetch CVEs using CVEFetcher
    - Create CVE nodes with metadata
    - Add HAS_CVE edges from releases to CVEs
    - Include provenance (source: osv, confidence: 0.95, match_confidence)
    - _Requirements: US-3.1, US-3.3, US-3.4_
  
  - [x] 10.2 Handle CVE fetch failures gracefully
    - Catch network errors and timeouts
    - Log warnings
    - Return partial graph without CVE nodes
    - Add warning to graph metadata
    - _Requirements: US-3.5_
  
  - [x] 10.3 Write property test for CVE node creation
    - **Property 5: CVE Node Creation**
    - **Validates: Requirements US-3.1**

- [x] 11. Implement package registry detection
  - [x] 11.1 Create RegistryDetector class
    - Implement detect_registries method
    - Check for manifest files (setup.py, package.json, pom.xml, etc.)
    - Map file types to registry types
    - _Requirements: US-4.1, US-4.2_
  
  - [x] 11.2 Implement package name extraction
    - Parse setup.py using ast.parse()
    - Parse package.json using json.loads()
    - Parse pom.xml using xml.etree.ElementTree
    - Parse pyproject.toml using toml library
    - Calculate match_confidence based on parsing success
    - _Requirements: US-4.2, US-4.4_
  
  - [x] 11.3 Create _add_registry_nodes method in GraphBuilder
    - Detect registries using RegistryDetector
    - Create REGISTRY nodes with metadata
    - Add PUBLISHED_AS edges from repo to registries
    - Include provenance (source: heuristic, confidence: 0.8, match_confidence)
    - _Requirements: US-4.1, US-4.3, US-4.4_
  
  - [x] 11.4 Write property test for registry node creation
    - **Property 6: Registry Node Creation**
    - **Validates: Requirements US-4.1, US-4.2**
  
  - [x] 11.5 Write unit tests for registry detection
    - Test PyPI detection (setup.py, pyproject.toml)
    - Test npm detection (package.json)
    - Test Maven detection (pom.xml)
    - Test repos with no package manifests


- [x] 12. Checkpoint - Ensure all data sources integrated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Create /api/graph endpoint
  - [x] 13.1 Implement graph endpoint in FastAPI
    - Add GET /api/graph route
    - Parse query parameters (repo, refresh, include_cves, max_releases, max_maintainers)
    - Validate repository format
    - _Requirements: US-2.1_
  
  - [x] 13.2 Implement graph generation orchestration
    - Call score_repo to get score data
    - Initialize GraphBuilder with all data sources
    - Build graph with error handling
    - Serialize graph to JSON
    - _Requirements: US-2.1, US-2.2_
  
  - [x] 13.3 Implement response formatting
    - Include repo, schema_version, generated_at
    - Include graph.nodes and graph.edges
    - Include metadata (node_count, edge_count, data_sources, cache_hit, generation_time_ms)
    - _Requirements: US-2.2_
  
  - [x] 13.4 Implement error handling
    - Return 400 for invalid repo format
    - Return 404 for repo not found
    - Return 500 for internal errors
    - Return 503 for external API failures (with partial graph if possible)
    - _Requirements: US-2.5_
  
  - [x] 13.5 Write property test for API response structure
    - **Property 9: API Response Structure**
    - **Validates: Requirements US-2.2**
  
  - [x] 13.6 Write property test for error response status codes
    - **Property 10: Error Response Status Codes**
    - **Validates: Requirements US-2.5**
  
  - [x] 13.7 Write unit tests for API endpoint
    - Test successful graph generation
    - Test with various query parameters
    - Test error cases (invalid repo, not found)
    - Test empty graph edge case

- [x] 14. Implement graph caching
  - [x] 14.1 Create graph cache storage
    - Cache complete graphs in data/graphs/{owner}__{repo}.json
    - Include cache metadata (cached_at, ttl_hours, expires_at)
    - TTL: 1 hour
    - _Requirements: US-2.3_
  
  - [x] 14.2 Implement cache lookup and storage
    - Check cache before building graph
    - Respect refresh parameter
    - Update cache after successful build
    - _Requirements: US-2.3_
  
  - [x] 14.3 Write unit tests for caching
    - Test cache hit scenario
    - Test cache miss scenario
    - Test refresh parameter
    - Test TTL expiration


- [x] 15. Checkpoint - Ensure API endpoint works end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Create frontend visualization page
  - [x] 16.1 Create HTML page for graph visualization
    - Create templates/graph.html
    - Include vis.js from CDN
    - Add graph container div
    - Add details panel for node information
    - Add controls (filters, search, export)
    - _Requirements: US-6.1_
  
  - [x] 16.2 Implement JavaScript graph rendering
    - Create static/graph-viz.js
    - Fetch graph data from /api/graph
    - Convert graph data to vis.js format
    - Apply node styling by type (colors, shapes)
    - Apply edge styling (colors, widths, dashed for low confidence)
    - Implement hierarchical layout
    - _Requirements: US-6.1, US-6.3, US-6.4_
  
  - [x] 16.3 Implement interactive features
    - Node click: Show details in side panel
    - Node hover: Show tooltip with key info
    - Zoom and pan controls
    - Filter by node type
    - Search by node label
    - Confidence filter slider
    - _Requirements: US-6.2, US-6.5_
  
  - [x] 16.4 Implement provenance display
    - Show provenance metadata in node details
    - Display confidence indicators (visual badges)
    - Add toggle to show/hide provenance
    - Highlight low-confidence nodes/edges
    - _Requirements: US-1.3, US-1.4_
  
  - [x] 16.5 Write integration tests for visualization
    - Test graph loads and renders
    - Test interactive features work
    - Test with various graph sizes

- [x] 17. Add export functionality
  - Implement JSON export (download graph data)
  - Implement PNG export (screenshot of visualization)
  - Add export buttons to UI
  - _Requirements: US-6.1_

- [x] 18. Implement comprehensive property tests
  - [x] 18.1 Write property test for node schema completeness
    - **Property 2: Node Schema Completeness**
    - **Validates: Requirements US-1.3, US-3.3, US-4.4, US-5.3, US-7.3**
  
  - [x] 18.2 Write property test for edge schema completeness
    - **Property 3: Edge Schema Completeness**
    - **Validates: Requirements US-1.4, US-3.4, US-4.3, US-5.2, US-7.2**
  
  - [x] 18.3 Write property test for graph serialization round-trip
    - **Property 4: Graph Serialization Round-Trip**
    - **Validates: Requirements US-2.2**
  
  - [x] 18.4 Write property test for risk factor node creation
    - **Property 8: Risk Factor Node Creation**
    - **Validates: Requirements US-7.1, US-7.4**


- [x] 19. Add logging and monitoring
  - [x] 19.1 Implement structured logging
    - Add request ID to all log entries
    - Log graph generation events (started, completed, failed)
    - Log external API calls with timing
    - Log cache hits/misses
    - Log validation failures
    - _Requirements: US-2.1_
  
  - [x] 19.2 Add performance metrics
    - Track graph generation time
    - Track API response time
    - Track cache hit rate
    - Track error rate by type
    - _Requirements: US-2.3_
  
  - [x] 19.3 Enhance health check endpoint
    - Add service status (github_api, osv_api, cache)
    - Add metrics (cache_hit_rate, avg_response_time_ms)
    - _Requirements: US-2.1_

- [x] 20. Create documentation
  - [x] 20.1 Update API documentation
    - Document /api/graph endpoint
    - Document query parameters
    - Document response format
    - Document error responses
    - Add examples
    - _Requirements: US-2.1_
  
  - [x] 20.2 Create user guide
    - Explain graph visualization features
    - Explain provenance and confidence
    - Provide usage examples
    - Document configuration options
    - _Requirements: US-6.1_
  
  - [x] 20.3 Update README
    - Add supply chain graph feature description
    - Add setup instructions for new dependencies
    - Add screenshots of visualization
    - _Requirements: US-6.1_

- [x] 21. Final checkpoint - End-to-end validation
  - Test complete workflow with multiple repositories
  - Verify all correctness properties hold
  - Verify performance targets met
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property-based and unit tests
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (minimum 100 iterations each)
- Unit tests validate specific examples and edge cases
- Implementation follows incremental approach: core → enrichments → visualization → polish
- Provenance and confidence tracking is integrated throughout for trustworthiness

