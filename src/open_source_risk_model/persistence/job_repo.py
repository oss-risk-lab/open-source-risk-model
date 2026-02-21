"""
JobRepository implementation for managing ingestion job state.

Provides CRUD operations for job tracking, status updates, and progress monitoring.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .db import get_connection
from .errors import DatabaseError, JobNotFoundError

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class JobRepository:
    """Repository for ingestion job state management."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize JobRepository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
    
    def create_job(
        self,
        repo_list: List[str],
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new ingestion job.
        
        Generates a UUID for the job and stores it with PENDING status.
        
        Args:
            repo_list: List of repository identifiers
            config: Graph configuration for ingestion (optional)
        
        Returns:
            Job ID (UUID string)
        
        Raises:
            DatabaseError: If job creation fails
        """
        if not repo_list:
            raise ValueError("repo_list cannot be empty")
        
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        conn = get_connection(self.db_path)
        
        try:
            conn.execute("""
                INSERT INTO ingestion_jobs
                (job_id, status, repo_list, total_repos, processed_repos,
                 successful_repos, failed_repos, errors, created_at, config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                JobStatus.PENDING.value,
                json.dumps(repo_list),
                len(repo_list),
                0,
                0,
                0,
                None,
                now,
                json.dumps(config) if config else None
            ))
            
            conn.commit()
            logger.info(f"Created job {job_id} with {len(repo_list)} repositories")
            
            return job_id
        
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create job: {e}", exc_info=True)
            raise DatabaseError(f"Failed to create job: {e}")
        finally:
            conn.close()
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job details by ID.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Job data dict with all fields, or None if not found
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM ingestion_jobs WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Parse JSON fields
            repo_list = json.loads(row["repo_list"])
            errors = json.loads(row["errors"]) if row["errors"] else []
            config = json.loads(row["config"]) if row["config"] else None
            
            return {
                "job_id": row["job_id"],
                "status": row["status"],
                "repo_list": repo_list,
                "total_repos": row["total_repos"],
                "processed_repos": row["processed_repos"],
                "successful_repos": row["successful_repos"],
                "failed_repos": row["failed_repos"],
                "errors": errors,
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "config": config
            }
        
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to retrieve job: {e}")
        finally:
            conn.close()
    
    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        processed: Optional[int] = None,
        successful: Optional[int] = None,
        failed: Optional[int] = None,
        errors: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Update job status and progress.
        
        Updates the job record with new status and optional progress metrics.
        Automatically sets started_at when transitioning to RUNNING and
        completed_at when transitioning to terminal states.
        
        Args:
            job_id: Job identifier
            status: New status
            processed: Number of repos processed (optional)
            successful: Number of successful ingestions (optional)
            failed: Number of failed ingestions (optional)
            errors: List of error objects (optional)
        
        Raises:
            JobNotFoundError: If job_id does not exist
            DatabaseError: If update fails
        """
        conn = get_connection(self.db_path)
        
        try:
            # Build dynamic UPDATE query based on provided fields
            updates = ["status = ?"]
            params = [status.value]
            
            # Set started_at when transitioning to RUNNING
            if status == JobStatus.RUNNING:
                updates.append("started_at = ?")
                params.append(datetime.now(timezone.utc).isoformat())
            
            # Set completed_at when transitioning to terminal states
            if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.INTERRUPTED):
                updates.append("completed_at = ?")
                params.append(datetime.now(timezone.utc).isoformat())
            
            # Add optional progress fields
            if processed is not None:
                updates.append("processed_repos = ?")
                params.append(processed)
            
            if successful is not None:
                updates.append("successful_repos = ?")
                params.append(successful)
            
            if failed is not None:
                updates.append("failed_repos = ?")
                params.append(failed)
            
            if errors is not None:
                updates.append("errors = ?")
                params.append(json.dumps(errors))
            
            # Add job_id for WHERE clause
            params.append(job_id)
            
            # Execute update
            query = f"""
                UPDATE ingestion_jobs
                SET {', '.join(updates)}
                WHERE job_id = ?
            """
            
            cursor = conn.execute(query, params)
            conn.commit()
            
            if cursor.rowcount == 0:
                raise JobNotFoundError(f"Job {job_id} not found")
            
            logger.debug(f"Updated job {job_id} to status {status.value}")
        
        except JobNotFoundError:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update job {job_id}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to update job status: {e}")
        finally:
            conn.close()
    
    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List jobs with optional status filter.
        
        Args:
            status: Filter by status (optional)
            limit: Maximum results
            offset: Pagination offset
        
        Returns:
            List of job data dicts
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            # Build query with optional filter
            query = """
                SELECT job_id, status, total_repos, processed_repos,
                       successful_repos, failed_repos, created_at,
                       started_at, completed_at
                FROM ingestion_jobs
            """
            params = []
            
            if status:
                query += " WHERE status = ?"
                params.append(status.value)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                {
                    "job_id": row["job_id"],
                    "status": row["status"],
                    "total_repos": row["total_repos"],
                    "processed_repos": row["processed_repos"],
                    "successful_repos": row["successful_repos"],
                    "failed_repos": row["failed_repos"],
                    "created_at": row["created_at"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"]
                }
                for row in rows
            ]
        
        except Exception as e:
            logger.error(f"Failed to list jobs: {e}", exc_info=True)
            raise DatabaseError(f"Failed to list jobs: {e}")
        finally:
            conn.close()
    
    def mark_interrupted_jobs(self) -> int:
        """
        Mark all RUNNING jobs as INTERRUPTED.
        
        This should be called on application startup to handle jobs
        that were running when the server stopped.
        
        Returns:
            Number of jobs marked as interrupted
        
        Raises:
            DatabaseError: If update fails
        """
        conn = get_connection(self.db_path)
        
        try:
            cursor = conn.execute("""
                UPDATE ingestion_jobs
                SET status = ?, completed_at = ?
                WHERE status = ?
            """, (
                JobStatus.INTERRUPTED.value,
                datetime.now(timezone.utc).isoformat(),
                JobStatus.RUNNING.value
            ))
            
            conn.commit()
            count = cursor.rowcount
            
            if count > 0:
                logger.info(f"Marked {count} running jobs as interrupted")
            
            return count
        
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to mark interrupted jobs: {e}", exc_info=True)
            raise DatabaseError(f"Failed to mark interrupted jobs: {e}")
        finally:
            conn.close()
