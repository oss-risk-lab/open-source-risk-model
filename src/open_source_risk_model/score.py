from __future__ import annotations

from typing import Any, Dict

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


# ---------------------------------------------------------------------------
# Feature-level risk computation
# ---------------------------------------------------------------------------

def compute_feature_risks(raw: Dict[str, Any]) -> Dict[str, float]:
    """
    Convert raw GitHub / derived fields into per-feature risk scores in [0, 1].

    Expected keys in `raw`:
      - "days_since_last_push": float
      - "stargazers_count": int
      - "contributors_count": int
      - "archived": bool
      - "open_issues_count": int
      - "license_spdx_id": Optional[str]
    """
    risks: Dict[str, float] = {}

    # 1. days_since_last_push (already in raw units of days)
    if "days_since_last_push" in raw:
        risks["days_since_last_push"] = compute_feature_risk(
            "days_since_last_push",
            float(raw["days_since_last_push"]),
        )
    # 1b. days_since_last_release
    if "days_since_last_release" in raw and raw["days_since_last_release"] is not None:
        risks["days_since_last_release"] = compute_feature_risk(
            "days_since_last_release",
            float(raw["days_since_last_release"]),
        )
    # 3c. fraction_issues_closed_12mo (0..1, higher is better)
    if "fraction_issues_closed_12mo" in raw and raw["fraction_issues_closed_12mo"] is not None:
        risks["fraction_issues_closed_12mo"] = compute_feature_risk(
            "fraction_issues_closed_12mo",
            float(raw["fraction_issues_closed_12mo"]),
        )
        
    if "fraction_open_issues_stale_180d" in raw and raw["fraction_open_issues_stale_180d"] is not None:
        risks["fraction_open_issues_stale_180d"] = compute_feature_risk(
            "fraction_open_issues_stale_180d",
            float(raw["fraction_open_issues_stale_180d"]),
    )

    # 2. stars_count (raw key: stargazers_count)
    if "stargazers_count" in raw:
        risks["stars_count"] = compute_feature_risk(
            "stars_count",
            float(raw["stargazers_count"]),
        )

    # 3. contributors_count (all-time)
    if "contributors_count" in raw:
        risks["contributors_count"] = compute_feature_risk(
            "contributors_count",
            float(raw["contributors_count"]),
        )

    # 3b. issues_per_contributor (derived)
    if "open_issues_count" in raw and "contributors_count" in raw:
        issues = float(raw["open_issues_count"])
        contributors = float(raw["contributors_count"]) or 1.0  # avoid divide-by-zero
        ratio = issues / max(contributors, 1.0)

        risks["issues_per_contributor"] = compute_feature_risk(
            "issues_per_contributor",
            ratio,
        )
        # 3d. contributors_last_12mo
    if "contributors_last_12mo" in raw:
        risks["contributors_last_12mo"] = compute_feature_risk(
            "contributors_last_12mo",
            float(raw["contributors_last_12mo"]),
        )
        # 3e. top_contributor_fraction_12mo (0..1, higher = riskier)
    if "top_contributor_fraction_12mo" in raw and raw["top_contributor_fraction_12mo"] is not None:
        risks["top_contributor_fraction_12mo"] = compute_feature_risk(
            "top_contributor_fraction_12mo",
            float(raw["top_contributor_fraction_12mo"]),
        )

    # 4. archived (bool → 0/1)
    if "archived" in raw:
        archived_flag = 1.0 if raw["archived"] else 0.0
        risks["archived"] = compute_feature_risk("archived", archived_flag)

    # 5. open_issues_count (keep mapped, may have weight 0 in YAML)
    if "open_issues_count" in raw:
        risks["open_issues_count"] = compute_feature_risk(
            "open_issues_count",
            float(raw["open_issues_count"]),
        )

    # 6. license_risk (SPDX string or None)
    if "license_spdx_id" in raw:
        risks["license_risk"] = compute_feature_risk(
            "license_risk",
            raw["license_spdx_id"],  # may be None
        )

    return risks


# ---------------------------------------------------------------------------
# Legacy composite (current behavior)
# ---------------------------------------------------------------------------

def _weighted_composite(
    feature_risks: Dict[str, float],
    weights: Dict[str, float],
) -> Dict[str, Any]:
    """
    Helper: weighted average of feature_risks using the given weights.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    weighted_breakdown: Dict[str, float] = {}

    for name, weight in weights.items():
        if name not in feature_risks:
            continue

        r = feature_risks[name]
        w = float(weight)
        contrib = r * w

        weighted_breakdown[name] = contrib
        weighted_sum += contrib
        total_weight += w

    overall_risk = weighted_sum / total_weight if total_weight > 0 else 0.0

    return {
        "overall_risk": overall_risk,
        "weighted_breakdown": weighted_breakdown,
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
    composite = _weighted_composite(feature_risks, FEATURE_WEIGHTS)

    return {
        "overall_risk": composite["overall_risk"],
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

    composite = _weighted_composite(feature_risks, weights)

    return {
        "overall_risk": composite["overall_risk"],
        "feature_risks": feature_risks,
        "weighted_breakdown": composite["weighted_breakdown"],
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
    license_risk = feature_risks.get("license_risk", 0.0)

    return {
        "overall_risk": maint["overall_risk"],   # same as maintenance
        "maintenance_risk": maint["overall_risk"],
        "license_risk": license_risk,
        "feature_risks": feature_risks,
        "maintenance_breakdown": maint["weighted_breakdown"],
    }

