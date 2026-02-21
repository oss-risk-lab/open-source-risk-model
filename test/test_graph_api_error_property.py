"""
Property-based tests for /api/graph endpoint error handling.

Feature: supply-chain-graph
Property 10: Error Response Status Codes

For any API request that results in an error, the response must return
an appropriate HTTP status code:
- 400 for bad requests (invalid input)
- 404 for not found (repo doesn't exist)
- 500 for server errors (internal processing errors)
- 503 for service unavailable (external API failures)

Validates: Requirements US-2.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st, settings
from fastapi.testclient import TestClient
from unittest.mock import patch

from api.app import app


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


# Hypothesis strategies for generating invalid inputs
@st.composite
def invalid_repo_names(draw):
    """Generate invalid repository names that should trigger 400 errors."""
    # Generate realistic invalid formats that won't cause URL parsing errors
    invalid_format_type = draw(st.integers(min_value=0, max_value=3))
    
    if invalid_format_type == 0:
        # Missing slash - just a single word
        return draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=20))
    elif invalid_format_type == 1:
        # Too many slashes
        owner = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10))
        repo = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10))
        extra = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10))
        return f"{owner}/{repo}/{extra}"
    elif invalid_format_type == 2:
        # Just a slash
        return "/"
    else:
        # Special characters that aren't allowed (but safe for URLs)
        owner = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10))
        return f"{owner}@invalid"


# Property 10: Error Response Status Codes
@settings(max_examples=50, deadline=None)
@given(invalid_repo=invalid_repo_names())
def test_invalid_repo_format_returns_400(invalid_repo):
    """
    Property 10a: Invalid repository format returns 400 Bad Request.
    
    For any invalid repository format, the API must return 400.
    
    Validates: Requirements US-2.5
    """
    response = client.get(f"/api/graph?repo={invalid_repo}")
    
    # Should return 400 Bad Request for invalid format
    assert response.status_code == 400, \
        f"Expected 400 for invalid repo '{invalid_repo}', got {response.status_code}"
    
    # Response should be JSON with error structure
    data = response.json()
    assert "error" in data or "detail" in data, \
        "Error response must include error information"


def test_repo_not_found_returns_404():
    """
    Property 10b: Repository not found returns 404.
    
    When a repository doesn't exist, the API must return 404.
    
    Validates: Requirements US-2.5
    """
    # Mock score_repo to raise ValueError indicating repo not found
    with patch("api.app.score_repo") as mock_score_repo:
        mock_score_repo.side_effect = ValueError("Repository not found")
        
        response = client.get("/api/graph?repo=nonexistent/repo")
        
        # Should return 404 Not Found
        assert response.status_code == 404, \
            f"Expected 404 for non-existent repo, got {response.status_code}"
        
        # Response should include error information
        data = response.json()
        assert "error" in data or "detail" in data


def test_internal_error_returns_500():
    """
    Property 10c: Internal processing errors return 500.
    
    When an unexpected internal error occurs, the API must return 500.
    
    Validates: Requirements US-2.5
    """
    # Mock build_graph to raise an unexpected exception
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = {
            "repo": {"url": "https://github.com/test/repo"},
            "overall": {"maintenance_risk": 0.5, "maintenance_label": "medium", "coverage": 0.5, "confidence": "medium"},
            "features": [],
            "top_drivers": [],
        }
        
        # Simulate internal error
        mock_build_graph.side_effect = RuntimeError("Unexpected internal error")
        
        response = client.get("/api/graph?repo=test/repo")
        
        # Should return 500 Internal Server Error
        assert response.status_code == 500, \
            f"Expected 500 for internal error, got {response.status_code}"
        
        # Response should include error information
        data = response.json()
        assert "error" in data or "detail" in data


def test_external_api_failure_returns_503():
    """
    Property 10d: External API failures return 503.
    
    When an external API (GitHub, OSV.dev) is unavailable, the API must return 503.
    
    Validates: Requirements US-2.5
    """
    # Mock build_graph to raise a connection/timeout error
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        
        mock_score_repo.return_value = {
            "repo": {"url": "https://github.com/test/repo"},
            "overall": {"maintenance_risk": 0.5, "maintenance_label": "medium", "coverage": 0.5, "confidence": "medium"},
            "features": [],
            "top_drivers": [],
        }
        
        # Simulate external API timeout
        mock_build_graph.side_effect = Exception("Connection timeout after 5s")
        
        response = client.get("/api/graph?repo=test/repo")
        
        # Should return 503 Service Unavailable
        assert response.status_code == 503, \
            f"Expected 503 for external API failure, got {response.status_code}"
        
        # Response should include error information
        data = response.json()
        assert "error" in data or "detail" in data


@settings(max_examples=50, deadline=None)
@given(
    max_releases=st.integers(min_value=-100, max_value=0),
)
def test_invalid_query_parameters_return_400(max_releases):
    """
    Property 10e: Invalid query parameters return 400.
    
    For any invalid query parameter values, the API must return 400.
    
    Validates: Requirements US-2.5
    """
    # Test with invalid max_releases (negative or zero)
    response = client.get(f"/api/graph?repo=test/repo&max_releases={max_releases}")
    
    # Should return 422 (FastAPI validation error) or 400
    assert response.status_code in [400, 422], \
        f"Expected 400/422 for invalid parameter, got {response.status_code}"


def test_error_response_structure():
    """
    Test that error responses have consistent structure.
    
    All error responses should include error information in a consistent format.
    
    Validates: Requirements US-2.5
    """
    # Test with invalid repo format
    response = client.get("/api/graph?repo=invalid-format")
    
    assert response.status_code == 400
    data = response.json()
    
    # Should have error information (either 'error' or 'detail' key)
    assert "error" in data or "detail" in data, \
        "Error response must include error information"
    
    # If using structured error format, verify structure
    if "error" in data:
        error = data["error"]
        assert "code" in error or "message" in error, \
            "Structured error must include code or message"


def test_multiple_error_scenarios():
    """
    Test various error scenarios to ensure proper status codes.
    
    This is a concrete example test to complement the property tests.
    """
    # Test 1: Invalid format
    response = client.get("/api/graph?repo=no-slash")
    assert response.status_code == 400
    
    # Test 2: Empty repo
    response = client.get("/api/graph?repo=")
    assert response.status_code in [400, 422]  # FastAPI may return 422 for missing required param
    
    # Test 3: Repo not found
    with patch("api.app.score_repo") as mock_score_repo:
        mock_score_repo.side_effect = ValueError("Repository does not exist")
        response = client.get("/api/graph?repo=fake/repo")
        assert response.status_code == 404
    
    # Test 4: External API timeout
    with patch("api.app.score_repo") as mock_score_repo, \
         patch("api.app.build_graph") as mock_build_graph:
        mock_score_repo.return_value = {
            "repo": {"url": "https://github.com/test/repo"},
            "overall": {"maintenance_risk": 0.5, "maintenance_label": "medium", "coverage": 0.5, "confidence": "medium"},
            "features": [],
            "top_drivers": [],
        }
        mock_build_graph.side_effect = Exception("OSV.dev API unavailable")
        response = client.get("/api/graph?repo=test/repo")
        assert response.status_code == 503
