# Tasks Document Improvements Applied

## Summary

Applied critical improvements to the implementation plan based on user feedback. These changes significantly strengthen the MVP scope, reduce risk, and ensure the new system maintains parity with the existing system.

## Changes Applied

### 1. Core Property Tests Made Required for MVP

**Rationale**: These areas are most likely to quietly break and need property-based validation.

**Changed from optional to REQUIRED**:
- Task 5.2: GraphQL batching correctness (Property 3)
- Task 7.4: Feature coverage threshold enforcement (Property 35)
- Task 12.2: Retrieval strategy consistency (Properties 27, 28)
- Task 15.2: Live ingestion persistence mode enforcement (Properties 31, 32)

**Impact**: Ensures core infrastructure has robust property-based testing that validates universal correctness across all inputs.

### 2. Entity Normalization Moved Earlier

**Rationale**: The numpy/numpy/numpy issue is a known user-facing bug. Normalization affects coverage logic, so coverage logic without normalization is partially wrong.

**Changes**:
- Task 10 moved earlier in sequence (before coverage detection)
- Added explicit ambiguity handling to Task 10.1
- Added confidence threshold logic
- Added Task 10.4 for unit tests on ambiguity handling
- Updated task description to emphasize EARLY implementation

**New order**:
1. Implement query parser basics
2. Implement entity normalizer (with ambiguity handling)
3. Then coverage checker

**Impact**: Fixes known bug earlier, prevents building coverage logic on incorrect entity identification.

### 3. Issue Fetching Split into Two Tasks

**Rationale**: "Issues fetcher with conservative event usage" was doing too much. Splitting allows MVP to ship without overcommitting to event-heavy logic.

**Changes**:
- Task 6.2 split into:
  - Task 6.2a: Fetch issue metadata/comments (core MVP)
  - Task 6.2b: Optional event enrichment path (defer if needed)

**Impact**: Cleaner MVP scope, easier to defer expensive issue events if needed.

### 4. Added Benchmark Parity Validation Task

**Rationale**: One of the most important trust checks - ensures new system produces same scores as current system.

**New Task 22**: Benchmark parity validation
- Task 22.1: Select 10-20 representative repos
- Task 22.2: Run baseline with current system
- Task 22.3: Run new system on same repos
- Task 22.4: Compare and validate parity (with tolerance thresholds)
- Task 22.5: Document parity validation results

**Impact**: Protects against shipping a faster system that quietly changes the model.

### 5. Improved Checkpoint Task Descriptions

**Rationale**: "Ask the user if questions arise" can cause stalls. Better to document blockers and maintain momentum.

**Changes**: All checkpoint tasks (4, 8, 13, 18, 23) now say:
> "Ensure all tests pass. If blockers arise, document them clearly and continue with the next non-blocked task where possible."

**Impact**: Keeps implementation momentum, reduces unnecessary blocking.

### 6. Added MVP Phasing Section

**Rationale**: Clarifies the cleanest first slice for implementation.

**New Section**: MVP Phasing
- **MVP Phase A** (Core Infrastructure): API clients, rate limiter, cache, snapshot fetcher, provisional features, single repo ingestion
- **MVP Phase B** (Query Coverage): Entity normalization (EARLY), coverage checker, retrieval strategy, DB retrieval, result summarization, intent executor wiring
- **MVP Phase C** (Full Features): Full issue enrichment, hybrid multi-repo, CLI expansion, deeper compatibility

**Impact**: Clear sequencing that reduces risk.

### 7. Enhanced Notes Section

**Rationale**: Clarify which property tests are required vs optional.

**New Section**: Critical Property Tests (REQUIRED for MVP)
- Lists the 4 core property tests that are NOT optional
- Explains why they're critical
- Notes that all other property tests can be deprioritized

**Impact**: Clear guidance on what can be skipped for MVP speed vs what cannot.

### 8. Updated Key Priorities

**Added to overview**:
- "Implement entity normalization with explicit rule hierarchy EARLY (before coverage detection)"
- "Validate score parity with existing system on benchmark repos"

**Impact**: Emphasizes critical changes in implementation approach.

## Verification

All changes have been applied to `.kiro/specs/github-api-optimization-query-coverage/tasks.md`.

The implementation plan is now:
- ✅ More robust (core property tests required)
- ✅ Better sequenced (entity normalization early)
- ✅ Cleaner scope (issue fetching split)
- ✅ More trustworthy (benchmark parity validation)
- ✅ Less likely to stall (improved checkpoint descriptions)
- ✅ Clearer phasing (MVP phases defined)

## Next Steps

The tasks document is now implementation-ready. Begin with Task 1: Set up project structure and data models.
