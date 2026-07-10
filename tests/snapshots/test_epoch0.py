"""
Tests for scripts/import_epoch0_snapshots.py.

Covers: output file creation, record parsing, epoch0 flag in manifest,
fetch_status classification, date grouping, skip-on-existing behavior.
"""

import gzip
import json
import sys
from pathlib import Path

import pytest

# The script lives in scripts/ not a package, so we import via path manipulation
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import import_epoch0_snapshots as epoch0_script


FIXTURES = Path(__file__).parent.parent / "fixtures" / "raw_snapshots"


# ---------------------------------------------------------------------------
# classify_fetch_status unit tests
# ---------------------------------------------------------------------------


class TestClassifyFetchStatus:
    def test_all_ok_is_success(self) -> None:
        fs = {"contributors_count": "ok", "days_since_last_release": "ok"}
        assert epoch0_script.classify_fetch_status(fs) == "success"

    def test_empty_dict_is_success(self) -> None:
        assert epoch0_script.classify_fetch_status({}) == "success"

    def test_not_applicable_is_partial(self) -> None:
        fs = {"contributors_count": "ok", "fraction_issues_closed_12mo": "not_applicable"}
        assert epoch0_script.classify_fetch_status(fs) == "partial"

    def test_any_non_ok_is_partial(self) -> None:
        fs = {"a": "ok", "b": "missing", "c": "ok"}
        assert epoch0_script.classify_fetch_status(fs) == "partial"


# ---------------------------------------------------------------------------
# load_raw_snapshots
# ---------------------------------------------------------------------------


class TestLoadRawSnapshots:
    def test_loads_fixture_files(self) -> None:
        records = epoch0_script.load_raw_snapshots(FIXTURES)
        assert len(records) == 3

    def test_records_have_required_keys(self) -> None:
        records = epoch0_script.load_raw_snapshots(FIXTURES)
        for r in records:
            assert "full_name" in r
            assert "fetched_at" in r
            assert "features" in r

    def test_skips_invalid_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        # one valid file
        good = tmp_path / "owner__good.json"
        good.write_text(json.dumps({
            "full_name": "owner/good",
            "fetched_at": "2026-03-30T10:00:00+00:00",
            "features": {},
        }))
        records = epoch0_script.load_raw_snapshots(tmp_path)
        assert len(records) == 1
        assert records[0]["full_name"] == "owner/good"

    def test_skips_missing_fields(self, tmp_path: Path) -> None:
        incomplete = tmp_path / "no_full_name.json"
        incomplete.write_text(json.dumps({"fetched_at": "2026-03-30T10:00:00+00:00", "features": {}}))
        records = epoch0_script.load_raw_snapshots(tmp_path)
        assert records == []


# ---------------------------------------------------------------------------
# group_by_date
# ---------------------------------------------------------------------------


class TestGroupByDate:
    def test_groups_by_date(self) -> None:
        records = [
            {"fetched_at": "2026-03-30T10:00:00+00:00", "x": 1},
            {"fetched_at": "2026-03-30T11:00:00+00:00", "x": 2},
            {"fetched_at": "2026-04-07T09:00:00+00:00", "x": 3},
        ]
        grouped = epoch0_script.group_by_date(records)
        assert set(grouped.keys()) == {"2026-03-30", "2026-04-07"}
        assert len(grouped["2026-03-30"]) == 2
        assert len(grouped["2026-04-07"]) == 1


# ---------------------------------------------------------------------------
# Full integration: run main() with fixture directory
# ---------------------------------------------------------------------------


def _run_main(argv: list[str]) -> None:
    """Invoke epoch0_script.main() with the given argv."""
    epoch0_script.main(argv)


class TestEpoch0Integration:
    def test_output_files_created(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        snap_files = list(tmp_path.glob("snapshots/**/*.jsonl.gz"))
        manifest_files = list(tmp_path.glob("manifests/*.json"))
        # Two dates in fixtures: 2026-03-30 and 2026-04-07
        assert len(snap_files) == 2
        assert len(manifest_files) == 2

    def test_snapshot_records_parseable(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        snap_files = sorted(tmp_path.glob("snapshots/**/*.jsonl.gz"))
        all_records = []
        for f in snap_files:
            with gzip.open(f, "rt") as fh:
                all_records.extend(json.loads(line) for line in fh)
        assert len(all_records) == 3

    def test_epoch0_flag_in_manifests(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        manifest_files = list(tmp_path.glob("manifests/*.json"))
        for f in manifest_files:
            manifest = json.loads(f.read_text())
            assert manifest.get("epoch0") is True, f"Missing epoch0=true in {f.name}"

    def test_run_id_format(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        manifest_files = list(tmp_path.glob("manifests/*.json"))
        for f in manifest_files:
            manifest = json.loads(f.read_text())
            assert manifest["run_id"].startswith("epoch0-"), manifest["run_id"]

    def test_fetch_status_success(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        snap_files = list(tmp_path.glob("snapshots/**/*.jsonl.gz"))
        records = {}
        for f in snap_files:
            with gzip.open(f, "rt") as fh:
                for line in fh:
                    r = json.loads(line)
                    records[r["repo_full_name"]] = r

        assert records["owner/success-repo"]["fetch_status"] == "success"

    def test_fetch_status_partial(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        snap_files = list(tmp_path.glob("snapshots/**/*.jsonl.gz"))
        records = {}
        for f in snap_files:
            with gzip.open(f, "rt") as fh:
                for line in fh:
                    r = json.loads(line)
                    records[r["repo_full_name"]] = r

        assert records["owner/partial-repo"]["fetch_status"] == "partial"

    def test_date_grouping_correct(self, tmp_path: Path) -> None:
        """2026-03-30 gets 2 records, 2026-04-07 gets 1 record."""
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        manifest_files = {f.stem: json.loads(f.read_text()) for f in tmp_path.glob("manifests/*.json")}
        assert manifest_files["2026-03-30"]["repos_total"] == 2
        assert manifest_files["2026-04-07"]["repos_total"] == 1

    def test_manifest_counters(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        manifest = json.loads((tmp_path / "manifests" / "2026-03-30.json").read_text())
        assert manifest["repos_success"] == 1
        assert manifest["repos_partial"] == 1
        assert manifest["repos_not_found"] == 0
        assert manifest["repos_error"] == 0

    def test_required_schema_fields_in_records(self, tmp_path: Path) -> None:
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        snap_files = list(tmp_path.glob("snapshots/**/*.jsonl.gz"))
        required = [
            "schema_version", "run_id", "observed_at", "repo_full_name",
            "universe_version", "fetch_status", "features", "raw",
            "feature_coverage", "feature_status",
        ]
        for f in snap_files:
            with gzip.open(f, "rt") as fh:
                for line in fh:
                    r = json.loads(line)
                    for field in required:
                        assert field in r, f"Missing field {field!r} in record {r.get('repo_full_name')}"

    def test_skips_existing_output(self, tmp_path: Path) -> None:
        """Second run should skip files that already exist (no FileExistsError abort)."""
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        # Second run on same output dir should log warnings and not raise
        _run_main(["--raw-snapshots-dir", str(FIXTURES), "--output-dir", str(tmp_path)])
        # Files should still be intact (not corrupted or missing)
        snap_files = list(tmp_path.glob("snapshots/**/*.jsonl.gz"))
        assert len(snap_files) == 2
