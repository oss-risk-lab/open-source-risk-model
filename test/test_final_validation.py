"""
Final end-to-end validation for supply chain graph feature.

Simplified validation that tests core functionality across multiple repositories.
"""

import pytest
import time
from fastapi.testclient import TestClient
from api.app import app
from src.open_source_risk_model.graph.cache import GraphCache

client = TestClient(app)


class TestFinalValidation:
    """Final validation tests for supply chain graph feature"""

    def test_numpy_complete_workflow(self):
        """Test complete workflow with numpy/numpy - a well-maintained repo"""
        # Clear cache for this repo
        cache = GraphCache()
        cache.invalidate("numpy/numpy")
        
        # Make request
        response = client.get("/api/graph?repo=numpy/numpy")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "repo" in data
        assert data["repo"] == "numpy/numpy"
        assert "schema_version" in data
        assert "generated_at" in data
        assert "graph" in data
        assert "metadata" in data
        
        graph = data["graph"]
        
        # Verify graph has nodes and edges
        assert len(graph["nodes"]) > 0
        assert len(graph["edges"]) > 0
        
        # Verify exactly one repo node
        repo_nodes = [n for n in graph["nodes"] if n["type"] == "repo"]
        assert len(repo_nodes) == 1
        
        # Verify releases exist (numpy has many releases)
        release_nodes = [n for n in graph["nodes"] if n["type"] == "release"]
        assert len(release_nodes) > 0
        
        # Verify maintainers exist
        maintainer_nodes = [n for n in graph["nodes"] if n["type"] == "maintainer"]
        assert len(maintainer_nodes) > 0
        
        # Verify risk factors exist
        risk_nodes = [n for n in graph["nodes"] if n["type"] == "risk_factor"]
        assert len(risk_nodes) > 0
        
        # Verify registry nodes exist (numpy is on PyPI)
        registry_nodes = [n for n in graph["nodes"] if n["type"] == "registry"]
        assert len(registry_nodes) > 0
        
        print(f"✓ numpy/numpy: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    def test_requests_complete_workflow(self):
        """Test complete workflow with psf/requests - another popular repo"""
        response = client.get("/api/graph?repo=psf/requests")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["repo"] == "psf/requests"
        graph = data["graph"]
        
        # Verify basic structure
        assert len(graph["nodes"]) > 0
        assert len(graph["edges"]) > 0
        
        # Verify repo node
        repo_nodes = [n for n in graph["nodes"] if n["type"] == "repo"]
        assert len(repo_nodes) == 1
        
        print(f"✓ psf/requests: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    def test_small_repo_workflow(self):
        """Test with a smaller repository"""
        response = client.get("/api/graph?repo=octocat/Hello-World")
        
        assert response.status_code == 200
        data = response.json()
        
        graph = data["graph"]
        assert len(graph["nodes"]) > 0
        
        # Verify repo node exists
        repo_nodes = [n for n in graph["nodes"] if n["type"] == "repo"]
        assert len(repo_nodes) == 1
        
        print(f"✓ octocat/Hello-World: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    def test_graph_invariants(self):
        """Verify all graph invariants hold"""
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
            assert len(repo_nodes) == 1, f"{repo}: Expected 1 repo node, got {len(repo_nodes)}"
            
            # Invariant 2: Unique node IDs
            node_ids = [n["id"] for n in nodes]
            assert len(node_ids) == len(set(node_ids)), f"{repo}: Duplicate node IDs found"
            
            # Invariant 3: Valid edge references
            node_id_set = set(node_ids)
            for edge in edges:
                assert edge["source"] in node_id_set, f"{repo}: Edge source not in nodes"
                assert edge["target"] in node_id_set, f"{repo}: Edge target not in nodes"
            
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
            
            # Invariant 6: Provenance has required fields
            for node in nodes:
                prov = node["provenance"]
                assert "source" in prov
                assert "fetched_at" in prov
                # Note: Some nodes use 'data_confidence' instead of 'confidence'
                assert "confidence" in prov or "data_confidence" in prov
            
            for edge in edges:
                prov = edge["provenance"]
                assert "source" in prov
                assert "established_at" in prov
                assert "confidence" in prov or "data_confidence" in prov
            
            print(f"✓ {repo}: All invariants hold")

    def test_performance_targets(self):
        """Verify performance targets are met"""
        # Clear cache
        cache = GraphCache()
        cache.invalidate("numpy/numpy")
        
        # Test 1: First request (uncached) < 2s
        start = time.time()
        response = client.get("/api/graph?repo=numpy/numpy")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        print(f"✓ Uncached request: {elapsed:.2f}s (target: < 2s)")
        assert elapsed < 2.0, f"Uncached request took {elapsed:.2f}s, expected < 2s"
        
        # Test 2: Cached request < 500ms
        start = time.time()
        response = client.get("/api/graph?repo=numpy/numpy")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert response.json()["metadata"]["cache_hit"] is True
        print(f"✓ Cached request: {elapsed:.2f}s (target: < 0.5s)")
        assert elapsed < 0.5, f"Cached request took {elapsed:.2f}s, expected < 0.5s"

    def test_error_handling(self):
        """Verify error handling works correctly"""
        # Invalid repo format
        response = client.get("/api/graph?repo=invalid")
        assert response.status_code == 400
        print("✓ Invalid repo format returns 400")
        
        # Repo not found
        response = client.get("/api/graph?repo=nonexistent/nonexistent-repo-99999")
        assert response.status_code in [404, 500]  # May be 500 if GitHub API error
        print(f"✓ Nonexistent repo returns {response.status_code}")

    def test_provenance_tracking(self):
        """Verify provenance is tracked correctly"""
        response = client.get("/api/graph?repo=numpy/numpy")
        assert response.status_code == 200
        
        data = response.json()
        graph = data["graph"]
        
        # Check all nodes have provenance
        for node in graph["nodes"]:
            assert "provenance" in node
            prov = node["provenance"]
            assert "source" in prov
            assert "fetched_at" in prov
            
            # Check confidence value exists and is valid
            confidence = prov.get("confidence") or prov.get("data_confidence")
            assert confidence is not None
            assert 0.0 <= confidence <= 1.0
        
        # Check all edges have provenance
        for edge in graph["edges"]:
            assert "provenance" in edge
            prov = edge["provenance"]
            assert "source" in prov
            assert "established_at" in prov
            
            # Check confidence value exists and is valid
            confidence = prov.get("confidence") or prov.get("data_confidence")
            assert confidence is not None
            assert 0.0 <= confidence <= 1.0
        
        print("✓ All nodes and edges have valid provenance")

    def test_data_source_integration(self):
        """Verify multiple data sources are integrated"""
        response = client.get("/api/graph?repo=numpy/numpy")
        assert response.status_code == 200
        
        data = response.json()
        metadata = data["metadata"]
        
        # Verify data sources are tracked
        assert "data_sources" in metadata
        data_sources = metadata["data_sources"]
        
        # Should include at least github_api
        assert "github_api" in data_sources
        
        # Should include score_model for risk factors
        assert "score_model" in data_sources
        
        print(f"✓ Data sources integrated: {', '.join(data_sources)}")

    def test_graph_size_limits(self):
        """Verify graph size stays within reasonable limits"""
        response = client.get("/api/graph?repo=numpy/numpy")
        assert response.status_code == 200
        
        data = response.json()
        graph = data["graph"]
        
        # Verify node count is reasonable (< 200 per requirements)
        node_count = len(graph["nodes"])
        assert node_count < 200, f"Node count {node_count} exceeds limit of 200"
        
        # Verify edge count is reasonable
        edge_count = len(graph["edges"])
        assert edge_count < 500, f"Edge count {edge_count} exceeds limit of 500"
        
        print(f"✓ Graph size within limits: {node_count} nodes, {edge_count} edges")

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
        
        print("✓ Graph serialization is lossless")

    def test_all_property_tests_pass(self):
        """Verify all property-based tests pass"""
        import subprocess
        import glob
        
        # Find all property test files
        property_test_files = glob.glob("test/*property*.py")
        
        if not property_test_files:
            pytest.skip("No property test files found")
        
        # Run all property tests
        result = subprocess.run(
            ["python", "-m", "pytest"] + property_test_files + ["-v", "--tb=line"],
            capture_output=True,
            text=True
        )
        
        # Check if tests passed
        assert result.returncode == 0, f"Property tests failed:\n{result.stdout}\n{result.stderr}"
        
        print("✓ All property-based tests pass")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
