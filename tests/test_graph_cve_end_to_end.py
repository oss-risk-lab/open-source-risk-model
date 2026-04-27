"""
End-to-end integration test for CVE integration.

Tests the complete flow from graph building to CVE node creation.
"""

from unittest.mock import Mock, patch
import pytest

from src.open_source_risk_model.graph.builder import build_graph
from src.open_source_risk_model.graph.schema import GraphConfig, NodeType, EdgeType
from src.open_source_risk_model.graph.cve_fetcher import CVERecord


@pytest.fixture
def sample_score_data_with_releases():
    """Sample score data with release information."""
    return {
        "repo": {
            "url": "https://github.com/psf/requests",
        },
        "overall": {
            "maintenance_risk": 0.2,
            "maintenance_label": "low",
            "coverage": 0.9,
            "confidence": "high",
        },
        "features": [
            {
                "key": "days_since_last_release",
                "label": "Days Since Last Release",
                "raw_value": 30,
                "risk_score": 0.1,
                "weight": 0.15,
                "category": "activity",
            }
        ],
        "top_drivers": [
            {
                "key": "days_since_last_release",
                "contribution": 0.08,
            }
        ],
    }


def test_end_to_end_graph_with_cves(sample_score_data_with_releases):
    """Test complete graph building with CVE integration."""
    config = GraphConfig(include_cves=True, max_releases=5)
    
    # Mock GitHub API responses
    mock_releases = [
        {
            "tag_name": "v2.28.0",
            "name": "2.28.0",
            "published_at": "2023-01-15T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v2.27.0",
            "name": "2.27.0",
            "published_at": "2022-06-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    mock_contributors = [
        {
            "login": "kennethreitz",
            "contributions": 1000,
            "avatar_url": "https://avatars.githubusercontent.com/u/...",
            "type": "User",
        },
        {
            "login": "nateprewitt",
            "contributions": 500,
            "avatar_url": "https://avatars.githubusercontent.com/u/...",
            "type": "User",
        },
    ]
    
    mock_contents = [
        {"name": "setup.py", "type": "file"},
        {"name": "README.md", "type": "file"},
    ]
    
    mock_cves = [
        CVERecord(
            id="CVE-2023-1234",
            severity="HIGH",
            cvss_score=7.5,
            summary="Security vulnerability in requests",
            published="2023-02-01T10:00:00Z",
            fixed_in="2.28.0",
            affected_ranges=[
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "0"},
                        {"fixed": "2.28.0"}
                    ]
                }
            ],
            source="osv"
        ),
    ]
    
    with patch('src.open_source_risk_model.graph.builder.GitHubClient') as MockGitHubClient:
        mock_client = Mock()
        mock_client.fetch_releases.return_value = mock_releases
        mock_client.fetch_contributors.return_value = mock_contributors
        
        # Mock session for ecosystem detection
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_contents
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        
        MockGitHubClient.return_value = mock_client
        
        with patch('src.open_source_risk_model.graph.builder.CVEFetcher') as MockCVEFetcher:
            mock_cve_fetcher = Mock()
            mock_cve_fetcher.fetch_cves.return_value = mock_cves
            mock_cve_fetcher.map_cves_to_releases.return_value = {
                "v2.27.0": mock_cves,
            }
            MockCVEFetcher.return_value = mock_cve_fetcher
            
            # Build the graph
            graph = build_graph("psf/requests", sample_score_data_with_releases, config)
    
    # Verify graph structure
    assert len(graph.nodes) > 0
    assert len(graph.edges) > 0
    
    # Verify node types
    repo_nodes = [n for n in graph.nodes if n.type == NodeType.REPO]
    release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
    maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    risk_factor_nodes = [n for n in graph.nodes if n.type == NodeType.RISK_FACTOR]
    
    assert len(repo_nodes) == 1
    assert len(release_nodes) == 2
    assert len(maintainer_nodes) == 2
    assert len(cve_nodes) == 1
    assert len(risk_factor_nodes) == 1
    
    # Verify CVE node details
    cve_node = cve_nodes[0]
    assert cve_node.label == "CVE-2023-1234"
    assert cve_node.metadata["severity"] == "HIGH"
    assert cve_node.metadata["cvss_score"] == 7.5
    
    # Verify CVE edges
    cve_edges = [e for e in graph.edges if e.relationship_type == EdgeType.HAS_CVE]
    assert len(cve_edges) == 1
    assert cve_edges[0].source == "release:psf/requests:v2.27.0"
    assert cve_edges[0].target == "cve:CVE-2023-1234"
    
    # Verify graph validation passes
    errors = graph.validate()
    assert len(errors) == 0
    
    # Verify no warnings (successful build)
    warnings = graph.metadata.get("warnings", [])
    assert len(warnings) == 0


def test_end_to_end_graph_without_cves(sample_score_data_with_releases):
    """Test complete graph building with CVEs disabled."""
    config = GraphConfig(include_cves=False)
    
    with patch('src.open_source_risk_model.graph.builder.GitHubClient') as MockGitHubClient:
        mock_client = Mock()
        mock_client.fetch_releases.return_value = []
        mock_client.fetch_contributors.return_value = []
        MockGitHubClient.return_value = mock_client
        
        # Build the graph
        graph = build_graph("psf/requests", sample_score_data_with_releases, config)
    
    # Verify no CVE nodes were created
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    assert len(cve_nodes) == 0
    
    # Verify graph is still valid
    errors = graph.validate()
    assert len(errors) == 0
