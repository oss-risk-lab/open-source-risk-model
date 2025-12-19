# -----------------------------------------------------------------------------
# test_option_c.py
#
# Standalone test harness for the option_c mapping.
# Loads a population dataset (typically JSON of days_since_last_push values),
# applies the empirical CDF mapping to sample values, and prints the resulting
# risk scores.
#
# Intended to validate percentile behavior, gamma transforms, and population
# loading logic independently of dispatcher routing.
# -----------------------------------------------------------------------------

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from open_source_risk_model.feature_mappings.option_c import apply_option_c

# Fake population: lots of fresh repos, some stale ones
population = [
    1, 3, 5, 7, 10,
    20, 30, 40, 60, 90,
    120, 150, 200, 250, 365,
]

for v in [5, 30, 120, 365]:
    risk = apply_option_c(v, population)
    print(f"value={v:3d} days -> risk={risk:.2f}")
