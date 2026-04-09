# Design Document Updates Applied

## Summary

Applied critical fixes to the github-api-optimization-query-coverage design document based on user review feedback. All changes maintain existing correctness properties and requirements coverage.

## Changes Applied

### 1. ✅ Switched from dataclasses to Pydantic models

**What changed:**
- All external data models now use Pydantic BaseModel
- Applied to: RepositorySnapshot, ContributorRecord, IssueRecord, MaintenanceRiskScore, DataProvenance, EvidenceScope
- Added Field validators with descriptions, constraints (ge=0, ge=0.0, le=1.0)
- Added json_encoders for datetime serialization
- Kept dataclasses only for small internal utility objects (none currently in design)

**Why:** Validation, parsing, safer serialization, easier error handling for GitHub responses

**Location:** Data Models section

### 2. ✅ Made GraphQL batching adaptive and conservative

**What changed:**
- Added "Adaptive Batching Strategy" section to GraphQL Client
- Start with small configurable batch size (default: 10-15 repos)
- Track query costs from X-RateLimit-Cost response header
- Shrink batches by 50% on errors/complexity issues
- Grow batches cautiously by 20% on successes (max: 30)
- Keep fallback path to single-repo snapshot fetch
- Added track_query_cost() method to GraphQL Client interface

**Configuration changes:**
- Changed `default_batch_size: 30` to `initial_batch_size: 10`
- Changed `max_batch_size: 50` to `max_batch_size: 30`
- Added `min_batch_size: 1`
- Added `batch_size_increase_factor: 1.2`
- Added `batch_size_decrease_factor: 0.5`
- Added `track_query_costs: true`

**Why:** Conservative approach prevents rate limit issues, adapts to actual GitHub API costs

**Location:** GraphQL Client component, Configuration Schema

### 3. ✅ Clarified entity normalization precedence

**What changed:**
- Added "CRITICAL - Entity Normalization Rule Hierarchy" section
- Defined explicit rule hierarchy:
  1. Exact owner/repo format (highest priority, confidence: 1.0)
  2. Exact package mapping by ecosystem (confidence: 0.95)
  3. Inferred mapping from known aliases (confidence: 0.80)
  4. Unresolved entity warning (lowest priority, confidence: 0.0)

- Added NormalizationResult Pydantic model with:
  - canonical_identifier
  - confidence score
  - alternatives list
  - warning message

- Specified edge case handling:
  - Package maps to multiple repos: Return primary + log alternatives
  - Repo obvious but not in mapping: Use heuristic with lower confidence
  - Same term across ecosystems: Require ecosystem or return ambiguity error
  - Determinism: Same inputs always produce same result

**Why:** Removes ambiguity, provides confidence scores, handles edge cases explicitly

**Location:** Entity Normalizer component

### 4. ✅ Made feature coverage explicitly weight-based

**What changed:**
- Added "CRITICAL - Weighted Coverage Calculation" section to Feature Engineer
- Clarified that coverage = Sum(weights of available features) / Sum(all feature weights)
- Provided examples:
  - Missing minor feature (stars_count: 0.05 weight) → 95% coverage (passes)
  - Missing major category (issue metrics: 0.40+ weight) → 55% coverage (fails)
- Emphasized tracking feature CATEGORIES, not individual features
- Categories: "snapshot_metrics", "contributor_metrics", "issue_lifecycle_metrics"

**Configuration changes:**
- Updated comment: `minimum_coverage_threshold: 0.6  # 60% of WEIGHTED features required`

**Why:** Prevents minor missing features from blocking scores while catching major gaps

**Location:** Feature Engineer component, Configuration Schema

### 5. ✅ Separated summary retrieval from raw evidence retrieval

**What changed:**
- Split DB_Retriever into two methods:
  - `retrieve_summary()`: Fast, query-time (repo name, score, features, provenance)
  - `retrieve_full_evidence()`: Slower, detailed inspection (all summary + raw data)

- Added new Pydantic models:
  - RepoSummary: Summary data for query-time use
  - RepoFullEvidence: Complete evidence including raw snapshots, contributors, issues

- Updated Live_Repo_Ingestor to return RepoSummary instead of RepoResult

**Why:** Prevents query flow from becoming slower and more coupled than necessary

**Location:** DB Retriever component, Live Repo Ingestor component

### 6. ✅ Split Result Summarizer responsibilities

**What changed:**
- Added "ARCHITECTURAL NOTE" section explaining current responsibilities
- Recommended split (not mandatory for MVP):
  - Result Merger/Formatter: Combines results, formats provenance
  - Answer Generator: Generates natural language

- Added merge_results() method to interface
- Updated QueryResponse to include evidence_scope field
- Noted that single component is acceptable for MVP

**Why:** Cleaner architecture, better separation of concerns (optional for MVP)

**Location:** Result Summarizer component

### 7. ✅ Added explicit Evidence Scope concept

**What changed:**
- Added EvidenceScope Pydantic model to Data Models section
- Fields:
  - source_level: "scored_features", "raw_ingestion", or "hybrid"
  - includes_live_fetch: bool
  - includes_cached_results: bool
  - includes_database_results: bool

- Added evidence_scope field to:
  - RetrievalPlan
  - QueryResponse

**Why:** Improves trust and transparency in query results

**Location:** Data Models section, Retrieval Strategy, Result Summarizer

### 8. ✅ Added careful guidance on issue events explosion

**What changed:**
- Added "CRITICAL - Issue Events Usage Guidance" section to Issues Fetcher
- Identified which features TRULY require per-issue events:
  - avg_time_to_first_maintainer_response_days: May need events
  - median_time_to_close_days: Can use timestamps (no events)
  - fraction_issues_closed_12mo: Can use state (no events)
  - fraction_open_issues_stale_180d: Can use updated_at (no events)

- Guidance for provisional mode: Skip deep issue enrichment entirely
- Guidance for full mode: Fetch events ONLY when truly required
- Suggested capping issue history depth (e.g., last 100 issues)
- Suggested sampling for repos with 1000+ issues

**Configuration changes:**
- Added mvp_scope section:
  - enable_deep_issue_enrichment: false
  - max_issues_per_repo: 100
  - enable_hybrid_comparison: true

**Why:** Critical for rate limit goals, prevents API usage explosion

**Location:** Issues Fetcher component, Configuration Schema

### 9. ✅ Added MVP prioritization guidance

**What changed:**
- Added "MVP Prioritization" section before Phase 1
- MVP Scope (deliver first):
  1. GraphQL snapshot ingestion with adaptive batching
  2. Live fallback for single missing repo queries
  3. Provenance-aware query responses

- DEFER for post-MVP:
  1. Broader multi-repo hybrid comparison complexity
  2. Deep issue-event enrichment
  3. Advanced features (parallel ingestion, incremental updates, etc.)

**Why:** Focuses implementation on delivering core value first

**Location:** Implementation Notes section

### 10. ✅ Updated Key Design Decisions

**What changed:**
- Expanded from 6 to 10 key design decisions
- Added:
  - Adaptive GraphQL Batching (decision #2)
  - Entity Normalization with Explicit Precedence (decision #3)
  - Weighted Feature Coverage (decision #4)
  - Split Retrieval Responsibilities (decision #5)
  - Evidence Scope Tracking (decision #6)
  - Conservative Issue Events Usage (decision #8)
  - Pydantic for External Boundaries (decision #10)

**Why:** Captures all critical architectural decisions in one place

**Location:** Key Design Decisions section

### 11. ✅ Updated Solution Approach

**What changed:**
- Added paragraph on Adaptive Batching
- Added paragraph on Data Validation with Pydantic
- Emphasized conservative approach and fallback paths

**Why:** Provides high-level overview of critical changes

**Location:** Overview section

## Verification

All changes maintain:
- ✅ Existing correctness properties (35 properties unchanged)
- ✅ Requirements coverage (all 22 requirements still covered)
- ✅ Backward compatibility requirements
- ✅ Testing strategy (dual unit + property-based testing)
- ✅ Error handling strategy
- ✅ Security considerations

## Files Modified

- `.kiro/specs/github-api-optimization-query-coverage/design.md`

## Next Steps

The design document is now ready for implementation with:
1. Clear Pydantic models for all external boundaries
2. Conservative adaptive batching strategy
3. Explicit entity normalization rules
4. Weight-based feature coverage
5. Split retrieval responsibilities
6. Evidence scope tracking
7. Issue events usage guidance
8. MVP prioritization
