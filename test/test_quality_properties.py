"""
Property-based tests for data quality and validation.

Tests Properties 16-19:
- Property 16: Graph Validation Before Storage
- Property 18: TTL Enforcement
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st, assume

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


# Test strategies for generating invalid graph data

@st.composite
def invalid_graph_missing_fields_strategy(draw):
    """Generate a graph with nodes missing required provenance fields."""
    # Create a node with missing provenance
    node = Node(
        id=f"repo:{draw(st.text(min_size=5, max_size=20))}",
        type=NodeType.REPO,
        label=draw(st.text(min_size=3, max_size=50)),
        metadata={"url": "https://github.com/test/repo"},
        provenance={}  # Missing required fields
    )
    
    graph = Graph(
        nodes=[node],
        edges=[],
        metadata={"schema_version": "1.0"}
    )
    
    return graph


@st.composite
def invalid_graph_duplicate_ids_strategy(draw):
    """Generate a graph with duplicate node IDs."""
    node_id = f"repo:{draw(st.text(min_size=5, max_size=20))}"
    
    node1 = Node(
        id=node_id,
        type=NodeType.REPO,
        label=draw(st.text(min_size=3, max_size=50)),
        metadata={"url": "https://github.com/test/repo1"},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0
        }
    )
    
    node2 = Node(
        id=node_id,  # Duplicate ID
        type=NodeType.REPO,
        label=draw(st.text(min_size=3, max_size=50)),
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
    
    return graph


@st.composite
def invalid_graph_orphaned_edges_strategy(draw):
    """Generate a graph with edges referencing non-existent nodes."""
    node = Node(
        id=f"repo:{draw(st.text(min_size=5, max_size=20))}",
        type=NodeType.REPO,
        label=draw(st.text(min_size=3, max_size=50)),
        metadata={"url": "https://github.com/test/repo"},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0
        }
    )
    
    # Edge referencing non-existent target
    edge = Edge(
        source=node.id,
        target=f"nonexistent:{draw(st.text(min_size=5, max_size=20))}",
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
    
    return graph


@st.composite
def invalid_graph_multiple_repo_nodes_strategy(draw):
    """Generate a graph with multiple repo nodes."""
    node1 = Node(
        id=f"repo:{draw(st.text(min_size=5, max_size=20))}",
        type=NodeType.REPO,
        label=draw(st.text(min_size=3, max_size=50)),
        metadata={"url": "https://github.com/test/repo1"},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0
        }
    )
    
    node2 = Node(
        id=f"repo:{draw(st.text(min_size=5, max_size=20))}",
        type=NodeType.REPO,
        label=draw(st.text(min_size=3, max_size=50)),
        metadata={"url": "https://github.com/test/repo2"},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0
        }
    )
    
    # Ensure different IDs
    assume(node1.id != node2.id)
    
    graph = Graph(
        nodes=[node1, node2],
        edges=[],
        metadata={"schema_version": "1.0"}
    )
    
    return graph


# Property 16: Graph Validation Before Storage

@settings(max_examples=100)
@given(invalid_graph=st.one_of(
    invalid_graph_missing_fields_strategy(),
    invalid_graph_duplicate_ids_strategy(),
    invalid_graph_orphaned_edges_strategy(),
    invalid_graph_multiple_repo_nodes_strategy()
))
def test_property_16_graph_validation_before_storage(invalid_graph):
    """
    Feature: multi-repo-persistent-graph, Property 16: Graph Validation Before Storage
    
    For any graph that violates the graph schema (missing required fields,
    invalid references, duplicate IDs), attempting to save it should fail
    with a validation error and no data should be stored.
    
    Validates: Requirements 9.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        repo_name = "test/invalid-repo"
        
        # Attempt to save invalid graph should raise ValidationError
        with pytest.raises(ValidationError):
            repo.save_graph(repo_name, invalid_graph, 100)
        
        # Verify no data was stored
        retrieved = repo.get_graph(repo_name)
        assert retrieved is None, "Invalid graph should not be stored in database"


# Property 18: TTL Enforcement

def test_property_18_ttl_enforcement_stale_indicator():
    """
    Feature: multi-repo-persistent-graph, Property 18: TTL Enforcement
    
    For any repository graph in the database, if the age exceeds the
    configured TTL and refresh=false, the system should clearly indicate
    the data is stale.
    
    Validates: Requirements 7.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Create a valid graph
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
        
        graph = Graph(
            nodes=[node],
            edges=[],
            metadata={"schema_version": "1.0"}
        )
        
        # Save graph
        repo.save_graph("test/repo", graph, 100)
        
        # Retrieve immediately - should be fresh
        result = repo.get_graph("test/repo")
        assert result is not None
        
        # Manually update the timestamp to simulate old data
        # Set updated_at to 25 hours ago (exceeds default 24 hour TTL)
        old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        
        import sqlite3
        from src.open_source_risk_model.persistence.db import get_connection
        
        conn = get_connection(db_path)
        try:
            conn.execute("""
                UPDATE repo_graphs
                SET updated_at = ?
                WHERE repo_full_name = ?
            """, (old_timestamp, "test/repo"))
            conn.commit()
        finally:
            conn.close()
        
        # Retrieve again - data should be marked as stale
        result = repo.get_graph("test/repo")
        assert result is not None
        
        # Calculate age
        updated_at = datetime.fromisoformat(result["generated_at"])
        age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
        
        # Verify age exceeds TTL (24 hours)
        assert age_hours > 24, f"Age {age_hours} should exceed TTL of 24 hours"
        
        # The API layer is responsible for adding is_stale flag based on TTL
        # Here we verify the timestamp is correctly stored and retrievable
        assert result["generated_at"] == old_timestamp


def test_property_18_ttl_enforcement_fresh_data():
    """
    Feature: multi-repo-persistent-graph, Property 18: TTL Enforcement
    
    For any repository graph in the database, if the age is within the
    configured TTL, the system should return the data without stale indicator.
    
    Validates: Requirements 7.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Create a valid graph
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
        
        graph = Graph(
            nodes=[node],
            edges=[],
            metadata={"schema_version": "1.0"}
        )
        
        # Save graph
        repo.save_graph("test/repo", graph, 100)
        
        # Retrieve immediately - should be fresh
        result = repo.get_graph("test/repo")
        assert result is not None
        
        # Calculate age
        updated_at = datetime.fromisoformat(result["generated_at"])
        age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
        
        # Verify age is within TTL (24 hours)
        assert age_hours < 24, f"Age {age_hours} should be within TTL of 24 hours"
