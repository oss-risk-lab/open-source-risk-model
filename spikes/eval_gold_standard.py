# spikes/eval_gold_standard.py

from typing import Any, Dict, List

from open_source_risk_model.data_ingestion.gold_standard_repos import GOLD_STANDARD_REPOS
from open_source_risk_model.data_ingestion.github_features import (
    _github_session,
    fetch_repo_features,
)
from open_source_risk_model.score import (
    compute_maintenance_risk,
    classify_maintenance_risk,
    classify_license_risk,
)


def evaluate_gold_standard_repos() -> List[Dict[str, Any]]:
    session = _github_session()
    rows: List[Dict[str, Any]] = []

    for full_name in GOLD_STANDARD_REPOS:
        print(f"Fetching {full_name}...")
        repo_features = fetch_repo_features(full_name, session=session)
        raw = repo_features.as_raw_dict()

        # DEBUG: inspect raw license value from GitHub
        if full_name in ("numpy/numpy", "pytorch/pytorch", "matplotlib/matplotlib", "torvalds/linux"):
            print(f"LICENSE RAW {full_name}: {repr(raw.get('license_spdx_id'))}")

        # --- maintenance-only composite ---
        maint = compute_maintenance_risk(raw)
        maintenance_risk = maint["overall_risk"]
        feature_risks = maint["feature_risks"]
        maintenance_label = classify_maintenance_risk(maintenance_risk)

        # license_risk just comes from the feature_risks dict
        license_risk = feature_risks.get("license_risk", 0.0)
        license_label = classify_license_risk(license_risk)

        print("\nRISK BREAKDOWN:")
        print(f"  maintenance_risk  = {maintenance_risk:.3f} ({maintenance_label})")
        print(f"  license_risk      = {license_risk:.3f} ({license_label})")
        print()

        # Optional debug for a few key repos
        if True:
            print(f"DEBUG {full_name}")
            print(f"  maintenance_risk  = {maintenance_risk:.3f} ({maintenance_label})")
            print(f"  license_risk      = {license_risk:.3f} ({license_label})")
            print("  feature_risks:")
            for name, risk in feature_risks.items():
                print(f"    {name:22s} -> {risk:.3f}")
            print()

        # Build row for CSV / later analysis
        row: Dict[str, Any] = {
            "repo": full_name,
            "maintenance_risk": maintenance_risk,
            "maintenance_label": maintenance_label,
            "license_risk": license_risk,
            "license_label": license_label,
        }

        # Add per-feature risks as separate columns
        for name, risk in feature_risks.items():
            row[f"risk_{name}"] = risk

        rows.append(row)

    return rows


if __name__ == "__main__":
    rows = evaluate_gold_standard_repos()

    # Sort by maintenance_risk (ascending)
    rows_sorted = sorted(rows, key=lambda r: r["maintenance_risk"])

    print("\nGold standard repos by increasing MAINTENANCE risk:")
    for r in rows_sorted:
        print(
            f"{r['repo']:35s} "
            f"maint={r['maintenance_risk']:.3f} {r['maintenance_label']}, "
            f"license={r['license_risk']:.3f} {r['license_label']}"
        )

    # Write CSV for analysis
    try:
        import csv

        with open("gold_standard_scores.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print("\nWrote gold_standard_scores.csv")
    except Exception as e:
        print(f"Could not write CSV: {e}")
