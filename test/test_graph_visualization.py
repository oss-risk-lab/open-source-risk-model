"""
Integration tests for graph visualization.

Tests that the visualization HTML and JavaScript files are properly structured
and that the graph API endpoint returns data in the expected format for visualization.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app


class TestVisualizationFiles:
    """Test that visualization files exist and are properly structured."""
    
    def test_graph_html_exists(self):
        """Test that graph.html file exists."""
        html_path = Path("ui/graph.html")
        assert html_path.exists(), "graph.html should exist in ui/ directory"
    
    def test_graph_js_exists(self):
        """Test that graph-viz.js file exists."""
        js_path = Path("ui/graph-viz.js")
        assert js_path.exists(), "graph-viz.js should exist in ui/ directory"
    
    def test_graph_html_includes_visjs(self):
        """Test that graph.html includes vis.js library."""
        html_path = Path("ui/graph.html")
        content = html_path.read_text()
        
        assert "vis-network" in content, "HTML should include vis-network library"
        assert "graph-viz.js" in content, "HTML should include graph-viz.js script"
    
    def test_graph_html_has_required_elements(self):
        """Test that graph.html has required UI elements."""
        html_path = Path("ui/graph.html")
        content = html_path.read_text()
        
        # Check for required elements
        required_ids = [
            "repoInput",
            "loadBtn",
            "graph-container",
            "nodeDetails",
            "nodeTypeFilters",
            "confidenceSlider",
            "searchInput",
            "showProvenance",
            "exportJson",
            "exportPng"
        ]
        
        for element_id in required_ids:
            assert f'id="{element_id}"' in content, f"HTML should have element with id='{element_id}'"
    
    def test_graph_js_has_required_functions(self):
        """Test that graph-viz.js has required functions."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # Check for required functions
        required_functions = [
            "loadGraph",
            "renderGraph",
            "convertToVisFormat",
            "showNodeDetails",
            "applyFilters",
            "initializeFilters"
        ]
        
        for func_name in required_functions:
            assert f"function {func_name}" in content or f"{func_name} =" in content, \
                f"JavaScript should define function '{func_name}'"
    
    def test_graph_js_has_node_type_config(self):
        """Test that graph-viz.js has node type configuration."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # Check for node types
        node_types = ["repo", "release", "maintainer", "cve", "registry", "risk_factor"]
        
        for node_type in node_types:
            assert node_type in content, f"JavaScript should have configuration for '{node_type}' node type"


class TestGraphAPIForVisualization:
    """Test that graph API returns data in format expected by visualization."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_graph_api_returns_visualization_compatible_format(self, client):
        """Test that graph API returns data compatible with vis.js visualization."""
        # Use a small, well-known repo
        response = client.get("/api/graph?repo=psf/requests&max_releases=3&max_maintainers=2")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level structure
        assert "repo" in data
        assert "graph" in data
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        
        # Check nodes have required fields for visualization
        if len(data["graph"]["nodes"]) > 0:
            node = data["graph"]["nodes"][0]
            assert "id" in node, "Node should have id"
            assert "type" in node, "Node should have type"
            assert "label" in node, "Node should have label"
            assert "metadata" in node, "Node should have metadata"
            assert "provenance" in node, "Node should have provenance"
        
        # Check edges have required fields for visualization
        if len(data["graph"]["edges"]) > 0:
            edge = data["graph"]["edges"][0]
            assert "source" in edge, "Edge should have source"
            assert "target" in edge, "Edge should have target"
            assert "relationship_type" in edge, "Edge should have relationship_type"
    
    def test_graph_api_node_types_match_visualization_config(self, client):
        """Test that node types from API match those configured in visualization."""
        response = client.get("/api/graph?repo=psf/requests&max_releases=3")
        
        assert response.status_code == 200
        data = response.json()
        
        # Valid node types that visualization knows about
        valid_types = {"repo", "release", "maintainer", "cve", "registry", "risk_factor"}
        
        for node in data["graph"]["nodes"]:
            assert node["type"] in valid_types, \
                f"Node type '{node['type']}' should be one of {valid_types}"
    
    def test_graph_api_provenance_fields_present(self, client):
        """Test that nodes have provenance fields needed for visualization."""
        response = client.get("/api/graph?repo=psf/requests&max_releases=2")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that nodes have provenance
        for node in data["graph"]["nodes"]:
            assert "provenance" in node, f"Node {node['id']} should have provenance"
            prov = node["provenance"]
            
            # Should have at least source
            assert "source" in prov, f"Node {node['id']} provenance should have source"
            
            # Should have some confidence measure
            has_confidence = "confidence" in prov or "data_confidence" in prov
            assert has_confidence, f"Node {node['id']} provenance should have confidence"
    
    def test_graph_api_empty_graph_structure(self, client):
        """Test that API returns valid structure even for empty/minimal graphs."""
        # Use a repo that might have minimal data
        response = client.get("/api/graph?repo=psf/requests&include_cves=false&max_releases=1&max_maintainers=1")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should still have valid structure
        assert isinstance(data["graph"]["nodes"], list)
        assert isinstance(data["graph"]["edges"], list)
        
        # Should have at least repo node
        assert len(data["graph"]["nodes"]) >= 1
        
        # First node should be repo
        repo_nodes = [n for n in data["graph"]["nodes"] if n["type"] == "repo"]
        assert len(repo_nodes) == 1, "Should have exactly one repo node"


class TestGraphVisualizationIntegration:
    """Integration tests for complete visualization workflow."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_small_graph_loads_successfully(self, client):
        """Test that a small graph can be loaded and has reasonable structure."""
        response = client.get("/api/graph?repo=psf/requests&max_releases=5&max_maintainers=3")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have multiple nodes
        assert len(data["graph"]["nodes"]) >= 3, "Should have at least repo + some enrichment nodes"
        
        # Should have edges connecting nodes
        assert len(data["graph"]["edges"]) >= 1, "Should have at least one edge"
        
        # All edges should reference valid nodes
        node_ids = {n["id"] for n in data["graph"]["nodes"]}
        for edge in data["graph"]["edges"]:
            assert edge["source"] in node_ids, f"Edge source {edge['source']} should reference valid node"
            assert edge["target"] in node_ids, f"Edge target {edge['target']} should reference valid node"
    
    def test_medium_graph_loads_successfully(self, client):
        """Test that a medium-sized graph can be loaded."""
        response = client.get("/api/graph?repo=numpy/numpy&max_releases=10&max_maintainers=5")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have at least repo node (enrichment may vary based on data availability)
        node_count = len(data["graph"]["nodes"])
        assert node_count >= 1, f"Graph should have at least 1 node (repo), got {node_count}"
        
        # Should have metadata
        assert "metadata" in data
        assert "node_count" in data["metadata"]
        assert "edge_count" in data["metadata"]
        assert data["metadata"]["node_count"] == node_count
    
    def test_graph_with_various_node_types(self, client):
        """Test that graph includes various node types for rich visualization."""
        response = client.get("/api/graph?repo=numpy/numpy&include_cves=true&max_releases=5&max_maintainers=3")
        
        assert response.status_code == 200
        data = response.json()
        
        # Collect node types
        node_types = {n["type"] for n in data["graph"]["nodes"]}
        
        # Should have at least repo and some enrichment
        assert "repo" in node_types, "Should have repo node"
        
        # Should have at least one other type
        assert len(node_types) >= 2, f"Should have multiple node types, got {node_types}"
    
    def test_graph_metadata_for_visualization(self, client):
        """Test that graph includes metadata useful for visualization."""
        response = client.get("/api/graph?repo=psf/requests")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check metadata
        meta = data["metadata"]
        assert "node_count" in meta
        assert "edge_count" in meta
        assert "data_sources" in meta
        assert "generation_time_ms" in meta
        
        # Data sources should be a list
        assert isinstance(meta["data_sources"], list)
        assert len(meta["data_sources"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
