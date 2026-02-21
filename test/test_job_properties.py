"""
Property-based tests for job management system.

Tests Properties 7-8:
- Property 7: Job State Persistence
- Property 8: Async Job Creation
"""

import os
import tempfile
import time
from datetime import datetime, timezone

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.persistence.db import init_database
from src.open_source_risk_model.persistence.job_repo import JobRepository, JobStatus


# Test strategies for generating job data

@st.composite
def repo_list_strategy(draw):
    """Generate a list of repository names."""
    num_repos = draw(st.integers(min_value=1, max_value=50))
    repos = []
    for _ in range(num_repos):
        owner = draw(st.text(
            min_size=3,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")
        ))
        repo = draw(st.text(
            min_size=3,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")
        ))
        repos.append(f"{owner}/{repo}")
    return repos


@st.composite
def job_config_strategy(draw):
    """Generate a job configuration dict."""
    return {
        "include_cves": draw(st.booleans()),
        "max_releases": draw(st.integers(min_value=1, max_value=50)),
        "max_maintainers": draw(st.integers(min_value=1, max_value=20)),
    }


@st.composite
def progress_update_strategy(draw):
    """Generate progress update values."""
    total = draw(st.integers(min_value=1, max_value=100))
    processed = draw(st.integers(min_value=0, max_value=total))
    successful = draw(st.integers(min_value=0, max_value=processed))
    failed = processed - successful
    
    return {
        "total": total,
        "processed": processed,
        "successful": successful,
        "failed": failed,
    }


# Property Tests

@settings(max_examples=100, deadline=None)
@given(
    repo_list=repo_list_strategy(),
    config=st.one_of(st.none(), job_config_strategy()),
    status_sequence=st.lists(
        st.sampled_from([JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED]),
        min_size=1,
        max_size=3
    )
)
def test_property_7_job_state_persistence(repo_list, config, status_sequence):
    """
    Feature: multi-repo-persistent-graph, Property 7: Job State Persistence
    
    For any ingestion job, the job status, progress, and results should be
    persisted in the database and retrievable via job ID at any time,
    including after server restarts.
    
    Validates: Requirements 3.2, 3.3, 3.4, 3.6
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        
        # Create job with first connection
        job_repo1 = JobRepository(db_path)
        job_id = job_repo1.create_job(repo_list, config)
        
        # Verify job was created
        assert job_id is not None
        assert len(job_id) > 0
        
        # Get initial job state
        job = job_repo1.get_job(job_id)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["status"] == JobStatus.PENDING.value
        assert job["repo_list"] == repo_list
        assert job["total_repos"] == len(repo_list)
        assert job["processed_repos"] == 0
        assert job["successful_repos"] == 0
        assert job["failed_repos"] == 0
        assert job["errors"] == []
        assert job["created_at"] is not None
        assert job["started_at"] is None
        assert job["completed_at"] is None
        assert job["config"] == config
        
        # Update job through status sequence
        for i, status in enumerate(status_sequence):
            processed = min(i + 1, len(repo_list))
            successful = processed - (i % 2)  # Some failures
            failed = processed - successful
            errors = [
                {"repo": f"test/repo{j}", "error": "Test error", "timestamp": datetime.now(timezone.utc).isoformat()}
                for j in range(failed)
            ]
            
            job_repo1.update_job_status(
                job_id=job_id,
                status=status,
                processed=processed,
                successful=successful,
                failed=failed,
                errors=errors
            )
            
            # Verify update was persisted
            job = job_repo1.get_job(job_id)
            assert job["status"] == status.value
            assert job["processed_repos"] == processed
            assert job["successful_repos"] == successful
            assert job["failed_repos"] == failed
            assert len(job["errors"]) == failed
            
            # Verify timestamps are set appropriately
            if status == JobStatus.RUNNING:
                assert job["started_at"] is not None
            
            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                assert job["completed_at"] is not None
        
        # Close connection by deleting repository object (simulate restart)
        final_status = status_sequence[-1]
        del job_repo1
        
        # Create new connection (simulating server restart)
        job_repo2 = JobRepository(db_path)
        
        # Verify job state persisted across restart
        job_after_restart = job_repo2.get_job(job_id)
        assert job_after_restart is not None
        assert job_after_restart["job_id"] == job_id
        assert job_after_restart["status"] == final_status.value
        assert job_after_restart["repo_list"] == repo_list
        assert job_after_restart["total_repos"] == len(repo_list)
        assert job_after_restart["config"] == config
        
        # Verify all progress data persisted
        assert job_after_restart["processed_repos"] == job["processed_repos"]
        assert job_after_restart["successful_repos"] == job["successful_repos"]
        assert job_after_restart["failed_repos"] == job["failed_repos"]
        assert job_after_restart["errors"] == job["errors"]
        
        # Verify timestamps persisted
        assert job_after_restart["created_at"] == job["created_at"]
        assert job_after_restart["started_at"] == job["started_at"]
        assert job_after_restart["completed_at"] == job["completed_at"]


@settings(max_examples=100, deadline=None)
@given(
    repo_lists=st.lists(repo_list_strategy(), min_size=1, max_size=10),
    configs=st.lists(st.one_of(st.none(), job_config_strategy()), min_size=1, max_size=10)
)
def test_property_8_async_job_creation(repo_lists, configs):
    """
    Feature: multi-repo-persistent-graph, Property 8: Async Job Creation
    
    For any batch ingestion request, the system should return a job ID
    immediately without waiting for ingestion to complete.
    
    Validates: Requirements 3.1
    """
    # Ensure lists are same length
    num_jobs = min(len(repo_lists), len(configs))
    repo_lists = repo_lists[:num_jobs]
    configs = configs[:num_jobs]
    
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        job_repo = JobRepository(db_path)
        
        # Create multiple jobs and measure time
        job_ids = []
        start_time = time.time()
        
        for repo_list, config in zip(repo_lists, configs):
            job_id = job_repo.create_job(repo_list, config)
            job_ids.append(job_id)
        
        elapsed_time = time.time() - start_time
        
        # Verify all jobs were created
        assert len(job_ids) == num_jobs
        assert len(set(job_ids)) == num_jobs  # All unique
        
        # Verify job creation was fast (< 1 second per job on average)
        # This validates async behavior - we're not waiting for processing
        avg_time_per_job = elapsed_time / num_jobs
        assert avg_time_per_job < 1.0, f"Job creation took {avg_time_per_job:.3f}s per job (should be < 1s)"
        
        # Verify all jobs are in PENDING status (not started yet)
        for job_id in job_ids:
            job = job_repo.get_job(job_id)
            assert job is not None
            assert job["status"] == JobStatus.PENDING.value
            assert job["started_at"] is None
            assert job["completed_at"] is None
            assert job["processed_repos"] == 0
        
        # Verify jobs can be listed
        all_jobs = job_repo.list_jobs()
        assert len(all_jobs) >= num_jobs
        
        # Verify filtering by status works
        pending_jobs = job_repo.list_jobs(status=JobStatus.PENDING)
        pending_job_ids = {j["job_id"] for j in pending_jobs}
        assert all(job_id in pending_job_ids for job_id in job_ids)


@settings(max_examples=50, deadline=None)
@given(
    repo_list=repo_list_strategy(),
    config=st.one_of(st.none(), job_config_strategy())
)
def test_property_7_interrupted_jobs_handling(repo_list, config):
    """
    Feature: multi-repo-persistent-graph, Property 7: Job State Persistence (Interrupted Jobs)
    
    For any job that is RUNNING when the server restarts, the system should
    mark it as INTERRUPTED and preserve its state.
    
    Validates: Requirements 3.6
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        job_repo = JobRepository(db_path)
        
        # Create job and start it
        job_id = job_repo.create_job(repo_list, config)
        job_repo.update_job_status(
            job_id=job_id,
            status=JobStatus.RUNNING,
            processed=5,
            successful=4,
            failed=1
        )
        
        # Verify job is running
        job = job_repo.get_job(job_id)
        assert job["status"] == JobStatus.RUNNING.value
        assert job["started_at"] is not None
        assert job["completed_at"] is None
        
        # Simulate server restart by marking interrupted jobs
        interrupted_count = job_repo.mark_interrupted_jobs()
        assert interrupted_count == 1
        
        # Verify job is now interrupted
        job_after = job_repo.get_job(job_id)
        assert job_after["status"] == JobStatus.INTERRUPTED.value
        assert job_after["completed_at"] is not None
        
        # Verify progress was preserved
        assert job_after["processed_repos"] == 5
        assert job_after["successful_repos"] == 4
        assert job_after["failed_repos"] == 1
        
        # Verify job can be queried by interrupted status
        interrupted_jobs = job_repo.list_jobs(status=JobStatus.INTERRUPTED)
        assert any(j["job_id"] == job_id for j in interrupted_jobs)
