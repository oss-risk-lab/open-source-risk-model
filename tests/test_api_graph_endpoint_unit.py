"""
Unit tests for /api/graph endpoint with database caching.

Tests specific scenarios for cache hit/miss, TTL, refresh, and fallback behavior.
"""

import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from api.app import app
from open_source_risk_model.graph.schema import Graph, Node, NodeType
from open_source_risk_model.persistence.errors import DatabaseError


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={"url": "https://github.com/test/repo"},
        provenance={"source": "github_api", "data_confidence": 1.0}
    )
    
    return Graph(
        nodes=[repo_node],
        edges=[],
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api"],
            "warnings": [],
        }
    )


def test_cache_hit_path(sample_graph):
    """
    Test cache hit path - database returns cached data.
    
    Validates: Requirements 6.2
    """
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_file_cache.get.return_value = None
        
        # Setup cached response
        graph_dict = sample_graph.to_dict()
        cached_response = {
            "repo": "test/repo",
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "graph": graph_dict,
            "metadata": {
                "node_count": 1,
                "edge_count": 0,
                "data_sources": ["github_api"],
                "cache_hit": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        
        mock_graph_repo.get_graph.return_value = cached_response
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify cache hit
        assert data["metadata"]["cache_hit"] is True
        
        # Verify score_repo and build_graph were NOT called
        assert not mock_score.called
        assert not mock_build.called


def test_cache_miss_path(sample_graph):
    """
    Test cache miss path - database returns None, dynamic generation occurs.
    
    Validates: Requirements 6.2
    """
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": "test/repo"}
        mock_build.return_value = sample_graph
        mock_file_cache.get.return_value = None
        mock_graph_repo.get_graph.return_value = None
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify cache miss
        assert data["metadata"]["cache_hit"] is False
        
        # Verify dynamic generation occurred
        assert mock_score.called
        assert mock_build.called
        
        # Verify save_graph was called
        assert mock_graph_repo.save_graph.called


def test_refresh_forces_regeneration(sample_graph):
    """
    Test refresh=true forces regeneration even if cached data exists.
    
    Validates: Requirements 6.5
    """
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": "test/repo"}
        mock_build.return_value = sample_graph
        mock_file_cache.get.return_value = None
        
        # Setup cached response (should be ignored due to refresh=true)
        graph_dict = sample_graph.to_dict()
        cached_response = {
            "repo": "test/repo",
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "graph": graph_dict,
            "metadata": {
                "node_count": 1,
                "edge_count": 0,
                "data_sources": ["github_api"],
                "cache_hit": True,
            }
        }
        
        mock_graph_repo.get_graph.return_value = cached_response
        
        response = client.get("/api/graph?repo=test/repo&refresh=true")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify regeneration occurred
        assert mock_score.called
        assert mock_build.called
        
        # Verify save_graph was called to update database
        assert mock_graph_repo.save_graph.called


def test_ttl_expiration_auto_refresh_false(sample_graph):
    """
    Test TTL expiration with auto_refresh_stale=false returns stale data with flag.
    
    Validates: Requirements 7.5
    """
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache, \
         patch.dict(os.environ, {"GRAPH_TTL_HOURS": "24", "GRAPH_AUTO_REFRESH_STALE": "false"}):
        
        mock_file_cache.get.return_value = None
        
        # Create stale cached response (48 hours old, TTL is 24 hours)
        updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
        graph_dict = sample_graph.to_dict()
        cached_response = {
            "repo": "test/repo",
            "schema_version": "1.0",
            "generated_at": updated_at.isoformat(),
            "graph": graph_dict,
            "metadata": {
                "node_count": 1,
                "edge_count": 0,
                "data_sources": ["github_api"],
                "cache_hit": True,
                "created_at": updated_at.isoformat(),
                "updated_at": updated_at.isoformat(),
            }
        }
        
        mock_graph_repo.get_graph.return_value = cached_response
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify stale data returned with flag
        assert data["metadata"]["cache_hit"] is True
        assert data["metadata"]["is_stale"] is True
        assert data["metadata"]["age_hours"] > 24
        
        # Verify no regeneration occurred
        assert not mock_score.called
        assert not mock_build.called


def test_ttl_expiration_auto_refresh_true(sample_graph):
    """
    Test TTL expiration with auto_refresh_stale=true triggers regeneration.
    
    Validates: Requirements 7.5
    """
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache, \
         patch.dict(os.environ, {"GRAPH_TTL_HOURS": "24", "GRAPH_AUTO_REFRESH_STALE": "true"}):
        
        mock_score.return_value = {"repo": "test/repo"}
        mock_build.return_value = sample_graph
        mock_file_cache.get.return_value = None
        
        # Create stale cached response (48 hours old, TTL is 24 hours)
        updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
        graph_dict = sample_graph.to_dict()
        cached_response = {
            "repo": "test/repo",
            "schema_version": "1.0",
            "generated_at": updated_at.isoformat(),
            "graph": graph_dict,
            "metadata": {
                "node_count": 1,
                "edge_count": 0,
                "data_sources": ["github_api"],
                "cache_hit": True,
                "created_at": updated_at.isoformat(),
                "updated_at": updated_at.isoformat(),
            }
        }
        
        mock_graph_repo.get_graph.return_value = cached_response
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify regeneration occurred
        assert mock_score.called
        assert mock_build.called
        
        # Verify save_graph was called to update database
        assert mock_graph_repo.save_graph.called


def test_database_unavailable_fallback(sample_graph):
    """
    Test database unavailable fallback to dynamic generation.
    
    Validates: Requirements 6.3, 9.3
    """
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": "test/repo"}
        mock_build.return_value = sample_graph
        mock_file_cache.get.return_value = None
        
        # Simulate database error
        mock_graph_repo.get_graph.side_effect = DatabaseError("Database unavailable")
        
        response = client.get("/api/graph?repo=test/repo")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify fallback to dynamic generation
        assert mock_score.called
        assert mock_build.called
        
        # Verify response is valid
        assert "repo" in data
        assert "graph" in data
        assert "metadata" in data
        assert data["metadata"]["cache_hit"] is False


def test_database_save_failure_does_not_fail_request(sample_graph):
    """
    Test that database save failure doesn't fail the request (best effort).
    
    Validates: Requirements 9.3
    """
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": "test/repo"}
        mock_build.return_value = sample_graph
        mock_file_cache.get.return_value = None
        mock_graph_repo.get_graph.return_value = None
        
        # Simulate save failure
        mock_graph_repo.save_graph.side_effect = DatabaseError("Save failed")
        
        response = client.get("/api/graph?repo=test/repo")
        
        # Request should still succeed
        assert response.status_code == 200
        data = response.json()
        
        # Verify response is valid
        assert "repo" in data
        assert "graph" in data
        assert "metadata" in data
        
        # Verify save was attempted
        assert mock_graph_repo.save_graph.called
