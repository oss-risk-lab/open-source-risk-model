"""
Tests for enhanced graph validation logic.
"""

import pytest
from datetime import datetime, timezone
from src.open_source_risk_model.graph.schema import Node, Edge, Graph, NodeType, EdgeType


def test_validation_duplicate_node_ids():
    """Test that validation detects duplicate node IDs."""
    graph = Graph()
    
    # Add two nodes with the same ID
    node1 = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.95,
        }
    )
    node2 = Node(
        id="repo:test/repo",  # Duplicate ID
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0,
        }
    )
    
    graph.add_node(node1)
    graph.add_node(node2)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("duplicate" in error.lower() for error in errors)


def test_validation_invalid_edge_references():
    """Test that validation detects edges referencing non-existent nodes."""
    graph = Graph()
    
    # Add a repo node
    node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.95,
        }
    )
    graph.add_node(node)
    
    # Add edge referencing non-existent node
    edge = Edge(
        source="repo:test/repo",
        target="release:test/repo:v1.0.0",  # This node doesn't exist
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={},
        provenance={
            "source": "github_api",
            "established_at": datetime.now(timezone.utc).isoformat(),
            "confidence": 1.0,
        }
    )
    graph.add_edge(edge)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("invalid" in error.lower() and "target" in error.lower() for error in errors)


def test_validation_no_repo_node():
    """Test that validation detects missing repo node."""
    graph = Graph()
    
    # Add a non-repo node
    node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0,
        }
    )
    graph.add_node(node)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("repo" in error.lower() and "one" in error.lower() for error in errors)


def test_validation_multiple_repo_nodes():
    """Test that validation detects multiple repo nodes."""
    graph = Graph()
    
    # Add two repo nodes
    node1 = Node(
        id="repo:test/repo1",
        type=NodeType.REPO,
        label="test/repo1",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.95,
        }
    )
    node2 = Node(
        id="repo:test/repo2",
        type=NodeType.REPO,
        label="test/repo2",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.95,
        }
    )
    
    graph.add_node(node1)
    graph.add_node(node2)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("multiple" in error.lower() and "repo" in error.lower() for error in errors)


def test_validation_valid_graph():
    """Test that validation passes for a valid graph."""
    graph = Graph()
    
    # Add repo node
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.95,
        }
    )
    graph.add_node(repo_node)
    
    # Add release node
    release_node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0,
        }
    )
    graph.add_node(release_node)
    
    # Add edge
    edge = Edge(
        source="repo:test/repo",
        target="release:test/repo:v1.0.0",
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={},
        provenance={
            "source": "github_api",
            "established_at": datetime.now(timezone.utc).isoformat(),
            "confidence": 1.0,
        }
    )
    graph.add_edge(edge)
    
    errors = graph.validate()
    assert len(errors) == 0


def test_validation_confidence_range():
    """Test that validation checks confidence values are in range 0.0-1.0."""
    graph = Graph()
    
    # Test confidence > 1.0
    node1 = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "confidence": 1.5,  # Invalid
        }
    )
    graph.add_node(node1)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("confidence" in error.lower() and "1.0" in error for error in errors)
    
    # Test confidence < 0.0
    graph2 = Graph()
    node2 = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": -0.1,  # Invalid
        }
    )
    graph2.add_node(node2)
    
    errors2 = graph2.validate()
    assert len(errors2) > 0
    assert any("confidence" in error.lower() and "0.0" in error for error in errors2)


def test_validation_missing_source():
    """Test that validation detects missing source in provenance."""
    graph = Graph()
    
    node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            # Missing "source"
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.95,
        }
    )
    graph.add_node(node)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("source" in error.lower() for error in errors)


def test_validation_missing_timestamp():
    """Test that validation detects missing timestamp in provenance."""
    graph = Graph()
    
    node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={},
        provenance={
            "source": "github_api",
            # Missing "fetched_at" or "established_at"
            "data_confidence": 0.95,
        }
    )
    graph.add_node(node)
    
    errors = graph.validate()
    assert len(errors) > 0
    assert any("timestamp" in error.lower() for error in errors)


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
def node_strategy(draw, node_type=None):
    """Strategy for generating valid Node objects with provenance."""
    if node_type is None:
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
def valid_graph_strategy(draw):
    """Strategy for generating valid Graph objects that satisfy all invariants."""
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
        # Generate non-REPO nodes
        node_type = draw(st.sampled_from([nt for nt in NodeType if nt != NodeType.REPO]))
        node = draw(node_strategy(node_type=node_type))
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


# Feature: supply-chain-graph, Property 1: Graph Validity Invariant
@given(graph=valid_graph_strategy())
@settings(max_examples=100, deadline=None)
def test_property_graph_validity_invariant(graph):
    """
    Property 1: Graph Validity Invariant
    
    For any generated graph, all edges must reference existing node IDs, 
    all node IDs must be unique, and exactly one REPO node must exist.
    
    Validates: Requirements US-1.2, US-1.5
    
    Rationale: This is a fundamental invariant that ensures graph structural 
    integrity. A graph with orphaned edges or duplicate IDs is invalid and 
    will cause visualization and analysis failures.
    """
    # Collect all node IDs
    node_ids = [node.id for node in graph.nodes]
    node_id_set = set(node_ids)
    
    # Invariant 1: All node IDs must be unique
    assert len(node_ids) == len(node_id_set), \
        f"Duplicate node IDs found: {[nid for nid in node_ids if node_ids.count(nid) > 1]}"
    
    # Invariant 2: All edges must reference existing node IDs
    for edge in graph.edges:
        assert edge.source in node_id_set, \
            f"Edge references non-existent source node: {edge.source}"
        assert edge.target in node_id_set, \
            f"Edge references non-existent target node: {edge.target}"
    
    # Invariant 3: Exactly one REPO node must exist
    repo_nodes = [node for node in graph.nodes if node.type == NodeType.REPO]
    assert len(repo_nodes) == 1, \
        f"Graph must have exactly one REPO node, found {len(repo_nodes)}"
    
    # Additional check: Graph validation should pass
    errors = graph.validate()
    assert len(errors) == 0, \
        f"Valid graph failed validation with errors: {errors}"
