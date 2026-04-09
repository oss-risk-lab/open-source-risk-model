#!/usr/bin/env python3
"""
Batch graph enrichment for existing repos in the database.

Phase 1 (fast): releases, contributors, registry detection, risk factors
Phase 2 (full): adds CVEs on top of Phase 1

Usage:
    # Fast enrichment, all repos (skip already-enriched)
    python scripts/enrich_graphs.py

    # Fast enrichment, limit to 10 repos
    python scripts/enrich_graphs.py --limit 10

    # Full enrichment with CVEs
    python scripts/enrich_graphs.py --include-cves

    # Force re-enrich everything
    python scripts/enrich_graphs.py --force

    # Dry run (show what would be enriched)
    python scripts/enrich_graphs.py --dry-run
"""
import argparse
import json
import os
import sys
import time
import sqlite3
import requests
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

DB_PATH = os.getenv("GRAPH_DB_PATH", "data/graphs.db")


def check_rate_limit():
    """Check GitHub API rate limit, return (remaining, reset_timestamp)."""
    token = os.environ.get("GITHUB_TOKEN")
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            core = data["resources"]["core"]
            return core["remaining"], core["reset"]
    except Exception:
        pass
    return None, None


def wait_for_rate_limit(min_remaining=200):
    """If rate limit is low, sleep until reset."""
    remaining, reset_ts = check_rate_limit()
    if remaining is not None and remaining < min_remaining:
        wait_seconds = max(0, reset_ts - time.time()) + 5
        print(f"  ⏳ Rate limit low ({remaining} remaining). Sleeping {int(wait_seconds)}s until reset...")
        time.sleep(wait_seconds)
        return True
    return False


def get_repos_to_enrich(db_path, force=False, limit=None):
    """Get list of repos that need enrichment."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if force:
        query = "SELECT repo_full_name, node_count, edge_count FROM repo_graphs ORDER BY repo_full_name"
    else:
        # Only repos with stub graphs (node_count <= 1)
        query = "SELECT repo_full_name, node_count, edge_count FROM repo_graphs WHERE node_count <= 1 ORDER BY repo_full_name"
    if limit:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def enrich_repo(repo_full_name, include_cves=False, db_path=DB_PATH):
    """Run graph builder for a single repo and save to database."""
    from open_source_risk_model.service.score_repo import score_repo
    from open_source_risk_model.graph.builder import build_graph
    from open_source_risk_model.graph.schema import GraphConfig
    from open_source_risk_model.persistence.graph_repo import GraphRepository

    # Get score data (uses cached snapshots if available)
    score_data = score_repo(repo_full_name, refresh=False, fetch_issues=False)

    # Build graph — fast mode: no CVEs, no dependency re-parsing
    config = GraphConfig(
        include_cves=include_cves,
        max_releases=10,
        max_maintainers=5,
        max_risk_factors=5,
        cve_timeout_seconds=5,
        cache_ttl_hours=24,
        parse_dependencies=False,  # deps already populated
    )

    start = time.time()
    graph = build_graph(repo_full_name, score_data, config)
    elapsed_ms = int((time.time() - start) * 1000)

    # Save to database
    graph_repo = GraphRepository(db_path)
    graph_repo.save_graph(repo_full_name, graph, elapsed_ms)

    return len(graph.nodes), len(graph.edges), elapsed_ms


def main():
    parser = argparse.ArgumentParser(description="Batch graph enrichment")
    parser.add_argument("--limit", type=int, default=None, help="Max repos to enrich")
    parser.add_argument("--include-cves", action="store_true", help="Include CVE nodes (slower)")
    parser.add_argument("--force", action="store_true", help="Re-enrich repos that already have graphs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enriched")
    parser.add_argument("--db-path", default=DB_PATH, help="Database path")
    args = parser.parse_args()

    # Validate token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN not set. Add it to .env or export it.")
        sys.exit(1)

    remaining, _ = check_rate_limit()
    if remaining is not None:
        print(f"📊 GitHub API: {remaining} requests remaining")
    else:
        print("⚠️  Could not check rate limit")

    # Get repos
    repos = get_repos_to_enrich(args.db_path, force=args.force, limit=args.limit)
    total = len(repos)

    if total == 0:
        print("✅ All repos already enriched. Use --force to re-enrich.")
        return

    mode = "full (with CVEs)" if args.include_cves else "fast (no CVEs)"
    print(f"\n🔧 Enrichment mode: {mode}")
    print(f"📦 Repos to enrich: {total}")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for r in repos:
            print(f"  {r['repo_full_name']} (current: {r['node_count']} nodes, {r['edge_count']} edges)")
        return

    # Run enrichment
    success = 0
    failed = 0
    errors = []
    total_nodes = 0
    total_edges = 0
    batch_start = time.time()

    for i, repo in enumerate(repos, 1):
        name = repo["repo_full_name"]

        # Rate limit guard every 10 repos
        if i % 10 == 0:
            wait_for_rate_limit(min_remaining=200)

        try:
            nodes, edges, ms = enrich_repo(name, include_cves=args.include_cves, db_path=args.db_path)
            success += 1
            total_nodes += nodes
            total_edges += edges
            print(f"  [{i}/{total}] ✅ {name} → {nodes} nodes, {edges} edges ({ms}ms)")
        except Exception as e:
            failed += 1
            error_msg = str(e)[:100]
            errors.append({"repo": name, "error": error_msg})
            print(f"  [{i}/{total}] ❌ {name} → {error_msg}")

    # Summary
    elapsed = time.time() - batch_start
    print(f"\n{'='*60}")
    print(f"📊 Enrichment complete")
    print(f"   Success: {success}/{total}")
    print(f"   Failed:  {failed}/{total}")
    print(f"   Total nodes added: {total_nodes}")
    print(f"   Total edges added: {total_edges}")
    print(f"   Avg nodes/repo: {total_nodes/max(success,1):.1f}")
    print(f"   Avg edges/repo: {total_edges/max(success,1):.1f}")
    print(f"   Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    if errors:
        print(f"\n❌ Failed repos ({len(errors)}):")
        for e in errors:
            print(f"   {e['repo']}: {e['error']}")

    # Check final rate limit
    remaining, _ = check_rate_limit()
    if remaining is not None:
        print(f"\n📊 GitHub API remaining: {remaining}")


if __name__ == "__main__":
    main()
