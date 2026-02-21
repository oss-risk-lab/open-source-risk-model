"""
Tests for graceful error handling in GraphBuilder.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.schema import GraphConfig


def test_error_handling_maintainer_nodes_failure():
    """Test that GraphBuilder handles maintainer node creation failure gracefully."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [
            {
                "key": "contributors_last_12mo",
                "raw_value": 10,
                "risk_score": 0.2,
            }
        ],
        "top_drivers": [],
    }
    
    builder = GraphBuilder("test/repo", score_data)
    
    # Mock _add_maintainer_nodes to raise an exception
    with patch.object(builder, '_add_maintainer_nodes', side_effect=Exception("API timeout")):
        graph = builder.build()
    
    # Graph should still be built (graceful degradation)
    assert graph is not None
    assert len(graph.nodes) > 0  # At least repo node should exist
    
    # Check that warning was added to metadata
    assert "warnings" in graph.metadata
    warnings = graph.metadata["warnings"]
    assert len(warnings) > 0
    assert any("maintainer_nodes" in w.get("source", "") for w in warnings)
    assert any("API timeout" in w.get("error", "") for w in warnings)


def test_error_handling_risk_factor_nodes_failure():
    """Test that GraphBuilder handles risk factor node creation failure gracefully."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [
            {
                "key": "test_risk",
                "contribution": 0.1,
            }
        ],
    }
    
    builder = GraphBuilder("test/repo", score_data)
    
    # Mock _add_risk_factor_nodes to raise an exception
    with patch.object(builder, '_add_risk_factor_nodes', side_effect=Exception("Data parsing error")):
        graph = builder.build()
    
    # Graph should still be built
    assert graph is not None
    assert len(graph.nodes) > 0
    
    # Check that warning was added
    assert "warnings" in graph.metadata
    warnings = graph.metadata["warnings"]
    assert len(warnings) > 0
    assert any("risk_factor_nodes" in w.get("source", "") for w in warnings)


def test_error_handling_release_nodes_failure():
    """Test that GraphBuilder handles release node creation failure gracefully."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [
            {
                "key": "days_since_last_release",
                "raw_value": 30,
                "risk_score": 0.2,
            }
        ],
        "top_drivers": [],
    }
    
    builder = GraphBuilder("test/repo", score_data)
    
    # Mock _add_release_nodes to raise an exception
    with patch.object(builder, '_add_release_nodes', side_effect=Exception("GitHub API error")):
        graph = builder.build()
    
    # Graph should still be built
    assert graph is not None
    assert len(graph.nodes) > 0
    
    # Check that warning was added
    assert "warnings" in graph.metadata
    warnings = graph.metadata["warnings"]
    assert len(warnings) > 0
    assert any("release_nodes" in w.get("source", "") for w in warnings)


def test_error_handling_multiple_failures():
    """Test that GraphBuilder handles multiple enrichment failures gracefully."""
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
    
    builder = GraphBuilder("test/repo", score_data)
    
    # Mock multiple methods to raise exceptions
    with patch.object(builder, '_add_maintainer_nodes', side_effect=Exception("Error 1")), \
         patch.object(builder, '_add_risk_factor_nodes', side_effect=Exception("Error 2")), \
         patch.object(builder, '_add_release_nodes', side_effect=Exception("Error 3")):
        graph = builder.build()
    
    # Graph should still be built with at least repo node
    assert graph is not None
    assert len(graph.nodes) >= 1
    
    # Check that all warnings were added
    assert "warnings" in graph.metadata
    warnings = graph.metadata["warnings"]
    assert len(warnings) == 3
    
    # Verify each error is captured
    sources = [w.get("source", "") for w in warnings]
    assert "maintainer_nodes" in sources
    assert "risk_factor_nodes" in sources
    assert "release_nodes" in sources


def test_error_handling_repo_node_failure_raises():
    """Test that GraphBuilder raises exception if repo node creation fails (critical)."""
    score_data = {
        "repo": {},  # Missing required fields
        "overall": {},
        "features": [],
        "top_drivers": [],
    }
    
    builder = GraphBuilder("test/repo", score_data)
    
    # Mock _add_repo_node to raise an exception
    with patch.object(builder, '_add_repo_node', side_effect=Exception("Critical error")):
        # Repo node failure should raise (not graceful)
        with pytest.raises(Exception, match="Critical error"):
            builder.build()


def test_successful_build_has_empty_warnings():
    """Test that successful graph build has empty warnings list."""
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
    
    builder = GraphBuilder("test/repo", score_data)
    graph = builder.build()
    
    # Successful build should have empty warnings
    assert "warnings" in graph.metadata
    assert len(graph.metadata["warnings"]) == 0


def test_warning_structure():
    """Test that warnings have the expected structure."""
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
    
    builder = GraphBuilder("test/repo", score_data)
    
    # Mock to cause a failure
    with patch.object(builder, '_add_maintainer_nodes', side_effect=Exception("Test error")):
        graph = builder.build()
    
    # Check warning structure
    warnings = graph.metadata["warnings"]
    assert len(warnings) > 0
    
    warning = warnings[0]
    assert "source" in warning
    assert "error" in warning
    assert "impact" in warning
    assert warning["source"] == "maintainer_nodes"
    assert warning["error"] == "Test error"
    assert "not included" in warning["impact"].lower()


# Property-Based Tests using Hypothesis

from hypothesis import given, strategies as st, settings
from src.open_source_risk_model.graph.schema import NodeType


# Hypothesis strategies for generating test data

@st.composite
def score_data_strategy(draw):
    """Strategy for generating valid score data."""
    return {
        "repo": {"url": f"https://github.com/{draw(st.text(min_size=1, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'))}/{draw(st.text(min_size=1, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'))}"},
        "overall": {
            "maintenance_risk": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
            "maintenance_label": draw(st.sampled_from(["low", "medium", "high", "critical"])),
            "coverage": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
            "confidence": draw(st.sampled_from(["low", "medium", "high"])),
        },
        "features": draw(st.lists(
            st.fixed_dictionaries({
                "key": st.sampled_from([
                    "contributors_last_12mo",
                    "top_contributor_fraction_12mo",
                    "days_since_last_release",
                    "test_risk_factor"
                ]),
                "raw_value": st.one_of(
                    st.integers(min_value=0, max_value=1000),
                    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
                "risk_score": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            }),
            min_size=0,
            max_size=10
        )),
        "top_drivers": draw(st.lists(
            st.fixed_dictionaries({
                "key": st.text(min_size=1, max_size=30, alphabet='abcdefghijklmnopqrstuvwxyz_'),
                "contribution": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            }),
            min_size=0,
            max_size=5
        )),
    }


@st.composite
def failure_scenario_strategy(draw):
    """Strategy for generating different failure scenarios."""
    # Choose which enrichment functions to fail (at least one, not all)
    fail_maintainer = draw(st.booleans())
    fail_risk_factor = draw(st.booleans())
    fail_release = draw(st.booleans())
    
    # Ensure at least one fails and at least one succeeds
    if not (fail_maintainer or fail_risk_factor or fail_release):
        # If none selected, randomly pick one to fail
        fail_maintainer = True
    
    if fail_maintainer and fail_risk_factor and fail_release:
        # If all selected, randomly pick one to succeed
        choice = draw(st.integers(min_value=0, max_value=2))
        if choice == 0:
            fail_maintainer = False
        elif choice == 1:
            fail_risk_factor = False
        else:
            fail_release = False
    
    return {
        "fail_maintainer": fail_maintainer,
        "fail_risk_factor": fail_risk_factor,
        "fail_release": fail_release,
    }


# Feature: supply-chain-graph, Property 12: Partial Graph Validity
@given(
    score_data=score_data_strategy(),
    failure_scenario=failure_scenario_strategy()
)
@settings(max_examples=100, deadline=None)
def test_property_partial_graph_validity(score_data, failure_scenario):
    """
    Property 12: Partial Graph Validity
    
    For any graph generation where one or more data sources fail, the resulting 
    graph must still be valid (pass all structural invariants) and include nodes 
    from successful data sources.
    
    Validates: Requirements US-3.5
    
    Rationale: External API failures should not break the entire graph. Graceful 
    degradation ensures users get partial data rather than complete failure.
    """
    # Create a full_name from the score_data
    repo_url = score_data["repo"]["url"]
    full_name = repo_url.replace("https://github.com/", "")
    
    builder = GraphBuilder(full_name, score_data)
    
    # Mock GitHub API calls for maintainer nodes
    # Create mock contributors based on score_data
    features = score_data.get("features", [])
    has_contributor_data = any(f["key"] == "contributors_last_12mo" for f in features)
    mock_contributors = []
    if has_contributor_data:
        contributor_value = next((f["raw_value"] for f in features if f["key"] == "contributors_last_12mo"), 0)
        if contributor_value > 0:
            # Create mock contributors (convert to int, ensure at least 1 if value > 0)
            num_contributors = max(1, int(min(contributor_value, 5)))  # Max 5 contributors, min 1 if value > 0
            for i in range(num_contributors):
                mock_contributors.append({
                    "login": f"contributor{i}",
                    "contributions": 100 - (i * 10),
                })
    
    # Mock the enrichment functions to fail based on scenario
    with patch.object(
        builder.github_client,
        'fetch_contributors',
        return_value=mock_contributors
    ), patch.object(
        builder, 
        '_add_maintainer_nodes', 
        side_effect=Exception("Maintainer API timeout") if failure_scenario["fail_maintainer"] else builder._add_maintainer_nodes
    ), patch.object(
        builder,
        '_add_risk_factor_nodes',
        side_effect=Exception("Risk factor processing error") if failure_scenario["fail_risk_factor"] else builder._add_risk_factor_nodes
    ), patch.object(
        builder,
        '_add_release_nodes',
        side_effect=Exception("Release API error") if failure_scenario["fail_release"] else builder._add_release_nodes
    ):
        # Build the graph (should not raise exception)
        graph = builder.build()
    
    # Invariant 1: Graph must not be None
    assert graph is not None, "Graph generation must not return None even with failures"
    
    # Invariant 2: Graph must have at least the repo node (core node always present)
    assert len(graph.nodes) >= 1, "Graph must have at least the repo node"
    
    # Invariant 3: Exactly one REPO node must exist
    repo_nodes = [n for n in graph.nodes if n.type == NodeType.REPO]
    assert len(repo_nodes) == 1, f"Graph must have exactly one REPO node, found {len(repo_nodes)}"
    
    # Invariant 4: All structural invariants must hold (unique IDs, valid edges)
    node_ids = [n.id for n in graph.nodes]
    node_id_set = set(node_ids)
    
    # Check unique node IDs
    assert len(node_ids) == len(node_id_set), \
        f"Node IDs must be unique even with partial failures"
    
    # Check all edges reference existing nodes
    for edge in graph.edges:
        assert edge.source in node_id_set, \
            f"Edge source {edge.source} must reference existing node"
        assert edge.target in node_id_set, \
            f"Edge target {edge.target} must reference existing node"
    
    # Invariant 5: Graph validation should pass (or only have non-critical errors)
    errors = graph.validate()
    # Filter out validation_errors metadata (which is informational)
    critical_errors = [e for e in errors if "validation_errors" not in str(e)]
    assert len(critical_errors) == 0, \
        f"Graph with partial failures must pass validation, got errors: {critical_errors}"
    
    # Invariant 6: Warnings must be present for failed data sources
    assert "warnings" in graph.metadata, "Graph metadata must include warnings field"
    warnings = graph.metadata["warnings"]
    
    # Count expected warnings based on failure scenario
    expected_warning_count = sum([
        failure_scenario["fail_maintainer"],
        failure_scenario["fail_risk_factor"],
        failure_scenario["fail_release"]
    ])
    
    assert len(warnings) == expected_warning_count, \
        f"Expected {expected_warning_count} warnings, got {len(warnings)}"
    
    # Invariant 7: Each warning must have proper structure
    for warning in warnings:
        assert "source" in warning, "Warning must include source field"
        assert "error" in warning, "Warning must include error field"
        assert "impact" in warning, "Warning must include impact field"
    
    # Invariant 8: Successful data sources should have added nodes (when data is available)
    # Note: We only check if nodes were added when we know the data source succeeded
    # AND the data was actually available in the score_data
    
    if not failure_scenario["fail_maintainer"]:
        # If maintainer nodes succeeded, check if maintainer data was available
        features = score_data.get("features", [])
        has_contributor_data = any(f["key"] == "contributors_last_12mo" for f in features)
        if has_contributor_data:
            contributor_value = next((f["raw_value"] for f in features if f["key"] == "contributors_last_12mo"), 0)
            if contributor_value > 0:
                # Should have maintainer nodes
                maintainer_nodes = [n for n in graph.nodes if n.type == NodeType.MAINTAINER]
                assert len(maintainer_nodes) > 0, \
                    f"Successful maintainer source should add maintainer nodes when data available (contributors={contributor_value})"
    
    if not failure_scenario["fail_risk_factor"]:
        # If risk factor nodes succeeded, check if risk data was available
        top_drivers = score_data.get("top_drivers", [])
        # Need to also check that features have the matching keys
        features = score_data.get("features", [])
        feature_keys = {f["key"] for f in features}
        
        # Find drivers that have both significant contribution AND matching feature data
        significant_drivers = [
            d for d in top_drivers 
            if d.get("contribution", 0) >= 0.05 and d.get("key") in feature_keys
        ]
        
        if significant_drivers:
            # Should have risk factor nodes
            risk_nodes = [n for n in graph.nodes if n.type == NodeType.RISK_FACTOR]
            assert len(risk_nodes) > 0, \
                f"Successful risk factor source should add risk nodes when data available (drivers={len(significant_drivers)})"
    
    if not failure_scenario["fail_release"]:
        # If release nodes succeeded, check if release data was available
        features = score_data.get("features", [])
        has_release_data = any(f["key"] == "days_since_last_release" for f in features)
        if has_release_data:
            release_value = next((f["raw_value"] for f in features if f["key"] == "days_since_last_release"), None)
            if release_value is not None:
                # Should have release nodes
                release_nodes = [n for n in graph.nodes if n.type == NodeType.RELEASE]
                assert len(release_nodes) > 0, \
                    f"Successful release source should add release nodes when data available (days_since_release={release_value})"
    
    # Invariant 9: All nodes must have provenance (even in partial graphs)
    for node in graph.nodes:
        assert node.provenance is not None, \
            f"Node {node.id} must have provenance even in partial graph"
        assert "source" in node.provenance, \
            f"Node {node.id} must have source in provenance"
    
    # Invariant 10: All edges must have provenance (even in partial graphs)
    for edge in graph.edges:
        assert edge.provenance is not None, \
            f"Edge {edge.source} -> {edge.target} must have provenance even in partial graph"
        assert "source" in edge.provenance, \
            f"Edge {edge.source} -> {edge.target} must have source in provenance"
