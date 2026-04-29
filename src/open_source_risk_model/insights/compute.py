"""Insight engine orchestrator.

Reads stored graph JSON, extracts signals, evaluates rules,
and assembles a RepoInsight output. Computes on demand — no
persistence, no external API calls, no rescoring.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from ..persistence.graph_repo import GraphRepository
from ..tree.scope_risk import (
    CONFIDENCE_MODIFIERS,
    DEFAULT_SCOPE_WEIGHTS,
    DependencyInput,
    compute_scope_exposure_metrics,
    compute_scope_weighted_risk,
    get_scope_weight,
)
from .actionable import (
    generate_priority_recommendations,
    generate_risk_clusters,
    generate_risk_narrative,
    compute_overall_confidence,
)
from .graph_signals import (
    extract_base_risk,
    extract_cve_signal,
    extract_maintainer_signal,
    extract_release_signal,
)
from .models import RepoInsight
from .risk_rules import evaluate_cve_risk, evaluate_maintainer_risk, evaluate_release_risk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safe default for when scope data is unavailable (Req 7.4)
# ---------------------------------------------------------------------------

_SAFE_DEFAULT_SCOPE_WEIGHTED_RISK: dict[str, Any] = {
    "scope_weighted_dependency_risk": 0.0,
    "risk_label": "low",
    "top_drivers": [],
    "scope_note": "Dependency scope is classified from manifests and may not reflect actual runtime usage.",
    "confidence_note": "Scope data is not available for this repository.",
}


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


def _build_dependency_inputs(graph: dict[str, Any]) -> List[DependencyInput]:
    """Build a list of DependencyInput objects from graph nodes.

    For each node in graph["nodes"] that is not the root repo node,
    extract dependency data with safe defaults when fields are missing.
    """
    dependencies: List[DependencyInput] = []
    nodes = graph.get("nodes", [])

    for node in nodes:
        node_type = node.get("type", "")
        # Skip non-package nodes (repo, cve, maintainer, release, etc.)
        if node_type != "package":
            continue

        meta = node.get("metadata", {})
        prov = node.get("provenance", {})

        package_name = meta.get("package_name") or node.get("label", "unknown")
        dependency_scope = meta.get("dependency_scope") or "unknown"
        scope_confidence = meta.get("scope_confidence") or "low"
        vulnerability_count = meta.get("vulnerability_count", 0)
        risk_score = meta.get("risk_score")
        depth = meta.get("depth", 1)
        dependency_type = "direct" if depth == 1 else "transitive"

        dependencies.append(
            DependencyInput(
                package_name=package_name,
                dependency_scope=dependency_scope,
                scope_confidence=scope_confidence,
                vulnerability_count=vulnerability_count,
                risk_score=risk_score,
                dependency_type=dependency_type,
            )
        )

    return dependencies


def compute_scope_aware_reasons(
    dependencies: List[DependencyInput],
) -> List[str]:
    """Compute scope-aware insight reasons from dependency data.

    Returns a list of reason strings based on the 5 scope-aware rules
    (Req 5.1–5.5). Returns empty list when all scopes are unknown (Req 5.7).

    This is extracted as a standalone function for testability.
    """
    if not dependencies:
        return []

    # Check if all scopes are unknown (Req 5.7)
    all_unknown = all(
        (dep.dependency_scope or "unknown") == "unknown" for dep in dependencies
    )
    if all_unknown:
        return []

    reasons: List[str] = []

    # Compute per-dependency contributions for Rule 1
    from ..tree.scope_risk import _normalized_risk, _deduplicate

    deduped = _deduplicate(dependencies)

    records = []
    for dep in deduped:
        scope = dep.dependency_scope or "unknown"
        nr = _normalized_risk(dep)
        sw = get_scope_weight(scope)
        cm = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
        contribution = round(sw * nr * cm, 6)
        records.append((dep, scope, contribution))

    total_weighted_sum = sum(r[2] for r in records)

    # Rule 1: Runtime dominance (Req 5.1)
    if total_weighted_sum > 0:
        runtime_contribution = sum(
            r[2] for r in records if r[1] == "runtime"
        )
        runtime_contribution_fraction = runtime_contribution / total_weighted_sum
        if runtime_contribution_fraction > 0.5:
            reasons.append(
                "Most dependency risk comes from runtime-scoped dependencies."
            )

    # Rule 2: High transitive runtime count (Req 5.2)
    transitive_runtime_count = sum(
        1
        for dep in deduped
        if dep.dependency_type == "transitive"
        and (dep.dependency_scope or "unknown") == "runtime"
    )
    if transitive_runtime_count > 20:
        reasons.append(
            "This repository has a high number of transitive runtime dependencies."
        )

    # Rule 3: Vulnerable runtime paths (Req 5.3)
    metrics = compute_scope_exposure_metrics(dependencies)
    if (
        metrics.vulnerable_runtime_dependency_count > 0
        or metrics.vulnerable_transitive_runtime_dependency_count > 0
    ):
        reasons.append(
            "Several vulnerable dependencies appear in runtime-relevant paths."
        )

    # Rule 4: Dev/test majority (Req 5.4)
    total_deps = len(deduped)
    if total_deps > 0:
        dev_test_count = sum(
            1
            for dep in deduped
            if (dep.dependency_scope or "unknown") in ("dev", "test")
        )
        dev_test_fraction = dev_test_count / total_deps
        if dev_test_fraction > 0.5:
            reasons.append(
                "Most dependencies are dev/test scoped, reducing likely production exposure."
            )

    # Rule 5: High unknown ratio (Req 5.5)
    if total_deps > 0:
        unknown_count = sum(
            1
            for dep in deduped
            if (dep.dependency_scope or "unknown") == "unknown"
        )
        unknown_scope_ratio = unknown_count / total_deps
        if unknown_scope_ratio > 0.5:
            reasons.append(
                "A large unknown-scope share limits confidence in runtime exposure estimates."
            )

    return reasons


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

    # --- Phase 4: Scope-weighted risk integration ---
    dep_inputs = _build_dependency_inputs(graph)

    if dep_inputs:
        payload = compute_scope_weighted_risk(dep_inputs)
        scope_weighted_risk = payload.to_dict()

        # Append scope-aware insight reasons (Req 5.1–5.7)
        scope_reasons = compute_scope_aware_reasons(dep_inputs)
        reasons.extend(scope_reasons)
    else:
        # Safe defaults when scope data is unavailable (Req 7.4)
        scope_weighted_risk = dict(_SAFE_DEFAULT_SCOPE_WEIGHTED_RISK)

    # --- Phase 5: Actionable Insights integration ---
    if dep_inputs:
        priority_recommendations = generate_priority_recommendations(dep_inputs)
        risk_clusters = generate_risk_clusters(dep_inputs)
        overall_confidence = compute_overall_confidence(dep_inputs)
    else:
        priority_recommendations = []
        risk_clusters = generate_risk_clusters([])  # returns 4 empty clusters
        overall_confidence = compute_overall_confidence([])  # returns safe default

    repo_insight = RepoInsight(
        repo_full_name=repo_full_name,
        base_maintenance_risk=base_risk.maintenance_risk,
        base_maintenance_label=base_risk.maintenance_label,
        graph_signal_score=graph_signal_score,
        graph_signal_label=graph_signal_label,
        reasons=reasons,
        direct_signals=direct_signals,
        scope_weighted_risk=scope_weighted_risk,
        priority_recommendations=priority_recommendations,
        risk_clusters=risk_clusters,
        overall_confidence=overall_confidence,
    )
    # Generate narrative after RepoInsight is built (needs insight + clusters)
    risk_narrative = generate_risk_narrative(repo_insight, risk_clusters)
    repo_insight.risk_narrative = risk_narrative

    return repo_insight
