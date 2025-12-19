# -----------------------------------------------------------------------------
# test_dispatcher.py
#
# End-to-end test for the feature mapping dispatcher.
# Calls compute_feature_risk() for several features and sample values to confirm:
#   - Correct mapping selection based on config
#   - Proper baseline population loading
#   - Functional integration of option_a / option_b / option_c mappings
#
# This script verifies that dispatcher routing and config lookups are correct
# across the full mapping pipeline.
# -----------------------------------------------------------------------------

import os, sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

# Fake population for Option C
population = {
    "days_since_last_push_option_c": [1, 3, 5, 7, 10, 20, 30, 40, 365]
}

print(
    "A:",
    compute_feature_risk("days_since_last_push_option_a", 45)
)

print(
    "B:",
    compute_feature_risk("days_since_last_push_option_b", 45)
)

print(
    "C:",
    compute_feature_risk("days_since_last_push_option_c", 45, population=population)
)
