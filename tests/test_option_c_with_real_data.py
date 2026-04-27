# -----------------------------------------------------------------------------
# test_option_c_with_real_data.py
#
# Experimental test of the option_c mapping using an actual JSON population
# file (e.g. days_since_last_push_population_combined.json) rather than
# synthetic values.
#
# Loads real population values, applies percentile mapping to multiple sample
# test inputs, and prints new risk scores. Useful for tuning gamma and
# evaluating separation of real-world values (3, 30, 90, 365 days, etc.).
#
# Excellent script for verifying mapping performance before committing config
# changes to feature_mapping_config.py.
# -----------------------------------------------------------------------------

import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from open_source_risk_model.feature_mappings.dispatcher import compute_feature_risk

# Load real distribution
population_path = os.path.join(
    PROJECT_ROOT, "data", "baseline", "days_since_last_push_population.json"
)
with open(population_path, "r") as f:
    days_values = json.load(f)

population = {
    "days_since_last_push_option_c": days_values
}

print("Population values:", days_values)
print()

for v in [0, 1, 3, 7, 30]:
    risk = compute_feature_risk(
        "days_since_last_push_option_c",
        v,
        population=population,
    )
    print(f"value={v:2d} days -> risk={risk:.2f}")
