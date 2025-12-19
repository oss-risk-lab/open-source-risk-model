# src/open_source_risk_model/feature_mappings/option_b.py
# -----------------------------------------------------------------------------
# option_b.py
#
# Threshold / piecewise risk mapping.
# Supports simple rule-based or lookup-table style transformations for numeric
# or categorical features.
#
# Appropriate for features that are not well-suited to linear or percentile
# mappings, and instead require discrete buckets or fixed cutoffs.
# -----------------------------------------------------------------------------

from typing import Optional


def apply_option_b(
    value: float,
    *,
    min_value: float,
    max_value: float,
    higher_is_riskier: bool = True,
    clip: bool = True,
) -> float:
    """
    Linear mapping (Option B).

    Maps a raw value to a risk in [0, 1] based on min/max.

    If higher_is_riskier = True:
        min_value -> 0.0
        max_value -> 1.0

    If higher_is_riskier = False:
        min_value -> 1.0
        max_value -> 0.0
    """
    if max_value <= min_value:
        raise ValueError("max_value must be > min_value")

    # normalize to [0, 1] assuming higher is worse
    normalized = (value - min_value) / (max_value - min_value)

    if not higher_is_riskier:
        normalized = 1.0 - normalized

    if clip:
        normalized = max(0.0, min(1.0, normalized))

    return float(normalized)
