"""
Property-based tests for persistence layer.

Tests Properties 1-3:
- Property 1: Graph Storage Round-Trip
- Property 2: Database Persistence Across Restarts
- Property 3: Update Idempotency
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.graph.schema import (
    Graph,
    Node,
    Edge,
    NodeType,
    EdgeType,
)
from src.open_source_risk_model.persistence.db import init_database
from src.open_source_risk_model.persistence.graph_repo import GraphRepository


# Test strategies for generating valid graph data

@st.composite
def provenance_strategy(draw):
    """Generate valid provenance metadata."""
    source = draw(st.sampled_from(["github_api", "osv", "heuristic", "registry"]))
    timestamp = datetime.now(timezone.utc).isoformat()
    confidence = draw(st.floats(min_value=0.0, max_value=1.0))
    
    return {
        "source": source,
        "fetched_at": timestamp,
        "data_confidence": confidence,
    }


@st.composite
def node_strategy(draw, node_type=None):
    """Generate a valid node."""
    if node_type is None:
        node_type = draw(st.sampled_from(list(NodeType)))
    
    # Generate appropriate metadata based on node type
    metadata = {}
    if node_type == NodeType.REPO:
        metadata = {
            "url": f"https://github.com/{draw(st.text(min_size=3, max_size=20))}/{draw(st.text(min_size=3, max_size=20))}",
            "maintenance_risk": draw(st.floats(min_value=0.0, max_value=1.0)),
            "maintenance_label": draw(st.sampled_from(["low", "medium", "high"])),
        }
    elif node_type == NodeType.MAINTAINER:
        metadata = {
            "username": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"))),
            "contribution_fraction": draw(st.floats(min_value=0.0, max_value=1.0)),
            "commit_count": draw(st.integers(min_value=1, max_value=10000)),
        }
    elif node_type == NodeType.CVE:
        cve_year = draw(st.integers(min_value=2000, max_value=2026))
        cve_num = draw(st.integers(min_value=1, max_value=99999))
        metadata = {
            "cve_id": f"CVE-{cve_year}-{cve_num}",
            "severity": draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
            "cvss_score": draw(st.floats(min_value=0.0, max_value=10.0)),
        }
    elif node_type == NodeType.REGISTRY:
        metadata = {
            "registry_type": draw(st.sampled_from(["pypi", "npm", "maven", "rubygems"])),
            "package_name": draw(st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-_"))),
            "latest_version": f"{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=50))}.{draw(st.integers(min_value=0, max_value=100))}",
        }
    elif node_type == NodeType.RELEASE:
        metadata = {
            "tag_name": f"v{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=50))}.{draw(st.integers(min_value=0, max_value=100))}",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
    
    node_id_suffix = draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_/:')))
    node_id = f"{node_type.value}:{node_id_suffix}"
    label = draw(st.text(min_size=3, max_size=50))
    
    return Node(
        id=node_id,
        type=node_type,
        label=label,
        metadata=metadata,
        provenance=draw(provenance_strategy())
    )


@st.composite
def edge_strategy(draw, node_ids):
    """Generate a valid edge between existing nodes."""
    if len(node_ids) < 2:
        # Need at least 2 nodes for an edge
        return None
    
    source = draw(st.sampled_from(node_ids))
    target = draw(st.sampled_from([nid for nid in node_ids if nid != source]))
    relationship_type = draw(st.sampled_from(list(EdgeType)))
    
    return Edge(
        source=source,
        target=target,
        relationship_type=relationship_type,
        metadata={},
        provenance=draw(provenance_strategy())
    )


@st.composite
def valid_graph_strategy(draw):
    """
    Generate a valid graph with at least one repo node.
    
    Ensures the graph passes validation by:
    - Having exactly one repo node
    - Having unique node IDs
    - Having edges that reference valid nodes
    - Having unique CVE IDs (to avoid index constraint violations)
    - Having unique maintainer usernames (to avoid index constraint violations)
    """
    # Always start with one repo node
    repo_node = draw(node_strategy(node_type=NodeType.REPO))
    nodes = [repo_node]
    
    # Track used CVE IDs and maintainer usernames to ensure uniqueness
    used_cve_ids = set()
    used_maintainer_usernames = set()
    
    # Add additional nodes (0-10 of various types)
    num_additional_nodes = draw(st.integers(min_value=0, max_value=10))
    for _ in range(num_additional_nodes):
        # Don't add more repo nodes
        node_type = draw(st.sampled_from([
            NodeType.RELEASE,
            NodeType.MAINTAINER,
            NodeType.CVE,
            NodeType.REGISTRY,
            NodeType.RISK_FACTOR,
        ]))
        
        node = draw(node_strategy(node_type=node_type))
        
        # For CVE nodes, ensure unique cve_id
        if node_type == NodeType.CVE:
            cve_id = node.metadata.get("cve_id")
            if cve_id in used_cve_ids:
                # Skip this node if CVE ID already used
                continue
            used_cve_ids.add(cve_id)
        
        # For maintainer nodes, ensure unique username
        if node_type == NodeType.MAINTAINER:
            username = node.metadata.get("username")
            if username in used_maintainer_usernames:
                # Skip this node if username already used
                continue
            used_maintainer_usernames.add(username)
        
        nodes.append(node)
    
    # Ensure unique node IDs
    seen_ids = set()
    unique_nodes = []
    for node in nodes:
        if node.id not in seen_ids:
            seen_ids.add(node.id)
            unique_nodes.append(node)
    
    node_ids = [n.id for n in unique_nodes]
    
    # Generate edges (0-15 edges)
    edges = []
    num_edges = draw(st.integers(min_value=0, max_value=min(15, len(node_ids) * 2)))
    for _ in range(num_edges):
        edge = draw(edge_strategy(node_ids))
        if edge:
            edges.append(edge)
    
    # Create graph with metadata
    metadata = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": draw(st.lists(
            st.sampled_from(["github_api", "osv", "heuristic"]),
            min_size=1,
            max_size=3,
            unique=True
        )),
        "warnings": draw(st.lists(st.text(min_size=5, max_size=50), max_size=3)),
    }
    
    return Graph(nodes=unique_nodes, edges=edges, metadata=metadata)


# Test strategies for repo names

@st.composite
def repo_name_strategy(draw):
    """Generate valid repository names in owner/repo format."""
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
    return f"{owner}/{repo}"


# Property Tests

@settings(max_examples=100, deadline=None)
@given(
    repo_name=repo_name_strategy(),
    graph=valid_graph_strategy()
)
def test_property_1_graph_storage_round_trip(repo_name, graph):
    """
    Feature: multi-repo-persistent-graph, Property 1: Graph Storage Round-Trip
    
    For any valid repository graph, saving it to the database and then
    retrieving it should produce an equivalent graph with all nodes, edges,
    metadata, and provenance preserved.
    
    Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.6
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Save graph
        repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Retrieve graph
        result = repo.get_graph(repo_name)
        
        # Verify result exists
        assert result is not None
        assert result["repo"] == repo_name
        
        # Verify graph structure is preserved
        retrieved_graph = result["graph"]
        original_graph = graph.to_dict()
        
        # Check node count
        assert len(retrieved_graph["nodes"]) == len(original_graph["nodes"])
        assert result["metadata"]["node_count"] == len(graph.nodes)
        
        # Check edge count
        assert len(retrieved_graph["edges"]) == len(original_graph["edges"])
        assert result["metadata"]["edge_count"] == len(graph.edges)
        
        # Verify all nodes are preserved
        original_node_ids = {n["id"] for n in original_graph["nodes"]}
        retrieved_node_ids = {n["id"] for n in retrieved_graph["nodes"]}
        assert original_node_ids == retrieved_node_ids
        
        # Verify node data is preserved (check a sample)
        for orig_node in original_graph["nodes"]:
            retr_node = next(n for n in retrieved_graph["nodes"] if n["id"] == orig_node["id"])
            assert retr_node["type"] == orig_node["type"]
            assert retr_node["label"] == orig_node["label"]
            # Metadata and provenance should be preserved
            assert retr_node["metadata"] == orig_node["metadata"]
            assert retr_node["provenance"] == orig_node["provenance"]
        
        # Verify all edges are preserved
        original_edges = {(e["source"], e["target"], e["relationship_type"]) for e in original_graph["edges"]}
        retrieved_edges = {(e["source"], e["target"], e["relationship_type"]) for e in retrieved_graph["edges"]}
        assert original_edges == retrieved_edges
        
        # Verify metadata is preserved
        assert result["metadata"]["data_sources"] == graph.metadata.get("data_sources", [])
        assert result["metadata"]["warnings"] == graph.metadata.get("warnings", [])


@settings(max_examples=50, deadline=None)
@given(
    repo_name=repo_name_strategy(),
    graph=valid_graph_strategy()
)
def test_property_2_database_persistence_across_restarts(repo_name, graph):
    """
    Feature: multi-repo-persistent-graph, Property 2: Database Persistence Across Restarts
    
    For any set of repository graphs stored in the database, closing and
    reopening the database connection should preserve all graph data.
    
    Validates: Requirements 1.3
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        
        # Save graph with first connection
        repo1 = GraphRepository(db_path)
        repo1.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Close connection by deleting repository object
        del repo1
        
        # Create new connection (simulating restart)
        repo2 = GraphRepository(db_path)
        result = repo2.get_graph(repo_name)
        
        # Verify data is still there
        assert result is not None
        assert result["repo"] == repo_name
        assert result["metadata"]["node_count"] == len(graph.nodes)
        assert result["metadata"]["edge_count"] == len(graph.edges)
        
        # Verify graph structure is intact
        retrieved_graph = result["graph"]
        assert len(retrieved_graph["nodes"]) == len(graph.nodes)
        assert len(retrieved_graph["edges"]) == len(graph.edges)


@settings(max_examples=50, deadline=None)
@given(
    repo_name=repo_name_strategy(),
    graph1=valid_graph_strategy(),
    graph2=valid_graph_strategy()
)
def test_property_3_update_idempotency(repo_name, graph1, graph2):
    """
    Feature: multi-repo-persistent-graph, Property 3: Update Idempotency
    
    For any repository, ingesting it multiple times should result in exactly
    one entry in the database with the most recent data and an updated timestamp.
    
    Validates: Requirements 2.6, 7.4
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        repo = GraphRepository(db_path)
        
        # Save first version
        repo.save_graph(repo_name, graph1, generation_time_ms=1000)
        result1 = repo.get_graph(repo_name)
        created_at_1 = result1["metadata"]["created_at"]
        updated_at_1 = result1["metadata"]["updated_at"]
        
        # Save second version (update)
        repo.save_graph(repo_name, graph2, generation_time_ms=2000)
        result2 = repo.get_graph(repo_name)
        created_at_2 = result2["metadata"]["created_at"]
        updated_at_2 = result2["metadata"]["updated_at"]
        
        # Verify only one entry exists
        count = repo.get_repo_count()
        assert count == 1
        
        # Verify created_at is preserved
        assert created_at_2 == created_at_1
        
        # Verify updated_at changed
        assert updated_at_2 >= updated_at_1
        
        # Verify data is from second graph
        assert result2["metadata"]["node_count"] == len(graph2.nodes)
        assert result2["metadata"]["edge_count"] == len(graph2.edges)
        assert result2["metadata"]["generation_time_ms"] == 2000
