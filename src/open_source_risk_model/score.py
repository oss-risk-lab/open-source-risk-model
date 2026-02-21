from __future__ import annotations

from typing import Any, Dict, Optional

from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk
from open_source_risk_model.config.feature_mapping_config import get_composite_config


# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------

_cfg = get_composite_config()

# Legacy / current composite config (what you already have)
_COMPOSITE_CFG = _cfg.get("composite", {})
FEATURE_WEIGHTS: Dict[str, float] = _COMPOSITE_CFG.get("feature_weights", {})
_COMPOSITE_BANDS = _COMPOSITE_CFG.get("bands", [])

# Optional maintenance-only composite (if you add it to YAML)
_MAINTENANCE_CFG = _cfg.get("maintenance_composite")
_MAINTENANCE_WEIGHTS: Dict[str, float] = {}
_MAINTENANCE_BANDS = []
if _MAINTENANCE_CFG is not None:
    _MAINTENANCE_WEIGHTS = _MAINTENANCE_CFG.get("feature_weights", {})
    _MAINTENANCE_BANDS = _MAINTENANCE_CFG.get("bands", [])

# Optional license-only bands (if you add them)
_LICENSE_BANDS = []
if "license_composite" in _cfg:
    _LICENSE_BANDS = _cfg["license_composite"].get("bands", [])

UNCERTAINTY_PENALTY = 1.0  # 1.0 = worst-case for missing expected weight
MIN_COVERAGE_FOR_CONFIDENT_SCORE = 0.80

# Missing signal imputation used inside _weighted_composite().
# 0.0 = don't penalize missing; missingness is handled via coverage/uncertainty.
MISSING_DEFAULT_RISK = 0.5

MIN_CONTRIBUTORS_FOR_BUS_FACTOR = 5

# ---------------------------------------------------------------------------
# Feature-level risk computation
# ---------------------------------------------------------------------------

def compute_feature_risks(raw: Dict[str, Any]) -> Dict[str, float]:
    """
    Convert raw GitHub / derived fields into per-feature risk scores in [0, 1].
    """
    risks: Dict[str, float] = {}

    # 1. days_since_last_push (days; higher = riskier)
    if "days_since_last_push" in raw:
        risks["days_since_last_push"] = compute_feature_risk(
            "days_since_last_push",
            float(raw["days_since_last_push"]),
        )

    # 2. days_since_last_release (days; higher = riskier)
    if "days_since_last_release" in raw and raw["days_since_last_release"] is not None:
        risks["days_since_last_release"] = compute_feature_risk(
            "days_since_last_release",
            float(raw["days_since_last_release"]),
        )

    # 3. fraction_issues_closed_12mo (0..1; higher = better, so mapping inverts to risk)
    if "fraction_issues_closed_12mo" in raw and raw["fraction_issues_closed_12mo"] is not None:
        risks["fraction_issues_closed_12mo"] = compute_feature_risk(
            "fraction_issues_closed_12mo",
            float(raw["fraction_issues_closed_12mo"]),
        )

    # 4. fraction_open_issues_stale_180d (0..1; higher = riskier)
    if "fraction_open_issues_stale_180d" in raw and raw["fraction_open_issues_stale_180d"] is not None:
        risks["fraction_open_issues_stale_180d"] = compute_feature_risk(
            "fraction_open_issues_stale_180d",
            float(raw["fraction_open_issues_stale_180d"]),
        )

    # 5. stars_count (raw: stargazers_count; higher = less risky)
    if "stargazers_count" in raw:
        risks["stars_count"] = compute_feature_risk(
            "stars_count",
            float(raw["stargazers_count"]),
        )

    # 6. contributors_count (all-time; higher = less risky)
    if "contributors_count" in raw and raw["contributors_count"] is not None:
        risks["contributors_count"] = compute_feature_risk(
            "contributors_count",
            float(raw["contributors_count"]),
        )

    # 7. issues_per_contributor (open issues / contributors; higher = riskier)
    if (
        "open_issues_count" in raw
        and "contributors_count" in raw
        and raw["contributors_count"] is not None
    ):
        issues = float(raw["open_issues_count"])
        contributors = float(raw["contributors_count"])
        ratio = issues / max(contributors, 1.0)

        risks["issues_per_contributor"] = compute_feature_risk(
            "issues_per_contributor",
            ratio,
        )

    # 8. contributors_last_12mo (count; higher = less risky)
    if "contributors_last_12mo" in raw:
        risks["contributors_last_12mo"] = compute_feature_risk(
            "contributors_last_12mo",
            float(raw["contributors_last_12mo"]),
        )

    # 9. top_contributor_fraction_12mo (0..1; higher = riskier)
    if (
        "top_contributor_fraction_12mo" in raw
        and raw["top_contributor_fraction_12mo"] is not None
        and raw.get("contributors_last_12mo", 0) >= MIN_CONTRIBUTORS_FOR_BUS_FACTOR
    ):
        risks["top_contributor_fraction_12mo"] = compute_feature_risk(
            "top_contributor_fraction_12mo",
            float(raw["top_contributor_fraction_12mo"]),
        )

    # 10. archived (bool -> 0/1; archived=True = riskier)
    if "archived" in raw:
        archived_flag = 1.0 if raw["archived"] else 0.0
        risks["archived"] = compute_feature_risk("archived", archived_flag)

    # 11. open_issues_count (count; higher = riskier)
    if "open_issues_count" in raw:
        risks["open_issues_count"] = compute_feature_risk(
            "open_issues_count",
            float(raw["open_issues_count"]),
        )

    # 12. license_risk (SPDX string or None; mapping handles missing/unknown)
    if "license_spdx_id" in raw:
        risks["license_risk"] = compute_feature_risk(
            "license_risk",
            raw["license_spdx_id"],
        )

    # 13. avg_time_to_first_maintainer_response_days (days; higher = riskier)
    if "avg_time_to_first_maintainer_response_days" in raw:
        risks["avg_time_to_first_maintainer_response_days"] = compute_feature_risk(
            "avg_time_to_first_maintainer_response_days",
            float(raw["avg_time_to_first_maintainer_response_days"]),
        )

    # 14. fraction_unanswered_after_30d (0..1; higher = riskier)
    if "fraction_unanswered_after_30d" in raw:
        risks["fraction_unanswered_after_30d"] = compute_feature_risk(
            "fraction_unanswered_after_30d",
            float(raw["fraction_unanswered_after_30d"]),
        )

    # 15. median_time_to_close_days (days; higher = riskier)
    if "median_time_to_close_days" in raw:
        risks["median_time_to_close_days"] = compute_feature_risk(
            "median_time_to_close_days",
            float(raw["median_time_to_close_days"]),
        )

    # 16. open_issue_age_p90_days (days; higher = riskier)
    if "open_issue_age_p90_days" in raw:
        risks["open_issue_age_p90_days"] = compute_feature_risk(
            "open_issue_age_p90_days",
            float(raw["open_issue_age_p90_days"]),
        )

    return risks



# ---------------------------------------------------------------------------
# Legacy composite (current behavior)
# ---------------------------------------------------------------------------

def _weighted_composite(
    feature_risks: Dict[str, float],
    weights: Dict[str, float],
    *,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = (raw or {}).get("__meta__") or {}
    feature_status = meta.get("feature_status") or {}
    has_issues = bool(meta.get("has_issues", True))

    # --- derived feature dependencies ---
    # issues_per_contributor requires BOTH open_issues_count + contributors_count.
    # If dependency is missing, FORCE not_applicable (override any prior status).
    if raw:
        if ("contributors_count" not in raw) or (raw.get("contributors_count") is None) or (raw.get("open_issues_count") is None):
            feature_status["issues_per_contributor"] = "not_applicable"

    if not has_issues:
        for k in (
            "fraction_issues_closed_12mo",
            "fraction_open_issues_stale_180d",
            "open_issues_count",
            "issues_per_contributor",
        ):
            feature_status.setdefault(k, "not_applicable")
            
    if raw:
        cl12 = raw.get("contributors_last_12mo", 0)
        if cl12 < MIN_CONTRIBUTORS_FOR_BUS_FACTOR:
            feature_status["top_contributor_fraction_12mo"] = "not_applicable"

    # If contributors_count is unavailable due to API restrictions/errors,
    # FORCE contributors_count + issues_per_contributor to not_applicable (override).
    if feature_status.get("contributors_count") in ("forbidden", "rate_limited", "not_found", "error"):
        feature_status["contributors_count"] = "not_applicable"
        feature_status["issues_per_contributor"] = "not_applicable"

    expected_weight = 0.0
    observed_weight = 0.0
    weighted_sum = 0.0

    weighted_breakdown: Dict[str, float] = {}
    missing_weight_by_feature: Dict[str, float] = {}

    for name, weight in weights.items():
        w = float(weight)

        # NEW: skip zero-weight features entirely
        if w <= 0.0:
            continue

        st = feature_status.get(name)
        if st in ("disabled", "not_applicable"):
            continue

        expected_weight += w

        if name not in feature_risks:
            # Missing signal: do NOT reward or punish.
            # Neutral-impute into the mean, but keep it "missing" for coverage/uncertainty.
            missing_weight_by_feature[name] = w
            weighted_sum += MISSING_DEFAULT_RISK * w
            continue

        r = float(feature_risks[name])
        contrib = r * w

        weighted_breakdown[name] = contrib
        weighted_sum += contrib
        observed_weight += w

    # Mean risk uses expected_weight (present + missing), so missing doesn't collapse the score.
    observed_risk = weighted_sum / expected_weight if expected_weight > 0 else 0.0
    coverage = (observed_weight / expected_weight) if expected_weight > 0 else 0.0


    risk_with_uncertainty = min(1.0, observed_risk + (1.0 - coverage) * UNCERTAINTY_PENALTY)

    if coverage >= 0.95:
        confidence_label = "high"
    elif coverage >= 0.80:
        confidence_label = "medium"
    else:
        confidence_label = "low"

    return {
        "overall_risk": observed_risk,
        "risk_with_uncertainty": risk_with_uncertainty,
        "weighted_breakdown": weighted_breakdown,
        "weighted_coverage": coverage,
        "confidence": confidence_label,
        "expected_weight": expected_weight,
        "observed_weight": observed_weight,
        "missing_weight_by_feature": missing_weight_by_feature,
    }

def compute_composite_risk(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute overall composite risk using the 'composite.feature_weights'
    in the YAML. This is your original behavior and remains for backward
    compatibility.

    Returns:
      {
        "overall_risk": float,
        "feature_risks": { ... },
        "weighted_breakdown": { ... }
      }
    """
    feature_risks = compute_feature_risks(raw)
    composite = _weighted_composite(feature_risks, FEATURE_WEIGHTS, raw=raw)

    return {
        "overall_risk": composite["overall_risk"],
        "risk_with_uncertainty": composite["risk_with_uncertainty"],
        "weighted_coverage": composite["weighted_coverage"],
        "confidence": composite["confidence"],
        "missing_weight_by_feature": composite["missing_weight_by_feature"],
        "feature_risks": feature_risks,
        "weighted_breakdown": composite["weighted_breakdown"],
    }

def classify_overall_risk(score: float) -> str:
    """
    Map the numeric composite score to a label using composite.bands in YAML.
    """
    for band in _COMPOSITE_BANDS:
        if score <= band["max"]:
            return band["name"]
    return "unknown"


# ---------------------------------------------------------------------------
# New: maintenance-only composite (no license) + license-aware overall
# ---------------------------------------------------------------------------

def compute_maintenance_risk(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute a composite score focused on maintenance/health signals only.

    Uses 'maintenance_composite.feature_weights' if present in YAML,
    otherwise falls back to the main 'composite.feature_weights'.
    """
    feature_risks = compute_feature_risks(raw)

    # If you have defined maintenance_composite in YAML, use that.
    # Otherwise, fall back to the existing composite weights.
    weights = _MAINTENANCE_WEIGHTS or FEATURE_WEIGHTS

    composite = _weighted_composite(feature_risks, weights, raw=raw)

    return {
        # base score (what you already print as maintenance_risk)
        "overall_risk": composite["overall_risk"],

        # uncertainty-aware score
        "risk_with_uncertainty": composite.get("risk_with_uncertainty", composite["overall_risk"]),

        # coverage metrics
        "weighted_coverage": composite.get("weighted_coverage", 0.0),

        # confidence + missing-weight introspection (THIS fixes your None)
        "confidence": composite.get("confidence", "unknown"),
        "missing_weight_by_feature": composite.get("missing_weight_by_feature", {}),

        # introspection
        "feature_risks": feature_risks,
        "weighted_breakdown": composite["weighted_breakdown"],
        "feature_status": composite.get("feature_status", {}),
    }



def classify_maintenance_risk(score: float) -> str:
    """
    Classify maintenance risk using maintenance_composite.bands if present,
    otherwise fall back to composite.bands.
    """
    bands = _MAINTENANCE_BANDS or _COMPOSITE_BANDS
    for band in bands:
        if score <= band["max"]:
            return band["name"]
    return "unknown"


def classify_license_risk(license_risk: float) -> str:
    """
    Classify license risk using license_composite.bands if present,
    otherwise fall back to composite.bands.
    """
    if license_risk is None:
        return "unknown"
    bands = _LICENSE_BANDS or _COMPOSITE_BANDS
    for band in bands:
        if license_risk <= band["max"]:
            return band["name"]
    return "unknown"

def compute_overall_risk(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deprecated: for now we treat maintenance_risk as the primary scalar and
    keep license_risk as a separate dimension. This function just forwards
    to compute_maintenance_risk and includes license_risk for convenience.
    """
    maint = compute_maintenance_risk(raw)
    feature_risks = maint["feature_risks"]
    license_risk = feature_risks.get("license_risk", None)

    return {
        "overall_risk": maint["overall_risk"],
        "maintenance_risk": maint["overall_risk"],
        "maintenance_risk_with_uncertainty": maint["risk_with_uncertainty"],
        "maintenance_coverage": maint["weighted_coverage"],
        "maintenance_confidence": maint["confidence"],
        "missing_weight_by_feature": maint["missing_weight_by_feature"],
        "license_risk": license_risk,
        "feature_risks": feature_risks,
        "maintenance_breakdown": maint["weighted_breakdown"],
    }


