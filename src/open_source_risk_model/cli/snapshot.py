"""
Snapshot CLI: weekly batch collector for temporal repository observations.

Usage:
    python -m open_source_risk_model.cli.snapshot \\
        --universe data/universe/universe_v1.txt \\
        --output-dir /path/to/observatory \\
        [--max-repos 10] [--force] [--run-date 2026-07-13]

Execution is two-phase to use GraphQL batching:
  Phase 1: fetch_snapshots() issues alias-batched GraphQL queries (~70 calls
           for 1,400 repos instead of ~1,400 serial calls).
  Phase 2: per-repo REST calls for contributors and issues, then feature
           engineering. Failures are caught per-repo and never abort the run.

Exit codes:
  0 -- (success + partial) / total >= 0.90
  1 -- success rate below 0.90, or critical startup error
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from open_source_risk_model.ingestion.config import IngestionConfig
from open_source_risk_model.ingestion.ingestion_pipeline import IngestionPipeline
from open_source_risk_model.snapshots.mapper import pipeline_result_to_snapshot_record
from open_source_risk_model.snapshots.models import RunManifest, SCHEMA_VERSION
from open_source_risk_model.snapshots.writer import SnapshotWriter

logger = logging.getLogger(__name__)

SUCCESS_RATE_THRESHOLD = 0.90
COVERAGE_THRESHOLD = 0.60
PROGRESS_INTERVAL = 25
ERROR_SAMPLE_LIMIT = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_universe(path: Path) -> list[str]:
    """Load repo list from file, stripping comments and blank lines."""
    repos: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                repos.append(line)
    return repos


def universe_sha256(path: Path) -> str:
    """Return hex SHA-256 of the universe file bytes."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def classify_fetch_status(
    error: Optional[str],
    success: bool,
    coverage: float,
    coverage_threshold: float = COVERAGE_THRESHOLD,
) -> str:
    """Classify a per-repo fetch outcome as a v1.0 fetch_status string.

    This is the single source of truth for status classification. It is never
    called by the mapper; the caller passes a pre-classified status to the mapper.

    Classification rules (evaluated in order):
      1. "not found" or "could not resolve" (case-insensitive) in error  ->  not_found
         Covers "Repository not found: ..." and the GraphQL form
         "Could not resolve to a Repository with the name '...'".
      2. "404" in error                            ->  not_found
         Covers REST 404 responses.
      3. "451" in error                            ->  not_found
         Legal takedown, treated as a death event.
      4. "403" in error                            ->  error
         Rate limit or auth failure; NOT a death event.
      5. success=True, coverage >= threshold       ->  success
      6. success=True, coverage < threshold        ->  partial
      7. everything else                           ->  error
    """
    if error:
        err_lower = error.lower()
        if "not found" in err_lower or "could not resolve" in err_lower or "404" in error or "451" in error:
            return "not_found"
        if "403" in error:
            return "error"
    if success:
        return "success" if coverage >= coverage_threshold else "partial"
    return "error"


def get_git_sha() -> str:
    """Return short git SHA of HEAD, or 'unknown' if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the snapshot collector CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Weekly snapshot collector for Deep Signal temporal dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run
  python -m open_source_risk_model.cli.snapshot \\
      --universe data/universe/universe_v1.txt --output-dir /tmp/observatory

  # Smoke test (10 repos, no auth needed beyond GITHUB_TOKEN)
  python -m open_source_risk_model.cli.snapshot \\
      --universe data/universe/universe_v1.txt --output-dir /tmp/obs --max-repos 10
""",
    )
    parser.add_argument("--universe", required=True, type=Path, help="Path to universe_vN.txt")
    parser.add_argument("--output-dir", required=True, type=Path, help="Observatory output directory")
    parser.add_argument("--max-repos", type=int, default=None, help="Limit run to first N repos (smoke test)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing snapshot file for this date")
    parser.add_argument(
        "--run-date",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Override run date as YYYY-MM-DD (default: UTC today)",
    )
    parser.add_argument(
        "--universe-version",
        default="v1",
        help="Universe version label written into each record (default: v1)",
    )
    args = parser.parse_args()

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    run_date = args.run_date or datetime.now(timezone.utc).date()
    started_at = datetime.now(timezone.utc)
    run_id = f"snap-{run_date.strftime('%Y%m%d')}-{started_at.strftime('%H%M%S')}"

    logger.info("Run ID: %s | date: %s | output: %s", run_id, run_date, args.output_dir)

    # Load universe
    try:
        all_repos = load_universe(args.universe)
    except OSError as exc:
        logger.error("Cannot read universe file: %s", exc)
        sys.exit(1)

    sha256 = universe_sha256(args.universe)
    universe_version = args.universe_version

    if args.max_repos is not None:
        all_repos = all_repos[: args.max_repos]
        logger.info("--max-repos %d: limited universe to %d repos", args.max_repos, len(all_repos))

    logger.info("Universe: %d repos | sha256: %s", len(all_repos), sha256[:16] + "...")

    git_sha = get_git_sha()

    # Initialize pipeline
    config = IngestionConfig()
    pipeline = IngestionPipeline(github_token=github_token, config=config)

    # Counters
    repos_success = 0
    repos_partial = 0
    repos_not_found = 0
    repos_error = 0
    error_sample: list[dict[str, str]] = []
    api_calls_estimate = 0

    writer = SnapshotWriter(args.output_dir, run_date, force=args.force)

    try:
        writer.open()
    except FileExistsError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Phase 1: GraphQL batch snapshot fetch
    # ------------------------------------------------------------------
    logger.info("Phase 1: GraphQL batch fetch for %d repos...", len(all_repos))
    try:
        snapshots = pipeline.snapshot_fetcher.fetch_snapshots(all_repos)
    except Exception as exc:
        logger.warning("Phase 1 batch fetch raised an exception: %s -- proceeding with empty snapshot map", exc)
        snapshots = []

    snapshot_map = {s.repo_full_name: s for s in snapshots}
    batch_size = pipeline.snapshot_fetcher.current_batch_size
    api_calls_estimate += max(1, len(all_repos) // max(batch_size, 1))
    logger.info(
        "Phase 1 complete: %d/%d repos in snapshot map (batch_size=%d)",
        len(snapshot_map),
        len(all_repos),
        batch_size,
    )

    # ------------------------------------------------------------------
    # Phase 2: per-repo REST calls + feature engineering
    # ------------------------------------------------------------------
    logger.info("Phase 2: per-repo REST + features...")

    for idx, repo in enumerate(all_repos, 1):
        observed_at = datetime.now(timezone.utc)
        snapshot = snapshot_map.get(repo)
        fetch_error: Optional[str] = None

        # If repo is missing from batch result, call fetch_single for error classification
        if snapshot is None:
            try:
                snapshot = pipeline.snapshot_fetcher.fetch_single(repo)
                snapshot_map[repo] = snapshot
                api_calls_estimate += 1
            except Exception as exc:
                fetch_error = str(exc)
                api_calls_estimate += 1

        if snapshot is None:
            # Could not obtain snapshot data - classify and record
            fetch_status = classify_fetch_status(fetch_error, False, 0.0)
            record = pipeline_result_to_snapshot_record(
                repo_full_name=repo,
                snapshot=None,
                features={},
                fetch_status=fetch_status,
                error_message=fetch_error,
                run_id=run_id,
                universe_version=universe_version,
                observed_at=observed_at,
            )
            writer.write_record(record)
            if fetch_status == "not_found":
                repos_not_found += 1
            else:
                repos_error += 1
            if len(error_sample) < ERROR_SAMPLE_LIMIT:
                error_sample.append({"repo": repo, "message": fetch_error or "unknown"})
            _log_progress(idx, len(all_repos), repos_success, repos_partial, repos_not_found, repos_error, pipeline)
            continue

        # Fetch contributors
        contributors = []
        try:
            contributors = pipeline.contributors_fetcher.fetch_contributors(repo)
            api_calls_estimate += 2
        except Exception as exc:
            fetch_error = fetch_error or str(exc)
            api_calls_estimate += 1

        # Fetch issues
        issues = []
        try:
            issues = pipeline.issues_fetcher.fetch_issues(repo)
            api_calls_estimate += 1
        except Exception as exc:
            fetch_error = fetch_error or str(exc)

        # Feature engineering
        features: dict = {}
        coverage = 0.0
        fe_success = False
        try:
            features = pipeline.feature_engineer.compute_features(snapshot, contributors, issues)
            coverage, _ = pipeline.feature_engineer.check_feature_coverage(features)
            fe_success = True
        except Exception as exc:
            fetch_error = fetch_error or str(exc)

        fetch_status = classify_fetch_status(fetch_error, fe_success, coverage)

        record = pipeline_result_to_snapshot_record(
            repo_full_name=repo,
            snapshot=snapshot,
            features=features,
            fetch_status=fetch_status,
            error_message=fetch_error,
            run_id=run_id,
            universe_version=universe_version,
            observed_at=observed_at,
        )
        writer.write_record(record)

        if fetch_status == "success":
            repos_success += 1
        elif fetch_status == "partial":
            repos_partial += 1
        elif fetch_status == "not_found":
            repos_not_found += 1
            if len(error_sample) < ERROR_SAMPLE_LIMIT:
                error_sample.append({"repo": repo, "message": fetch_error or "not_found"})
        else:
            repos_error += 1
            if len(error_sample) < ERROR_SAMPLE_LIMIT:
                error_sample.append({"repo": repo, "message": fetch_error or "error"})

        _log_progress(idx, len(all_repos), repos_success, repos_partial, repos_not_found, repos_error, pipeline)

    # ------------------------------------------------------------------
    # Finalize: write manifest
    # ------------------------------------------------------------------
    completed_at = datetime.now(timezone.utc)
    manifest = RunManifest(
        run_id=run_id,
        started_at=started_at.isoformat(),
        completed_at=completed_at.isoformat(),
        universe_version=universe_version,
        universe_sha256=sha256,
        repos_total=len(all_repos),
        repos_success=repos_success,
        repos_partial=repos_partial,
        repos_not_found=repos_not_found,
        repos_error=repos_error,
        error_sample=error_sample,
        api_calls_estimate=api_calls_estimate,
        collector_git_sha=git_sha,
        schema_version=SCHEMA_VERSION,
    )
    writer.close(manifest)

    success_rate = (repos_success + repos_partial) / len(all_repos) if all_repos else 0.0
    logger.info(
        "Run complete: %d success, %d partial, %d not_found, %d error | "
        "success_rate=%.1f%% | manifest: %s",
        repos_success,
        repos_partial,
        repos_not_found,
        repos_error,
        success_rate * 100,
        writer.manifest_path(),
    )

    sys.exit(0 if success_rate >= SUCCESS_RATE_THRESHOLD else 1)


def _log_progress(
    idx: int,
    total: int,
    success: int,
    partial: int,
    not_found: int,
    error: int,
    pipeline: "IngestionPipeline",
) -> None:
    if idx % PROGRESS_INTERVAL == 0 or idx == total:
        gql_remaining = pipeline.rate_limiter.get_remaining("graphql")
        rest_remaining = pipeline.rate_limiter.get_remaining("rest")
        logger.info(
            "Progress %d/%d | success=%d partial=%d not_found=%d error=%d "
            "| graphql_remaining=%d rest_remaining=%d",
            idx,
            total,
            success,
            partial,
            not_found,
            error,
            gql_remaining,
            rest_remaining,
        )


if __name__ == "__main__":
    main()
