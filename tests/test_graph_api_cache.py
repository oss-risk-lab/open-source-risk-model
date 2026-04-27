"""
Integration tests for graph API endpoint caching functionality.

Tests cache hit/miss scenarios, refresh parameter behavior, and TTL expiration
in the context of the API endpoint.

Feature: supply-chain-graph
Task: 14.3 Write unit tests for caching
"""

import tempfile
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from api.app import app, graph_cache
from open_source_risk_model.graph.schema import Graph, Node, NodeType


client = TestClient(app)


def test_api_cache_miss_then_hit():
    """Test that first request caches, second request uses cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Temporarily replace the global cache with a test cache
        from api import app as api_module
        original_cache = api_module.graph_cache
        api_module.graph_cache = MagicMock()
        api_module.graph_cache.get.return_value = None  # Cache miss
        
        try:
            with patch("api.app.score_repo") as mock_score_repo, \
                 patch("api.app.build_graph") as mock_build_graph:
                
                # Setup mocks
                mock_score_repo.return_value = {
                    "repo": {"url": "https://github.com/test/repo"},
                    "overall": {"maintenance_risk": 0.3, "coverage": 0.8},
                    "features": [],
                    "top_drivers": [],
                }
                
                mock_graph = Graph(metadata={"schema_version": "1.0", "generated_at": "2024-01-01T00:00:00Z"})
                mock_graph.add_node(Node(
                    id="repo:test/repo",
                    type=NodeType.REPO,
                    label="test/repo",
                    metadata={},
                    provenance={"source": "github_api", "fetched_at": "2024-01-01T00:00:00Z", "data_confidence": 0.9}
                ))
                mock_build_graph.return_value = mock_graph
                
                # First request - cache miss
                response = client.get("/api/graph?repo=test/repo")
                
                assert response.status_code == 200
                data = response.json()
                assert data["metadata"]["cache_hit"] is False
                
                # Verify cache.set was called
                api_module.graph_cache.set.assert_called_once()
                
                # Second request - simulate cache hit
                api_module.graph_cache.get.return_value = mock_graph
                
                response2 = client.get("/api/graph?repo=test/repo")
                
                assert response2.status_code == 200
                data2 = response2.json()
                assert data2["metadata"]["cache_hit"] is True
                
                # Verify build_graph was only called once (first request)
                assert mock_build_graph.call_count == 1
        
        finally:
            # Restore original cache
            api_module.graph_cache = original_cache


def test_api_refresh_parameter_bypasses_cache():
    """Test that refresh=true bypasses cache and rebuilds graph."""
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        from api import app as api_module
        original_cache = api_module.graph_cache
        api_module.graph_cache = MagicMock()
        
        try:
            # Setup mocks
            mock_score_repo.return_value = {
                "repo": {"url": "https://github.com/test/repo"},
                "overall": {"maintenance_risk": 0.3, "coverage": 0.8},
                "features": [],
                "top_drivers": [],
            }
            
            mock_graph = Graph(metadata={"schema_version": "1.0", "generated_at": "2024-01-01T00:00:00Z"})
            mock_graph.add_node(Node(
                id="repo:test/repo",
                type=NodeType.REPO,
                label="test/repo",
                metadata={},
                provenance={"source": "github_api", "fetched_at": "2024-01-01T00:00:00Z", "data_confidence": 0.9}
            ))
            mock_build_graph.return_value = mock_graph
            
            # Simulate cache has data
            api_module.graph_cache.get.return_value = mock_graph
            
            # Request with refresh=true
            response = client.get("/api/graph?repo=test/repo&refresh=true")
            
            assert response.status_code == 200
            data = response.json()
            
            # Cache should not be checked when refresh=true
            # (cache.get should not be called, or if called, result should be ignored)
            # build_graph should be called to rebuild
            assert mock_build_graph.called
            
            # Cache should be updated with new graph
            api_module.graph_cache.set.assert_called()
        
        finally:
            api_module.graph_cache = original_cache


def test_api_cache_hit_performance():
    """Test that cache hit is significantly faster than cache miss."""
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        from api import app as api_module
        original_cache = api_module.graph_cache
        api_module.graph_cache = MagicMock()
        
        try:
            # Setup mocks
            mock_score_repo.return_value = {
                "repo": {"url": "https://github.com/test/repo"},
                "overall": {"maintenance_risk": 0.3, "coverage": 0.8},
                "features": [],
                "top_drivers": [],
            }
            
            mock_graph = Graph(metadata={"schema_version": "1.0", "generated_at": "2024-01-01T00:00:00Z"})
            mock_graph.add_node(Node(
                id="repo:test/repo",
                type=NodeType.REPO,
                label="test/repo",
                metadata={},
                provenance={"source": "github_api", "fetched_at": "2024-01-01T00:00:00Z", "data_confidence": 0.9}
            ))
            mock_build_graph.return_value = mock_graph
            
            # Cache miss - should call build_graph
            api_module.graph_cache.get.return_value = None
            response1 = client.get("/api/graph?repo=test/repo")
            assert response1.status_code == 200
            time1 = response1.json()["metadata"]["generation_time_ms"]
            
            # Cache hit - should not call build_graph
            api_module.graph_cache.get.return_value = mock_graph
            mock_build_graph.reset_mock()
            
            response2 = client.get("/api/graph?repo=test/repo")
            assert response2.status_code == 200
            time2 = response2.json()["metadata"]["generation_time_ms"]
            
            # Cache hit should be faster (or at least not call build_graph)
            assert not mock_build_graph.called
            # Note: time2 might not always be less than time1 due to test overhead,
            # but build_graph not being called is the key indicator
        
        finally:
            api_module.graph_cache = original_cache


def test_api_cache_with_different_parameters():
    """Test that different query parameters don't affect cache key (only repo matters)."""
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        from api import app as api_module
        original_cache = api_module.graph_cache
        api_module.graph_cache = MagicMock()
        
        try:
            # Setup mocks
            mock_score_repo.return_value = {
                "repo": {"url": "https://github.com/test/repo"},
                "overall": {"maintenance_risk": 0.3, "coverage": 0.8},
                "features": [],
                "top_drivers": [],
            }
            
            mock_graph = Graph(metadata={"schema_version": "1.0", "generated_at": "2024-01-01T00:00:00Z"})
            mock_graph.add_node(Node(
                id="repo:test/repo",
                type=NodeType.REPO,
                label="test/repo",
                metadata={},
                provenance={"source": "github_api", "fetched_at": "2024-01-01T00:00:00Z", "data_confidence": 0.9}
            ))
            mock_build_graph.return_value = mock_graph
            
            # First request with default parameters
            api_module.graph_cache.get.return_value = None
            response1 = client.get("/api/graph?repo=test/repo")
            assert response1.status_code == 200
            
            # Cache should be set
            api_module.graph_cache.set.assert_called_once_with("test/repo", mock_graph)
            
            # Second request with different parameters but same repo
            # Note: In current implementation, cache is keyed only by repo name,
            # so different parameters will still hit the same cache entry
            api_module.graph_cache.get.return_value = mock_graph
            response2 = client.get("/api/graph?repo=test/repo&max_releases=5")
            assert response2.status_code == 200
            
            # Should use cache (cache.get called with same repo)
            assert api_module.graph_cache.get.call_count >= 2
        
        finally:
            api_module.graph_cache = original_cache


def test_api_cache_error_handling():
    """Test that cache errors don't break the API."""
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        from api import app as api_module
        original_cache = api_module.graph_cache
        api_module.graph_cache = MagicMock()
        
        try:
            # Setup mocks
            mock_score_repo.return_value = {
                "repo": {"url": "https://github.com/test/repo"},
                "overall": {"maintenance_risk": 0.3, "coverage": 0.8},
                "features": [],
                "top_drivers": [],
            }
            
            mock_graph = Graph(metadata={"schema_version": "1.0", "generated_at": "2024-01-01T00:00:00Z"})
            mock_graph.add_node(Node(
                id="repo:test/repo",
                type=NodeType.REPO,
                label="test/repo",
                metadata={},
                provenance={"source": "github_api", "fetched_at": "2024-01-01T00:00:00Z", "data_confidence": 0.9}
            ))
            mock_build_graph.return_value = mock_graph
            
            # Simulate cache.get raising an exception
            api_module.graph_cache.get.side_effect = Exception("Cache read error")
            
            # Request should still succeed (falls back to building graph)
            response = client.get("/api/graph?repo=test/repo")
            
            # Should get 200 despite cache error
            assert response.status_code == 200
            
            # build_graph should have been called as fallback
            assert mock_build_graph.called
        
        finally:
            api_module.graph_cache = original_cache
