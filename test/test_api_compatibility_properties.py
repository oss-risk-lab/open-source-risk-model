"""
Property-based tests for API backward compatibility.

Tests Property 13: API Response Schema Compatibility
"""

import pytest
from hypothesis import given, settings, strategies as st
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from api.app import app
from open_source_risk_model.graph.schema import Graph, Node, Edge, NodeType, EdgeType


# Strategy for generating valid repository names
@st.composite
def repo_name_strategy(draw):
    """Generate valid repository names in owner/repo format."""
    # Use only ASCII alphanumeric characters, hyphens, underscores, and dots
    # Must start with alphanumeric
    owner = draw(st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,19}", fullmatch=True))
    repo = draw(st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,19}", fullmatch=True))
    
    return f"{owner}/{repo}"


# Strategy for generating valid graph objects
@st.composite
def graph_strategy(draw):
    """Generate valid Graph objects."""
    repo_name = draw(repo_name_strategy())
    
    # Create repo node
    repo_node = Node(
        id=f"repo:{repo_name}",
        type=NodeType.REPO,
        label=repo_name,
        metadata={
            "url": f"https://github.com/{repo_name}",
            "maintenance_risk": draw(st.floats(min_value=0.0, max_value=1.0)),
        },
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0,
        }
    )
    
    nodes = [repo_node]
    edges = []
    
    # Add some release nodes
    num_releases = draw(st.integers(min_value=0, max_value=3))
    for i in range(num_releases):
        release_node = Node(
            id=f"release:{repo_name}:v1.{i}.0",
            type=NodeType.RELEASE,
            label=f"v1.{i}.0",
            metadata={"tag_name": f"v1.{i}.0"},
            provenance={"source": "github_api", "data_confidence": 1.0}
        )
        nodes.append(release_node)
        edges.append(Edge(
            source=repo_node.id,
            target=release_node.id,
            relationship_type=EdgeType.HAS_RELEASE,
            metadata={},
            provenance={"source": "github_api", "confidence": 1.0}
        ))
    
    graph = Graph(
        nodes=nodes,
        edges=edges,
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api"],
            "warnings": [],
        }
    )
    
    return repo_name, graph


@settings(max_examples=100, deadline=None)
@given(graph_data=graph_strategy())
def test_property_13_api_response_schema_compatibility(graph_data):
    """
    Feature: multi-repo-persistent-graph, Property 13: API Response Schema Compatibility
    
    For any repository, the response from /api/graph should conform to the existing
    schema regardless of whether data comes from the database or dynamic generation.
    
    Validates: Requirements 6.1, 6.4
    """
    repo_name, graph_obj = graph_data
    
    client = TestClient(app)
    
    # Mock the score_repo and build_graph functions to return our test data
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        # Setup mocks
        mock_score.return_value = {"repo": repo_name}
        mock_build.return_value = graph_obj
        mock_file_cache.get.return_value = None  # Disable file cache
        
        # Test 1: Dynamic generation (database returns None)
        mock_graph_repo.get_graph.return_value = None
        
        response = client.get(f"/api/graph?repo={repo_name}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify required top-level fields
        assert "repo" in data
        assert "schema_version" in data
        assert "generated_at" in data
        assert "graph" in data
        assert "metadata" in data
        
        # Verify graph structure
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert isinstance(data["graph"]["nodes"], list)
        assert isinstance(data["graph"]["edges"], list)
        
        # Verify metadata fields
        metadata = data["metadata"]
        assert "node_count" in metadata
        assert "edge_count" in metadata
        assert "data_sources" in metadata
        assert "cache_hit" in metadata
        assert "generation_time_ms" in metadata
        assert "request_id" in metadata
        
        # Verify types
        assert isinstance(metadata["node_count"], int)
        assert isinstance(metadata["edge_count"], int)
        assert isinstance(metadata["data_sources"], list)
        assert isinstance(metadata["cache_hit"], bool)
        assert isinstance(metadata["generation_time_ms"], int)
        
        # Test 2: Database cache hit
        graph_dict = graph_obj.to_dict()
        cached_response = {
            "repo": repo_name,
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "graph": graph_dict,  # This includes nodes, edges, and metadata
            "metadata": {
                "node_count": len(graph_obj.nodes),
                "edge_count": len(graph_obj.edges),
                "data_sources": ["github_api"],
                "warnings": [],
                "generation_time_ms": 100,
                "cache_hit": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        mock_graph_repo.get_graph.return_value = cached_response
        
        response2 = client.get(f"/api/graph?repo={repo_name}")
        
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Verify same schema structure
        assert set(data.keys()) == set(data2.keys())
        # Both should have nodes and edges in graph
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert "nodes" in data2["graph"]
        assert "edges" in data2["graph"]
        
        # Both should have the same required metadata fields
        required_metadata_fields = {
            "node_count", "edge_count", "data_sources", 
            "cache_hit", "generation_time_ms", "request_id"
        }
        assert required_metadata_fields.issubset(set(data["metadata"].keys()))
        assert required_metadata_fields.issubset(set(data2["metadata"].keys()))


@settings(max_examples=50, deadline=None)
@given(graph_data=graph_strategy())
def test_property_13_cache_hit_flag_accuracy(graph_data):
    """
    Feature: multi-repo-persistent-graph, Property 13: API Response Schema Compatibility
    
    The cache_hit flag should accurately reflect whether data came from cache or
    was dynamically generated.
    
    Validates: Requirements 6.1, 6.4
    """
    repo_name, graph_obj = graph_data
    
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": repo_name}
        mock_build.return_value = graph_obj
        mock_file_cache.get.return_value = None  # Disable file cache
        
        # Test cache miss - cache_hit should be False
        mock_graph_repo.get_graph.return_value = None
        
        response = client.get(f"/api/graph?repo={repo_name}")
        assert response.status_code == 200
        data = response.json()
        
        # When dynamically generated, cache_hit should be False
        assert data["metadata"]["cache_hit"] is False
        
        # Test cache hit - cache_hit should be True
        graph_dict = graph_obj.to_dict()
        cached_response = {
            "repo": repo_name,
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "graph": graph_dict,
            "metadata": {
                "node_count": len(graph_obj.nodes),
                "edge_count": len(graph_obj.edges),
                "data_sources": ["github_api"],
                "cache_hit": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        mock_graph_repo.get_graph.return_value = cached_response
        
        response2 = client.get(f"/api/graph?repo={repo_name}")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # When from cache, cache_hit should be True
        assert data2["metadata"]["cache_hit"] is True


@settings(max_examples=50, deadline=None)
@given(
    graph_data=graph_strategy(),
    include_cves=st.booleans(),
    max_releases=st.integers(min_value=1, max_value=100),
    max_maintainers=st.integers(min_value=1, max_value=50),
)
def test_property_13_query_parameters_preserved(graph_data, include_cves, max_releases, max_maintainers):
    """
    Feature: multi-repo-persistent-graph, Property 13: API Response Schema Compatibility
    
    Query parameters should work the same way regardless of whether data comes
    from cache or is dynamically generated.
    
    Validates: Requirements 6.1, 6.4
    """
    repo_name, graph_obj = graph_data
    
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": repo_name}
        mock_build.return_value = graph_obj
        mock_graph_repo.get_graph.return_value = None
        mock_file_cache.get.return_value = None  # Disable file cache
        
        # Make request with query parameters
        response = client.get(
            f"/api/graph?repo={repo_name}&include_cves={include_cves}"
            f"&max_releases={max_releases}&max_maintainers={max_maintainers}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure is consistent
        assert "repo" in data
        assert "graph" in data
        assert "metadata" in data
        assert data["repo"] == repo_name
        
        # Verify the build_graph was called with correct config
        if mock_build.called:
            call_args = mock_build.call_args
            config = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('config')
            if config:
                assert config.include_cves == include_cves
                assert config.max_releases == max_releases
                assert config.max_maintainers == max_maintainers
