# -----------------------------------------------------------------------------
# test_option_a.py
#
# Standalone test harness for the option_a mapping.
# Imports the option_a module, runs sample numeric values through the linear
# scaling mapping, and prints results.
#
# Intended to verify correct behavior of option_a independently of dispatcher
# integration or baseline population loading.
# -----------------------------------------------------------------------------

from open_source_risk_model.config.feature_mapping_config import FEATURE_MAPPINGS
from open_source_risk_model.feature_mappings.option_a import apply_option_a
from open_source_risk_model.utils.plotting import plot_piecewise_mapping

cfg = FEATURE_MAPPINGS["days_since_last_push_option_a"]
anchors = cfg["anchors"]

print("Risk at 0 days:", apply_option_a(0, anchors))
print("Risk at 45 days:", apply_option_a(45, anchors))
print("Risk at 200 days:", apply_option_a(200, anchors))

plot_piecewise_mapping(anchors, "Days Since Last Push — Option A").show()
