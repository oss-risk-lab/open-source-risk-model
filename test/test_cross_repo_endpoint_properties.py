"""
Property-based tests for cross-repo query API endpoints.

Tests Properties 17 and 19 from the design document.
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from open_source_risk_model.graph.schema import (
    Graph,
    Node,
    Edge,
    NodeType,
    EdgeType,
)
from open_source_risk_model.persistence.graph_repo import GraphRepository
from open_source_risk_model.persistence.db import init_database


# Strategy for generating valid repo names
@st.composite
def repo_name_strategy(draw):
    """Generate valid repository names (owner/repo format)."""
    owner = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'),
        whitelist_characters='-_'
    )))
    repo = draw(st.text(min_size=1, max_size=30, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'),
        whitelist_characters='-_.'
    )))
    return f"{owner}/{repo}"


# Strategy for generating provenance
@st.composite
def provenance_strategy(draw):
    """Generate valid provenance dictionaries."""
    return {
        "source": draw(st.sampled_from(["github_api", "osv", "manual"])),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_confidence": draw(st.floats(min_value=0.0, max_value=1.0))
    }


# Strategy for generating nodes
@st.composite
def node_strategy(draw, node_type=None, node_id=None):
    """Generate valid nodes."""
    if node_type is None:
        node_type = draw(st.sampled_from([
            NodeType.REPO,
            NodeType.RELEASE,
            NodeType.MAINTAINER,
            NodeType.CVE,
            NodeType.REGISTRY,
            NodeType.RISK_FACTOR
        ]))
    
    # Generate unique node ID if not provided
    if node_id is None:
        node_id = f"{node_type.value}:{draw(st.text(min_size=5, max_size=50))}"
    
    label = draw(st.text(min_size=1, max_size=100))
    
    # Generate type-specific metadata
    metadata = {}
    if node_type == NodeType.REPO:
        metadata = {
            "url": f"https://github.com/{draw(repo_name_strategy())}",
            "maintenance_risk": draw(st.floats(min_value=0.0, max_value=1.0)),
            "maintenance_label": draw(st.sampled_from(["low", "medium", "high"]))
        }
    elif node_type == NodeType.MAINTAINER:
        metadata = {
            "username": draw(st.text(min_size=1, max_size=39)),
            "contribution_fraction": draw(st.floats(min_value=0.0, max_value=1.0)),
            "commit_count": draw(st.integers(min_value=1, max_value=10000))
        }
    elif node_type == NodeType.CVE:
        metadata = {
            "cve_id": f"CVE-{draw(st.integers(min_value=2000, max_value=2026))}-{draw(st.integers(min_value=1, max_value=99999))}",
            "severity": draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
            "cvss_score": draw(st.floats(min_value=0.0, max_value=10.0))
        }
    elif node_type == NodeType.REGISTRY:
        metadata = {
            "registry_type": draw(st.sampled_from(["pypi", "npm", "maven", "rubygems"])),
            "package_name": draw(st.text(min_size=1, max_size=50)),
            "latest_version": f"{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=20))}.{draw(st.integers(min_value=0, max_value=50))}"
        }
    elif node_type == NodeType.RELEASE:
        metadata = {
            "tag_name": f"v{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=20))}.{draw(st.integers(min_value=0, max_value=50))}",
            "published_at": datetime.now(timezone.utc).isoformat()
        }
    
    return Node(
        id=node_id,
        type=node_type,
        label=label,
        metadata=metadata,
        provenance=draw(provenance_strategy())
    )


# Strategy for generating edges
@st.composite
def edge_strategy(draw, source_id, target_id):
    """Generate valid edges."""
    return Edge(
        source=source_id,
        target=target_id,
        relationship_type=draw(st.sampled_from([
            EdgeType.HAS_RELEASE,
            EdgeType.MAINTAINED_BY,
            EdgeType.HAS_CVE,
            EdgeType.PUBLISHED_AS,
            EdgeType.HAS_RISK_FACTOR
        ])),
        metadata={},
        provenance=draw(provenance_strategy())
    )


# Strategy for generating complete graphs
@st.composite
def graph_strategy(draw):
    """Generate valid graphs with exactly one repo node and unique node IDs and CVE IDs."""
    # Always include exactly one repo node with unique ID
    repo_node_id = f"repo:{draw(st.text(min_size=5, max_size=50))}"
    repo_node = draw(node_strategy(node_type=NodeType.REPO, node_id=repo_node_id))
    
    # Generate additional nodes with unique IDs and unique CVE IDs
    num_additional_nodes = draw(st.integers(min_value=0, max_value=10))
    additional_nodes = []
    used_ids = {repo_node_id}
    used_cve_ids = set()
    used_maintainer_usernames = set()
    used_registry_keys = set()
    
    for i in range(num_additional_nodes):
        # Generate a unique node type
        node_type = draw(st.sampled_from([
            NodeType.RELEASE,
            NodeType.MAINTAINER,
            NodeType.CVE,
            NodeType.REGISTRY,
            NodeType.RISK_FACTOR
        ]))
        
        # Generate unique node ID
        node_id = f"{node_type.value}:{draw(st.text(min_size=5, max_size=50))}-{i}"
        while node_id in used_ids:
            node_id = f"{node_type.value}:{draw(st.text(min_size=5, max_size=50))}-{i}-retry"
        used_ids.add(node_id)
        
        # Create node with type-specific unique constraints
        if node_type == NodeType.CVE:
            # Ensure unique CVE ID
            cve_id = f"CVE-{draw(st.integers(min_value=2000, max_value=2026))}-{i}"
            while cve_id in used_cve_ids:
                cve_id = f"CVE-{draw(st.integers(min_value=2000, max_value=2026))}-{i}-{len(used_cve_ids)}"
            used_cve_ids.add(cve_id)
            
            node = Node(
                id=node_id,
                type=node_type,
                label=cve_id,
                metadata={
                    "cve_id": cve_id,
                    "severity": draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
                    "cvss_score": draw(st.floats(min_value=0.0, max_value=10.0))
                },
                provenance=draw(provenance_strategy())
            )
        elif node_type == NodeType.MAINTAINER:
            # Ensure unique maintainer username
            username = f"user{i}-{draw(st.text(min_size=1, max_size=20))}"
            while username in used_maintainer_usernames:
                username = f"user{i}-{len(used_maintainer_usernames)}-{draw(st.text(min_size=1, max_size=10))}"
            used_maintainer_usernames.add(username)
            
            node = Node(
                id=node_id,
                type=node_type,
                label=username,
                metadata={
                    "username": username,
                    "contribution_fraction": draw(st.floats(min_value=0.0, max_value=1.0)),
                    "commit_count": draw(st.integers(min_value=1, max_value=10000))
                },
                provenance=draw(provenance_strategy())
            )
        elif node_type == NodeType.REGISTRY:
            # Ensure unique registry key (registry_type + package_name)
            registry_type = draw(st.sampled_from(["pypi", "npm", "maven", "rubygems"]))
            package_name = f"package{i}-{draw(st.text(min_size=1, max_size=20))}"
            registry_key = f"{registry_type}:{package_name}"
            while registry_key in used_registry_keys:
                package_name = f"package{i}-{len(used_registry_keys)}"
                registry_key = f"{registry_type}:{package_name}"
            used_registry_keys.add(registry_key)
            
            node = Node(
                id=node_id,
                type=node_type,
                label=package_name,
                metadata={
                    "registry_type": registry_type,
                    "package_name": package_name,
                    "latest_version": f"{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=20))}.{draw(st.integers(min_value=0, max_value=50))}"
                },
                provenance=draw(provenance_strategy())
            )
        else:
            # For other node types, use the standard strategy
            node = draw(node_strategy(node_type=node_type, node_id=node_id))
        
        additional_nodes.append(node)
    
    nodes = [repo_node] + additional_nodes
    
    # Generate edges between nodes
    edges = []
    if len(nodes) > 1:
        num_edges = draw(st.integers(min_value=0, max_value=min(20, len(nodes) * 2)))
        for _ in range(num_edges):
            source = draw(st.sampled_from(nodes))
            target = draw(st.sampled_from(nodes))
            if source.id != target.id:
                edges.append(draw(edge_strategy(source.id, target.id)))
    
    return Graph(
        nodes=nodes,
        edges=edges,
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api", "osv"],
            "warnings": []
        }
    )


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


@settings(max_examples=100, deadline=None)
@given(
    repo_name=repo_name_strategy(),
    graph=graph_strategy()
)
def test_property_17_metadata_completeness(repo_name, graph):
    """
    Feature: multi-repo-persistent-graph, Property 17: Metadata Completeness
    
    For any query result (single repo, multi-repo, or cross-repo), the response
    should include all required metadata fields (timestamps, confidence, provenance,
    node/edge counts).
    
    Validates: Requirements 4.3, 7.2, 10.5
    """
    # Create temporary database for this test
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Initialize database schema
        init_database(db_path)
        
        # Initialize repository
        repo = GraphRepository(db_path=db_path)
        
        # Save the graph
        repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Test 1: Single repo query (get_graph)
        result = repo.get_graph(repo_name)
        assert result is not None, "Graph should be retrievable"
        
        # Verify required metadata fields
        assert "repo" in result
        assert "schema_version" in result
        assert "generated_at" in result
        assert "graph" in result
        assert "metadata" in result
        
        metadata = result["metadata"]
        required_metadata_fields = [
            "node_count",
            "edge_count",
            "data_sources",
            "warnings",
            "generation_time_ms",
            "cache_hit",
            "created_at",
            "updated_at"
        ]
        
        for field in required_metadata_fields:
            assert field in metadata, f"Metadata should include {field}"
        
        # Verify metadata values are correct
        assert metadata["node_count"] == len(graph.nodes)
        assert metadata["edge_count"] == len(graph.edges)
        assert isinstance(metadata["data_sources"], list)
        assert isinstance(metadata["warnings"], list)
        assert isinstance(metadata["generation_time_ms"], int)
        assert isinstance(metadata["cache_hit"], bool)
        
        # Verify timestamps are valid ISO format
        try:
            datetime.fromisoformat(metadata["created_at"].replace('Z', '+00:00'))
            datetime.fromisoformat(metadata["updated_at"].replace('Z', '+00:00'))
        except ValueError:
            pytest.fail("Timestamps should be valid ISO format")
        
        # Test 2: Multi-repo query (list_repos)
        repos_list = repo.list_repos(limit=10)
        assert len(repos_list) > 0, "Should return at least one repo"
        
        for repo_metadata in repos_list:
            required_list_fields = [
                "repo_full_name",
                "node_count",
                "edge_count",
                "created_at",
                "updated_at",
                "data_sources",
                "generation_time_ms"
            ]
            
            for field in required_list_fields:
                assert field in repo_metadata, f"Repo list metadata should include {field}"
            
            # Verify data types
            assert isinstance(repo_metadata["node_count"], int)
            assert isinstance(repo_metadata["edge_count"], int)
            assert isinstance(repo_metadata["data_sources"], list)
            assert isinstance(repo_metadata["generation_time_ms"], int)
            
            # Verify timestamps
            try:
                datetime.fromisoformat(repo_metadata["created_at"].replace('Z', '+00:00'))
                datetime.fromisoformat(repo_metadata["updated_at"].replace('Z', '+00:00'))
            except ValueError:
                pytest.fail("List timestamps should be valid ISO format")



@settings(max_examples=100, deadline=None)
@given(
    repo_name=repo_name_strategy(),
    graph=graph_strategy()
)
def test_property_19_cascade_deletion_completeness(repo_name, graph):
    """
    Feature: multi-repo-persistent-graph, Property 19: Cascade Deletion Completeness
    
    For any repository, deleting it from the database should remove the graph data
    and all associated index entries (maintainers, CVEs, registries).
    
    Validates: Requirements 8.5
    """
    # Create temporary database for this test
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Initialize database schema
        init_database(db_path)
        
        # Initialize repositories
        graph_repo = GraphRepository(db_path=db_path)
        from open_source_risk_model.persistence.index_repo import IndexRepository
        index_repo = IndexRepository(db_path=db_path)
        
        # Save the graph
        graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Verify graph is saved
        result = graph_repo.get_graph(repo_name)
        assert result is not None, "Graph should be saved"
        
        # Count index entries before deletion
        # Check maintainer indexes
        maintainer_count_before = 0
        for node in graph.nodes:
            if node.type == NodeType.MAINTAINER and "username" in node.metadata:
                username = node.metadata["username"]
                repos = index_repo.find_repos_by_maintainer(username)
                maintainer_count_before += len([r for r in repos if r["repo_full_name"] == repo_name])
        
        # Check CVE indexes
        cve_count_before = 0
        for node in graph.nodes:
            if node.type == NodeType.CVE and "cve_id" in node.metadata:
                cve_id = node.metadata["cve_id"]
                repos = index_repo.find_repos_by_cve(cve_id)
                cve_count_before += len([r for r in repos if r["repo_full_name"] == repo_name])
        
        # Check registry indexes
        registry_count_before = 0
        for node in graph.nodes:
            if node.type == NodeType.REGISTRY:
                registry_type = node.metadata.get("registry_type")
                package_name = node.metadata.get("package_name")
                if registry_type and package_name:
                    result = index_repo.find_repo_by_package(registry_type, package_name)
                    if result and result["repo_full_name"] == repo_name:
                        registry_count_before += 1
        
        # Delete the repository
        deleted = graph_repo.delete_graph(repo_name)
        assert deleted, "Repository should be deleted"
        
        # Verify graph is deleted
        result = graph_repo.get_graph(repo_name)
        assert result is None, "Graph should be deleted"
        
        # Verify all index entries are deleted
        # Check maintainer indexes
        for node in graph.nodes:
            if node.type == NodeType.MAINTAINER and "username" in node.metadata:
                username = node.metadata["username"]
                repos = index_repo.find_repos_by_maintainer(username)
                # Should not find this repo anymore
                assert not any(r["repo_full_name"] == repo_name for r in repos), \
                    f"Maintainer index for {username} should not contain deleted repo"
        
        # Check CVE indexes
        for node in graph.nodes:
            if node.type == NodeType.CVE and "cve_id" in node.metadata:
                cve_id = node.metadata["cve_id"]
                repos = index_repo.find_repos_by_cve(cve_id)
                # Should not find this repo anymore
                assert not any(r["repo_full_name"] == repo_name for r in repos), \
                    f"CVE index for {cve_id} should not contain deleted repo"
        
        # Check registry indexes
        for node in graph.nodes:
            if node.type == NodeType.REGISTRY:
                registry_type = node.metadata.get("registry_type")
                package_name = node.metadata.get("package_name")
                if registry_type and package_name:
                    result = index_repo.find_repo_by_package(registry_type, package_name)
                    # Should either be None or not match this repo
                    assert result is None or result["repo_full_name"] != repo_name, \
                        f"Registry index for {registry_type}:{package_name} should not contain deleted repo"
