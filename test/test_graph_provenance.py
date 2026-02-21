"""
Tests for graph schema provenance support.
"""

import pytest
from datetime import datetime, timezone
from src.open_source_risk_model.graph.schema import Node, Edge, Graph, NodeType, EdgeType
from src.open_source_risk_model.graph.builder import GraphBuilder


def test_node_with_provenance():
    """Test that nodes can be created with provenance metadata."""
    node = Node(
        id="test:node:1",
        type=NodeType.REPO,
        label="Test Node",
        metadata={"key": "value"},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.95,
        }
    )
    
    assert node.provenance["source"] == "github_api"
    assert "fetched_at" in node.provenance
    assert node.provenance["data_confidence"] == 0.95


def test_edge_with_provenance():
    """Test that edges can be created with provenance metadata."""
    edge = Edge(
        source="node:1",
        target="node:2",
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={"days_ago": 10},
        provenance={
            "source": "github_api",
            "established_at": datetime.now(timezone.utc).isoformat(),
            "confidence": 1.0,
        }
    )
    
    assert edge.provenance["source"] == "github_api"
    assert "established_at" in edge.provenance
    assert edge.provenance["confidence"] == 1.0


def test_node_serialization_includes_provenance():
    """Test that node serialization includes provenance field."""
    node = Node(
        id="test:node:1",
        type=NodeType.REPO,
        label="Test Node",
        metadata={"key": "value"},
        provenance={
            "source": "github_api",
            "fetched_at": "2026-02-17T10:00:00Z",
            "data_confidence": 0.95,
        }
    )
    
    node_dict = node.to_dict()
    assert "provenance" in node_dict
    assert node_dict["provenance"]["source"] == "github_api"
    assert node_dict["provenance"]["data_confidence"] == 0.95


def test_edge_serialization_includes_provenance():
    """Test that edge serialization includes provenance field."""
    edge = Edge(
        source="node:1",
        target="node:2",
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={"days_ago": 10},
        provenance={
            "source": "github_api",
            "established_at": "2026-02-17T10:00:00Z",
            "confidence": 1.0,
        }
    )
    
    edge_dict = edge.to_dict()
    assert "provenance" in edge_dict
    assert edge_dict["provenance"]["source"] == "github_api"
    assert edge_dict["provenance"]["confidence"] == 1.0


def test_graph_validation_missing_provenance():
    """Test that graph validation detects missing provenance."""
    graph = Graph()
    
    # Add node without provenance
    node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={}
    )
    graph.add_node(node)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("provenance" in error.lower() for error in errors)


def test_graph_validation_invalid_confidence():
    """Test that graph validation detects invalid confidence values."""
    graph = Graph()
    
    # Add node with invalid confidence
    node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": "2026-02-17T10:00:00Z",
            "confidence": 1.5,  # Invalid: > 1.0
        }
    )
    graph.add_node(node)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("confidence" in error.lower() and "1.0" in error for error in errors)


def test_graph_validation_valid_provenance():
    """Test that graph validation passes with valid provenance."""
    graph = Graph()
    
    # Add node with valid provenance
    node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": "2026-02-17T10:00:00Z",
            "data_confidence": 0.95,
        }
    )
    graph.add_node(node)
    
    errors = graph.validate()
    # Should only have no errors or non-provenance errors
    provenance_errors = [e for e in errors if "provenance" in e.lower()]
    assert len(provenance_errors) == 0


def test_graph_builder_adds_provenance_to_nodes():
    """Test that GraphBuilder adds provenance to all nodes."""
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
    graph = builder.build()
    
    # Check that all nodes have provenance
    for node in graph.nodes:
        assert "source" in node.provenance, f"Node {node.id} missing source in provenance"
        assert "fetched_at" in node.provenance or "established_at" in node.provenance, \
            f"Node {node.id} missing timestamp in provenance"


def test_graph_builder_adds_provenance_to_edges():
    """Test that GraphBuilder adds provenance to all edges."""
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
    graph = builder.build()
    
    # Check that all edges have provenance
    for edge in graph.edges:
        assert "source" in edge.provenance, \
            f"Edge {edge.source} -> {edge.target} missing source in provenance"
        assert "established_at" in edge.provenance or "fetched_at" in edge.provenance, \
            f"Edge {edge.source} -> {edge.target} missing timestamp in provenance"


def test_graph_serialization_includes_provenance():
    """Test that full graph serialization includes provenance."""
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
    graph = builder.build()
    graph_dict = graph.to_dict()
    
    # Check that serialized nodes include provenance
    for node_dict in graph_dict["nodes"]:
        assert "provenance" in node_dict, f"Serialized node missing provenance: {node_dict['id']}"
    
    # Check that serialized edges include provenance
    for edge_dict in graph_dict["edges"]:
        assert "provenance" in edge_dict, \
            f"Serialized edge missing provenance: {edge_dict['source']} -> {edge_dict['target']}"


# Property-Based Tests using Hypothesis

from hypothesis import given, strategies as st, settings


# Hypothesis strategies for generating test data

@st.composite
def node_type_strategy(draw):
    """Strategy for generating valid NodeType values."""
    return draw(st.sampled_from(list(NodeType)))


@st.composite
def edge_type_strategy(draw):
    """Strategy for generating valid EdgeType values."""
    return draw(st.sampled_from(list(EdgeType)))


@st.composite
def valid_confidence_strategy(draw):
    """Strategy for generating valid confidence values (0.0-1.0)."""
    return draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))


@st.composite
def provenance_strategy(draw, use_fetched_at=True):
    """Strategy for generating valid provenance metadata."""
    source = draw(st.sampled_from(["github_api", "osv", "score_model", "heuristic", "registry_api"]))
    
    provenance = {
        "source": source,
    }
    
    # Add timestamp (either fetched_at or established_at)
    if use_fetched_at:
        provenance["fetched_at"] = datetime.now(timezone.utc).isoformat()
    else:
        provenance["established_at"] = datetime.now(timezone.utc).isoformat()
    
    # Optionally add confidence fields
    if draw(st.booleans()):
        provenance["confidence"] = draw(valid_confidence_strategy())
    if draw(st.booleans()):
        provenance["data_confidence"] = draw(valid_confidence_strategy())
    if draw(st.booleans()):
        provenance["match_confidence"] = draw(valid_confidence_strategy())
    
    return provenance


@st.composite
def node_strategy(draw):
    """Strategy for generating valid Node objects with provenance."""
    node_type = draw(node_type_strategy())
    node_id = f"{node_type.value}:{draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='/-_')))}"
    
    return Node(
        id=node_id,
        type=node_type,
        label=draw(st.text(min_size=1, max_size=100)),
        metadata=draw(st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(st.text(), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans()),
            max_size=10
        )),
        provenance=draw(provenance_strategy(use_fetched_at=True))
    )


@st.composite
def edge_strategy(draw, node_ids):
    """Strategy for generating valid Edge objects with provenance."""
    if len(node_ids) < 2:
        # Need at least 2 nodes to create an edge
        return None
    
    source = draw(st.sampled_from(node_ids))
    target = draw(st.sampled_from([nid for nid in node_ids if nid != source]))
    
    return Edge(
        source=source,
        target=target,
        relationship_type=draw(edge_type_strategy()),
        metadata=draw(st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(st.text(), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans()),
            max_size=10
        )),
        provenance=draw(provenance_strategy(use_fetched_at=False))
    )


@st.composite
def graph_with_provenance_strategy(draw):
    """Strategy for generating valid Graph objects with provenance on all nodes and edges."""
    # Always include exactly one REPO node
    repo_node = Node(
        id=f"repo:{draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='/-_')))}",
        type=NodeType.REPO,
        label=draw(st.text(min_size=1, max_size=100)),
        metadata={},
        provenance=draw(provenance_strategy(use_fetched_at=True))
    )
    
    nodes = [repo_node]
    
    # Add random number of other nodes (0-20)
    num_additional_nodes = draw(st.integers(min_value=0, max_value=20))
    for _ in range(num_additional_nodes):
        node = draw(node_strategy())
        # Ensure unique IDs
        if node.id not in [n.id for n in nodes]:
            nodes.append(node)
    
    # Generate edges between nodes
    edges = []
    node_ids = [n.id for n in nodes]
    
    if len(node_ids) > 1:
        num_edges = draw(st.integers(min_value=0, max_value=min(len(node_ids) * 2, 30)))
        for _ in range(num_edges):
            edge = draw(edge_strategy(node_ids))
            if edge is not None:
                edges.append(edge)
    
    return Graph(
        nodes=nodes,
        edges=edges,
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


# Feature: supply-chain-graph, Property 13: Provenance Completeness
@given(graph=graph_with_provenance_strategy())
@settings(max_examples=100, deadline=None)
def test_property_provenance_completeness(graph):
    """
    Property 13: Provenance Completeness
    
    For any node or edge in a graph, it must include provenance metadata 
    with source, timestamp, and confidence fields.
    
    Validates: Requirements US-1.3, US-1.4
    
    Rationale: Provenance transforms the graph from "cool visualization" into 
    a trustworthy risk artifact. Users must be able to trace where data came from, 
    when it was fetched, and how confident we are in it.
    """
    # Check all nodes have complete provenance
    for node in graph.nodes:
        # Must have provenance dict
        assert node.provenance is not None, f"Node {node.id} missing provenance"
        assert isinstance(node.provenance, dict), f"Node {node.id} provenance is not a dict"
        
        # Must have source
        assert "source" in node.provenance, f"Node {node.id} missing 'source' in provenance"
        assert node.provenance["source"], f"Node {node.id} has empty 'source' in provenance"
        
        # Must have timestamp (either fetched_at or established_at)
        has_timestamp = "fetched_at" in node.provenance or "established_at" in node.provenance
        assert has_timestamp, f"Node {node.id} missing timestamp in provenance (fetched_at or established_at)"
        
        # If confidence fields present, they must be valid (0.0-1.0)
        for conf_field in ["confidence", "data_confidence", "match_confidence"]:
            if conf_field in node.provenance:
                conf_value = node.provenance[conf_field]
                assert isinstance(conf_value, (int, float)), \
                    f"Node {node.id} {conf_field} must be numeric, got {type(conf_value)}"
                assert 0.0 <= conf_value <= 1.0, \
                    f"Node {node.id} {conf_field} must be in [0.0, 1.0], got {conf_value}"
    
    # Check all edges have complete provenance
    for edge in graph.edges:
        # Must have provenance dict
        assert edge.provenance is not None, \
            f"Edge {edge.source} -> {edge.target} missing provenance"
        assert isinstance(edge.provenance, dict), \
            f"Edge {edge.source} -> {edge.target} provenance is not a dict"
        
        # Must have source
        assert "source" in edge.provenance, \
            f"Edge {edge.source} -> {edge.target} missing 'source' in provenance"
        assert edge.provenance["source"], \
            f"Edge {edge.source} -> {edge.target} has empty 'source' in provenance"
        
        # Must have timestamp (either fetched_at or established_at)
        has_timestamp = "fetched_at" in edge.provenance or "established_at" in edge.provenance
        assert has_timestamp, \
            f"Edge {edge.source} -> {edge.target} missing timestamp in provenance"
        
        # If confidence fields present, they must be valid (0.0-1.0)
        for conf_field in ["confidence", "data_confidence", "match_confidence"]:
            if conf_field in edge.provenance:
                conf_value = edge.provenance[conf_field]
                assert isinstance(conf_value, (int, float)), \
                    f"Edge {edge.source} -> {edge.target} {conf_field} must be numeric"
                assert 0.0 <= conf_value <= 1.0, \
                    f"Edge {edge.source} -> {edge.target} {conf_field} must be in [0.0, 1.0]"


# Additional property test: GraphBuilder produces graphs with complete provenance
@given(
    contributors=st.integers(min_value=0, max_value=100),
    top_contributor_fraction=valid_confidence_strategy(),
    days_since_release=st.one_of(st.none(), st.integers(min_value=0, max_value=1000)),
    risk_contribution=valid_confidence_strategy()
)
@settings(max_examples=100, deadline=None)
def test_property_graph_builder_provenance_completeness(
    contributors, top_contributor_fraction, days_since_release, risk_contribution
):
    """
    Property 13 (GraphBuilder variant): Provenance Completeness for GraphBuilder
    
    For any graph generated by GraphBuilder, all nodes and edges must include 
    complete provenance metadata.
    
    Validates: Requirements US-1.3, US-1.4
    """
    # Create score data with random values
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
                "raw_value": contributors,
                "risk_score": 0.2,
            },
            {
                "key": "top_contributor_fraction_12mo",
                "raw_value": top_contributor_fraction,
                "risk_score": 0.3,
            },
        ],
        "top_drivers": [],
    }
    
    # Add release data if specified
    if days_since_release is not None:
        score_data["features"].append({
            "key": "days_since_last_release",
            "raw_value": days_since_release,
            "risk_score": 0.2,
        })
    
    # Add a risk factor with significant contribution
    if risk_contribution >= 0.05:
        score_data["features"].append({
            "key": "test_risk_factor",
            "label": "Test Risk Factor",
            "raw_value": 100,
            "risk_score": 0.5,
            "contribution": risk_contribution,
            "weight": 1.0,
            "category": "test",
        })
        score_data["top_drivers"] = [{
            "key": "test_risk_factor",
            "contribution": risk_contribution,
        }]
    
    # Build graph
    builder = GraphBuilder("test/repo", score_data)
    graph = builder.build()
    
    # Verify all nodes have complete provenance
    for node in graph.nodes:
        assert node.provenance, f"Node {node.id} missing provenance"
        assert "source" in node.provenance, f"Node {node.id} missing 'source' in provenance"
        has_timestamp = "fetched_at" in node.provenance or "established_at" in node.provenance
        assert has_timestamp, f"Node {node.id} missing timestamp in provenance"
    
    # Verify all edges have complete provenance
    for edge in graph.edges:
        assert edge.provenance, f"Edge {edge.source} -> {edge.target} missing provenance"
        assert "source" in edge.provenance, \
            f"Edge {edge.source} -> {edge.target} missing 'source' in provenance"
        has_timestamp = "fetched_at" in edge.provenance or "established_at" in edge.provenance
        assert has_timestamp, \
            f"Edge {edge.source} -> {edge.target} missing timestamp in provenance"
