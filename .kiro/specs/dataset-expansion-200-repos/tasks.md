# Implementation Plan: Dataset Expansion to 200 Repositories

## ⚠️ PRODUCTION VALIDATION OUTCOME (March 9, 2026)

**Status**: Rollback to 51-repo baseline completed  
**Reason**: Scope mismatch discovered - only 2 of 5 required ecosystems supported

**What Was Validated** ✅:
- Infrastructure scales to 200 repos successfully
- Query performance excellent (0.041s max)
- Resolution rate strong (88.3%)
- npm + PyPI pipeline production-ready

**What Failed** ❌:
- Only 2 ecosystems supported (npm, PyPI)
- Missing parsers: Go, Maven, RubyGems
- Cannot meet 5-ecosystem distribution requirements

**Actions Taken**:
1. ✅ Preserved 200-repo data as `data/graphs_200repo_validation.db`
2. ✅ Restored 51-repo baseline from `backups/graphs_20260309_115956.db`
3. ✅ Rebuilt indexes
4. ✅ Created `PRODUCTION_VALIDATION_FINDINGS.md` with detailed analysis

**Recommended Next Steps**:
- **Phase A**: 2-ecosystem expansion (npm + PyPI only) - immediate value
- **Phase B**: Implement missing parsers, then 5-ecosystem expansion - future work

See `PRODUCTION_VALIDATION_FINDINGS.md` for complete details.

---

## Overview

This plan implements a 4x dataset expansion from 51 to 200 repositories using a 6-phase approach. The implementation builds on proven infrastructure (batch ingestion CLI, repository selection scripts, multi-repo database) while adding comprehensive validation, monitoring, and rollback capabilities. The expansion targets 15,000-50,000 dependencies with ≥85% resolution rate while maintaining query performance <5 seconds.

## Tasks

- [x] 1. Phase 1: Repository Selection (Week 1)
  - [x] 1.1 Create data models for repository selection
    - Implement `SelectionCriteria` dataclass with ecosystem targets and constraints
    - Implement `RepositoryCandidate` dataclass with metadata fields
    - Add type hints and validation
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  
  - [x] 1.2 Write property test for star threshold filtering
    - **Property 1: Star Threshold Filtering**
    - **Validates: Requirements 1.1**
  
  - [x] 1.3 Implement GitHub API client with rate limiting
    - Create `src/open_source_risk_model/expansion/github_client.py`
    - Implement exponential backoff for rate limits (base_delay * 2^attempt)
    - Add jitter (0-10%) to avoid thundering herd
    - Maximum 3 retry attempts per request
    - _Requirements: 2.4_
  
  - [x] 1.4 Write unit test for exponential backoff (PRIORITY: prevents expensive failures)
    - Test backoff logic with fake clock
    - Test delay increases exponentially (base_delay * 2^attempt)
    - Test jitter is within 0-10% range
    - Test max retry attempts (3)
    - **Property 9: Exponential Backoff on Rate Limits**
    - **Validates: Requirements 2.4**
  
  - [x] 1.5 Implement ecosystem inference algorithm (BOUNDED + CACHED)
    - **Phase 1**: Check root-level manifests only (fast, 1 API call)
    - **Phase 2**: If none found, check common subpaths allowlist (/frontend, /backend, /packages, /apps - max 5 paths)
    - **Phase 3**: Only if still none found, do deeper scan with hard cap (max 10 API calls)
    - Cache results in JSON file (data/ecosystem_cache.json) to avoid re-hitting API on reruns
    - Map manifest types to ecosystems (package.json→npm, requirements.txt→pypi, etc.)
    - Determine primary ecosystem based on production manifest presence
    - Return tuple of (primary_ecosystem, all_manifest_types)
    - _Requirements: 1.2, 1.5_
  
  - [x] 1.6 Implement priority score calculation
    - Calculate normalized star score (log scale)
    - Calculate recency score (days since last commit)
    - Add production dependencies bonus
    - Add ecosystem diversity bonus
    - Weighted sum: 0.4*stars + 0.3*recency + 0.2*prod_deps + 0.1*diversity
    - _Requirements: 1.1, 1.3, 1.4, 1.5_
  
  - [x] 1.7 Write property tests for priority scoring
    - **Property 3: Recency Prioritization**
    - **Property 4: Production Dependency Prioritization**
    - **Validates: Requirements 1.3, 1.5**
  
  - [x] 1.8 Implement duplicate detection (forks and name similarity)
    - Check if repository is a fork
    - Check for similar names using Levenshtein distance
    - Filter out duplicates before selection
    - _Requirements: 1.6_
  
  - [x] 1.9 Write property tests for duplicate detection
    - **Property 5: Fork Exclusion**
    - **Property 6: Duplicate Fork Exclusion**
    - **Validates: Requirements 1.6**
  
  - [x] 1.10 Implement quota-based repository selection algorithm
    - Create `src/open_source_risk_model/expansion/repo_selector.py`
    - Implement `RepositorySelector` class with `select_repositories()` method
    - Phase 1: Query GitHub API and filter by basic criteria
    - Phase 2: Infer ecosystems for all candidates
    - Phase 3: Calculate priority scores and deduplicate
    - Phase 4: Apply quota-based selection with EXPLICIT QUOTAS for 149 new repos:
      - npm: 38-60 repos (25-40% of 200 total)
      - pypi: 38-60 repos (25-40% of 200 total)
      - go: ≥15 repos (≥10% of 200 total)
      - maven: ≥15 repos (≥10% of 200 total)
      - rubygems: ≥8 repos (≥5% of 200 total)
    - Fill minimum quotas first, then by priority within max constraints
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2_
  
  - [x] 1.11 Write property tests for selection algorithm
    - **Property 2: Ecosystem Diversity**
    - **Property 7: Priority Ordering**
    - **Property 10: Existing Repository Exclusion**
    - **Validates: Requirements 1.2, 2.2, 2.5**
  
  - [x] 1.12 Enhance populate_popular_repos.py script (STABLE + REPRODUCIBLE)
    - Integrate new `RepositorySelector` class
    - Add CLI arguments for target count and criteria
    - Use deterministic seed/sorting key for reproducible selection
    - Output repository list with metadata (stars, ecosystem, last_commit_date)
    - Include generated_at timestamp and selection criteria in output
    - Save output to JSON file with format: repos_YYYYMMDD_HHMMSS.json
    - _Requirements: 2.1, 2.2, 2.3_
  
  - [x] 1.13 Write property test for repository metadata completeness
    - **Property 8: Repository Metadata Completeness**
    - **Validates: Requirements 2.3**
  
  - [x] 1.14 Write unit tests for repository selection (PRIORITY: prevents expensive failures)
    - Test selection produces exact count
    - Test ecosystem quotas are met (38-60 npm, 38-60 pypi, ≥15 go, ≥15 maven, ≥8 rubygems)
    - Test excludes existing repos from database
    - Test priority ordering
    - Test duplicate exclusion
    - Test error handling (API failures, rate limits)

- [x] 2. Phase 2: Ingestion and Monitoring (Week 2)
  - [x] 2.1 Enhance progress monitor in batch ingestion CLI
    - Add resolution rate to progress display
    - Add ETA calculation based on average time per repo
    - Add failure reason display for failed repositories
    - Update display format: `[progress_bar] X% | N/Total | ✅ owner/repo | ETA: Xh Ym`
    - Update interval: minimum 60 seconds
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [x] 2.2 Write property tests for progress monitor
    - **Property 13: Monitor Display Completeness**
    - **Property 14: ETA Display**
    - **Property 15: Failure Reason Display**
    - **Property 16: Monitor Update Frequency**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**
  
  - [x] 2.3 Integrate database backup before ingestion
    - Call existing `scripts/backup_database.py` before starting ingestion
    - Generate timestamp-based backup filename
    - Verify backup creation succeeded
    - Store backup path for potential rollback
    - _Requirements: 7.1, 7.2_
  
  - [x] 2.4 Write property tests for backup creation (PRIORITY: prevents expensive failures)
    - **Property 27: Backup Creation**
    - **Property 28: Backup Timestamp Naming**
    - **Validates: Requirements 7.1, 7.2**
  
  - [x] 2.5 Implement error logging and continuation logic
    - Wrap repository ingestion in try-catch
    - Log errors with repository name and failure reason
    - Continue processing remaining repositories on failure
    - Track failed repos in database (repo_ingestion_runs table)
    - _Requirements: 3.4_
  
  - [x] 2.6 Write property test for error logging and continuation
    - **Property 12: Error Logging and Continuation**
    - **Validates: Requirements 3.4**
  
  - [x] 2.7 Create expansion orchestrator script
    - Create `scripts/expand_dataset.py`
    - Implement `expand_dataset()` function with orchestration logic
    - Calculate number of repos to add (target - current)
    - Invoke repository selector
    - Create pre-expansion backup
    - Execute batch ingestion with monitoring
    - Return `ExpansionResult` with status and metrics
    - _Requirements: 3.1, 3.2_
  
  - [x] 2.8 Write unit tests for ingestion orchestration
    - Test backup integration
    - Test error handling with injected failures
    - Test progress monitoring updates
    - Test continuation after failures

- [x] 3. Checkpoint - Verify ingestion infrastructure + PREFLIGHT VALIDATION
  - Ensure all tests pass
  - **PREFLIGHT**: Run ingestion on 10 repos from selected list
  - Validate resolution rate, ecosystem classification, basic query patterns on 10-repo subset
  - If preflight passes, proceed with full 149-repo run
  - This prevents burning 10+ hours on a bad assumption

- [x] 4. Phase 3: Validation Framework (Week 3)
  - [x] 4.1 Implement count validators
    - Create `src/open_source_risk_model/expansion/validators.py`
    - Implement `DataQualityValidator` class
    - Implement `validate_counts()` method (verify repo count == 200, dependency count in [15000, 50000])
    - _Requirements: 5.1, 5.2_
  
  - [x] 4.2 Write property tests for count validation
    - **Property 17: Dependency Count Range**
    - **Validates: Requirements 5.2**
  
  - [x] 4.3 Implement ecosystem distribution validator
    - Implement `validate_ecosystem_distribution()` method
    - Query database for ecosystem counts
    - Calculate percentages
    - Verify: npm ∈ [25%, 40%], PyPI ∈ [25%, 40%], Go ≥ 10%, Maven ≥ 10%, RubyGems ≥ 5%
    - Verify at least 5 ecosystems present
    - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_
  
  - [x] 4.4 Write property tests for ecosystem distribution
    - **Property 19: Ecosystem Count Threshold**
    - **Property 20: Ecosystem Distribution Constraints**
    - **Validates: Requirements 5.4, 5.5, 5.6, 5.7, 5.8, 5.9**
  
  - [x] 4.5 Implement resolution rate validator (VERIFY METADATA RETRIEVAL)
    - Implement `validate_resolution_rate()` method
    - Query database for total dependencies
    - Query for resolved dependencies using THREE criteria:
      1. registry_type IS NOT NULL AND registry_type != ''
      2. specifier IS NOT NULL
      3. resolved_repo IS NOT NULL AND resolution_confidence IS NOT NULL
    - Note: resolved_repo proves metadata was retrieved (stores GitHub repo providing the package)
    - Calculate resolution rate = resolved / total
    - Verify rate >= 85%
    - Document any dependencies failing any of the three criteria
    - _Requirements: 5.3, 5A.1, 5A.2, 5A.3, 5A.4, 5A.5_
  
  - [x] 4.6 Write unit tests for resolution validation (PRIORITY: prevents expensive failures)
    - Test resolution rate calculation with known data
    - Test three-criteria resolution definition (registry + version + metadata)
    - Test validator detects resolution rate below 85%
    - Test failure documentation for unresolved dependencies
    - **Property 11: Resolution Rate Threshold**
    - **Property 18: Resolution Rate Validation**
    - **Property 22: Resolution Definition Consistency**
    - **Property 23: Resolution Rate Calculation**
    - **Property 24: Resolution Failure Documentation**
    - **Validates: Requirements 5.3, 5A.1, 5A.2, 5A.3, 5A.4, 5A.5**
  
  - [x] 4.7 Implement query performance benchmarker
    - Implement `validate_query_performance()` method
    - Define 10 query patterns (single repo deps, package dependents, hub packages, etc.)
    - Run each pattern 3 times (1 cold cache + 2 warm cache)
    - Measure end-to-end API time including Python overhead
    - Calculate median and p95 for each pattern
    - Verify max p95 < 5 seconds
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [x] 4.8 Write property tests for performance validation
    - **Property 25: Query Performance Threshold**
    - **Property 26: Performance Degradation Detection**
    - **Validates: Requirements 6.1, 6.3**
  
  - [x] 4.9 Implement validation orchestration and reporting
    - Implement `validate_expansion()` method that runs all validators
    - Collect results into `ValidationResult` dataclass
    - Generate detailed failure report if any check fails
    - Return pass/fail status with metrics
    - _Requirements: 5.10_
  
  - [x] 4.10 Write property test for validation failure reporting
    - **Property 21: Validation Failure Reporting**
    - **Validates: Requirements 5.10**
  
  - [x] 4.11 Create validation CLI script
    - Create `scripts/validate_expansion.py`
    - Accept command-line arguments (db_path, expected_repo_count, min_resolution_rate)
    - Run validation suite
    - Print results to console
    - Exit with non-zero status on failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [x] 4.12 Write unit tests for validation framework
    - Test with passing conditions
    - Test with failing conditions (low resolution, wrong counts, etc.)
    - Test report generation
    - Test error handling

- [x] 5. Phase 4: Signal Quality Analysis (Week 4)
  - [x] 5.1 Implement hub package detector
    - Create `src/open_source_risk_model/expansion/insight_analyzer.py`
    - Implement `SignalQualityAnalyzer` class
    - Implement `find_hub_packages()` method
    - Query dependencies grouped by package_name and registry_type
    - Count unique repositories per package
    - Filter packages used by >25% of repositories
    - Return list of `HubPackage` with usage metrics
    - _Requirements: 9.2_
  
  - [x] 5.2 Write property test for hub package detection
    - **Property 34: Hub Package Detection**
    - **Validates: Requirements 9.2**
  
  - [x] 5.3 Implement transitive footprint calculator
    - Implement `calculate_transitive_footprint()` method
    - For each package, count total transitive dependencies
    - Rank packages by footprint size
    - Return list of `FootprintMetric` with counts
    - _Requirements: 9.4_
  
  - [x] 5.4 Implement ecosystem pattern detector
    - Implement `detect_ecosystem_patterns()` method
    - Identify ecosystem-specific patterns (npm peer deps, Python extras, etc.)
    - Group patterns by ecosystem
    - Return list of `EcosystemPattern` with examples
    - _Requirements: 9.5_
  
  - [x] 5.5 Implement post-ingestion duplicate graph detector
    - Create `src/open_source_risk_model/expansion/duplicate_detector.py`
    - For each repository, compute dependency graph signature (sorted set of direct dependencies)
    - Group repositories by signature
    - Identify groups with >1 repository (duplicates)
    - Return list of duplicate groups with repository names
    - _Requirements: 1.7_
  
  - [x] 5.6 Write property test for duplicate graph detection
    - **Property 37: Post-Ingestion Duplicate Graph Detection**
    - **Validates: Requirements 1.7**
  
  - [x] 5.7 Implement baseline comparison logic
    - Implement `analyze_insights()` method
    - Run all insight detectors on current dataset
    - Compare with baseline (51-repo dataset) metrics
    - Identify new insights not visible in baseline
    - Count new insights discovered
    - _Requirements: 9.1_
  
  - [x] 5.8 Write property tests for insight analysis
    - **Property 33: Minimum Insights Threshold**
    - **Property 35: Insight Documentation**
    - **Property 36: Insufficient Signal Detection**
    - **Validates: Requirements 9.1, 9.6, 9.7**
  
  - [x] 5.9 Create insight analysis CLI script
    - Create `scripts/analyze_insights.py`
    - Accept command-line arguments (db_path, baseline_repo_count)
    - Run insight analysis
    - Print insights to console
    - Save results to JSON file
    - _Requirements: 9.1, 9.2, 9.4, 9.5_
  
  - [x] 5.10 Write unit tests for signal quality analysis
    - Test hub package detection with known data
    - Test footprint calculation
    - Test pattern detection
    - Test duplicate graph detection
    - Test baseline comparison

- [x] 6. Checkpoint - Verify validation and analysis
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Phase 5: Reporting and Rollback (Week 5)
  - [x] 7.1 Implement expansion report generator
    - Create `scripts/generate_expansion_report.py`
    - Implement `generate_expansion_report()` function
    - Generate Markdown report with sections: Executive Summary, Newly Added Repositories, Failed Ingestions, Ecosystem Distribution, Query Performance, Cross-Repository Insights, Duplicate Graph Detection, Validation Status
    - Include before/after comparison for query performance
    - Include cold/warm cache metrics
    - Save report to file
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [x] 7.2 Write unit test for report completeness (PRIORITY: prevents crashes)
    - Test report generator doesn't crash
    - Test all key sections are present
    - **Property 30: Expansion Report Completeness**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
  
  - [x] 7.3 Implement rollback procedure
    - Add `rollback_expansion()` function to orchestrator
    - Verify backup integrity before restoration
    - Call existing `scripts/restore_database.py` with backup path
    - Verify restored database has expected repo count
    - Rebuild indexes after restoration
    - _Requirements: 7.3, 7.4, 7.5_
  
  - [x] 7.4 Write property test for rollback round-trip
    - **Property 29: Rollback Round-Trip**
    - **Validates: Requirements 7.4**
  
  - [x] 7.5 Integrate validation and reporting into orchestrator
    - Update `expand_dataset()` to run validation after ingestion
    - Run signal quality analysis after validation
    - Generate expansion report with all results
    - Offer rollback option if validation fails
    - Return complete `ExpansionResult` with all metrics
    - _Requirements: 3.1, 5.1, 9.1_
  
  - [x] 7.6 Write end-to-end integration test
    - Test complete expansion workflow from selection through reporting
    - Start with 51-repo test database
    - Run expansion to 200 repos
    - Verify all validation checks pass
    - Verify report generation
    - Test rollback procedure
  
  - [x] 7.7 Create expansion runbook documentation
    - Document step-by-step expansion procedure
    - Document rollback procedure
    - Document validation checks and thresholds
    - Document troubleshooting common issues
    - Add examples and command-line usage
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [-] 8. Phase 6: Production Expansion (Week 6)
  - [x] 8.1 Create production database backup
    - Run backup script on production database
    - Verify backup integrity
    - Store backup in safe location
    - _Requirements: 7.1, 7.2_
    - **STATUS**: ✅ Complete - Backup created at `backups/graphs_20260309_115956.db`
  
  - [x] 8.2 Generate repository selection list
    - Run enhanced populate_popular_repos.py script
    - Target: 149 repositories (200 - 51 current)
    - Review generated list for quality
    - Verify ecosystem distribution targets
    - Save approved list to file
    - _Requirements: 2.1, 2.2, 2.3_
    - **STATUS**: ✅ Complete - Selection list generated
  
  - [x] 8.3 Execute batch ingestion
    - Run expansion orchestrator with approved repository list
    - Monitor progress in real-time
    - Track any failures
    - Allow 24 hours for completion
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
    - **STATUS**: ✅ Complete - 200 repos ingested successfully
  
  - [x] 8.4 Run validation suite
    - Execute validation script on expanded database
    - Verify all checks pass (repo count, dependency count, resolution rate, ecosystem distribution, query performance)
    - Review validation report
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1_
    - **STATUS**: ⚠️ PARTIAL - Infrastructure validated (✅ 200 repos, ✅ 88.3% resolution, ✅ 0.041s query time) BUT ❌ Ecosystem distribution failed (only 2 ecosystems: npm 70%, PyPI 30%). Missing parsers for Go, Maven, RubyGems.
  
  - [-] 8.5 Run signal quality analysis
    - Execute insight analysis script
    - Verify at least 5 new cross-repository insights discovered
    - Review hub packages, footprints, and patterns
    - Review duplicate graph detection results
    - _Requirements: 9.1, 9.2, 9.4, 9.5_
    - **STATUS**: ⏸️ BLOCKED - Deferred pending parser implementation for missing ecosystems
  
  - [-] 8.6 Generate final expansion report
    - Run report generator with all results
    - Review report for completeness
    - Share report with stakeholders
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
    - **STATUS**: ⏸️ BLOCKED - Replaced by `PRODUCTION_VALIDATION_FINDINGS.md` documenting scope mismatch
  
  - [-] 8.7 Update documentation and demos
    - Update README with new dataset size
    - Update demo scripts with new examples
    - Update query examples to showcase new insights
    - Document any new patterns discovered
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
    - **STATUS**: ⏸️ BLOCKED - Deferred pending decision on Phase A (2-ecosystem) vs Phase B (5-ecosystem) expansion

- [ ] 9. Final checkpoint - Production expansion complete
  - Ensure all validation checks pass, review expansion report, confirm with user that expansion is successful.

## Notes

- Tasks marked with `*` are optional property-based tests and can be skipped for faster MVP
- **Test Priorities** (focus on these to prevent expensive failures):
  1. Selection exact count + ecosystem quotas + excludes existing repos
  2. Backoff logic with fake clock (unit test, not property test)
  3. Orchestrator "backup happens before ingest"
  4. Validator correctness for counts/resolution/distribution
  5. Report generator "doesn't crash" and contains key sections
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at major phase boundaries
- Property tests validate universal correctness properties using hypothesis library (min 100 iterations)
- Unit tests validate specific examples and edge cases
- Phase 6 (Production Expansion) should only be executed after Phases 1-5 are complete and tested
- Dependency depth validation removed - requires transitive edges not yet available (deferred to future work)
- Duplicate graph detection split into two phases: selection-time heuristics (Property 6) and post-ingestion analysis (Property 37)
- Query performance measured as end-to-end API time with cold/warm cache runs
- Resolution definition: package matched to registry + version parsed + metadata retrieved (resolved_repo IS NOT NULL proves metadata retrieval)
- Ecosystem inference uses bounded 3-phase approach with caching to prevent API rate explosion
- Explicit quotas for 149 new repos: npm 38-60, pypi 38-60, go ≥15, maven ≥15, rubygems ≥8
- Repository selection output includes deterministic seed and timestamp for reproducibility
- Preflight validation on 10-repo subset before full 149-repo run prevents wasting hours on bad assumptions
