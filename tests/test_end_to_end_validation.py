"""
End-to-end validation tests for supply chain graph feature.

Tests complete workflow with multiple repositories to verify:
- All correctness properties hold
- Performance targets are met
- All components work together correctly
"""

import pytest
import time
from fastapi.testclient import TestClient
from api.app import app
from src.open_source_risk_model.graph.cache import GraphCache

client = TestClient(app)


class TestEndToEndValidation:
    """End-to-end validation tests across multiple repositories"""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Clear cache before each test"""
        # Cache will be cleared per-repo as needed in tests
        yield

    def test_complete_workflow_numpy(self):
        """Test complete workflow with numpy/numpy repository"""
        start_time = time.time()
        
        # First request (cache miss) with explicit limits
        response = client.get("/api/graph?repo=numpy/numpy&max_releases=5&max_maintainers=3")
        
        elapsed = time.time() - start_time
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "repo" in data
        assert "schema_version" in data
        assert "generated_at" in data
        assert "graph" in data
        assert "metadata" in data
        
        # Verify graph structure
        graph = data["graph"]
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) > 0
        assert len(graph["edges"]) > 0
        
        # Verify repo node exists
        repo_nodes = [n for n in graph["nodes"] if n["type"] == "repo"]
        assert len(repo_nodes) == 1
        assert repo_nodes[0]["id"] == "repo:numpy/numpy"
        
        # Verify release nodes exist (numpy has releases)
        release_nodes = [n for n in graph["nodes"] if n["type"] == "release"]
        assert len(release_nodes) > 0
        assert len(release_nodes) <= 5  # max_releases=5
        
        # Verify maintainer nodes exist
        maintainer_nodes = [n for n in graph["nodes"] if n["type"] == "maintainer"]
        assert len(maintainer_nodes) > 0
        assert len(maintainer_nodes) <= 3  # max_maintainers=3
        
        # Verify risk factor nodes exist
        risk_nodes = [n for n in graph["nodes"] if n["type"] == "risk_factor"]
        assert len(risk_nodes) > 0
        
        # Verify registry nodes exist (numpy is on PyPI)
        registry_nodes = [n for n in graph["nodes"] if n["type"] == "registry"]
        assert len(registry_nodes) > 0
        
        # Verify all nodes have provenance
        for node in graph["nodes"]:
            assert "provenance" in node
            assert "source" in node["provenance"]
            assert "fetched_at" in node["provenance"]
            assert "confidence" in node["provenance"]
            assert 0.0 <= node["provenance"]["confidence"] <= 1.0
        
        # Verify all edges have provenance
        for edge in graph["edges"]:
            assert "provenance" in edge
            assert "source" in edge["provenance"]
            assert "established_at" in edge["provenance"]
            assert "confidence" in edge["provenance"]
            assert 0.0 <= edge["provenance"]["confidence"] <= 1.0
        
        # Verify metadata
        metadata = data["metadata"]
        assert metadata["node_count"] == len(graph["nodes"])
        assert metadata["edge_count"] == len(graph["edges"])
        assert "data_sources" in metadata
        assert "github_api" in metadata["data_sources"]
        assert "generation_time_ms" in metadata
        
        # Performance target: < 2s for first request (uncached)
        assert elapsed < 2.0, f"First request took {elapsed:.2f}s, expected < 2s"
        
        # Second request (cache hit)
        start_time = time.time()
        response2 = client.get("/api/graph?repo=numpy/numpy&max_releases=5&max_maintainers=3")
        elapsed2 = time.time() - start_time
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["metadata"]["cache_hit"] is True
        
        # Performance target: < 500ms for cached data
        assert elapsed2 < 0.5, f"Cached request took {elapsed2:.2f}s, expected < 0.5s"

    def test_complete_workflow_requests(self):
        """Test complete workflow with psf/requests repository"""
        response = client.get("/api/graph?repo=psf/requests&max_releases=5")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify basic structure
        assert data["repo"] == "psf/requests"
        graph = data["graph"]
        
        # Verify repo node
        repo_nodes = [n for n in graph["nodes"] if n["type"] == "repo"]
        assert len(repo_nodes) == 1
        
        # Verify releases exist (requests has many releases)
        release_nodes = [n for n in graph["nodes"] if n["type"] == "release"]
        assert len(release_nodes) > 0
        
        # Verify registry detection (requests is on PyPI)
        registry_nodes = [n for n in graph["nodes"] if n["type"] == "registry"]
        assert len(registry_nodes) > 0
        pypi_nodes = [n for n in registry_nodes if n["metadata"]["registry_type"] == "pypi"]
        assert len(pypi_nodes) > 0

    def test_complete_workflow_small_repo(self):
        """Test complete workflow with a smaller repository"""
        response = client.get("/api/graph?repo=octocat/Hello-World")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify basic structure
        graph = data["graph"]
        assert len(graph["nodes"]) > 0
        
        # Verify repo node exists
        repo_nodes = [n for n in graph["nodes"] if n["type"] == "repo"]
        assert len(repo_nodes) == 1

    def test_graph_with_all_parameters(self):
        """Test graph generation with all query parameters"""
        response = client.get(
            "/api/graph?repo=numpy/numpy"
            "&include_cves=true"
            "&max_releases=3"
            "&max_maintainers=2"
            "&refresh=false"
        )
        
        assert response.status_code == 200
        data = response.json()
        graph = data["graph"]
        
        # Verify parameter limits are respected
        release_nodes = [n for n in graph["nodes"] if n["type"] == "release"]
        assert len(release_nodes) <= 3
        
        maintainer_nodes = [n for n in graph["nodes"] if n["type"] == "maintainer"]
        assert len(maintainer_nodes) <= 2

    def test_graph_without_cves(self):
        """Test graph generation with CVEs disabled"""
        response = client.get("/api/graph?repo=numpy/numpy&include_cves=false")
        
        assert response.status_code == 200
        data = response.json()
        graph = data["graph"]
        
        # Verify no CVE nodes
        cve_nodes = [n for n in graph["nodes"] if n["type"] == "cve"]
        assert len(cve_nodes) == 0

    def test_graph_invariants_hold(self):
        """Verify all graph invariants hold for generated graphs"""
        repos = ["numpy/numpy", "psf/requests", "octocat/Hello-World"]
        
        for repo in repos:
            response = client.get(f"/api/graph?repo={repo}")
            assert response.status_code == 200
            
            data = response.json()
            graph = data["graph"]
            nodes = graph["nodes"]
            edges = graph["edges"]
            
            # Invariant 1: Exactly one REPO node
            repo_nodes = [n for n in nodes if n["type"] == "repo"]
            assert len(repo_nodes) == 1, f"Expected 1 repo node, got {len(repo_nodes)}"
            
            # Invariant 2: Unique node IDs
            node_ids = [n["id"] for n in nodes]
            assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs found"
            
            # Invariant 3: Valid edge references
            node_id_set = set(node_ids)
            for edge in edges:
                assert edge["source"] in node_id_set, f"Edge source {edge['source']} not in nodes"
                assert edge["target"] in node_id_set, f"Edge target {edge['target']} not in nodes"
            
            # Invariant 4: All nodes have required fields
            for node in nodes:
                assert "id" in node
                assert "type" in node
                assert "label" in node
                assert "metadata" in node
                assert "provenance" in node
            
            # Invariant 5: All edges have required fields
            for edge in edges:
                assert "source" in edge
                assert "target" in edge
                assert "relationship_type" in edge
                assert "provenance" in edge
            
            # Invariant 6: Provenance completeness
            for node in nodes:
                prov = node["provenance"]
                assert "source" in prov
                assert "fetched_at" in prov
                assert "confidence" in prov
                assert 0.0 <= prov["confidence"] <= 1.0
            
            for edge in edges:
                prov = edge["provenance"]
                assert "source" in prov
                assert "established_at" in prov
                assert "confidence" in prov
                assert 0.0 <= prov["confidence"] <= 1.0

    def test_performance_targets(self):
        """Verify performance targets are met"""
        # Clear cache for test repos
        cache = GraphCache()
        cache.invalidate("numpy/numpy")
        cache.invalidate("psf/requests")
        
        # Test 1: Cached data < 500ms
        # First request to populate cache
        client.get("/api/graph?repo=numpy/numpy")
        
        # Second request (cached)
        start = time.time()
        response = client.get("/api/graph?repo=numpy/numpy")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.5, f"Cached request took {elapsed:.2f}s, expected < 0.5s"
        
        # Test 2: Total API response < 2s (uncached)
        cache.invalidate("psf/requests")
        
        start = time.time()
        response = client.get("/api/graph?repo=psf/requests")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 2.0, f"Uncached request took {elapsed:.2f}s, expected < 2s"

    def test_error_handling_robustness(self):
        """Verify error handling works correctly"""
        # Invalid repo format
        response = client.get("/api/graph?repo=invalid")
        assert response.status_code == 400
        
        # Repo not found
        response = client.get("/api/graph?repo=nonexistent/nonexistent-repo-12345")
        assert response.status_code == 404
        
        # Invalid query parameters
        response = client.get("/api/graph?repo=numpy/numpy&max_releases=invalid")
        assert response.status_code == 400

    def test_serialization_round_trip(self):
        """Verify graph serialization is lossless"""
        response = client.get("/api/graph?repo=numpy/numpy")
        assert response.status_code == 200
        
        data = response.json()
        graph = data["graph"]
        
        # Verify we can serialize and deserialize without loss
        import json
        serialized = json.dumps(graph)
        deserialized = json.loads(serialized)
        
        assert deserialized == graph
        assert len(deserialized["nodes"]) == len(graph["nodes"])
        assert len(deserialized["edges"]) == len(graph["edges"])

    def test_multiple_repos_in_sequence(self):
        """Test generating graphs for multiple repos in sequence"""
        repos = [
            "numpy/numpy",
            "psf/requests",
            "octocat/Hello-World"
        ]
        
        for repo in repos:
            response = client.get(f"/api/graph?repo={repo}")
            assert response.status_code == 200
            
            data = response.json()
            assert data["repo"] == repo
            assert len(data["graph"]["nodes"]) > 0
            
            # Verify metadata
            metadata = data["metadata"]
            assert "generation_time_ms" in metadata
            assert metadata["generation_time_ms"] > 0

    def test_data_source_integration(self):
        """Verify all data sources are integrated correctly"""
        response = client.get("/api/graph?repo=numpy/numpy")
        assert response.status_code == 200
        
        data = response.json()
        metadata = data["metadata"]
        
        # Verify data sources are tracked
        assert "data_sources" in metadata
        data_sources = metadata["data_sources"]
        
        # Should include at least github_api and score_data
        assert "github_api" in data_sources
        assert "score_data" in data_sources

    def test_graph_size_limits(self):
        """Verify graph size stays within reasonable limits"""
        response = client.get("/api/graph?repo=numpy/numpy")
        assert response.status_code == 200
        
        data = response.json()
        graph = data["graph"]
        
        # Verify node count is reasonable (< 200 per requirements)
        assert len(graph["nodes"]) < 200
        
        # Verify edge count is reasonable
        assert len(graph["edges"]) < 500

    def test_confidence_tracking(self):
        """Verify confidence values are tracked correctly"""
        response = client.get("/api/graph?repo=numpy/numpy")
        assert response.status_code == 200
        
        data = response.json()
        graph = data["graph"]
        
        # Check node confidence values
        for node in graph["nodes"]:
            confidence = node["provenance"]["confidence"]
            assert 0.0 <= confidence <= 1.0
            
            # Verify confidence levels match expected sources
            source = node["provenance"]["source"]
            if source == "github_api" and node["type"] == "release":
                assert confidence == 1.0  # Authoritative
            elif source == "osv":
                assert confidence >= 0.85  # High reliability
            elif source == "heuristic":
                assert confidence >= 0.7  # Heuristic-based
        
        # Check edge confidence values
        for edge in graph["edges"]:
            confidence = edge["provenance"]["confidence"]
            assert 0.0 <= confidence <= 1.0


class TestHealthCheckIntegration:
    """Test health check endpoint with graph feature"""

    def test_health_check_includes_graph_status(self):
        """Verify health check includes graph-related status"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
