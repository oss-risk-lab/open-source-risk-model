# Implementation Plan: Insight Layer Upgrade

## Overview

Upgrade the multi-repo Overview page interpretation layer across `api/app.py` (backend compute functions) and `ui/overview.html` (frontend render functions). All changes are additive — no scoring formulas, graph structure, API endpoints, persistence, or layout changes.

Execution order is optimized for fastest visible impact: risk summary → signals → priority fix → dependency fix → insight statements → frontend → tests.

## Tasks

- [x] 1. Extend `compute_system_risk_summary()` with explanation fields
  - [x] 1.1 Add `_generate_risk_explanation()` helper and `_generate_key_factors()` helper to `api/app.py`
    - Implement `_generate_risk_explanation(aggregate_label, high_risk_repos, vulnerable_dependencies, high_risk_dependencies, total_repos)` following the [Conclusion] + [because] + [Reason] pattern from the design
    - Implement `_generate_key_factors(aggregate_label, high_risk_repos, medium_risk_repos, vulnerable_dependencies, high_risk_dependencies, total_unique_dependencies)` returning 1–5 short strings
    - Implement `_get_recommended_action(aggregate_label)` returning the exact action string per label
    - Implement `_extract_primary_risk_factor(aggregate_label, vulnerable_dependencies, high_risk_repos, high_risk_dependencies)` returning the single dominant factor string
    - No generic fallback text allowed — all text must be data-derived (Design Decision 6)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [x] 1.2 Wire new helpers into `compute_system_risk_summary()` return dict
    - Call the four new helpers after existing metric computation
    - Add `risk_explanation`, `key_factors`, `recommended_action`, `primary_risk_factor` to the returned dict
    - Preserve all existing return fields unchanged
    - _Requirements: 2.1, 2.5, 2.7, 8.3_

  - [x] 1.3 Write property test: risk explanation pattern (Property 3) — REQUIRED
    - **Property 3: Risk explanation follows pattern and matches aggregate label**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 1.4 Write property test: key factors length invariant (Property 4) — REQUIRED
    - **Property 4: Key factors list length invariant**
    - **Validates: Requirements 2.5, 2.6**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 1.5 Write property test: recommended action mapping (Property 5) — REQUIRED
    - **Property 5: Recommended action maps to aggregate label**
    - **Validates: Requirements 2.7, 2.8, 2.9, 2.10**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 1.6 Write property test: no generic fallback text (Property 12) — REQUIRED
    - **Property 12: Risk explanation never contains generic fallback text**
    - **Validates: Design Decision 6 (No generic fallbacks)**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 1.7 Write property test: primary risk factor (Property 14) — REQUIRED
    - **Property 14: Primary risk factor is always a non-empty data-derived string**
    - **Validates: Design Decision 8 (Primary risk factor extraction)**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

- [x] 2. Refactor `get_top_risk_drivers()` to return signal objects
  - [x] 2.1 Rewrite `get_top_risk_drivers()` in `api/app.py`
    - Change signature to accept `(per_repo_results, merged_graph)`
    - Generate signal objects with `signal`, `category`, `severity` fields based on the signal generation rules table in the design
    - Guarantee at least 1 positive signal when aggregate risk is LOW
    - Handle empty `per_repo_results` by returning at least 1 info signal
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 2.2 Add explicit signal sorting step
    - After generating all signals, sort using explicit ordering dicts:
    - `severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}`
    - `category_order = {"vulnerability": 0, "maintenance": 1, "dependency": 2}`
    - Sort with: `signals.sort(key=lambda s: (severity_order[s["severity"]], category_order[s["category"]]))`
    - This ensures most critical signals always appear first — without this, ordering will be inconsistent
    - _Requirements: Design Decision 7 (Signal ordering)_

  - [x] 2.3 Update call site in `build_scope_response()` or ingestion flow to pass `merged_graph` to `get_top_risk_drivers()`
    - Find where `get_top_risk_drivers(per_repo_results)` is called and add `merged_graph` argument
    - _Requirements: 4.6, 8.3_

  - [x] 2.4 Write property test: signal structure (Property 7) — REQUIRED
    - **Property 7: Risk driver signals have valid structure**
    - **Validates: Requirements 4.1**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 2.5 Write property test: vulnerability signals (Property 8)
    - **Property 8: Vulnerability signals match vulnerability state**
    - **Validates: Requirements 4.2, 4.5**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 2.6 Write property test: maintenance signals and positive guarantee (Property 9)
    - **Property 9: Maintenance signals and positive signal guarantee**
    - **Validates: Requirements 4.3, 4.4, 4.7**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 2.7 Write property test: signal ordering (Property 13)
    - **Property 13: Risk driver signals are ordered by severity then category**
    - **Validates: Design Decision 7 (Signal ordering)**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

- [x] 3. Fix `compute_priority_risks()` for medium-risk repo guarantee
  - [x] 3.1 Add medium-risk repo candidates to `compute_priority_risks()` in `api/app.py`
    - Add "MEDIUM" risk_label repos as candidates with severity "medium" alongside existing "HIGH" repo logic
    - Ensure at least 1 priority risk item is returned when any repo has MEDIUM or HIGH risk
    - _Requirements: 3.4_

  - [x] 3.2 Write property test: priority risks guarantee (Property 6) — REQUIRED
    - **Property 6: Medium or high-risk repos guarantee non-empty priority risks**
    - **Validates: Requirements 3.4**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

- [x] 4. Fix unmapped dependency handling (active injection test)
  - [x] 4.1 Actively test and fix unmapped dependency flow in `api/app.py`
    - Create test input with dependencies: `["scikit-learn", "nonexistent-lib"]`
    - Assert each unmapped dependency:
      - appears as a node in the merged graph with `type: "package"` and empty `source_repos`
      - is counted in `total_unique_dependencies`
      - appears in `compute_top_risky_dependencies()` output with `risk_score: 0`, `risk_label: "LOW"`, `cve_count: 0`
    - If any assertion fails, fix the code path — do NOT assume it works
    - Add unit tests confirming these behaviors in `test/multi_repo/test_insight_layer_unit.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.2_

  - [x] 4.2 Write property test: unmapped deps counted (Property 1) — REQUIRED
    - **Property 1: Unmapped dependencies are counted in total_unique_dependencies**
    - **Validates: Requirements 1.1, 1.2**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 4.3 Write property test: unmapped deps default values (Property 2)
    - **Property 2: Unmapped dependencies appear in risky deps with default values**
    - **Validates: Requirements 1.3, 5.2**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

- [x] 5. Checkpoint — Verify core backend changes
  - Ensure all tests pass, ask the user if questions arise.
  - Run existing tests: `test/multi_repo/test_scope_properties.py`, `test/multi_repo/test_scope_unit.py`, `test/multi_repo/test_scope_integration.py`
  - Run new property tests: `test/multi_repo/test_insight_layer_properties.py`

- [x] 6. Implement `compute_insight_statements()` function
  - [x] 6.1 Add `compute_insight_statements()` to `api/app.py`
    - Implement the function accepting `(system_risk_summary, per_repo_results, merged_graph)`
    - Generate 1–6 interpretive strings based on the statement rules table in the design
    - Statements are interpretive ("what this means overall"), distinct from risk driver signals ("what is affecting risk")
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 6.2 Wire `compute_insight_statements()` into the ingestion flow
    - Call after `compute_system_risk_summary()` in the `POST /api/ingest-scope` handler
    - Add `insight_statements` to `build_scope_response()` return dict
    - _Requirements: 6.1, 8.3_

  - [x] 6.3 Write property test: statement count invariant (Property 10) — REQUIRED
    - **Property 10: Insight statements count invariant**
    - **Validates: Requirements 6.2, 6.7**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

  - [x] 6.4 Write property test: statement content matches conditions (Property 11)
    - **Property 11: Insight statement content matches input conditions**
    - **Validates: Requirements 6.3, 6.4, 6.5, 6.6**
    - Test file: `test/multi_repo/test_insight_layer_properties.py`

- [x] 7. Checkpoint — Verify all backend changes
  - Ensure all tests pass, ask the user if questions arise.
  - Run all existing + new backend tests

- [x] 8. Update frontend render functions in `ui/overview.html`
  - [x] 8.1 Update `renderRiskSummary()` to display new fields
    - Render `primary_risk_factor` as bold text under the risk badge
    - Render `risk_explanation` as a paragraph below the primary risk factor
    - Render `key_factors` as a row of small tag/chip elements using existing CSS patterns
    - Render `recommended_action` as a call-to-action line
    - Render `insight_statements` in a light background box with italic text
    - Check for field existence before rendering (backward compatibility)
    - _Requirements: 7.1, 7.2, 7.3, 7.8_

  - [x] 8.2 Update `renderPriorityRisks()` with contextual empty states
    - Replace generic "No priority risks identified." with risk-level-aware messages per the design's Priority Risk Empty State Messages table
    - LOW: "No priority risks found — your system shows low risk across all analyzed components."
    - MEDIUM: "No critical risks identified, but your system shows moderate risk that warrants monitoring."
    - HIGH: "Risk data is being evaluated. Review individual repository insights for detailed analysis."
    - _Requirements: 3.1, 3.2, 3.3, 7.5_

  - [x] 8.3 Update `renderRiskDrivers()` to render signal cards
    - Replace repo-list rendering with signal card rendering
    - Each card shows: signal text, category badge (using existing type-badge CSS), severity indicator (using existing severity-badge CSS)
    - Add graceful degradation: check for `signal` field; if absent, fall back to rendering repo name (backward compatibility with old format)
    - _Requirements: 4.1, 7.6_

  - [x] 8.4 Update `renderRiskyDeps()` with contextual empty states
    - When empty: "No risky dependencies identified across your analyzed components."
    - When all low-risk: "All analyzed dependencies show low risk — no immediate concerns."
    - _Requirements: 5.1, 5.3, 7.7_

- [x] 9. Checkpoint — Verify frontend changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Write backend unit tests
  - [x] 10.1 Write unit tests for risk explanation, key factors, recommended action, and primary risk factor
    - Test LOW with no vulnerabilities produces expected explanation text
    - Test HIGH with 3 vulnerable deps produces expected explanation text
    - Test recommended action exact string matching for each label
    - Test primary risk factor selection priority
    - Test file: `test/multi_repo/test_insight_layer_unit.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 2.9, 2.10_

  - [x] 10.2 Write unit tests for signal-based risk drivers
    - Test signal generation with zero repos (edge case)
    - Test signal ordering by severity then category
    - Test positive signal guarantee for LOW aggregate
    - Test file: `test/multi_repo/test_insight_layer_unit.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7_

  - [x] 10.3 Write unit tests for insight statements
    - Test all-healthy system produces stability statement
    - Test mixed risk levels produce appropriate statements
    - Test statement count bounds (1–6)
    - Test file: `test/multi_repo/test_insight_layer_unit.py`
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 11. Write frontend tests
  - [x] 11.1 Write frontend tests for updated render functions
    - Test `renderRiskSummary()` displays risk_explanation, key_factors tags, recommended_action, insight_statements
    - Test `renderPriorityRisks()` shows contextual empty state for each risk level
    - Test `renderRiskDrivers()` renders signal cards with category badges and severity indicators
    - Test `renderRiskyDeps()` shows contextual empty state messages
    - Test graceful degradation when new fields are missing from data
    - Test file: `test/ui/test_overview_upgrade.js`
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6, 7.7, 7.8_

- [x] 12. Final checkpoint — Verify all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run all new tests: `test/multi_repo/test_insight_layer_properties.py`, `test/multi_repo/test_insight_layer_unit.py`, `test/ui/test_overview_upgrade.js`
  - Run all existing tests: `test/multi_repo/test_scope_properties.py`, `test/multi_repo/test_scope_unit.py`, `test/multi_repo/test_scope_integration.py`
  - Confirm no existing behavior is broken (Requirements 8.1–8.6)

## Notes

- Core property tests (Properties 1, 3, 4, 5, 6, 7, 10, 12, 14) are REQUIRED — these validate the fundamental correctness guarantees
- Tasks marked with `*` are optional — these cover edge cases, extra ordering checks, and supplementary unit/frontend tests
- Execution order optimized for fastest visible impact: risk summary (1) → signals (2) → priority fix (3) → deps fix (4) → checkpoint (5) → insight statements (6) → frontend (8) → tests (10–11)
- Signal sorting uses explicit ordering dicts: `severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}`, `category_order = {"vulnerability": 0, "maintenance": 1, "dependency": 2}`
- Dependency verification is active injection testing, not passive confirmation — assert real inputs produce expected outputs
