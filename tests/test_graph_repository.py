"""
Unit tests for GraphRepository.

Tests specific scenarios including:
- Transaction rollback on errors
- Cascade deletion
- Pagination
- Age-based filtering
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest

from src.open_source_risk_model.graph.schema import (
    Graph,
    Node,
    Edge,
    NodeType,
    EdgeType,
)
from src.open_source_risk_model.persistence.db import init_database
from src.open_source_risk_model.persistence.graph_repo import GraphRepository
from src.open_source_risk_model.persistence.errors import ValidationError, DatabaseError


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        yield db_path


@pytest.fixture
def sample_graph():
    """Create a sample valid graph for testing."""
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={"url": "https://github.com/test/repo"},
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    maintainer_node = Node(
        id="maintainer:testuser",
        type=NodeType.MAINTAINER,
        label="testuser",
        metadata={"username": "testuser", "contribution_fraction": 0.5, "commit_count": 100},
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    cve_node = Node(
        id="cve:CVE-2024-1234",
        type=NodeType.CVE,
        label="CVE-2024-1234",
        metadata={"cve_id": "CVE-2024-1234", "severity": "HIGH", "cvss_score": 7.5},
        provenance={"source": "osv", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 0.9}
    )
    
    release_node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={"tag_name": "v1.0.0", "published_at": datetime.now(timezone.utc).isoformat()},
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    registry_node = Node(
        id="registry:pypi:test-package",
        type=NodeType.REGISTRY,
        label="pypi:test-package",
        metadata={"registry_type": "pypi", "package_name": "test-package", "latest_version": "1.0.0"},
        provenance={"source": "heuristic", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 0.8}
    )
    
    edge1 = Edge(
        source="repo:test/repo",
        target="maintainer:testuser",
        relationship_type=EdgeType.MAINTAINED_BY,
        metadata={},
        provenance={"source": "github_api", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
    )
    
    edge2 = Edge(
        source="repo:test/repo",
        target="release:test/repo:v1.0.0",
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={},
        provenance={"source": "github_api", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
    )
    
    edge3 = Edge(
        source="release:test/repo:v1.0.0",
        target="cve:CVE-2024-1234",
        relationship_type=EdgeType.HAS_CVE,
        metadata={},
        provenance={"source": "osv", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 0.9}
    )
    
    edge4 = Edge(
        source="repo:test/repo",
        target="registry:pypi:test-package",
        relationship_type=EdgeType.PUBLISHED_AS,
        metadata={},
        provenance={"source": "heuristic", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 0.8}
    )
    
    return Graph(
        nodes=[repo_node, maintainer_node, cve_node, release_node, registry_node],
        edges=[edge1, edge2, edge3, edge4],
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api", "osv"],
            "warnings": []
        }
    )


def test_transaction_rollback_on_validation_error(temp_db, sample_graph):
    """Test that transaction rolls back when validation fails."""
    repo = GraphRepository(temp_db)
    
    # Save a valid graph first
    repo.save_graph("test/repo", sample_graph, 1000)
    
    # Create an invalid graph (no repo node)
    invalid_graph = Graph(
        nodes=[Node(
            id="maintainer:user",
            type=NodeType.MAINTAINER,
            label="user",
            metadata={"username": "user"},
            provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
        )],
        edges=[],
        metadata={"schema_version": "1.0", "data_sources": ["github_api"]}
    )
    
    # Attempt to save invalid graph should raise ValidationError
    with pytest.raises(ValidationError):
        repo.save_graph("test/invalid", invalid_graph, 1000)
    
    # Verify the invalid graph was not saved
    result = repo.get_graph("test/invalid")
    assert result is None
    
    # Verify the original graph is still intact
    result = repo.get_graph("test/repo")
    assert result is not None
    assert result["metadata"]["node_count"] == 5


def test_cascade_deletion(temp_db, sample_graph):
    """Test that deleting a graph also deletes index entries."""
    repo = GraphRepository(temp_db)
    
    # Save graph
    repo.save_graph("test/repo", sample_graph, 1000)
    
    # Verify indexes were created
    import sqlite3
    conn = sqlite3.connect(temp_db)
    
    # Check maintainer index
    cursor = conn.execute("SELECT COUNT(*) FROM repo_maintainers WHERE repo_full_name = ?", ("test/repo",))
    assert cursor.fetchone()[0] == 1
    
    # Check CVE index
    cursor = conn.execute("SELECT COUNT(*) FROM repo_cves WHERE repo_full_name = ?", ("test/repo",))
    assert cursor.fetchone()[0] == 1
    
    # Check registry index
    cursor = conn.execute("SELECT COUNT(*) FROM repo_registries WHERE repo_full_name = ?", ("test/repo",))
    assert cursor.fetchone()[0] == 1
    
    conn.close()
    
    # Delete the graph
    deleted = repo.delete_graph("test/repo")
    assert deleted is True
    
    # Verify graph is gone
    result = repo.get_graph("test/repo")
    assert result is None
    
    # Verify indexes were cascade deleted
    conn = sqlite3.connect(temp_db)
    
    cursor = conn.execute("SELECT COUNT(*) FROM repo_maintainers WHERE repo_full_name = ?", ("test/repo",))
    assert cursor.fetchone()[0] == 0
    
    cursor = conn.execute("SELECT COUNT(*) FROM repo_cves WHERE repo_full_name = ?", ("test/repo",))
    assert cursor.fetchone()[0] == 0
    
    cursor = conn.execute("SELECT COUNT(*) FROM repo_registries WHERE repo_full_name = ?", ("test/repo",))
    assert cursor.fetchone()[0] == 0
    
    conn.close()


def test_delete_nonexistent_graph(temp_db):
    """Test deleting a graph that doesn't exist returns False."""
    repo = GraphRepository(temp_db)
    
    deleted = repo.delete_graph("nonexistent/repo")
    assert deleted is False


def test_pagination(temp_db, sample_graph):
    """Test list_repos pagination."""
    repo = GraphRepository(temp_db)
    
    # Save multiple graphs
    for i in range(15):
        repo.save_graph(f"test/repo{i}", sample_graph, 1000 + i)
    
    # Test first page
    page1 = repo.list_repos(limit=5, offset=0)
    assert len(page1) == 5
    
    # Test second page
    page2 = repo.list_repos(limit=5, offset=5)
    assert len(page2) == 5
    
    # Test third page
    page3 = repo.list_repos(limit=5, offset=10)
    assert len(page3) == 5
    
    # Verify no overlap
    page1_names = {r["repo_full_name"] for r in page1}
    page2_names = {r["repo_full_name"] for r in page2}
    page3_names = {r["repo_full_name"] for r in page3}
    
    assert len(page1_names & page2_names) == 0
    assert len(page2_names & page3_names) == 0
    assert len(page1_names & page3_names) == 0
    
    # Verify total count
    total_count = repo.get_repo_count()
    assert total_count == 15


def test_age_based_filtering(temp_db):
    """Test filtering repos by age."""
    repo = GraphRepository(temp_db)
    
    # Create graphs with different timestamps
    old_graph = Graph(
        nodes=[Node(
            id="repo:old/repo",
            type=NodeType.REPO,
            label="old/repo",
            metadata={},
            provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
        )],
        edges=[],
        metadata={"schema_version": "1.0", "data_sources": ["github_api"]}
    )
    
    new_graph = Graph(
        nodes=[Node(
            id="repo:new/repo",
            type=NodeType.REPO,
            label="new/repo",
            metadata={},
            provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
        )],
        edges=[],
        metadata={"schema_version": "1.0", "data_sources": ["github_api"]}
    )
    
    # Save old graph
    repo.save_graph("old/repo", old_graph, 1000)
    
    # Manually update timestamp to make it old
    import sqlite3
    conn = sqlite3.connect(temp_db)
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn.execute("UPDATE repo_graphs SET updated_at = ? WHERE repo_full_name = ?", (old_timestamp, "old/repo"))
    conn.commit()
    conn.close()
    
    # Save new graph
    repo.save_graph("new/repo", new_graph, 1000)
    
    # Filter for repos older than 7 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    old_repos = repo.list_repos(older_than=cutoff)
    
    # Should only return the old repo
    assert len(old_repos) == 1
    assert old_repos[0]["repo_full_name"] == "old/repo"
    
    # Filter for repos older than 60 days (should return none)
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    very_old_repos = repo.list_repos(older_than=cutoff)
    assert len(very_old_repos) == 0


def test_get_repo_count(temp_db, sample_graph):
    """Test getting total repository count."""
    repo = GraphRepository(temp_db)
    
    # Initially empty
    assert repo.get_repo_count() == 0
    
    # Add some repos
    for i in range(5):
        repo.save_graph(f"test/repo{i}", sample_graph, 1000)
    
    assert repo.get_repo_count() == 5
    
    # Delete one
    repo.delete_graph("test/repo0")
    assert repo.get_repo_count() == 4


def test_index_population(temp_db, sample_graph):
    """Test that indexes are correctly populated from graph data."""
    repo = GraphRepository(temp_db)
    repo.save_graph("test/repo", sample_graph, 1000)
    
    import sqlite3
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    
    # Check maintainer index
    cursor = conn.execute("SELECT * FROM repo_maintainers WHERE repo_full_name = ?", ("test/repo",))
    maintainer = cursor.fetchone()
    assert maintainer is not None
    assert maintainer["maintainer_username"] == "testuser"
    assert maintainer["contribution_fraction"] == 0.5
    assert maintainer["commit_count"] == 100
    
    # Check CVE index
    cursor = conn.execute("SELECT * FROM repo_cves WHERE repo_full_name = ?", ("test/repo",))
    cve = cursor.fetchone()
    assert cve is not None
    assert cve["cve_id"] == "CVE-2024-1234"
    assert cve["severity"] == "HIGH"
    assert cve["cvss_score"] == 7.5
    # Check affected releases
    affected_releases = json.loads(cve["affected_releases"]) if cve["affected_releases"] else []
    assert "v1.0.0" in affected_releases
    
    # Check registry index
    cursor = conn.execute("SELECT * FROM repo_registries WHERE repo_full_name = ?", ("test/repo",))
    registry = cursor.fetchone()
    assert registry is not None
    assert registry["registry_type"] == "pypi"
    assert registry["package_name"] == "test-package"
    assert registry["latest_version"] == "1.0.0"
    
    conn.close()


def test_index_update_on_graph_update(temp_db, sample_graph):
    """Test that indexes are updated when graph is updated."""
    repo = GraphRepository(temp_db)
    
    # Save initial graph
    repo.save_graph("test/repo", sample_graph, 1000)
    
    # Create updated graph with different maintainer
    updated_graph = Graph(
        nodes=[
            Node(
                id="repo:test/repo",
                type=NodeType.REPO,
                label="test/repo",
                metadata={},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            ),
            Node(
                id="maintainer:newuser",
                type=NodeType.MAINTAINER,
                label="newuser",
                metadata={"username": "newuser", "contribution_fraction": 0.8, "commit_count": 200},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            )
        ],
        edges=[],
        metadata={"schema_version": "1.0", "data_sources": ["github_api"]}
    )
    
    # Update the graph
    repo.save_graph("test/repo", updated_graph, 2000)
    
    # Check that old maintainer is gone and new one is present
    import sqlite3
    conn = sqlite3.connect(temp_db)
    
    cursor = conn.execute("SELECT COUNT(*) FROM repo_maintainers WHERE repo_full_name = ? AND maintainer_username = ?", 
                         ("test/repo", "testuser"))
    assert cursor.fetchone()[0] == 0
    
    cursor = conn.execute("SELECT COUNT(*) FROM repo_maintainers WHERE repo_full_name = ? AND maintainer_username = ?", 
                         ("test/repo", "newuser"))
    assert cursor.fetchone()[0] == 1
    
    conn.close()
