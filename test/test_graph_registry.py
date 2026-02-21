"""
Tests for package registry detection in graph builder.

Tests both unit tests for registry node creation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import base64
import json

from src.open_source_risk_model.graph.schema import Node, Edge, Graph, NodeType, EdgeType, GraphConfig
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.registry_detector import RegistryDetector, RegistryInfo


# Unit Tests

def test_registry_detector_pypi_from_setup_py():
    """Test PyPI detection from setup.py.
    
    Note: The current implementation uses a heuristic approach for setup.py,
    converting the repo name to a package name (lowercase, underscores).
    This is because parsing setup.py with AST is complex and error-prone.
    """
    # Mock GitHub session
    mock_session = Mock()
    
    # Mock repository contents response
    contents_response = Mock()
    contents_response.json.return_value = [
        {"name": "setup.py", "type": "file"},
        {"name": "README.md", "type": "file"},
    ]
    contents_response.raise_for_status = Mock()
    
    mock_session.get.return_value = contents_response
    
    detector = RegistryDetector(github_session=mock_session)
    registries = detector.detect_registries("test", "my-repo")
    
    assert len(registries) == 1
    assert registries[0].registry_type == "pypi"
    # Heuristic converts repo name: lowercase and replace hyphens with underscores
    assert registries[0].package_name == "my_repo"
    assert registries[0].detected_from == "setup.py"
    # Lower confidence for heuristic approach
    assert registries[0].match_confidence == 0.7


def test_registry_detector_pypi_from_pyproject():
    """Test PyPI detection from pyproject.toml."""
    # Mock GitHub session
    mock_session = Mock()
    
    # Mock repository contents response
    contents_response = Mock()
    contents_response.json.return_value = [
        {"name": "pyproject.toml", "type": "file"},
        {"name": "README.md", "type": "file"},
    ]
    contents_response.raise_for_status = Mock()
    
    # Mock pyproject.toml content
    pyproject_content = """
[project]
name = "my-package"
version = "1.0.0"
"""
    pyproject_response = Mock()
    pyproject_response.json.return_value = {
        "content": base64.b64encode(pyproject_content.encode()).decode()
    }
    pyproject_response.raise_for_status = Mock()
    
    # Configure mock session to return appropriate responses
    mock_session.get.side_effect = [contents_response, pyproject_response]
    
    detector = RegistryDetector(github_session=mock_session)
    registries = detector.detect_registries("test", "repo")
    
    assert len(registries) == 1
    assert registries[0].registry_type == "pypi"
    assert registries[0].package_name == "my-package"
    assert registries[0].detected_from == "pyproject.toml"
    assert registries[0].match_confidence == 0.9


def test_registry_detector_npm_from_package_json():
    """Test npm detection from package.json."""
    # Mock GitHub session
    mock_session = Mock()
    
    # Mock repository contents response
    contents_response = Mock()
    contents_response.json.return_value = [
        {"name": "package.json", "type": "file"},
        {"name": "README.md", "type": "file"},
    ]
    contents_response.raise_for_status = Mock()
    
    # Mock package.json content
    package_content = json.dumps({"name": "@scope/my-package", "version": "1.0.0"})
    package_response = Mock()
    package_response.json.return_value = {
        "content": base64.b64encode(package_content.encode()).decode()
    }
    package_response.raise_for_status = Mock()
    
    # Configure mock session to return appropriate responses
    mock_session.get.side_effect = [contents_response, package_response]
    
    detector = RegistryDetector(github_session=mock_session)
    registries = detector.detect_registries("test", "repo")
    
    assert len(registries) == 1
    assert registries[0].registry_type == "npm"
    assert registries[0].package_name == "@scope/my-package"
    assert registries[0].detected_from == "package.json"
    assert registries[0].match_confidence == 0.95


def test_registry_detector_maven_from_pom_xml():
    """Test Maven detection from pom.xml."""
    # Mock GitHub session
    mock_session = Mock()
    
    # Mock repository contents response
    contents_response = Mock()
    contents_response.json.return_value = [
        {"name": "pom.xml", "type": "file"},
        {"name": "README.md", "type": "file"},
    ]
    contents_response.raise_for_status = Mock()
    
    # Mock pom.xml content
    pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project>
    <artifactId>my-artifact</artifactId>
    <version>1.0.0</version>
</project>
"""
    pom_response = Mock()
    pom_response.json.return_value = {
        "content": base64.b64encode(pom_content.encode()).decode()
    }
    pom_response.raise_for_status = Mock()
    
    # Configure mock session to return appropriate responses
    mock_session.get.side_effect = [contents_response, pom_response]
    
    detector = RegistryDetector(github_session=mock_session)
    registries = detector.detect_registries("test", "repo")
    
    assert len(registries) == 1
    assert registries[0].registry_type == "maven"
    assert registries[0].package_name == "my-artifact"
    assert registries[0].detected_from == "pom.xml"
    assert registries[0].match_confidence == 0.9


def test_registry_detector_no_manifest_files():
    """Test that no registries are detected when no manifest files exist."""
    # Mock GitHub session
    mock_session = Mock()
    
    # Mock repository contents response with no manifest files
    contents_response = Mock()
    contents_response.json.return_value = [
        {"name": "README.md", "type": "file"},
        {"name": "LICENSE", "type": "file"},
    ]
    contents_response.raise_for_status = Mock()
    
    mock_session.get.return_value = contents_response
    
    detector = RegistryDetector(github_session=mock_session)
    registries = detector.detect_registries("test", "repo")
    
    assert len(registries) == 0


def test_graph_builder_adds_registry_nodes():
    """Test that GraphBuilder adds registry nodes when registries are detected."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Mock registry detection
    mock_registries = [
        RegistryInfo(
            registry_type="pypi",
            package_name="test-package",
            detected_from="pyproject.toml",
            match_confidence=0.9,
        )
    ]
    
    with patch.object(RegistryDetector, 'detect_registries', return_value=mock_registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Find registry nodes
        registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
        
        assert len(registry_nodes) == 1
        assert registry_nodes[0].id == "registry:pypi:test-package"
        assert registry_nodes[0].label == "pypi: test-package"
        assert registry_nodes[0].metadata["registry_type"] == "pypi"
        assert registry_nodes[0].metadata["package_name"] == "test-package"
        assert registry_nodes[0].metadata["detected_from"] == "pyproject.toml"
        assert registry_nodes[0].provenance["source"] == "heuristic"
        assert registry_nodes[0].provenance["match_confidence"] == 0.9
        assert registry_nodes[0].provenance["data_confidence"] == 0.8
        
        # Find PUBLISHED_AS edges
        published_as_edges = [e for e in graph.edges if e.relationship_type == EdgeType.PUBLISHED_AS]
        
        assert len(published_as_edges) == 1
        assert published_as_edges[0].source == "repo:test/repo"
        assert published_as_edges[0].target == "registry:pypi:test-package"
        assert published_as_edges[0].metadata["package_name"] == "test-package"
        assert published_as_edges[0].provenance["source"] == "heuristic"
        assert published_as_edges[0].provenance["match_confidence"] == 0.9
        assert published_as_edges[0].provenance["confidence"] == 0.8


def test_graph_builder_handles_no_registries():
    """Test that GraphBuilder handles repos with no detected registries gracefully."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Mock registry detection to return empty list
    with patch.object(RegistryDetector, 'detect_registries', return_value=[]):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Find registry nodes
        registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
        
        # Should have no registry nodes
        assert len(registry_nodes) == 0
        
        # Should still have repo node (graph should be valid)
        repo_nodes = [n for n in graph.nodes if n.type == NodeType.REPO]
        assert len(repo_nodes) == 1


def test_graph_builder_handles_multiple_registries():
    """Test that GraphBuilder can handle multiple registries (e.g., PyPI and npm)."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Mock registry detection with multiple registries
    mock_registries = [
        RegistryInfo(
            registry_type="pypi",
            package_name="test-package",
            detected_from="pyproject.toml",
            match_confidence=0.9,
        ),
        RegistryInfo(
            registry_type="npm",
            package_name="@test/package",
            detected_from="package.json",
            match_confidence=0.95,
        ),
    ]
    
    with patch.object(RegistryDetector, 'detect_registries', return_value=mock_registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Find registry nodes
        registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
        
        assert len(registry_nodes) == 2
        
        # Check PyPI node
        pypi_node = next(n for n in registry_nodes if n.metadata["registry_type"] == "pypi")
        assert pypi_node.id == "registry:pypi:test-package"
        
        # Check npm node
        npm_node = next(n for n in registry_nodes if n.metadata["registry_type"] == "npm")
        assert npm_node.id == "registry:npm:@test/package"
        
        # Find PUBLISHED_AS edges
        published_as_edges = [e for e in graph.edges if e.relationship_type == EdgeType.PUBLISHED_AS]
        
        assert len(published_as_edges) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
