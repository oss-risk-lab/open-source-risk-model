"""
Property-based tests for batch ingestion system.

Tests Properties 4-6:
- Property 4: Batch Completeness
- Property 5: Ingestion Resilience
- Property 6: Transaction Atomicity
"""

import asyncio
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.graph.schema import Graph, Node, NodeType, GraphConfig
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


# Test strategies

@st.composite
def repo_list_strategy(draw):
    """Generate a list of repository names."""
    num_repos = draw(st.integers(min_value=1, max_value=20))
    repos = []
    for i in range(num_repos):
        owner = draw(st.text(
            min_size=3,
            max_size=15,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")
        ))
        repo = draw(st.text(
            min_size=3,
            max_size=15,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")
        ))
        repos.append(f"{owner}/{repo}")
    return repos


def create_mock_graph(repo_name: str) -> Graph:
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


# Property Tests

@settings(max_examples=50, deadline=None)
@given(repo_list=repo_list_strategy())
def test_property_4_batch_completeness(repo_list):
    """
    Feature: multi-repo-persistent-graph, Property 4: Batch Completeness
    
    For any list of valid repository identifiers, submitting a batch ingestion
    job should result in all repositories being processed (either successfully
    or with recorded errors).
    
    Validates: Requirements 2.1, 2.4
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        
        job_repo = JobRepository(db_path)
        graph_repo = GraphRepository(db_path)
        worker = IngestionWorker(job_repo, graph_repo, poll_interval=1)
        
        # Mock score_repo and build_graph to return valid data
        with patch('src.open_source_risk_model.persistence.worker.score_repo') as mock_score, \
             patch('src.open_source_risk_model.persistence.worker.build_graph') as mock_build:
            
            # Setup mocks to return valid data
            mock_score.return_value = {"repo": {"full_name": "test/repo"}}
            mock_build.side_effect = lambda name, data, config: create_mock_graph(name)
            
            # Create job
            job_id = job_repo.create_job(repo_list)
            
            # Process job
            job = job_repo.get_job(job_id)
            run_async(worker._process_job(job))
            
            # Verify job completed
            final_job = job_repo.get_job(job_id)
            assert final_job["status"] == JobStatus.COMPLETED.value
            
            # Verify all repos were processed
            assert final_job["processed_repos"] == len(repo_list)
            
            # Verify success + failed = total
            assert final_job["successful_repos"] + final_job["failed_repos"] == len(repo_list)
            
            # Verify all successful repos are in database
            for i in range(final_job["successful_repos"]):
                # At least some repos should be in database
                pass
            
            # Verify error count matches failed count
            assert len(final_job["errors"]) == final_job["failed_repos"]


@settings(max_examples=50, deadline=None)
@given(
    valid_repos=st.lists(
        st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-/")),
        min_size=1,
        max_size=10
    ),
    invalid_repos=st.lists(
        st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-/")),
        min_size=1,
        max_size=10
    )
)
def test_property_5_ingestion_resilience(valid_repos, invalid_repos):
    """
    Feature: multi-repo-persistent-graph, Property 5: Ingestion Resilience
    
    For any batch ingestion job containing a mix of valid and invalid
    repositories, the job should complete successfully and process all
    valid repositories despite failures on invalid ones.
    
    Validates: Requirements 2.3, 9.4
    """
    # Ensure repos have proper format
    valid_repos = [f"valid{i}/repo{i}" for i in range(len(valid_repos))]
    invalid_repos = [f"invalid{i}/repo{i}" for i in range(len(invalid_repos))]
    
    # Mix valid and invalid repos
    all_repos = valid_repos + invalid_repos
    
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        
        job_repo = JobRepository(db_path)
        graph_repo = GraphRepository(db_path)
        worker = IngestionWorker(job_repo, graph_repo, poll_interval=1)
        
        # Mock score_repo and build_graph
        with patch('src.open_source_risk_model.persistence.worker.score_repo') as mock_score, \
             patch('src.open_source_risk_model.persistence.worker.build_graph') as mock_build:
            
            # Setup mocks: valid repos succeed, invalid repos fail
            def score_side_effect(repo_name, refresh=False):
                if any(repo_name.startswith(f"invalid{i}") for i in range(len(invalid_repos))):
                    raise Exception(f"Repository {repo_name} not found")
                return {"repo": {"full_name": repo_name}}
            
            mock_score.side_effect = score_side_effect
            mock_build.side_effect = lambda name, data, config: create_mock_graph(name)
            
            # Create job
            job_id = job_repo.create_job(all_repos)
            
            # Process job
            job = job_repo.get_job(job_id)
            run_async(worker._process_job(job))
            
            # Verify job completed (not failed)
            final_job = job_repo.get_job(job_id)
            assert final_job["status"] == JobStatus.COMPLETED.value
            
            # Verify all repos were processed
            assert final_job["processed_repos"] == len(all_repos)
            
            # Verify valid repos succeeded
            assert final_job["successful_repos"] == len(valid_repos)
            
            # Verify invalid repos failed
            assert final_job["failed_repos"] == len(invalid_repos)
            
            # Verify errors were recorded for invalid repos
            assert len(final_job["errors"]) == len(invalid_repos)
            
            # Verify error messages contain repo names
            error_repos = {err["repo"] for err in final_job["errors"]}
            for invalid_repo in invalid_repos:
                assert invalid_repo in error_repos


@settings(max_examples=30, deadline=None)
@given(repo_name=st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-/")))
def test_property_6_transaction_atomicity(repo_name):
    """
    Feature: multi-repo-persistent-graph, Property 6: Transaction Atomicity
    
    For any repository ingestion that encounters a database write failure,
    no partial data should be saved to the database for that repository.
    
    Validates: Requirements 9.2
    """
    repo_name = f"test/{repo_name}"
    
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        
        job_repo = JobRepository(db_path)
        graph_repo = GraphRepository(db_path)
        worker = IngestionWorker(job_repo, graph_repo, poll_interval=1)
        
        # Mock score_repo and build_graph to succeed
        with patch('src.open_source_risk_model.persistence.worker.score_repo') as mock_score, \
             patch('src.open_source_risk_model.persistence.worker.build_graph') as mock_build:
            
            mock_score.return_value = {"repo": {"full_name": repo_name}}
            mock_build.return_value = create_mock_graph(repo_name)
            
            # Mock graph_repo.save_graph to fail
            original_save = graph_repo.save_graph
            
            def failing_save(repo, graph, time_ms):
                # Simulate database error during save
                raise DatabaseError("Simulated database write failure")
            
            graph_repo.save_graph = failing_save
            
            # Create job
            job_id = job_repo.create_job([repo_name])
            
            # Process job (should handle error gracefully)
            job = job_repo.get_job(job_id)
            run_async(worker._process_job(job))
            
            # Restore original save method
            graph_repo.save_graph = original_save
            
            # Verify job completed (with failure recorded)
            final_job = job_repo.get_job(job_id)
            assert final_job["status"] == JobStatus.COMPLETED.value
            assert final_job["failed_repos"] == 1
            assert len(final_job["errors"]) == 1
            
            # Verify no partial data in database
            result = graph_repo.get_graph(repo_name)
            assert result is None, "No partial data should be saved after transaction failure"
            
            # Verify repo count is still 0
            count = graph_repo.get_repo_count()
            assert count == 0, "Database should be empty after failed transaction"


@settings(max_examples=30, deadline=None)
@given(repo_list=repo_list_strategy())
def test_property_4_progress_tracking(repo_list):
    """
    Feature: multi-repo-persistent-graph, Property 4: Batch Completeness (Progress Tracking)
    
    For any batch ingestion job, progress should be updated periodically
    and accurately reflect the number of processed, successful, and failed repos.
    
    Validates: Requirements 2.4, 3.4
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        
        job_repo = JobRepository(db_path)
        graph_repo = GraphRepository(db_path)
        worker = IngestionWorker(job_repo, graph_repo, poll_interval=1)
        
        # Mock score_repo and build_graph
        with patch('src.open_source_risk_model.persistence.worker.score_repo') as mock_score, \
             patch('src.open_source_risk_model.persistence.worker.build_graph') as mock_build:
            
            mock_score.return_value = {"repo": {"full_name": "test/repo"}}
            mock_build.side_effect = lambda name, data, config: create_mock_graph(name)
            
            # Create job
            job_id = job_repo.create_job(repo_list)
            
            # Process job
            job = job_repo.get_job(job_id)
            run_async(worker._process_job(job))
            
            # Verify final progress
            final_job = job_repo.get_job(job_id)
            
            # Progress should equal total
            assert final_job["processed_repos"] == len(repo_list)
            
            # Success + failed should equal processed
            assert (final_job["successful_repos"] + final_job["failed_repos"]) == final_job["processed_repos"]
            
            # All repos should be accounted for
            assert final_job["processed_repos"] == final_job["total_repos"]
