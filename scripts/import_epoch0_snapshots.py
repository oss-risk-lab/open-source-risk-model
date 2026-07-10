"""
Backfill script: import pre-existing raw snapshots into the observatory format.

Each JSON file in the raw snapshots directory represents one repository observation
from before the temporal snapshot engine existed. This script groups them by
observed date and writes one append-only JSONL.gz + one manifest per date.

All output files are written atomically. Existing files are never overwritten.

Usage:
    python scripts/import_epoch0_snapshots.py \
        --raw-snapshots-dir data/raw_snapshots/ \
        --output-dir /path/to/observatory/
"""

import argparse
import hashlib
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from open_source_risk_model.snapshots.mapper import pipeline_result_to_snapshot_record
from open_source_risk_model.snapshots.models import RunManifest, SCHEMA_VERSION
from open_source_risk_model.snapshots.writer import SnapshotWriter

logger = logging.getLogger(__name__)

UNIVERSE_VERSION_EPOCH0 = "epoch0"

_REPO_RE = __import__("re").compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _raw_snapshot_filename_to_repo(name: str) -> str | None:
    """Convert 'Owner__repo.json' to 'Owner/repo', None if not parseable."""
    stem = name.removesuffix(".json")
    if "__" not in stem:
        return None
    owner, _, rest = stem.partition("__")
    if not owner or not rest:
        return None
    repo = f"{owner}/{rest}"
    return repo if _REPO_RE.match(repo) else None


def classify_fetch_status(feature_status: dict[str, str]) -> str:
    """Classify epoch0 fetch_status from the feature_status dict.

    Rules:
      - absent or empty feature_status -> "success" (no known degradation)
      - all values "ok" -> "success"
      - any value other than "ok" -> "partial"
    """
    if not feature_status:
        return "success"
    return "success" if all(v == "ok" for v in feature_status.values()) else "partial"


def _sha256_of_dir(path: Path) -> str:
    """Stable SHA-256 over sorted filenames in a directory (names only, not content)."""
    names = sorted(f.name for f in path.glob("*.json"))
    digest = hashlib.sha256("\n".join(names).encode()).hexdigest()
    return digest


def load_raw_snapshots(raw_dir: Path) -> list[dict]:
    """Read all .json files in raw_dir and return parsed records.

    Supports two on-disk schemas:
    - v1: top-level keys include ``full_name`` and ``fetched_at``
    - v0: no ``full_name``; repo name is inferred from the filename
          (``Owner__repo.json`` -> ``Owner/repo``)
    """
    records = []
    for path in sorted(raw_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "fetched_at" not in data:
                logger.warning("Skipping %s: missing fetched_at", path.name)
                continue
            if "full_name" not in data:
                repo = _raw_snapshot_filename_to_repo(path.name)
                if not repo:
                    logger.warning("Skipping %s: cannot infer full_name from filename", path.name)
                    continue
                data = dict(data, full_name=repo)
                logger.debug("Inferred full_name=%s from filename %s", repo, path.name)
            records.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping %s: %s", path.name, exc)
    return records


def group_by_date(records: list[dict]) -> dict[str, list[dict]]:
    """Group raw snapshot records by UTC date string (YYYY-MM-DD)."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        date_str = record["fetched_at"][:10]
        grouped[date_str].append(record)
    return dict(grouped)


def write_date_group(
    date_str: str,
    raw_records: list[dict],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write one JSONL.gz and one manifest for a single date group.

    Returns (snapshot_path, manifest_path). Raises FileExistsError if either
    output file already exists.
    """
    from datetime import date as date_type

    run_date = date_type.fromisoformat(date_str)
    run_id = f"epoch0-{date_str}"

    started_at = datetime.now(timezone.utc)

    repos_success = 0
    repos_partial = 0
    error_sample: list[dict[str, str]] = []

    writer = SnapshotWriter(output_dir, run_date, force=False)
    writer.open()

    for raw in raw_records:
        repo_full_name: str = raw["full_name"]
        fetched_at_str: str = raw["fetched_at"]
        observed_at = datetime.fromisoformat(fetched_at_str)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)

        features: dict = raw.get("features", {})
        meta = features.get("__meta__", {})
        feature_status = meta.get("feature_status", {})
        fetch_status = classify_fetch_status(feature_status)

        record = pipeline_result_to_snapshot_record(
            repo_full_name=repo_full_name,
            snapshot=None,
            features=features,
            fetch_status=fetch_status,
            error_message=None,
            run_id=run_id,
            universe_version=UNIVERSE_VERSION_EPOCH0,
            observed_at=observed_at,
        )
        writer.write_record(record)

        if fetch_status == "success":
            repos_success += 1
        else:
            repos_partial += 1

    completed_at = datetime.now(timezone.utc)
    manifest = RunManifest(
        run_id=run_id,
        started_at=started_at.isoformat(),
        completed_at=completed_at.isoformat(),
        universe_version=UNIVERSE_VERSION_EPOCH0,
        universe_sha256=_sha256_of_dir(output_dir.parent if output_dir.name else output_dir),
        repos_total=len(raw_records),
        repos_success=repos_success,
        repos_partial=repos_partial,
        repos_not_found=0,
        repos_error=0,
        error_sample=error_sample,
        api_calls_estimate=0,
        collector_git_sha="epoch0",
        schema_version=SCHEMA_VERSION,
        epoch0=True,
    )
    writer.close(manifest)

    return writer.snapshot_path(), writer.manifest_path()


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Import pre-existing raw snapshots into the observatory JSONL.gz format.",
    )
    parser.add_argument(
        "--raw-snapshots-dir",
        type=Path,
        default=Path("data/raw_snapshots"),
        help="Directory containing .json raw snapshot files (default: data/raw_snapshots/)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Observatory output directory (receives snapshots/ and manifests/ subdirs)",
    )
    args = parser.parse_args(argv)

    raw_dir: Path = args.raw_snapshots_dir
    output_dir: Path = args.output_dir

    if not raw_dir.is_dir():
        logger.error("Raw snapshots directory not found: %s", raw_dir)
        sys.exit(1)

    logger.info("Loading raw snapshots from %s ...", raw_dir)
    raw_records = load_raw_snapshots(raw_dir)
    if not raw_records:
        logger.error("No valid .json files found in %s", raw_dir)
        sys.exit(1)

    grouped = group_by_date(raw_records)
    dates = sorted(grouped)
    logger.info("Found %d records across %d dates: %s", len(raw_records), len(dates), dates)

    written_snapshots = []
    written_manifests = []
    skipped = []

    for date_str in dates:
        group = grouped[date_str]
        logger.info("Writing %d records for %s ...", len(group), date_str)
        try:
            snap_path, manifest_path = write_date_group(date_str, group, output_dir)
            written_snapshots.append(snap_path)
            written_manifests.append(manifest_path)
            logger.info("  snapshot : %s", snap_path)
            logger.info("  manifest : %s", manifest_path)
        except FileExistsError as exc:
            logger.warning("Skipping %s (already exists): %s", date_str, exc)
            skipped.append(date_str)

    print()
    print("=== Epoch 0 import summary ===")
    print(f"  Input files : {len(raw_records)}")
    print(f"  Dates found : {len(dates)}")
    for date_str in dates:
        g = grouped[date_str]
        success = sum(1 for r in g if classify_fetch_status(
            r.get("features", {}).get("__meta__", {}).get("feature_status", {})
        ) == "success")
        partial = len(g) - success
        status = "(skipped, already exists)" if date_str in skipped else "written"
        print(f"    {date_str}: {len(g)} records ({success} success, {partial} partial) [{status}]")
    print(f"  Files written : {len(written_snapshots)} snapshots + {len(written_manifests)} manifests")
    if skipped:
        print(f"  Skipped (already exist): {skipped}")


if __name__ == "__main__":
    main()
