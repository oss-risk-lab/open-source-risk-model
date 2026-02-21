# src/open_source_risk_model/config/feature_mapping_config.py
# -----------------------------------------------------------------------------
# feature_mapping_config.py
#
# Central configuration dictionary describing all features in the risk model.
# Each entry specifies:
#   - mapping type (option_a / option_b / option_c)
#   - baseline population filename (for option_c)
#   - any optional mapping parameters
#
# This file is the source of truth for which JSON baseline file is associated
# with each feature, and which mapping implementation the dispatcher should use.
# -----------------------------------------------------------------------------
import os
import yaml

FEATURE_MAPPINGS = {
    "days_since_last_push": {
        "type": "option_a",
        "anchors": [
            (0.0,    0.00),
            (7.0,    0.20),
            (30.0,   0.40),
            (90.0,   0.60),
            (180.0,  0.80),
            (365.0,  1.00),
        ],
    },
    "days_since_last_release": {
        "type": "option_a",
        "anchors": [
            (0.0, 0.00),
            (30.0, 0.20),
            (90.0, 0.50),
            (180.0, 0.75),
            (365.0, 0.90),
            (730.0, 1.00),
        ],
    },
    
    "stars_count": {
        "type": "option_a",
        "anchors": [
            (0.0,      1.00),
            (50.0,     0.80),
            (200.0,    0.60),
            (1000.0,   0.35),
            (10000.0,  0.10),
            (50000.0,  0.03),
            (200000.0, 0.00),
        ],
    },

    "contributors_count": {
        "type": "option_b",
        "min_value": 1.0,       # 1 contributor = worst
        "max_value": 5000.0,      # 5000+ contributors = best
        "higher_is_riskier": False,
    },
    "archived": {
        "type": "option_a",
        # We'll pass 0.0 for not archived, 1.0 for archived
        "anchors": [
            (0.0, 0.0),  # not archived → no risk from this factor
            (1.0, 1.0),  # archived     → full risk from this factor
        ],
    },
    
    "issues_per_contributor": {
        "type": "option_a",
        "anchors": [
            (0.00, 0.00),
            (0.05, 0.05),
            (0.25, 0.20),
            (0.50, 0.35),
            (1.00, 0.55),
            (2.00, 0.75),
            (4.00, 0.90),
            (8.00, 1.00),
        ],
    },
    
    "open_issues_count": {
        "type": "option_a",
        "anchors": [
            (0.0,      0.00),
            (50.0,     0.10),
            (200.0,    0.20),
            (1000.0,   0.40),
            (5000.0,   0.70),
            (20000.0,  1.00),
        ],
    },
    "fraction_issues_closed_12mo": {
        "type": "option_a",
        "anchors": [
            (0.00, 1.00),
            (0.25, 0.85),
            (0.50, 0.60),
            (0.75, 0.30),
            (0.90, 0.10),
            (1.00, 0.00),
        ],
    },
    "fraction_open_issues_stale_180d": {
        "type": "option_a",
        "anchors": [
            (0.00, 0.00),
            (0.20, 0.10),
            (0.40, 0.25),
            (0.60, 0.45),
            (0.80, 0.70),
            (0.90, 0.85),
            (1.00, 1.00),
        ],
    },

    "contributors_last_12mo": {
        "type": "option_a",
        "anchors": [
            (0.0, 1.00),
            (1.0, 0.90),
            (2.0, 0.80),
            (5.0, 0.55),
            (10.0, 0.30),
            (25.0, 0.10),
            (50.0, 0.00),
        ],
    },
    
    "top_contributor_fraction_12mo": {
        "type": "option_a",
        "anchors": [
            (0.20, 0.00),
            (0.35, 0.15),
            (0.50, 0.40),
            (0.70, 0.75),
            (0.90, 1.00),
        ],
    },
    "avg_time_to_first_maintainer_response_days": {
        "type": "option_a",
        # days; higher = riskier
        "anchors": [
            (0.0,  0.00),
            (1.0,  0.15),
            (3.0,  0.35),
            (7.0,  0.60),
            (14.0, 0.80),
            (30.0, 1.00),
        ],
    },

    "fraction_unanswered_after_30d": {
        "type": "option_a",
        # 0..1; higher = riskier
        "anchors": [
            (0.00, 0.00),
            (0.05, 0.15),
            (0.10, 0.30),
            (0.20, 0.55),
            (0.35, 0.75),
            (0.50, 0.90),
            (1.00, 1.00),
        ],
    },

    "median_time_to_close_days": {
        "type": "option_a",
        # days; higher = riskier
        "anchors": [
            (0.0,   0.00),
            (7.0,   0.15),
            (14.0,  0.30),
            (30.0,  0.50),
            (60.0,  0.65),
            (120.0, 0.80),
            (365.0, 1.00),
        ],
    },

    "open_issue_age_p90_days": {
        "type": "option_a",
        # days; higher = riskier
        "anchors": [
            (0.0,   0.00),
            (30.0,  0.20),
            (90.0,  0.40),
            (180.0, 0.60),
            (365.0, 0.75),
            (730.0, 0.85),
            (1460.0, 0.95),
            (2190.0, 1.00),
        ],
    },


    "license_risk": {
      "type": "license_table",
      "table": {
          # Permissive – very low risk for most orgs
          "MIT":              0.0,
          "BSD-3-Clause":     0.0,
          "BSD-2-Clause":     0.0,
          "Apache-2.0":       0.0,
          "ISC":              0.0,
          "PSF-2.0":          0.0,   # Python Software Foundation

          # Weak copyleft – some obligations, usually acceptable
          "LGPL-2.1":         0.3,
          "LGPL-2.1-only":    0.3,
          "LGPL-2.1-or-later":0.3,
          "LGPL-3.0":         0.3,
          "LGPL-3.0-only":    0.3,
          "LGPL-3.0-or-later":0.3,
          "MPL-2.0":          0.3,

          # Strong copyleft – can conflict with proprietary distribution
          "GPL-2.0":          0.6,
          "GPL-2.0-only":     0.6,
          "GPL-2.0-or-later": 0.6,
          "GPL-3.0":          0.6,
          "GPL-3.0-only":     0.6,
          "GPL-3.0-or-later": 0.6,

          # Affero – very strong copyleft, including network use
          "AGPL-3.0":         0.8,
          "AGPL-3.0-only":    0.8,
          "AGPL-3.0-or-later":0.8,

          # GitHub “we don’t know” value
          "NOASSERTION":      None,

          # fallback for anything unknown or missing
          "__DEFAULT__":      None,
      },
    },
}



# -----------------------------------------------------------------------------
# Composite config validation
# -----------------------------------------------------------------------------

def _validate_and_normalize_composite_config(cfg: dict) -> dict:
    """
    Structural validation for composite_config.yaml.

    - Ensures feature_weights are numeric and non-negative.
    - Normalizes weights to sum to 1.0 for interpretability.
      (Scoring is scale-invariant, so this will not change the score.)
    - Stores the original sum under __weights_sum__ in each section.
    """
    if not isinstance(cfg, dict):
        return cfg

    for section_name in ("composite", "maintenance_composite"):
        section = cfg.get(section_name)
        if not isinstance(section, dict):
            continue

        weights = section.get("feature_weights")
        if weights is None:
            continue
        if not isinstance(weights, dict):
            raise ValueError(f"{section_name}.feature_weights must be a mapping")

        cleaned: dict[str, float] = {}
        for k, v in weights.items():
            try:
                fv = float(v)
            except Exception as e:
                raise ValueError(f"{section_name}.feature_weights[{k!r}] must be numeric") from e
            if fv < 0:
                raise ValueError(f"{section_name}.feature_weights[{k!r}] must be >= 0")
            cleaned[k] = fv

        total = sum(cleaned.values())
        section["__weights_sum__"] = total

        if total > 0:
            section["feature_weights"] = {k: (v / total) for k, v in cleaned.items()}
        else:
            section["feature_weights"] = cleaned

    return cfg

def get_composite_config():
    """
    Loads composite_config.yaml from the same config directory.
    """
    config_dir = os.path.dirname(__file__)
    yaml_path = os.path.join(config_dir, "composite_config.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(
            f"Missing composite_config.yaml in {config_dir}. "
            "Please create it with composite feature weights."
        )

    with open(yaml_path, "r") as f:
        cfg = yaml.safe_load(f)

    # Validate + normalize weights for composite sections (structural correctness)
    cfg = _validate_and_normalize_composite_config(cfg)

    return cfg

