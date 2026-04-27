# -----------------------------------------------------------------------------
# test_option_b.py
#
# Standalone test harness for the option_b mapping.
# Exercises threshold or lookup-table behavior for sample values to confirm
# expected bucket assignments and edge case handling.
#
# Useful for validating discrete or piecewise mapping behavior before wiring
# option_b into the dispatcher.
# -----------------------------------------------------------------------------

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from open_source_risk_model.config.feature_mapping_config import FEATURE_MAPPINGS
from open_source_risk_model.feature_mappings.option_b import apply_option_b

cfg = FEATURE_MAPPINGS["days_since_last_push_option_b"]

for v in [0, 30, 180, 365, 500]:
    risk = apply_option_b(
        v,
        min_value=cfg["min_value"],
        max_value=cfg["max_value"],
        higher_is_riskier=cfg["higher_is_riskier"],
    )
    print(f"value={v:3.0f} days -> risk={risk:.2f}")
