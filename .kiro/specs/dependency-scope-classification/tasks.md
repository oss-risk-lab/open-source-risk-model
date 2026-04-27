# Implementation Plan: Dependency Scope Classification (Phase 1 — Direct Dependencies)

## Overview

Phase 1 classifies direct dependencies only. A pure-function `ScopeClassifier` module maps manifest metadata to `(dependency_scope, scope_confidence)` tuples. Classification integrates into existing parsers, persists through the ingestion pipeline, and surfaces in API responses with `direct_`-prefixed summary counts.

Explicit non-goals: transitive scope inheritance, `resolved_dependencies` changes, UI filtering, graph filtering.

## Tasks

- [x] 1. Create ScopeClassifier module
  - [x] 1.1 Create `src/open_source_risk_model/dependencies/scope_classifier.py` with `DependencyScope` enum, `ScopeConfidence` enum, and `classify()` pure function
    - Implement all ecosystem classification rules from the design table: npm (prod/dev/optional/peer), pyproject.toml PEP 621 (dependencies, optional-dependencies, named groups dev/test/docs/lint/typecheck/tooling), pyproject.toml Poetry (main deps, dev/test/docs groups, optional/extras), requirements.txt (filename pattern matching for dev/test/docs), Cargo.toml (dependencies/dev-dependencies/build-dependencies), and fallback to (unknown, low)
    - The function must be pure, stateless, and never raise exceptions — always falls through to the default
    - Handle `dependency_group = None` defensively: normalize with `dependency_group = dependency_group or "unknown"` before classification to prevent misclassification or errors from parsers that don't set this cleanly
    - _Requirements: 2.1–2.4, 3.1–3.4, 4.1–4.5, 5.1–5.3, 6.1–6.3, 7.1–7.2_

  - [x] 1.2 Write unit tests in `test/dependencies/test_scope_classifier.py`
    - Exhaustive table-driven tests for every row in the classification rules table
    - Test fallback for unrecognized ecosystem/manifest
    - _Requirements: 15.1–15.5_

  - [x] 1.3 Write property tests in `test/dependencies/test_scope_classifier_properties.py`
    - **Property 1: Output Domain Validity** — For arbitrary string inputs to `classify()`, output is always in valid enum sets
    - **Validates: Requirements 7.2, 16.2**

  - [x] 1.4 Write property test for classification determinism
    - **Property 2: Classification Determinism** — Calling `classify()` twice with identical args produces identical results
    - **Validates: Requirements 16.1**

- [x] 2. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Integrate classification into parsers and data model
  - [x] 3.1 Add `dependency_scope` and `scope_confidence` fields to the `Dependency` dataclass in `src/open_source_risk_model/dependencies/parsers.py`
    - Default values: `dependency_scope="unknown"`, `scope_confidence="low"`
    - Update `to_dict()` to include the new fields
    - _Requirements: 9.1_

  - [x] 3.2 Update `PackageJsonParser.parse()` to call `classify()` and set scope fields on each `Dependency`
    - Pass ecosystem="npm", manifest_type="package.json", and the appropriate dependency_group
    - _Requirements: 2.1–2.4, 9.1_

  - [x] 3.3 Update `PyProjectTomlParser.parse()` to call `classify()` and set scope fields on each `Dependency`
    - Handle PEP 621 and Poetry paths, passing correct group names
    - _Requirements: 3.1–3.4, 5.1–5.3, 9.1_

  - [x] 3.4 Update `RequirementsTxtParser.parse()` to call `classify()` and set scope fields on each `Dependency`
    - Pass the source_file path for filename-based classification
    - _Requirements: 4.1–4.5, 9.1_

  - [x] 3.5 Write parser integration tests in `test/dependencies/test_parser_scope_integration.py`
    - Parse sample manifest content for each ecosystem, verify `dependency_scope` and `scope_confidence` on every `Dependency` object
    - _Requirements: 9.1, 15.1–15.4_

- [x] 4. Update database schema and persistence
  - [x] 4.1 Add `dependency_scope` and `scope_confidence` columns to `repo_dependencies` table in `src/open_source_risk_model/persistence/db.py`
    - Add migration logic in `_migrate_schema()` to ALTER TABLE with DEFAULT 'unknown' / 'low'
    - Add index `idx_repo_dependencies_scope` on `dependency_scope`
    - Update the CREATE TABLE statement to include the new columns for fresh databases
    - _Requirements: 1.1, 1.2, 1.5, 1.6_

  - [x] 4.2 Update `DependencyRepository.save_dependencies()` in `src/open_source_risk_model/persistence/dependency_repo.py` to persist `dependency_scope` and `scope_confidence`
    - Add the two fields to the INSERT statement
    - _Requirements: 9.2_

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Add scope summary counts to API responses
  - [x] 6.1 Add `direct_*` scope count fields, `scope_counts_are_direct_only`, and `scope_classification_label` to `SummaryMetrics` dataclass in `src/open_source_risk_model/tree/models.py`
    - Fields: `direct_runtime_dependency_count`, `direct_dev_dependency_count`, `direct_test_dependency_count`, `direct_build_dependency_count`, `direct_optional_dependency_count`, `direct_peer_dependency_count`, `direct_unknown_dependency_count`, `direct_total_dependency_count`, `scope_counts_are_direct_only: bool = True`, `scope_classification_label: str = "Direct dependencies, classified from manifests"`, `scope_note: str = "Dependency scope is classified from manifests and may not reflect actual runtime usage."`
    - Update `SummaryMetrics.to_dict()` to include the new fields including `scope_note`
    - _Requirements: 11.1, 14.2_

  - [x] 6.2 Update `SummaryMetricsCalculator.calculate_metrics()` in `src/open_source_risk_model/tree/metrics.py` to compute scope breakdown counts
    - Counts MUST be computed strictly from `repo_dependencies WHERE repo_id = X`. Do NOT derive counts from tree nodes, resolved_dependencies, or any join/tree logic — this prevents accidental mixing with transitive data and keeps Phase 1 clean
    - Count each dependency exactly once toward its scope bucket
    - _Requirements: 11.1, 11.2_

  - [x] 6.3 Add optional `dependency_scope` and `scope_confidence` fields to `TreeNode` in `src/open_source_risk_model/tree/models.py`
    - Include in `to_dict()` only when not None
    - _Requirements: 10.2_

  - [x] 6.4 Update `TreeService._build_canonical_tree()` in `src/open_source_risk_model/tree/service.py` to populate `dependency_scope` and `scope_confidence` on direct TreeNodes from `repo_dependencies` row data
    - _Requirements: 10.2_

  - [x] 6.5 Ensure dependency API endpoint responses include `dependency_scope` and `scope_confidence` fields
    - The `get_dependencies()` method already uses `SELECT *`, so new columns appear automatically — verify this works
    - _Requirements: 10.1_

  - [x] 6.6 Write scope count conservation property test in `test/tree/test_scope_metrics.py`
    - **Property 3: Scope Count Conservation** — Sum of all `direct_*` scope counts equals `direct_total_dependency_count`
    - **Validates: Requirements 11.1, 11.2**

  - [x] 6.7 Write existing metrics preservation property test in `test/tree/test_scope_metrics.py`
    - **Property 4: Existing Metrics Preservation** — `total_dependencies == direct_dependencies + transitive_dependencies` still holds
    - **Validates: Requirements 14.2**

- [x] 7. API response and regression tests
  - [x] 7.1 Write API response tests in `test/api/test_scope_api.py`
    - Verify scope fields appear in dependency list and tree endpoint responses
    - Verify `scope_counts_are_direct_only` is True and `scope_classification_label` is present
    - _Requirements: 10.1, 10.2, 15.6_

  - [x] 7.2 Write regression tests confirming existing `total_dependencies`, `direct_dependencies`, `transitive_dependencies` counts are unchanged
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 15.7_

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Phase 1 scope is strictly direct dependencies only — no transitive inheritance, no resolved_dependencies changes, no UI filters
