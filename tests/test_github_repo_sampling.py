# -----------------------------------------------------------------------------
# test_github_repo_sampling.py
#
# Development test for GitHub repo sampling logic.
# Executes GitHub API calls using github_client.py, fetches repository metadata,
# computes derived numeric features (e.g. days_since_last_push), and prints them.
#
# This script is useful for verifying:
#   - Authentication / rate limit behavior
#   - Correct parsing of GitHub API JSON responses
#   - Proper data extraction prior to saving baseline population files
# -----------------------------------------------------------------------------

import os
import sys
import statistics as stats

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

print("PROJECT_ROOT:", PROJECT_ROOT)
print("SRC_PATH    :", SRC_PATH)

from open_source_risk_model.data_ingestion.github_repo_sampling import (
    sample_active_days_since_last_push,
    sample_typical_days_since_last_push,
    sample_stale_days_since_last_push,
    build_days_since_last_push_population,
)


def summarize(label, values):
    values_sorted = sorted(values)
    print(f"\n=== {label} ({len(values)} repos) ===")
    print("min   :", min(values_sorted))
    print("median:", stats.median(values_sorted))
    print("max   :", max(values_sorted))


def main():
    print(">>> ENTERED main() <<<")

    print("\nSampling ACTIVE repos...")
    active = sample_active_days_since_last_push(100)

    print("Sampling TYPICAL repos...")
    typical = sample_typical_days_since_last_push(100)

    print("Sampling STALE repos...")
    stale = sample_stale_days_since_last_push(100)

    print("Building COMBINED population...")
    combined = build_days_since_last_push_population(mode="combined", n_each=100)

    summarize("ACTIVE", active)
    summarize("TYPICAL", typical)
    summarize("STALE", stale)
    summarize("COMBINED", combined)


if __name__ == "__main__":
    main()

