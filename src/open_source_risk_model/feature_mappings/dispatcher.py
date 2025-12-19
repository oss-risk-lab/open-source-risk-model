# -----------------------------------------------------------------------------
# dispatcher.py
#
# Central routing logic for feature mappings.
# Responsibilities:
#   - Load baseline population data from JSON files
#   - Select mapping strategy based on feature configuration
#   - Compute final risk score for a single feature value
#
# Public API:
#   compute_feature_risk(name, value) → float
#
# This is the entry point used by spikes/test_auto_load_population.py and the
# recommended interface for application code.
# -----------------------------------------------------------------------------

import os
import json

from open_source_risk_model.config.feature_mapping_config import FEATURE_MAPPINGS

# dispatcher.py is at: src/open_source_risk_model/feature_mappings/dispatcher.py
# We want PROJECT_ROOT = /Users/.../open-source-risk-model
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_BASELINE_DIR = os.path.join(_PROJECT_ROOT, "data", "baseline")

_population_cache = {}

def _load_population(name, cfg):
    filename = cfg.get("population_file")
    if not filename:
        raise ValueError(
            f"Feature '{name}' with type 'option_c' requires 'population_file' in config."
        )

    if filename in _population_cache:
        return _population_cache[filename]

    path = os.path.join(_BASELINE_DIR, filename)
    with open(path, "r") as f:
        data = json.load(f)

    _population_cache[filename] = data
    return data


def compute_feature_risk(name: str, value, *, population=None):
    cfg = FEATURE_MAPPINGS[name]
    t = cfg["type"]

    if t == "license_table":
        table = cfg.get("table", {})
        # value is expected to be the SPDX string (or None)
        default_risk = float(table.get("__DEFAULT__", 1.0))
        return float(table.get(value, default_risk))

    if t == "option_a":
        from .option_a import apply_option_a
        return apply_option_a(value, cfg["anchors"])

    if t == "option_b":
        from .option_b import apply_option_b
        return apply_option_b(
            value,
            min_value=cfg["min_value"],
            max_value=cfg["max_value"],
            higher_is_riskier=cfg.get("higher_is_riskier", True),
        )

    if t == "option_c":
        from .option_c import apply_option_c

        if population is None:
            # AUTO LOAD
            population_values = _load_population(name, cfg)
        else:
            population_values = population

        return apply_option_c(value, population_values)


    raise ValueError(f"Unknown feature mapping type: {t}")
