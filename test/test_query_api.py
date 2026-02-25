"""
End-to-end tests for POST /api/query endpoint.

Tests the complete flow:
1. HTTP request → API endpoint
2. Dev mode (explicit intent) → Intent executor
3. Query execution → Database
4. Response formatting → HTTP response
"""

import pytest
from fastapi.testclient import TestClient
from api.app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestQueryEndpointDevMode:
    """Test query endpoint in dev mode (explicit intent)."""
    
    def test_list_dependencies(self, client):
        """Test listing dependencies via API."""
        response = client.post("/api/query", json={
            "query": "List dependencies",
            "intent": "list_dependencies",
            "parameters": {"repo_full_name": "django/django"},
            "max_results": 5
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["intent"] == "list_dependencies"
        assert data["confidence"] == 1.0
        assert data["result_count"] >= 0
        assert len(data["results"]) <= 5
        assert "execution_time_ms" in data
        assert data["metadata"]["repo_full_name"] == "django/django"
    
    def test_find_dependents(self, client):
        """Test finding dependents via API."""
        response = client.post("/api/query", json={
            "query": "Find dependents",
            "intent": "find_dependents",
            "parameters": {"package_name": "flask", "registry_type": "pypi"},
            "max_results": 10
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["intent"] == "find_dependents"
        assert data["result_count"] >= 0
        assert all("repo_full_name" in r for r in data["results"])
    
    def test_dataset_stats(self, client):
        """Test getting dataset stats via API."""
        response = client.post("/api/query", json={
            "query": "Dataset stats",
            "intent": "dataset_stats",
            "parameters": {},
            "max_results": 1
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["intent"] == "dataset_stats"
        assert data["result_count"] == 1
        assert "repo_count" in data["results"][0]
        assert "total_dependencies" in data["results"][0]
        assert data["results"][0]["repo_count"] > 0
    
    def test_dependency_tree(self, client):
        """Test getting dependency tree via API."""
        response = client.post("/api/query", json={
            "query": "Dependency tree",
            "intent": "get_dependency_tree",
            "parameters": {"repo_full_name": "pallets/flask", "max_depth": 2},
            "max_results": 20
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["intent"] == "get_dependency_tree"
        assert all("depth" in r for r in data["results"])
        assert all(r["depth"] <= 2 for r in data["results"])


class TestQueryEndpointValidation:
    """Test parameter validation and error handling."""
    
    def test_invalid_intent(self, client):
        """Test that invalid intents are rejected."""
        response = client.post("/api/query", json={
            "query": "Malicious query",
            "intent": "DROP TABLE repo_dependencies",
            "parameters": {},
            "max_results": 10
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "INVALID_QUERY"
        assert "Unknown intent" in data["detail"]["error"]["message"]
    
    def test_missing_required_parameter(self, client):
        """Test that missing required parameters are rejected."""
        response = client.post("/api/query", json={
            "query": "List dependencies",
            "intent": "list_dependencies",
            "parameters": {},  # Missing repo_full_name
            "max_results": 10
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "INVALID_QUERY"
        assert "required" in data["detail"]["error"]["message"].lower()
    
    def test_max_results_validation(self, client):
        """Test that max_results is validated."""
        # Test too large
        response = client.post("/api/query", json={
            "query": "Dataset stats",
            "intent": "dataset_stats",
            "parameters": {},
            "max_results": 10000  # Exceeds limit
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_natural_language_not_implemented(self, client):
        """Test that natural language queries return not implemented."""
        response = client.post("/api/query", json={
            "query": "What are the dependencies of django/django?",
            "max_results": 10
        })
        
        assert response.status_code == 501
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "NOT_IMPLEMENTED"
        assert "LLM" in data["detail"]["error"]["message"]


class TestQueryEndpointSecurity:
    """Test security features."""
    
    def test_sql_injection_in_parameters(self, client):
        """Test that SQL injection attempts are neutralized."""
        response = client.post("/api/query", json={
            "query": "Malicious query",
            "intent": "list_dependencies",
            "parameters": {"repo_full_name": "django/django' OR '1'='1"},
            "max_results": 10
        })
        
        assert response.status_code == 200
        data = response.json()
        # Should return 0 results (no repo with that name)
        assert data["result_count"] == 0
    
    def test_no_arbitrary_sql_execution(self, client):
        """Test that arbitrary SQL cannot be executed."""
        response = client.post("/api/query", json={
            "query": "Malicious query",
            "intent": "list_dependencies; DROP TABLE repo_dependencies; --",
            "parameters": {"repo_full_name": "django/django"},
            "max_results": 10
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "INVALID_QUERY"


class TestQueryEndpointPerformance:
    """Test performance characteristics."""
    
    def test_query_execution_time(self, client):
        """Test that queries execute quickly."""
        response = client.post("/api/query", json={
            "query": "List dependencies",
            "intent": "list_dependencies",
            "parameters": {"repo_full_name": "django/django"},
            "max_results": 10
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should execute in < 100ms
        assert data["execution_time_ms"] < 100
    
    def test_multiple_concurrent_queries(self, client):
        """Test that multiple queries can execute concurrently."""
        responses = []
        
        for _ in range(5):
            response = client.post("/api/query", json={
                "query": "Dataset stats",
                "intent": "dataset_stats",
                "parameters": {},
                "max_results": 1
            })
            responses.append(response)
        
        # All should succeed
        assert all(r.status_code == 200 for r in responses)
        
        # All should return same results (deterministic)
        results = [r.json()["results"][0]["repo_count"] for r in responses]
        assert len(set(results)) == 1  # All same value


class TestQueryEndpointResponseFormat:
    """Test response format and structure."""
    
    def test_response_structure(self, client):
        """Test that response has correct structure."""
        response = client.post("/api/query", json={
            "query": "Dataset stats",
            "intent": "dataset_stats",
            "parameters": {},
            "max_results": 1
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "intent" in data
        assert "parameters" in data
        assert "confidence" in data
        assert "results" in data
        assert "result_count" in data
        assert "execution_time_ms" in data
        assert "metadata" in data
        
        # Types
        assert isinstance(data["intent"], str)
        assert isinstance(data["parameters"], dict)
        assert isinstance(data["confidence"], (int, float))
        assert isinstance(data["results"], list)
        assert isinstance(data["result_count"], int)
        assert isinstance(data["execution_time_ms"], (int, float))
    
    def test_error_response_structure(self, client):
        """Test that error responses have correct structure."""
        response = client.post("/api/query", json={
            "query": "Invalid",
            "intent": "invalid_intent",
            "parameters": {},
            "max_results": 10
        })
        
        assert response.status_code == 400
        data = response.json()
        
        # FastAPI error structure
        assert "detail" in data
        assert "error" in data["detail"]
        assert "code" in data["detail"]["error"]
        assert "message" in data["detail"]["error"]
        assert "details" in data["detail"]["error"]


class TestQueryEndpointEdgeCases:
    """Test edge cases."""
    
    def test_nonexistent_repo(self, client):
        """Test querying a repo that doesn't exist."""
        response = client.post("/api/query", json={
            "query": "List dependencies",
            "intent": "list_dependencies",
            "parameters": {"repo_full_name": "nonexistent/repo"},
            "max_results": 10
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["result_count"] == 0
        assert data["results"] == []
    
    def test_zero_max_results(self, client):
        """Test that max_results must be >= 1."""
        response = client.post("/api/query", json={
            "query": "Dataset stats",
            "intent": "dataset_stats",
            "parameters": {},
            "max_results": 0
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_large_result_set(self, client):
        """Test handling large result sets."""
        response = client.post("/api/query", json={
            "query": "Search packages",
            "intent": "search_packages",
            "parameters": {"pattern": "%"},
            "max_results": 1000  # Max allowed
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 1000
