"""
Validate a completed snapshot run: verify record count, schema fields, and uniqueness.

Usage:
    python scripts/validate_snapshot_run.py \\
        --snapshot-file path/to/snapshots/2026/deep-signal-snapshot-2026-07-13.jsonl.gz \\
        --manifest-file path/to/manifests/2026-07-13.json

Exit codes:
  0  all checks pass
  1  one or more checks failed, or files could not be read
"""

import argparse
import gzip
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
    "observed_at",
    "repo_full_name",
    "universe_version",
    "fetch_status",
    "features",
    "raw",
    "feature_coverage",
    "feature_status",
)

VALID_FETCH_STATUSES = frozenset({"success", "partial", "not_found", "error"})


def validate(snapshot_file: Path, manifest_file: Path) -> int:
    """Run all checks. Prints results and returns exit code (0 = pass, 1 = fail)."""
    failures: list[str] = []

    # Load manifest
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: Cannot read manifest: {exc}", file=sys.stderr)
        return 1

    repos_total = manifest.get("repos_total", -1)
    repos_success = manifest.get("repos_success", 0)
    repos_partial = manifest.get("repos_partial", 0)

    # Load snapshot records
    try:
        with gzip.open(snapshot_file, "rt", encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh if line.strip()]
    except (OSError, gzip.BadGzipFile) as exc:
        print(f"ERROR: Cannot read snapshot file: {exc}", file=sys.stderr)
        return 1

    line_count = len(records)

    # Check 1: line count matches repos_total
    if line_count != repos_total:
        failures.append(
            f"Line count mismatch: snapshot has {line_count} records, "
            f"manifest.repos_total={repos_total}"
        )

    # Check 2: required fields present on every record
    for i, record in enumerate(records):
        missing = [f for f in REQUIRED_FIELDS if f not in record]
        if missing:
            failures.append(
                f"Record {i} ({record.get('repo_full_name', '?')}): "
                f"missing fields {missing}"
            )
        status = record.get("fetch_status")
        if status not in VALID_FETCH_STATUSES:
            failures.append(
                f"Record {i} ({record.get('repo_full_name', '?')}): "
                f"invalid fetch_status {status!r}"
            )

    # Check 3: no duplicate repo_full_name
    names = [r.get("repo_full_name") for r in records]
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        failures.append(f"Duplicate repo_full_name values ({len(duplicates)}): {duplicates[:5]}")

    # Always print success rate
    total = line_count if line_count > 0 else 1
    success_rate = (repos_success + repos_partial) / total * 100
    print(f"run_id       : {manifest.get('run_id', '?')}")
    print(f"snapshot     : {snapshot_file}")
    print(f"records      : {line_count}")
    print(f"repos_total  : {repos_total}")
    print(f"success rate : {repos_success + repos_partial}/{total} = {success_rate:.1f}%")
    print(f"  success={repos_success} partial={repos_partial} "
          f"not_found={manifest.get('repos_not_found', 0)} "
          f"error={manifest.get('repos_error', 0)}")
    print()

    if failures:
        print(f"FAILED ({len(failures)} check(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"OK: all {len(REQUIRED_FIELDS)} field checks, count check, and uniqueness check passed.")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate a snapshot JSONL.gz against its manifest.",
    )
    parser.add_argument(
        "--snapshot-file",
        required=True,
        type=Path,
        help="Path to the .jsonl.gz snapshot file",
    )
    parser.add_argument(
        "--manifest-file",
        required=True,
        type=Path,
        help="Path to the manifest .json file",
    )
    args = parser.parse_args(argv)
    sys.exit(validate(args.snapshot_file, args.manifest_file))


if __name__ == "__main__":
    main()
