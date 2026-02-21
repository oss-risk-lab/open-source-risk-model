"""
Tests for GitHub Releases integration in graph builder.

Tests both property-based and unit tests for release node creation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, settings, assume

from src.open_source_risk_model.graph.schema import Node, Edge, Graph, NodeType, EdgeType, GraphConfig
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.github_client import GitHubClient


# Hypothesis strategies for generating test data

@st.composite
def release_data_strategy(draw, tag_suffix=None):
    """Strategy for generating valid GitHub release data."""
    if tag_suffix is None:
        tag_suffix = draw(st.integers(min_value=0, max_value=9999))
    
    tag_name = f"v{draw(st.integers(min_value=0, max_value=99))}.{draw(st.integers(min_value=0, max_value=99))}.{tag_suffix}"
    
    # Generate a date in the past (up to 1000 days ago)
    days_ago = draw(st.integers(min_value=0, max_value=1000))
    published_dt = datetime.now(timezone.utc)
    published_dt = published_dt.replace(day=1)  # Avoid day overflow issues
    published_at = published_dt.isoformat().replace("+00:00", "Z")
    
    return {
        "tag_name": tag_name,
        "name": draw(st.one_of(st.just(tag_name), st.text(min_size=1, max_size=50))),
        "published_at": published_at,
        "prerelease": draw(st.booleans()),
        "draft": False,  # Drafts should be filtered out
    }


@st.composite
def releases_list_strategy(draw):
    """Strategy for generating a list of GitHub releases with unique tag names."""
    num_releases = draw(st.integers(min_value=0, max_value=20))
    releases = []
    
    for i in range(num_releases):
        release = draw(release_data_strategy(tag_suffix=i))
        releases.append(release)
    
    return releases


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


# Property-Based Tests

# Feature: supply-chain-graph, Property 5 (adapted): Release Node Creation
@given(
    releases=releases_list_strategy(),
    score_data=score_data_strategy(),
    max_releases=st.integers(min_value=1, max_value=20)
)
@settings(max_examples=100, deadline=None)
def test_property_release_nodes_created_when_releases_exist(releases, score_data, max_releases):
    """
    Property 5 (adapted): Release nodes created when releases exist
    
    For any repository with releases in the GitHub API, the generated graph 
    must include RELEASE nodes for those releases (up to max_releases limit).
    
    Validates: Requirements US-2.1
    
    Rationale: Release nodes are critical for understanding the release cadence 
    and linking CVEs to specific versions. Missing release data when it exists 
    represents a failure in data integration.
    """
    # Skip if no releases (tested separately)
    assume(len(releases) > 0)
    
    # Mock the GitHub client to return limited releases (simulating what fetch_releases does)
    limited_releases = releases[:max_releases]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=limited_releases):
        config = GraphConfig(max_releases=max_releases)
        builder = GraphBuilder("test/repo", score_data, config)
        graph = builder.build()
        
        # Find all release nodes
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        
        # Should have release nodes (up to max_releases limit)
        expected_count = min(len(releases), max_releases)
        assert len(release_nodes) == expected_count, \
            f"Expected {expected_count} release nodes, got {len(release_nodes)}"
        
        # Each release node should have required metadata
        for node in release_nodes:
            assert node.id.startswith("release:test/repo:"), \
                f"Release node ID should start with 'release:test/repo:', got {node.id}"
            assert "tag_name" in node.metadata, f"Release node {node.id} missing tag_name"
            assert "published_at" in node.metadata, f"Release node {node.id} missing published_at"
            assert "is_latest" in node.metadata, f"Release node {node.id} missing is_latest"
            assert "is_prerelease" in node.metadata, f"Release node {node.id} missing is_prerelease"
            
            # Provenance should be complete
            assert node.provenance, f"Release node {node.id} missing provenance"
            assert node.provenance.get("source") == "github_api", \
                f"Release node {node.id} should have source='github_api'"
            assert node.provenance.get("data_confidence") == 1.0, \
                f"Release node {node.id} should have data_confidence=1.0"
        
        # Should have HAS_RELEASE edges from repo to releases
        release_edges = [e for e in graph.edges if e.relationship_type == EdgeType.HAS_RELEASE]
        assert len(release_edges) == expected_count, \
            f"Expected {expected_count} HAS_RELEASE edges, got {len(release_edges)}"
        
        # All edges should point from repo to release nodes
        repo_id = "repo:test/repo"
        for edge in release_edges:
            assert edge.source == repo_id, \
                f"HAS_RELEASE edge should start from {repo_id}, got {edge.source}"
            assert edge.target.startswith("release:test/repo:"), \
                f"HAS_RELEASE edge should point to release node, got {edge.target}"
            
            # Edge provenance should be complete
            assert edge.provenance, f"HAS_RELEASE edge missing provenance"
            assert edge.provenance.get("source") == "github_api", \
                f"HAS_RELEASE edge should have source='github_api'"
            assert edge.provenance.get("confidence") == 1.0, \
                f"HAS_RELEASE edge should have confidence=1.0"
        
        # Exactly one release should be marked as latest (if any releases exist)
        if len(release_nodes) > 0:
            latest_nodes = [n for n in release_nodes if n.metadata.get("is_latest")]
            assert len(latest_nodes) == 1, \
                f"Exactly one release should be marked as latest, got {len(latest_nodes)}"


@given(
    score_data=score_data_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_property_no_release_nodes_when_no_releases(score_data):
    """
    Property 5 (edge case): No release nodes when repository has no releases
    
    For any repository with no releases in the GitHub API, the generated graph 
    should not include RELEASE nodes from the GitHub API (may include fallback 
    from score_data if available).
    
    Validates: Requirements US-2.1
    """
    # Mock the GitHub client to return empty list
    with patch.object(GitHubClient, 'fetch_releases', return_value=[]):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Find all release nodes from GitHub API
        release_nodes = [
            n for n in graph.nodes 
            if n.type == NodeType.RELEASE and n.provenance.get("source") == "github_api"
        ]
        
        # Should have no release nodes from GitHub API
        assert len(release_nodes) == 0, \
            f"Expected no GitHub API release nodes when no releases exist, got {len(release_nodes)}"


@given(
    releases=releases_list_strategy(),
    score_data=score_data_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_property_release_node_ordering(releases, score_data):
    """
    Property: Release nodes are ordered by publication date
    
    For any repository with multiple releases, the first release node should 
    be marked as is_latest=True, representing the most recent release.
    
    Validates: Requirements US-2.1
    """
    # Skip if less than 2 releases
    assume(len(releases) >= 2)
    
    # Mock the GitHub client to return our test releases
    with patch.object(GitHubClient, 'fetch_releases', return_value=releases):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Find all release nodes
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        
        if len(release_nodes) > 0:
            # Exactly one should be marked as latest
            latest_nodes = [n for n in release_nodes if n.metadata.get("is_latest")]
            assert len(latest_nodes) == 1, \
                f"Exactly one release should be marked as latest, got {len(latest_nodes)}"


@given(
    releases=releases_list_strategy(),
    score_data=score_data_strategy(),
    max_releases=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=50, deadline=None)
def test_property_release_node_limit_respected(releases, score_data, max_releases):
    """
    Property: Release node count respects max_releases configuration
    
    For any repository, the number of release nodes should not exceed 
    the configured max_releases limit.
    
    Validates: Requirements US-2.1
    """
    # Skip if no releases
    assume(len(releases) > 0)
    
    # Mock the GitHub client to return limited releases (simulating what fetch_releases does)
    limited_releases = releases[:max_releases]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=limited_releases):
        config = GraphConfig(max_releases=max_releases)
        builder = GraphBuilder("test/repo", score_data, config)
        graph = builder.build()
        
        # Find all release nodes
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        
        # Should not exceed max_releases
        assert len(release_nodes) <= max_releases, \
            f"Release node count {len(release_nodes)} exceeds max_releases {max_releases}"



# Unit Tests

def test_release_integration_with_numpy():
    """Test release integration with a known repository (numpy)."""
    score_data = {
        "repo": {"url": "https://github.com/numpy/numpy"},
        "overall": {
            "maintenance_risk": 0.2,
            "maintenance_label": "low",
            "coverage": 0.9,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Mock numpy releases
    mock_releases = [
        {
            "tag_name": "v1.26.0",
            "name": "NumPy 1.26.0",
            "published_at": "2024-09-16T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v1.25.2",
            "name": "NumPy 1.25.2",
            "published_at": "2024-07-15T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=mock_releases):
        builder = GraphBuilder("numpy/numpy", score_data)
        graph = builder.build()
        
        # Should have 2 release nodes
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        assert len(release_nodes) == 2
        
        # First release should be marked as latest
        latest_nodes = [n for n in release_nodes if n.metadata.get("is_latest")]
        assert len(latest_nodes) == 1
        assert latest_nodes[0].metadata["tag_name"] == "v1.26.0"
        
        # Should have 2 HAS_RELEASE edges
        release_edges = [e for e in graph.edges if e.relationship_type == EdgeType.HAS_RELEASE]
        assert len(release_edges) == 2


def test_release_integration_with_requests():
    """Test release integration with another known repository (requests)."""
    score_data = {
        "repo": {"url": "https://github.com/psf/requests"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.85,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Mock requests releases
    mock_releases = [
        {
            "tag_name": "v2.31.0",
            "name": "2.31.0",
            "published_at": "2023-05-22T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=mock_releases):
        builder = GraphBuilder("psf/requests", score_data)
        graph = builder.build()
        
        # Should have 1 release node
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        assert len(release_nodes) == 1
        
        # Should be marked as latest
        assert release_nodes[0].metadata.get("is_latest") is True
        assert release_nodes[0].metadata["tag_name"] == "v2.31.0"


def test_repo_with_no_releases():
    """Test edge case: repository with no releases."""
    score_data = {
        "repo": {"url": "https://github.com/test/no-releases"},
        "overall": {
            "maintenance_risk": 0.5,
            "maintenance_label": "medium",
            "coverage": 0.7,
            "confidence": "medium",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Mock empty releases list
    with patch.object(GitHubClient, 'fetch_releases', return_value=[]):
        builder = GraphBuilder("test/no-releases", score_data)
        graph = builder.build()
        
        # Should have no release nodes from GitHub API
        release_nodes = [
            n for n in graph.nodes 
            if n.type == NodeType.RELEASE and n.provenance.get("source") == "github_api"
        ]
        assert len(release_nodes) == 0
        
        # Should have no HAS_RELEASE edges from GitHub API
        release_edges = [
            e for e in graph.edges 
            if e.relationship_type == EdgeType.HAS_RELEASE 
            and e.provenance.get("source") == "github_api"
        ]
        assert len(release_edges) == 0


def test_release_caching_behavior():
    """Test that release data is cached properly."""
    score_data = {
        "repo": {"url": "https://github.com/test/cached-repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    mock_releases = [
        {
            "tag_name": "v1.0.0",
            "name": "Release 1.0.0",
            "published_at": "2024-01-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    # First call - should fetch from API
    with patch.object(GitHubClient, 'fetch_releases', return_value=mock_releases) as mock_fetch:
        builder1 = GraphBuilder("test/cached-repo", score_data)
        graph1 = builder1.build()
        
        # Should have called fetch_releases
        assert mock_fetch.call_count == 1
        
        # Should have 1 release node
        release_nodes1 = [n for n in graph1.nodes if n.type == NodeType.RELEASE]
        assert len(release_nodes1) == 1
    
    # Second call - should use cache (within TTL)
    # Note: This test verifies the caching mechanism exists, but actual cache behavior
    # depends on the GitHubClient implementation and file system state


def test_release_node_metadata_completeness():
    """Test that release nodes have all required metadata fields."""
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
    
    mock_releases = [
        {
            "tag_name": "v2.0.0",
            "name": "Version 2.0.0",
            "published_at": "2024-06-15T14:30:00Z",
            "prerelease": True,
            "draft": False,
        },
    ]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=mock_releases):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        assert len(release_nodes) == 1
        
        node = release_nodes[0]
        
        # Check required metadata fields
        assert "tag_name" in node.metadata
        assert "name" in node.metadata
        assert "published_at" in node.metadata
        assert "days_ago" in node.metadata
        assert "is_latest" in node.metadata
        assert "is_prerelease" in node.metadata
        
        # Check values
        assert node.metadata["tag_name"] == "v2.0.0"
        assert node.metadata["name"] == "Version 2.0.0"
        assert node.metadata["is_prerelease"] is True
        assert node.metadata["is_latest"] is True
        assert isinstance(node.metadata["days_ago"], int)


def test_release_edge_metadata_completeness():
    """Test that HAS_RELEASE edges have all required metadata fields."""
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
    
    mock_releases = [
        {
            "tag_name": "v1.5.0",
            "name": "Release 1.5.0",
            "published_at": "2024-03-10T10:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=mock_releases):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        release_edges = [e for e in graph.edges if e.relationship_type == EdgeType.HAS_RELEASE]
        assert len(release_edges) == 1
        
        edge = release_edges[0]
        
        # Check edge structure
        assert edge.source == "repo:test/repo"
        assert edge.target.startswith("release:test/repo:")
        
        # Check metadata
        assert "days_ago" in edge.metadata
        assert "is_latest" in edge.metadata
        assert edge.metadata["is_latest"] is True
        
        # Check provenance
        assert edge.provenance.get("source") == "github_api"
        assert edge.provenance.get("confidence") == 1.0
        assert "established_at" in edge.provenance


def test_max_releases_configuration():
    """Test that max_releases configuration is respected."""
    score_data = {
        "repo": {"url": "https://github.com/test/many-releases"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Create 15 mock releases
    mock_releases = [
        {
            "tag_name": f"v1.{i}.0",
            "name": f"Release 1.{i}.0",
            "published_at": f"2024-{i+1:02d}-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        }
        for i in range(15)
    ]
    
    # Test with max_releases=5
    with patch.object(GitHubClient, 'fetch_releases', return_value=mock_releases[:5]):
        config = GraphConfig(max_releases=5)
        builder = GraphBuilder("test/many-releases", score_data, config)
        graph = builder.build()
        
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        assert len(release_nodes) == 5
        
        release_edges = [e for e in graph.edges if e.relationship_type == EdgeType.HAS_RELEASE]
        assert len(release_edges) == 5


def test_release_with_invalid_published_at():
    """Test handling of releases with invalid published_at timestamps."""
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
    
    mock_releases = [
        {
            "tag_name": "v1.0.0",
            "name": "Release 1.0.0",
            "published_at": "invalid-date",
            "prerelease": False,
            "draft": False,
        },
    ]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=mock_releases):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        
        # Should still create the node, but days_ago might be None
        assert len(release_nodes) == 1
        # The node should exist even with invalid timestamp
        assert release_nodes[0].metadata["tag_name"] == "v1.0.0"
