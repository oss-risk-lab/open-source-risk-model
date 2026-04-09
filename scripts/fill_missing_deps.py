"""Fill dependency data for repos that have graphs but no parsed dependencies."""
import sqlite3
import sys
import time

DB_PATH = "data/graphs.db"


def get_missing_repos():
    conn = sqlite3.connect(DB_PATH)
    all_repos = set(r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM repo_graphs"
    ).fetchall())
    has_deps = set(r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM repo_dependencies"
    ).fetchall())
    conn.close()
    return sorted(all_repos - has_deps)


def main():
    missing = get_missing_repos()
    if not missing:
        print("All repos already have dependency data.")
        return 0

    print(f"Found {len(missing)} repos missing dependency data.\n")

    # Step 1: Parse direct dependencies
    from open_source_risk_model.dependencies.ingestion_service import DependencyIngestionService
    svc = DependencyIngestionService(db_path=DB_PATH)

    success = 0
    errors = 0
    for i, repo in enumerate(missing, 1):
        try:
            result = svc.ingest_repo(repo, refresh=False, resolve_packages=True)
            dep_count = result.dependencies_found
            status = f"{dep_count} deps"
            if dep_count == 0:
                status = "0 deps (no manifest found?)"
            print(f"[{i}/{len(missing)}] {repo}: {status} ({result.duration_seconds:.1f}s)")
            success += 1
        except Exception as e:
            errors += 1
            print(f"[{i}/{len(missing)}] {repo}: ERROR - {e}")

    print(f"\nDirect dependency parsing: {success}/{len(missing)} succeeded, {errors} errors")

    # Step 2: Resolve transitive dependencies for newly parsed repos
    print("\nResolving transitive dependencies...")
    from open_source_risk_model.resolution.resolver import TransitiveResolver
    from open_source_risk_model.resolution.storage import ResolvedDependencyStorage
    from open_source_risk_model.resolution.budget_tracker import BudgetConfig

    conn = sqlite3.connect(DB_PATH)
    has_deps_now = set(r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM repo_dependencies"
    ).fetchall())
    already_resolved = set(r[0] for r in conn.execute(
        "SELECT DISTINCT repo_full_name FROM resolved_dependencies"
    ).fetchall())
    conn.close()

    to_resolve = sorted(has_deps_now - already_resolved)
    if not to_resolve:
        print("All repos with dependencies are already resolved.")
        return 0

    storage = ResolvedDependencyStorage(DB_PATH)
    resolved_ok = 0
    for i, repo in enumerate(to_resolve, 1):
        try:
            resolver = TransitiveResolver(
                db_path=DB_PATH, max_depth=3,
                budget_config=BudgetConfig(global_budget=200),
            )
            edges, summary = resolver.resolve_repo(repo)
            storage.store_edges(repo, edges)
            resolved_ok += 1
            print(f"[{i}/{len(to_resolve)}] {repo}: {summary.resolved_count} resolved, {summary.error_count} err")
        except Exception as e:
            print(f"[{i}/{len(to_resolve)}] {repo}: RESOLVE ERROR - {e}")

    print(f"\nTransitive resolution: {resolved_ok}/{len(to_resolve)} succeeded")

    # Final counts
    conn = sqlite3.connect(DB_PATH)
    total_graphs = conn.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_graphs").fetchone()[0]
    total_deps = conn.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_dependencies").fetchone()[0]
    total_resolved = conn.execute("SELECT COUNT(DISTINCT repo_full_name) FROM resolved_dependencies").fetchone()[0]
    conn.close()
    print(f"\nFinal: {total_graphs} graphs, {total_deps} with deps, {total_resolved} resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
