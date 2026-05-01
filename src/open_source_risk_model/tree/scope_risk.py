"""Scope-weighted dependency risk: data models, weight map, and helpers.

Pure-function module — no database access, no API calls, no side effects.
Phase 4 of dependency scope classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SCOPE_WEIGHTS: dict[str, float] = {
    "runtime": 1.00,
    "optional": 0.75,
    "peer": 0.65,
    "build": 0.50,
    "test": 0.35,
    "dev": 0.25,
    "unknown": 0.40,
}

CONFIDENCE_MODIFIERS: dict[str, float] = {
    "high": 1.0,
    "medium": 0.75,
    "low": 0.5,
}


# ---------------------------------------------------------------------------
# Weight lookup
# ---------------------------------------------------------------------------

def get_scope_weight(
    scope: str | None,
    weights: dict[str, float] | None = None,
) -> float:
    """Return weight for a scope value. Never raises KeyError.

    * ``None`` or empty-string scope is treated as ``"unknown"``.
    * Falls back to the ``"unknown"`` entry in *weights*, then to ``0.40``.
    """
    w = weights or DEFAULT_SCOPE_WEIGHTS
    return w.get(scope or "unknown", w.get("unknown", 0.40))


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DependencyInput:
    """Single dependency for scope-weighted risk calculation."""

    package_name: str
    dependency_scope: str       # one of {runtime, dev, test, build, optional, peer, unknown}
    scope_confidence: str       # one of {high, medium, low}
    vulnerability_count: int    # >= 0
    risk_score: Optional[float]  # 0–100 scale, or None
    dependency_type: str        # "direct" or "transitive"


@dataclass(frozen=True)
class TopDriver:
    """A dependency that contributes significantly to scope-weighted risk."""

    package: str
    scope: str
    reason: str
    contribution: float  # normalized 0–1


@dataclass(frozen=True)
class ExplainabilityPayload:
    """Structured explainability payload for scope-weighted risk."""

    scope_weighted_dependency_risk: float  # 0.0–1.0
    risk_label: str                        # "low", "medium", "high"
    top_drivers: List[TopDriver]
    scope_note: str
    confidence_note: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return {
            "scope_weighted_dependency_risk": round(
                self.scope_weighted_dependency_risk, 6
            ),
            "risk_label": self.risk_label,
            "top_drivers": [
                {
                    "package": d.package,
                    "scope": d.scope,
                    "reason": d.reason,
                    "contribution": round(d.contribution, 6),
                }
                for d in self.top_drivers
            ],
            "scope_note": self.scope_note,
            "confidence_note": self.confidence_note,
        }


@dataclass(frozen=True)
class ScopeExposureMetrics:
    """Scope-aware exposure metrics computed from dependency data."""

    runtime_dependency_exposure: float                    # 0.0–1.0
    transitive_runtime_dependency_exposure: float         # 0.0–1.0
    scope_weighted_dependency_exposure: float             # 0.0–1.0
    vulnerable_runtime_dependency_count: int
    vulnerable_transitive_runtime_dependency_count: int
    high_risk_runtime_dependency_count: int
    unknown_scope_dependency_ratio: float                 # 0.0–1.0


# ---------------------------------------------------------------------------
# Static strings
# ---------------------------------------------------------------------------

_SCOPE_NOTE = (
    "Dependency scope is classified from manifests and may not reflect "
    "actual runtime usage."
)

_EMPTY_CONFIDENCE_NOTE = (
    "Scope data is not available for this repository."
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _classify_risk_label(score: float) -> str:
    """Map a 0–1 score to a categorical risk label."""
    if score <= 0.33:
        return "low"
    if score <= 0.66:
        return "medium"
    return "high"


def _normalized_risk(dep: DependencyInput) -> float:
    """Compute per-dependency normalized risk in [0.0, 1.0].

    Uses the *max* of two signals so the larger one dominates:
      max((risk_score or 0) / 100, min(vuln_count, 5) * 0.1)
    Result is clamped to [0.0, 1.0].
    """
    rs = (dep.risk_score or 0) / 100.0
    vc = min(dep.vulnerability_count, 5) * 0.1
    return max(0.0, min(max(rs, vc), 1.0))


def _build_reason(dep: DependencyInput, scope: str, nr: float) -> str:
    """Build a human-readable reason string for a top driver."""
    parts: list[str] = []
    if dep.vulnerability_count > 0:
        parts.append(f"{dep.vulnerability_count} known CVE(s)")
    if dep.risk_score is not None and dep.risk_score > 0:
        parts.append(f"risk score {dep.risk_score:.0f}/100")
    if not parts:
        parts.append("contributes to weighted risk")
    return f"{scope}-scoped: {', '.join(parts)}"


def _confidence_note(unknown_ratio: float) -> str:
    """Derive confidence note from unknown-scope dependency ratio."""
    if unknown_ratio > 0.5:
        return (
            "Low confidence: a large proportion of dependencies have "
            "unknown scope, limiting accuracy of runtime exposure estimates"
        )
    if unknown_ratio >= 0.2:
        return (
            "Moderate confidence: some dependencies have unknown scope, "
            "which may affect accuracy"
        )
    return (
        "High confidence: most dependencies have classified scope, "
        "providing reliable runtime exposure estimates"
    )


def _deduplicate(
    dependencies: list[DependencyInput],
) -> list[DependencyInput]:
    """Deduplicate by (package_name, dependency_type).

    When duplicates exist, keep the entry with the highest normalized_risk.
    Ties are broken deterministically by preferring higher scope_weight,
    then higher confidence_modifier, then higher raw risk_score, then
    higher vulnerability_count — ensuring input-order independence.
    """
    best: dict[tuple[str, str], DependencyInput] = {}
    best_key_val: dict[tuple[str, str], tuple[float, float, float, float, int]] = {}
    for dep in dependencies:
        key = (dep.package_name, dep.dependency_type)
        nr = _normalized_risk(dep)
        scope = dep.dependency_scope or "unknown"
        sw = DEFAULT_SCOPE_WEIGHTS.get(scope, DEFAULT_SCOPE_WEIGHTS.get("unknown", 0.40))
        cm = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
        rs = dep.risk_score if dep.risk_score is not None else -1.0
        sort_val = (nr, sw, cm, rs, dep.vulnerability_count)
        if key not in best or sort_val > best_key_val[key]:
            best[key] = dep
            best_key_val[key] = sort_val
    return list(best.values())


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------

def compute_scope_weighted_risk(
    dependencies: list[DependencyInput],
    weights: dict[str, float] | None = None,
) -> ExplainabilityPayload:
    """Compute scope-weighted dependency risk score.

    Returns an :class:`ExplainabilityPayload` with score, label,
    top_drivers, scope_note, and confidence_note.

    Pure function — no DB access, no API calls, no side effects.
    """
    # --- empty input -------------------------------------------------------
    if not dependencies:
        return ExplainabilityPayload(
            scope_weighted_dependency_risk=0.0,
            risk_label="low",
            top_drivers=[],
            scope_note=_SCOPE_NOTE,
            confidence_note=_EMPTY_CONFIDENCE_NOTE,
        )

    # --- deduplicate -------------------------------------------------------
    deps = _deduplicate(dependencies)

    # --- per-dependency contributions --------------------------------------
    # Each entry: (dep, scope, nr, contribution)
    records: list[tuple[DependencyInput, str, float, float]] = []
    for dep in deps:
        scope = dep.dependency_scope or "unknown"
        nr = _normalized_risk(dep)
        sw = get_scope_weight(scope, weights)
        cm = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
        contribution = round(sw * nr * cm, 6)
        records.append((dep, scope, nr, contribution))

    # --- aggregation -------------------------------------------------------
    # Sort contributions before summing for deterministic floating-point results
    sorted_contributions = sorted((r[3] for r in records), reverse=True)
    total_weighted_sum = sum(sorted_contributions)
    max_possible = float(len(deps)) * 1.0  # theoretical max per dep = 1.0
    score = round(total_weighted_sum / max_possible, 6) if max_possible > 0 else 0.0

    # --- risk label --------------------------------------------------------
    risk_label = _classify_risk_label(score)

    # --- top drivers -------------------------------------------------------
    # Sort: contribution desc, then package_name asc (stable)
    sorted_records = sorted(
        records,
        key=lambda r: (-r[3], r[0].package_name),
    )

    top_drivers: list[TopDriver] = []
    if total_weighted_sum > 0:
        for dep, scope, nr, contribution in sorted_records[:5]:
            driver_contribution = round(contribution / total_weighted_sum, 6)
            top_drivers.append(
                TopDriver(
                    package=dep.package_name,
                    scope=scope,
                    reason=_build_reason(dep, scope, nr),
                    contribution=driver_contribution,
                )
            )

    # --- confidence note ---------------------------------------------------
    unknown_count = sum(
        1 for dep, scope, _, _ in records if scope == "unknown"
    )
    unknown_ratio = unknown_count / len(deps) if deps else 0.0
    conf_note = _confidence_note(unknown_ratio)

    return ExplainabilityPayload(
        scope_weighted_dependency_risk=score,
        risk_label=risk_label,
        top_drivers=top_drivers,
        scope_note=_SCOPE_NOTE,
        confidence_note=conf_note,
    )


# ---------------------------------------------------------------------------
# Scope exposure metrics
# ---------------------------------------------------------------------------

def compute_scope_exposure_metrics(
    dependencies: list[DependencyInput],
    weights: dict[str, float] | None = None,
) -> ScopeExposureMetrics:
    """Compute scope exposure metrics from dependency list.

    Pure function. Division-safe (returns 0.0 when totals are zero).
    Null or missing ``dependency_scope`` is treated as ``'unknown'``.
    Duplicates are removed via :func:`_deduplicate` before computing.
    """
    if not dependencies:
        return ScopeExposureMetrics(
            runtime_dependency_exposure=0.0,
            transitive_runtime_dependency_exposure=0.0,
            scope_weighted_dependency_exposure=0.0,
            vulnerable_runtime_dependency_count=0,
            vulnerable_transitive_runtime_dependency_count=0,
            high_risk_runtime_dependency_count=0,
            unknown_scope_dependency_ratio=0.0,
        )

    deps = _deduplicate(dependencies)
    w = weights or DEFAULT_SCOPE_WEIGHTS

    # Normalise scope once per dependency
    scoped: list[tuple[DependencyInput, str]] = [
        (dep, dep.dependency_scope or "unknown") for dep in deps
    ]

    # --- partition by dependency_type -------------------------------------
    direct = [(dep, s) for dep, s in scoped if dep.dependency_type == "direct"]
    transitive = [(dep, s) for dep, s in scoped if dep.dependency_type == "transitive"]

    # --- ratio metrics ----------------------------------------------------
    direct_runtime = sum(1 for _, s in direct if s == "runtime")
    runtime_dependency_exposure = (
        direct_runtime / len(direct) if direct else 0.0
    )

    transitive_runtime = sum(1 for _, s in transitive if s == "runtime")
    transitive_runtime_dependency_exposure = (
        transitive_runtime / len(transitive) if transitive else 0.0
    )

    # --- weighted exposure ------------------------------------------------
    max_weight = max(w.values()) if w else 1.0
    weight_sum = sum(get_scope_weight(s, w) for _, s in scoped)
    scope_weighted_dependency_exposure = (
        weight_sum / (len(deps) * max_weight) if deps and max_weight > 0 else 0.0
    )

    # --- count metrics ----------------------------------------------------
    vulnerable_runtime_dependency_count = sum(
        1 for dep, s in direct
        if s == "runtime" and dep.vulnerability_count > 0
    )

    vulnerable_transitive_runtime_dependency_count = sum(
        1 for dep, s in transitive
        if s == "runtime" and dep.vulnerability_count > 0
    )

    high_risk_runtime_dependency_count = sum(
        1 for dep, s in direct
        if s == "runtime"
        and dep.risk_score is not None
        and dep.risk_score > 70
    )

    # --- unknown ratio ----------------------------------------------------
    unknown_count = sum(1 for _, s in scoped if s == "unknown")
    unknown_scope_dependency_ratio = (
        unknown_count / len(deps) if deps else 0.0
    )

    return ScopeExposureMetrics(
        runtime_dependency_exposure=runtime_dependency_exposure,
        transitive_runtime_dependency_exposure=transitive_runtime_dependency_exposure,
        scope_weighted_dependency_exposure=scope_weighted_dependency_exposure,
        vulnerable_runtime_dependency_count=vulnerable_runtime_dependency_count,
        vulnerable_transitive_runtime_dependency_count=vulnerable_transitive_runtime_dependency_count,
        high_risk_runtime_dependency_count=high_risk_runtime_dependency_count,
        unknown_scope_dependency_ratio=unknown_scope_dependency_ratio,
    )
