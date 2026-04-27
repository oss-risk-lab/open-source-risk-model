"""
Unit tests for /api/graph endpoint.

Tests successful graph generation, various query parameters,
error cases, and edge cases.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.app import app
from open_source_risk_model.graph.schema import Graph, Node, Edge, NodeType, EdgeType


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


def create_mock_score_data(repo_name: str = "test/repo") -> dict:
    """Create mock score data for testing."""
    return {
        "repo": {
            "url": f"https://github.com/{repo_name}",
            "full_name": repo_name,
        },
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [
            {
                "key": "days_since_last_release",
                "label": "Days Since Last Release",
                "raw_value": 30,
                "risk_score": 0.2,
                "weight": 0.15,
                "category": "activity",
            }
        ],
        "top_drivers": [
            {
                "key": "days_since_last_release",
                "contribution": 0.08,
            }
        ],
    }


def create_mock_graph(repo_name: str = "test/repo") -> Graph:
    """Create a mock graph for testing."""
    repo_node = Node(
        id=f"repo:{repo_name}",
        type=NodeType.REPO,
        label=repo_name,
        metadata={
            "url": f"https://github.com/{repo_name}",
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
        },
        provenance={
            "source": "github_api",
            "fetched_at": "2026-02-13T10:00:00Z",
            "data_confidence": 0.9,
        }
    )
    
    release_node = Node(
        id=f"release:{repo_name}:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={
            "tag_name": "v1.0.0",
            "published_at": "2026-01-15T10:00:00Z",
            "is_latest": True,
        },
        provenance={
            "source": "github_api",
            "fetched_at": "2026-02-13T10:00:00Z",
            "data_confidence": 1.0,
        }
    )
    
    edge = Edge(
        source=repo_node.id,
        target=release_node.id,
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={"is_latest": True},
        provenance={
            "source": "github_api",
            "established_at": "2026-02-13T10:00:00Z",
            "confidence": 1.0,
        }
    )
    
    graph = Graph(
        nodes=[repo_node, release_node],
        edges=[edge],
        metadata={
            "schema_version": "1.0",
            "generated_at": "2026-02-13T10:00:00Z",
            "repo": repo_name,
            "warnings": [],
        }
    )
    
    return graph


def test_successful_graph_generation():
    """Test successful graph generation with default parameters."""
    mock_score = create_mock_score_data("numpy/numpy")
    mock_graph = create_mock_graph("numpy/numpy")
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph
        
        response = client.get("/api/graph?repo=numpy/numpy")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert data["repo"] == "numpy/numpy"
        assert data["schema_version"] == "1.0"
        assert "generated_at" in data
        assert len(data["graph"]["nodes"]) == 2
        assert len(data["graph"]["edges"]) == 1
        assert data["metadata"]["node_count"] == 2
        assert data["metadata"]["edge_count"] == 1
        assert isinstance(data["metadata"]["generation_time_ms"], int)


def test_graph_with_query_parameters():
    """Test graph generation with various query parameters."""
    mock_score = create_mock_score_data("test/repo")
    mock_graph = create_mock_graph("test/repo")
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph
        
        # Test with custom parameters
        response = client.get(
            "/api/graph?repo=test/repo&include_cves=false&max_releases=5&max_maintainers=3"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify build_graph was called with correct config
        assert mock_build_graph.called
        call_args = mock_build_graph.call_args
        config = call_args[0][2]  # Third argument is config
        assert config.include_cves is False
        assert config.max_releases == 5
        assert config.max_maintainers == 3


def test_graph_with_refresh_parameter():
    """Test that refresh parameter is passed to score_repo."""
    mock_score = create_mock_score_data("test/repo")
    mock_graph = create_mock_graph("test/repo")
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph
        
        response = client.get("/api/graph?repo=test/repo&refresh=true")
        
        assert response.status_code == 200
        
        # Verify score_repo was called with refresh=True
        assert mock_score_repo.called
        call_args = mock_score_repo.call_args
        assert call_args[1]["refresh"] is True


def test_graph_with_github_url():
    """Test that GitHub URLs are properly normalized."""
    mock_score = create_mock_score_data("owner/repo")
    mock_graph = create_mock_graph("owner/repo")
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph
        
        # Test with GitHub URL
        response = client.get("/api/graph?repo=https://github.com/owner/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify normalized repo name
        assert data["repo"] == "owner/repo"
        
        # Verify score_repo was called with normalized name
        mock_score_repo.assert_called_once()
        assert mock_score_repo.call_args[0][0] == "owner/repo"


def test_invalid_repo_format():
    """Test error handling for invalid repository format."""
    response = client.get("/api/graph?repo=invalid-format")
    
    assert response.status_code == 400
    data = response.json()
    
    # Should have error information
    assert "error" in data or "detail" in data


def test_repo_not_found():
    """Test error handling when repository doesn't exist."""
    with patch("api.app.score_repo") as mock_score_repo:
        mock_score_repo.side_effect = ValueError("Repository not found")
        
        response = client.get("/api/graph?repo=nonexistent/repo")
        
        assert response.status_code == 404
        data = response.json()
        
        # Should have error information
        assert "error" in data or "detail" in data


def test_empty_graph():
    """Test that empty graph (only repo node) returns valid structure."""
    mock_score = create_mock_score_data("empty/repo")
    
    # Create minimal graph with only repo node
    repo_node = Node(
        id="repo:empty/repo",
        type=NodeType.REPO,
        label="empty/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": "2026-02-13T10:00:00Z",
            "data_confidence": 0.9,
        }
    )
    
    empty_graph = Graph(
        nodes=[repo_node],
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
        mock_build_graph.return_value = empty_graph
        
        response = client.get("/api/graph?repo=empty/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Empty arrays, not null
        assert isinstance(data["graph"]["nodes"], list)
        assert isinstance(data["graph"]["edges"], list)
        assert len(data["graph"]["nodes"]) == 1
        assert len(data["graph"]["edges"]) == 0
        assert data["metadata"]["node_count"] == 1
        assert data["metadata"]["edge_count"] == 0


def test_graph_with_warnings():
    """Test that warnings from graph generation are included in response."""
    mock_score = create_mock_score_data("test/repo")
    mock_graph = create_mock_graph("test/repo")
    
    # Add warnings to graph metadata
    mock_graph.metadata["warnings"] = [
        {
            "source": "cve_nodes",
            "error": "Connection timeout",
            "impact": "CVE nodes not included"
        }
    ]
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Warnings should be included in metadata
        assert "warnings" in data["metadata"]
        assert len(data["metadata"]["warnings"]) == 1
        assert data["metadata"]["warnings"][0]["source"] == "cve_nodes"


def test_data_sources_in_metadata():
    """Test that data sources are correctly extracted from node provenance."""
    mock_score = create_mock_score_data("test/repo")
    
    # Create graph with nodes from different sources
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={"source": "github_api", "fetched_at": "2026-02-13T10:00:00Z", "data_confidence": 0.9}
    )
    
    cve_node = Node(
        id="cve:CVE-2024-1234",
        type=NodeType.CVE,
        label="CVE-2024-1234",
        metadata={},
        provenance={"source": "osv", "fetched_at": "2026-02-13T10:00:00Z", "data_confidence": 0.95}
    )
    
    risk_node = Node(
        id="risk:test/repo:days_since_release",
        type=NodeType.RISK_FACTOR,
        label="Days Since Release",
        metadata={},
        provenance={"source": "score_model", "fetched_at": "2026-02-13T10:00:00Z", "data_confidence": 0.9}
    )
    
    graph = Graph(
        nodes=[repo_node, cve_node, risk_node],
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
        mock_build_graph.return_value = graph
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should include all unique data sources
        data_sources = data["metadata"]["data_sources"]
        assert "github_api" in data_sources
        assert "osv" in data_sources
        assert "score_model" in data_sources
        assert len(data_sources) == 3


def test_invalid_query_parameter_values():
    """Test error handling for invalid query parameter values."""
    # Test with negative max_releases
    response = client.get("/api/graph?repo=test/repo&max_releases=-1")
    assert response.status_code in [400, 422]  # FastAPI validation error
    
    # Test with max_releases exceeding limit
    response = client.get("/api/graph?repo=test/repo&max_releases=1000")
    assert response.status_code in [400, 422]
    
    # Test with negative max_maintainers
    response = client.get("/api/graph?repo=test/repo&max_maintainers=0")
    assert response.status_code in [400, 422]


def test_generation_time_tracking():
    """Test that generation time is tracked and included in response."""
    mock_score = create_mock_score_data("test/repo")
    mock_graph = create_mock_graph("test/repo")
    
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = mock_score
        mock_build_graph.return_value = mock_graph
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have generation time
        assert "generation_time_ms" in data["metadata"]
        assert isinstance(data["metadata"]["generation_time_ms"], int)
        assert data["metadata"]["generation_time_ms"] >= 0
