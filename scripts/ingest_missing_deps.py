"""Ingest dependency data for repos that have graphs but no dependencies."""
import sqlite3
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from open_source_risk_model.dependencies.ingestion_service import DependencyIngestionService

DB_PATH = "data/graphs.db"


def get_missing_repos():
    conn = sqlite3.connect(DB_PATH)
    all_repos = set(r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM repo_graphs"
    ).fetchall())
    dep_repos = set(r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM repo_dependencies"
    ).fetchall())
    conn.close()
    return sorted(all_repos - dep_repos)


def main():
    missing = get_missing_repos()
    print(f"Found {len(missing)} repos missing dependency data\n")
    if not missing:
        print("Nothing to do.")
        return

    svc = DependencyIngestionService(DB_PATH)
    success = 0
    errors = 0
    start = time.monotonic()

    for i, repo in enumerate(missing, 1):
        try:
            result = svc.ingest_repo(repo, refresh=False, resolve_packages=True)
            elapsed = time.monotonic() - start
            eta = (elapsed / i) * (len(missing) - i)
            print(
                f"[{i}/{len(missing)}] {repo}: "
                f"{result.dependencies_found} deps, "
                f"{result.dependencies_resolved} resolved, "
                f"{result.manifests_discovered} manifests "
                f"({result.duration_seconds:.1f}s) "
                f"ETA {eta/60:.0f}m"
            )
            success += 1
        except Exception as e:
            errors += 1
            print(f"[{i}/{len(missing)}] {repo}: ERROR - {e}")

    elapsed = time.monotonic() - start
    print(f"\nDone in {elapsed/60:.1f} minutes")
    print(f"  Success: {success}/{len(missing)}")
    print(f"  Errors: {errors}")

    # Verify
    conn = sqlite3.connect(DB_PATH)
    dep_count = conn.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_dependencies").fetchone()[0]
    resolved_count = conn.execute("SELECT COUNT(DISTINCT repo_full_name) FROM resolved_dependencies").fetchone()[0]
    print(f"\nDatabase state:")
    print(f"  Repos with direct deps: {dep_count}")
    print(f"  Repos with resolved deps: {resolved_count}")
    conn.close()


if __name__ == "__main__":
    main()
