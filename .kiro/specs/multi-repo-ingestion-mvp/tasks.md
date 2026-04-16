# Implementation Plan: Multi-Repo Ingestion MVP

## Overview

Transform Deep Signal from single-repo analysis into a multi-repo system risk analyzer. Backend adds two endpoints to `api/app.py` (synchronous POST /api/ingest-scope + GET /api/scope/{scope_id}) with in-memory scope storage, graph merging, and priority risk scoring. Frontend adds a multi-repo toggle on the homepage, a new `overview.html` page, nav update, and scope-aware behavior on graph/tree pages. All backend in Python (FastAPI), all frontend in vanilla HTML/CSS/JS.

## Development Rules

- Backend is fully synchronous — POST /api/ingest-scope returns HTTP 200 with complete results, no polling
- In-memory scope store only — scopes lost on restart, acceptable for MVP
- Dependency-to-repo mapping is best-effort via hardcoded dict — may be incomplete
- Existing single-repo flows MUST remain fully functional (backward compatibility)
- Frontend is vanilla HTML/CSS/JS — no framework, no build step

## Tasks

- [x] 1. Backend core: scope models, graph merger, dependency resolver, and risk computation functions
  - [x] 1.1 Add scope data structures and helper functions to `api/app.py`
    - Add `SCOPE_STORE: Dict[str, dict] = {}` module-level dict
    - Add `PACKAGE_TO_REPO` hardcoded mapping dict (flask, requests, sqlalchemy, django, numpy, pandas, fastapi, express, react, lodash, axios, scikit-learn)
    - Add `IngestScopeRequest` and `IngestScopeResponse` Pydantic models
    - Add `_generate_scope_id()` function returning unique string IDs
    - Add `_risk_label_from_score(score)` if not already present (LOW < 0.30, MEDIUM 0.30–0.59, HIGH ≥ 0.60)
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

  - [x] 1.2 Implement `resolve_dependency_input()` helper function
    - Accept a dependency name string
    - Look up in PACKAGE_TO_REPO mapping
    - If mapped: return `{"kind": "repo", "repo": "owner/repo", "package_name": dep, "mapped": True}`
    - If unmapped: return `{"kind": "package_only", "repo": None, "package_name": dep, "mapped": False}`
    - This keeps dependency resolution logic isolated from the endpoint
    - _Requirements: 2.9_

  - [x] 1.3 Implement `merge_graphs()` function
    - Accept `List[Tuple[str, graph_object]]` and `List[dict]` unmapped nodes
    - Deduplicate nodes by `node.id`, first occurrence wins for properties
    - Add `source_repos` list to each merged node tracking contributing repos
    - Deduplicate edges by `(source, target, relationship_type)` tuple — different relationship types between the same node pair are PRESERVED, never collapsed
    - Append unmapped dependency nodes as standalone package nodes
    - Return merged graph dict with `nodes` and `edges` lists
    - _Requirements: 2.6, 2.7_

  - [x] 1.4 Implement `compute_system_risk_summary()` function
    - Accept per_repo_results list and merged_graph dict
    - Compute repo-level metrics: total_repos, high/medium/low counts, per_repo breakdown
    - Compute dependency-level metrics: total_unique_dependencies, dependencies_used_by_multiple_repos, high_risk_dependencies (risk_score ≥ 0.60), vulnerable_dependencies (cve_count > 0)
    - Compute aggregate_risk_score as arithmetic mean of non-error repo risk scores (intentionally simple for MVP)
    - Compute aggregate_label using standard thresholds
    - Generate system_summary sentence (human-readable 1–2 sentences)
    - _Requirements: 2.8_

  - [x] 1.5 Implement `compute_priority_risks()` function
    - Gather candidates: high-risk repos, deps with CVEs, deps used by many repos, single-maintainer repos
    - Score each: `priority_score = SEVERITY_BASE[severity] + (usage_count * 0.5) + (cve_count * 1.0)`
    - Sort descending by priority_score, return top 3–5 items
    - Each item: `{name, type, reason, severity, priority_score, used_by_repos}`
    - _Requirements: 2.11_

  - [x] 1.6 Implement `compute_top_risky_dependencies()` function
    - Separate from `compute_priority_risks()` — purpose-built for dependency cards in the UI
    - Extract dependency nodes from merged graph
    - Score each dependency: prioritize high severity/risk, CVE count, then breadth of usage across repos
    - Sort by combined score descending, return top 5–10
    - Each item: `{package_name, risk_score, risk_label, used_by_repos, cve_count, priority_score}`
    - _Requirements: 5.5_

  - [x] 1.7 Implement `compute_scope_status()` function
    - All succeed → "complete", all fail → "failed", mixed → "partial"
    - _Requirements: 1.5, 2.10_

  - [x] 1.8 Implement `get_top_risk_drivers()` function
    - Sort non-error per_repo_results by risk_score descending, return top 5
    - Each item: `{repo, risk_score, risk_label}`
    - _Requirements: 5.4_

  - [x] 1.9 Define and document scope response schema
    - Define the exact JSON shape returned by both POST /api/ingest-scope and GET /api/scope/{scope_id}
    - Required top-level fields: scope_id, name, status, system_risk_summary, priority_risks, top_risk_drivers, top_risky_dependencies, graph, errors
    - Create a `ScopeResponse` Pydantic model or explicit dict builder function that enforces this shape
    - This is the contract between backend and frontend — must be stable
    - _Requirements: 3.1_

  - [x] 1.10 Write property tests for `merge_graphs()`
    - **Property 3: Graph merge deduplication and source tracking**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 2.6, 2.7**

  - [x] 1.11 Write property tests for `compute_system_risk_summary()`
    - **Property 4: System risk summary correctness**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 2.8**

  - [x] 1.12 Write property tests for `compute_scope_status()`
    - **Property 5: Status computation from processing outcomes**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 2.10**

  - [x] 1.13 Write property tests for `compute_priority_risks()`
    - **Property 6: Priority risk ranking by score**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 2.11**

  - [x] 1.14 Write property tests for dependency resolution (mapped vs unmapped)
    - **Property 7: Dependency resolution — mapped vs unmapped**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 2.9**

  - [x] 1.15 Write property tests for `get_top_risk_drivers()`
    - **Property 8: Top risk drivers sorting**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 5.4**

- [x] 2. Checkpoint — Verify all pure computation functions and core property tests pass
  - Ensure merge_graphs, compute_system_risk_summary, and compute_scope_status property tests pass (these are required, not optional)
  - Ask the user if questions arise.

- [x] 3. Backend endpoints: POST /api/ingest-scope and GET /api/scope/{scope_id}
  - [x] 3.1 Implement `POST /api/ingest-scope` endpoint in `api/app.py`
    - Validate: repos + dependencies not both empty → 422; repos length ≤ 10 (MVP performance constraint) → 422; repo format via `_normalize_repo_name()`
    - Generate scope_id, store initial scope in SCOPE_STORE
    - Synchronous processing loop: for each repo call `score_repo()`, `build_graph()`, `compute_repo_insight()`, collect results
    - For each dependency: call `resolve_dependency_input()`, if mapped → run full pipeline, if unmapped → create graph-only package node
    - Call `merge_graphs()`, `compute_system_risk_summary()`, `compute_priority_risks()`, `compute_top_risky_dependencies()`, `compute_scope_status()`, `get_top_risk_drivers()`
    - Build response using the scope response schema from task 1.9
    - Store complete results in SCOPE_STORE, return HTTP 200 with full response
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.9, 2.10_

  - [x] 3.2 Implement `GET /api/scope/{scope_id}` endpoint in `api/app.py`
    - Look up scope_id in SCOPE_STORE
    - Return full scope object using same response schema, 404 if not found
    - _Requirements: 3.1, 3.2_

  - [x] 3.3 Write property tests for scope creation round-trip and ID uniqueness
    - **Property 1: Scope creation round-trip**
    - **Property 2: Scope ID uniqueness**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 1.1, 1.2, 3.1**

  - [x] 3.4 Write property test for oversized repo list rejection
    - **Property 9: Oversized repo list rejection**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 2.3**

  - [x] 3.5 Write property test for partial failure resilience
    - **Property 10: Partial failure resilience**
    - Test file: `test/multi_repo/test_scope_properties.py`
    - **Validates: Requirements 2.5**

  - [x] 3.6 Write unit tests for endpoints
    - Test file: `test/multi_repo/test_scope_unit.py`
    - POST returns 200 with valid input and response matches schema
    - POST returns 422 for empty input
    - POST returns 422 for >10 repos
    - GET returns 404 for unknown scope_id
    - Priority score formula correctness
    - Dependency resolution: mapped → full pipeline, unmapped → graph-only
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [x] 3.7 Write integration tests with mocked pipelines
    - Test file: `test/multi_repo/test_scope_integration.py`
    - Full endpoint flow with mocked `score_repo` and `build_graph`
    - Partial failure scenario (one repo fails, others succeed)
    - Dependency resolution with mixed mapped/unmapped packages
    - System summary sentence generation
    - _Requirements: 8.4, 8.7_

- [x] 4. Checkpoint — Verify backend endpoints work end-to-end with tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Frontend: Homepage multi-repo toggle
  - [x] 5.1 Add multi-repo mode toggle and input UI to `ui/index.html`
    - Add segmented control (two-button toggle) in hero section: "Single Repo" (default) / "Multi-Repo"
    - Single Repo mode: existing input + "Scan a Repository" button (unchanged)
    - Multi-Repo mode: textarea for repos (one per line), scope name input, optional dependencies textarea, "Analyze System" button
    - Toggle shows/hides appropriate input group
    - CSS for toggle control and multi-repo inputs using design system tokens
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.2 Add multi-repo submission logic to `ui/index.html`
    - "Analyze System" button sends POST to `/api/ingest-scope` with name, repos, dependencies
    - On success (200): redirect to `overview.html?scope_id={scope_id}`
    - On error: display error message inline without navigating
    - Show loading state on button during request
    - _Requirements: 4.5, 4.6_

  - [x] 5.3 Verify single-repo mode backward compatibility
    - Confirm existing "Scan a Repository" flow still works unchanged
    - Confirm navigation to insights.html?repo=... still works
    - Confirm no regressions in single-repo input validation or focus behavior
    - _Requirements: 4.2_

- [x] 6. Frontend: Navigation update
  - [x] 6.1 Update `ui/nav.js` to add Overview page and scope_id propagation
    - Add `{ pageId: "overview", label: "Overview", file: "overview.html" }` to NAV_PAGES between Home and Insights
    - Add `parseScopeParam(searchString)` function to extract scope_id from URL
    - Update `buildPageUrl()` to accept and propagate scope_id parameter
    - Update `renderNav()` to propagate scope_id to Overview, Graph, and Tree links when present
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 7. Frontend: Overview page
  - [x] 7.1 Create `ui/overview.html` with page structure and data loading
    - Follow same pattern as insights.html: load design-system.css, nav.js, config.js
    - Read scope_id from URL query params
    - Fetch GET /api/scope/{scope_id} (single fetch, no polling)
    - Error states: missing scope_id → error with link to homepage; 404 → error message
    - Loading state with spinner while fetching
    - _Requirements: 5.1, 5.7, 5.8_

  - [x] 7.2 Implement System Risk Summary section at top of overview page
    - Large risk label badge (LOW/MEDIUM/HIGH) as most prominent element
    - 1–2 sentence system summary text below the badge
    - This is the product centerpiece — immediate understanding of system risk
    - _Requirements: 5.2_

  - [x] 7.3 Implement KPI cards section
    - Cards: total repos analyzed, total unique dependencies, high-risk dependencies, vulnerable dependencies, aggregate risk score with label
    - Use ds-card and ds-kpi design system classes
    - _Requirements: 5.2_

  - [x] 7.4 Implement Priority Risks section
    - Render top 3–5 priority risk items
    - Each shows: name, type badge (dependency/repo/maintainer/CVE), reason, severity, "used by X repos" where applicable
    - Sorted by priority_score descending
    - _Requirements: 5.3_

  - [x] 7.5 Implement Top Risk Drivers section
    - Top 5 repos by descending risk score
    - Each shows: repo name (clickable → insights page), risk label, risk score
    - _Requirements: 5.4, 5.9_

  - [x] 7.6 Implement Risky Dependencies section
    - Uses data from `compute_top_risky_dependencies()` (purpose-built for dependency cards, NOT just filtered priority_risks)
    - Prioritizes: high severity/risk, CVE count, breadth of usage across repos
    - Each shows: package name, risk score, used_by_repos list, CVE count
    - "Used by X repos" shown prominently on every dependency card
    - _Requirements: 5.5_

  - [x] 7.7 Add action links: "Open Graph" and "Open Dependency Tree" with scope_id
    - Links navigate to graph.html?scope_id=... and dependency-tree.html?scope_id=...
    - _Requirements: 5.1_

  - [x] 7.8 Add partial results warning banner
    - If status is "partial", show warning banner listing failed repos
    - _Requirements: 5.6_

- [x] 8. Checkpoint — Verify overview page renders correctly with backend data
  - Ensure all sections render with real or mocked scope data
  - Ask the user if questions arise.

- [x] 9. Frontend: Scope-aware graph and tree pages
  - [x] 9.1 Update `ui/graph-viz.js` and `ui/graph.html` for scope_id support
    - When `scope_id` is present in URL: fetch merged graph from GET /api/scope/{scope_id}
    - Hide single-repo input controls
    - Display scope name as page title
    - Render merged graph using existing vis.js visualization
    - Maintain backward compatibility: when `repo` param is present, use existing single-repo behavior
    - _Requirements: 7.1, 7.3_

  - [x] 9.2 Update `ui/dependency-tree.js` and `ui/dependency-tree.html` for scope_id support
    - When `scope_id` is present in URL: fetch scope data from GET /api/scope/{scope_id}
    - Build combined tree from merged graph data (NOTE: may need adapter layer if tree logic expects different data shape than merged graph provides)
    - Hide single-repo input controls
    - Display scope name as page title
    - Maintain backward compatibility: when `repo` param is present, use existing single-repo behavior
    - _Requirements: 7.2, 7.3_

- [x] 10. Backward compatibility verification
  - [x] 10.1 Verify existing single-repo flows still work
    - Homepage "Scan a Repository" → insights.html?repo=... works unchanged
    - graph.html?repo=... loads single-repo graph correctly
    - dependency-tree.html?repo=... loads single-repo tree correctly
    - Navigation links with ?repo= param still propagate correctly
    - No regressions in any existing page behavior

- [x] 11. Frontend tests
  - [x] 11.1 Write frontend tests for overview page logic
    - Test file: `test/ui/test_overview_logic.js`
    - KPI computation from scope data
    - Priority risk rendering with used_by_repos
    - Top risk drivers sorting
    - Error display for missing scope_id
    - System risk summary sentence display
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 12. Final checkpoint — Full integration verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify POST /api/ingest-scope returns 200 with complete results matching defined response schema
  - Verify graph merging deduplicates nodes by ID with source_repos tracking
  - Verify edges deduplicated by (source, target, type) — different types preserved
  - Verify priority_score formula: SEVERITY_BASE[severity] + (usage_count * 0.5) + (cve_count * 1.0)
  - Verify aggregate score is arithmetic mean of non-error repo scores
  - Verify overview page has System Risk Summary sentence at top, KPIs, Priority Risks, Top Risk Drivers, Risky Dependencies
  - Verify Risky Dependencies uses purpose-built scoring (not just filtered priority_risks)
  - Verify nav has "Overview" between "Home" and "Insights" with scope_id propagation
  - Verify graph/tree pages support ?scope_id= for merged data
  - Verify existing single-repo flows (homepage, insights, graph, tree) still work unchanged
  - Verify no polling on frontend — single fetch on page load

## Notes

- Tasks 1.10, 1.11, 1.12 (property tests for merge_graphs, system_risk_summary, scope_status) are REQUIRED — these protect the core invariants
- Tasks marked with `*` are optional and can be skipped for faster MVP
- Backend is fully synchronous — POST /api/ingest-scope returns HTTP 200 with complete results, no polling
- In-memory scope store only — scopes lost on restart, acceptable for MVP
- Frontend is vanilla HTML/CSS/JS — no framework, no build step
- Task 9.2 (dependency tree scope mode) may need an adapter layer — watch for data shape mismatches between merged graph and tree expectations
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
