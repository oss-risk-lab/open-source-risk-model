"""
Property-based tests for CVE node creation in graph builder.

Tests Property 5: CVE Node Creation
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, settings, assume

from src.open_source_risk_model.graph.schema import Node, Edge, Graph, NodeType, EdgeType, GraphConfig
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.cve_fetcher import CVEFetcher, CVERecord


# Hypothesis strategies for generating test data

@st.composite
def cve_record_strategy(draw, cve_id_suffix=None):
    """Strategy for generating valid CVE records."""
    if cve_id_suffix is None:
        cve_id_suffix = draw(st.integers(min_value=1000, max_value=9999))
    
    # Generate CVE ID (either CVE-YYYY-NNNN or GHSA-xxxx-yyyy-zzzz)
    cve_type = draw(st.sampled_from(["CVE", "GHSA"]))
    if cve_type == "CVE":
        year = draw(st.integers(min_value=2020, max_value=2024))
        cve_id = f"CVE-{year}-{cve_id_suffix}"
        source = "cve"
    else:
        cve_id = f"GHSA-{cve_id_suffix:04x}-yyyy-zzzz"
        source = "github_advisory"
    
    severity = draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]))
    
    # CVSS score should match severity
    if severity == "LOW":
        cvss_score = draw(st.floats(min_value=0.1, max_value=3.9, allow_nan=False))
    elif severity == "MEDIUM":
        cvss_score = draw(st.floats(min_value=4.0, max_value=6.9, allow_nan=False))
    elif severity == "HIGH":
        cvss_score = draw(st.floats(min_value=7.0, max_value=8.9, allow_nan=False))
    elif severity == "CRITICAL":
        cvss_score = draw(st.floats(min_value=9.0, max_value=10.0, allow_nan=False))
    else:
        cvss_score = None
    
    return CVERecord(
        id=cve_id,
        severity=severity,
        cvss_score=cvss_score,
        summary=draw(st.text(min_size=10, max_size=200)),
        published=datetime.now(timezone.utc).isoformat(),
        fixed_in=draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        affected_ranges=[],
        source=source
    )


@st.composite
def cve_list_strategy(draw):
    """Strategy for generating a list of CVE records with unique IDs."""
    num_cves = draw(st.integers(min_value=0, max_value=20))
    cves = []
    
    for i in range(num_cves):
        cve = draw(cve_record_strategy(cve_id_suffix=1000 + i))
        cves.append(cve)
    
    return cves


@st.composite
def score_data_strategy(draw):
    """Strategy for generating valid score data."""
    return {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
            "maintenance_label": draw(st.sampled_from(["low", "medium", "high", "critical"])),
            "coverage": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
            "confidence": draw(st.sampled_from(["low", "medium", "high"])),
        },
        "features": [],
        "top_drivers": [],
    }


@st.composite
def ecosystem_strategy(draw):
    """Strategy for generating valid ecosystem information."""
    ecosystem = draw(st.sampled_from(["PyPI", "npm", "Maven", "RubyGems", "crates.io"]))
    package_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'
    )))
    return (ecosystem, package_name)


# Property-Based Tests

# Feature: supply-chain-graph, Property 5: CVE Node Creation
@given(
    cves=cve_list_strategy(),
    score_data=score_data_strategy(),
    ecosystem_info=ecosystem_strategy()
)
@settings(max_examples=100, deadline=None)
def test_property_cve_nodes_created_when_cves_exist(cves, score_data, ecosystem_info):
    """
    Property 5: CVE Node Creation
    
    For any repository with known vulnerabilities in the CVE database, 
    the generated graph must include CVE nodes for those vulnerabilities 
    (unless CVE fetching is disabled).
    
    Validates: Requirements US-3.1
    
    Rationale: CVE nodes are critical for security analysis. Missing CVE data 
    when it exists represents a failure in data integration.
    """
    # Skip if no CVEs (tested separately)
    assume(len(cves) > 0)
    
    config = GraphConfig(include_cves=True)
    
    # Mock ecosystem detection
    with patch.object(GraphBuilder, '_detect_ecosystem', return_value=ecosystem_info):
        # Mock CVE fetcher to return our test CVEs
        with patch.object(CVEFetcher, 'fetch_cves', return_value=cves):
            # Mock CVE-to-release mapping (no releases for this test)
            with patch.object(CVEFetcher, 'map_cves_to_releases', return_value={}):
                builder = GraphBuilder("test/repo", score_data, config)
                graph = builder.build()
    
    # Find all CVE nodes
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    
    # Should have CVE nodes for all CVEs
    assert len(cve_nodes) == len(cves), \
        f"Expected {len(cves)} CVE nodes, got {len(cve_nodes)}"
    
    # Each CVE node should have required metadata
    cve_ids_in_graph = set()
    for node in cve_nodes:
        assert node.id.startswith("cve:"), \
            f"CVE node ID should start with 'cve:', got {node.id}"
        
        # Extract CVE ID from node ID
        cve_id = node.id.replace("cve:", "")
        cve_ids_in_graph.add(cve_id)
        
        # Check required metadata fields
        assert "cve_id" in node.metadata, f"CVE node {node.id} missing cve_id"
        assert "severity" in node.metadata, f"CVE node {node.id} missing severity"
        assert "summary" in node.metadata, f"CVE node {node.id} missing summary"
        assert "published" in node.metadata, f"CVE node {node.id} missing published"
        assert "source" in node.metadata, f"CVE node {node.id} missing source"
        
        # Validate severity is valid
        assert node.metadata["severity"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"], \
            f"CVE node {node.id} has invalid severity: {node.metadata['severity']}"
        
        # Validate CVSS score if present
        if "cvss_score" in node.metadata and node.metadata["cvss_score"] is not None:
            cvss_score = node.metadata["cvss_score"]
            assert 0.0 <= cvss_score <= 10.0, \
                f"CVE node {node.id} has invalid CVSS score: {cvss_score}"
        
        # Provenance should be complete
        assert node.provenance, f"CVE node {node.id} missing provenance"
        assert node.provenance.get("source") in ["osv", "cve", "github_advisory"], \
            f"CVE node {node.id} should have valid source in provenance"
        assert node.provenance.get("data_confidence") == 0.95, \
            f"CVE node {node.id} should have data_confidence=0.95"
        assert "fetched_at" in node.provenance, \
            f"CVE node {node.id} missing fetched_at in provenance"
    
    # Verify all CVEs from input are represented in graph
    expected_cve_ids = {cve.id for cve in cves}
    assert cve_ids_in_graph == expected_cve_ids, \
        f"CVE IDs in graph {cve_ids_in_graph} don't match expected {expected_cve_ids}"


@given(
    score_data=score_data_strategy(),
    ecosystem_info=ecosystem_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_no_cve_nodes_when_no_cves(score_data, ecosystem_info):
    """
    Property 5 (edge case): No CVE nodes when no vulnerabilities exist
    
    For any repository with no known vulnerabilities in the CVE database, 
    the generated graph should not include CVE nodes.
    
    Validates: Requirements US-3.1
    """
    config = GraphConfig(include_cves=True)
    
    # Mock ecosystem detection
    with patch.object(GraphBuilder, '_detect_ecosystem', return_value=ecosystem_info):
        # Mock CVE fetcher to return empty list
        with patch.object(CVEFetcher, 'fetch_cves', return_value=[]):
            builder = GraphBuilder("test/repo", score_data, config)
            graph = builder.build()
    
    # Find all CVE nodes
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    
    # Should have no CVE nodes
    assert len(cve_nodes) == 0, \
        f"Expected no CVE nodes when no CVEs exist, got {len(cve_nodes)}"


@given(
    cves=cve_list_strategy(),
    score_data=score_data_strategy(),
    ecosystem_info=ecosystem_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_no_cve_nodes_when_disabled(cves, score_data, ecosystem_info):
    """
    Property 5 (configuration): No CVE nodes when CVE fetching is disabled
    
    For any repository, when include_cves=False in configuration, 
    the generated graph should not include CVE nodes regardless of 
    whether CVEs exist.
    
    Validates: Requirements US-3.1
    """
    # Skip if no CVEs (we want to test that CVEs are ignored when disabled)
    assume(len(cves) > 0)
    
    config = GraphConfig(include_cves=False)
    
    # Mock ecosystem detection
    with patch.object(GraphBuilder, '_detect_ecosystem', return_value=ecosystem_info):
        # Mock CVE fetcher to return CVEs (but they should be ignored)
        with patch.object(CVEFetcher, 'fetch_cves', return_value=cves):
            builder = GraphBuilder("test/repo", score_data, config)
            graph = builder.build()
    
    # Find all CVE nodes
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    
    # Should have no CVE nodes when disabled
    assert len(cve_nodes) == 0, \
        f"Expected no CVE nodes when include_cves=False, got {len(cve_nodes)}"


@given(
    score_data=score_data_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_property_no_cve_nodes_when_no_ecosystem(score_data):
    """
    Property 5 (edge case): No CVE nodes when no ecosystem is detected
    
    For any repository where no package ecosystem can be detected 
    (no manifest files), the generated graph should not include CVE nodes.
    
    Validates: Requirements US-3.1
    """
    config = GraphConfig(include_cves=True)
    
    # Mock ecosystem detection to return None
    with patch.object(GraphBuilder, '_detect_ecosystem', return_value=None):
        builder = GraphBuilder("test/repo", score_data, config)
        graph = builder.build()
    
    # Find all CVE nodes
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    
    # Should have no CVE nodes when no ecosystem detected
    assert len(cve_nodes) == 0, \
        f"Expected no CVE nodes when no ecosystem detected, got {len(cve_nodes)}"


@given(
    cves=cve_list_strategy(),
    score_data=score_data_strategy(),
    ecosystem_info=ecosystem_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_cve_nodes_with_releases(cves, score_data, ecosystem_info):
    """
    Property 5 (with releases): CVE nodes linked to affected releases
    
    For any repository with CVEs and releases, CVE nodes should be created 
    and linked to affected releases via HAS_CVE edges.
    
    Validates: Requirements US-3.1, US-3.4
    """
    # Skip if no CVEs
    assume(len(cves) > 0)
    
    config = GraphConfig(include_cves=True)
    
    # Create mock releases
    mock_releases = [
        {
            "tag_name": "v1.0.0",
            "name": "Release 1.0.0",
            "published_at": "2024-01-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v2.0.0",
            "name": "Release 2.0.0",
            "published_at": "2024-06-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    # Mock CVE-to-release mapping (map all CVEs to first release)
    mock_mapping = {
        "v1.0.0": cves,
    }
    
    # Mock ecosystem detection
    with patch.object(GraphBuilder, '_detect_ecosystem', return_value=ecosystem_info):
        # Mock GitHub client for releases
        with patch('src.open_source_risk_model.graph.builder.GitHubClient') as MockGitHubClient:
            mock_client = Mock()
            mock_client.fetch_releases.return_value = mock_releases
            mock_client.fetch_contributors.return_value = []
            MockGitHubClient.return_value = mock_client
            
            # Mock CVE fetcher
            with patch.object(CVEFetcher, 'fetch_cves', return_value=cves):
                with patch.object(CVEFetcher, 'map_cves_to_releases', return_value=mock_mapping):
                    builder = GraphBuilder("test/repo", score_data, config)
                    graph = builder.build()
    
    # Find all CVE nodes
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    
    # Should have CVE nodes
    assert len(cve_nodes) == len(cves), \
        f"Expected {len(cves)} CVE nodes, got {len(cve_nodes)}"
    
    # Should have HAS_CVE edges
    cve_edges = [e for e in graph.edges if e.relationship_type == EdgeType.HAS_CVE]
    assert len(cve_edges) == len(cves), \
        f"Expected {len(cves)} HAS_CVE edges, got {len(cve_edges)}"
    
    # All edges should point from release to CVE
    for edge in cve_edges:
        assert edge.source.startswith("release:test/repo:"), \
            f"HAS_CVE edge should start from release node, got {edge.source}"
        assert edge.target.startswith("cve:"), \
            f"HAS_CVE edge should point to CVE node, got {edge.target}"
        
        # Edge should have required metadata
        assert "severity" in edge.metadata, \
            f"HAS_CVE edge missing severity"
        
        # Edge provenance should be complete
        assert edge.provenance, f"HAS_CVE edge missing provenance"
        assert "source" in edge.provenance, \
            f"HAS_CVE edge missing source in provenance"
        assert edge.provenance.get("confidence") == 0.85, \
            f"HAS_CVE edge should have confidence=0.85"
        assert edge.provenance.get("match_confidence") == 0.85, \
            f"HAS_CVE edge should have match_confidence=0.85"


@given(
    cves=cve_list_strategy(),
    score_data=score_data_strategy(),
    ecosystem_info=ecosystem_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_cve_node_uniqueness(cves, score_data, ecosystem_info):
    """
    Property 5 (uniqueness): CVE nodes are unique even when mapped to multiple releases
    
    For any repository where a CVE affects multiple releases, only one CVE node 
    should be created, with multiple edges to different releases.
    
    Validates: Requirements US-3.1
    """
    # Skip if no CVEs
    assume(len(cves) > 0)
    
    config = GraphConfig(include_cves=True)
    
    # Create mock releases
    mock_releases = [
        {
            "tag_name": "v1.0.0",
            "name": "Release 1.0.0",
            "published_at": "2024-01-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v2.0.0",
            "name": "Release 2.0.0",
            "published_at": "2024-06-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    # Mock CVE-to-release mapping (map all CVEs to BOTH releases)
    mock_mapping = {
        "v1.0.0": cves,
        "v2.0.0": cves,
    }
    
    # Mock ecosystem detection
    with patch.object(GraphBuilder, '_detect_ecosystem', return_value=ecosystem_info):
        # Mock GitHub client for releases
        with patch('src.open_source_risk_model.graph.builder.GitHubClient') as MockGitHubClient:
            mock_client = Mock()
            mock_client.fetch_releases.return_value = mock_releases
            mock_client.fetch_contributors.return_value = []
            MockGitHubClient.return_value = mock_client
            
            # Mock CVE fetcher
            with patch.object(CVEFetcher, 'fetch_cves', return_value=cves):
                with patch.object(CVEFetcher, 'map_cves_to_releases', return_value=mock_mapping):
                    builder = GraphBuilder("test/repo", score_data, config)
                    graph = builder.build()
    
    # Find all CVE nodes
    cve_nodes = [n for n in graph.nodes if n.type == NodeType.CVE]
    
    # Should have exactly len(cves) CVE nodes (not duplicated)
    assert len(cve_nodes) == len(cves), \
        f"Expected {len(cves)} unique CVE nodes, got {len(cve_nodes)}"
    
    # Should have 2 * len(cves) edges (one per CVE per release)
    cve_edges = [e for e in graph.edges if e.relationship_type == EdgeType.HAS_CVE]
    expected_edges = len(cves) * 2  # Each CVE affects 2 releases
    assert len(cve_edges) == expected_edges, \
        f"Expected {expected_edges} HAS_CVE edges, got {len(cve_edges)}"
    
    # Verify node IDs are unique
    cve_node_ids = [n.id for n in cve_nodes]
    assert len(cve_node_ids) == len(set(cve_node_ids)), \
        "CVE node IDs should be unique"
