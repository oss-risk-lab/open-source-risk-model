# -----------------------------------------------------------------------------
# save_days_since_population_combined.py
#
# Helper script to combine multiple population snapshots (e.g. from repeated
# GitHub sampling runs) into a single consolidated JSON file.
#
# Reads multiple raw population arrays (days_since_last_push values), merges,
# de-duplicates, optionally sorts them, and writes a final combined JSON file
# into data/baseline/.
#
# This is typically used to maintain a stable, scalable population file for
# option_c mappings while allowing incremental sampling over time.
# -----------------------------------------------------------------------------

import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from open_source_risk_model.data_ingestion.github_repo_sampling import (
    build_days_since_last_push_population,
)


def main():
    population = build_days_since_last_push_population(mode="combined", n_each=300)

    output_dir = os.path.join(PROJECT_ROOT, "data", "baseline")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(
        output_dir, "days_since_last_push_population_combined.json"
    )

    with open(output_path, "w") as f:
        json.dump(population, f, indent=2)

    print("Saved combined population to:", output_path)


if __name__ == "__main__":
    main()
