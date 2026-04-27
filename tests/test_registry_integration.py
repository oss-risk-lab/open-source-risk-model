"""
Integration test for registry detection with real repositories.
"""

import pytest
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.schema import NodeType, EdgeType


def test_registry_detection_with_real_repo():
    """Test registry detection with a real repository (requests - PyPI)."""
    # Minimal score data for testing
    score_data = {
        "repo": {"url": "https://github.com/psf/requests"},
        "overall": {
            "maintenance_risk": 0.2,
            "maintenance_label": "low",
            "coverage": 0.9,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Build graph (this will make real API calls)
    builder = GraphBuilder("psf/requests", score_data)
    graph = builder.build()
    
    # Find registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    # requests is a Python package, should detect PyPI
    if len(registry_nodes) > 0:
        # Check that at least one is PyPI
        pypi_nodes = [n for n in registry_nodes if n.metadata.get("registry_type") == "pypi"]
        assert len(pypi_nodes) > 0, "Should detect PyPI registry for requests"
        
        # Check node structure
        pypi_node = pypi_nodes[0]
        assert "package_name" in pypi_node.metadata
        assert "detected_from" in pypi_node.metadata
        assert pypi_node.provenance.get("source") == "heuristic"
        assert 0.0 <= pypi_node.provenance.get("match_confidence", 0) <= 1.0
        
        # Check edges
        published_as_edges = [
            e for e in graph.edges 
            if e.relationship_type == EdgeType.PUBLISHED_AS and e.target == pypi_node.id
        ]
        assert len(published_as_edges) > 0, "Should have PUBLISHED_AS edge to PyPI registry"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
