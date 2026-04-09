#!/usr/bin/env python3
"""
Retry ingestion for rate-limited repos.

Runs the full pipeline for yaml/pyyaml and ytdl-org/youtube-dl:
  1. Dependency ingestion (parse direct deps)
  2. Transitive resolution
  3. Store resolved edges
  4. Graph enrichment
  5. Compute insight scores

Validates each repo after pipeline completion and exits 0 only
if both repos pass all checks.

Usage:
    python scripts/retry_rate_limited.py
"""
import logging
import os
import sys
import time
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

from open_source_risk_model.dependencies.ingestion_service import DependencyIngestionService
from open_source_risk_model.resolution.resolver import TransitiveResolver
from open_source_risk_model.resolution.storage import ResolvedDependencyStorage
from open_source_risk_model.resolution.budget_tracker import BudgetConfig
from open_source_risk_model.persistence.graph_repo import GraphRepository
from open_source_risk_model.persistence.db import get_connection
from open_source_risk_model.insights.compute import compute_repo_insight

DB_PATH = os.getenv("GRAPH_DB_PATH", "data/graphs.db")
TARGET_REPOS = ["yaml/pyyaml", "ytdl-org/youtube-dl"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("retry_rate_limited")


def enrich_repo_graph(repo_full_name: str, db_path: str) -> tuple[int, int]:
    """Run graph enrichment for a single repo. Returns (node_count, edge_count)."""
    from open_source_risk_model.service.score_repo import score_repo
    from open_source_risk_model.graph.builder import build_graph
    from open_source_risk_model.graph.schema import GraphConfig

    score_data = score_repo(repo_full_name, refresh=False, fetch_issues=False)

    config = GraphConfig(
        include_cves=False,
        max_releases=10,
        max_maintainers=5,
        max_risk_factors=5,
        cve_timeout_seconds=5,
        cache_ttl_hours=24,
        parse_dependencies=False,
    )

    graph = build_graph(repo_full_name, score_data, config)
    elapsed_ms = 0  # not timing enrichment separately

    graph_repo = GraphRepository(db_path)
    graph_repo.save_graph(repo_full_name, graph, elapsed_ms)
    return len(graph.nodes), len(graph.edges)


def get_dependency_count(repo_full_name: str, db_path: str) -> int:
    """Count rows in repo_dependencies for this repo."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM repo_dependencies WHERE repo_full_name = ?",
            (repo_full_name,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_graph_edge_count(repo_full_name: str, db_path: str) -> int:
    """Get edge_count from repo_graphs for this repo."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT edge_count FROM repo_graphs WHERE repo_full_name = ?",
            (repo_full_name,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def run_pipeline(repo: str, db_path: str) -> dict:
    """
    Execute the full pipeline for a single repo.
    Returns a result dict with success status and metrics.
    """
    result = {
        "repo": repo,
        "success": False,
        "dep_count": 0,
        "edge_count": 0,
        "insight_score": None,
        "error": None,
    }

    # Step 1: Dependency ingestion
    logger.info(f"[{repo}] Step 1/5: Ingesting dependencies...")
    try:
        service = DependencyIngestionService(db_path=db_path)
        ingestion = service.ingest_repo(repo, refresh=True, resolve_packages=True)
        if not ingestion.success:
            # Check for rate-limit errors in the error list
            for err in ingestion.errors:
                if "403" in str(err):
                    logger.error(f"[{repo}] Rate-limit failure (HTTP 403): {err}")
                else:
                    logger.error(f"[{repo}] Ingestion error: {err}")
            result["error"] = f"Ingestion failed: {'; '.join(ingestion.errors)}"
            return result
        logger.info(
            f"[{repo}] Ingestion complete: {ingestion.dependencies_found} deps, "
            f"{ingestion.dependencies_resolved} resolved"
        )
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg:
            logger.error(f"[{repo}] Rate-limit failure (HTTP 403): {error_msg}")
        else:
            logger.error(f"[{repo}] Ingestion failed: {error_msg}")
        result["error"] = f"Ingestion exception: {error_msg}"
        return result

    # Step 2: Transitive resolution
    logger.info(f"[{repo}] Step 2/5: Resolving transitive dependencies...")
    try:
        resolver = TransitiveResolver(
            db_path=db_path,
            max_depth=3,
            budget_config=BudgetConfig(global_budget=200),
        )
        edges, summary = resolver.resolve_repo(repo)
        logger.info(
            f"[{repo}] Resolution complete: {summary.resolved_count} resolved, "
            f"{summary.error_count} errors, {summary.total_edges} total edges"
        )
    except Exception as e:
        logger.error(f"[{repo}] Transitive resolution failed: {e}")
        result["error"] = f"Resolution failed: {e}"
        return result

    # Step 3: Store resolved edges
    logger.info(f"[{repo}] Step 3/5: Storing resolved edges...")
    try:
        storage = ResolvedDependencyStorage(db_path)
        storage.store_edges(repo, edges)
        logger.info(f"[{repo}] Stored {len(edges)} resolved edges")
    except Exception as e:
        logger.error(f"[{repo}] Edge storage failed: {e}")
        result["error"] = f"Storage failed: {e}"
        return result

    # Step 4: Graph enrichment
    logger.info(f"[{repo}] Step 4/5: Enriching graph...")
    try:
        node_count, edge_count = enrich_repo_graph(repo, db_path)
        logger.info(f"[{repo}] Graph enriched: {node_count} nodes, {edge_count} edges")
    except Exception as e:
        logger.error(f"[{repo}] Graph enrichment failed: {e}")
        result["error"] = f"Enrichment failed: {e}"
        return result

    # Step 5: Compute insight
    logger.info(f"[{repo}] Step 5/5: Computing insight scores...")
    try:
        graph_repo = GraphRepository(db_path)
        insight = compute_repo_insight(repo, graph_repo)
        insight_score = insight.graph_signal_score
        logger.info(
            f"[{repo}] Insight computed: score={insight_score}, "
            f"label={insight.graph_signal_label}"
        )
    except Exception as e:
        logger.error(f"[{repo}] Insight computation failed: {e}")
        result["error"] = f"Insight failed: {e}"
        return result

    # Populate result metrics
    result["dep_count"] = get_dependency_count(repo, db_path)
    result["edge_count"] = get_graph_edge_count(repo, db_path)
    result["insight_score"] = insight_score
    result["success"] = True
    return result


def validate_result(result: dict) -> list[str]:
    """Validate pipeline result. Returns list of failure reasons (empty = pass)."""
    failures = []
    repo = result["repo"]

    if not result["success"]:
        failures.append(f"Pipeline did not complete: {result['error']}")
        return failures

    if result["dep_count"] <= 0:
        failures.append(f"Dependency count is 0 (expected > 0)")

    if result["edge_count"] <= 0:
        failures.append(f"Graph edge count is 0 (expected > 0)")

    if result["insight_score"] is None:
        failures.append(f"Insight score is null (expected non-null)")

    return failures


def main() -> int:
    """
    Retry ingestion for rate-limited repos.
    Returns 0 on success, 1 if any repo fails.
    """
    logger.info(f"Starting retry for {len(TARGET_REPOS)} repos: {TARGET_REPOS}")
    logger.info(f"Database: {DB_PATH}")

    all_passed = True

    for repo in TARGET_REPOS:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {repo}")
        logger.info(f"{'='*60}")

        start = time.monotonic()
        result = run_pipeline(repo, DB_PATH)
        elapsed = time.monotonic() - start

        failures = validate_result(result)

        if failures:
            all_passed = False
            logger.error(
                f"FAILED: {repo} — {'; '.join(failures)} "
                f"(elapsed: {elapsed:.1f}s)"
            )
        else:
            logger.info(
                f"SUCCESS: {repo} — "
                f"deps={result['dep_count']}, "
                f"edges={result['edge_count']}, "
                f"insight_score={result['insight_score']} "
                f"(elapsed: {elapsed:.1f}s)"
            )

    if all_passed:
        logger.info("\nAll repos passed validation.")
        return 0
    else:
        logger.error("\nOne or more repos failed validation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
