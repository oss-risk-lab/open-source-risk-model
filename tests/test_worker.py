"""
Unit tests for IngestionWorker - simplified version.
"""

import asyncio
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from src.open_source_risk_model.graph.schema import Graph, Node, NodeType
from src.open_source_risk_model.persistence.db import init_database
from src.open_source_risk_model.persistence.graph_repo import GraphRepository
from src.open_source_risk_model.persistence.job_repo import JobRepository, JobStatus
from src.open_source_risk_model.persistence.worker import IngestionWorker
from src.open_source_risk_model.persistence.errors import DatabaseError


def run_async(coro):
    """Helper to run async functions in sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def create_mock_graph(repo_name):
    """Create a minimal valid graph for testing."""
    node = Node(
        id=f"repo:{repo_name}",
        type=NodeType.REPO,
        label=repo_name,
        metadata={"url": f"https://github.com/{repo_name}"},
        provenance={"source": "test", "fetched_at": "2026-02-20T00:00:00Z", "data_confidence": 1.0}
    )
    return Graph(
        nodes=[node],
        edges=[],
        metadata={"schema_version": "1.0", "data_sources": ["test"], "warnings": []}
    )


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        yield db_path


@pytest.fixture
def worker_components(temp_db):
    """Create worker components for testing."""
    job_repo = JobRepository(temp_db)
    graph_repo = GraphRepository(temp_db)
    worker = IngestionWorker(job_repo, graph_repo, poll_interval=1)
    return worker, job_repo, graph_repo


def test_single_repo_failure_doesnt_stop_job(worker_components):
    """Test that a single repo failure doesn't stop the entire job."""
    worker, job_repo, graph_repo = worker_components
    
    with patch('src.open_source_risk_model.persistence.worker.score_repo') as mock_score, \
         patch('src.open_source_risk_model.persistence.worker.build_graph') as mock_build:
        
        def score_side_effect(repo_name, refresh=False):
            if repo_name == "fail/repo":
                raise Exception("Repository not found")
            return {"repo": {"full_name": repo_name}}
        
        mock_score.side_effect = score_side_effect
        mock_build.return_value = create_mock_graph("success/repo")
        
        job_id = job_repo.create_job(["fail/repo", "success/repo"])
        job = job_repo.get_job(job_id)
        run_async(worker._process_job(job))
        
        final_job = job_repo.get_job(job_id)
        assert final_job["status"] == JobStatus.COMPLETED.value
        assert final_job["successful_repos"] == 1
        assert final_job["failed_repos"] == 1


def test_progress_tracking(worker_components):
    """Test that progress is tracked correctly."""
    worker, job_repo, graph_repo = worker_components
    
    with patch('src.open_source_risk_model.persistence.worker.score_repo') as mock_score, \
         patch('src.open_source_risk_model.persistence.worker.build_graph') as mock_build:
        
        mock_score.return_value = {"repo": {"full_name": "test/repo"}}
        mock_build.side_effect = lambda name, data, config: create_mock_graph(name)
        
        repos = [f"owner/repo{i}" for i in range(15)]
        job_id = job_repo.create_job(repos)
        job = job_repo.get_job(job_id)
        run_async(worker._process_job(job))
        
        final_job = job_repo.get_job(job_id)
        assert final_job["processed_repos"] == 15
        assert final_job["successful_repos"] == 15


def test_job_completion_with_mixed_results(worker_components):
    """Test that job completes even with some failures."""
    worker, job_repo, graph_repo = worker_components
    
    with patch('src.open_source_risk_model.persistence.worker.score_repo') as mock_score, \
         patch('src.open_source_risk_model.persistence.worker.build_graph') as mock_build:
        
        def score_side_effect(repo_name, refresh=False):
            if "fail" in repo_name:
                raise Exception("Failed")
            return {"repo": {"full_name": repo_name}}
        
        mock_score.side_effect = score_side_effect
        mock_build.side_effect = lambda name, data, config: create_mock_graph(name)
        
        repos = ["success/repo1", "fail/repo1", "success/repo2", "fail/repo2"]
        job_id = job_repo.create_job(repos)
        job = job_repo.get_job(job_id)
        run_async(worker._process_job(job))
        
        final_job = job_repo.get_job(job_id)
        assert final_job["status"] == JobStatus.COMPLETED.value
        assert final_job["successful_repos"] == 2
        assert final_job["failed_repos"] == 2


def test_graceful_shutdown(worker_components):
    """Test that worker stops gracefully."""
    worker, job_repo, graph_repo = worker_components
    worker.stop()
    assert not worker.running
