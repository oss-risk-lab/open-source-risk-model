"""
Unit tests for GraphRepository validation behavior.

Tests that invalid graphs are rejected during save operations.
Validates Requirements 9.5.
"""

import os
import tempfile
from datetime import datetime, timezone

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
from src.open_source_risk_model.persistence.errors import ValidationError


def test_invalid_graph_rejection_missing_fields():
    """
    Test invalid graph rejection (missing fields).
    
    Validates: Requirements 9.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Create graph with node missing provenance fields
        node = Node(
            id="repo:test/repo",
            type=NodeType.REPO,
            label="test/repo",
            metadata={"url": "https://github.com/test/repo"},
            provenance={}  # Missing required fields
        )
        
        graph = Graph(
            nodes=[node],
            edges=[],
            metadata={"schema_version": "1.0"}
        )
        
        # Attempt to save should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            repo.save_graph("test/repo", graph, 100)
        
        # Verify error message mentions missing provenance
        assert "provenance" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        
        # Verify no data was stored
        retrieved = repo.get_graph("test/repo")
        assert retrieved is None


def test_invalid_graph_rejection_orphaned_edges():
    """
    Test invalid graph rejection (orphaned edges).
    
    Validates: Requirements 9.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Create graph with edge referencing non-existent node
        node = Node(
            id="repo:test/repo",
            type=NodeType.REPO,
            label="test/repo",
            metadata={"url": "https://github.com/test/repo"},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        edge = Edge(
            source="repo:test/repo",
            target="nonexistent:node",  # This node doesn't exist
            relationship_type=EdgeType.HAS_RELEASE,
            metadata={},
            provenance={
                "source": "github_api",
                "established_at": datetime.now(timezone.utc).isoformat(),
                "confidence": 1.0
            }
        )
        
        graph = Graph(
            nodes=[node],
            edges=[edge],
            metadata={"schema_version": "1.0"}
        )
        
        # Attempt to save should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            repo.save_graph("test/repo", graph, 100)
        
        # Verify error message mentions invalid reference
        assert "invalid" in str(exc_info.value).lower() and "target" in str(exc_info.value).lower()
        
        # Verify no data was stored
        retrieved = repo.get_graph("test/repo")
        assert retrieved is None


def test_invalid_graph_rejection_duplicate_ids():
    """
    Test invalid graph rejection (duplicate IDs).
    
    Validates: Requirements 9.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Create graph with duplicate node IDs
        node1 = Node(
            id="repo:test/repo",
            type=NodeType.REPO,
            label="test/repo",
            metadata={"url": "https://github.com/test/repo"},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        node2 = Node(
            id="repo:test/repo",  # Duplicate ID
            type=NodeType.RELEASE,
            label="v1.0.0",
            metadata={},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        graph = Graph(
            nodes=[node1, node2],
            edges=[],
            metadata={"schema_version": "1.0"}
        )
        
        # Attempt to save should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            repo.save_graph("test/repo", graph, 100)
        
        # Verify error message mentions duplicate IDs
        assert "duplicate" in str(exc_info.value).lower()
        
        # Verify no data was stored
        retrieved = repo.get_graph("test/repo")
        assert retrieved is None


def test_invalid_graph_rejection_multiple_repo_nodes():
    """
    Test invalid graph rejection (multiple repo nodes).
    
    Validates: Requirements 9.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Create graph with multiple repo nodes
        node1 = Node(
            id="repo:test/repo1",
            type=NodeType.REPO,
            label="test/repo1",
            metadata={"url": "https://github.com/test/repo1"},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        node2 = Node(
            id="repo:test/repo2",
            type=NodeType.REPO,
            label="test/repo2",
            metadata={"url": "https://github.com/test/repo2"},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        graph = Graph(
            nodes=[node1, node2],
            edges=[],
            metadata={"schema_version": "1.0"}
        )
        
        # Attempt to save should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            repo.save_graph("test/repo", graph, 100)
        
        # Verify error message mentions multiple repo nodes
        assert "multiple" in str(exc_info.value).lower() and "repo" in str(exc_info.value).lower()
        
        # Verify no data was stored
        retrieved = repo.get_graph("test/repo")
        assert retrieved is None


def test_valid_graph_accepted():
    """
    Test that valid graphs are accepted and stored correctly.
    
    Validates: Requirements 9.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Create valid graph
        repo_node = Node(
            id="repo:test/repo",
            type=NodeType.REPO,
            label="test/repo",
            metadata={"url": "https://github.com/test/repo"},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        release_node = Node(
            id="release:test/repo:v1.0.0",
            type=NodeType.RELEASE,
            label="v1.0.0",
            metadata={"tag_name": "v1.0.0"},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        edge = Edge(
            source="repo:test/repo",
            target="release:test/repo:v1.0.0",
            relationship_type=EdgeType.HAS_RELEASE,
            metadata={},
            provenance={
                "source": "github_api",
                "established_at": datetime.now(timezone.utc).isoformat(),
                "confidence": 1.0
            }
        )
        
        graph = Graph(
            nodes=[repo_node, release_node],
            edges=[edge],
            metadata={"schema_version": "1.0"}
        )
        
        # Save should succeed
        repo.save_graph("test/repo", graph, 100)
        
        # Verify data was stored
        retrieved = repo.get_graph("test/repo")
        assert retrieved is not None
        assert retrieved["repo"] == "test/repo"
        assert retrieved["metadata"]["node_count"] == 2
        assert retrieved["metadata"]["edge_count"] == 1


def test_transaction_rollback_on_validation_error():
    """
    Test that transaction is rolled back when validation fails.
    
    Ensures no partial data is stored when validation fails.
    Validates: Requirements 9.2, 9.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # First, save a valid graph
        valid_node = Node(
            id="repo:test/repo",
            type=NodeType.REPO,
            label="test/repo",
            metadata={"url": "https://github.com/test/repo"},
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 1.0
            }
        )
        
        valid_graph = Graph(
            nodes=[valid_node],
            edges=[],
            metadata={"schema_version": "1.0"}
        )
        
        repo.save_graph("test/repo", valid_graph, 100)
        
        # Verify it was saved
        retrieved = repo.get_graph("test/repo")
        assert retrieved is not None
        original_node_count = retrieved["metadata"]["node_count"]
        
        # Now try to update with an invalid graph
        invalid_node = Node(
            id="repo:test/repo",
            type=NodeType.REPO,
            label="test/repo",
            metadata={"url": "https://github.com/test/repo"},
            provenance={}  # Missing required fields
        )
        
        invalid_graph = Graph(
            nodes=[invalid_node],
            edges=[],
            metadata={"schema_version": "1.0"}
        )
        
        # Attempt to save should fail
        with pytest.raises(ValidationError):
            repo.save_graph("test/repo", invalid_graph, 100)
        
        # Verify original data is still intact (transaction rolled back)
        retrieved = repo.get_graph("test/repo")
        assert retrieved is not None
        assert retrieved["metadata"]["node_count"] == original_node_count
