"""
Tests for SnapshotWriter.

Covers: round-trip, overwrite refusal, force overwrite, null handling, manifest.
"""

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from open_source_risk_model.snapshots.models import RunManifest, SnapshotRecord
from open_source_risk_model.snapshots.writer import SnapshotWriter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RUN_DATE = date(2026, 7, 13)
RUN_ID = "snap-20260713-060000"


def _make_record(repo: str = "owner/repo", status: str = "success") -> SnapshotRecord:
    return SnapshotRecord(
        schema_version="1.0",
        run_id=RUN_ID,
        observed_at="2026-07-13T06:14:32.000000+00:00",
        repo_full_name=repo,
        universe_version="v1",
        fetch_status=status,
        error_message=None,
        features={
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
        },
        raw={
            "pushed_at": "2026-07-01T00:00:00+00:00",
            "created_at": None,
            "archived": False,
            "disabled": None,
            "fork": None,
            "license_spdx_id": "MIT",
            "default_branch": None,
            "latest_release_tag": None,
            "latest_release_published_at": None,
        },
        feature_coverage=0.785714,
        feature_status={},
    )


def _make_manifest(total: int = 1, success: int = 1) -> RunManifest:
    return RunManifest(
        run_id=RUN_ID,
        started_at="2026-07-13T06:00:00.000000+00:00",
        completed_at="2026-07-13T07:00:00.000000+00:00",
        universe_version="v1",
        universe_sha256="abc123",
        repos_total=total,
        repos_success=success,
        repos_partial=0,
        repos_not_found=0,
        repos_error=total - success,
        error_sample=[],
        api_calls_estimate=total * 4,
        collector_git_sha="d77d475",
        schema_version="1.0",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSnapshotWriterRoundTrip:
    def test_single_record_round_trips(self, tmp_path: Path) -> None:
        record = _make_record()
        manifest = _make_manifest()

        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(record)
        writer.close(manifest)

        snap_path = writer.snapshot_path()
        assert snap_path.exists()

        with gzip.open(snap_path, "rt", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["repo_full_name"] == "owner/repo"
        assert parsed["fetch_status"] == "success"
        assert parsed["schema_version"] == "1.0"

    def test_multiple_records_round_trip(self, tmp_path: Path) -> None:
        repos = ["a/b", "c/d", "e/f"]
        records = [_make_record(repo=r) for r in repos]
        manifest = _make_manifest(total=3, success=3)

        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        for rec in records:
            writer.write_record(rec)
        writer.close(manifest)

        with gzip.open(writer.snapshot_path(), "rt", encoding="utf-8") as f:
            parsed = [json.loads(line) for line in f]

        assert [p["repo_full_name"] for p in parsed] == repos

    def test_manifest_written_correctly(self, tmp_path: Path) -> None:
        manifest = _make_manifest(total=5, success=4)
        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(_make_record())
        writer.close(manifest)

        manifest_data = json.loads(writer.manifest_path().read_text())
        assert manifest_data["repos_total"] == 5
        assert manifest_data["repos_success"] == 4
        assert manifest_data["repos_error"] == 1
        assert manifest_data["run_id"] == RUN_ID
        assert "epoch0" not in manifest_data

    def test_epoch0_flag_in_manifest(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        manifest.epoch0 = True
        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(_make_record())
        writer.close(manifest)

        data = json.loads(writer.manifest_path().read_text())
        assert data["epoch0"] is True


class TestSnapshotWriterOverwriteGuard:
    def test_refuses_overwrite_without_force(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(_make_record())
        writer.close(manifest)

        with pytest.raises(FileExistsError, match=str(RUN_DATE)):
            writer2 = SnapshotWriter(tmp_path, RUN_DATE)
            writer2.open()

    def test_force_overwrite_replaces_file(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(_make_record(repo="first/repo"))
        writer.close(manifest)

        writer2 = SnapshotWriter(tmp_path, RUN_DATE, force=True)
        writer2.open()
        writer2.write_record(_make_record(repo="second/repo"))
        writer2.close(manifest)

        with gzip.open(writer2.snapshot_path(), "rt") as f:
            lines = f.readlines()

        assert len(lines) == 1
        assert json.loads(lines[0])["repo_full_name"] == "second/repo"

    def test_force_write_is_atomic(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(_make_record(repo="original/repo"))
        writer.close(manifest)

        original_mtime = writer.snapshot_path().stat().st_mtime

        writer2 = SnapshotWriter(tmp_path, RUN_DATE, force=True)
        writer2.open()
        writer2.write_record(_make_record(repo="new/repo"))
        writer2.close(manifest)

        # No .tmp file left behind
        tmp_file = writer2.snapshot_path().parent / (writer2.snapshot_path().name + ".tmp")
        assert not tmp_file.exists()


class TestSnapshotWriterNullHandling:
    def test_all_null_features_round_trip(self, tmp_path: Path) -> None:
        record = _make_record()
        record.features = {
            "days_since_last_push": None,
            "days_since_last_release": None,
            "stars_count": None,
            "archived": None,
            "open_issues_count": None,
            "contributors_count": None,
            "contributors_last_12mo": None,
            "top_contributor_fraction_12mo": None,
            "issues_per_contributor": None,
            "fraction_issues_closed_12mo": None,
            "fraction_open_issues_stale_180d": None,
            "avg_time_to_first_maintainer_response_days": None,
            "median_time_to_close_days": None,
            "open_issue_age_p90_days": None,
        }
        record.feature_coverage = 0.0
        record.fetch_status = "not_found"
        record.error_message = "404 Not Found"

        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(record)
        writer.close(_make_manifest())

        with gzip.open(writer.snapshot_path(), "rt") as f:
            parsed = json.loads(f.readline())

        for key, value in parsed["features"].items():
            assert value is None, f"Feature {key!r} should be None"
        assert parsed["fetch_status"] == "not_found"
        assert parsed["error_message"] == "404 Not Found"

    def test_null_raw_fields_serialized(self, tmp_path: Path) -> None:
        record = _make_record(status="not_found")
        record.raw = {k: None for k in record.raw}

        writer = SnapshotWriter(tmp_path, RUN_DATE)
        writer.open()
        writer.write_record(record)
        writer.close(_make_manifest())

        with gzip.open(writer.snapshot_path(), "rt") as f:
            parsed = json.loads(f.readline())

        for key, value in parsed["raw"].items():
            assert value is None, f"Raw field {key!r} should be None"


class TestSnapshotWriterContextManager:
    def test_context_manager_calls_open(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        with SnapshotWriter(tmp_path, RUN_DATE) as writer:
            writer.write_record(_make_record())
            writer.close(manifest)

        assert writer.snapshot_path().exists()

    def test_exception_leaves_target_intact(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        writer_first = SnapshotWriter(tmp_path, RUN_DATE)
        writer_first.open()
        writer_first.write_record(_make_record(repo="safe/repo"))
        writer_first.close(manifest)

        original_content = writer_first.snapshot_path().read_bytes()

        try:
            with SnapshotWriter(tmp_path, RUN_DATE, force=True) as writer:
                writer.write_record(_make_record(repo="bad/repo"))
                raise RuntimeError("simulated crash")
        except RuntimeError:
            pass

        # Target must still contain the original content
        assert writer_first.snapshot_path().read_bytes() == original_content


class TestSnapshotRecordValidation:
    def test_invalid_fetch_status_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid fetch_status"):
            _make_record(status="unknown")

    def test_valid_statuses_accepted(self) -> None:
        for status in ("success", "partial", "not_found", "error"):
            record = _make_record(status=status)
            assert record.fetch_status == status
