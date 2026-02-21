"""
Tests for CVE integration in GraphBuilder.

Tests the _add_cve_nodes method and ecosystem detection.
"""

import json
from unittest.mock import Mock, patch, MagicMock
import pytest

from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.schema import GraphConfig, NodeType, EdgeType
from src.open_source_risk_model.graph.cve_fetcher import CVERecord


@pytest.fixture
def sample_score_data():
    """Sample score data for testing."""
    return {
        "repo": {
            "url": "https://github.com/test/repo",
        },
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }


@pytest.fixture
def sample_cve_records():
    """Sample CVE records for testing."""
    return [
        CVERecord(
            id="CVE-2024-1234",
            severity="HIGH",
            cvss_score=7.5,
            summary="Test vulnerability",
            published="2024-01-15T10:00:00Z",
            fixed_in="1.2.0",
            affected_ranges=[
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "0"},
                        {"fixed": "1.2.0"}
                    ]
                }
            ],
            source="osv"
        ),
        CVERecord(
            id="GHSA-xxxx-yyyy-zzzz",
            severity="MEDIUM",
            cvss_score=5.0,
            summary="Another test vulnerability",
            published="2024-02-01T10:00:00Z",
            fixed_in="1.3.0",
            affected_ranges=[
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "1.0.0"},
                        {"fixed": "1.3.0"}
                    ]
                }
            ],
            source="github_advisory"
        ),
    ]


def test_ecosystem_detection_python(sample_score_data):
    """Test ecosystem detection for Python repositories."""
    builder = GraphBuilder("test/repo", sample_score_data)
    
    # Mock GitHub API response for repository contents
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"name": "setup.py", "type": "file"},
        {"name": "README.md", "type": "file"},
    ]
    
    with patch.object(builder.github_client.session, 'get', return_value=mock_response):
        ecosystem_info = builder._detect_ecosystem()
    
    assert ecosystem_info is not None
    ecosystem, package_name = ecosystem_info
    assert ecosystem == "PyPI"
    assert package_name == "repo"  # Fallback to repo name


def test_ecosystem_detection_npm(sample_score_data):
    """Test ecosystem detection for npm repositories."""
    builder = GraphBuilder("test/repo", sample_score_data)
    
    # Mock GitHub API response for repository contents
    mock_contents_response = Mock()
    mock_contents_response.status_code = 200
    mock_contents_response.json.return_value = [
        {"name": "package.json", "type": "file"},
        {"name": "README.md", "type": "file"},
    ]
    
    # Mock package.json content
    mock_package_response = Mock()
    mock_package_response.status_code = 200
    import base64
    package_json = json.dumps({"name": "test-package"})
    mock_package_response.json.return_value = {
        "content": base64.b64encode(package_json.encode()).decode()
    }
    
    with patch.object(builder.github_client.session, 'get') as mock_get:
        mock_get.side_effect = [mock_contents_response, mock_package_response]
        ecosystem_info = builder._detect_ecosystem()
    
    assert ecosystem_info is not None
    ecosystem, package_name = ecosystem_info
    assert ecosystem == "npm"
    assert package_name == "test-package"


def test_ecosystem_detection_no_manifest(sample_score_data):
    """Test ecosystem detection when no manifest files are present."""
    builder = GraphBuilder("test/repo", sample_score_data)
    
    # Mock GitHub API response with no manifest files
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"name": "README.md", "type": "file"},
        {"name": "LICENSE", "type": "file"},
    ]
    
    with patch.object(builder.github_client.session, 'get', return_value=mock_response):
        ecosystem_info = builder._detect_ecosystem()
    
    assert ecosystem_info is None


def test_add_cve_nodes_with_releases(sample_score_data, sample_cve_records):
    """Test adding CVE nodes when releases exist."""
    config = GraphConfig(include_cves=True)
    builder = GraphBuilder("test/repo", sample_score_data, config)
    
    # Add a repo node and release nodes first
    builder._add_repo_node()
    
    # Mock release nodes
    from src.open_source_risk_model.graph.schema import Node
    release_node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={"tag_name": "v1.0.0"},
        provenance={"source": "github_api", "fetched_at": "2024-01-01T00:00:00Z", "data_confidence": 1.0}
    )
    builder.graph.add_node(release_node)
    
    # Mock ecosystem detection
    with patch.object(builder, '_detect_ecosystem', return_value=("PyPI", "test-package")):
        # Mock CVE fetcher
        with patch.object(builder.cve_fetcher, 'fetch_cves', return_value=sample_cve_records):
            # Mock CVE-to-release mapping
            with patch.object(builder.cve_fetcher, 'map_cves_to_releases', return_value={"v1.0.0": sample_cve_records}):
                builder._add_cve_nodes()
    
    # Verify CVE nodes were created
    cve_nodes = [n for n in builder.graph.nodes if n.type == NodeType.CVE]
    assert len(cve_nodes) == 2
    
    # Verify CVE node metadata
    cve_node = cve_nodes[0]
    assert cve_node.metadata["cve_id"] in ["CVE-2024-1234", "GHSA-xxxx-yyyy-zzzz"]
    assert cve_node.metadata["severity"] in ["HIGH", "MEDIUM"]
    assert "cvss_score" in cve_node.metadata
    
    # Verify edges were created
    cve_edges = [e for e in builder.graph.edges if e.relationship_type == EdgeType.HAS_CVE]
    assert len(cve_edges) == 2


def test_add_cve_nodes_no_ecosystem(sample_score_data):
    """Test adding CVE nodes when no ecosystem is detected."""
    config = GraphConfig(include_cves=True)
    builder = GraphBuilder("test/repo", sample_score_data, config)
    
    builder._add_repo_node()
    
    # Mock ecosystem detection to return None
    with patch.object(builder, '_detect_ecosystem', return_value=None):
        builder._add_cve_nodes()
    
    # Verify no CVE nodes were created
    cve_nodes = [n for n in builder.graph.nodes if n.type == NodeType.CVE]
    assert len(cve_nodes) == 0


def test_add_cve_nodes_no_cves_found(sample_score_data):
    """Test adding CVE nodes when no CVEs are found."""
    config = GraphConfig(include_cves=True)
    builder = GraphBuilder("test/repo", sample_score_data, config)
    
    builder._add_repo_node()
    
    # Mock ecosystem detection
    with patch.object(builder, '_detect_ecosystem', return_value=("PyPI", "test-package")):
        # Mock CVE fetcher to return empty list
        with patch.object(builder.cve_fetcher, 'fetch_cves', return_value=[]):
            builder._add_cve_nodes()
    
    # Verify no CVE nodes were created
    cve_nodes = [n for n in builder.graph.nodes if n.type == NodeType.CVE]
    assert len(cve_nodes) == 0


def test_cve_fetch_failure_graceful_degradation(sample_score_data):
    """Test that CVE fetch failures are handled gracefully."""
    config = GraphConfig(include_cves=True)
    builder = GraphBuilder("test/repo", sample_score_data, config)
    
    # Mock ecosystem detection
    with patch.object(builder, '_detect_ecosystem', return_value=("PyPI", "test-package")):
        # Mock CVE fetcher to raise an exception
        with patch.object(builder.cve_fetcher, 'fetch_cves', side_effect=Exception("Network error")):
            # This should not raise, but add a warning
            builder._safe_add_nodes("cve_nodes", builder._add_cve_nodes)
    
    # Verify graph is still valid (no CVE nodes, but has warning)
    cve_nodes = [n for n in builder.graph.nodes if n.type == NodeType.CVE]
    assert len(cve_nodes) == 0
    
    # Verify warning was added
    warnings = builder.graph.metadata.get("warnings", [])
    assert len(warnings) > 0
    assert any("cve_nodes" in w.get("source", "") for w in warnings)


def test_cve_nodes_disabled_in_config(sample_score_data):
    """Test that CVE nodes are not added when disabled in config."""
    config = GraphConfig(include_cves=False)
    builder = GraphBuilder("test/repo", sample_score_data, config)
    
    graph = builder.build()
    
    # Verify no CVE nodes were created
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    assert len(cve_nodes) == 0


def test_cve_node_provenance(sample_score_data, sample_cve_records):
    """Test that CVE nodes have proper provenance metadata."""
    config = GraphConfig(include_cves=True)
    builder = GraphBuilder("test/repo", sample_score_data, config)
    
    builder._add_repo_node()
    
    # Mock ecosystem detection
    with patch.object(builder, '_detect_ecosystem', return_value=("PyPI", "test-package")):
        # Mock CVE fetcher
        with patch.object(builder.cve_fetcher, 'fetch_cves', return_value=sample_cve_records):
            with patch.object(builder.cve_fetcher, 'map_cves_to_releases', return_value={}):
                builder._add_cve_nodes()
    
    # Verify CVE nodes have provenance
    cve_nodes = [n for n in builder.graph.nodes if n.type == NodeType.CVE]
    assert len(cve_nodes) == 2
    
    for cve_node in cve_nodes:
        assert "provenance" in cve_node.__dict__
        assert "source" in cve_node.provenance
        assert "fetched_at" in cve_node.provenance
        assert "data_confidence" in cve_node.provenance
        assert cve_node.provenance["data_confidence"] == 0.95


def test_cve_edge_provenance(sample_score_data, sample_cve_records):
    """Test that CVE edges have proper provenance metadata."""
    config = GraphConfig(include_cves=True)
    builder = GraphBuilder("test/repo", sample_score_data, config)
    
    builder._add_repo_node()
    
    # Add a release node
    from src.open_source_risk_model.graph.schema import Node
    release_node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={"tag_name": "v1.0.0"},
        provenance={"source": "github_api", "fetched_at": "2024-01-01T00:00:00Z", "data_confidence": 1.0}
    )
    builder.graph.add_node(release_node)
    
    # Mock ecosystem detection
    with patch.object(builder, '_detect_ecosystem', return_value=("PyPI", "test-package")):
        # Mock CVE fetcher
        with patch.object(builder.cve_fetcher, 'fetch_cves', return_value=sample_cve_records):
            with patch.object(builder.cve_fetcher, 'map_cves_to_releases', return_value={"v1.0.0": sample_cve_records}):
                builder._add_cve_nodes()
    
    # Verify CVE edges have provenance
    cve_edges = [e for e in builder.graph.edges if e.relationship_type == EdgeType.HAS_CVE]
    assert len(cve_edges) == 2
    
    for edge in cve_edges:
        assert "provenance" in edge.__dict__
        assert "source" in edge.provenance
        assert "established_at" in edge.provenance
        assert "confidence" in edge.provenance
        assert "match_confidence" in edge.provenance
        assert edge.provenance["confidence"] == 0.85
        assert edge.provenance["match_confidence"] == 0.85
