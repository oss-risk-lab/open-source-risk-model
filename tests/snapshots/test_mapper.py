"""
Tests for pipeline_result_to_snapshot_record and helpers.

Covers: happy path, not_found (snapshot=None), null features, stars_count alias,
feature_coverage, feature_status extraction.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from open_source_risk_model.ingestion.models import RepositorySnapshot
from open_source_risk_model.snapshots.mapper import (
    FEATURE_KEYS,
    _compute_coverage,
    _extract_features,
    pipeline_result_to_snapshot_record,
)
from open_source_risk_model.snapshots.models import SCHEMA_VERSION


OBSERVED_AT = datetime(2026, 7, 13, 6, 14, 32, tzinfo=timezone.utc)
RUN_ID = "snap-20260713-060000"


def _make_snapshot(repo: str = "owner/repo") -> RepositorySnapshot:
    return RepositorySnapshot(
        repo_full_name=repo,
        pushed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        latest_release=datetime(2026, 6, 3, tzinfo=timezone.utc),
        stargazer_count=1000,
        is_archived=False,
        license_info="MIT",
        open_issues_count=10,
        fetched_at=OBSERVED_AT,
    )


def _make_features(**overrides: object) -> dict:
    base = {
        "days_since_last_push": 12.4,
        "days_since_last_release": 39.1,
        "stars_count": 1000,
        "archived": False,
        "open_issues_count": 10,
        "contributors_count": 5,
        "contributors_last_12mo": 3,
        "top_contributor_fraction_12mo": 0.6,
        "issues_per_contributor": 2.0,
        "fraction_issues_closed_12mo": 0.8,
        "fraction_open_issues_stale_180d": 0.3,
        "avg_time_to_first_maintainer_response_days": None,
        "median_time_to_close_days": None,
        "open_issue_age_p90_days": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractFeatures:
    def test_canonical_keys_present(self) -> None:
        result = _extract_features(_make_features())
        assert set(result.keys()) == set(FEATURE_KEYS)

    def test_extra_keys_excluded(self) -> None:
        features = _make_features()
        features["unexpected_key"] = 99
        result = _extract_features(features)
        assert "unexpected_key" not in result

    def test_stars_count_preferred_over_stargazers(self) -> None:
        features = {"stars_count": 500, "stargazers_count": 999}
        result = _extract_features(features)
        assert result["stars_count"] == 500

    def test_stargazers_count_used_when_stars_missing(self) -> None:
        features = {"stargazers_count": 999}
        result = _extract_features(features)
        assert result["stars_count"] == 999

    def test_missing_features_are_none(self) -> None:
        result = _extract_features({})
        for key in FEATURE_KEYS:
            assert result[key] is None, f"Expected {key!r} to be None"


class TestComputeCoverage:
    def test_all_non_null(self) -> None:
        features = {k: 1.0 for k in FEATURE_KEYS}
        assert _compute_coverage(features) == 1.0

    def test_all_null(self) -> None:
        features = {k: None for k in FEATURE_KEYS}
        assert _compute_coverage(features) == 0.0

    def test_partial_coverage(self) -> None:
        features = {k: None for k in FEATURE_KEYS}
        non_null_count = 4
        for key in list(FEATURE_KEYS)[:non_null_count]:
            features[key] = 1.0
        coverage = _compute_coverage(features)
        assert abs(coverage - non_null_count / len(FEATURE_KEYS)) < 1e-6

    def test_empty_dict_returns_zero(self) -> None:
        assert _compute_coverage({}) == 0.0


class TestPipelineResultToSnapshotRecord:
    def test_happy_path(self) -> None:
        snapshot = _make_snapshot()
        features = _make_features()
        record = pipeline_result_to_snapshot_record(
            repo_full_name="owner/repo",
            snapshot=snapshot,
            features=features,
            fetch_status="success",
            error_message=None,
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )

        assert record.schema_version == SCHEMA_VERSION
        assert record.run_id == RUN_ID
        assert record.repo_full_name == "owner/repo"
        assert record.fetch_status == "success"
        assert record.error_message is None
        assert record.universe_version == "v1"
        assert record.observed_at == OBSERVED_AT.isoformat()

    def test_raw_fields_from_snapshot(self) -> None:
        snapshot = _make_snapshot()
        record = pipeline_result_to_snapshot_record(
            repo_full_name="owner/repo",
            snapshot=snapshot,
            features=_make_features(),
            fetch_status="success",
            error_message=None,
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )

        assert record.raw["archived"] is False
        assert record.raw["license_spdx_id"] == "MIT"
        assert "2026-07-01" in record.raw["pushed_at"]
        assert "2026-06-03" in record.raw["latest_release_published_at"]
        # Fields not in RepositorySnapshot v1 are None
        assert record.raw["created_at"] is None
        assert record.raw["disabled"] is None
        assert record.raw["fork"] is None
        assert record.raw["default_branch"] is None
        assert record.raw["latest_release_tag"] is None

    def test_not_found_record(self) -> None:
        record = pipeline_result_to_snapshot_record(
            repo_full_name="dead/repo",
            snapshot=None,
            features={},
            fetch_status="not_found",
            error_message="404 Not Found",
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )

        assert record.repo_full_name == "dead/repo"
        assert record.fetch_status == "not_found"
        assert record.error_message == "404 Not Found"
        assert record.feature_coverage == 0.0
        for value in record.features.values():
            assert value is None
        for value in record.raw.values():
            assert value is None

    def test_all_feature_keys_present_on_failure(self) -> None:
        record = pipeline_result_to_snapshot_record(
            repo_full_name="missing/repo",
            snapshot=None,
            features={},
            fetch_status="error",
            error_message="timeout",
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )
        assert set(record.features.keys()) == set(FEATURE_KEYS)

    def test_feature_coverage_computed(self) -> None:
        features = _make_features()
        # 3 null features (avg, median, p90), 11 non-null
        record = pipeline_result_to_snapshot_record(
            repo_full_name="owner/repo",
            snapshot=_make_snapshot(),
            features=features,
            fetch_status="success",
            error_message=None,
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )
        expected = 11 / 14
        assert abs(record.feature_coverage - expected) < 1e-4

    def test_feature_status_extracted_from_meta(self) -> None:
        features = _make_features()
        features["__meta__"] = {"feature_status": {"contributors_count": "ok", "stars_count": "ok"}}
        record = pipeline_result_to_snapshot_record(
            repo_full_name="owner/repo",
            snapshot=_make_snapshot(),
            features=features,
            fetch_status="success",
            error_message=None,
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )
        assert record.feature_status == {"contributors_count": "ok", "stars_count": "ok"}

    def test_feature_status_empty_when_no_meta(self) -> None:
        record = pipeline_result_to_snapshot_record(
            repo_full_name="owner/repo",
            snapshot=_make_snapshot(),
            features=_make_features(),
            fetch_status="success",
            error_message=None,
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )
        assert record.feature_status == {}

    def test_null_latest_release(self) -> None:
        snapshot = _make_snapshot()
        snapshot = snapshot.model_copy(update={"latest_release": None})
        record = pipeline_result_to_snapshot_record(
            repo_full_name="owner/repo",
            snapshot=snapshot,
            features=_make_features(),
            fetch_status="success",
            error_message=None,
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )
        assert record.raw["latest_release_published_at"] is None

    def test_to_json_dict_is_serializable(self) -> None:
        import json

        record = pipeline_result_to_snapshot_record(
            repo_full_name="owner/repo",
            snapshot=_make_snapshot(),
            features=_make_features(),
            fetch_status="partial",
            error_message="contributors timeout",
            run_id=RUN_ID,
            universe_version="v1",
            observed_at=OBSERVED_AT,
        )
        # Should not raise
        serialized = json.dumps(record.to_json_dict())
        parsed = json.loads(serialized)
        assert parsed["fetch_status"] == "partial"
