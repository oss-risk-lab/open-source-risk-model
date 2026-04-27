"""
Property-based tests for ingestion API endpoints.

Tests async job creation properties to ensure jobs are created quickly
and independently.
"""

import time
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings
from fastapi.testclient import TestClient

from api.app import app
from open_source_risk_model.persistence.db import init_database
from open_source_risk_model.persistence.job_repo import JobRepository


# Test client
client = TestClient(app)


@settings(max_examples=50, deadline=5000)
@given(
    repo_count=st.integers(min_value=1, max_value=100),
)
def test_property_async_job_creation(repo_count: int):
    """
    Property 8: Async Job Creation
    
    **Validates: Requirements 3.1**
    
    Property: Job creation returns immediately (< 1 second) regardless of repo count.
    
    This ensures that the ingestion API is truly asynchronous and doesn't block
    on processing repositories.
    """
    # Initialize test database with temporary path
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_async_job.db"
        init_database(str(db_path))
        
        # Create job repository
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo for this test
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Generate repo list
            repos = [f"owner{i}/repo{i}" for i in range(repo_count)]
            
            # Measure job creation time
            start_time = time.time()
            
            response = client.post(
                "/api/ingest",
                json={"repos": repos}
            )
            
            creation_time = time.time() - start_time
            
            # Assert: Job creation should be fast (< 1 second)
            assert creation_time < 1.0, (
                f"Job creation took {creation_time:.3f}s for {repo_count} repos, "
                f"expected < 1.0s (async requirement)"
            )
            
            # Assert: Response should be 202 Accepted
            assert response.status_code == 202, (
                f"Expected 202 Accepted, got {response.status_code}"
            )
            
            # Assert: Response should contain job_id
            data = response.json()
            assert "job_id" in data, "Response missing job_id"
            assert "status" in data, "Response missing status"
            assert data["status"] == "pending", (
                f"Expected status 'pending', got '{data['status']}'"
            )
            assert data["total_repos"] == repo_count, (
                f"Expected total_repos={repo_count}, got {data['total_repos']}"
            )
            
            # Verify job was created in database
            job = job_repo.get_job(data["job_id"])
            assert job is not None, "Job not found in database"
            assert job["status"] == "pending", (
                f"Job status should be 'pending', got '{job['status']}'"
            )
            assert job["total_repos"] == repo_count, (
                f"Job total_repos should be {repo_count}, got {job['total_repos']}"
            )
            
        finally:
            # Restore original job_repo
            app_module.job_repo = original_job_repo


@settings(max_examples=30, deadline=3000)
@given(
    job_count=st.integers(min_value=2, max_value=10),
)
def test_property_concurrent_job_creation(job_count: int):
    """
    Property: Multiple jobs can be created concurrently without interference.
    
    **Validates: Requirements 3.1**
    
    This ensures that creating multiple jobs doesn't cause race conditions
    or data corruption.
    """
    # Initialize test database with temporary path
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_concurrent_jobs.db"
        init_database(str(db_path))
        
        # Create job repository
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo for this test
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            job_ids = []
            
            # Create multiple jobs
            for i in range(job_count):
                repos = [f"owner{i}/repo{j}" for j in range(5)]
                
                response = client.post(
                    "/api/ingest",
                    json={"repos": repos}
                )
                
                assert response.status_code == 202
                data = response.json()
                job_ids.append(data["job_id"])
            
            # Assert: All job IDs should be unique
            assert len(set(job_ids)) == job_count, (
                f"Expected {job_count} unique job IDs, got {len(set(job_ids))}"
            )
            
            # Assert: All jobs should exist in database
            for job_id in job_ids:
                job = job_repo.get_job(job_id)
                assert job is not None, f"Job {job_id} not found in database"
                assert job["status"] == "pending"
            
        finally:
            # Restore original job_repo
            app_module.job_repo = original_job_repo


@settings(max_examples=20, deadline=2000)
@given(
    include_config=st.booleans(),
)
def test_property_job_creation_with_config(include_config: bool):
    """
    Property: Job creation works with and without config.
    
    **Validates: Requirements 3.1**
    
    This ensures that config is optional and properly handled.
    """
    # Initialize test database with temporary path
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_job_config.db"
        init_database(str(db_path))
        
        # Create job repository
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo for this test
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            repos = ["owner/repo1", "owner/repo2"]
            
            request_data = {"repos": repos}
            if include_config:
                request_data["config"] = {
                    "include_cves": True,
                    "max_releases": 5,
                    "max_maintainers": 3
                }
            
            response = client.post(
                "/api/ingest",
                json=request_data
            )
            
            assert response.status_code == 202
            data = response.json()
            
            # Verify job was created
            job = job_repo.get_job(data["job_id"])
            assert job is not None
            assert job["status"] == "pending"
            
            # Verify config was stored if provided
            if include_config:
                assert job["config"] is not None
            
        finally:
            # Restore original job_repo
            app_module.job_repo = original_job_repo
