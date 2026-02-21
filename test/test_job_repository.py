"""
Unit tests for JobRepository.

Tests specific examples and edge cases for job management:
- Job creation
- Status updates
- Progress tracking
- Filtering by status
- Error handling
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.open_source_risk_model.persistence.db import init_database
from src.open_source_risk_model.persistence.job_repo import JobRepository, JobStatus
from src.open_source_risk_model.persistence.errors import JobNotFoundError, DatabaseError


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        yield db_path


@pytest.fixture
def job_repo(temp_db):
    """Create a JobRepository instance."""
    return JobRepository(temp_db)


class TestJobCreation:
    """Tests for job creation."""
    
    def test_create_job_basic(self, job_repo):
        """Test creating a basic job."""
        repo_list = ["numpy/numpy", "pandas-dev/pandas"]
        job_id = job_repo.create_job(repo_list)
        
        assert job_id is not None
        assert len(job_id) == 36  # UUID format
        
        # Verify job was created
        job = job_repo.get_job(job_id)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["status"] == JobStatus.PENDING.value
        assert job["repo_list"] == repo_list
        assert job["total_repos"] == 2
        assert job["processed_repos"] == 0
        assert job["successful_repos"] == 0
        assert job["failed_repos"] == 0
        assert job["errors"] == []
        assert job["config"] is None
    
    def test_create_job_with_config(self, job_repo):
        """Test creating a job with configuration."""
        repo_list = ["numpy/numpy"]
        config = {
            "include_cves": True,
            "max_releases": 10,
            "max_maintainers": 5
        }
        
        job_id = job_repo.create_job(repo_list, config)
        job = job_repo.get_job(job_id)
        
        assert job["config"] == config
    
    def test_create_job_empty_list_raises_error(self, job_repo):
        """Test that creating a job with empty repo list raises error."""
        with pytest.raises(ValueError, match="repo_list cannot be empty"):
            job_repo.create_job([])
    
    def test_create_job_large_list(self, job_repo):
        """Test creating a job with large repository list."""
        repo_list = [f"owner{i}/repo{i}" for i in range(100)]
        job_id = job_repo.create_job(repo_list)
        
        job = job_repo.get_job(job_id)
        assert job["total_repos"] == 100
        assert len(job["repo_list"]) == 100


class TestJobRetrieval:
    """Tests for job retrieval."""
    
    def test_get_job_exists(self, job_repo):
        """Test retrieving an existing job."""
        repo_list = ["numpy/numpy"]
        job_id = job_repo.create_job(repo_list)
        
        job = job_repo.get_job(job_id)
        assert job is not None
        assert job["job_id"] == job_id
    
    def test_get_job_not_found(self, job_repo):
        """Test retrieving a non-existent job returns None."""
        job = job_repo.get_job("non-existent-id")
        assert job is None
    
    def test_get_job_all_fields(self, job_repo):
        """Test that get_job returns all expected fields."""
        repo_list = ["numpy/numpy"]
        config = {"include_cves": True}
        job_id = job_repo.create_job(repo_list, config)
        
        job = job_repo.get_job(job_id)
        
        # Verify all fields are present
        expected_fields = [
            "job_id", "status", "repo_list", "total_repos",
            "processed_repos", "successful_repos", "failed_repos",
            "errors", "created_at", "started_at", "completed_at", "config"
        ]
        for field in expected_fields:
            assert field in job


class TestStatusUpdates:
    """Tests for job status updates."""
    
    def test_update_status_to_running(self, job_repo):
        """Test updating job status to RUNNING sets started_at."""
        job_id = job_repo.create_job(["numpy/numpy"])
        
        job_repo.update_job_status(job_id, JobStatus.RUNNING)
        
        job = job_repo.get_job(job_id)
        assert job["status"] == JobStatus.RUNNING.value
        assert job["started_at"] is not None
        assert job["completed_at"] is None
    
    def test_update_status_to_completed(self, job_repo):
        """Test updating job status to COMPLETED sets completed_at."""
        job_id = job_repo.create_job(["numpy/numpy"])
        job_repo.update_job_status(job_id, JobStatus.RUNNING)
        job_repo.update_job_status(job_id, JobStatus.COMPLETED)
        
        job = job_repo.get_job(job_id)
        assert job["status"] == JobStatus.COMPLETED.value
        assert job["started_at"] is not None
        assert job["completed_at"] is not None
    
    def test_update_status_to_failed(self, job_repo):
        """Test updating job status to FAILED sets completed_at."""
        job_id = job_repo.create_job(["numpy/numpy"])
        job_repo.update_job_status(job_id, JobStatus.RUNNING)
        job_repo.update_job_status(job_id, JobStatus.FAILED)
        
        job = job_repo.get_job(job_id)
        assert job["status"] == JobStatus.FAILED.value
        assert job["completed_at"] is not None
    
    def test_update_status_to_interrupted(self, job_repo):
        """Test updating job status to INTERRUPTED sets completed_at."""
        job_id = job_repo.create_job(["numpy/numpy"])
        job_repo.update_job_status(job_id, JobStatus.RUNNING)
        job_repo.update_job_status(job_id, JobStatus.INTERRUPTED)
        
        job = job_repo.get_job(job_id)
        assert job["status"] == JobStatus.INTERRUPTED.value
        assert job["completed_at"] is not None
    
    def test_update_nonexistent_job_raises_error(self, job_repo):
        """Test updating a non-existent job raises JobNotFoundError."""
        with pytest.raises(JobNotFoundError):
            job_repo.update_job_status("non-existent-id", JobStatus.RUNNING)


class TestProgressTracking:
    """Tests for job progress tracking."""
    
    def test_update_progress_basic(self, job_repo):
        """Test updating job progress."""
        job_id = job_repo.create_job(["numpy/numpy", "pandas-dev/pandas"])
        
        job_repo.update_job_status(
            job_id,
            JobStatus.RUNNING,
            processed=1,
            successful=1,
            failed=0
        )
        
        job = job_repo.get_job(job_id)
        assert job["processed_repos"] == 1
        assert job["successful_repos"] == 1
        assert job["failed_repos"] == 0
    
    def test_update_progress_with_errors(self, job_repo):
        """Test updating job progress with errors."""
        job_id = job_repo.create_job(["numpy/numpy", "invalid/repo"])
        
        errors = [
            {
                "repo": "invalid/repo",
                "error": "Repository not found",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        job_repo.update_job_status(
            job_id,
            JobStatus.RUNNING,
            processed=2,
            successful=1,
            failed=1,
            errors=errors
        )
        
        job = job_repo.get_job(job_id)
        assert job["processed_repos"] == 2
        assert job["successful_repos"] == 1
        assert job["failed_repos"] == 1
        assert len(job["errors"]) == 1
        assert job["errors"][0]["repo"] == "invalid/repo"
    
    def test_update_progress_incrementally(self, job_repo):
        """Test updating progress multiple times."""
        job_id = job_repo.create_job([f"owner/repo{i}" for i in range(10)])
        
        job_repo.update_job_status(job_id, JobStatus.RUNNING)
        
        # Update progress incrementally
        for i in range(1, 11):
            job_repo.update_job_status(
                job_id,
                JobStatus.RUNNING,
                processed=i,
                successful=i,
                failed=0
            )
        
        job = job_repo.get_job(job_id)
        assert job["processed_repos"] == 10
        assert job["successful_repos"] == 10
        assert job["failed_repos"] == 0
    
    def test_update_progress_partial_fields(self, job_repo):
        """Test updating only some progress fields."""
        job_id = job_repo.create_job(["numpy/numpy"])
        
        # Update only processed count
        job_repo.update_job_status(
            job_id,
            JobStatus.RUNNING,
            processed=1
        )
        
        job = job_repo.get_job(job_id)
        assert job["processed_repos"] == 1
        assert job["successful_repos"] == 0  # Not updated
        assert job["failed_repos"] == 0  # Not updated


class TestJobListing:
    """Tests for listing jobs."""
    
    def test_list_jobs_empty(self, job_repo):
        """Test listing jobs when none exist."""
        jobs = job_repo.list_jobs()
        assert jobs == []
    
    def test_list_jobs_basic(self, job_repo):
        """Test listing all jobs."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_id2 = job_repo.create_job(["pandas-dev/pandas"])
        
        jobs = job_repo.list_jobs()
        assert len(jobs) == 2
        job_ids = {j["job_id"] for j in jobs}
        assert job_id1 in job_ids
        assert job_id2 in job_ids
    
    def test_list_jobs_ordered_by_created_at(self, job_repo):
        """Test that jobs are ordered by created_at descending."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_id2 = job_repo.create_job(["pandas-dev/pandas"])
        job_id3 = job_repo.create_job(["scikit-learn/scikit-learn"])
        
        jobs = job_repo.list_jobs()
        
        # Most recent first
        assert jobs[0]["job_id"] == job_id3
        assert jobs[1]["job_id"] == job_id2
        assert jobs[2]["job_id"] == job_id1


class TestStatusFiltering:
    """Tests for filtering jobs by status."""
    
    def test_filter_by_pending_status(self, job_repo):
        """Test filtering jobs by PENDING status."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_id2 = job_repo.create_job(["pandas-dev/pandas"])
        job_repo.update_job_status(job_id2, JobStatus.RUNNING)
        
        pending_jobs = job_repo.list_jobs(status=JobStatus.PENDING)
        assert len(pending_jobs) == 1
        assert pending_jobs[0]["job_id"] == job_id1
        assert pending_jobs[0]["status"] == JobStatus.PENDING.value
    
    def test_filter_by_running_status(self, job_repo):
        """Test filtering jobs by RUNNING status."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_id2 = job_repo.create_job(["pandas-dev/pandas"])
        job_repo.update_job_status(job_id1, JobStatus.RUNNING)
        
        running_jobs = job_repo.list_jobs(status=JobStatus.RUNNING)
        assert len(running_jobs) == 1
        assert running_jobs[0]["job_id"] == job_id1
        assert running_jobs[0]["status"] == JobStatus.RUNNING.value
    
    def test_filter_by_completed_status(self, job_repo):
        """Test filtering jobs by COMPLETED status."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_repo.update_job_status(job_id1, JobStatus.RUNNING)
        job_repo.update_job_status(job_id1, JobStatus.COMPLETED)
        
        job_id2 = job_repo.create_job(["pandas-dev/pandas"])
        
        completed_jobs = job_repo.list_jobs(status=JobStatus.COMPLETED)
        assert len(completed_jobs) == 1
        assert completed_jobs[0]["job_id"] == job_id1
    
    def test_filter_by_failed_status(self, job_repo):
        """Test filtering jobs by FAILED status."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_repo.update_job_status(job_id1, JobStatus.RUNNING)
        job_repo.update_job_status(job_id1, JobStatus.FAILED)
        
        failed_jobs = job_repo.list_jobs(status=JobStatus.FAILED)
        assert len(failed_jobs) == 1
        assert failed_jobs[0]["job_id"] == job_id1
    
    def test_filter_by_interrupted_status(self, job_repo):
        """Test filtering jobs by INTERRUPTED status."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_repo.update_job_status(job_id1, JobStatus.RUNNING)
        job_repo.update_job_status(job_id1, JobStatus.INTERRUPTED)
        
        interrupted_jobs = job_repo.list_jobs(status=JobStatus.INTERRUPTED)
        assert len(interrupted_jobs) == 1
        assert interrupted_jobs[0]["job_id"] == job_id1


class TestPagination:
    """Tests for job listing pagination."""
    
    def test_pagination_limit(self, job_repo):
        """Test limiting number of results."""
        for i in range(10):
            job_repo.create_job([f"owner/repo{i}"])
        
        jobs = job_repo.list_jobs(limit=5)
        assert len(jobs) == 5
    
    def test_pagination_offset(self, job_repo):
        """Test pagination with offset."""
        job_ids = []
        for i in range(10):
            job_id = job_repo.create_job([f"owner/repo{i}"])
            job_ids.append(job_id)
        
        # Get first page
        page1 = job_repo.list_jobs(limit=5, offset=0)
        assert len(page1) == 5
        
        # Get second page
        page2 = job_repo.list_jobs(limit=5, offset=5)
        assert len(page2) == 5
        
        # Verify no overlap
        page1_ids = {j["job_id"] for j in page1}
        page2_ids = {j["job_id"] for j in page2}
        assert len(page1_ids & page2_ids) == 0
    
    def test_pagination_with_filter(self, job_repo):
        """Test pagination with status filter."""
        for i in range(10):
            job_id = job_repo.create_job([f"owner/repo{i}"])
            if i % 2 == 0:
                job_repo.update_job_status(job_id, JobStatus.RUNNING)
        
        # Get pending jobs with pagination
        pending_jobs = job_repo.list_jobs(status=JobStatus.PENDING, limit=3)
        assert len(pending_jobs) == 3
        assert all(j["status"] == JobStatus.PENDING.value for j in pending_jobs)


class TestInterruptedJobs:
    """Tests for marking interrupted jobs."""
    
    def test_mark_interrupted_jobs_basic(self, job_repo):
        """Test marking running jobs as interrupted."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_id2 = job_repo.create_job(["pandas-dev/pandas"])
        
        job_repo.update_job_status(job_id1, JobStatus.RUNNING)
        job_repo.update_job_status(job_id2, JobStatus.RUNNING)
        
        count = job_repo.mark_interrupted_jobs()
        assert count == 2
        
        # Verify both jobs are interrupted
        job1 = job_repo.get_job(job_id1)
        job2 = job_repo.get_job(job_id2)
        assert job1["status"] == JobStatus.INTERRUPTED.value
        assert job2["status"] == JobStatus.INTERRUPTED.value
    
    def test_mark_interrupted_jobs_only_running(self, job_repo):
        """Test that only RUNNING jobs are marked as interrupted."""
        job_id1 = job_repo.create_job(["numpy/numpy"])
        job_id2 = job_repo.create_job(["pandas-dev/pandas"])
        job_id3 = job_repo.create_job(["scikit-learn/scikit-learn"])
        
        job_repo.update_job_status(job_id1, JobStatus.RUNNING)
        job_repo.update_job_status(job_id2, JobStatus.COMPLETED)
        # job_id3 stays PENDING
        
        count = job_repo.mark_interrupted_jobs()
        assert count == 1
        
        # Verify only running job was interrupted
        job1 = job_repo.get_job(job_id1)
        job2 = job_repo.get_job(job_id2)
        job3 = job_repo.get_job(job_id3)
        
        assert job1["status"] == JobStatus.INTERRUPTED.value
        assert job2["status"] == JobStatus.COMPLETED.value
        assert job3["status"] == JobStatus.PENDING.value
    
    def test_mark_interrupted_jobs_none_running(self, job_repo):
        """Test marking interrupted jobs when none are running."""
        job_id = job_repo.create_job(["numpy/numpy"])
        
        count = job_repo.mark_interrupted_jobs()
        assert count == 0
        
        # Verify job status unchanged
        job = job_repo.get_job(job_id)
        assert job["status"] == JobStatus.PENDING.value
    
    def test_mark_interrupted_jobs_sets_completed_at(self, job_repo):
        """Test that marking interrupted sets completed_at timestamp."""
        job_id = job_repo.create_job(["numpy/numpy"])
        job_repo.update_job_status(job_id, JobStatus.RUNNING)
        
        job_before = job_repo.get_job(job_id)
        assert job_before["completed_at"] is None
        
        job_repo.mark_interrupted_jobs()
        
        job_after = job_repo.get_job(job_id)
        assert job_after["completed_at"] is not None
