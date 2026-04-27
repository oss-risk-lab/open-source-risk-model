"""
Property-based tests for API cache behavior.

Tests Property 14: Cache Behavior Correctness
Tests Property 15: Fallback to Dynamic Generation
"""

import pytest
import os
from hypothesis import given, settings, strategies as st
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from api.app import app
from open_source_risk_model.graph.schema import Graph, Node, Edge, NodeType, EdgeType
from open_source_risk_model.persistence.errors import DatabaseError


# Strategy for generating valid repository names
@st.composite
def repo_name_strategy(draw):
    """Generate valid repository names in owner/repo format."""
    owner = draw(st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,19}", fullmatch=True))
    repo = draw(st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,19}", fullmatch=True))
    return f"{owner}/{repo}"


# Strategy for generating valid graph objects
@st.composite
def graph_strategy(draw):
    """Generate valid Graph objects."""
    repo_name = draw(repo_name_strategy())
    
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


@settings(max_examples=50, deadline=None)
@given(graph_data=graph_strategy())
def test_property_14_cache_behavior_correctness(graph_data):
    """
    Feature: multi-repo-persistent-graph, Property 14: Cache Behavior Correctness
    
    For any repository in the database, querying without refresh=true should return
    cached data (cache_hit=true), while querying with refresh=true should regenerate
    and update the database.
    
    Validates: Requirements 6.2, 6.5
    """
    repo_name, graph_obj = graph_data
    
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": repo_name}
        mock_build.return_value = graph_obj
        mock_file_cache.get.return_value = None
        
        # Setup cached response
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
        
        # Test 1: Query without refresh should return cached data
        mock_graph_repo.get_graph.return_value = cached_response
        
        response = client.get(f"/api/graph?repo={repo_name}")
        assert response.status_code == 200
        data = response.json()
        
        # Should return cached data
        assert data["metadata"]["cache_hit"] is True
        
        # Test 2: Query with refresh=true should regenerate
        mock_graph_repo.get_graph.return_value = None  # Simulate cache bypass
        
        response2 = client.get(f"/api/graph?repo={repo_name}&refresh=true")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Should regenerate (cache_hit=False)
        assert data2["metadata"]["cache_hit"] is False
        
        # Verify save_graph was called to update database
        assert mock_graph_repo.save_graph.called


@settings(max_examples=50, deadline=None)
@given(
    graph_data=graph_strategy(),
    ttl_hours=st.floats(min_value=1.0, max_value=48.0),
    age_hours=st.floats(min_value=0.0, max_value=72.0),
)
def test_property_14_ttl_behavior(graph_data, ttl_hours, age_hours):
    """
    Feature: multi-repo-persistent-graph, Property 14: Cache Behavior Correctness
    
    TTL logic should correctly determine whether cached data is fresh or stale.
    
    Validates: Requirements 6.2, 6.5
    """
    repo_name, graph_obj = graph_data
    
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache, \
         patch.dict(os.environ, {"GRAPH_TTL_HOURS": str(ttl_hours), "GRAPH_AUTO_REFRESH_STALE": "false"}):
        
        mock_score.return_value = {"repo": repo_name}
        mock_build.return_value = graph_obj
        mock_file_cache.get.return_value = None
        
        # Create cached response with specific age
        updated_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        graph_dict = graph_obj.to_dict()
        cached_response = {
            "repo": repo_name,
            "schema_version": "1.0",
            "generated_at": updated_at.isoformat(),
            "graph": graph_dict,
            "metadata": {
                "node_count": len(graph_obj.nodes),
                "edge_count": len(graph_obj.edges),
                "data_sources": ["github_api"],
                "cache_hit": True,
                "created_at": updated_at.isoformat(),
                "updated_at": updated_at.isoformat(),
            }
        }
        
        mock_graph_repo.get_graph.return_value = cached_response
        
        response = client.get(f"/api/graph?repo={repo_name}")
        assert response.status_code == 200
        data = response.json()
        
        # Verify TTL logic
        if age_hours < ttl_hours:
            # Fresh data - should return cached without is_stale flag
            assert data["metadata"]["cache_hit"] is True
            assert "is_stale" not in data["metadata"] or data["metadata"].get("is_stale") is False
        else:
            # Stale data - should return with is_stale flag (auto_refresh_stale=false)
            assert data["metadata"]["cache_hit"] is True
            assert data["metadata"].get("is_stale") is True


@settings(max_examples=50, deadline=None)
@given(graph_data=graph_strategy())
def test_property_15_fallback_to_dynamic_generation(graph_data):
    """
    Feature: multi-repo-persistent-graph, Property 15: Fallback to Dynamic Generation
    
    For any repository, if the database is unavailable, the /api/graph endpoint
    should still return valid graph data generated dynamically.
    
    Validates: Requirements 6.3, 9.3
    """
    repo_name, graph_obj = graph_data
    
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": repo_name}
        mock_build.return_value = graph_obj
        mock_file_cache.get.return_value = None
        
        # Simulate database error
        mock_graph_repo.get_graph.side_effect = DatabaseError("Database unavailable")
        
        # Request should still succeed with dynamic generation
        response = client.get(f"/api/graph?repo={repo_name}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "repo" in data
        assert "graph" in data
        assert "metadata" in data
        assert data["repo"] == repo_name
        
        # Should have generated dynamically
        assert data["metadata"]["cache_hit"] is False
        
        # Verify build_graph was called
        assert mock_build.called


@settings(max_examples=50, deadline=None)
@given(graph_data=graph_strategy())
def test_property_15_best_effort_save_on_error(graph_data):
    """
    Feature: multi-repo-persistent-graph, Property 15: Fallback to Dynamic Generation
    
    If database save fails after dynamic generation, the request should still
    succeed and return the generated graph.
    
    Validates: Requirements 6.3, 9.3
    """
    repo_name, graph_obj = graph_data
    
    client = TestClient(app)
    
    with patch('api.app.score_repo') as mock_score, \
         patch('api.app.build_graph') as mock_build, \
         patch('api.app.graph_repo') as mock_graph_repo, \
         patch('api.app.graph_cache') as mock_file_cache:
        
        mock_score.return_value = {"repo": repo_name}
        mock_build.return_value = graph_obj
        mock_file_cache.get.return_value = None
        
        # Database read succeeds (returns None), but save fails
        mock_graph_repo.get_graph.return_value = None
        mock_graph_repo.save_graph.side_effect = DatabaseError("Save failed")
        
        # Request should still succeed
        response = client.get(f"/api/graph?repo={repo_name}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "repo" in data
        assert "graph" in data
        assert "metadata" in data
        assert data["repo"] == repo_name
        
        # Should have generated dynamically
        assert data["metadata"]["cache_hit"] is False
        
        # Verify build_graph was called
        assert mock_build.called
        
        # Verify save was attempted (best effort)
        assert mock_graph_repo.save_graph.called
