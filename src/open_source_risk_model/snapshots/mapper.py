"""
Maps pipeline output to SnapshotRecord.

The caller (CLI) is responsible for classifying fetch_status before calling
pipeline_result_to_snapshot_record. This module does not inspect HTTP codes
or error strings; status classification lives entirely in cli/snapshot.py.
"""

from datetime import datetime
from typing import Any, Optional

from ..ingestion.models import RepositorySnapshot
from .models import SCHEMA_VERSION, SnapshotRecord


# Canonical feature keys for schema v1.0, in declaration order.
# Missing values are stored as None, never omitted.
FEATURE_KEYS: tuple[str, ...] = (
    "days_since_last_push",
    "days_since_last_release",
    "stars_count",
    "archived",
    "open_issues_count",
    "contributors_count",
    "contributors_last_12mo",
    "top_contributor_fraction_12mo",
    "issues_per_contributor",
    "fraction_issues_closed_12mo",
    "fraction_open_issues_stale_180d",
    "avg_time_to_first_maintainer_response_days",
    "median_time_to_close_days",
    "open_issue_age_p90_days",
)


def _extract_features(pipeline_features: dict[str, Any]) -> dict[str, Any]:
    """Return a dict with exactly the FEATURE_KEYS, missing values as None."""
    result: dict[str, Any] = {}
    for key in FEATURE_KEYS:
        if key == "stars_count":
            # The pipeline may emit stargazers_count or stars_count; prefer stars_count.
            value = pipeline_features.get("stars_count")
            if value is None:
                value = pipeline_features.get("stargazers_count")
        else:
            value = pipeline_features.get(key)
        result[key] = value
    return result


def _compute_coverage(features: dict[str, Any]) -> float:
    """Return the fraction of feature values that are not None."""
    if not features:
        return 0.0
    non_null = sum(1 for v in features.values() if v is not None)
    return round(non_null / len(features), 6)


def _build_raw(snapshot: Optional[RepositorySnapshot]) -> dict[str, Any]:
    """Build the raw metadata dict from a RepositorySnapshot.

    Fields not present in RepositorySnapshot v1 (created_at, disabled, fork,
    default_branch, latest_release_tag) are stored as None rather than
    requiring new API calls.
    """
    if snapshot is None:
        return {
            "pushed_at": None,
            "created_at": None,
            "archived": None,
            "disabled": None,
            "fork": None,
            "license_spdx_id": None,
            "default_branch": None,
            "latest_release_tag": None,
            "latest_release_published_at": None,
        }
    return {
        "pushed_at": snapshot.pushed_at.isoformat() if snapshot.pushed_at else None,
        "created_at": None,
        "archived": snapshot.is_archived,
        "disabled": None,
        "fork": None,
        "license_spdx_id": snapshot.license_info,
        "default_branch": None,
        "latest_release_tag": None,
        "latest_release_published_at": (
            snapshot.latest_release.isoformat() if snapshot.latest_release else None
        ),
    }


def pipeline_result_to_snapshot_record(
    repo_full_name: str,
    snapshot: Optional[RepositorySnapshot],
    features: dict[str, Any],
    fetch_status: str,
    error_message: Optional[str],
    run_id: str,
    universe_version: str,
    observed_at: datetime,
) -> SnapshotRecord:
    """Convert pipeline output to an immutable SnapshotRecord.

    Args:
        repo_full_name: Canonical owner/name from the universe file.
        snapshot: RepositorySnapshot from the GraphQL phase, or None on failure.
        features: Feature dict from feature_engineer, or empty dict on failure.
        fetch_status: Pre-classified status from cli.snapshot.classify_fetch_status().
        error_message: Error string on failure, None on success.
        run_id: Run identifier (e.g. "snap-20260713-060000").
        universe_version: Universe version label (e.g. "v1").
        observed_at: Per-repo fetch completion time (UTC).
    """
    canonical_features = _extract_features(features) if features else {k: None for k in FEATURE_KEYS}
    feature_status: dict[str, str] = {}
    if features:
        meta = features.get("__meta__")
        if isinstance(meta, dict):
            raw_status = meta.get("feature_status")
            if isinstance(raw_status, dict):
                feature_status = raw_status

    return SnapshotRecord(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        observed_at=observed_at.isoformat(),
        repo_full_name=repo_full_name,
        universe_version=universe_version,
        fetch_status=fetch_status,
        error_message=error_message,
        features=canonical_features,
        raw=_build_raw(snapshot),
        feature_coverage=_compute_coverage(canonical_features),
        feature_status=feature_status,
    )
