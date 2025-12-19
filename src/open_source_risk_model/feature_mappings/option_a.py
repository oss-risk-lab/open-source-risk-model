# src/open_source_risk_model/feature_mappings/option_a.py
# -----------------------------------------------------------------------------
# option_a.py
# src/open_source_risk_model/feature_mappings/option_a.py
# -----------------------------------------------------------------------------
# option_a.py
#
# Piecewise linear risk mapping using anchors.
# Typically maps a numeric feature to a normalized risk in [0, 1] by
# interpolating between (value, risk) anchor points.
#
# Appropriate for features where you want explicit, hand-crafted control over
# how risk increases with the feature value.
# -----------------------------------------------------------------------------

from typing import List, Tuple


def apply_option_a(value: float, anchors: List[Tuple[float, float]]) -> float:
    """
    Map a numeric value to a risk score using piecewise linear interpolation
    between (x, y) anchor points.

    Args:
      value:
        Raw feature value (e.g., days_since_last_push).
      anchors:
        List of (x, y) tuples where:
          - x is the feature value (same units as `value`)
          - y is the risk score in [0, 1]

        Example for days_since_last_push (in days):
          anchors = [
              (0.0,   0.0),
              (7.0,   0.0),
              (30.0,  0.3),
              (90.0,  0.4),
              (365.0, 0.6),
              (730.0, 0.8),
              (3650.0, 1.0),
          ]

    Returns:
      Risk in [0, 1] via:
        - constant extension below the first anchor
        - constant extension above the last anchor
        - linear interpolation between anchor pairs
    """
    if not anchors:
        raise ValueError("anchors must be a non-empty list of (x, y) pairs")

    # Ensure anchors are sorted by x
    anchors = sorted(anchors, key=lambda t: t[0])

    # Below the first anchor → clamp to its risk
    if value <= anchors[0][0]:
        return float(max(0.0, min(1.0, anchors[0][1])))

    # Above the last anchor → clamp to its risk
    if value >= anchors[-1][0]:
        return float(max(0.0, min(1.0, anchors[-1][1])))

    # Piecewise linear interpolation
    for (x1, y1), (x2, y2) in zip(anchors, anchors[1:]):
        if x1 <= value <= x2:
            if x2 == x1:
                # Degenerate segment; just use the upper risk
                y = y2
            else:
                t = (value - x1) / (x2 - x1)
                y = y1 + t * (y2 - y1)

            # Clamp numerically to [0, 1]
            return float(max(0.0, min(1.0, y)))

    # Shouldn't happen if anchors cover the range
    raise ValueError(f"value {value} not in any anchor interval; check anchors ordering")
