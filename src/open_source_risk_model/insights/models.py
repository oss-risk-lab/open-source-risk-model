"""Data models for the insight layer.

These are pure output containers — no logic, no side effects.
Every score has a reason. Every signal is explainable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SignalEvidence:
    """A single risk signal extracted from graph data.

    Every signal must carry a human-readable reason string.
    """
    signal_name: str          # e.g. "cve_risk", "maintainer_concentration"
    severity: str             # "high", "medium", "mild", "info"
    score_contribution: float # 0.0–1.0, additive contribution
    reason: str               # human-readable explanation
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DependencyRisk:
    """Risk assessment for a single dependency package."""
    package_name: str
    registry_type: str        # "pypi", "npm", etc.
    risk_score: float         # 0.0–1.0
    risk_label: str           # "HIGH", "MEDIUM", "LOW"
    reasons: list[str] = field(default_factory=list)
    cve_count: int = 0
    resolved_repo: Optional[str] = None


@dataclass
class RepoInsight:
    """Complete insight output for a repository.

    Composes on top of the existing maintenance scorer —
    does not replace it.
    """
    repo_full_name: str

    # From existing scorer (passed through, not recomputed)
    base_maintenance_risk: Optional[float] = None
    base_maintenance_label: Optional[str] = None

    # Graph-derived signal score (additive from direct signals only)
    graph_signal_score: float = 0.0
    graph_signal_label: str = "LOW"

    # Human-readable reasons (top-level summary)
    reasons: list[str] = field(default_factory=list)

    # Detailed signal evidence
    direct_signals: list[SignalEvidence] = field(default_factory=list)

    # Placeholder for future inheritance signals
    inherited_signals: list[SignalEvidence] = field(default_factory=list)

    # Top risky dependencies
    top_risky_dependencies: list[DependencyRisk] = field(default_factory=list)

    # Phase 4 — Scope-weighted risk (ExplainabilityPayload.to_dict())
    scope_weighted_risk: Optional[dict] = None

    # Phase 5 — Actionable Insights
    priority_recommendations: list = field(default_factory=list)
    risk_clusters: list = field(default_factory=list)
    risk_narrative: Optional[Any] = None
    overall_confidence: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses."""
        result = {
            "repo_full_name": self.repo_full_name,
            "base_maintenance_risk": self.base_maintenance_risk,
            "base_maintenance_label": self.base_maintenance_label,
            "graph_signal_score": round(self.graph_signal_score, 3),
            "graph_signal_label": self.graph_signal_label,
            "reasons": self.reasons,
            "direct_signals": [
                {
                    "signal_name": s.signal_name,
                    "severity": s.severity,
                    "score_contribution": round(s.score_contribution, 3),
                    "reason": s.reason,
                }
                for s in self.direct_signals
            ],
            "top_risky_dependencies": [
                {
                    "package_name": d.package_name,
                    "registry_type": d.registry_type,
                    "risk_score": round(d.risk_score, 3),
                    "risk_label": d.risk_label,
                    "reasons": d.reasons,
                    "cve_count": d.cve_count,
                }
                for d in self.top_risky_dependencies
            ],
        }
        if self.scope_weighted_risk is not None:
            result["scope_weighted_risk"] = self.scope_weighted_risk

        # Phase 5 — Actionable Insights
        result["priority_recommendations"] = [r.to_dict() for r in self.priority_recommendations]
        result["risk_clusters"] = [c.to_dict() for c in self.risk_clusters]
        result["risk_narrative"] = self.risk_narrative.to_dict() if self.risk_narrative else None
        result["overall_confidence"] = self.overall_confidence.to_dict() if self.overall_confidence else None

        return result
