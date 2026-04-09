# Implementation Plan: Insight Layer

## Overview

This plan implements the Insight Layer as defined in the design document. The layer reads stored graph JSON, extracts three direct signals, evaluates them against bucketed thresholds, and produces a `RepoInsight` output. All computation is on-demand with no persistence. The implementation builds on existing `graph_signals.py` and `models.py`.

## Task List

- [x] 1 Update CVSS severity extraction with fallback chain
  - [x] 1.1 Add `_severity_from_cvss_score()` function to `graph_signals.py` that maps numeric CVSS score to severity bucket (≥9.0→critical, ≥7.0→high, ≥4.0→medium, <4.0→low)
  - [x] 1.2 Add `_extract_severity_bucket()` function to `graph_signals.py` implementing the three-step fallback: normalized cvss_score → CVSS vector parse → None (count-only)
  - [x] 1.3 Update `extract_cve_signal()` to use `_extract_severity_bucket()` instead of calling `_parse_cvss_severity()` directly
  - [x] 1.4 Write unit tests in `test/insights/test_graph_signals.py` covering all three fallback steps and the count-only case

- [x] 2 Create risk rule evaluators
  - [x] 2.1 Create `src/open_source_risk_model/insights/risk_rules.py` with `evaluate_cve_risk()` function implementing Req 4 thresholds, populating metadata: `{"total_count": N, "has_critical": bool, "has_high": bool, "cve_ids": [...]}`
  - [x] 2.2 Add `evaluate_maintainer_risk()` function implementing Req 5 thresholds (>0.8→high/0.3, >0.65→medium/0.15, >0.5→mild/0.05, ≤0.5→info/0.0), populating metadata: `{"top_contributor_username": str, "top_contributor_fraction": float, "human_maintainer_count": int}`
  - [x] 2.3 Add `evaluate_release_risk()` function implementing Req 6 thresholds, ensuring absence of release metadata produces score_contribution 0.0, populating metadata: `{"days_since_latest": int|None, "has_releases": bool, "latest_tag": str|None, "total_releases": int}`
  - [x] 2.4 Write unit tests in `test/insights/test_risk_rules.py` covering all threshold boundaries, edge cases, and metadata population
  - [x] 2.5 Write property-based tests in `test/insights/test_risk_rules_properties.py` verifying: every SignalEvidence has non-empty reason, score_contribution is always 0.0–0.4, no positive score from missing release data, metadata dict is always populated

- [x] 3 Create insight engine orchestrator
  - [x] 3.1 Create `src/open_source_risk_model/insights/compute.py` with `compute_repo_insight(repo_full_name: str, graph_repo: GraphRepository)` — no db_path parameter; GraphRepository is required via dependency injection
  - [x] 3.2 Add `_has_meaningful_graph()` helper implementing the "no graph data" definition: get_graph() returns None, OR graph dict has no "nodes" key, OR "nodes" list is empty. A stub graph with only a root repo node (node_count=1) IS valid.
  - [x] 3.3 Implement `extract_base_risk()` fallback behavior: if repo node is absent or `maintenance_risk`/`maintenance_label` fields are missing, default to `maintenance_risk=None` and `maintenance_label=None`
  - [x] 3.4 Implement signal extraction → rule evaluation → score computation pipeline with deterministic signal ordering (cve_risk, maintainer_concentration, release_staleness)
  - [x] 3.5 Implement graph_signal_score as capped additive sum and label assignment (HIGH≥0.6, MEDIUM≥0.3, LOW otherwise)
  - [x] 3.6 Handle the case where graph has no meaningful data: return default RepoInsight with reason "No graph data available"
  - [x] 3.7 Add a unit test that reads `compute.py` source and asserts it does not import `score_repo` or any ingestion module (concrete no-rescoring invariant check)
  - [x] 3.8 Write unit tests in `test/insights/test_compute.py` covering: full pipeline, missing graph, empty nodes list, stub graph with single repo node, malformed graph JSON (e.g. `{"nodes": "not-a-list"}`), base risk defaults when repo node lacks fields, deterministic ordering
  - [x] 3.9 Write property-based tests in `test/insights/test_compute_properties.py` verifying: score bounded 0.0–1.0, label thresholds, reasons count matches non-info signals, deterministic signal order

- [x] 4 Add insights API endpoint
  - [x] 4.1 Add `_repo_exists_in_db()` helper to `api/app.py` that checks for row existence in `repo_graphs`
  - [x] 4.2 Add `GET /api/insights/{owner}/{repo}` endpoint that creates a single GraphRepository and passes it to `compute_repo_insight()`, distinguishing: repo not in DB → 404, repo exists but no meaningful graph → 200 with default insight, repo with graph → 200 with computed insight. Log unexpected exceptions at ERROR level before returning 500.
  - [x] 4.3 Write integration tests in `test/insights/test_api_endpoint.py` covering 200, 404, and 500 responses

- [x] 5 Create batch compute-and-print script
  - [x] 5.1 Create `scripts/compute_all_insights.py` that creates a single GraphRepository instance, iterates all repos, passes the shared instance to each `compute_repo_insight()` call, and prints summary per repo
  - [x] 5.2 Implement error handling: log per-repo errors and continue, print final summary with total/success/failed counts
  - [x] 5.3 Verify script does not persist insights to any database table

- [x] 6 Serialization and round-trip tests
  - [x] 6.1 Write tests in `test/insights/test_models.py` verifying to_dict() round-trip: serialize → construct → serialize produces identical output
  - [x] 6.2 Write tests in `test/insights/test_models.py` verifying to_dict() rounding: graph_signal_score and score_contribution have at most 3 decimal places
  - [x] 6.3 Write tests verifying direct_signals serialization order is deterministic (cve_risk, maintainer_concentration, release_staleness)
  - [x] 6.4 Write test verifying top_risky_dependencies defaults to empty list in v1
