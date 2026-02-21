from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from open_source_risk_model.service.score_repo import score_repo
from open_source_risk_model.graph.builder import build_graph
from open_source_risk_model.graph.schema import GraphConfig
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

# For local dev (React/Next/etc.). Tighten later for prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for UI
# Serve the ui/ directory at /ui for the graph visualization HTML
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")
# Also mount at /static for any static assets referenced in the HTML
app.mount("/static", StaticFiles(directory="ui"), name="static_ui")


@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    global graph_repo, job_repo, index_repo, ingestion_worker, worker_task
    
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
            ingestion_worker = None
    else:
        logger.info("Database persistence disabled")
        graph_repo = None
        job_repo = None
        index_repo = None


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
from pydantic import BaseModel
from typing import List, Optional, Any


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
