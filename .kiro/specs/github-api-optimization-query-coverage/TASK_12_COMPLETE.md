# Task 12 Complete: Retrieval Strategy Selection

## Summary

Successfully implemented Task 12 from the GitHub API Optimization and Query Coverage spec, delivering retrieval strategy selection with comprehensive property-based testing.

## Implementation Details

### Files Created

1. **src/open_source_risk_model/query/retrieval_strategy.py**
   - `RetrievalStrategy` class with `select_strategy()` method
   - Strategy selection logic based on coverage mode
   - Cost classification (low/medium/high)
   - Evidence scope creation
   - User preference handling (provisional vs full mode)

2. **test/query/test_retrieval_strategy.py**
   - 19 unit tests covering all scenarios
   - Tests for database_only, live_ingestion_required, and hybrid modes
   - Tests for user preferences (provisional vs full)
   - Tests for cost classification logic
   - Tests for evidence scope creation
   - Edge case handling (empty preferences, invalid modes)

3. **test/query/test_retrieval_strategy_properties.py**
   - 6 property-based tests with 100 iterations each
   - **Property 27**: Retrieval Strategy Consistency (REQUIRED FOR MVP)
   - **Property 28**: Score Mode Propagation (REQUIRED FOR MVP)
   - Additional properties for cost classification, evidence scope, defaults, and determinism

## Test Results

All tests pass successfully:
- **19 unit tests**: 100% pass rate
- **6 property tests**: 100% pass rate (600 total iterations)
- **Total**: 25 tests, 0 failures

## Key Features Implemented

### 1. Strategy Selection Logic

The `select_strategy()` method correctly implements the following logic:

- **database_only mode** → use DB_Retriever only
- **live_ingestion_required mode** → use Live_Repo_Ingestor only  
- **hybrid mode** → use both DB_Retriever and Live_Repo_Ingestor

### 2. User Preference Handling

- Respects `score_mode` preference from user
- Defaults to "provisional" (fast) when not specified
- Configures Live_Repo_Ingestor mode accordingly:
  - `score_mode: "provisional"` → `live_ingestion_mode: "provisional"`
  - `score_mode: "full"` → `live_ingestion_mode: "full"`

### 3. Cost Classification

Internal cost classification for logging and optional UI use:

- **Low**: database_only mode
- **Medium**: hybrid or live_ingestion with provisional mode
- **High**: live_ingestion with full mode

### 4. Evidence Scope Tracking

Creates `EvidenceScope` object to track data sources:

- `source_level`: "scored_features", "raw_ingestion", or "hybrid"
- `includes_live_fetch`: Whether live ingestion is used
- `includes_cached_results`: Set to False (updated by cache manager)
- `includes_database_results`: Whether database retrieval is used

### 5. Repository Lists

Correctly extracts and returns:

- `repos_from_database`: List of repo names from `in_database` status objects
- `repos_for_ingestion`: List of repo names from `missing` list
- Invalid repos are excluded from both lists

## Property Test Validation

### Property 27: Retrieval Strategy Consistency ✓

Validates that for any coverage mode, the selected strategy matches expectations:
- database_only → DB_Retriever only
- live_ingestion_required → Live_Repo_Ingestor only
- hybrid → both retrievers

Tested across 100 random coverage scenarios.

### Property 28: Score Mode Propagation ✓

Validates that user score mode preference is correctly propagated to live ingestion mode:
- "provisional" → provisional mode
- "full" → full mode

Tested across 100 random coverage and preference combinations.

## Requirements Validated

This implementation validates the following requirements from the spec:

- **Requirement 9.1**: database_only mode uses DB_Retriever
- **Requirement 9.2**: live_ingestion_required mode uses Live_Repo_Ingestor
- **Requirement 9.3**: hybrid mode uses both retrievers
- **Requirement 9.4**: provisional score preference is respected
- **Requirement 9.5**: full score preference is respected
- **Requirement 9.6**: Cost classification for internal logging

## Design Compliance

The implementation follows all design specifications:

1. ✓ Uses Pydantic models (`RetrievalPlan`, `EvidenceScope`)
2. ✓ Implements cost classification (low/medium/high)
3. ✓ Creates evidence scope for tracking data sources
4. ✓ Defaults to provisional mode (fast)
5. ✓ Handles user preferences correctly
6. ✓ Extracts repository lists from coverage report
7. ✓ Excludes invalid repositories from retrieval plan

## Integration Points

The `RetrievalStrategy` class integrates with:

- **Input**: `CoverageReport` from `CoverageChecker`
- **Input**: User preferences dictionary
- **Output**: `RetrievalPlan` for query execution
- **Dependencies**: `EvidenceScope` from ingestion models

## Next Steps

Task 12 is complete. The next task in the spec is:

- **Task 13**: Checkpoint - Ensure all tests pass
- **Task 14**: Implement database retrieval with split responsibilities

## Notes

- All property tests are marked as REQUIRED FOR MVP per the spec
- Property tests run 100 iterations each to ensure robustness
- Cost classification is internal only (not exposed to users)
- Evidence scope's `includes_cached_results` will be updated by cache manager
- Implementation is deterministic - same inputs always produce same outputs
