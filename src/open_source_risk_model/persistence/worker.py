"""
IngestionWorker implementation for background job processing.

Provides a polling-based worker that processes ingestion jobs from the database,
handling per-repo errors gracefully and tracking progress.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ..graph.builder import build_graph
from ..graph.schema import GraphConfig
from ..service.score_repo import score_repo
from .errors import DatabaseError
from .graph_repo import GraphRepository
from .job_repo import JobRepository, JobStatus

logger = logging.getLogger(__name__)


class IngestionWorker:
    """Background worker for processing ingestion jobs."""
    
    def __init__(
        self,
        job_repo: JobRepository,
        graph_repo: GraphRepository,
        poll_interval: int = 5
    ):
        """
        Initialize IngestionWorker.
        
        Args:
            job_repo: JobRepository instance for job management
            graph_repo: GraphRepository instance for graph storage
            poll_interval: Seconds between job queue polls (default: 5)
        """
        self.job_repo = job_repo
        self.graph_repo = graph_repo
        self.poll_interval = poll_interval
        self.running = False
    
    async def start(self) -> None:
        """
        Start the worker loop.
        
        Polls for pending jobs and processes them sequentially.
        Runs until stop() is called.
        """
        self.running = True
        logger.info("Ingestion worker started")
        
        while self.running:
            try:
                # Find pending jobs
                pending_jobs = self.job_repo.list_jobs(
                    status=JobStatus.PENDING,
                    limit=1
                )
                
                if pending_jobs:
                    # Get full job details (list_jobs doesn't include repo_list/config)
                    job_id = pending_jobs[0]["job_id"]
                    job = self.job_repo.get_job(job_id)
                    if job:
                        await self._process_job(job)
                else:
                    # No pending jobs, wait before polling again
                    await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
        
        logger.info("Ingestion worker stopped")
    
    def stop(self) -> None:
        """Stop the worker loop gracefully."""
        logger.info("Stopping ingestion worker...")
        self.running = False
    
    async def _process_job(self, job: Dict[str, Any]) -> None:
        """
        Process a single ingestion job.
        
        Processes all repositories in the job, handling per-repo errors
        gracefully. Updates job progress periodically and marks job as
        completed when done.
        
        Args:
            job: Job data dict from JobRepository
        """
        job_id = job["job_id"]
        repo_list = job["repo_list"]
        config_dict = job["config"]
        
        # Parse config
        if config_dict:
            config = GraphConfig(**config_dict)
        else:
            config = GraphConfig()
        
        logger.info(f"Processing job {job_id} with {len(repo_list)} repositories")
        
        # Mark job as running
        self.job_repo.update_job_status(
            job_id=job_id,
            status=JobStatus.RUNNING
        )
        
        processed = 0
        successful = 0
        failed = 0
        errors = []
        
        try:
            for repo_full_name in repo_list:
                try:
                    # Ingest repository
                    await self._ingest_repository(repo_full_name, config)
                    successful += 1
                    logger.debug(f"Successfully ingested {repo_full_name}")
                
                except Exception as e:
                    # Per-repo error handling - don't stop the job
                    failed += 1
                    error_entry = {
                        "repo": repo_full_name,
                        "error": str(e),
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }
                    errors.append(error_entry)
                    logger.warning(f"Failed to ingest {repo_full_name}: {e}")
                
                processed += 1
                
                # Update progress periodically (every 10 repos)
                if processed % 10 == 0:
                    self.job_repo.update_job_status(
                        job_id=job_id,
                        status=JobStatus.RUNNING,
                        processed=processed,
                        successful=successful,
                        failed=failed,
                        errors=errors
                    )
                    logger.info(
                        f"Job {job_id} progress: {processed}/{len(repo_list)} "
                        f"({successful} successful, {failed} failed)"
                    )
            
            # Mark job as completed
            self.job_repo.update_job_status(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                processed=processed,
                successful=successful,
                failed=failed,
                errors=errors
            )
            
            logger.info(
                f"Job {job_id} completed: {successful} successful, {failed} failed"
            )
        
        except Exception as e:
            # Job-level failure (infrastructure issue)
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            
            # Add job-level error to error list
            job_error = {
                "error": f"Job failed: {str(e)}",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            errors.append(job_error)
            
            # Mark job as failed
            self.job_repo.update_job_status(
                job_id=job_id,
                status=JobStatus.FAILED,
                processed=processed,
                successful=successful,
                failed=failed,
                errors=errors
            )
    
    async def _ingest_repository(
        self,
        repo_full_name: str,
        config: GraphConfig
    ) -> None:
        """
        Ingest a single repository.
        
        Scores the repository, builds the graph, and saves it to the database.
        
        Args:
            repo_full_name: Repository identifier (owner/repo)
            config: Graph configuration
        
        Raises:
            Exception: If ingestion fails (caught by _process_job)
        """
        start_time = time.time()
        
        # Score the repository
        # Note: score_repo is synchronous, so we run it in executor
        loop = asyncio.get_event_loop()
        score_data = await loop.run_in_executor(
            None,
            lambda: score_repo(repo_full_name, refresh=True)
        )
        
        # Build the graph (synchronous)
        graph = await loop.run_in_executor(
            None,
            lambda: build_graph(repo_full_name, score_data, config)
        )
        
        # Calculate generation time
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Save to database (synchronous)
        await loop.run_in_executor(
            None,
            lambda: self.graph_repo.save_graph(repo_full_name, graph, generation_time_ms)
        )
        
        logger.info(f"Ingested {repo_full_name} in {generation_time_ms}ms")
