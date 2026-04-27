"""
Tests for GitHub Contributors integration in graph builder.

Tests both property-based and unit tests for maintainer node creation.
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
def contributor_data_strategy(draw, username_suffix=None):
    """Strategy for generating valid GitHub contributor data."""
    if username_suffix is None:
        username_suffix = draw(st.integers(min_value=0, max_value=9999))
    
    username = f"user{username_suffix}"
    contributions = draw(st.integers(min_value=1, max_value=10000))
    
    return {
        "login": username,
        "contributions": contributions,
        "avatar_url": f"https://avatars.githubusercontent.com/u/{username_suffix}",
        "type": "User",
    }


@st.composite
def contributors_list_strategy(draw):
    """Strategy for generating a list of GitHub contributors with unique usernames."""
    num_contributors = draw(st.integers(min_value=0, max_value=20))
    contributors = []
    
    for i in range(num_contributors):
        contributor = draw(contributor_data_strategy(username_suffix=i))
        contributors.append(contributor)
    
    return contributors


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

# Feature: supply-chain-graph, Property 7: Maintainer Node Creation
@given(
    contributors=contributors_list_strategy(),
    score_data=score_data_strategy(),
    max_maintainers=st.integers(min_value=1, max_value=20)
)
@settings(max_examples=100, deadline=None)
def test_property_maintainer_nodes_created_when_contributors_exist(contributors, score_data, max_maintainers):
    """
    Property 7: Maintainer Node Creation
    
    For any repository with contributor data, the generated graph must include 
    maintainer nodes for the top contributors (up to max_maintainers limit).
    
    Validates: Requirements US-5.1
    
    Rationale: Maintainer nodes are critical for understanding bus factor and 
    governance. Missing maintainer data when it exists represents a failure 
    in data integration.
    """
    # Skip if no contributors (tested separately)
    assume(len(contributors) > 0)
    
    # Mock the GitHub client to return limited contributors (simulating what fetch_contributors does)
    limited_contributors = contributors[:max_maintainers]
    
    with patch.object(GitHubClient, 'fetch_contributors', return_value=limited_contributors):
        config = GraphConfig(max_maintainers=max_maintainers)
        builder = GraphBuilder("test/repo", score_data, config)
        graph = builder.build()
        
        # Find all maintainer nodes
        maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
        
        # Should have maintainer nodes (up to max_maintainers limit)
        expected_count = min(len(contributors), max_maintainers)
        assert len(maintainer_nodes) == expected_count, \
            f"Expected {expected_count} maintainer nodes, got {len(maintainer_nodes)}"
        
        # Calculate total contributions for validation
        total_contributions = sum(c.get("contributions", 0) for c in limited_contributors)
        
        # Each maintainer node should have required metadata
        for node in maintainer_nodes:
            assert node.id.startswith("maintainer:test/repo:"), \
                f"Maintainer node ID should start with 'maintainer:test/repo:', got {node.id}"
            assert "username" in node.metadata, f"Maintainer node {node.id} missing username"
            assert "contribution_fraction" in node.metadata, f"Maintainer node {node.id} missing contribution_fraction"
            assert "commit_count" in node.metadata, f"Maintainer node {node.id} missing commit_count"
            assert "type" in node.metadata, f"Maintainer node {node.id} missing type"
            
            # Validate contribution_fraction is in valid range
            contribution_fraction = node.metadata["contribution_fraction"]
            assert 0.0 <= contribution_fraction <= 1.0, \
                f"Maintainer node {node.id} contribution_fraction must be in [0.0, 1.0], got {contribution_fraction}"
            
            # Validate commit_count is positive
            commit_count = node.metadata["commit_count"]
            assert commit_count > 0, \
                f"Maintainer node {node.id} commit_count must be positive, got {commit_count}"
            
            # Provenance should be complete
            assert node.provenance, f"Maintainer node {node.id} missing provenance"
            assert node.provenance.get("source") == "github_api", \
                f"Maintainer node {node.id} should have source='github_api'"
            assert node.provenance.get("data_confidence") == 0.9, \
                f"Maintainer node {node.id} should have data_confidence=0.9"
        
        # Validate that contribution fractions sum to approximately 1.0
        if total_contributions > 0:
            total_fraction = sum(n.metadata["contribution_fraction"] for n in maintainer_nodes)
            assert 0.99 <= total_fraction <= 1.01, \
                f"Contribution fractions should sum to ~1.0, got {total_fraction}"
        
        # Should have MAINTAINED_BY edges from maintainers to repo
        maintained_by_edges = [e for e in graph.edges if e.relationship_type == EdgeType.MAINTAINED_BY]
        assert len(maintained_by_edges) == expected_count, \
            f"Expected {expected_count} MAINTAINED_BY edges, got {len(maintained_by_edges)}"
        
        # All edges should point from maintainer to repo
        repo_id = "repo:test/repo"
        for edge in maintained_by_edges:
            assert edge.source.startswith("maintainer:test/repo:"), \
                f"MAINTAINED_BY edge should start from maintainer node, got {edge.source}"
            assert edge.target == repo_id, \
                f"MAINTAINED_BY edge should point to {repo_id}, got {edge.target}"
            
            # Edge should have required metadata
            assert "contribution_fraction" in edge.metadata, \
                f"MAINTAINED_BY edge missing contribution_fraction"
            assert "commit_count" in edge.metadata, \
                f"MAINTAINED_BY edge missing commit_count"
            
            # Edge provenance should be complete
            assert edge.provenance, f"MAINTAINED_BY edge missing provenance"
            assert edge.provenance.get("source") == "github_api", \
                f"MAINTAINED_BY edge should have source='github_api'"
            assert edge.provenance.get("confidence") == 0.9, \
                f"MAINTAINED_BY edge should have confidence=0.9"


@given(
    score_data=score_data_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_property_no_maintainer_nodes_when_no_contributors(score_data):
    """
    Property 7 (edge case): No maintainer nodes when repository has no contributors
    
    For any repository with no contributors in the GitHub API, the generated graph 
    should not include MAINTAINER nodes from the GitHub API.
    
    Validates: Requirements US-5.1
    """
    # Mock the GitHub client to return empty list
    with patch.object(GitHubClient, 'fetch_contributors', return_value=[]):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Find all maintainer nodes from GitHub API
        maintainer_nodes = [
            n for n in graph.nodes 
            if n.type == NodeType.MAINTAINER and n.provenance.get("source") == "github_api"
        ]
        
        # Should have no maintainer nodes from GitHub API
        assert len(maintainer_nodes) == 0, \
            f"Expected no GitHub API maintainer nodes when no contributors exist, got {len(maintainer_nodes)}"


@given(
    contributors=contributors_list_strategy(),
    score_data=score_data_strategy(),
    max_maintainers=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=50, deadline=None)
def test_property_maintainer_node_limit_respected(contributors, score_data, max_maintainers):
    """
    Property: Maintainer node count respects max_maintainers configuration
    
    For any repository, the number of maintainer nodes should not exceed 
    the configured max_maintainers limit.
    
    Validates: Requirements US-5.1
    """
    # Skip if no contributors
    assume(len(contributors) > 0)
    
    # Mock the GitHub client to return limited contributors (simulating what fetch_contributors does)
    limited_contributors = contributors[:max_maintainers]
    
    with patch.object(GitHubClient, 'fetch_contributors', return_value=limited_contributors):
        config = GraphConfig(max_maintainers=max_maintainers)
        builder = GraphBuilder("test/repo", score_data, config)
        graph = builder.build()
        
        # Find all maintainer nodes
        maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
        
        # Should not exceed max_maintainers
        assert len(maintainer_nodes) <= max_maintainers, \
            f"Maintainer node count {len(maintainer_nodes)} exceeds max_maintainers {max_maintainers}"


@given(
    contributors=contributors_list_strategy(),
    score_data=score_data_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_property_contribution_fractions_valid(contributors, score_data):
    """
    Property: Contribution fractions are valid and sum to approximately 1.0
    
    For any repository with contributors, the contribution_fraction for each 
    maintainer should be in [0.0, 1.0] and all fractions should sum to ~1.0.
    
    Validates: Requirements US-5.2, US-5.3
    """
    # Skip if no contributors
    assume(len(contributors) > 0)
    
    # Ensure at least one contributor has contributions > 0
    assume(any(c.get("contributions", 0) > 0 for c in contributors))
    
    with patch.object(GitHubClient, 'fetch_contributors', return_value=contributors):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Find all maintainer nodes
        maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
        
        if len(maintainer_nodes) > 0:
            # Each contribution_fraction should be valid
            for node in maintainer_nodes:
                fraction = node.metadata["contribution_fraction"]
                assert 0.0 <= fraction <= 1.0, \
                    f"Contribution fraction must be in [0.0, 1.0], got {fraction}"
            
            # Sum should be approximately 1.0 (allowing for floating point errors)
            total_fraction = sum(n.metadata["contribution_fraction"] for n in maintainer_nodes)
            assert 0.99 <= total_fraction <= 1.01, \
                f"Contribution fractions should sum to ~1.0, got {total_fraction}"
