# -----------------------------------------------------------------------------
# test_auto_load_population.py
#
# Development / sanity-check driver for risk mappings.
# Loads the "days_since_last_push" feature, computes risk scores for example
# numeric values (e.g. 3, 7, 30, 365 days), and prints the results.
#
# This script exercises the full pipeline:
#   compute_feature_risk() → dispatcher → option_C → baseline JSON population
#
# No GitHub API access is performed here — all data is read from static JSON
# files in data/baseline/.
# -----------------------------------------------------------------------------

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

# test values (days since push)
for v in [0, 3, 7, 30, 90, 365]:
    risk = compute_feature_risk("days_since_last_push", v)
    print(f"{v:3d} days -> risk={risk:.3f}")
