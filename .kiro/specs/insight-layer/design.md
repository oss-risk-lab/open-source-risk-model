# Design: Insight Layer

## Architecture Overview

The Insight Layer is a read-only, compute-on-demand interpretation layer that sits between the stored graph data and API consumers. It reads graph JSON from `repo_graphs.graph_json`, extracts three direct signals (CVE risk, maintainer concentration, release staleness), evaluates them against bucketed thresholds, and assembles a `RepoInsight` output. No data is persisted; no external APIs are called; no scoring/ingestion logic is invoked.

```
[repo_graphs.graph_json (SQLite)]
        ↓ (read only)
[Insight_Engine (compute.py)]
    ├── extract_cve_signal()         → CVESignal
    ├── extract_maintainer_signal()  → MaintainerSignal
    ├── extract_release_signal()     → ReleaseSignal
    ├── extract_base_risk()          → BaseRiskSignal
    ├── evaluate_cve_risk()          → SignalEvidence
    ├── evaluate_maintainer_risk()   → SignalEvidence
    └── evaluate_release_risk()      → SignalEvidence
        ↓
[RepoInsight] → to_dict() → JSON response
```

Key architectural constraints:
- The Insight_Engine SHALL NOT invoke `score_repo()` or any external scoring/ingestion logic (Req 7.9).
- The Insight_Engine trusts pre-computed values (e.g., `contribution_fraction`) stored on graph nodes (Req 2.2).
- All computation uses full floating-point precision; rounding to 3 decimal places occurs only in `to_dict()` serialization (Req 8.3).
- `direct_signals` are always ordered: cve_risk, maintainer_concentration, release_staleness (Req 7.10, 11.4).
- `top_risky_dependencies` defaults to an empty list in v1 (Req 11.5).
- Neither the API endpoint nor the batch script persists insights to a table (Req 10.5).

## Data Models

### File: `src/open_source_risk_model/insights/models.py` (existing, minor updates)

The existing `RepoInsight`, `SignalEvidence`, and `DependencyRisk` dataclasses are already implemented. No structural changes needed. The `to_dict()` method already rounds to 3 decimal places.

All three rule evaluators populate the `metadata` dict on `SignalEvidence` from day one:
- CVE: `{"total_count": N, "has_critical": bool, "has_high": bool, "cve_ids": [...]}`
- Maintainer: `{"top_contributor_username": str, "top_contributor_fraction": float, "human_maintainer_count": int}`
- Release: `{"days_since_latest": int|None, "has_releases": bool, "latest_tag": str|None, "total_releases": int}`

The `to_dict()` method does NOT serialize `metadata` in v1 (keeps the API surface minimal), but the data is available internally for debugging and future use.

### File: `src/open_source_risk_model/insights/graph_signals.py` (existing, updates for CVSS fallback)

The existing signal dataclasses (`CVESignal`, `MaintainerSignal`, `ReleaseSignal`, `BaseRiskSignal`) and extraction functions are already implemented. Updates needed:

1. **CVSS severity fallback chain** (Req 1.2–1.4): Update `extract_cve_signal()` to implement the three-step fallback:
   - Step 1: Check for normalized `cvss_score` field → map to severity bucket
   - Step 2: If no `cvss_score`, check for CVSS vector string → parse to bucket
   - Step 3: If neither, count-only (no severity bucketing, no `has_critical`/`has_high` flags set for this node)

```python
def _severity_from_cvss_score(score: float | None) -> str | None:
    """Map numeric CVSS score to severity bucket."""
    if score is None:
        return None
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


def _extract_severity_bucket(meta: dict) -> str | None:
    """Three-step fallback chain for severity extraction (Req 1.2-1.4).
    
    1. Normalized cvss_score field → map to bucket
    2. CVSS vector string → parse to bucket  
    3. Neither → return None (count-only)
    """
    # Step 1: normalized severity field
    cvss_score = meta.get("cvss_score")
    if cvss_score is not None:
        try:
            return _severity_from_cvss_score(float(cvss_score))
        except (ValueError, TypeError):
            pass
    
    # Step 2: CVSS vector string
    severity_str = meta.get("severity", "")
    if severity_str:
        bucket = _parse_cvss_severity(severity_str)
        if bucket:
            return bucket
    
    # Step 3: count-only fallback
    return None
```

Updated `extract_cve_signal()` uses `_extract_severity_bucket()` instead of calling `_parse_cvss_severity()` directly.

## Component Design

### 1. Risk Rule Evaluators

**File**: `src/open_source_risk_model/insights/risk_rules.py` (new)
**Implements**: Req 4, 5, 6

Three pure functions that take signal dataclasses and return `SignalEvidence`.

```python
from .graph_signals import CVESignal, MaintainerSignal, ReleaseSignal
from .models import SignalEvidence


def evaluate_cve_risk(signal: CVESignal) -> SignalEvidence:
    """Evaluate CVE signal into risk evidence (Req 4.1-4.4)."""
    meta = {
        "total_count": signal.total_count,
        "has_critical": signal.has_critical,
        "has_high": signal.has_high,
        "cve_ids": signal.cve_ids,
    }
    if signal.has_critical or signal.has_high:
        return SignalEvidence(
            signal_name="cve_risk",
            severity="high",
            score_contribution=0.4,
            reason=f"{signal.total_count} CVE(s) found, including critical/high severity",
            metadata=meta,
        )
    if signal.total_count > 0:
        return SignalEvidence(
            signal_name="cve_risk",
            severity="medium",
            score_contribution=0.2,
            reason=f"{signal.total_count} CVE(s) found, no critical/high severity",
            metadata=meta,
        )
    return SignalEvidence(
        signal_name="cve_risk",
        severity="info",
        score_contribution=0.0,
        reason="No known CVEs",
        metadata=meta,
    )


def evaluate_maintainer_risk(signal: MaintainerSignal) -> SignalEvidence:
    """Evaluate maintainer concentration into risk evidence (Req 5.1-5.5)."""
    fraction = signal.top_contributor_fraction
    username = signal.top_contributor_username or "unknown"
    pct = f"{fraction:.0%}"
    meta = {
        "top_contributor_username": username,
        "top_contributor_fraction": fraction,
        "human_maintainer_count": signal.human_maintainer_count,
    }

    if fraction > 0.8:
        return SignalEvidence(
            signal_name="maintainer_concentration",
            severity="high",
            score_contribution=0.3,
            reason=f"Top contributor {username} accounts for {pct} of commits",
            metadata=meta,
        )
    if fraction > 0.65:
        return SignalEvidence(
            signal_name="maintainer_concentration",
            severity="medium",
            score_contribution=0.15,
            reason=f"Top contributor {username} accounts for {pct} of commits",
            metadata=meta,
        )
    if fraction > 0.5:
        return SignalEvidence(
            signal_name="maintainer_concentration",
            severity="mild",
            score_contribution=0.05,
            reason=f"Top contributor {username} accounts for {pct} of commits",
            metadata=meta,
        )
    return SignalEvidence(
        signal_name="maintainer_concentration",
        severity="info",
        score_contribution=0.0,
        reason=f"Maintainer concentration is healthy ({pct} top contributor)",
        metadata=meta,
    )


def evaluate_release_risk(signal: ReleaseSignal) -> SignalEvidence:
    """Evaluate release staleness into risk evidence (Req 6.1-6.6).
    
    Absence of release metadata does not contribute positive risk (Req 6.6).
    """
    meta = {
        "days_since_latest": signal.days_since_latest,
        "has_releases": signal.has_releases,
        "latest_tag": signal.latest_tag,
        "total_releases": signal.total_releases,
    }
    if not signal.has_releases:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="info",
            score_contribution=0.0,
            reason="No release data available",
            metadata=meta,
        )
    if signal.days_since_latest is None:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="info",
            score_contribution=0.0,
            reason="Latest release could not be determined",
            metadata=meta,
        )
    days = signal.days_since_latest
    if days > 365:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="high",
            score_contribution=0.3,
            reason=f"Last release was {days} days ago (over 1 year)",
            metadata=meta,
        )
    if days > 180:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="medium",
            score_contribution=0.15,
            reason=f"Last release was {days} days ago (over 6 months)",
            metadata=meta,
        )
    return SignalEvidence(
        signal_name="release_staleness",
        severity="info",
        score_contribution=0.0,
        reason=f"Last release was {days} days ago",
        metadata=meta,
    )
```

### 2. Insight Engine (Orchestrator)

**File**: `src/open_source_risk_model/insights/compute.py` (new)
**Implements**: Req 7, 8

```python
from __future__ import annotations

import logging
from typing import Optional

from ..persistence.graph_repo import GraphRepository
from .graph_signals import (
    extract_cve_signal,
    extract_maintainer_signal,
    extract_release_signal,
    extract_base_risk,
)
from .risk_rules import evaluate_cve_risk, evaluate_maintainer_risk, evaluate_release_risk
from .models import RepoInsight

logger = logging.getLogger(__name__)


def _has_meaningful_graph(graph_data: dict | None) -> bool:
    """Check whether graph data contains meaningful content.
    
    A graph is considered "no meaningful data" when:
    - get_graph() returned None
    - OR the returned graph dict has no "nodes" key
    - OR the "nodes" list is empty
    
    A stub graph with only a root repo node (node_count=1) IS treated
    as valid graph data (sparse but available).
    """
    if graph_data is None:
        return False
    graph = graph_data.get("graph", {})
    nodes = graph.get("nodes")
    if nodes is None or len(nodes) == 0:
        return False
    return True


def compute_repo_insight(
    repo_full_name: str,
    graph_repo: GraphRepository,
) -> RepoInsight:
    """Compute complete insight for a repository (Req 7.1-7.10).
    
    Accepts a GraphRepository instance via dependency injection for
    cleaner testing, batch reuse, and API integration. The graph_repo
    parameter is required to keep the contract explicit.
    
    Reads stored graph JSON. Does NOT invoke score_repo() or any
    external scoring/ingestion logic (Req 7.9).
    """
    graph_data = graph_repo.get_graph(repo_full_name)

    # No meaningful graph data (Req 7.8)
    if not _has_meaningful_graph(graph_data):
        return RepoInsight(
            repo_full_name=repo_full_name,
            reasons=["No graph data available"],
        )

    graph = graph_data.get("graph", {})

    # Extract signals (Req 7.2)
    cve_signal = extract_cve_signal(graph)
    maintainer_signal = extract_maintainer_signal(graph)
    release_signal = extract_release_signal(graph)
    base_risk = extract_base_risk(graph)

    # Evaluate rules (Req 7.3)
    cve_evidence = evaluate_cve_risk(cve_signal)
    maintainer_evidence = evaluate_maintainer_risk(maintainer_signal)
    release_evidence = evaluate_release_risk(release_signal)

    # Deterministic order (Req 7.10)
    direct_signals = [cve_evidence, maintainer_evidence, release_evidence]

    # Compute score (Req 7.4, 8.1, 8.2) — full precision
    raw_score = sum(s.score_contribution for s in direct_signals)
    graph_signal_score = min(raw_score, 1.0)

    # Label (Req 7.5)
    if graph_signal_score >= 0.6:
        graph_signal_label = "HIGH"
    elif graph_signal_score >= 0.3:
        graph_signal_label = "MEDIUM"
    else:
        graph_signal_label = "LOW"

    # Reasons from non-info signals (Req 7.6)
    reasons = [s.reason for s in direct_signals if s.severity != "info"]

    return RepoInsight(
        repo_full_name=repo_full_name,
        base_maintenance_risk=base_risk.maintenance_risk,
        base_maintenance_label=base_risk.maintenance_label,
        graph_signal_score=graph_signal_score,
        graph_signal_label=graph_signal_label,
        reasons=reasons,
        direct_signals=direct_signals,
    )
```

### 3. Insights API Endpoint

**File**: `api/app.py` (add endpoint)
**Implements**: Req 9

```python
@app.get("/api/insights/{owner}/{repo}")
def get_repo_insights(owner: str, repo: str):
    """Return computed insight for a repository (Req 9.1-9.5).
    
    Computes on demand. Does not persist results.
    Creates a single GraphRepository and passes it to compute_repo_insight().
    """
    repo_full_name = f"{owner}/{repo}"
    
    try:
        # Check repo existence first
        repo_exists = _repo_exists_in_db(repo_full_name, db_path)
        if not repo_exists:
            raise HTTPException(status_code=404, detail=f"Repository {repo_full_name} not found")
        
        graph_repo = GraphRepository(db_path)
        insight = compute_repo_insight(repo_full_name, graph_repo=graph_repo, db_path=db_path)
        return insight.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing insights for {repo_full_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error computing insights")
```

The `_repo_exists_in_db()` helper checks whether a row exists in `repo_graphs` for the given repo name. If the row exists but `graph_json` is NULL or the graph has no nodes, `compute_repo_insight()` returns the default RepoInsight with "No graph data available" (Req 9.4). If no row exists at all, the endpoint returns 404 (Req 9.3).

### 4. Batch Script

**File**: `scripts/compute_all_insights.py` (new)
**Implements**: Req 10

```python
#!/usr/bin/env python3
"""Compute and print insights for all repos. Does NOT persist results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.insights.compute import compute_repo_insight
from src.open_source_risk_model.persistence.graph_repo import GraphRepository


def main():
    db_path = "data/graphs.db"
    # Create a single GraphRepository and reuse it for all repos
    graph_repo = GraphRepository(db_path)
    repos = graph_repo.list_repos(limit=10000)

    total = len(repos)
    success = 0
    failed = 0

    for repo_info in repos:
        name = repo_info["repo_full_name"]
        try:
            insight = compute_repo_insight(name, graph_repo=graph_repo, db_path=db_path)
            label = insight.graph_signal_label
            score = insight.graph_signal_score
            reasons = "; ".join(insight.reasons) if insight.reasons else "none"
            print(f"  {name}: {label} ({score:.3f}) — {reasons}")
            success += 1
        except Exception as e:
            print(f"  {name}: ERROR — {e}", file=sys.stderr)
            failed += 1

    print(f"\nTotal: {total} | Success: {success} | Failed: {failed}")


if __name__ == "__main__":
    main()
```

## Repo Existence vs Graph Existence

The API distinguishes two cases (Req 7.8, 9.3, 9.4):

| Condition | API Response |
|---|---|
| No row in `repo_graphs` for the repo | 404 with error message |
| Row exists but graph has no meaningful data | 200 with default RepoInsight, reason: "No graph data available" |
| Row exists with valid graph JSON | 200 with computed RepoInsight |

### Definition of "No Meaningful Graph Data"

A graph is considered "no meaningful data" when:
- `get_graph()` returns `None`
- OR the returned graph dict has no `"nodes"` key
- OR the `"nodes"` list is empty

A stub graph with only a root repo node (`node_count=1`) IS treated as valid graph data (sparse but available). This matches the current DB state where all 145 repos have at least a repo node after enrichment.

The `_repo_exists_in_db()` helper performs a simple `SELECT 1 FROM repo_graphs WHERE repo_full_name = ?` check. The `compute_repo_insight()` function handles the graph-missing case internally via the `_has_meaningful_graph()` helper.

## Base Risk Source Contract

`extract_base_risk()` reads `maintenance_risk` (float) and `maintenance_label` (string) from the repo node's metadata in graph JSON. If the repo node is absent or these fields are missing, defaults to `maintenance_risk=None` and `maintenance_label=None`. The function never calls `score_repo()` or accesses any other data source.

### Malformed Graph Handling

If graph JSON has an unexpected shape (e.g., `{"nodes": "not-a-list"}`), `_has_meaningful_graph()` treats it as no meaningful data and returns the default RepoInsight. The layer is defensive and never raises on malformed input.

## CVSS Severity Fallback Chain

The severity extraction for CVE nodes follows a three-step fallback (Req 1.2–1.4):

| Step | Condition | Action |
|---|---|---|
| 1 | `cvss_score` field present and numeric | Map to bucket: ≥9.0→critical, ≥7.0→high, ≥4.0→medium, <4.0→low |
| 2 | No `cvss_score` but `severity` field has CVSS vector | Parse vector heuristically (existing `_parse_cvss_severity()`) |
| 3 | Neither present | Count-only: node counted in `total_count`, ID added to `cve_ids`, no severity flags set |

> **Note on `severity` field naming:** The `severity` field on CVE nodes is historical/raw source data from OSV.dev and may contain a CVSS vector string rather than a human-readable severity label. The fallback chain handles this by checking for a numeric `cvss_score` first.

## Score Computation and Rounding

- Internal computation uses full `float` precision (Req 8.3).
- `graph_signal_score = min(sum(contributions), 1.0)` (Req 8.1, 8.2).
- `to_dict()` rounds `graph_signal_score` and each `score_contribution` to 3 decimal places (Req 8.3, 11.3).
- This separation avoids subtle drift in round-trip tests: `to_dict() → construct → to_dict()` produces identical output because rounding is applied consistently at serialization time only.

## Correctness Properties

### Property 1: Signal Score Bounded (Req 8.1, 8.2)
For all valid graph inputs, `0.0 <= graph_signal_score <= 1.0`.

### Property 2: Score is Additive Sum Capped at 1.0 (Req 7.4, 8.1)
`graph_signal_score == min(cve_evidence.score_contribution + maintainer_evidence.score_contribution + release_evidence.score_contribution, 1.0)`.

### Property 3: Label Thresholds (Req 7.5)
- `graph_signal_score >= 0.6` → `graph_signal_label == "HIGH"`
- `0.3 <= graph_signal_score < 0.6` → `graph_signal_label == "MEDIUM"`
- `graph_signal_score < 0.3` → `graph_signal_label == "LOW"`

### Property 4: Deterministic Signal Order (Req 7.10, 11.4)
For all inputs, `direct_signals[0].signal_name == "cve_risk"`, `direct_signals[1].signal_name == "maintainer_concentration"`, `direct_signals[2].signal_name == "release_staleness"`.

### Property 5: Reasons Match Non-Info Signals (Req 7.6)
`len(reasons) == count of signals where severity != "info"`.

### Property 6: Bot Exclusion (Req 2.1)
For all graph inputs, no maintainer node with username ending in `[bot]` appears in `MaintainerSignal.top_contributor_username`.

### Property 7: No Positive Score from Missing Release Data (Req 6.6)
For all `ReleaseSignal` where `has_releases == False` or `days_since_latest is None`, `score_contribution == 0.0`.

### Property 8: Round-Trip Serialization (Req 8.4, 11.6)
For all valid `RepoInsight` instances: `to_dict(construct_from(to_dict(insight))) == to_dict(insight)`.

### Property 9: Serialization Rounding (Req 8.3, 11.3)
For all `RepoInsight` instances, `to_dict()["graph_signal_score"]` has at most 3 decimal places, and each entry in `to_dict()["direct_signals"]` has `score_contribution` with at most 3 decimal places.

### Property 10: CVE Count Invariant (Req 1.1)
For all graph inputs, `CVESignal.total_count == number of nodes with type "cve"` in the graph.

### Property 11: Every SignalEvidence Has Non-Empty Reason (Req 4.4)
For all signal inputs, the returned `SignalEvidence.reason` is a non-empty string.

### Property 12: top_risky_dependencies Empty in v1 (Req 11.5)
For all `RepoInsight` instances in v1, `to_dict()["top_risky_dependencies"] == []`.

### Property 13: No Rescoring Invariant (Req 7.9)
The `compute.py` module does not import or call `score_repo` or any ingestion function. This is verified by static analysis of the module's imports.

## Files Changed

| File | Action | Description |
|---|---|---|
| `src/open_source_risk_model/insights/graph_signals.py` | Modify | Add CVSS fallback chain (`_severity_from_cvss_score`, `_extract_severity_bucket`) |
| `src/open_source_risk_model/insights/risk_rules.py` | Create | Three rule evaluator functions |
| `src/open_source_risk_model/insights/compute.py` | Create | Insight engine orchestrator |
| `api/app.py` | Modify | Add `/api/insights/{owner}/{repo}` endpoint |
| `scripts/compute_all_insights.py` | Create | Batch compute-and-print script |
| `test/insights/test_risk_rules.py` | Create | Unit tests for rule evaluators |
| `test/insights/test_compute.py` | Create | Unit tests for insight engine |
| `test/insights/test_risk_rules_properties.py` | Create | Property-based tests for rules |
| `test/insights/test_compute_properties.py` | Create | Property-based tests for engine |
| `test/insights/test_api_endpoint.py` | Create | API endpoint integration tests |
