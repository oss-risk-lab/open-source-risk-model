"""
Integration tests for cross-repo query API endpoints.

Tests the /api/repos endpoints with real database operations.
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from open_source_risk_model.graph.schema import Graph, Node, Edge, NodeType, EdgeType
from open_source_risk_model.persistence.db import init_database
from open_source_risk_model.persistence.graph_repo import GraphRepository
from open_source_risk_model.persistence.index_repo import IndexRepository


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        yield db_path


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    return Graph(
        nodes=[
            Node(
                id="repo:test/repo1",
                type=NodeType.REPO,
                label="test/repo1",
                metadata={"url": "https://github.com/test/repo1"},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            ),
            Node(
                id="maintainer:testuser",
                type=NodeType.MAINTAINER,
                label="testuser",
                metadata={"username": "testuser", "contribution_fraction": 0.5, "commit_count": 100},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            ),
            Node(
                id="cve:CVE-2024-1234",
                type=NodeType.CVE,
                label="CVE-2024-1234",
                metadata={"cve_id": "CVE-2024-1234", "severity": "HIGH", "cvss_score": 7.5},
                provenance={"source": "osv", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            ),
            Node(
                id="registry:pypi:test-package",
                type=NodeType.REGISTRY,
                label="test-package",
                metadata={"registry_type": "pypi", "package_name": "test-package", "latest_version": "1.0.0"},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            ),
        ],
        edges=[
            Edge(
                source="repo:test/repo1",
                target="maintainer:testuser",
                relationship_type=EdgeType.MAINTAINED_BY,
                metadata={},
                provenance={"source": "github_api", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
            ),
        ],
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api", "osv"],
            "warnings": []
        }
    )


def test_list_repos_with_pagination(temp_db, sample_graph):
    """Test /api/repos with pagination."""
    # Setup: Save multiple graphs
    graph_repo = GraphRepository(db_path=temp_db)
    
    for i in range(5):
        repo_name = f"test/repo{i}"
        graph_repo.save_graph(repo_name, sample_graph, generation_time_ms=1000)
    
    # Test: List repos with limit
    repos = graph_repo.list_repos(limit=3, offset=0)
    assert len(repos) == 3
    
    # Test: List repos with offset
    repos_page2 = graph_repo.list_repos(limit=3, offset=3)
    assert len(repos_page2) == 2
    
    # Verify no overlap
    repo_names_page1 = {r["repo_full_name"] for r in repos}
    repo_names_page2 = {r["repo_full_name"] for r in repos_page2}
    assert len(repo_names_page1 & repo_names_page2) == 0


def test_list_repos_with_age_filtering(temp_db, sample_graph):
    """Test /api/repos with age filtering."""
    graph_repo = GraphRepository(db_path=temp_db)
    
    # Save a graph
    graph_repo.save_graph("test/old-repo", sample_graph, generation_time_ms=1000)
    
    # Filter for repos older than now (should return the repo)
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    repos = graph_repo.list_repos(older_than=future_time)
    assert len(repos) == 1
    assert repos[0]["repo_full_name"] == "test/old-repo"
    
    # Filter for repos older than 1 hour ago (should return nothing)
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    repos = graph_repo.list_repos(older_than=past_time)
    assert len(repos) == 0


def test_find_repos_by_maintainer(temp_db, sample_graph):
    """Test /api/repos/by-maintainer."""
    graph_repo = GraphRepository(db_path=temp_db)
    index_repo = IndexRepository(db_path=temp_db)
    
    # Save graph with maintainer
    graph_repo.save_graph("test/repo1", sample_graph, generation_time_ms=1000)
    
    # Find repos by maintainer
    repos = index_repo.find_repos_by_maintainer("testuser")
    assert len(repos) == 1
    assert repos[0]["repo_full_name"] == "test/repo1"
    assert repos[0]["contribution_fraction"] == 0.5
    assert repos[0]["commit_count"] == 100


def test_find_repos_by_cve(temp_db, sample_graph):
    """Test /api/repos/by-cve."""
    graph_repo = GraphRepository(db_path=temp_db)
    index_repo = IndexRepository(db_path=temp_db)
    
    # Save graph with CVE
    graph_repo.save_graph("test/repo1", sample_graph, generation_time_ms=1000)
    
    # Find repos by CVE
    repos = index_repo.find_repos_by_cve("CVE-2024-1234")
    assert len(repos) == 1
    assert repos[0]["repo_full_name"] == "test/repo1"
    assert repos[0]["severity"] == "HIGH"
    assert repos[0]["cvss_score"] == 7.5


def test_find_repo_by_package(temp_db, sample_graph):
    """Test /api/repos/by-package."""
    graph_repo = GraphRepository(db_path=temp_db)
    index_repo = IndexRepository(db_path=temp_db)
    
    # Save graph with registry
    graph_repo.save_graph("test/repo1", sample_graph, generation_time_ms=1000)
    
    # Find repo by package
    result = index_repo.find_repo_by_package("pypi", "test-package")
    assert result is not None
    assert result["repo_full_name"] == "test/repo1"
    assert result["registry_type"] == "pypi"
    assert result["package_name"] == "test-package"
    assert result["latest_version"] == "1.0.0"


def test_delete_repo(temp_db, sample_graph):
    """Test DELETE /api/repos/{repo}."""
    graph_repo = GraphRepository(db_path=temp_db)
    index_repo = IndexRepository(db_path=temp_db)
    
    # Save graph
    graph_repo.save_graph("test/repo1", sample_graph, generation_time_ms=1000)
    
    # Verify it exists
    result = graph_repo.get_graph("test/repo1")
    assert result is not None
    
    # Verify indexes exist
    maintainers = index_repo.find_repos_by_maintainer("testuser")
    assert len(maintainers) == 1
    
    # Delete the repo
    deleted = graph_repo.delete_graph("test/repo1")
    assert deleted is True
    
    # Verify it's deleted
    result = graph_repo.get_graph("test/repo1")
    assert result is None
    
    # Verify indexes are deleted (cascade)
    maintainers = index_repo.find_repos_by_maintainer("testuser")
    assert len(maintainers) == 0


def test_delete_nonexistent_repo(temp_db):
    """Test DELETE /api/repos/{repo} for nonexistent repo."""
    graph_repo = GraphRepository(db_path=temp_db)
    
    # Try to delete nonexistent repo
    deleted = graph_repo.delete_graph("test/nonexistent")
    assert deleted is False


def test_cross_repo_query_with_multiple_repos(temp_db, sample_graph):
    """Test cross-repo queries with multiple repositories."""
    graph_repo = GraphRepository(db_path=temp_db)
    index_repo = IndexRepository(db_path=temp_db)
    
    # Save multiple graphs with the same maintainer
    for i in range(3):
        repo_name = f"test/repo{i}"
        graph_repo.save_graph(repo_name, sample_graph, generation_time_ms=1000)
    
    # Find all repos by maintainer
    repos = index_repo.find_repos_by_maintainer("testuser")
    assert len(repos) == 3
    
    # Verify all repos are returned
    repo_names = {r["repo_full_name"] for r in repos}
    assert repo_names == {"test/repo0", "test/repo1", "test/repo2"}
