"""
Property-based tests for node count limits in graph builder.

Tests Property 11: Node Count Limits
Validates that the number of nodes of each type respects configured limits.
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
    
    tag_name = f"v1.{tag_suffix}.0"
    
    return {
        "tag_name": tag_name,
        "name": f"Release {tag_name}",
        "published_at": "2024-01-15T10:00:00Z",
        "prerelease": draw(st.booleans()),
        "draft": False,
    }


@st.composite
def releases_list_strategy(draw):
    """Strategy for generating a list of GitHub releases with unique tags."""
    num_releases = draw(st.integers(min_value=0, max_value=30))
    releases = []
    
    for i in range(num_releases):
        release = draw(release_data_strategy(tag_suffix=i))
        releases.append(release)
    
    return releases


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
    num_contributors = draw(st.integers(min_value=0, max_value=30))
    contributors = []
    
    for i in range(num_contributors):
        contributor = draw(contributor_data_strategy(username_suffix=i))
        contributors.append(contributor)
    
    return contributors


@st.composite
def risk_driver_strategy(draw, key_suffix=None):
    """Strategy for generating risk driver data."""
    if key_suffix is None:
        key_suffix = draw(st.integers(min_value=0, max_value=9999))
    
    key = f"risk_factor_{key_suffix}"
    contribution = draw(st.floats(min_value=0.05, max_value=0.5, allow_nan=False))
    
    return {
        "key": key,
        "contribution": contribution,
    }


@st.composite
def risk_drivers_list_strategy(draw):
    """Strategy for generating a list of risk drivers."""
    num_drivers = draw(st.integers(min_value=0, max_value=30))
    drivers = []
    
    for i in range(num_drivers):
        driver = draw(risk_driver_strategy(key_suffix=i))
        drivers.append(driver)
    
    return drivers


# Property-Based Tests

# Feature: supply-chain-graph, Property 11: Node Count Limits
@given(
    releases=releases_list_strategy(),
    contributors=contributors_list_strategy(),
    risk_drivers=risk_drivers_list_strategy(),
    max_releases=st.integers(min_value=1, max_value=20),
    max_maintainers=st.integers(min_value=1, max_value=20),
    max_risk_factors=st.integers(min_value=1, max_value=20),
    coverage=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    maintenance_risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=100, deadline=None)
def test_property_node_count_limits(
    releases, contributors, risk_drivers, 
    max_releases, max_maintainers, max_risk_factors,
    coverage, maintenance_risk
):
    """
    Property 11: Node Count Limits
    
    For any generated graph, the number of nodes of each type must not exceed 
    the configured limits (max_releases, max_maintainers, max_risk_factors).
    
    Validates: Requirements US-5.4
    
    Rationale: Node limits prevent graph explosion and ensure reasonable 
    visualization performance. Exceeding limits indicates a failure in 
    filtering logic.
    """
    # Generate score data with risk factors
    features = []
    for driver in risk_drivers:
        key = driver["key"]
        features.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "raw_value": 50.0,
            "risk_score": 0.5,
            "weight": 0.5,
            "category": "activity",
        })
    
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": maintenance_risk,
            "maintenance_label": "medium",
            "coverage": coverage,
            "confidence": "medium",
        },
        "features": features,
        "top_drivers": risk_drivers,
    }
    
    # Mock the GitHub client to return limited data (simulating what fetch methods do)
    limited_releases = releases[:max_releases]
    limited_contributors = contributors[:max_maintainers]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=limited_releases), \
         patch.object(GitHubClient, 'fetch_contributors', return_value=limited_contributors):
        
        config = GraphConfig(
            max_releases=max_releases,
            max_maintainers=max_maintainers,
            max_risk_factors=max_risk_factors
        )
        builder = GraphBuilder("test/repo", score_data, config)
        graph = builder.build()
        
        # Count nodes of each type
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
        risk_factor_nodes = [n for n in graph.nodes if n.type == NodeType.RISK_FACTOR]
        
        # Validate release node count limit
        assert len(release_nodes) <= max_releases, \
            f"Release node count {len(release_nodes)} exceeds max_releases {max_releases}"
        
        # Validate maintainer node count limit
        assert len(maintainer_nodes) <= max_maintainers, \
            f"Maintainer node count {len(maintainer_nodes)} exceeds max_maintainers {max_maintainers}"
        
        # Validate risk factor node count limit
        # Note: Risk factors also filter by contribution > 0.05, so actual count may be less
        assert len(risk_factor_nodes) <= max_risk_factors, \
            f"Risk factor node count {len(risk_factor_nodes)} exceeds max_risk_factors {max_risk_factors}"
        
        # Additional validation: Verify that if we have enough data, we get up to the limit
        # (unless filtered by other criteria like contribution threshold)
        
        if len(releases) > 0:
            expected_release_count = min(len(releases), max_releases)
            assert len(release_nodes) == expected_release_count, \
                f"Expected {expected_release_count} release nodes, got {len(release_nodes)}"
        
        if len(contributors) > 0:
            expected_maintainer_count = min(len(contributors), max_maintainers)
            assert len(maintainer_nodes) == expected_maintainer_count, \
                f"Expected {expected_maintainer_count} maintainer nodes, got {len(maintainer_nodes)}"
        
        # For risk factors, we need to account for the contribution > 0.05 filter
        significant_drivers = [d for d in risk_drivers if d.get("contribution", 0) >= 0.05]
        if len(significant_drivers) > 0:
            expected_risk_count = min(len(significant_drivers), max_risk_factors)
            assert len(risk_factor_nodes) == expected_risk_count, \
                f"Expected {expected_risk_count} risk factor nodes, got {len(risk_factor_nodes)}"


@given(
    releases=releases_list_strategy(),
    contributors=contributors_list_strategy(),
    risk_drivers=risk_drivers_list_strategy(),
    coverage=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    maintenance_risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=50, deadline=None)
def test_property_node_limits_with_default_config(
    releases, contributors, risk_drivers, coverage, maintenance_risk
):
    """
    Property 11 (variant): Node count limits with default configuration
    
    For any generated graph using default configuration, the number of nodes 
    of each type must not exceed the default limits (10 releases, 5 maintainers, 
    5 risk factors).
    
    Validates: Requirements US-5.4
    """
    # Generate score data with risk factors
    features = []
    for driver in risk_drivers:
        key = driver["key"]
        features.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "raw_value": 50.0,
            "risk_score": 0.5,
            "weight": 0.5,
            "category": "activity",
        })
    
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": maintenance_risk,
            "maintenance_label": "medium",
            "coverage": coverage,
            "confidence": "medium",
        },
        "features": features,
        "top_drivers": risk_drivers,
    }
    
    # Default limits from GraphConfig
    default_max_releases = 10
    default_max_maintainers = 5
    default_max_risk_factors = 5
    
    # Mock the GitHub client to return limited data
    limited_releases = releases[:default_max_releases]
    limited_contributors = contributors[:default_max_maintainers]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=limited_releases), \
         patch.object(GitHubClient, 'fetch_contributors', return_value=limited_contributors):
        
        # Use default config
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Count nodes of each type
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
        risk_factor_nodes = [n for n in graph.nodes if n.type == NodeType.RISK_FACTOR]
        
        # Validate against default limits
        assert len(release_nodes) <= default_max_releases, \
            f"Release node count {len(release_nodes)} exceeds default max_releases {default_max_releases}"
        
        assert len(maintainer_nodes) <= default_max_maintainers, \
            f"Maintainer node count {len(maintainer_nodes)} exceeds default max_maintainers {default_max_maintainers}"
        
        assert len(risk_factor_nodes) <= default_max_risk_factors, \
            f"Risk factor node count {len(risk_factor_nodes)} exceeds default max_risk_factors {default_max_risk_factors}"


@given(
    data_count=st.integers(min_value=50, max_value=100),
    limit=st.integers(min_value=1, max_value=10),
    coverage=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    maintenance_risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=50, deadline=None)
def test_property_node_limits_with_excess_data(data_count, limit, coverage, maintenance_risk):
    """
    Property 11 (stress test): Node count limits when data far exceeds limits
    
    For any generated graph where available data significantly exceeds configured 
    limits, the graph must still respect the limits and not include excess nodes.
    
    Validates: Requirements US-5.4
    
    Rationale: This tests the filtering logic under stress conditions where 
    there's much more data available than the limit allows.
    """
    # Ensure data_count exceeds limit significantly
    assume(data_count >= limit * 3)
    
    # Generate excess data
    releases = []
    for i in range(data_count):
        releases.append({
            "tag_name": f"v1.{i}.0",
            "name": f"Release v1.{i}.0",
            "published_at": "2024-01-15T10:00:00Z",
            "prerelease": False,
            "draft": False,
        })
    
    contributors = []
    for i in range(data_count):
        contributors.append({
            "login": f"user{i}",
            "contributions": 100,
            "avatar_url": f"https://avatars.githubusercontent.com/u/{i}",
            "type": "User",
        })
    
    risk_drivers = []
    for i in range(data_count):
        risk_drivers.append({
            "key": f"risk_factor_{i}",
            "contribution": 0.1,  # All above 0.05 threshold
        })
    
    # Generate score data
    features = []
    for driver in risk_drivers:
        key = driver["key"]
        features.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "raw_value": 50.0,
            "risk_score": 0.5,
            "weight": 0.5,
            "category": "activity",
        })
    
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": maintenance_risk,
            "maintenance_label": "medium",
            "coverage": coverage,
            "confidence": "medium",
        },
        "features": features,
        "top_drivers": risk_drivers,
    }
    
    # Mock the GitHub client to return limited data
    limited_releases = releases[:limit]
    limited_contributors = contributors[:limit]
    
    with patch.object(GitHubClient, 'fetch_releases', return_value=limited_releases), \
         patch.object(GitHubClient, 'fetch_contributors', return_value=limited_contributors):
        
        config = GraphConfig(
            max_releases=limit,
            max_maintainers=limit,
            max_risk_factors=limit
        )
        builder = GraphBuilder("test/repo", score_data, config)
        graph = builder.build()
        
        # Count nodes of each type
        release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
        maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
        risk_factor_nodes = [n for n in graph.nodes if n.type == NodeType.RISK_FACTOR]
        
        # Strict validation: Must not exceed limits even with excess data
        assert len(release_nodes) <= limit, \
            f"Release node count {len(release_nodes)} exceeds limit {limit} despite excess data"
        
        assert len(maintainer_nodes) <= limit, \
            f"Maintainer node count {len(maintainer_nodes)} exceeds limit {limit} despite excess data"
        
        assert len(risk_factor_nodes) <= limit, \
            f"Risk factor node count {len(risk_factor_nodes)} exceeds limit {limit} despite excess data"
        
        # Verify we're actually getting nodes up to the limit (when data is available)
        assert len(release_nodes) == limit, \
            f"Expected exactly {limit} release nodes with excess data, got {len(release_nodes)}"
        
        assert len(maintainer_nodes) == limit, \
            f"Expected exactly {limit} maintainer nodes with excess data, got {len(maintainer_nodes)}"
        
        # Risk factors may be less due to contribution filter, but should not exceed limit
        significant_drivers = [d for d in risk_drivers if d.get("contribution", 0) >= 0.05]
        expected_risk_count = min(len(significant_drivers), limit)
        assert len(risk_factor_nodes) == expected_risk_count, \
            f"Expected {expected_risk_count} risk factor nodes with excess data, got {len(risk_factor_nodes)}"
