"""Batch resolve transitive dependencies for all repos in the database."""
import sqlite3
import time
import sys

from open_source_risk_model.resolution.resolver import TransitiveResolver
from open_source_risk_model.resolution.storage import ResolvedDependencyStorage
from open_source_risk_model.resolution.budget_tracker import BudgetConfig

DB_PATH = "data/graphs.db"
MAX_DEPTH = 3
BUDGET_PER_REPO = 200


def get_repos_to_resolve():
    conn = sqlite3.connect(DB_PATH)
    already = {r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM resolved_dependencies"
    ).fetchall()}
    all_repos = [r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM repo_dependencies ORDER BY repo_full_name"
    ).fetchall()]
    conn.close()
    return [r for r in all_repos if r not in already]


def main():
    repos = get_repos_to_resolve()
    total = len(repos)
    if total == 0:
        print("All repos already resolved.")
        return 0

    storage = ResolvedDependencyStorage(DB_PATH)
    print(f"Resolving {total} repos (max_depth={MAX_DEPTH}, budget={BUDGET_PER_REPO}/repo)\n")

    global_start = time.monotonic()
    success = 0
    errors = 0
    total_edges = 0

    for i, repo in enumerate(repos, 1):
        try:
            resolver = TransitiveResolver(
                db_path=DB_PATH,
                max_depth=MAX_DEPTH,
                budget_config=BudgetConfig(global_budget=BUDGET_PER_REPO),
            )
            edges, summary = resolver.resolve_repo(repo)
            storage.store_edges(repo, edges)
            total_edges += len(edges)
            success += 1
            elapsed = time.monotonic() - global_start
            rate = elapsed / i
            eta = rate * (total - i)
            print(
                f"[{i}/{total}] {repo}: "
                f"{summary.resolved_count} resolved, "
                f"{summary.error_count} err, "
                f"{summary.cycle_count} cyc, "
                f"{summary.budget_exhausted_count} budget, "
                f"{summary.unsupported_ecosystem_count} unsup, "
                f"api={summary.api_calls_made} cache={summary.cache_hits} "
                f"({summary.elapsed_seconds:.1f}s) "
                f"ETA {eta/60:.0f}m"
            )
        except Exception as e:
            errors += 1
            print(f"[{i}/{total}] {repo}: ERROR - {e}")

    elapsed = time.monotonic() - global_start
    print(f"\nDone in {elapsed/60:.1f} minutes")
    print(f"  Resolved: {success}/{total} repos")
    print(f"  Errors: {errors}")
    print(f"  Total edges: {total_edges}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
