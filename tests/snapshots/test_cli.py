"""
Tests for the snapshot CLI.

Covers: universe loading, fetch_status classification, mixed success/404/error
universe, manifest counters, exit codes, progress logging.
"""

import gzip
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from open_source_risk_model.ingestion.models import RepositorySnapshot


# ---------------------------------------------------------------------------
# Import the CLI module under a clean alias so we can patch internals
# ---------------------------------------------------------------------------
import open_source_risk_model.cli.snapshot as snapshot_cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OBSERVED_AT = datetime(2026, 7, 13, 6, 0, 0, tzinfo=timezone.utc)


def _make_snapshot(repo: str) -> RepositorySnapshot:
    return RepositorySnapshot(
        repo_full_name=repo,
        pushed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        latest_release=None,
        stargazer_count=100,
        is_archived=False,
        license_info="MIT",
        open_issues_count=5,
        fetched_at=OBSERVED_AT,
    )


def _full_features() -> dict:
    return {
        "days_since_last_push": 12.0,
        "days_since_last_release": 30.0,
        "stars_count": 100,
        "archived": False,
        "open_issues_count": 5,
        "contributors_count": 3,
        "contributors_last_12mo": 2,
        "top_contributor_fraction_12mo": 0.5,
        "issues_per_contributor": 1.5,
        "fraction_issues_closed_12mo": 0.7,
        "fraction_open_issues_stale_180d": 0.2,
        "avg_time_to_first_maintainer_response_days": None,
        "median_time_to_close_days": None,
        "open_issue_age_p90_days": None,
    }


def _make_pipeline_mock(
    snapshots: list[RepositorySnapshot],
    single_raises: dict[str, Exception] | None = None,
    features: dict | None = None,
    coverage: float = 0.79,
) -> MagicMock:
    """Build a mock IngestionPipeline with configurable per-repo behavior."""
    pipeline = MagicMock()

    pipeline.snapshot_fetcher.fetch_snapshots.return_value = snapshots
    pipeline.snapshot_fetcher.current_batch_size = 20

    if single_raises:
        def fetch_single_side_effect(repo):
            if repo in single_raises:
                raise single_raises[repo]
            snap = next((s for s in snapshots if s.repo_full_name == repo), None)
            if snap:
                return snap
            raise Exception(f"Repository not found: {repo}")
        pipeline.snapshot_fetcher.fetch_single.side_effect = fetch_single_side_effect
    else:
        pipeline.snapshot_fetcher.fetch_single.side_effect = lambda repo: (
            next((s for s in snapshots if s.repo_full_name == repo), None)
            or (_ for _ in ()).throw(Exception(f"Repository not found: {repo}"))
        )

    pipeline.contributors_fetcher.fetch_contributors.return_value = []
    pipeline.issues_fetcher.fetch_issues.return_value = []
    pipeline.feature_engineer.compute_features.return_value = features or _full_features()
    pipeline.feature_engineer.check_feature_coverage.return_value = (coverage, [])
    pipeline.rate_limiter.get_remaining.return_value = 4000

    return pipeline


def _write_universe(tmp_path: Path, repos: list[str], extra_lines: list[str] | None = None) -> Path:
    lines = ["# Universe v1", ""] + repos + (extra_lines or [])
    universe_file = tmp_path / "universe_v1.txt"
    universe_file.write_text("\n".join(lines))
    return universe_file


def _run_main(argv: list[str]) -> int:
    """Run snapshot_cli.main() with a fake GITHUB_TOKEN already in env."""
    with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token-x"}):
        with patch.object(sys, "argv", ["snapshot"] + argv):
            try:
                snapshot_cli.main()
            except SystemExit as exc:
                return int(exc.code)
    return 0


# ---------------------------------------------------------------------------
# classify_fetch_status tests
# ---------------------------------------------------------------------------


class TestClassifyFetchStatus:
    def test_not_found_from_graphql_message(self) -> None:
        assert snapshot_cli.classify_fetch_status("Repository not found: owner/repo", False, 0.0) == "not_found"

    def test_not_found_from_graphql_resolve_error(self) -> None:
        # GraphQL form seen in production: "GraphQL errors: Could not resolve to a Repository with the name 'X'."
        msg = "GraphQL query failed after 3 attempts: GraphQL errors: Could not resolve to a Repository with the name 'owner/repo'."
        assert snapshot_cli.classify_fetch_status(msg, False, 0.0) == "not_found"

    def test_not_found_from_404_string(self) -> None:
        assert snapshot_cli.classify_fetch_status("HTTP 404 Not Found", False, 0.0) == "not_found"

    def test_not_found_from_451(self) -> None:
        assert snapshot_cli.classify_fetch_status("HTTP 451 Unavailable For Legal Reasons", False, 0.0) == "not_found"

    def test_403_is_error_not_not_found(self) -> None:
        result = snapshot_cli.classify_fetch_status("HTTP 403 Forbidden rate limit", False, 0.0)
        assert result == "error", "403 must not be classified as not_found (false death observation)"

    def test_success_high_coverage(self) -> None:
        assert snapshot_cli.classify_fetch_status(None, True, 0.80) == "success"

    def test_success_at_threshold(self) -> None:
        assert snapshot_cli.classify_fetch_status(None, True, 0.60) == "success"

    def test_partial_below_threshold(self) -> None:
        assert snapshot_cli.classify_fetch_status(None, True, 0.50) == "partial"

    def test_generic_exception_is_error(self) -> None:
        assert snapshot_cli.classify_fetch_status("Connection reset by peer", False, 0.0) == "error"

    def test_no_error_no_success_is_error(self) -> None:
        assert snapshot_cli.classify_fetch_status(None, False, 0.0) == "error"


# ---------------------------------------------------------------------------
# load_universe tests
# ---------------------------------------------------------------------------


class TestLoadUniverse:
    def test_loads_repos(self, tmp_path: Path) -> None:
        f = _write_universe(tmp_path, ["owner/a", "owner/b"])
        repos = snapshot_cli.load_universe(f)
        assert repos == ["owner/a", "owner/b"]

    def test_strips_comments_and_blanks(self, tmp_path: Path) -> None:
        f = tmp_path / "u.txt"
        f.write_text("# comment\n\nowner/repo\n  # inline\nfoo/bar\n")
        repos = snapshot_cli.load_universe(f)
        assert repos == ["owner/repo", "foo/bar"]

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("# just comments\n\n")
        assert snapshot_cli.load_universe(f) == []


# ---------------------------------------------------------------------------
# Full CLI integration tests (with mocked pipeline)
# ---------------------------------------------------------------------------


class TestSnapshotCLIMixedUniverse:
    """Verify correct record counts, manifest, and exit codes for mixed runs."""

    REPOS = ["owner/success1", "owner/success2", "owner/deleted", "owner/error1"]

    def _setup_pipeline(self) -> MagicMock:
        # success1 and success2 come back from batch
        # deleted and error1 are missing from batch
        snapshots = [_make_snapshot("owner/success1"), _make_snapshot("owner/success2")]
        single_raises = {
            "owner/deleted": Exception("Repository not found: owner/deleted"),
            "owner/error1": Exception("HTTP 403 Forbidden"),
        }
        return _make_pipeline_mock(snapshots, single_raises=single_raises)

    def test_record_count_matches_universe(self, tmp_path: Path) -> None:
        pipeline = self._setup_pipeline()
        universe = _write_universe(tmp_path, self.REPOS)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            _run_main(["--universe", str(universe), "--output-dir", str(output), "--force"])

        snap_path = output / "snapshots" / "2026" / f"deep-signal-snapshot-{date.today().isoformat()}.jsonl.gz"
        if not snap_path.exists():
            # Find whatever date was written
            import glob
            files = list(output.glob("snapshots/**/*.jsonl.gz"))
            assert files, "No snapshot file was written"
            snap_path = files[0]

        with gzip.open(snap_path, "rt") as f:
            records = [json.loads(line) for line in f]

        assert len(records) == len(self.REPOS)

    def test_fetch_status_values(self, tmp_path: Path) -> None:
        pipeline = self._setup_pipeline()
        universe = _write_universe(tmp_path, self.REPOS)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            _run_main(["--universe", str(universe), "--output-dir", str(output), "--force"])

        files = list(output.glob("snapshots/**/*.jsonl.gz"))
        with gzip.open(files[0], "rt") as f:
            records = {json.loads(l)["repo_full_name"]: json.loads(l) for l in f}

        # Reparse correctly
        with gzip.open(files[0], "rt") as f:
            records = {}
            for line in f:
                r = json.loads(line)
                records[r["repo_full_name"]] = r

        assert records["owner/success1"]["fetch_status"] == "success"
        assert records["owner/success2"]["fetch_status"] == "success"
        assert records["owner/deleted"]["fetch_status"] == "not_found"
        assert records["owner/error1"]["fetch_status"] == "error"

    def test_manifest_counters(self, tmp_path: Path) -> None:
        pipeline = self._setup_pipeline()
        universe = _write_universe(tmp_path, self.REPOS)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            _run_main(["--universe", str(universe), "--output-dir", str(output), "--force"])

        files = list(output.glob("manifests/*.json"))
        assert files
        manifest = json.loads(files[0].read_text())
        assert manifest["repos_total"] == 4
        assert manifest["repos_success"] == 2
        assert manifest["repos_not_found"] == 1
        assert manifest["repos_error"] == 1
        assert manifest["repos_partial"] == 0

    def test_exit_code_0_when_rate_above_threshold(self, tmp_path: Path) -> None:
        # 2 success out of 4 = 50% -- below threshold... let's use a universe where 90%+ pass
        repos = [f"owner/repo{i}" for i in range(10)]
        snapshots = [_make_snapshot(r) for r in repos[:9]]  # 9 of 10 succeed
        single_raises = {"owner/repo9": Exception("Repository not found: owner/repo9")}
        pipeline = _make_pipeline_mock(snapshots, single_raises=single_raises)
        universe = _write_universe(tmp_path, repos)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            exit_code = _run_main(["--universe", str(universe), "--output-dir", str(output)])

        assert exit_code == 0, "90% success rate should give exit code 0"

    def test_exit_code_1_when_rate_below_threshold(self, tmp_path: Path) -> None:
        # Only 2 of 4 succeed = 50%, below 90% threshold
        pipeline = self._setup_pipeline()
        universe = _write_universe(tmp_path, self.REPOS)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            exit_code = _run_main(["--universe", str(universe), "--output-dir", str(output)])

        assert exit_code == 1, "50% success rate should give exit code 1"

    def test_max_repos_limits_universe(self, tmp_path: Path) -> None:
        repos = [f"owner/repo{i}" for i in range(20)]
        snapshots = [_make_snapshot(r) for r in repos]
        pipeline = _make_pipeline_mock(snapshots)
        universe = _write_universe(tmp_path, repos)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            _run_main(["--universe", str(universe), "--output-dir", str(output), "--max-repos", "5"])

        files = list(output.glob("manifests/*.json"))
        manifest = json.loads(files[0].read_text())
        assert manifest["repos_total"] == 5

    def test_force_flag_overwrites_existing(self, tmp_path: Path) -> None:
        repos = ["owner/repo1"]
        snapshots = [_make_snapshot("owner/repo1")]
        pipeline = _make_pipeline_mock(snapshots)
        universe = _write_universe(tmp_path, repos)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            _run_main(["--universe", str(universe), "--output-dir", str(output)])
            # Second run without --force should fail (exit 1 due to FileExistsError)
            exit_code = _run_main(["--universe", str(universe), "--output-dir", str(output)])
        assert exit_code == 1

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            exit_code = _run_main(
                ["--universe", str(universe), "--output-dir", str(output), "--force"]
            )
        assert exit_code == 0


class TestProgressLogging:
    def test_progress_logged_every_25_repos(self, tmp_path: Path, caplog) -> None:
        import logging

        repos = [f"owner/repo{i}" for i in range(50)]
        snapshots = [_make_snapshot(r) for r in repos]
        pipeline = _make_pipeline_mock(snapshots)
        universe = _write_universe(tmp_path, repos)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            with caplog.at_level(logging.INFO, logger="open_source_risk_model.cli.snapshot"):
                _run_main(["--universe", str(universe), "--output-dir", str(output)])

        progress_lines = [r.message for r in caplog.records if "Progress" in r.message]
        # Expect progress at idx=25 and idx=50
        assert len(progress_lines) >= 2
        assert any("25/50" in line for line in progress_lines)
        assert any("50/50" in line for line in progress_lines)


class TestManifestFields:
    def test_manifest_has_required_fields(self, tmp_path: Path) -> None:
        repos = ["owner/repo1"]
        snapshots = [_make_snapshot("owner/repo1")]
        pipeline = _make_pipeline_mock(snapshots)
        universe = _write_universe(tmp_path, repos)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            _run_main(["--universe", str(universe), "--output-dir", str(output)])

        manifest = json.loads(list(output.glob("manifests/*.json"))[0].read_text())
        required = [
            "schema_version", "run_id", "started_at", "completed_at",
            "universe_version", "universe_sha256", "repos_total",
            "repos_success", "repos_partial", "repos_not_found", "repos_error",
            "error_sample", "api_calls_estimate", "collector_git_sha",
        ]
        for field in required:
            assert field in manifest, f"Missing manifest field: {field!r}"

    def test_run_id_format(self, tmp_path: Path) -> None:
        repos = ["owner/repo1"]
        snapshots = [_make_snapshot("owner/repo1")]
        pipeline = _make_pipeline_mock(snapshots)
        universe = _write_universe(tmp_path, repos)
        output = tmp_path / "obs"

        with patch("open_source_risk_model.cli.snapshot.IngestionPipeline", return_value=pipeline):
            _run_main(["--universe", str(universe), "--output-dir", str(output)])

        manifest = json.loads(list(output.glob("manifests/*.json"))[0].read_text())
        assert manifest["run_id"].startswith("snap-")
