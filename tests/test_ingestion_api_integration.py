"""
Integration tests for ingestion API endpoints.

Tests the complete ingestion workflow including job creation, status tracking,
and batch processing.
"""

import time
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from api.app import app
from open_source_risk_model.persistence.db import init_database
from open_source_risk_model.persistence.job_repo import JobRepository
from open_source_risk_model.persistence.graph_repo import GraphRepository


# Test client
client = TestClient(app)


def test_job_creation_returns_quickly():
    """
    Test that job creation returns quickly (< 1 second).
    
    **Validates: Requirements 3.1**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_quick_creation.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Create a job with 50 repos
            repos = [f"owner/repo{i}" for i in range(50)]
            
            start_time = time.time()
            response = client.post("/api/ingest", json={"repos": repos})
            creation_time = time.time() - start_time
            
            assert response.status_code == 202
            assert creation_time < 1.0, f"Job creation took {creation_time:.3f}s, expected < 1.0s"
            
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "pending"
            assert data["total_repos"] == 50
            
        finally:
            app_module.job_repo = original_job_repo


def test_job_status_tracking():
    """
    Test that job status can be queried and tracked.
    
    **Validates: Requirements 3.2, 3.4**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_status_tracking.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Create a job
            repos = ["owner/repo1", "owner/repo2"]
            response = client.post("/api/ingest", json={"repos": repos})
            assert response.status_code == 202
            
            job_id = response.json()["job_id"]
            
            # Query job status
            status_response = client.get(f"/api/jobs/{job_id}")
            assert status_response.status_code == 200
            
            status_data = status_response.json()
            assert status_data["job_id"] == job_id
            assert status_data["status"] == "pending"
            assert status_data["total_repos"] == 2
            assert status_data["processed_repos"] == 0
            assert status_data["successful_repos"] == 0
            assert status_data["failed_repos"] == 0
            
            # Manually update job status to simulate processing
            from open_source_risk_model.persistence.job_repo import JobStatus
            job_repo.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                processed=1,
                successful=1,
                failed=0
            )
            
            # Query again
            status_response = client.get(f"/api/jobs/{job_id}")
            assert status_response.status_code == 200
            
            status_data = status_response.json()
            assert status_data["status"] == "running"
            assert status_data["processed_repos"] == 1
            assert status_data["successful_repos"] == 1
            
        finally:
            app_module.job_repo = original_job_repo


def test_job_list_filtering():
    """
    Test that jobs can be listed and filtered by status.
    
    **Validates: Requirements 3.1, 3.2**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_list_filtering.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Create multiple jobs
            job_ids = []
            for i in range(3):
                response = client.post("/api/ingest", json={"repos": [f"owner/repo{i}"]})
                assert response.status_code == 202
                job_ids.append(response.json()["job_id"])
            
            # Update one job to running
            from open_source_risk_model.persistence.job_repo import JobStatus
            job_repo.update_job_status(job_ids[0], status=JobStatus.RUNNING)
            
            # Update one job to completed
            job_repo.update_job_status(job_ids[1], status=JobStatus.COMPLETED)
            
            # List all jobs
            response = client.get("/api/jobs")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 3
            
            # Filter by pending status
            response = client.get("/api/jobs?status=pending")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["status"] == "pending"
            
            # Filter by running status
            response = client.get("/api/jobs?status=running")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["status"] == "running"
            
            # Filter by completed status
            response = client.get("/api/jobs?status=completed")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["status"] == "completed"
            
        finally:
            app_module.job_repo = original_job_repo


def test_job_not_found():
    """
    Test that querying a non-existent job returns 404.
    
    **Validates: Requirements 3.2**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_not_found.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Query non-existent job
            response = client.get("/api/jobs/nonexistent-job-id")
            assert response.status_code == 404
            
            data = response.json()
            assert "detail" in data
            assert "error" in data["detail"]
            assert data["detail"]["error"]["code"] == "JOB_NOT_FOUND"
            
        finally:
            app_module.job_repo = original_job_repo


def test_empty_repo_list_validation():
    """
    Test that empty repo list is rejected.
    
    **Validates: Requirements 2.5**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_validation.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Try to create job with empty repo list
            response = client.post("/api/ingest", json={"repos": []})
            assert response.status_code == 400
            
            data = response.json()
            assert "detail" in data
            assert "error" in data["detail"]
            assert data["detail"]["error"]["code"] == "INVALID_REQUEST"
            
        finally:
            app_module.job_repo = original_job_repo


def test_max_repo_limit_validation():
    """
    Test that repo list exceeding 1000 is rejected.
    
    **Validates: Requirements 2.5**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_max_limit.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Try to create job with 1001 repos
            repos = [f"owner/repo{i}" for i in range(1001)]
            response = client.post("/api/ingest", json={"repos": repos})
            assert response.status_code == 400
            
            data = response.json()
            assert "detail" in data
            assert "error" in data["detail"]
            assert data["detail"]["error"]["code"] == "INVALID_REQUEST"
            assert "1000" in data["detail"]["error"]["message"]
            
        finally:
            app_module.job_repo = original_job_repo


def test_invalid_config_validation():
    """
    Test that invalid config is rejected.
    
    **Validates: Requirements 3.1**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_invalid_config.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Try to create job with invalid config (unknown field)
            response = client.post(
                "/api/ingest",
                json={
                    "repos": ["owner/repo"],
                    "config": {
                        "invalid_field": "value"  # Unknown field
                    }
                }
            )
            # GraphConfig should reject unknown fields
            assert response.status_code == 400
            
            data = response.json()
            assert "detail" in data
            assert "error" in data["detail"]
            assert data["detail"]["error"]["code"] == "INVALID_CONFIG"
            
        finally:
            app_module.job_repo = original_job_repo


def test_pagination():
    """
    Test that job list pagination works correctly.
    
    **Validates: Requirements 8.3**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_pagination.db"
        init_database(str(db_path))
        
        job_repo = JobRepository(db_path=str(db_path))
        
        # Override app's job_repo
        import api.app as app_module
        original_job_repo = app_module.job_repo
        app_module.job_repo = job_repo
        
        try:
            # Create 5 jobs
            for i in range(5):
                response = client.post("/api/ingest", json={"repos": [f"owner/repo{i}"]})
                assert response.status_code == 202
            
            # Get first page (limit=2)
            response = client.get("/api/jobs?limit=2&offset=0")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 2
            assert data["limit"] == 2
            assert data["offset"] == 0
            
            # Get second page
            response = client.get("/api/jobs?limit=2&offset=2")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 2
            assert data["offset"] == 2
            
            # Get third page
            response = client.get("/api/jobs?limit=2&offset=4")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 1  # Only 1 job left
            
        finally:
            app_module.job_repo = original_job_repo


def test_service_unavailable_when_db_disabled():
    """
    Test that endpoints return 503 when database is disabled.
    
    **Validates: Requirements 9.3**
    """
    # Override app's job_repo to None (simulating disabled database)
    import api.app as app_module
    original_job_repo = app_module.job_repo
    app_module.job_repo = None
    
    try:
        # Try to create job
        response = client.post("/api/ingest", json={"repos": ["owner/repo"]})
        assert response.status_code == 503
        
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "SERVICE_UNAVAILABLE"
        
        # Try to get job status
        response = client.get("/api/jobs/some-job-id")
        assert response.status_code == 503
        
        # Try to list jobs
        response = client.get("/api/jobs")
        assert response.status_code == 503
        
    finally:
        app_module.job_repo = original_job_repo
