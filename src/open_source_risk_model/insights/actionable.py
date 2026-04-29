"""Actionable Insights Layer (Phase 5) — data models and pure functions.

This module provides priority-ranked remediation recommendations, risk cluster
groupings, plain-language narratives, overall confidence scoring, and snapshot
comparison. All logic is pure-function — no DB, no API calls, no side effects.

Reuses Phase 4 primitives from scope_risk.py for formula consistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .models import RepoInsight

from ..tree.scope_risk import (
    CONFIDENCE_MODIFIERS,
    DEFAULT_SCOPE_WEIGHTS,
    DependencyInput,
    _deduplicate,
    _normalized_risk,
    get_scope_weight,
)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionableInsight:
    """A single prioritized recommendation."""

    package_name: str
    dependency_scope: str
    dependency_type: str
    reason: str
    priority_score: float  # 0.0–1.0, higher = more urgent
    action: str  # human-readable recommended action

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_name": self.package_name,
            "dependency_scope": self.dependency_scope,
            "dependency_type": self.dependency_type,
            "reason": self.reason,
            "priority_score": round(self.priority_score, 6),
            "action": self.action,
        }


@dataclass(frozen=True)
class RiskCluster:
    """A named grouping of dependencies sharing a risk characteristic."""

    cluster_name: str
    summary: str
    count: int
    risk_contribution: float  # fraction of total scope-weighted risk
    example_packages: list[str] = field(default_factory=list)  # at most 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_name": self.cluster_name,
            "summary": self.summary,
            "count": self.count,
            "risk_contribution": round(self.risk_contribution, 6),
            "example_packages": list(self.example_packages),
        }


@dataclass(frozen=True)
class RiskNarrative:
    """Plain-language risk posture summary."""

    summary: str  # 1–3 sentence overview
    key_findings: list[str] = field(default_factory=list)  # at most 5 findings
    recommendation: str = ""  # single actionable sentence

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "key_findings": list(self.key_findings),
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class OverallConfidence:
    """Composite confidence score for the analysis."""

    score: float  # 0.0–1.0
    label: str  # "high", "medium", "low"
    explanation: str  # human-readable sentence

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 6),
            "label": self.label,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class RepoSnapshotDiff:
    """Diff between two RepoInsight snapshots."""

    new_risky_dependencies: list[str] = field(default_factory=list)  # sorted by package_name asc
    removed_dependencies: list[str] = field(default_factory=list)  # sorted by package_name asc
    risk_score_change: float = 0.0  # new_score - old_score
    risk_label_change: Optional[str] = None  # e.g. "low → medium", or None

    def to_dict(self) -> dict[str, Any]:
        return {
            "new_risky_dependencies": list(self.new_risky_dependencies),
            "removed_dependencies": list(self.removed_dependencies),
            "risk_score_change": round(self.risk_score_change, 6),
            "risk_label_change": self.risk_label_change,
        }


# ---------------------------------------------------------------------------
# Priority Recommendations
# ---------------------------------------------------------------------------


def generate_priority_recommendations(
    dependencies: list[DependencyInput],
) -> list[ActionableInsight]:
    """Generate ranked remediation recommendations.

    Pure function. No DB, no API, no side effects.
    Returns at most 10 recommendations sorted by priority_score desc,
    then package_name asc. Excludes zero-score dependencies.
    """
    if not dependencies:
        return []

    # Deduplicate using Phase 4 logic
    deps = _deduplicate(dependencies)

    # Compute priority scores and build insights
    candidates: list[ActionableInsight] = []
    for dep in deps:
        scope = dep.dependency_scope or "unknown"
        normalized_risk = _normalized_risk(dep)
        scope_weight = get_scope_weight(scope)
        confidence_modifier = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
        priority_score = round(min(scope_weight * normalized_risk * confidence_modifier, 1.0), 6)

        # Exclude zero-score dependencies
        if priority_score == 0.0:
            continue

        # Assign action using first-match rules
        if dep.vulnerability_count > 0:
            action = "Upgrade to patched version"
        elif dep.risk_score is not None and dep.risk_score > 70:
            action = "Review high-risk dependency"
        elif scope == "unknown":
            action = "Investigate unknown scope"
        else:
            action = "Monitor dependency risk"

        # Build deterministic reason string
        signals: list[str] = []
        if dep.vulnerability_count > 0:
            signals.append(f"{dep.vulnerability_count} known CVE(s)")
        if dep.risk_score is not None and dep.risk_score > 0:
            signals.append(f"risk score {dep.risk_score:.0f}/100")
        if not signals:
            signals.append("contributes to weighted risk")
        reason = f"{scope}-scoped: {', '.join(signals)}"

        candidates.append(
            ActionableInsight(
                package_name=dep.package_name,
                dependency_scope=scope,
                dependency_type=dep.dependency_type,
                reason=reason,
                priority_score=priority_score,
                action=action,
            )
        )

    # Sort by (-priority_score, package_name, dependency_type) for deterministic output
    candidates.sort(key=lambda x: (-x.priority_score, x.package_name, x.dependency_type))

    # Return at most 10
    return candidates[:10]


# ---------------------------------------------------------------------------
# Risk Clusters
# ---------------------------------------------------------------------------

# Fixed cluster definitions: (name, summary, filter_fn)
_CLUSTER_SUMMARIES = {
    "Runtime Risk Cluster": "Dependencies in runtime scope with elevated risk.",
    "Transitive Risk Cluster": "Transitive dependencies with elevated risk.",
    "Vulnerability Cluster": "Dependencies with known vulnerabilities.",
    "Unknown Scope Cluster": "Dependencies with unclassified scope.",
}


def generate_risk_clusters(
    dependencies: list[DependencyInput],
) -> list[RiskCluster]:
    """Generate four predefined risk clusters.

    Pure function. Returns exactly 4 clusters in fixed order:
    Runtime Risk, Transitive Risk, Vulnerability, Unknown Scope.
    """
    # Deduplicate using Phase 4 logic
    deps = _deduplicate(dependencies) if dependencies else []

    # Compute per-dependency contribution using Phase 4 formula exactly
    contributions: list[tuple[DependencyInput, str, float, float]] = []
    for dep in deps:
        scope = dep.dependency_scope or "unknown"
        nr = _normalized_risk(dep)
        contribution = round(
            get_scope_weight(scope) * nr * CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5),
            6,
        )
        contributions.append((dep, scope, nr, contribution))

    # Compute total_contribution using sorted summation for deterministic floating-point
    sorted_contribs = sorted((c[3] for c in contributions), reverse=True)
    total_contribution = sum(sorted_contribs)

    # Define cluster filters
    def _runtime_filter(dep: DependencyInput, scope: str, nr: float) -> bool:
        return scope == "runtime" and nr > 0

    def _transitive_filter(dep: DependencyInput, scope: str, nr: float) -> bool:
        return dep.dependency_type == "transitive" and nr > 0

    def _vulnerability_filter(dep: DependencyInput, scope: str, nr: float) -> bool:
        return dep.vulnerability_count > 0

    def _unknown_filter(dep: DependencyInput, scope: str, nr: float) -> bool:
        return scope == "unknown"

    cluster_defs = [
        ("Runtime Risk Cluster", _runtime_filter),
        ("Transitive Risk Cluster", _transitive_filter),
        ("Vulnerability Cluster", _vulnerability_filter),
        ("Unknown Scope Cluster", _unknown_filter),
    ]

    clusters: list[RiskCluster] = []
    for cluster_name, filter_fn in cluster_defs:
        # Filter matching dependencies
        matching = [
            (dep, scope, nr, contrib)
            for dep, scope, nr, contrib in contributions
            if filter_fn(dep, scope, nr)
        ]

        count = len(matching)

        # Compute cluster risk_contribution
        if total_contribution > 0 and matching:
            cluster_sum = sum(m[3] for m in matching)
            risk_contribution = round(cluster_sum / total_contribution, 6)
        else:
            risk_contribution = 0.0

        # Select example_packages: top 3 by highest _normalized_risk, then package_name asc
        sorted_matching = sorted(
            matching,
            key=lambda m: (-m[2], m[0].package_name),
        )
        example_packages = [m[0].package_name for m in sorted_matching[:3]]

        clusters.append(
            RiskCluster(
                cluster_name=cluster_name,
                summary=_CLUSTER_SUMMARIES[cluster_name],
                count=count,
                risk_contribution=risk_contribution,
                example_packages=example_packages,
            )
        )

    return clusters


# ---------------------------------------------------------------------------
# Overall Confidence
# ---------------------------------------------------------------------------


def compute_overall_confidence(
    dependencies: list[DependencyInput],
) -> OverallConfidence:
    """Compute overall confidence score for the analysis.

    Pure function. No DB, no API, no side effects.
    Combines scope confidence distribution, unknown scope ratio, and data
    coverage into a single composite score with label and explanation.
    """
    # Deduplicate using Phase 4 logic
    deps = _deduplicate(dependencies) if dependencies else []

    # Empty input → safe default
    if not deps:
        return OverallConfidence(
            score=0.0,
            label="low",
            explanation="No dependency data available for confidence assessment.",
        )

    total_count = len(deps)

    # --- Component 1: Scope confidence score (weight 0.4) ---
    high_count = sum(1 for d in deps if d.scope_confidence == "high")
    medium_count = sum(1 for d in deps if d.scope_confidence == "medium")
    low_count = sum(1 for d in deps if d.scope_confidence == "low")
    scope_confidence = min(max(
        (high_count * 1.0 + medium_count * 0.75 + low_count * 0.5) / total_count,
        0.0,
    ), 1.0)

    # --- Component 2: Unknown scope penalty (weight 0.3) ---
    unknown_count = sum(
        1 for d in deps
        if (d.dependency_scope or "unknown") == "unknown" or d.dependency_scope is None
    )
    unknown_penalty = min(max(1.0 - (unknown_count / total_count), 0.0), 1.0)

    # --- Component 3: Data coverage score (weight 0.3) ---
    has_risk_count = sum(1 for d in deps if d.risk_score is not None)
    data_coverage = min(max(has_risk_count / total_count, 0.0), 1.0)

    # --- Weighted score ---
    score = round(0.4 * scope_confidence + 0.3 * unknown_penalty + 0.3 * data_coverage, 6)

    # --- Label ---
    if score >= 0.7:
        label = "high"
    elif score >= 0.4:
        label = "medium"
    else:
        label = "low"

    # --- Explanation ---
    if label == "high":
        explanation = "Analysis confidence is high; most dependencies have classified scope and risk data."
    elif label == "medium":
        explanation = "Analysis confidence is moderate; some dependencies lack complete data."
    else:
        # Identify weakest component
        components = {
            "scope_confidence": scope_confidence,
            "unknown_penalty": unknown_penalty,
            "data_coverage": data_coverage,
        }
        weakest = min(components, key=lambda k: components[k])
        if weakest == "unknown_penalty":
            explanation = "Many dependencies have unknown scope, limiting confidence in the analysis."
        elif weakest == "data_coverage":
            explanation = "Risk data is missing for most dependencies."
        else:
            explanation = "Scope confidence is low across dependencies."

    return OverallConfidence(
        score=score,
        label=label,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Risk Narrative
# ---------------------------------------------------------------------------


def generate_risk_narrative(
    insight: "RepoInsight",
    clusters: list[RiskCluster],
) -> RiskNarrative:
    """Generate plain-language risk summary.

    Pure function. Uses fixed templates only — no LLMs.
    """
    # 1. Extract scope_weighted_risk dict from insight
    swr = getattr(insight, "scope_weighted_risk", None)
    if swr is None:
        return RiskNarrative(
            summary="Insufficient data available for risk narrative generation.",
            key_findings=[],
            recommendation="Continue monitoring dependency health.",
        )

    # 2. Read risk_label and score
    risk_label = swr.get("risk_label", "low")
    score = swr.get("scope_weighted_dependency_risk", 0.0)

    # 3. Summary: fixed template based on risk_label
    if risk_label == "high":
        summary = f"This repository has significant dependency risk with a scope-weighted risk score of {score:.1%}."
    elif risk_label == "medium":
        summary = f"This repository has moderate dependency risk with a scope-weighted risk score of {score:.1%}."
    else:
        summary = f"This repository has low dependency risk with a scope-weighted risk score of {score:.1%}."

    # 4. Key findings (at most 5)
    key_findings: list[str] = []

    # 4a. Top drivers from scope_weighted_risk["top_drivers"]
    top_drivers = swr.get("top_drivers", [])
    # Sort by contribution desc, then package asc
    sorted_drivers = sorted(
        top_drivers,
        key=lambda d: (-d.get("contribution", 0.0), d.get("package", "")),
    )
    for driver in sorted_drivers:
        if len(key_findings) >= 5:
            break
        package = driver.get("package", "unknown")
        scope = driver.get("scope", "unknown")
        contribution = driver.get("contribution", 0.0)
        key_findings.append(
            f"{package} ({scope}-scoped) contributes {contribution:.1%} of total risk."
        )

    # 4b. Non-zero clusters sorted by (-risk_contribution, cluster_name)
    non_zero_clusters = [c for c in clusters if c.risk_contribution > 0]
    sorted_clusters = sorted(
        non_zero_clusters,
        key=lambda c: (-c.risk_contribution, c.cluster_name),
    )
    for cluster in sorted_clusters:
        if len(key_findings) >= 5:
            break
        key_findings.append(
            f"The {cluster.cluster_name} contains {cluster.count} dependencies "
            f"accounting for {cluster.risk_contribution:.1%} of risk."
        )

    # 5. Recommendation: single sentence based on highest-priority cluster
    vuln_cluster = next(
        (c for c in clusters if c.cluster_name == "Vulnerability Cluster"),
        None,
    )
    runtime_cluster = next(
        (c for c in clusters if c.cluster_name == "Runtime Risk Cluster"),
        None,
    )

    if vuln_cluster is not None and vuln_cluster.count > 0:
        recommendation = (
            f"Prioritize patching the {vuln_cluster.count} vulnerable "
            f"dependencies to reduce exposure."
        )
    elif runtime_cluster is not None and runtime_cluster.count > 0:
        recommendation = (
            f"Review the {runtime_cluster.count} runtime dependencies "
            f"contributing to risk."
        )
    else:
        recommendation = "Continue monitoring dependency health."

    return RiskNarrative(
        summary=summary,
        key_findings=key_findings,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Snapshot Comparison
# ---------------------------------------------------------------------------


def compare_repo_snapshots(
    old: "RepoInsight",
    new: "RepoInsight",
) -> RepoSnapshotDiff:
    """Compare two RepoInsight snapshots.

    Pure function. Simple diff — no time-series storage.
    Uses priority_recommendations from each RepoInsight to determine
    new risky and removed dependencies.
    """
    # 1. Extract scope_weighted_risk from both; treat None as default
    _default_swr = {"scope_weighted_dependency_risk": 0.0, "risk_label": "low"}

    old_swr = getattr(old, "scope_weighted_risk", None) or _default_swr
    new_swr = getattr(new, "scope_weighted_risk", None) or _default_swr

    old_score = old_swr.get("scope_weighted_dependency_risk", 0.0)
    new_score = new_swr.get("scope_weighted_dependency_risk", 0.0)

    old_label = old_swr.get("risk_label", "low")
    new_label = new_swr.get("risk_label", "low")

    # 2. Compute risk_score_change
    risk_score_change = round(new_score - old_score, 6)

    # 3. Compute risk_label_change
    if old_label != new_label:
        risk_label_change: Optional[str] = f"{old_label} \u2192 {new_label}"
    else:
        risk_label_change = None

    # 4. Extract dependency identity sets from priority_recommendations
    old_recs = getattr(old, "priority_recommendations", None) or []
    new_recs = getattr(new, "priority_recommendations", None) or []

    def _extract_identity_set(
        recs: list,
    ) -> set[tuple[str, str]]:
        """Extract (package_name, dependency_type) identity set from recommendations."""
        identities: set[tuple[str, str]] = set()
        for rec in recs:
            if hasattr(rec, "package_name"):
                # ActionableInsight object
                pkg = rec.package_name
                dep_type = rec.dependency_type
            elif isinstance(rec, dict):
                # Dict from to_dict()
                pkg = rec.get("package_name", "")
                dep_type = rec.get("dependency_type", "")
            else:
                continue
            identities.add((pkg, dep_type))
        return identities

    def _extract_priority_map(
        recs: list,
    ) -> dict[tuple[str, str], float]:
        """Extract (package_name, dependency_type) -> priority_score map."""
        result: dict[tuple[str, str], float] = {}
        for rec in recs:
            if hasattr(rec, "package_name"):
                pkg = rec.package_name
                dep_type = rec.dependency_type
                score = rec.priority_score
            elif isinstance(rec, dict):
                pkg = rec.get("package_name", "")
                dep_type = rec.get("dependency_type", "")
                score = rec.get("priority_score", 0.0)
            else:
                continue
            key = (pkg, dep_type)
            # Deduplicate: keep highest priority_score
            if key not in result or score > result[key]:
                result[key] = score
        return result

    old_identities = _extract_identity_set(old_recs)
    new_priority_map = _extract_priority_map(new_recs)
    new_identities = set(new_priority_map.keys())

    # 5. new_risky_dependencies: in new but not old, with priority_score > 0
    new_only = new_identities - old_identities
    new_risky = sorted(
        {pkg for pkg, dep_type in new_only if new_priority_map.get((pkg, dep_type), 0.0) > 0}
    )

    # 6. removed_dependencies: in old but not new
    removed_only = old_identities - new_identities
    removed = sorted({pkg for pkg, _ in removed_only})

    return RepoSnapshotDiff(
        new_risky_dependencies=new_risky,
        removed_dependencies=removed,
        risk_score_change=risk_score_change,
        risk_label_change=risk_label_change,
    )
