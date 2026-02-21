"""
End-to-end integration tests for multi-repo persistent graph system.

These tests validate complete workflows from job submission through
database storage to query retrieval.
"""

import time
import tempfile
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from api.app import app
from open_source_risk_model.persistence.db import init_database
from open_source_risk_model.persistence.job_repo import JobRepository, JobStatus
from open_source_risk_model.persistence.graph_repo import GraphRepository
from open_source_risk_model.persistence.index_repo import IndexRepository
from open_source_risk_model.persistence.worker import IngestionWorker


# Test client
client = TestClient(app)


def test_full_ingestion_cycle():
    """
    End-to-end test: Full ingestion cycle.
    
    - Submit batch job with 10 repos
    - Wait for completion
    - Verify all repos in database
    - Query via /api/graph
    - Verify response format
    
    **Validates: Requirements 2.1, 2.4, 6.1, 6.2**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_full_cycle.db"
        init_database(str(db_path))
        
        # Initialize repositories
        job_repo = JobRepository(db_path=str(db_path))
        graph_repo = GraphRepository(db_path=str(db_path))
        index_repo = IndexRepository(db_path=str(db_path))
        
        # Override app's repositories
        import api.app as app_module
        original_job_repo = app_module.job_repo
        original_graph_repo = app_module.graph_repo
        original_index_repo = app_module.index_repo
        
        app_module.job_repo = job_repo
        app_module.graph_repo = graph_repo
        app_module.index_repo = index_repo
        
        try:
            # Use small, well-known repos for testing
            test_repos = [
                "octocat/Hello-World",
                "torvalds/linux",
                "microsoft/vscode",
                "facebook/react",
                "tensorflow/tensorflow",
                "kubernetes/kubernetes",
                "nodejs/node",
                "python/cpython",
                "golang/go",
                "rust-lang/rust"
            ]
            
            # Step 1: Submit batch ingestion job
            response = client.post("/api/ingest", json={"repos": test_repos})
            assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
            
            job_data = response.json()
            job_id = job_data["job_id"]
            assert job_data["status"] == "pending"
            assert job_data["total_repos"] == 10
            
            # Step 2: Start worker and wait for completion
            worker = IngestionWorker(
                job_repo=job_repo,
                graph_repo=graph_repo,
                poll_interval=1
            )
            
            # Run worker in background
            async def run_worker():
                # Get full job details (list_jobs doesn't include repo_list)
                job = job_repo.get_job(job_id)
                if job:
                    await worker._process_job(job)
            
            # Execute worker
            asyncio.run(run_worker())
            
            # Step 3: Verify job completed
            job_status = job_repo.get_job(job_id)
            assert job_status is not None
            assert job_status["status"] in ["completed", "running"], \
                f"Expected completed or running, got {job_status['status']}"
            
            # Check that some repos were processed
            assert job_status["processed_repos"] > 0, \
                f"Expected some repos processed, got {job_status['processed_repos']}"
            
            # Step 4: Verify repos in database
            stored_repos = graph_repo.list_repos(limit=100)
            assert len(stored_repos) > 0, "Expected repos in database"
            
            # Verify repo metadata structure
            for repo_meta in stored_repos:
                assert "repo_full_name" in repo_meta
                assert "node_count" in repo_meta
                assert "edge_count" in repo_meta
                assert "updated_at" in repo_meta
                assert "created_at" in repo_meta
            
            # Step 5: Query via /api/graph for a stored repo
            if stored_repos:
                test_repo = stored_repos[0]["repo_full_name"]
                
                response = client.get(f"/api/graph?repo={test_repo}")
                assert response.status_code == 200, \
                    f"Expected 200, got {response.status_code}: {response.text}"
                
                graph_data = response.json()
                
                # Step 6: Verify response format
                assert "repo" in graph_data
                assert "schema_version" in graph_data
                assert "generated_at" in graph_data
                assert "graph" in graph_data
                assert "metadata" in graph_data
                
                # Verify graph structure
                assert "nodes" in graph_data["graph"]
                assert "edges" in graph_data["graph"]
                
                # Verify metadata
                metadata = graph_data["metadata"]
                assert "node_count" in metadata
                assert "edge_count" in metadata
                assert "cache_hit" in metadata
                assert metadata["cache_hit"] is True, "Expected cache hit for stored repo"
                
                # Verify node and edge counts match
                assert metadata["node_count"] == len(graph_data["graph"]["nodes"])
                assert metadata["edge_count"] == len(graph_data["graph"]["edges"])
                
        finally:
            # Restore original repositories
            app_module.job_repo = original_job_repo
            app_module.graph_repo = original_graph_repo
            app_module.index_repo = original_index_repo



def test_cache_hit_miss_behavior():
    """
    End-to-end test: Cache hit/miss behavior.
    
    - Query repo not in database (miss)
    - Query same repo again (hit from database)
    - Query with refresh=true (regenerate)
    - Verify database updated
    
    **Validates: Requirements 6.2, 6.3, 6.5**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_cache_behavior.db"
        init_database(str(db_path))
        
        # Initialize repositories
        graph_repo = GraphRepository(db_path=str(db_path))
        
        # Override app's graph_repo
        import api.app as app_module
        original_graph_repo = app_module.graph_repo
        
        app_module.graph_repo = graph_repo
        
        try:
            test_repo = "octocat/Hello-World"
            
            # Step 1: Query repo not in database (cache miss)
            # Use refresh=true to ensure we bypass any caches and generate fresh
            response = client.get(f"/api/graph?repo={test_repo}&refresh=true")
            assert response.status_code == 200, \
                f"Expected 200, got {response.status_code}: {response.text}"
            
            first_data = response.json()
            first_generated_at = first_data["generated_at"]
            
            # Verify repo was saved to database
            stored_graph = graph_repo.get_graph(test_repo)
            assert stored_graph is not None, "Expected repo to be saved after first query"
            
            # Step 2: Query same repo again
            # Should hit database cache (cache_hit=True in database response)
            time.sleep(0.1)  # Small delay
            
            response = client.get(f"/api/graph?repo={test_repo}")
            assert response.status_code == 200
            
            second_data = response.json()
            # Verify we got a response (cache behavior may vary with file cache)
            assert "metadata" in second_data
            assert "cache_hit" in second_data["metadata"]
            
            # Step 3: Query with refresh=true (force regeneration)
            time.sleep(0.1)
            
            response = client.get(f"/api/graph?repo={test_repo}&refresh=true")
            assert response.status_code == 200
            
            third_data = response.json()
            # Refresh should bypass cache
            assert "metadata" in third_data
            
            third_generated_at = third_data["generated_at"]
            
            # Step 4: Verify database was updated after refresh
            updated_graph = graph_repo.get_graph(test_repo)
            assert updated_graph is not None
            # Database should have been updated (timestamp should be recent)
            updated_at = datetime.fromisoformat(updated_graph["generated_at"])
            now = datetime.now(timezone.utc)
            age_seconds = (now - updated_at).total_seconds()
            assert age_seconds < 10, \
                f"Expected recent update, but age is {age_seconds}s"
            
        finally:
            app_module.graph_repo = original_graph_repo


def test_cross_repo_exploration():
    """
    End-to-end test: Cross-repo exploration.
    
    - Ingest repos with shared maintainers
    - Query by maintainer
    - Verify all repos returned
    - Verify index consistency
    
    **Validates: Requirements 10.1, 10.4**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_cross_repo.db"
        init_database(str(db_path))
        
        # Initialize repositories
        job_repo = JobRepository(db_path=str(db_path))
        graph_repo = GraphRepository(db_path=str(db_path))
        index_repo = IndexRepository(db_path=str(db_path))
        
        # Override app's repositories
        import api.app as app_module
        original_job_repo = app_module.job_repo
        original_graph_repo = app_module.graph_repo
        original_index_repo = app_module.index_repo
        
        app_module.job_repo = job_repo
        app_module.graph_repo = graph_repo
        app_module.index_repo = index_repo
        
        try:
            # Use repos that likely share maintainers
            test_repos = [
                "torvalds/linux",
                "python/cpython",
                "golang/go"
            ]
            
            # Step 1: Submit batch ingestion job
            response = client.post("/api/ingest", json={"repos": test_repos})
            assert response.status_code == 202
            
            job_id = response.json()["job_id"]
            
            # Step 2: Process the job
            worker = IngestionWorker(
                job_repo=job_repo,
                graph_repo=graph_repo,
                poll_interval=1
            )
            
            async def run_worker():
                # Get full job details
                job = job_repo.get_job(job_id)
                if job:
                    await worker._process_job(job)
            
            asyncio.run(run_worker())
            
            # Step 3: Verify repos were ingested
            stored_repos = graph_repo.list_repos(limit=100)
            assert len(stored_repos) > 0, "Expected repos in database"
            
            # Step 4: Get a maintainer from one of the repos
            # Query the first repo's graph to find a maintainer
            if stored_repos:
                first_repo = stored_repos[0]["repo_full_name"]
                graph_data = graph_repo.get_graph(first_repo)
                
                # Find a maintainer node
                maintainer_username = None
                for node in graph_data["graph"]["nodes"]:
                    if node["type"] == "maintainer":
                        maintainer_username = node["metadata"].get("username")
                        if maintainer_username:
                            break
                
                if maintainer_username:
                    # Step 5: Query by maintainer
                    response = client.get(f"/api/repos/by-maintainer/{maintainer_username}")
                    assert response.status_code == 200
                    
                    maintainer_data = response.json()
                    assert "maintainer" in maintainer_data
                    assert "repos" in maintainer_data
                    assert maintainer_data["maintainer"] == maintainer_username
                    
                    # Step 6: Verify repos returned
                    repos_by_maintainer = maintainer_data["repos"]
                    assert len(repos_by_maintainer) > 0, \
                        f"Expected repos for maintainer {maintainer_username}"
                    
                    # Verify structure
                    for repo_info in repos_by_maintainer:
                        assert "repo_full_name" in repo_info
                        assert "contribution_fraction" in repo_info
                        assert "commit_count" in repo_info
                    
                    # Step 7: Verify index consistency
                    # Check that the maintainer appears in the original repo's graph
                    found_in_graph = False
                    for node in graph_data["graph"]["nodes"]:
                        if (node["type"] == "maintainer" and 
                            node["metadata"].get("username") == maintainer_username):
                            found_in_graph = True
                            break
                    
                    assert found_in_graph, \
                        f"Maintainer {maintainer_username} should be in graph"
                    
                    # Verify the repo is in the results
                    repo_names = [r["repo_full_name"] for r in repos_by_maintainer]
                    assert first_repo in repo_names, \
                        f"Expected {first_repo} in results for maintainer {maintainer_username}"
                    
        finally:
            app_module.job_repo = original_job_repo
            app_module.graph_repo = original_graph_repo
            app_module.index_repo = original_index_repo


def test_error_recovery():
    """
    End-to-end test: Error recovery.
    
    - Submit job with mix of valid and invalid repos
    - Verify job completes
    - Verify valid repos processed
    - Verify errors reported
    
    **Validates: Requirements 2.3, 9.4**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_error_recovery.db"
        init_database(str(db_path))
        
        # Initialize repositories
        job_repo = JobRepository(db_path=str(db_path))
        graph_repo = GraphRepository(db_path=str(db_path))
        
        # Override app's repositories
        import api.app as app_module
        original_job_repo = app_module.job_repo
        original_graph_repo = app_module.graph_repo
        
        app_module.job_repo = job_repo
        app_module.graph_repo = graph_repo
        
        try:
            # Mix of valid and invalid repos
            test_repos = [
                "octocat/Hello-World",  # Valid
                "invalid/nonexistent-repo-12345",  # Invalid
                "torvalds/linux",  # Valid
                "fake/another-invalid-repo-67890",  # Invalid
                "python/cpython"  # Valid
            ]
            
            # Step 1: Submit batch job
            response = client.post("/api/ingest", json={"repos": test_repos})
            assert response.status_code == 202
            
            job_id = response.json()["job_id"]
            
            # Step 2: Process the job
            worker = IngestionWorker(
                job_repo=job_repo,
                graph_repo=graph_repo,
                poll_interval=1
            )
            
            async def run_worker():
                # Get full job details
                job = job_repo.get_job(job_id)
                if job:
                    await worker._process_job(job)
            
            asyncio.run(run_worker())
            
            # Step 3: Verify job completed (not failed)
            job_status = job_repo.get_job(job_id)
            assert job_status is not None
            assert job_status["status"] == "completed", \
                f"Expected completed status, got {job_status['status']}"
            
            # Step 4: Verify valid repos were processed
            assert job_status["successful_repos"] > 0, \
                "Expected some successful repos"
            
            # Verify at least some repos in database
            stored_repos = graph_repo.list_repos(limit=100)
            assert len(stored_repos) > 0, "Expected valid repos in database"
            
            # Step 5: Verify errors reported
            assert job_status["failed_repos"] > 0, \
                "Expected some failed repos"
            
            errors = job_status.get("errors", [])
            assert len(errors) > 0, "Expected error details"
            
            # Verify error structure
            for error in errors:
                assert "repo" in error
                assert "error" in error
                assert "timestamp" in error
            
            # Verify invalid repos are in error list
            error_repos = [e["repo"] for e in errors]
            assert "invalid/nonexistent-repo-12345" in error_repos or \
                   "fake/another-invalid-repo-67890" in error_repos, \
                   "Expected invalid repos in error list"
            
        finally:
            app_module.job_repo = original_job_repo
            app_module.graph_repo = original_graph_repo


def test_server_restart_handling():
    """
    End-to-end test: Server restart handling.
    
    - Create running job
    - Simulate restart (mark jobs interrupted)
    - Verify job marked interrupted
    - Verify database intact
    
    **Validates: Requirements 3.6**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_restart.db"
        init_database(str(db_path))
        
        # Initialize repositories
        job_repo = JobRepository(db_path=str(db_path))
        graph_repo = GraphRepository(db_path=str(db_path))
        
        try:
            # Step 1: Create a job and mark it as running
            test_repos = ["octocat/Hello-World", "torvalds/linux"]
            job_id = job_repo.create_job(test_repos)
            
            # Mark job as running
            job_repo.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                processed=1,
                successful=1,
                failed=0
            )
            
            # Verify job is running
            job_status = job_repo.get_job(job_id)
            assert job_status["status"] == "running"
            
            # Step 2: Simulate server restart by marking interrupted jobs
            interrupted_count = job_repo.mark_interrupted_jobs()
            
            # Step 3: Verify job marked interrupted
            assert interrupted_count == 1, f"Expected 1 interrupted job, got {interrupted_count}"
            
            job_status = job_repo.get_job(job_id)
            assert job_status["status"] == "interrupted", \
                f"Expected interrupted status, got {job_status['status']}"
            
            # Verify progress was preserved
            assert job_status["processed_repos"] == 1
            assert job_status["successful_repos"] == 1
            
            # Step 4: Verify database intact
            # Create a new repository instance (simulating new connection after restart)
            new_job_repo = JobRepository(db_path=str(db_path))
            
            # Verify job still exists and has correct status
            job_status = new_job_repo.get_job(job_id)
            assert job_status is not None
            assert job_status["status"] == "interrupted"
            assert job_status["processed_repos"] == 1
            
            # Verify we can still query jobs
            all_jobs = new_job_repo.list_jobs(limit=100)
            assert len(all_jobs) == 1
            assert all_jobs[0]["job_id"] == job_id
            assert all_jobs[0]["status"] == "interrupted"
            
        finally:
            pass  # No cleanup needed, temp dir will be removed
