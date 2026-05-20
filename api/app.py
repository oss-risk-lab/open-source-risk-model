from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from open_source_risk_model.service.score_repo import score_repo
from open_source_risk_model.graph.builder import build_graph
from open_source_risk_model.graph.schema import Graph, GraphConfig
from open_source_risk_model.graph.cache import GraphCache
from open_source_risk_model.utils.logging_utils import (
    StructuredLogger,
    generate_request_id,
    set_request_id,
    clear_request_id,
    log_event,
    LogEvent,
)
from open_source_risk_model.utils.metrics import get_metrics_collector
from open_source_risk_model.persistence.graph_repo import GraphRepository
from open_source_risk_model.persistence.job_repo import JobRepository
from open_source_risk_model.persistence.index_repo import IndexRepository
from open_source_risk_model.persistence.worker import IngestionWorker
from open_source_risk_model.persistence.errors import DatabaseError
from open_source_risk_model.persistence.db import get_connection, init_database
from open_source_risk_model.persistence.dependency_repo import DependencyRepository
from open_source_risk_model.persistence.scope_repo import ScopeRepository
from open_source_risk_model.insights.compute import compute_repo_insight
from open_source_risk_model.config.demo_repos import load_demo_repos, validate_demo_repos

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, skip

app = FastAPI(title="Deep Signal Security API", version="0.1.0")

# Initialize structured logger
logger = StructuredLogger(__name__)

# Initialize graph cache (1 hour TTL)
graph_cache = GraphCache(cache_dir="data/graphs", ttl_hours=1)

# Initialize metrics collector
metrics = get_metrics_collector()

# Initialize graph repository (will be set in startup event)
graph_repo: GraphRepository | None = None

# Initialize job repository (will be set in startup event)
job_repo: JobRepository | None = None

# Initialize index repository (will be set in startup event)
index_repo: IndexRepository | None = None

# Initialize ingestion worker (will be set in startup event)
ingestion_worker: IngestionWorker | None = None
worker_task = None

# Initialize dependency repository (will be set in startup event)
dependency_repo: DependencyRepository | None = None

# Initialize scope repository (will be set in startup event)
scope_repo: ScopeRepository | None = None

# CORS: read allowed origins from env var (comma-separated), fall back to ["*"] for dev
_cors_origins_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()] if _cors_origins_raw else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Best-effort dependency-to-repo mapping (hardcoded for MVP)
PACKAGE_TO_REPO: Dict[str, str] = {
    "flask": "pallets/flask",
    "requests": "psf/requests",
    "sqlalchemy": "sqlalchemy/sqlalchemy",
    "django": "django/django",
    "numpy": "numpy/numpy",
    "pandas": "pandas-dev/pandas",
    "fastapi": "tiangolo/fastapi",
    "express": "expressjs/express",
    "react": "facebook/react",
    "lodash": "lodash/lodash",
    "axios": "axios/axios",
    "scikit-learn": "scikit-learn/scikit-learn",
}

# Root route — serves homepage at /
@app.get("/")
def serve_home():
    return FileResponse("ui/index.html")


# Catch-all for UI pages (insights.html, graph.html, etc.)
@app.get("/{page}.html")
def serve_page(page: str):
    file_path = Path("ui") / f"{page}.html"
    if file_path.exists():
        return FileResponse(str(file_path))
    raise HTTPException(status_code=404, detail="Page not found")


# Mount static files for UI
# Serve the ui/ directory at /ui for the graph visualization HTML
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")
# Also mount at /static for any static assets referenced in the HTML
app.mount("/static", StaticFiles(directory="ui"), name="static_ui")


@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    global graph_repo, job_repo, index_repo, ingestion_worker, worker_task, dependency_repo, scope_repo

    db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")

    # Startup banner
    print("=" * 60)
    print("  Deep Signal — Open Source Risk Intelligence")
    print("=" * 60)
    print(f"  DB path:        {db_path}")
    print(f"  DB exists:      {Path(db_path).exists()}")
    print(f"  GITHUB_TOKEN:   {'set' if os.environ.get('GITHUB_TOKEN') else 'NOT SET (degraded mode)'}")
    print(f"  OPENAI_API_KEY: {'set' if os.environ.get('OPENAI_API_KEY') else 'not set'}")
    print("=" * 60)

    # Startup validation: warn if GITHUB_TOKEN is not set (degraded mode)
    if not os.environ.get("GITHUB_TOKEN"):
        logger.warning(
            "GITHUB_TOKEN is not set — running in degraded mode with rate-limited GitHub API access"
        )

    # Ensure data directory exists (critical for fresh deployments like Render)
    data_dir = Path(db_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    # Run schema migrations (idempotent — safe to call every startup)
    try:
        init_database(db_path)
    except Exception as e:
        logger.warning(f"Schema migration warning: {e}")
    
    # Check if database persistence is enabled
    db_enabled = os.getenv("GRAPH_DB_ENABLED", "true").lower() == "true"
    
    if db_enabled:
        try:
            # Get database path from environment or use default
            db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")
            
            # Initialize GraphRepository
            graph_repo = GraphRepository(db_path=db_path)
            
            # Initialize JobRepository
            job_repo = JobRepository(db_path=db_path)
            
            # Initialize IndexRepository
            index_repo = IndexRepository(db_path=db_path)

            # Initialize DependencyRepository
            dependency_repo = DependencyRepository(db_path=db_path)

            # Initialize ScopeRepository
            scope_repo = ScopeRepository(db_path=db_path)

            # Mark interrupted jobs (jobs that were running when server stopped)
            interrupted_count = job_repo.mark_interrupted_jobs()
            if interrupted_count > 0:
                logger.info(
                    "Marked interrupted jobs",
                    count=interrupted_count,
                )
            
            logger.info(
                "Database persistence enabled",
                db_path=db_path,
            )
            
            # Check if worker is enabled
            worker_enabled = os.getenv("GRAPH_WORKER_ENABLED", "true").lower() == "true"
            
            if worker_enabled:
                # Get worker configuration
                poll_interval = int(os.getenv("GRAPH_WORKER_POLL_INTERVAL", "5"))
                
                # Initialize IngestionWorker
                ingestion_worker = IngestionWorker(
                    job_repo=job_repo,
                    graph_repo=graph_repo,
                    poll_interval=poll_interval
                )
                
                # Start worker in background
                import asyncio
                worker_task = asyncio.create_task(ingestion_worker.start())
                
                logger.info(
                    "Ingestion worker started",
                    poll_interval=poll_interval,
                )
            else:
                logger.info("Ingestion worker disabled")
                
        except Exception as e:
            logger.error(
                "Failed to initialize database persistence",
                error=str(e),
            )
            # Set repositories to None to fall back to dynamic generation
            graph_repo = None
            job_repo = None
            index_repo = None
            dependency_repo = None
            scope_repo = None
            ingestion_worker = None
    else:
        logger.info("Database persistence disabled")
        graph_repo = None
        job_repo = None
        index_repo = None
        dependency_repo = None
        scope_repo = None


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    global ingestion_worker, worker_task
    
    logger.info("Application shutting down")
    
    # Stop ingestion worker if running
    if ingestion_worker is not None:
        logger.info("Stopping ingestion worker...")
        ingestion_worker.stop()
        
        # Wait for worker to finish current job
        if worker_task is not None:
            try:
                import asyncio
                await asyncio.wait_for(worker_task, timeout=30.0)
                logger.info("Ingestion worker stopped gracefully")
            except asyncio.TimeoutError:
                logger.warning("Ingestion worker did not stop within timeout")
            except Exception as e:
                logger.error("Error stopping ingestion worker", error=str(e))

@app.get("/api/health")
def health():
    """
    Health check endpoint with service status and metrics.
    
    Returns:
        Health status including:
        - Overall status
        - Service statuses (github_api, osv_api, cache)
        - Performance metrics (cache_hit_rate, avg_response_time_ms)
    """
    # Get current metrics
    metrics_data = metrics.get_metrics_dict()
    
    # Check service statuses
    services = {
        "github_api": _check_github_api_status(),
        "osv_api": _check_osv_api_status(),
        "cache": _check_cache_status(),
    }
    
    # Determine overall status
    all_services_ok = all(s["status"] == "ok" for s in services.values())
    overall_status = "ok" if all_services_ok else "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
        "metrics": {
            "cache_hit_rate": metrics_data["cache"]["hit_rate"],
            "avg_response_time_ms": metrics_data["api_response"]["avg_ms"],
            "total_requests": metrics_data["api_response"]["count"],
            "total_errors": metrics_data["errors"]["total"],
        },
        "uptime_seconds": metrics_data["uptime_seconds"],
    }


@app.get("/api/admin/ingestion-health")
def ingestion_health():
    """
    Ingestion data quality report.

    Classifies every ingested repo by health status using the ingestion_health view:
      - parse_failure   manifests found but 0 deps parsed (language parser gap)
      - persistence_gap deps parsed but <70% reached the database (schema/bug)
      - stale_90d       last successful ingestion >90 days ago
      - stale_30d       last successful ingestion 30–90 days ago
      - ok              ingested within the last 30 days with good coverage

    Returns repos grouped by health status plus a summary count.
    """
    db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")
    try:
        with get_connection(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT repo_full_name, last_run_at, manifests_discovered,
                       dependencies_found, rows_in_db, age_days, health
                FROM ingestion_health
                ORDER BY health, age_days DESC
            """).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    grouped: Dict[str, list] = {
        "parse_failure": [],
        "persistence_gap": [],
        "stale_90d": [],
        "stale_30d": [],
        "ok": [],
    }
    for row in rows:
        entry = {
            "repo": row["repo_full_name"],
            "last_run_at": row["last_run_at"],
            "manifests_discovered": row["manifests_discovered"],
            "dependencies_found": row["dependencies_found"],
            "rows_in_db": row["rows_in_db"],
            "age_days": row["age_days"],
        }
        grouped[row["health"]].append(entry)

    return {
        "summary": {h: len(v) for h, v in grouped.items()},
        "stale_threshold_days": {"warning": 30, "critical": 90},
        "repos": grouped,
    }


def _check_github_api_status() -> Dict:
    """
    Check GitHub API status.
    
    Returns:
        Status dict with status and message
    """
    try:
        # Check if GitHub token is configured
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return {
                "status": "warning",
                "message": "No GitHub token configured (rate limits apply)",
            }
        
        # Simple connectivity check - try to access GitHub API
        import requests
        response = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        
        if response.status_code == 200:
            rate_limit_data = response.json()
            remaining = rate_limit_data.get("rate", {}).get("remaining", 0)
            limit = rate_limit_data.get("rate", {}).get("limit", 0)
            
            return {
                "status": "ok",
                "message": f"Connected (rate limit: {remaining}/{limit})",
                "rate_limit_remaining": remaining,
                "rate_limit_total": limit,
            }
        else:
            return {
                "status": "error",
                "message": f"GitHub API returned status {response.status_code}",
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect: {str(e)}",
        }


def _check_osv_api_status() -> Dict:
    """
    Check OSV.dev API status.
    
    Returns:
        Status dict with status and message
    """
    try:
        # Simple connectivity check - try to access OSV API
        import requests
        response = requests.post(
            "https://api.osv.dev/v1/query",
            json={"package": {"name": "test", "ecosystem": "PyPI"}},
            timeout=5
        )
        
        if response.status_code in [200, 404]:  # 404 is ok (package not found)
            return {
                "status": "ok",
                "message": "Connected",
            }
        else:
            return {
                "status": "error",
                "message": f"OSV API returned status {response.status_code}",
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect: {str(e)}",
        }


def _check_cache_status() -> Dict:
    """
    Check cache status.
    
    Returns:
        Status dict with status and message
    """
    try:
        # Check if cache directory exists and is writable
        cache_dir = Path("data/graphs")
        if not cache_dir.exists():
            return {
                "status": "warning",
                "message": "Cache directory does not exist",
            }
        
        # Check if writable
        test_file = cache_dir / ".health_check"
        try:
            test_file.write_text("test")
            test_file.unlink()
            return {
                "status": "ok",
                "message": "Cache is operational",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Cache not writable: {str(e)}",
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Cache check failed: {str(e)}",
        }

@app.get("/api/score")
def score(
    repo: str = Query(..., description="GitHub repo in owner/repo format or GitHub URL"),
    refresh: bool = Query(False, description="Force refresh from GitHub and overwrite snapshot"),
    fetch_issues: bool = Query(True, description="Fetch issues + compute issue metrics"),
):
    try:
        payload = score_repo(repo, refresh=refresh, fetch_issues=fetch_issues)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Keep it simple for v1; later we can return structured error codes
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.get("/api/graph")
def graph(
    request: Request,
    repo: str = Query(..., description="GitHub repo in owner/repo format or GitHub URL"),
    refresh: bool = Query(False, description="Force refresh from external APIs"),
    include_cves: bool = Query(True, description="Include CVE nodes (may be slow)"),
    max_releases: int = Query(10, description="Maximum number of release nodes", ge=1, le=100),
    max_maintainers: int = Query(5, description="Maximum number of maintainer nodes", ge=1, le=50),
    max_risk_factors: int = Query(5, description="Maximum number of risk factor nodes", ge=1, le=20),
):
    """
    Generate supply chain risk graph for a repository.
    
    Returns a graph representation with nodes (repo, releases, maintainers, CVEs, etc.)
    and edges representing relationships between entities.
    
    Args:
        repo: Repository in owner/repo format or GitHub URL
        refresh: Force refresh from external APIs (ignores cache and database)
        include_cves: Whether to include CVE vulnerability nodes
        max_releases: Maximum number of release nodes to include
        max_maintainers: Maximum number of maintainer nodes to include
        max_risk_factors: Maximum number of risk factor nodes to include
    
    Returns:
        JSON response with graph structure and metadata
    
    Raises:
        HTTPException: 400 for invalid input, 404 for repo not found,
                      500 for internal errors, 503 for external API failures
    """
    # Generate and set request ID
    request_id = generate_request_id()
    set_request_id(request_id)
    
    start_time = time.time()
    
    try:
        # Log request start
        logger.info(
            "Graph API request received",
            repo=repo,
            refresh=refresh,
            include_cves=include_cves,
            max_releases=max_releases,
            max_maintainers=max_maintainers,
            max_risk_factors=max_risk_factors,
        )
        
        # Validate repository format
        repo_normalized = _normalize_repo_name(repo)
        if not repo_normalized:
            logger.warning("Invalid repository format", provided=repo)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_REPO_FORMAT",
                        "message": "Invalid repository format. Use 'owner/repo' or GitHub URL",
                        "details": {
                            "provided": repo,
                            "expected": "owner/repo"
                        }
                    }
                }
            )
        
        # Try database first (unless refresh is requested)
        cache_hit = False
        if not refresh and graph_repo is not None:
            try:
                cached_graph_data = graph_repo.get_graph(repo_normalized)
                if cached_graph_data:
                    # Check TTL
                    updated_at = datetime.fromisoformat(cached_graph_data["generated_at"])
                    age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
                    ttl_hours = float(os.getenv("GRAPH_TTL_HOURS", "24"))
                    auto_refresh_stale = os.getenv("GRAPH_AUTO_REFRESH_STALE", "false").lower() == "true"
                    
                    if age_hours < ttl_hours:
                        # Fresh data, return immediately
                        logger.info(f"Returning fresh cached graph for {repo_normalized}")
                        
                        # Record cache hit
                        metrics.record_cache_hit()
                        
                        # Calculate response time
                        generation_time_ms = int((time.time() - start_time) * 1000)
                        metrics.record_api_response(generation_time_ms)
                        
                        # Add request_id to metadata
                        cached_graph_data["metadata"]["request_id"] = request_id
                        cached_graph_data["metadata"]["generation_time_ms"] = generation_time_ms
                        
                        return cached_graph_data
                    elif not auto_refresh_stale:
                        # Stale but auto-refresh disabled, return with stale indicator
                        logger.info(f"Returning stale cached graph for {repo_normalized} (age: {age_hours:.1f}h)")
                        
                        # Record cache hit (even though stale)
                        metrics.record_cache_hit()
                        
                        # Calculate response time
                        generation_time_ms = int((time.time() - start_time) * 1000)
                        metrics.record_api_response(generation_time_ms)
                        
                        # Add stale indicators to metadata
                        cached_graph_data["metadata"]["is_stale"] = True
                        cached_graph_data["metadata"]["age_hours"] = age_hours
                        cached_graph_data["metadata"]["request_id"] = request_id
                        cached_graph_data["metadata"]["generation_time_ms"] = generation_time_ms
                        
                        return cached_graph_data
                    # else: fall through to regeneration (auto_refresh_stale=true and data is stale)
                    else:
                        logger.info(f"Auto-refreshing stale graph for {repo_normalized} (age: {age_hours:.1f}h)")
            except DatabaseError as e:
                logger.warning(f"Database read failed for {repo_normalized}: {e}, falling back to dynamic generation")
            except Exception as e:
                logger.warning(f"Unexpected error reading from database for {repo_normalized}: {e}, falling back to dynamic generation")
        
        # Check file-based cache (unless refresh is requested)
        if not refresh:
            try:
                cached_graph = graph_cache.get(repo_normalized, max_releases, max_maintainers, include_cves, max_risk_factors)
                if cached_graph:
                    # Cache hit - return cached graph
                    cache_hit = True
                    graph_obj = cached_graph
                    
                    # Record cache hit
                    metrics.record_cache_hit()
                    
                    # Log cache hit
                    log_event(logger, LogEvent.CACHE_HIT, repo=repo_normalized)
                    
                    # Calculate generation time (minimal for cache hit)
                    generation_time_ms = int((time.time() - start_time) * 1000)
                    
                    # Record API response time
                    metrics.record_api_response(generation_time_ms)
                    
                    # Serialize graph to dict
                    graph_dict = graph_obj.to_dict()
                    
                    # Collect data sources used
                    data_sources = set()
                    for node in graph_obj.nodes:
                        if "source" in node.provenance:
                            data_sources.add(node.provenance["source"])
                    
                    # Build response
                    response = {
                        "repo": repo_normalized,
                        "schema_version": graph_obj.metadata.get("schema_version", "1.0"),
                        "generated_at": graph_obj.metadata.get("generated_at"),
                        "graph": {
                            "nodes": graph_dict["nodes"],
                            "edges": graph_dict["edges"],
                        },
                        "metadata": {
                            "node_count": len(graph_obj.nodes),
                            "edge_count": len(graph_obj.edges),
                            "data_sources": sorted(list(data_sources)),
                            "cache_hit": True,
                            "generation_time_ms": generation_time_ms,
                            "request_id": request_id,
                        }
                    }
                    
                    # Include warnings if any
                    warnings = graph_obj.metadata.get("warnings", [])
                    if warnings:
                        response["metadata"]["warnings"] = warnings
                    
                    logger.info(
                        "Graph API request completed (cache hit)",
                        repo=repo_normalized,
                        generation_time_ms=generation_time_ms,
                    )
                    
                    return response
                else:
                    # Cache miss
                    metrics.record_cache_miss()
                    log_event(logger, LogEvent.CACHE_MISS, repo=repo_normalized)
            except Exception as e:
                # Cache read error - log and continue to build graph
                logger.warning(f"Cache read error for {repo_normalized}: {e}, falling back to build")
        
        # Cache miss or refresh requested - build graph from scratch
        log_event(logger, LogEvent.GRAPH_GENERATION_STARTED, repo=repo_normalized)
        
        # Get score data first (this validates repo exists)
        try:
            score_data = score_repo(repo_normalized, refresh=refresh, fetch_issues=False)
        except ValueError as e:
            # Repository not found or invalid
            error_msg = str(e)
            if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
                logger.warning("Repository not found", repo=repo_normalized)
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": {
                            "code": "REPO_NOT_FOUND",
                            "message": f"Repository '{repo_normalized}' not found",
                            "details": {
                                "repo": repo_normalized,
                                "suggestion": "Check repository name and ensure it's public or you have access"
                            }
                        }
                    }
                )
            else:
                raise HTTPException(status_code=400, detail=str(e))
        
        # Build graph configuration
        config = GraphConfig(
            include_cves=include_cves,
            max_releases=max_releases,
            max_maintainers=max_maintainers,
            max_risk_factors=max_risk_factors,
        )
        
        # Build the graph
        try:
            graph_build_start = time.time()
            graph_obj = build_graph(repo_normalized, score_data, config)
            graph_build_time_ms = int((time.time() - graph_build_start) * 1000)
            
            # Record graph generation time
            metrics.record_graph_generation(graph_build_time_ms)
            
            # Log successful generation
            log_event(
                logger,
                LogEvent.GRAPH_GENERATION_COMPLETED,
                repo=repo_normalized,
                node_count=len(graph_obj.nodes),
                edge_count=len(graph_obj.edges),
                generation_time_ms=graph_build_time_ms,
            )
        except Exception as e:
            # Log failed generation
            log_event(
                logger,
                LogEvent.GRAPH_GENERATION_FAILED,
                level="error",
                repo=repo_normalized,
                error=str(e),
            )
            
            # Record error
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ["timeout", "connection", "unavailable"]):
                metrics.record_error("external_api")
            else:
                metrics.record_error("graph_generation")
            
            # Check if this is an external API failure
            if any(keyword in error_msg for keyword in ["timeout", "connection", "unavailable", "rate limit"]):
                # External API failure - return 503 with partial graph if possible
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": {
                            "code": "EXTERNAL_API_FAILURE",
                            "message": "External API temporarily unavailable",
                            "details": {
                                "error": str(e),
                                "suggestion": "Try again later or disable CVE fetching with include_cves=false"
                            }
                        }
                    }
                )
            else:
                # Internal processing error
                raise
        
        # Calculate generation time
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Record API response time
        metrics.record_api_response(generation_time_ms)
        
        # Try to save to database (best effort)
        if graph_repo is not None:
            try:
                graph_repo.save_graph(repo_normalized, graph_obj, graph_build_time_ms)
                logger.info(f"Saved graph for {repo_normalized} to database")
            except DatabaseError as e:
                logger.warning(f"Failed to save graph to database: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error saving graph to database: {e}")
        
        # Store graph in file-based cache for future requests
        try:
            graph_cache.set(repo_normalized, graph_obj, max_releases, max_maintainers, include_cves, max_risk_factors)
            log_event(logger, LogEvent.CACHE_WRITE, repo=repo_normalized)
        except Exception as e:
            # Cache write error - log but don't fail the request
            log_event(
                logger,
                LogEvent.CACHE_WRITE_FAILED,
                level="warning",
                repo=repo_normalized,
                error=str(e),
            )
        
        # Serialize graph to dict
        graph_dict = graph_obj.to_dict()
        
        # Collect data sources used
        data_sources = set()
        for node in graph_obj.nodes:
            if "source" in node.provenance:
                data_sources.add(node.provenance["source"])
        
        # Build response
        response = {
            "repo": repo_normalized,
            "schema_version": graph_obj.metadata.get("schema_version", "1.0"),
            "generated_at": graph_obj.metadata.get("generated_at"),
            "graph": {
                "nodes": graph_dict["nodes"],
                "edges": graph_dict["edges"],
            },
            "metadata": {
                "node_count": len(graph_obj.nodes),
                "edge_count": len(graph_obj.edges),
                "data_sources": sorted(list(data_sources)),
                "cache_hit": cache_hit,
                "generation_time_ms": generation_time_ms,
                "request_id": request_id,
            }
        }
        
        # Include warnings if any
        warnings = graph_obj.metadata.get("warnings", [])
        if warnings:
            response["metadata"]["warnings"] = warnings
        
        logger.info(
            "Graph API request completed",
            repo=repo_normalized,
            generation_time_ms=generation_time_ms,
            node_count=len(graph_obj.nodes),
            edge_count=len(graph_obj.edges),
        )
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        metrics.record_error("internal")
        log_event(
            logger,
            LogEvent.GRAPH_GENERATION_FAILED,
            level="error",
            repo=repo,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error during graph generation",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )
    finally:
        # Clear request ID from context
        clear_request_id()


def _normalize_repo_name(repo: str) -> str:
    """
    Normalize repository name from various formats to owner/repo.
    
    Accepts:
    - owner/repo
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    
    Args:
        repo: Repository identifier in various formats
    
    Returns:
        Normalized owner/repo string, or empty string if invalid
    """
    if not repo:
        return ""
    
    # First check if it's a GitHub URL
    github_url_pattern = r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$"
    match = re.match(github_url_pattern, repo)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    
    # For non-URL formats, only accept exact owner/repo format
    # Remove trailing .git if present
    if repo.endswith(".git"):
        repo = repo[:-4]
    
    # Remove single trailing slash if present
    if repo.endswith("/"):
        repo = repo[:-1]
    
    # Check if it's in owner/repo format (exactly one slash, no extra slashes)
    # Must match the entire string (no extra characters)
    if re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repo):
        return repo
    
    # Invalid format
    return ""


def _risk_label_from_score(score: float) -> str:
    """Return LOW / MEDIUM / HIGH label based on risk score thresholds."""
    if score < 0.30:
        return "LOW"
    elif score < 0.60:
        return "MEDIUM"
    return "HIGH"


def _generate_scope_id() -> str:
    """Generate a unique scope identifier."""
    return f"scope_{uuid.uuid4().hex[:12]}"


from pydantic import BaseModel
from typing import List, Optional, Any


class IngestScopeRequest(BaseModel):
    """Request model for multi-repo scope ingestion."""
    name: str
    repos: List[str]
    dependencies: Optional[List[str]] = []


class IngestScopeResponse(BaseModel):
    """Response model for multi-repo scope ingestion."""
    scope_id: str
    status: str
    system_risk_summary: dict
    priority_risks: List[dict]
    top_risk_drivers: List[dict]
    top_risky_dependencies: List[dict]
    graph: dict
    errors: dict


def resolve_dependency_input(dep: str) -> dict:
    """Resolve a dependency name to a repo mapping or a package-only entry.

    Looks up the dependency in PACKAGE_TO_REPO. If found, returns a repo-backed
    entry; otherwise returns a package-only entry with no repo association.
    """
    repo = PACKAGE_TO_REPO.get(dep)
    if repo:
        return {"kind": "repo", "repo": repo, "package_name": dep, "mapped": True}
    return {"kind": "package_only", "repo": None, "package_name": dep, "mapped": False}


def merge_graphs(graphs: List[Tuple[str, Graph]], unmapped_nodes: List[dict]) -> dict:
    """Merge multiple repo graphs into a single merged graph dict.

    Deduplicates nodes by node.id (first occurrence wins for properties),
    tracks contributing repos via source_repos on each node, deduplicates
    edges by (source, target, relationship_type) tuple while preserving
    different relationship types between the same node pair, and appends
    unmapped dependency nodes as standalone package nodes.

    Args:
        graphs: List of (repo_name, Graph) tuples to merge.
        unmapped_nodes: List of dicts with id, type, label for unmapped deps.

    Returns:
        Dict with "nodes" and "edges" lists of plain dicts.
    """
    merged_nodes: Dict[str, dict] = {}  # keyed by node.id
    seen_edges: set = set()  # (source, target, relationship_type) tuples
    merged_edges: List[dict] = []

    for repo_name, graph_obj in graphs:
        for node in graph_obj.nodes:
            if node.id not in merged_nodes:
                node_dict = node.to_dict()
                node_dict["source_repos"] = [repo_name]
                merged_nodes[node.id] = node_dict
            else:
                if repo_name not in merged_nodes[node.id]["source_repos"]:
                    merged_nodes[node.id]["source_repos"].append(repo_name)

        for edge in graph_obj.edges:
            edge_key = (edge.source, edge.target, edge.relationship_type.value)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                merged_edges.append(edge.to_dict())

    # Append unmapped dependency nodes as standalone package nodes
    for unode in unmapped_nodes:
        node_id = unode.get("id", "")
        if node_id and node_id not in merged_nodes:
            merged_nodes[node_id] = {
                "id": node_id,
                "type": unode.get("type", "package"),
                "label": unode.get("label", ""),
                "metadata": {},
                "provenance": {},
                "source_repos": [],
            }

    return {"nodes": list(merged_nodes.values()), "edges": merged_edges}


def _generate_risk_explanation(aggregate_label: str, high_risk_repos: int,
                               vulnerable_dependencies: int, high_risk_dependencies: int,
                               total_repos: int) -> str:
    """Generate a risk explanation following [Conclusion] + [because] + [Reason] pattern.

    All text is data-derived — no generic fallback placeholders allowed.
    """
    conclusion = f"Your system shows {aggregate_label.lower()} risk"
    if aggregate_label == "LOW":
        reasons = []
        if vulnerable_dependencies == 0:
            reasons.append("no vulnerable dependencies were detected")
        if high_risk_repos == 0:
            reasons.append("no high-risk repositories were found")
        if not reasons:
            reasons.append("no significant risk factors were detected across repositories or dependencies")
        return conclusion + " because " + " and ".join(reasons) + "."
    else:  # MEDIUM or HIGH
        reasons = []
        if vulnerable_dependencies > 0:
            reasons.append(f"{vulnerable_dependencies} vulnerable dependenc{'y was' if vulnerable_dependencies == 1 else 'ies were'} detected")
        if high_risk_repos > 0:
            reasons.append(f"{high_risk_repos} repositor{'y shows' if high_risk_repos == 1 else 'ies show'} high maintenance risk")
        if high_risk_dependencies > 0 and vulnerable_dependencies == 0:
            reasons.append(f"{high_risk_dependencies} high-risk dependenc{'y was' if high_risk_dependencies == 1 else 'ies were'} identified")
        if not reasons:
            reasons.append(f"maintenance risk scores across {total_repos} analyzed repositories exceed healthy thresholds")
        return conclusion + " because " + " and ".join(reasons) + "."


def _generate_key_factors(aggregate_label: str, high_risk_repos: int, medium_risk_repos: int,
                          vulnerable_dependencies: int, high_risk_dependencies: int,
                          total_unique_dependencies: int) -> List[str]:
    """Return 1–5 short strings identifying primary factors that influenced the risk level.

    All factors are data-derived — no generic placeholders allowed.
    """
    factors = []
    if vulnerable_dependencies == 0:
        factors.append("no vulnerable dependencies")
    else:
        factors.append(f"{vulnerable_dependencies} vulnerable dependenc{'y' if vulnerable_dependencies == 1 else 'ies'}")
    if high_risk_repos == 0:
        factors.append("no high-risk repositories")
    else:
        factors.append(f"{high_risk_repos} high-risk repositor{'y' if high_risk_repos == 1 else 'ies'}")
    if medium_risk_repos > 0:
        factors.append(f"{medium_risk_repos} medium-risk repositor{'y' if medium_risk_repos == 1 else 'ies'}")
    if high_risk_dependencies > 0:
        factors.append(f"{high_risk_dependencies} high-risk dependenc{'y' if high_risk_dependencies == 1 else 'ies'}")
    if total_unique_dependencies > 0 and vulnerable_dependencies == 0 and high_risk_dependencies == 0:
        factors.append(f"{total_unique_dependencies} dependencies analyzed")
    # Guarantee 1–5 entries
    if not factors:
        factors.append("no significant risk factors detected across analyzed components")
    return factors[:5]


def _get_recommended_action(aggregate_label: str) -> str:
    """Return the exact recommended action string for the given aggregate risk label."""
    actions = {
        "LOW": "No immediate action required.",
        "MEDIUM": "Monitor dependencies and maintenance activity.",
        "HIGH": "Review vulnerable dependencies and high-risk repositories immediately.",
    }
    return actions.get(aggregate_label, "Monitor dependencies and maintenance activity.")


def _extract_primary_risk_factor(aggregate_label: str, vulnerable_dependencies: int,
                                 high_risk_repos: int, high_risk_dependencies: int) -> str:
    """Return a single dominant factor string identifying what drives the system's risk level.

    Selection priority:
    1. Vulnerable dependencies > 0
    2. High-risk repos > 0
    3. High-risk dependencies > 0
    4. Aggregate is LOW
    5. Fallback (still data-derived, never generic)
    """
    if vulnerable_dependencies > 0:
        return f"{vulnerable_dependencies} vulnerable dependenc{'y' if vulnerable_dependencies == 1 else 'ies'} drive elevated system risk"
    if high_risk_repos > 0:
        return f"{high_risk_repos} high-risk repositor{'y' if high_risk_repos == 1 else 'ies'} contribute to elevated maintenance risk"
    if high_risk_dependencies > 0:
        return f"{high_risk_dependencies} high-risk dependenc{'y' if high_risk_dependencies == 1 else 'ies'} identified in the supply chain"
    if aggregate_label == "LOW":
        return "No vulnerable dependencies detected"
    return "No significant risk factors were detected across repositories or dependencies"


def compute_system_risk_summary(per_repo_results: List[dict], merged_graph: dict) -> dict:
    """Compute aggregated system risk summary from per-repo results and merged graph.

    Args:
        per_repo_results: List of dicts, each with repo (str), risk_score (float|None),
                          risk_label (str|None), error (str|None).
        merged_graph: Dict with "nodes" and "edges" lists (output of merge_graphs()).

    Returns:
        Dict with repo-level metrics, dependency-level metrics, aggregate score/label,
        system_summary sentence, and per_repo_results.
    """
    total_repos = len(per_repo_results)

    # Repo-level metrics from non-error repos
    high_risk_repos = 0
    medium_risk_repos = 0
    low_risk_repos = 0
    valid_scores = []

    for r in per_repo_results:
        if r.get("error") is not None:
            continue
        label = (r.get("risk_label") or "").upper()
        if label == "HIGH":
            high_risk_repos += 1
        elif label == "MEDIUM":
            medium_risk_repos += 1
        elif label == "LOW":
            low_risk_repos += 1
        score = r.get("risk_score")
        if score is not None:
            valid_scores.append(score)

    # Aggregate risk score: arithmetic mean of non-error repo risk scores
    aggregate_risk_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    aggregate_label = _risk_label_from_score(aggregate_risk_score)

    # Dependency-level metrics from merged graph nodes
    nodes = merged_graph.get("nodes", [])
    total_unique_dependencies = 0
    dependencies_used_by_multiple_repos = 0
    high_risk_dependencies = 0
    vulnerable_dependencies = 0

    for node in nodes:
        node_type = (node.get("type") or "").lower()
        if node_type not in ("package", "dependency"):
            continue
        total_unique_dependencies += 1
        source_repos = node.get("source_repos", [])
        if len(source_repos) > 1:
            dependencies_used_by_multiple_repos += 1
        metadata = node.get("metadata", {}) or {}
        risk_score = metadata.get("risk_score")
        if risk_score is not None and risk_score >= 0.60:
            high_risk_dependencies += 1
        cve_count = metadata.get("cve_count", 0) or 0
        if cve_count > 0:
            vulnerable_dependencies += 1

    # System summary sentence
    system_summary = (
        f"Your system shows {aggregate_label.lower()} risk across "
        f"{total_repos} repositor{'y' if total_repos == 1 else 'ies'}"
    )
    detail_parts = []
    if high_risk_dependencies > 0:
        detail_parts.append(f"{high_risk_dependencies} high-risk dependenc{'y' if high_risk_dependencies == 1 else 'ies'}")
    if vulnerable_dependencies > 0:
        detail_parts.append(f"{vulnerable_dependencies} vulnerable dependenc{'y' if vulnerable_dependencies == 1 else 'ies'}")
    if detail_parts:
        system_summary += " with " + " and ".join(detail_parts)
    system_summary += "."

    # Generate new explanation fields from helpers
    risk_explanation = _generate_risk_explanation(
        aggregate_label, high_risk_repos, vulnerable_dependencies,
        high_risk_dependencies, total_repos
    )
    key_factors = _generate_key_factors(
        aggregate_label, high_risk_repos, medium_risk_repos,
        vulnerable_dependencies, high_risk_dependencies, total_unique_dependencies
    )
    recommended_action = _get_recommended_action(aggregate_label)
    primary_risk_factor = _extract_primary_risk_factor(
        aggregate_label, vulnerable_dependencies, high_risk_repos,
        high_risk_dependencies
    )

    return {
        "total_repos": total_repos,
        "high_risk_repos": high_risk_repos,
        "medium_risk_repos": medium_risk_repos,
        "low_risk_repos": low_risk_repos,
        "total_unique_dependencies": total_unique_dependencies,
        "dependencies_used_by_multiple_repos": dependencies_used_by_multiple_repos,
        "high_risk_dependencies": high_risk_dependencies,
        "vulnerable_dependencies": vulnerable_dependencies,
        "aggregate_risk_score": aggregate_risk_score,
        "aggregate_label": aggregate_label,
        "system_summary": system_summary,
        "per_repo_results": per_repo_results,
        "risk_explanation": risk_explanation,
        "key_factors": key_factors,
        "recommended_action": recommended_action,
        "primary_risk_factor": primary_risk_factor,
    }


# Severity base scores for priority risk computation
SEVERITY_BASE = {"high": 3.0, "medium": 2.0, "low": 1.0}


def compute_priority_risks(per_repo_results: List[dict], merged_graph: dict) -> List[dict]:
    """Compute prioritized risk items across the entire analysis scope.

    Gathers candidates from high-risk repos, dependencies with CVEs, and
    dependencies used by many repos. Scores each candidate using:
        priority_score = SEVERITY_BASE[severity] + (usage_count * 0.5) + (cve_count * 1.0)

    Deduplicates by name, sorts descending by priority_score, returns top 5.

    Args:
        per_repo_results: List of dicts with repo, risk_score, risk_label, error.
        merged_graph: Dict with "nodes" and "edges" lists (output of merge_graphs()).

    Returns:
        List of dicts, each with name, type, reason, severity, priority_score, used_by_repos.
    """
    candidates: Dict[str, dict] = {}  # keyed by name for deduplication

    # Source 1: High-risk repos (risk_label == "HIGH")
    for r in per_repo_results:
        if r.get("error") is not None:
            continue
        label = (r.get("risk_label") or "").upper()
        if label == "HIGH":
            repo_name = r.get("repo", "")
            severity = "high"
            usage_count = 0
            cve_count = 0
            score = SEVERITY_BASE[severity] + (usage_count * 0.5) + (cve_count * 1.0)
            candidates[repo_name] = {
                "name": repo_name,
                "type": "repo",
                "reason": "High-risk repository",
                "severity": severity,
                "priority_score": score,
                "used_by_repos": [],
            }
        if label == "MEDIUM":
            repo_name = r.get("repo", "")
            severity = "medium"
            usage_count = 0
            cve_count = 0
            score = SEVERITY_BASE[severity] + (usage_count * 0.5) + (cve_count * 1.0)
            if repo_name not in candidates or score > candidates[repo_name]["priority_score"]:
                candidates[repo_name] = {
                    "name": repo_name,
                    "type": "repo",
                    "reason": "Medium-risk repository",
                    "severity": severity,
                    "priority_score": score,
                    "used_by_repos": [],
                }

    # Process dependency nodes from merged graph
    nodes = merged_graph.get("nodes", [])
    for node in nodes:
        node_type = (node.get("type") or "").lower()
        if node_type not in ("package", "dependency"):
            continue

        node_name = node.get("label") or node.get("id", "")
        metadata = node.get("metadata", {}) or {}
        source_repos = node.get("source_repos", [])
        cve_count = metadata.get("cve_count", 0) or 0
        usage_count = len(source_repos)

        # Source 2: Dependencies with CVEs (cve_count > 0)
        if cve_count > 0:
            severity = "high" if cve_count >= 3 else "medium"
            score = SEVERITY_BASE[severity] + (usage_count * 0.5) + (cve_count * 1.0)
            # Keep the higher score if already a candidate
            if node_name not in candidates or score > candidates[node_name]["priority_score"]:
                candidates[node_name] = {
                    "name": node_name,
                    "type": "dependency",
                    "reason": f"Has {cve_count} known CVE{'s' if cve_count != 1 else ''}, used by {usage_count} repo{'s' if usage_count != 1 else ''}",
                    "severity": severity,
                    "priority_score": score,
                    "used_by_repos": list(source_repos),
                }

        # Source 3: Dependencies used by many repos (>= 2)
        if usage_count >= 2:
            severity = "medium"
            score = SEVERITY_BASE[severity] + (usage_count * 0.5) + (cve_count * 1.0)
            if node_name not in candidates or score > candidates[node_name]["priority_score"]:
                candidates[node_name] = {
                    "name": node_name,
                    "type": "dependency",
                    "reason": f"Used by {usage_count} repos (concentration risk)",
                    "severity": severity,
                    "priority_score": score,
                    "used_by_repos": list(source_repos),
                }

    # Sort descending by priority_score, return top 5
    sorted_risks = sorted(candidates.values(), key=lambda x: x["priority_score"], reverse=True)
    return sorted_risks[:5]


def compute_top_risky_dependencies(merged_graph: dict) -> List[dict]:
    """Compute top risky dependencies for UI dependency cards.

    Extracts dependency/package nodes from the merged graph, scores each by
    a combined formula prioritising severity, CVE count, then breadth of usage,
    and returns the top 10 sorted descending.

    Combined score: (risk_score or 0) * 3.0 + (cve_count * 1.0) + (len(source_repos) * 0.5)

    Args:
        merged_graph: Dict with "nodes" and "edges" lists (output of merge_graphs()).

    Returns:
        List of dicts, each with package_name, risk_score, risk_label,
        used_by_repos, cve_count, priority_score.
    """
    deps: List[dict] = []
    for node in merged_graph.get("nodes", []):
        node_type = (node.get("type") or "").lower()
        if node_type not in ("package", "dependency"):
            continue
        metadata = node.get("metadata", {}) or {}
        risk_score = metadata.get("risk_score") or 0
        cve_count = metadata.get("cve_count", 0) or 0
        source_repos = node.get("source_repos", [])
        combined = (risk_score * 3.0) + (cve_count * 1.0) + (len(source_repos) * 0.5)
        deps.append({
            "package_name": node.get("label") or node.get("id", ""),
            "risk_score": risk_score,
            "risk_label": _risk_label_from_score(risk_score),
            "used_by_repos": list(source_repos),
            "cve_count": cve_count,
            "priority_score": combined,
        })
    deps.sort(key=lambda x: x["priority_score"], reverse=True)
    return deps[:10]


def compute_scope_status(per_repo_results: List[dict]) -> str:
    """Derive scope status from per-repo processing outcomes.

    Args:
        per_repo_results: List of dicts, each with an optional "error" key.

    Returns:
        "complete" if all succeed (or empty list), "failed" if all fail,
        "partial" if mixed.
    """
    if not per_repo_results:
        return "complete"
    errors = sum(1 for r in per_repo_results if r.get("error") is not None)
    if errors == 0:
        return "complete"
    if errors == len(per_repo_results):
        return "failed"
    return "partial"


def get_top_risk_drivers(per_repo_results: List[dict], merged_graph: dict) -> List[dict]:
    """Return signal objects describing the top risk drivers.

    Generates factual signal objects with signal, category, and severity
    fields based on repo-level and dependency-level data.

    Args:
        per_repo_results: List of dicts with repo, risk_score, risk_label, error.
        merged_graph: Merged dependency graph dict with nodes and edges.

    Returns:
        List of signal dicts with signal, category, severity — sorted by
        severity (high first) then category priority.
    """
    # Handle empty per_repo_results
    if not per_repo_results:
        return [{"signal": "No repositories analyzed yet", "category": "maintenance", "severity": "info"}]

    signals: List[dict] = []
    valid = [r for r in per_repo_results if r.get("error") is None]

    # --- Vulnerability signals from merged_graph ---
    vuln_count = 0
    nodes = merged_graph.get("nodes", []) if merged_graph else []
    for node in nodes:
        node_type = node.get("type", "")
        if node_type in ("package", "dependency"):
            meta = node.get("metadata", {}) or {}
            if (meta.get("cve_count") or 0) > 0:
                vuln_count += 1

    if vuln_count == 0:
        signals.append({"signal": "No vulnerable dependencies detected", "category": "vulnerability", "severity": "info"})
    else:
        signals.append({"signal": f"{vuln_count} vulnerable dependencies detected", "category": "vulnerability", "severity": "high"})

    # --- Maintenance signals from per_repo_results ---
    high_risk_repos = [r for r in valid if r.get("risk_label") == "HIGH"]
    medium_risk_repos = [r for r in valid if r.get("risk_label") == "MEDIUM"]
    low_risk_repos = [r for r in valid if r.get("risk_label") == "LOW"]

    if len(high_risk_repos) > 0:
        signals.append({"signal": f"{len(high_risk_repos)} repositories show high maintenance risk", "category": "maintenance", "severity": "high"})

    if len(medium_risk_repos) > 0:
        signals.append({"signal": f"{len(medium_risk_repos)} repositories show moderate maintenance risk", "category": "maintenance", "severity": "medium"})

    if len(valid) > 0 and len(low_risk_repos) == len(valid):
        signals.append({"signal": "All repositories show low maintenance risk", "category": "maintenance", "severity": "info"})

    # --- Dependency signals from merged_graph ---
    dep_repo_counts: dict = {}
    for node in nodes:
        node_type = node.get("type", "")
        if node_type in ("package", "dependency"):
            meta = node.get("metadata", {}) or {}
            source_repos = meta.get("source_repos", []) or []
            if len(source_repos) > 1:
                dep_repo_counts[node.get("id", "")] = len(source_repos)

    shared_deps = len(dep_repo_counts)
    if shared_deps > 0:
        signals.append({"signal": f"{shared_deps} dependencies shared across multiple repositories", "category": "dependency", "severity": "medium"})

    # --- Positive signal guarantee for LOW aggregate risk ---
    all_low = len(valid) > 0 and all(r.get("risk_label") == "LOW" for r in valid) and vuln_count == 0
    if all_low:
        # Ensure at least 1 positive signal
        has_positive = any(s["severity"] == "info" for s in signals)
        if not has_positive:
            signals.append({"signal": "All components show strong maintenance activity", "category": "maintenance", "severity": "info"})

    # --- Sort signals by severity then category (Task 2.2) ---
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    category_order = {"vulnerability": 0, "maintenance": 1, "dependency": 2}
    signals.sort(key=lambda s: (severity_order[s["severity"]], category_order[s["category"]]))

    return signals


def compute_insight_statements(
    system_risk_summary: dict,
    per_repo_results: List[dict],
    merged_graph: dict
) -> List[str]:
    """Generate 1–6 interpretive insight statements about overall system posture.

    These are distinct from Risk Driver signals:
    - Risk Drivers = factual ("No vulnerable dependencies detected")
    - Insight Statements = interpretive ("Your dependency supply chain appears clean and well-maintained")

    Args:
        system_risk_summary: Dict with vulnerable_dependencies, high_risk_repos, etc.
        per_repo_results: List of per-repo result dicts.
        merged_graph: Merged dependency graph dict with nodes and edges.

    Returns:
        List of 1–6 interpretive strings.
    """
    statements: List[str] = []

    vulnerable_deps = system_risk_summary.get("vulnerable_dependencies", 0) or 0
    high_risk_repos = system_risk_summary.get("high_risk_repos", 0) or 0
    low_risk_repos = system_risk_summary.get("low_risk_repos", 0) or 0
    total_repos = system_risk_summary.get("total_repos", 0) or 0
    deps_shared = system_risk_summary.get("dependencies_used_by_multiple_repos", 0) or 0
    high_risk_deps = system_risk_summary.get("high_risk_dependencies", 0) or 0
    aggregate_label = system_risk_summary.get("aggregate_label", "LOW")

    # No vulnerable deps → clean supply chain
    if vulnerable_deps == 0:
        statements.append("Your dependency supply chain appears clean and well-maintained.")

    # All repos low maintenance risk
    if total_repos > 0 and low_risk_repos == total_repos:
        statements.append("Your repositories demonstrate consistent maintenance practices.")

    # N high-risk repos exist
    if high_risk_repos > 0:
        statements.append(
            f"{high_risk_repos} repositor{'y requires' if high_risk_repos == 1 else 'ies require'} "
            f"attention due to elevated maintenance risk, which may impact long-term system stability."
        )

    # Deps used by multiple repos (>= 2)
    if deps_shared >= 2:
        statements.append(
            f"{deps_shared} dependencies are shared across multiple repositories, "
            f"creating concentration points worth monitoring."
        )

    # All repos + deps low risk
    if total_repos > 0 and low_risk_repos == total_repos and vulnerable_deps == 0 and high_risk_deps == 0:
        statements.append("Your system appears stable and well-maintained across all analyzed components.")

    # High vulnerable deps (>= 3)
    if vulnerable_deps >= 3:
        statements.append("Multiple vulnerable dependencies suggest the dependency supply chain needs immediate review.")

    # Guarantee: return between 1 and 6 statements
    if not statements:
        statements.append("System risk posture has been evaluated across all analyzed components.")

    return statements[:6]


def build_scope_response(
    scope_id: str,
    name: str,
    status: str,
    system_risk_summary: dict,
    priority_risks: List[dict],
    top_risk_drivers: List[dict],
    top_risky_dependencies: List[dict],
    graph: dict,
    errors: dict,
    insight_statements: List[str] = None,
) -> dict:
    """Build the canonical scope response dict.

    This is the single contract between backend and frontend — both
    POST /api/ingest-scope and GET /api/scope/{scope_id} return this shape.

    Returns:
        Dict with scope_id, name, status, system_risk_summary, priority_risks,
        top_risk_drivers, top_risky_dependencies, graph, errors, insight_statements.
    """
    return {
        "scope_id": scope_id,
        "name": name,
        "status": status,
        "system_risk_summary": system_risk_summary,
        "priority_risks": priority_risks,
        "top_risk_drivers": top_risk_drivers,
        "top_risky_dependencies": top_risky_dependencies,
        "graph": graph,
        "errors": errors,
        "insight_statements": insight_statements or [],
    }


class IngestRequest(BaseModel):
    """Request model for batch ingestion."""
    repos: List[str]
    config: Optional[Dict[str, Any]] = None


@app.post("/api/ingest", status_code=202)
async def create_ingestion_job(request: IngestRequest):
    """
    Create a batch ingestion job.

    Submits a list of repositories for background ingestion into the graph database.
    Returns immediately with a job ID that can be used to track progress.

    Args:
        request: IngestRequest containing list of repos and optional config

    Returns:
        Job details including job_id, status, and metadata

    Raises:
        HTTPException: 400 for invalid input, 500 for internal errors,
                      503 if database or worker not available
    """
    try:
        # Check if job repository is available
        if job_repo is None:
            logger.error("Job repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Ingestion service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Validate repo list
        if not request.repos:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "repos list cannot be empty",
                        "details": {
                            "provided": request.repos
                        }
                    }
                }
            )

        if len(request.repos) > 1000:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Maximum 1000 repos per job",
                        "details": {
                            "provided": len(request.repos),
                            "maximum": 1000
                        }
                    }
                }
            )

        # Parse config if provided
        config_dict = None
        if request.config:
            try:
                config = GraphConfig(**request.config)
                # Convert GraphConfig to dict for storage
                config_dict = request.config
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_CONFIG",
                            "message": "Invalid graph configuration",
                            "details": {
                                "error": str(e)
                            }
                        }
                    }
                )

        # Create job (pass dict, not GraphConfig object)
        job_id = job_repo.create_job(request.repos, config_dict)

        logger.info(
            "Created ingestion job",
            job_id=job_id,
            repo_count=len(request.repos),
        )

        return {
            "job_id": job_id,
            "status": "pending",
            "total_repos": len(request.repos),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": "Ingestion job created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to create ingestion job",
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to create ingestion job",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )
@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Get ingestion job status and progress.

    Returns detailed information about a specific ingestion job including
    progress, errors, and completion status.

    Args:
        job_id: Job identifier (UUID)

    Returns:
        Job details including status, progress, and errors

    Raises:
        HTTPException: 404 if job not found, 500 for internal errors,
                      503 if database not available
    """
    try:
        # Check if job repository is available
        if job_repo is None:
            logger.error("Job repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Ingestion service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Get job details
        job = job_repo.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "JOB_NOT_FOUND",
                        "message": f"Job {job_id} not found",
                        "details": {
                            "job_id": job_id
                        }
                    }
                }
            )

        return job

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get job status",
            job_id=job_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to get job status",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )
@app.get("/api/jobs")
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status (pending, running, completed, failed, interrupted)"),
    limit: int = Query(100, description="Maximum number of results", ge=1, le=1000),
    offset: int = Query(0, description="Pagination offset", ge=0),
):
    """
    List ingestion jobs with optional filtering.

    Returns a paginated list of ingestion jobs, optionally filtered by status.

    Args:
        status: Optional status filter (pending, running, completed, failed, interrupted)
        limit: Maximum number of results (1-1000, default 100)
        offset: Pagination offset (default 0)

    Returns:
        List of jobs with pagination metadata

    Raises:
        HTTPException: 400 for invalid input, 500 for internal errors,
                      503 if database not available
    """
    try:
        # Check if job repository is available
        if job_repo is None:
            logger.error("Job repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Ingestion service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Validate status if provided
        valid_statuses = ["pending", "running", "completed", "failed", "interrupted"]
        if status and status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_STATUS",
                        "message": f"Invalid status filter: {status}",
                        "details": {
                            "provided": status,
                            "valid_values": valid_statuses
                        }
                    }
                }
            )

        # Convert status string to JobStatus enum if provided
        from open_source_risk_model.persistence.job_repo import JobStatus
        status_enum = None
        if status:
            status_enum = JobStatus(status)

        # List jobs
        jobs = job_repo.list_jobs(status=status_enum, limit=limit, offset=offset)

        # Get total count (for pagination)
        # Note: This is a simple implementation. For better performance with large datasets,
        # consider adding a count method to JobRepository
        total = len(jobs)

        return {
            "jobs": jobs,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to list jobs",
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to list jobs",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )


@app.get("/api/repos")
async def list_repos(
    limit: int = Query(100, description="Maximum number of results", ge=1, le=1000),
    offset: int = Query(0, description="Pagination offset", ge=0),
    older_than: Optional[str] = Query(None, description="ISO timestamp to filter repos updated before this time"),
):
    """
    List stored repositories with metadata.

    Returns a paginated list of repositories stored in the database with
    metadata including node counts, timestamps, and data sources.

    Args:
        limit: Maximum number of results (1-1000, default 100)
        offset: Pagination offset (default 0)
        older_than: Optional ISO timestamp to filter repos updated before this time

    Returns:
        List of repositories with metadata and pagination info

    Raises:
        HTTPException: 400 for invalid input, 500 for internal errors,
                      503 if database not available
    """
    try:
        # Check if graph repository is available
        if graph_repo is None:
            logger.error("Graph repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Repository service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Parse older_than timestamp if provided
        older_than_dt = None
        if older_than:
            try:
                older_than_dt = datetime.fromisoformat(older_than.replace('Z', '+00:00'))
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_TIMESTAMP",
                            "message": f"Invalid timestamp format: {older_than}",
                            "details": {
                                "provided": older_than,
                                "expected_format": "ISO 8601 (e.g., 2026-02-18T10:30:00Z)"
                            }
                        }
                    }
                )

        # List repositories
        repos = graph_repo.list_repos(limit=limit, offset=offset, older_than=older_than_dt)

        # Get total count
        total = graph_repo.get_repo_count()

        return {
            "repos": repos,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to list repos",
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to list repositories",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )



@app.get("/api/repos/by-maintainer/{username}")
async def find_repos_by_maintainer(
    username: str,
    limit: int = Query(100, description="Maximum number of results", ge=1, le=1000),
):
    """
    Find repositories by maintainer username.

    Returns all repositories maintained by the specified user, ordered by
    contribution fraction (highest first).

    Args:
        username: GitHub username
        limit: Maximum number of results (1-1000, default 100)

    Returns:
        List of repositories with contribution details

    Raises:
        HTTPException: 500 for internal errors, 503 if database not available
    """
    try:
        # Check if index repository is available
        if index_repo is None:
            logger.error("Index repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Repository service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Find repos by maintainer
        repos = index_repo.find_repos_by_maintainer(username=username, limit=limit)

        return {
            "maintainer": username,
            "repos": repos,
            "total": len(repos)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to find repos by maintainer",
            username=username,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to find repositories by maintainer",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )



@app.get("/api/repos/by-cve/{cve_id}")
async def find_repos_by_cve(
    cve_id: str,
    limit: int = Query(100, description="Maximum number of results", ge=1, le=1000),
):
    """
    Find repositories affected by a CVE.

    Returns all repositories affected by the specified CVE, ordered by
    CVSS score (highest first).

    Args:
        cve_id: CVE identifier (e.g., "CVE-2024-1234")
        limit: Maximum number of results (1-1000, default 100)

    Returns:
        List of repositories with severity and affected releases

    Raises:
        HTTPException: 500 for internal errors, 503 if database not available
    """
    try:
        # Check if index repository is available
        if index_repo is None:
            logger.error("Index repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Repository service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Find repos by CVE
        repos = index_repo.find_repos_by_cve(cve_id=cve_id, limit=limit)

        return {
            "cve_id": cve_id,
            "repos": repos,
            "total": len(repos)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to find repos by CVE",
            cve_id=cve_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to find repositories by CVE",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )



@app.get("/api/repos/by-package")
async def find_repo_by_package(
    registry: str = Query(..., description="Registry type (pypi, npm, maven, etc.)"),
    package: str = Query(..., description="Package name"),
):
    """
    Find repository by package name in a registry.

    Returns the repository associated with the specified package in the
    given registry.

    Args:
        registry: Registry type (pypi, npm, maven, etc.)
        package: Package name

    Returns:
        Repository information with package details, or 404 if not found

    Raises:
        HTTPException: 404 if not found, 500 for internal errors,
                      503 if database not available
    """
    try:
        # Check if index repository is available
        if index_repo is None:
            logger.error("Index repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Repository service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Find repo by package
        result = index_repo.find_repo_by_package(registry_type=registry, package_name=package)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "PACKAGE_NOT_FOUND",
                        "message": f"No repository found for package {registry}:{package}",
                        "details": {
                            "registry": registry,
                            "package": package
                        }
                    }
                }
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to find repo by package",
            registry=registry,
            package=package,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to find repository by package",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )



@app.delete("/api/repos/{repo_full_name:path}", status_code=204)
async def delete_repo(repo_full_name: str):
    """
    Delete a repository from the database.

    Removes the repository graph and all associated index entries
    (maintainers, CVEs, registries) from the database.

    Args:
        repo_full_name: Repository identifier (owner/repo)

    Returns:
        204 No Content on success

    Raises:
        HTTPException: 404 if repo not found, 500 for internal errors,
                      503 if database not available
    """
    try:
        # Check if graph repository is available
        if graph_repo is None:
            logger.error("Graph repository not available")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Repository service not available",
                        "details": {
                            "reason": "Database persistence is disabled or failed to initialize"
                        }
                    }
                }
            )

        # Delete the repository
        deleted = graph_repo.delete_graph(repo_full_name)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "REPO_NOT_FOUND",
                        "message": f"Repository {repo_full_name} not found",
                        "details": {
                            "repo_full_name": repo_full_name
                        }
                    }
                }
            )

        logger.info(
            "Deleted repository",
            repo_full_name=repo_full_name,
        )

        # Return 204 No Content (no response body)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete repo",
            repo_full_name=repo_full_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to delete repository",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )


# ============================================================================
# Dependency API Endpoints (Step 2: Dependency Graph)
# ============================================================================


@app.get("/api/repos/{owner}/{repo}/dependencies")
def get_repo_dependencies(
    owner: str,
    repo: str,
    include_dev: bool = Query(True, description="Include development dependencies"),
    include_optional: bool = Query(True, description="Include optional dependencies")
):
    """
    Get dependencies for a repository.
    
    Returns direct dependencies parsed from manifest files.
    
    Args:
        owner: Repository owner
        repo: Repository name
        include_dev: Include development dependencies
        include_optional: Include optional dependencies
    
    Returns:
        JSON response with dependencies list
    
    Raises:
        HTTPException: 503 if service unavailable, 404 if repo not found
    """
    if dependency_repo is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Dependency service not available",
                    "details": {
                        "reason": "Database persistence is disabled or failed to initialize"
                    }
                }
            }
        )
    
    repo_full_name = f"{owner}/{repo}"
    
    try:
        dependencies = dependency_repo.get_dependencies(
            repo_full_name,
            include_dev=include_dev,
            include_optional=include_optional
        )
        
        return {
            "repo": repo_full_name,
            "dependencies": dependencies,
            "total": len(dependencies),
            "metadata": {
                "include_dev": include_dev,
                "include_optional": include_optional,
                "transitive": False
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get dependencies for {repo_full_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to retrieve dependencies",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )


@app.get("/api/packages/{package}/dependents")
def get_package_dependents(
    package: str,
    registry: str = Query(..., description="Registry type (pypi, npm, maven, etc.)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Get repositories that depend on a package.
    
    Args:
        package: Package name
        registry: Registry type (pypi, npm, maven, etc.)
        limit: Maximum results
        offset: Pagination offset
    
    Returns:
        JSON response with dependents list
    
    Raises:
        HTTPException: 503 if service unavailable
    """
    if dependency_repo is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Dependency service not available",
                    "details": {
                        "reason": "Database persistence is disabled or failed to initialize"
                    }
                }
            }
        )
    
    try:
        result = dependency_repo.get_dependents(
            package_name=package,
            registry_type=registry,
            limit=limit,
            offset=offset
        )
        
        return {
            "package_name": package,
            "registry_type": registry,
            **result
        }
    
    except Exception as e:
        logger.error(f"Failed to get dependents for {package} ({registry}): {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to retrieve dependents",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )


# ============================================================================
# Dependency Tree API - Hierarchical Dependency Visualization
# ============================================================================

from open_source_risk_model.tree.service import TreeService
from open_source_risk_model.tree.exceptions import (
    RepositoryNotFoundError as TreeRepoNotFoundError,
    TreeConstructionTimeoutError,
    AllDependenciesFailedError,
)


@app.get("/repos/{repo_id:path}/dependency-tree", tags=["dependency-tree"])
async def get_dependency_tree(
    repo_id: str,
    max_depth: Optional[int] = Query(None, ge=1, le=10, description="Maximum tree depth (1-10)"),
    high_risk_only: bool = Query(False, description="Include only high-risk nodes and ancestors"),
    vulnerable_only: bool = Query(False, description="Include only vulnerable nodes and ancestors"),
    direct_only: bool = Query(False, description="Include only direct dependencies"),
    sort_by: Optional[str] = Query(None, description="Sort order: risk_score, name, vulnerability_count"),
    truncate_after_children: Optional[int] = Query(None, ge=1, description="Max children per node"),
):
    """Get dependency tree for a repository.

    Returns a hierarchical tree of dependencies enriched with risk metadata,
    summary metrics, and provenance information.

    The ``repo_id`` accepts ``owner/repo`` format (e.g. ``facebook/react``).
    """
    # Validate sort_by
    if sort_by is not None and sort_by not in ("risk_score", "name", "vulnerability_count"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_PARAMETER",
                    "message": f"Invalid sort_by value: '{sort_by}'. Must be one of: risk_score, name, vulnerability_count",
                }
            },
        )

    db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")
    service = TreeService(db_path=db_path)

    try:
        response = service.get_dependency_tree(
            repo_full_name=repo_id,
            max_depth=max_depth,
            high_risk_only=high_risk_only,
            vulnerable_only=vulnerable_only,
            direct_only=direct_only,
            sort_by=sort_by,
            truncate_after_children=truncate_after_children,
        )
        return response.to_dict()

    except TreeRepoNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": str(exc)}})

    except TreeConstructionTimeoutError as exc:
        raise HTTPException(status_code=503, detail={"error": {"code": "TIMEOUT", "message": str(exc)}})

    except AllDependenciesFailedError as exc:
        raise HTTPException(status_code=503, detail={"error": {"code": "ALL_DEPS_FAILED", "message": str(exc)}})

    except Exception as exc:
        logger.error(f"Unexpected error building dependency tree for {repo_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "INTERNAL_ERROR", "message": "Failed to build dependency tree"}},
        )


# ============================================================================
# Query API - Intent-Based Natural Language Queries
# ============================================================================

from pydantic import BaseModel, Field
from open_source_risk_model.query.intent_executor import IntentExecutor
from open_source_risk_model.query.intent_classifier import IntentClassifier
from open_source_risk_model.llm import create_provider_from_env, LLMClient, PromptManager


class QueryRequest(BaseModel):
    """Request for natural language query."""
    query: str = Field(..., description="Natural language query or explicit intent")
    intent: Optional[str] = Field(None, description="Explicit intent (dev mode)")
    parameters: Optional[Dict] = Field(None, description="Explicit parameters (dev mode)")
    max_results: int = Field(100, ge=1, le=1000, description="Maximum results to return")


class QueryResponse(BaseModel):
    """Response from query execution."""
    intent: str
    parameters: Dict
    confidence: Optional[float] = None
    results: list
    result_count: int
    execution_time_ms: float
    metadata: Optional[Dict] = None


# Initialize intent executor and classifier
intent_executor = IntentExecutor(db_path="data/graphs.db")
intent_classifier = None  # Lazy initialization (requires API key)


@app.post("/api/query", response_model=QueryResponse, tags=["query"])
async def query_dependencies(
    request: QueryRequest,
    request_obj: Request
) -> QueryResponse:
    """
    Execute natural language query against dependency graph.
    
    This endpoint supports two modes:
    
    1. **Dev Mode** (explicit intent): Provide `intent` and `parameters` directly
       ```json
       {
         "query": "List dependencies",
         "intent": "list_dependencies",
         "parameters": {"repo_full_name": "django/django"},
         "max_results": 10
       }
       ```
    
    2. **Production Mode** (LLM classification): Provide natural language `query`
       ```json
       {
         "query": "What are the dependencies of django/django?",
         "max_results": 10
       }
       ```
       (LLM classifier not yet implemented - returns error)
    
    **Available Intents:**
    - `list_dependencies`: List direct dependencies of a repo
    - `find_dependents`: Find repos that depend on a package
    - `get_dependency_tree`: Get dependency tree (BFS, max depth 5)
    - `check_resolution`: Check if package resolves to GitHub repo
    - `list_unresolved`: List unresolved dependencies
    - `list_manifests`: List manifest files for a repo
    - `count_by_manifest_type`: Count manifests by type
    - `repo_stats`: Get repository statistics
    - `dataset_stats`: Get overall dataset statistics
    - `search_repos`: Search repositories by name
    - `search_packages`: Search packages by name
    
    **Security:**
    - No SQL generation from user input
    - Strict intent allowlist
    - Parameterized queries only
    - No network calls in query execution
    
    Args:
        request: Query request with natural language or explicit intent
        request_obj: FastAPI request object for logging
    
    Returns:
        QueryResponse with results and metadata
    
    Raises:
        HTTPException: 400 for invalid requests, 500 for execution errors
    """
    request_id = generate_request_id()
    set_request_id(request_id)
    
    try:
        # Dev mode: Explicit intent provided
        if request.intent and request.parameters is not None:
            intent = request.intent
            parameters = request.parameters
            confidence = 1.0  # Explicit intent has 100% confidence
            
            logger.info(
                "Query (dev mode)",
                extra={
                    "intent": intent,
                    "parameters": parameters,
                    "query": request.query
                }
            )
        
        # Production mode: LLM classification
        else:
            # Lazy initialize classifier
            global intent_classifier
            if intent_classifier is None:
                try:
                    # Create LLM provider from environment
                    provider = create_provider_from_env()
                    
                    # Initialize prompt manager
                    prompts_dir = Path("src/open_source_risk_model/llm/prompts")
                    prompt_manager = PromptManager(prompts_dir)
                    
                    # Create LLM client
                    llm_client = LLMClient(provider, prompt_manager)
                    
                    # Initialize classifier with LLM client
                    intent_classifier = IntentClassifier(llm_client)
                except Exception as e:
                    logger.error(f"Failed to initialize intent classifier: {e}")
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": {
                                "code": "SERVICE_UNAVAILABLE",
                                "message": "Intent classifier not available",
                                "details": {
                                    "reason": str(e),
                                    "suggestion": "Ensure OPENAI_API_KEY is set in environment"
                                }
                            }
                        }
                    )
            
            # Classify query
            try:
                classification = intent_classifier.classify(request.query)
                
                if classification.intent == "unknown":
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": {
                                "code": "UNKNOWN_INTENT",
                                "message": "Could not classify query intent",
                                "details": {
                                    "query": request.query,
                                    "confidence": classification.confidence,
                                    "reasoning": classification.reasoning,
                                    "suggestion": "Try rephrasing your query or use one of the supported intents"
                                }
                            }
                        }
                    )
                
                intent = classification.intent
                parameters = classification.parameters
                confidence = classification.confidence
                
                logger.info(
                    "Query classified",
                    extra={
                        "query": request.query,
                        "intent": intent,
                        "confidence": confidence
                    }
                )
            
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "CLASSIFICATION_FAILED",
                            "message": "Failed to classify query",
                            "details": {
                                "error": str(e),
                                "query": request.query
                            }
                        }
                    }
                )
        
        # Execute intent
        result = intent_executor.execute(
            intent=intent,
            parameters=parameters,
            max_results=request.max_results
        )
        
        logger.info(
            "Query executed",
            extra={
                "intent": result.intent,
                "result_count": result.result_count,
                "execution_time_ms": result.execution_time_ms
            }
        )
        
        return QueryResponse(
            intent=result.intent,
            parameters=result.parameters,
            confidence=confidence,
            results=result.results,
            result_count=result.result_count,
            execution_time_ms=result.execution_time_ms,
            metadata=result.metadata
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions (don't catch them)
        raise
    
    except ValueError as e:
        # Invalid intent or parameters
        logger.warning(f"Invalid query: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_QUERY",
                    "message": str(e),
                    "details": {
                        "query": request.query,
                        "intent": request.intent if request.intent else "not provided"
                    }
                }
            }
        )
    
    except Exception as e:
        # Unexpected error
        logger.error(f"Query execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "EXECUTION_ERROR",
                    "message": "Query execution failed",
                    "details": {
                        "error": str(e)
                    }
                }
            }
        )
    
    finally:
        clear_request_id()


# ---------------------------------------------------------------------------
# Stats API
# ---------------------------------------------------------------------------


@app.get("/api/stats")
def get_stats():
    """Return dataset coverage statistics.

    Computes total repos, fully analyzed repos (present in both repo_graphs
    and repo_dependencies), and coverage ratio.
    """
    db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")

    try:
        conn = get_connection(db_path)
    except Exception:
        raise HTTPException(status_code=503, detail="Database is not available")

    try:
        cursor = conn.execute(
            "SELECT COUNT(DISTINCT repo_full_name) FROM repo_graphs"
        )
        total_repos = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(DISTINCT rg.repo_full_name) "
            "FROM repo_graphs rg "
            "INNER JOIN repo_dependencies rd ON rg.repo_full_name = rd.repo_full_name"
        )
        fully_analyzed_repos = cursor.fetchone()[0]

        if total_repos > 0:
            coverage_ratio = round(fully_analyzed_repos / total_repos, 2)
        else:
            coverage_ratio = 0.00

        return {
            "total_repos": total_repos,
            "fully_analyzed_repos": fully_analyzed_repos,
            "coverage_ratio": coverage_ratio,
        }
    except Exception as e:
        logger.error(f"Error computing stats: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database is not available")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Demo Repos API
# ---------------------------------------------------------------------------


@app.get("/api/demo-repos")
def get_demo_repos():
    """Return curated demo repos with live risk labels.

    Loads repos from demo_repos.yaml, validates against the database,
    and enriches each validated entry with a risk_label from
    compute_repo_insight. Invalid repos are excluded from the response.

    If the database is unavailable, returns all repos from YAML
    without enrichment (risk_label: null for all).
    """
    db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")

    # Always load the YAML config first
    try:
        config = load_demo_repos()
    except Exception as e:
        logger.error(f"Failed to load demo repos config: {e}", exc_info=True)
        return {"repos": []}

    # Try to validate and enrich from DB
    try:
        validated = validate_demo_repos(db_path)

        repos = []
        for demo in validated:
            owner, name = demo.repo.split("/", 1)
            risk_label = None
            try:
                gr = GraphRepository(db_path=db_path)
                insight = compute_repo_insight(demo.repo, gr)
                if insight.graph_signal_score is not None:
                    risk_label = insight.graph_signal_label
            except Exception:
                risk_label = None

            repos.append({
                "repo": demo.repo,
                "name": name,
                "owner": owner,
                "tags": demo.tags,
                "risk_label": risk_label,
            })

        return {"repos": repos}

    except Exception as e:
        # DB unavailable — fall back to YAML without enrichment
        logger.warning(
            f"DB unavailable for demo-repos validation, returning unenriched list: {e}"
        )
        repos = []
        for demo in config.repos:
            owner, name = demo.repo.split("/", 1)
            repos.append({
                "repo": demo.repo,
                "name": name,
                "owner": owner,
                "tags": demo.tags,
                "risk_label": None,
            })
        return {"repos": repos}


# ---------------------------------------------------------------------------
# Insights API
# ---------------------------------------------------------------------------


def _repo_exists_in_db(repo_full_name: str, db_path: str) -> bool:
    """Check whether a row exists in repo_graphs for the given repo.

    Uses a lightweight SELECT 1 query — does not load graph JSON.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT 1 FROM repo_graphs WHERE repo_full_name = ?",
            (repo_full_name,),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


@app.get("/api/insights/{owner}/{repo}")
def get_repo_insights(owner: str, repo: str):
    """Return computed insight for a repository (Req 9.1-9.5).

    Computes on demand. Does not persist results.
    """
    repo_full_name = f"{owner}/{repo}"

    try:
        if graph_repo is None:
            raise HTTPException(
                status_code=503,
                detail="Database is not available",
            )

        db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")

        if not _repo_exists_in_db(repo_full_name, db_path):
            raise HTTPException(
                status_code=404,
                detail=f"Repository {repo_full_name} not found",
            )

        insight = compute_repo_insight(repo_full_name, graph_repo)
        result = insight.to_dict()

        # Attach last-analysis timestamp from graph metadata
        try:
            with sqlite3.connect(db_path) as _conn:
                row = _conn.execute(
                    "SELECT updated_at FROM repo_graphs WHERE repo_full_name = ?",
                    (repo_full_name,),
                ).fetchone()
                if row and row[0]:
                    result["analyzed_at"] = row[0]
        except Exception:
            pass

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error computing insights for {repo_full_name}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error computing insights",
        )


@app.get("/api/insights")
def list_insights(
    sort_by: str = Query("score", description="Sort key: score, base_risk, cve_count, maintainer_fraction, release_staleness"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    label: Optional[str] = Query(None, description="Filter by graph_signal_label: HIGH, MEDIUM, LOW"),
    has_cves: Optional[bool] = Query(None, description="Filter repos with/without CVEs"),
    has_maintainer_risk: Optional[bool] = Query(None, description="Filter repos with/without maintainer risk (severity != info)"),
    has_stale_release: Optional[bool] = Query(None, description="Filter repos with/without stale releases (severity != info)"),
    min_score: Optional[float] = Query(None, description="Minimum graph_signal_score", ge=0.0, le=1.0),
    limit: int = Query(25, description="Max results to return", ge=1, le=500),
    offset: int = Query(0, description="Pagination offset", ge=0),
):
    """Cross-repo insight listing with filtering and sorting.

    Computes insights on the fly for all repos, applies filters,
    sorts, and returns a paginated lightweight summary.
    """
    try:
        if graph_repo is None:
            raise HTTPException(status_code=503, detail="Database is not available")

        repos = graph_repo.list_repos(limit=10000)
        all_insights = []
        for r in repos:
            name = r["repo_full_name"]
            try:
                insight = compute_repo_insight(name, graph_repo)
                all_insights.append(insight)
            except Exception:
                continue

        # --- helpers to pull signal metadata ---
        def _signal(insight, name):
            for s in insight.direct_signals:
                if s.signal_name == name:
                    return s
            return None

        # --- filter ---
        filtered = all_insights

        if label:
            filtered = [i for i in filtered if i.graph_signal_label == label.upper()]

        if has_cves is not None:
            if has_cves:
                filtered = [i for i in filtered if (_signal(i, "cve_risk") and _signal(i, "cve_risk").severity != "info")]
            else:
                filtered = [i for i in filtered if (not _signal(i, "cve_risk") or _signal(i, "cve_risk").severity == "info")]

        if has_maintainer_risk is not None:
            if has_maintainer_risk:
                filtered = [i for i in filtered if (_signal(i, "maintainer_concentration") and _signal(i, "maintainer_concentration").severity != "info")]
            else:
                filtered = [i for i in filtered if (not _signal(i, "maintainer_concentration") or _signal(i, "maintainer_concentration").severity == "info")]

        if has_stale_release is not None:
            if has_stale_release:
                filtered = [i for i in filtered if (_signal(i, "release_staleness") and _signal(i, "release_staleness").severity != "info")]
            else:
                filtered = [i for i in filtered if (not _signal(i, "release_staleness") or _signal(i, "release_staleness").severity == "info")]

        if min_score is not None:
            filtered = [i for i in filtered if i.graph_signal_score >= min_score]

        # --- sort ---
        sort_keys = {
            "score": lambda i: i.graph_signal_score,
            "base_risk": lambda i: i.base_maintenance_risk or 0.0,
            "cve_count": lambda i: (_signal(i, "cve_risk").metadata.get("total_count", 0) if _signal(i, "cve_risk") else 0),
            "maintainer_fraction": lambda i: (_signal(i, "maintainer_concentration").metadata.get("top_contributor_fraction", 0.0) if _signal(i, "maintainer_concentration") else 0.0),
            "release_staleness": lambda i: (_signal(i, "release_staleness").metadata.get("days_since_latest", 0) or 0 if _signal(i, "release_staleness") else 0),
        }
        key_fn = sort_keys.get(sort_by, sort_keys["score"])
        reverse = order.lower() != "asc"
        filtered.sort(key=key_fn, reverse=reverse)

        total = len(filtered)
        page = filtered[offset : offset + limit]

        # --- serialize lightweight items ---
        items = []
        for i in page:
            cve_s = _signal(i, "cve_risk")
            maint_s = _signal(i, "maintainer_concentration")
            rel_s = _signal(i, "release_staleness")
            items.append({
                "repo_full_name": i.repo_full_name,
                "graph_signal_score": round(i.graph_signal_score, 3),
                "graph_signal_label": i.graph_signal_label,
                "base_maintenance_risk": i.base_maintenance_risk,
                "base_maintenance_label": i.base_maintenance_label,
                "reasons": i.reasons,
                "signals": {
                    "has_cves": cve_s.severity != "info" if cve_s else False,
                    "cve_count": cve_s.metadata.get("total_count", 0) if cve_s else 0,
                    "maintainer_concentration": maint_s.severity if maint_s else "info",
                    "top_contributor": maint_s.metadata.get("top_contributor_username") if maint_s else None,
                    "top_contributor_fraction": round(maint_s.metadata.get("top_contributor_fraction", 0.0), 2) if maint_s else None,
                    "release_staleness": rel_s.severity if rel_s else "info",
                    "days_since_release": rel_s.metadata.get("days_since_latest") if rel_s else None,
                },
            })

        return {"total": total, "returned": len(items), "items": items}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error listing insights")


# ============================================================================
# Multi-Repo Scope Ingestion Endpoints
# ============================================================================


@app.post("/api/ingest-scope")
def ingest_scope(request: IngestScopeRequest):
    """Ingest multiple repos and optional dependencies into an analysis scope.

    Validates input, processes each repo synchronously through the existing
    score_repo / build_graph / compute_repo_insight pipeline, resolves
    dependencies, merges graphs, and returns a complete risk overview.

    Returns HTTP 200 with full results (synchronous, no polling).
    """
    repos = request.repos or []
    dependencies = request.dependencies or []

    # --- Validation ---
    if not repos and not dependencies:
        raise HTTPException(status_code=422, detail="At least one repo or dependency required")

    if len(repos) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 repos allowed (MVP performance constraint)")

    # Validate and normalize each repo name
    normalized_repos: List[str] = []
    for repo in repos:
        norm = _normalize_repo_name(repo)
        if not norm:
            raise HTTPException(status_code=422, detail=f"Invalid repo format: {repo}")
        normalized_repos.append(norm)

    # --- Create scope ---
    scope_id = _generate_scope_id()
    created_at = datetime.now(timezone.utc).isoformat()
    if scope_repo:
        scope_repo.save(scope_id, {
            "scope_id": scope_id,
            "name": request.name,
            "repos": normalized_repos,
            "dependencies": dependencies,
            "status": "processing",
            "created_at": created_at,
        })

    try:
        return _process_scope(scope_id, request.name, normalized_repos, dependencies, created_at)
    except HTTPException:
        raise  # Let validation errors through
    except Exception as e:
        # Absolute last resort — never let the endpoint crash
        logger.error(f"Unhandled error in ingest_scope for {scope_id}: {e}", exc_info=True)
        fallback = build_scope_response(
            scope_id=scope_id,
            name=request.name,
            status="failed",
            system_risk_summary={
                "total_repos": len(normalized_repos),
                "high_risk_repos": 0, "medium_risk_repos": 0, "low_risk_repos": 0,
                "total_unique_dependencies": 0, "dependencies_used_by_multiple_repos": 0,
                "high_risk_dependencies": 0, "vulnerable_dependencies": 0,
                "aggregate_risk_score": 0.0, "aggregate_label": "LOW",
                "system_summary": "Analysis failed due to an internal error.",
                "per_repo_results": [],
            },
            priority_risks=[],
            top_risk_drivers=[],
            top_risky_dependencies=[],
            graph={"nodes": [], "edges": []},
            errors={"_internal": str(e)},
        )
        if scope_repo:
            scope_repo.save(scope_id, {**fallback, "created_at": created_at})
        return fallback


def _process_scope(scope_id: str, name: str, normalized_repos: List[str], dependencies: List[str], created_at: str) -> dict:
    """Core processing logic for ingest_scope, extracted for error isolation."""
    # --- Process repos ---
    per_repo_results: List[dict] = []
    graphs: List[Tuple[str, Graph]] = []
    errors: Dict[str, str] = {}
    config = GraphConfig()

    for repo_name in normalized_repos:
        try:
            score_data = score_repo(repo_name)
            graph_obj = build_graph(repo_name, score_data, config)
            # Attempt to compute insight (best-effort, needs graph_repo)
            insight = None
            if graph_repo is not None:
                try:
                    insight = compute_repo_insight(repo_name, graph_repo)
                except Exception:
                    pass
            # Extract risk score from score_repo's nested response
            overall = score_data.get("overall", {}) if isinstance(score_data, dict) else {}
            risk_score = overall.get("maintenance_risk", 0) or 0
            risk_label = _risk_label_from_score(risk_score)
            per_repo_results.append({
                "repo": repo_name,
                "risk_score": risk_score,
                "risk_label": risk_label,
                "error": None,
            })
            graphs.append((repo_name, graph_obj))
        except Exception as e:
            error_msg = str(e)
            # Make error messages more user-friendly
            if "404" in error_msg or "Not Found" in error_msg:
                error_msg = f"Repository '{repo_name}' not found on GitHub"
            elif "403" in error_msg or "rate limit" in error_msg.lower():
                error_msg = f"GitHub API rate limit reached while processing '{repo_name}'"
            elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                error_msg = f"Network error while processing '{repo_name}'"
            per_repo_results.append({
                "repo": repo_name,
                "risk_score": None,
                "risk_label": None,
                "error": error_msg,
            })
            errors[repo_name] = error_msg

    # --- Process dependencies ---
    unmapped_nodes: List[dict] = []
    for dep in dependencies:
        resolution = resolve_dependency_input(dep)
        if resolution["mapped"]:
            mapped_repo = resolution["repo"]
            try:
                score_data = score_repo(mapped_repo)
                graph_obj = build_graph(mapped_repo, score_data, config)
                graphs.append((mapped_repo, graph_obj))
                # Add to per_repo_results if not already present
                already_present = any(r["repo"] == mapped_repo for r in per_repo_results)
                if not already_present:
                    overall = score_data.get("overall", {}) if isinstance(score_data, dict) else {}
                    risk_score = overall.get("maintenance_risk", 0) or 0
                    risk_label = _risk_label_from_score(risk_score)
                    per_repo_results.append({
                        "repo": mapped_repo,
                        "risk_score": risk_score,
                        "risk_label": risk_label,
                        "error": None,
                    })
            except Exception:
                pass  # Best-effort for dependencies
        else:
            unmapped_nodes.append({
                "id": f"pkg:{dep}",
                "type": "package",
                "label": dep,
            })

    # --- Aggregate results ---
    try:
        merged_graph = merge_graphs(graphs, unmapped_nodes)
        system_risk_summary = compute_system_risk_summary(per_repo_results, merged_graph)
        priority_risks = compute_priority_risks(per_repo_results, merged_graph)
        top_risky_deps = compute_top_risky_dependencies(merged_graph)
        status = compute_scope_status(per_repo_results)
        top_drivers = get_top_risk_drivers(per_repo_results, merged_graph)
        insight_statements = compute_insight_statements(system_risk_summary, per_repo_results, merged_graph)
    except Exception as e:
        # If aggregation fails, still return a valid response with what we have
        logger.error(f"Aggregation error for scope {scope_id}: {e}")
        merged_graph = {"nodes": [], "edges": []}
        system_risk_summary = compute_system_risk_summary(per_repo_results, merged_graph)
        priority_risks = []
        top_risky_deps = []
        status = "failed" if not any(r.get("error") is None for r in per_repo_results) else "partial"
        top_drivers = get_top_risk_drivers(per_repo_results, merged_graph)
        insight_statements = []
        errors["_aggregation"] = str(e)

    # --- Build and store response ---
    response = build_scope_response(
        scope_id=scope_id,
        name=name,
        status=status,
        system_risk_summary=system_risk_summary,
        priority_risks=priority_risks,
        top_risk_drivers=top_drivers,
        top_risky_dependencies=top_risky_deps,
        graph=merged_graph,
        errors=errors,
        insight_statements=insight_statements,
    )

    if scope_repo:
        scope_repo.save(scope_id, {**response, "created_at": created_at})

    return response


@app.get("/api/scope/{scope_id}")
def get_scope(scope_id: str):
    """Retrieve a previously created analysis scope by ID.

    Returns the full scope object from the in-memory store.
    Returns 404 if the scope_id is not found.
    """
    if scope_repo is None:
        raise HTTPException(status_code=503, detail="Scope service unavailable")
    scope = scope_repo.get(scope_id)
    if scope is None:
        raise HTTPException(status_code=404, detail=f"Scope not found: {scope_id}")
    return scope
