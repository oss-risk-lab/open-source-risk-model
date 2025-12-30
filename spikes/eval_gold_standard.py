# spikes/eval_gold_standard.py

import argparse
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone

from open_source_risk_model.data_ingestion.gold_standard_repos import GOLD_STANDARD_REPOS
from open_source_risk_model.data_ingestion.github_features import (
    _github_session,
    fetch_repo_features,
)
from pathlib import Path
from open_source_risk_model.issues.metrics import compute_issue_metrics
import open_source_risk_model.data_ingestion.github_features as ghf
print("DEBUG github_features.py loaded from:", ghf.__file__)
from open_source_risk_model.score import (
    compute_maintenance_risk,
    classify_maintenance_risk,
    classify_license_risk,
)

from open_source_risk_model.storage.snapshots import JsonSnapshotStore, RepoSnapshot


def evaluate_gold_standard_repos(refresh: bool = False) -> List[Dict[str, Any]]:
    session = _github_session()
    store = JsonSnapshotStore("data/raw_snapshots")
    max_age = timedelta(hours=24)

    rows: List[Dict[str, Any]] = []

    for full_name in GOLD_STANDARD_REPOS:
        cached = store.get_latest(full_name)

        if (not refresh) and cached is not None and store.is_fresh(cached, max_age):
            print(f"Using cache {full_name} (fetched_at={cached.fetched_at.isoformat()})")
            raw = cached.features
        else:
            print(f"Fetching {full_name} from GitHub...")
            repo_features = fetch_repo_features(full_name, session=session)
            raw = repo_features.as_raw_dict()

            snap = RepoSnapshot(
                full_name=full_name,
                fetched_at=datetime.now(timezone.utc),
                features=raw,
            )
            store.save(snap)
            print(f"Saved snapshot {full_name} -> data/raw_snapshots/")

        # --- NEW: merge deterministic issue metrics (if issues data exists) ---
        issue_dir = Path("data/issues") / full_name.replace("/", "__")
        if issue_dir.exists():
            raw.update(compute_issue_metrics(str(issue_dir)))

        EXPECTED_RAW_FEATURES = [
            "archived",
            "contributors_count",
            "contributors_last_12mo",
            "days_since_last_push",
            "days_since_last_release",
            "fraction_issues_closed_12mo",
            "fraction_open_issues_stale_180d",
            "license_spdx_id",
            "open_issues_count",
            "stargazers_count",
            "top_contributor_fraction_12mo",
        ]

        missing_raw = [
            k for k in EXPECTED_RAW_FEATURES
            if k not in raw or raw.get(k) is None
        ]

        if missing_raw:
            print(f"NOTE {full_name}: missing RAW features: {missing_raw}")

        # --- raw data coverage summary ---
        covered_raw = len(EXPECTED_RAW_FEATURES) - len(missing_raw)
        total_raw = len(EXPECTED_RAW_FEATURES)
        coverage_frac = covered_raw / total_raw if total_raw > 0 else 0.0

        print(f"  data_coverage    = {covered_raw}/{total_raw} raw features ({coverage_frac:.0%})")

        # DEBUG: inspect raw license value from GitHub
        if full_name in ("numpy/numpy", "pytorch/pytorch", "matplotlib/matplotlib", "torvalds/linux"):
            print(f"LICENSE RAW {full_name}: {repr(raw.get('license_spdx_id'))}")

        # --- maintenance-only composite ---
        maint = compute_maintenance_risk(raw)
        maintenance_risk = maint["overall_risk"]
        feature_risks = maint["feature_risks"]
        maintenance_label = classify_maintenance_risk(maintenance_risk)

        maintenance_risk_unc = maint.get("risk_with_uncertainty", maintenance_risk)
        maintenance_cov = maint.get("weighted_coverage", None)
        maintenance_conf = maint.get("confidence")
        missing_weight = maint.get("missing_weight_by_feature", {}) or {}


        # license_risk just comes from the feature_risks dict
        license_risk = feature_risks.get("license_risk", 0.0)
        license_label = classify_license_risk(license_risk)

        print("\nRISK BREAKDOWN:")
        print(f"  maintenance_risk  = {maintenance_risk:.3f} ({maintenance_label})")
        if maintenance_cov is not None:
            print(
                f"  maint_risk_unc    = {maintenance_risk_unc:.3f} "
                f"({maintenance_conf} confidence, coverage={maintenance_cov:.0%})"
            )
        else:
            print(f"  maint_risk_unc    = {maintenance_risk_unc:.3f}")
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

            if missing_weight:
                top_missing = sorted(missing_weight.items(), key=lambda kv: kv[1], reverse=True)[:5]
                print("  missing_weight_by_feature (top):")
                for k, w in top_missing:
                    print(f"    {k:22s} -> {w:.3f}")

            print()


        # Build row for CSV / later analysis
        row: Dict[str, Any] = {
            "repo": full_name,
            "maintenance_risk": maintenance_risk,
            "maintenance_risk_unc": maintenance_risk_unc,
            "maintenance_coverage": maintenance_cov,
            "maintenance_confidence": maintenance_conf,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Force refresh GitHub fetch even if cache is fresh")
    args = parser.parse_args()

    rows = evaluate_gold_standard_repos(refresh=args.refresh)


    # Sort by maintenance_risk (ascending)
    rows_sorted = sorted(rows, key=lambda r: r["maintenance_risk"])

    print("\nGold standard repos by increasing MAINTENANCE risk:")
    for r in rows_sorted:
        print(
            f"{r['repo']:35s} "
            f"maint={r['maintenance_risk']:.3f} {r['maintenance_label']}, "
            f"unc={r.get('maintenance_risk_unc', r['maintenance_risk']):.3f} "
            f"(cov={ (r.get('maintenance_coverage') or 0):.0%}), "
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
