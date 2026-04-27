"""
Property-based tests for /api/graph endpoint response structure.

Feature: supply-chain-graph
Property 9: API Response Structure

For any valid API request to /api/graph, the response must include:
- repo
- schema_version
- generated_at
- graph.nodes
- graph.edges
- metadata fields (node_count, edge_count, data_sources, cache_hit, generation_time_ms)

Validates: Requirements US-2.2
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st, settings
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.app import app
from open_source_risk_model.graph.schema import Graph, Node, NodeType, GraphConfig


# Create test client
client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_cache():
    """Mock the graph cache for all tests to avoid cache interference."""
    with patch("api.app.graph_cache") as mock:
        # Default: cache miss (return None)
        mock.get.return_value = None
        mock.set.return_value = True
        yield mock


# Hypothesis strategies for generating test data
@st.composite
def valid_repo_names(draw):
    """Generate valid repository names in owner/repo format."""
    # Use only ASCII alphanumeric characters plus allowed special chars
    owner_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    repo_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
    
    owner = draw(st.text(alphabet=owner_chars, min_size=1, max_size=20))
    repo = draw(st.text(alphabet=repo_chars, min_size=1, max_size=30))
    return f"{owner}/{repo}"


@st.composite
def mock_score_data(draw):
    """Generate mock score data for testing."""
    return {
        "repo": {
            "url": draw(st.text(min_size=10)),
        },
        "overall": {
            "maintenance_risk": draw(st.floats(min_value=0.0, max_value=1.0)),
            "maintenance_label": draw(st.sampled_from(["low", "medium", "high", "critical"])),
            "coverage": draw(st.floats(min_value=0.0, max_value=1.0)),
            "confidence": draw(st.sampled_from(["high", "medium", "low"])),
        },
        "features": [],
        "top_drivers": [],
    }


@st.composite
def mock_graph(draw):
    """Generate a mock graph for testing."""
    # Create a simple graph with at least a repo node
    repo_node = Node(
        id=f"repo:{draw(st.text(min_size=5))}",
        type=NodeType.REPO,
        label=draw(st.text(min_size=1)),
        metadata={},
        provenance={"source": "github_api", "fetched_at": "2026-02-13T10:00:00Z", "data_confidence": 0.9}
    )
    
    graph = Graph(
        nodes=[repo_node],
        edges=[],
        metadata={
            "schema_version": "1.0",
            "generated_at": "2026-02-13T10:00:00Z",
            "repo": draw(st.text(min_size=5)),
            "warnings": [],
        }
    )
    
    return graph


# Property 9: API Response Structure
@settings(max_examples=100, deadline=None)
@given(
    repo_name=valid_repo_names(),
    score_data=mock_score_data(),
    graph_obj=mock_graph(),
)
def test_api_response_structure_property(repo_name, score_data, graph_obj):
    """
    Property 9: API Response Structure
    
    For any valid API request to /api/graph, the response must include
    repo, schema_version, generated_at, graph.nodes, graph.edges, and
    metadata fields.
    
    Validates: Requirements US-2.2
    """
    # Mock the score_repo and build_graph functions
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        # Setup mocks
        mock_score_repo.return_value = score_data
        mock_build_graph.return_value = graph_obj
        
        # Make API request
        response = client.get(f"/api/graph?repo={repo_name}")
        
        # Should return 200 OK
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Parse response
        data = response.json()
        
        # Verify required top-level fields
        assert "repo" in data, "Response must include 'repo' field"
        assert "schema_version" in data, "Response must include 'schema_version' field"
        assert "generated_at" in data, "Response must include 'generated_at' field"
        assert "graph" in data, "Response must include 'graph' field"
        assert "metadata" in data, "Response must include 'metadata' field"
        
        # Verify graph structure
        assert "nodes" in data["graph"], "Graph must include 'nodes' field"
        assert "edges" in data["graph"], "Graph must include 'edges' field"
        assert isinstance(data["graph"]["nodes"], list), "Nodes must be a list"
        assert isinstance(data["graph"]["edges"], list), "Edges must be a list"
        
        # Verify metadata fields
        metadata = data["metadata"]
        assert "node_count" in metadata, "Metadata must include 'node_count'"
        assert "edge_count" in metadata, "Metadata must include 'edge_count'"
        assert "data_sources" in metadata, "Metadata must include 'data_sources'"
        assert "cache_hit" in metadata, "Metadata must include 'cache_hit'"
        assert "generation_time_ms" in metadata, "Metadata must include 'generation_time_ms'"
        
        # Verify metadata types
        assert isinstance(metadata["node_count"], int), "node_count must be an integer"
        assert isinstance(metadata["edge_count"], int), "edge_count must be an integer"
        assert isinstance(metadata["data_sources"], list), "data_sources must be a list"
        assert isinstance(metadata["cache_hit"], bool), "cache_hit must be a boolean"
        assert isinstance(metadata["generation_time_ms"], int), "generation_time_ms must be an integer"
        
        # Verify counts match actual data
        assert metadata["node_count"] == len(data["graph"]["nodes"]), \
            "node_count must match actual number of nodes"
        assert metadata["edge_count"] == len(data["graph"]["edges"]), \
            "edge_count must match actual number of edges"


def test_api_response_structure_with_real_repo():
    """
    Test API response structure with a real repository (non-property test).
    
    This is a concrete example test to complement the property test.
    """
    # Mock the score_repo and build_graph functions
    mock_score = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    mock_graph_obj = Graph(
        nodes=[
            Node(
                id="repo:test/repo",
                type=NodeType.REPO,
                label="test/repo",
                metadata={},
                provenance={"source": "github_api", "fetched_at": "2026-02-13T10:00:00Z", "data_confidence": 0.9}
            )
        ],
        edges=[],
        metadata={
            "schema_version": "1.0",
            "generated_at": "2026-02-13T10:00:00Z",
            "repo": "test/repo",
            "warnings": [],
        }
    )
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph_obj
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required fields present
        assert data["repo"] == "test/repo"
        assert data["schema_version"] == "1.0"
        assert "generated_at" in data
        assert len(data["graph"]["nodes"]) == 1
        assert len(data["graph"]["edges"]) == 0
        assert data["metadata"]["node_count"] == 1
        assert data["metadata"]["edge_count"] == 0


def test_api_response_empty_graph():
    """
    Test that empty graph returns valid structure (not null).
    
    Edge case: Repository with no enrichment data should still return
    valid response structure with empty arrays.
    """
    mock_score = {
        "repo": {"url": "https://github.com/empty/repo"},
        "overall": {
            "maintenance_risk": 0.5,
            "maintenance_label": "medium",
            "coverage": 0.5,
            "confidence": "medium",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Empty graph (only repo node)
    mock_graph_obj = Graph(
        nodes=[
            Node(
                id="repo:empty/repo",
                type=NodeType.REPO,
                label="empty/repo",
                metadata={},
                provenance={"source": "github_api", "fetched_at": "2026-02-13T10:00:00Z", "data_confidence": 0.9}
            )
        ],
        edges=[],
        metadata={
            "schema_version": "1.0",
            "generated_at": "2026-02-13T10:00:00Z",
            "repo": "empty/repo",
            "warnings": [],
        }
    )
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph_obj
        
        response = client.get("/api/graph?repo=empty/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Empty arrays, not null
        assert data["graph"]["nodes"] == [{"id": "repo:empty/repo", "type": "repo", "label": "empty/repo", "metadata": {}, "provenance": {"source": "github_api", "fetched_at": "2026-02-13T10:00:00Z", "data_confidence": 0.9}}]
        assert data["graph"]["edges"] == []
        assert data["metadata"]["node_count"] == 1
        assert data["metadata"]["edge_count"] == 0
