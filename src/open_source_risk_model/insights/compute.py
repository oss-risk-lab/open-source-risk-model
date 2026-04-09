"""Insight engine orchestrator.

Reads stored graph JSON, extracts signals, evaluates rules,
and assembles a RepoInsight output. Computes on demand — no
persistence, no external API calls, no rescoring.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ..persistence.graph_repo import GraphRepository
from .graph_signals import (
    extract_base_risk,
    extract_cve_signal,
    extract_maintainer_signal,
    extract_release_signal,
)
from .models import RepoInsight
from .risk_rules import evaluate_cve_risk, evaluate_maintainer_risk, evaluate_release_risk

logger = logging.getLogger(__name__)


def _has_meaningful_graph(graph_data: Optional[dict[str, Any]]) -> bool:
    """Check whether graph data contains meaningful content.

    A graph is considered "no meaningful data" when:
    - get_graph() returned None
    - OR the inner graph dict has no "nodes" key
    - OR the "nodes" value is not a list
    - OR the "nodes" list is empty

    A stub graph with only a root repo node (node_count=1) IS treated
    as valid graph data (sparse but available).
    """
    if graph_data is None:
        return False
    graph = graph_data.get("graph", {})
    if not isinstance(graph, dict):
        return False
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return False
    if len(nodes) == 0:
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

    Reads stored graph JSON. Does NOT invoke any external scoring
    or ingestion logic (Req 7.9).
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
