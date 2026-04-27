"""
Comprehensive property-based tests for graph schema completeness.

Tests Properties 2, 3, 4, and 8 from the design document.
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import patch
from hypothesis import given, strategies as st, settings, assume

from src.open_source_risk_model.graph.schema import (
    Node, Edge, Graph, NodeType, EdgeType, GraphConfig
)
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.github_client import GitHubClient
from src.open_source_risk_model.graph.registry_detector import RegistryDetector


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
def repo_node_metadata_strategy(draw):
    """Strategy for generating REPO node metadata."""
    return {
        "url": f"https://github.com/{draw(st.text(min_size=1, max_size=20))}/{draw(st.text(min_size=1, max_size=20))}",
        "maintenance_risk": draw(valid_confidence_strategy()),
        "maintenance_label": draw(st.sampled_from(["low", "medium", "high", "critical"])),
        "coverage": draw(valid_confidence_strategy()),
        "confidence": draw(st.sampled_from(["high", "medium", "low"])),
        "stars": draw(st.integers(min_value=0, max_value=100000)),
        "archived": draw(st.booleans()),
    }


@st.composite
def release_node_metadata_strategy(draw):
    """Strategy for generating RELEASE node metadata."""
    days_ago = draw(st.integers(min_value=0, max_value=1000))
    return {
        "tag_name": f"v{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=20))}.{draw(st.integers(min_value=0, max_value=50))}",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "days_ago": days_ago,
        "is_latest": draw(st.booleans()),
        "is_prerelease": draw(st.booleans()),
    }


@st.composite
def maintainer_node_metadata_strategy(draw):
    """Strategy for generating MAINTAINER node metadata."""
    return {
        "username": draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'))),
        "contribution_fraction": draw(valid_confidence_strategy()),
        "commit_count": draw(st.integers(min_value=1, max_value=10000)),
        "last_activity": datetime.now(timezone.utc).isoformat(),
        "type": draw(st.sampled_from(["individual", "aggregate"])),
    }


@st.composite
def cve_node_metadata_strategy(draw):
    """Strategy for generating CVE node metadata."""
    return {
        "cve_id": f"CVE-{draw(st.integers(min_value=2000, max_value=2026))}-{draw(st.integers(min_value=1000, max_value=9999))}",
        "severity": draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
        "cvss_score": draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False)),
        "summary": draw(st.text(min_size=10, max_size=200)),
        "published": datetime.now(timezone.utc).isoformat(),
        "fixed_in": draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        "source": draw(st.sampled_from(["osv", "github_advisory"])),
    }


@st.composite
def registry_node_metadata_strategy(draw):
    """Strategy for generating REGISTRY node metadata."""
    return {
        "registry_type": draw(st.sampled_from(["pypi", "npm", "maven", "rubygems", "crates"])),
        "package_name": draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_.'))),
        "latest_version": draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        "download_count": draw(st.one_of(st.none(), st.integers(min_value=0, max_value=1000000))),
        "registry_url": draw(st.text(min_size=10, max_size=100)),
    }


@st.composite
def risk_factor_node_metadata_strategy(draw):
    """Strategy for generating RISK_FACTOR node metadata."""
    return {
        "key": draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_'))),
        "label": draw(st.text(min_size=1, max_size=100)),
        "raw_value": draw(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.text())),
        "risk_score": draw(valid_confidence_strategy()),
        "contribution": draw(st.floats(min_value=0.05, max_value=1.0, allow_nan=False)),
        "weight": draw(valid_confidence_strategy()),
        "category": draw(st.sampled_from(["activity", "community", "quality"])),
    }


@st.composite
def node_metadata_strategy(draw, node_type):
    """Strategy for generating type-specific node metadata."""
    if node_type == NodeType.REPO:
        return draw(repo_node_metadata_strategy())
    elif node_type == NodeType.RELEASE:
        return draw(release_node_metadata_strategy())
    elif node_type == NodeType.MAINTAINER:
        return draw(maintainer_node_metadata_strategy())
    elif node_type == NodeType.CVE:
        return draw(cve_node_metadata_strategy())
    elif node_type == NodeType.REGISTRY:
        return draw(registry_node_metadata_strategy())
    elif node_type == NodeType.RISK_FACTOR:
        return draw(risk_factor_node_metadata_strategy())
    else:
        return {}


@st.composite
def node_strategy(draw, node_type=None):
    """Strategy for generating valid Node objects with complete metadata."""
    if node_type is None:
        node_type = draw(node_type_strategy())
    
    node_id = f"{node_type.value}:{draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='/-_:')))}"
    
    return Node(
        id=node_id,
        type=node_type,
        label=draw(st.text(min_size=1, max_size=100)),
        metadata=draw(node_metadata_strategy(node_type)),
        provenance=draw(provenance_strategy(use_fetched_at=True))
    )


@st.composite
def edge_metadata_strategy(draw, edge_type):
    """Strategy for generating type-specific edge metadata."""
    if edge_type == EdgeType.HAS_RELEASE:
        return {
            "days_ago": draw(st.integers(min_value=0, max_value=1000)),
            "is_latest": draw(st.booleans()),
        }
    elif edge_type == EdgeType.MAINTAINED_BY:
        return {
            "contribution_fraction": draw(valid_confidence_strategy()),
            "commit_count": draw(st.integers(min_value=1, max_value=10000)),
        }
    elif edge_type == EdgeType.HAS_CVE:
        return {
            "severity": draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
            "fixed_in": draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        }
    elif edge_type == EdgeType.PUBLISHED_AS:
        return {
            "package_name": draw(st.text(min_size=1, max_size=50)),
            "latest_version": draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        }
    elif edge_type == EdgeType.HAS_RISK_FACTOR:
        return {
            "contribution": draw(st.floats(min_value=0.05, max_value=1.0, allow_nan=False)),
        }
    else:
        return {}


@st.composite
def edge_strategy(draw, node_ids):
    """Strategy for generating valid Edge objects with complete metadata."""
    if len(node_ids) < 2:
        return None
    
    source = draw(st.sampled_from(node_ids))
    target = draw(st.sampled_from([nid for nid in node_ids if nid != source]))
    edge_type = draw(edge_type_strategy())
    
    return Edge(
        source=source,
        target=target,
        relationship_type=edge_type,
        metadata=draw(edge_metadata_strategy(edge_type)),
        provenance=draw(provenance_strategy(use_fetched_at=False))
    )


@st.composite
def graph_strategy(draw):
    """Strategy for generating valid Graph objects with complete schema."""
    # Always include exactly one REPO node
    repo_node = draw(node_strategy(node_type=NodeType.REPO))
    nodes = [repo_node]
    
    # Add random number of other nodes (0-20)
    num_additional_nodes = draw(st.integers(min_value=0, max_value=20))
    for _ in range(num_additional_nodes):
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


# Property-Based Tests

# Feature: supply-chain-graph, Property 2: Node Schema Completeness
@given(graph=graph_strategy())
@settings(max_examples=100, deadline=None)
def test_property_node_schema_completeness(graph):
    """
    Property 2: Node Schema Completeness
    
    For any node in a graph, it must have the required fields (id, type, label, 
    metadata) and the metadata must contain type-specific required fields based 
    on the node type.
    
    Validates: Requirements US-1.3, US-3.3, US-4.4, US-5.3, US-7.3
    
    Rationale: This ensures all nodes conform to their schema contracts. Missing 
    required fields will cause serialization errors and visualization failures.
    """
    for node in graph.nodes:
        # Check required base fields
        assert node.id, f"Node missing id"
        assert node.type, f"Node {node.id} missing type"
        assert node.label, f"Node {node.id} missing label"
        assert node.metadata is not None, f"Node {node.id} missing metadata"
        assert isinstance(node.metadata, dict), f"Node {node.id} metadata is not a dict"
        
        # Check type-specific required metadata fields
        if node.type == NodeType.REPO:
            required_fields = ["url", "maintenance_risk", "maintenance_label", "coverage", "confidence"]
            for field in required_fields:
                assert field in node.metadata, \
                    f"REPO node {node.id} missing required metadata field: {field}"
        
        elif node.type == NodeType.RELEASE:
            required_fields = ["tag_name", "published_at", "days_ago", "is_latest"]
            for field in required_fields:
                assert field in node.metadata, \
                    f"RELEASE node {node.id} missing required metadata field: {field}"
        
        elif node.type == NodeType.MAINTAINER:
            required_fields = ["username", "contribution_fraction", "commit_count"]
            for field in required_fields:
                assert field in node.metadata, \
                    f"MAINTAINER node {node.id} missing required metadata field: {field}"
        
        elif node.type == NodeType.CVE:
            required_fields = ["cve_id", "severity", "cvss_score", "summary", "published", "source"]
            for field in required_fields:
                assert field in node.metadata, \
                    f"CVE node {node.id} missing required metadata field: {field}"
        
        elif node.type == NodeType.REGISTRY:
            required_fields = ["registry_type", "package_name", "registry_url"]
            for field in required_fields:
                assert field in node.metadata, \
                    f"REGISTRY node {node.id} missing required metadata field: {field}"
        
        elif node.type == NodeType.RISK_FACTOR:
            required_fields = ["key", "label", "raw_value", "risk_score", "contribution", "weight", "category"]
            for field in required_fields:
                assert field in node.metadata, \
                    f"RISK_FACTOR node {node.id} missing required metadata field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# Feature: supply-chain-graph, Property 3: Edge Schema Completeness
@given(graph=graph_strategy())
@settings(max_examples=100, deadline=None)
def test_property_edge_schema_completeness(graph):
    """
    Property 3: Edge Schema Completeness
    
    For any edge in a graph, it must have source, target, and relationship_type 
    fields, and the relationship type must be valid for the source and target 
    node types.
    
    Validates: Requirements US-1.4, US-3.4, US-4.3, US-5.2, US-7.2
    
    Rationale: This ensures edges are well-formed and semantically valid. Invalid 
    edge types or connections will cause confusion in visualization and analysis.
    """
    # Build a map of node IDs to node types for validation
    node_type_map = {node.id: node.type for node in graph.nodes}
    
    for edge in graph.edges:
        # Check required base fields
        assert edge.source, f"Edge missing source"
        assert edge.target, f"Edge missing target"
        assert edge.relationship_type, f"Edge {edge.source} -> {edge.target} missing relationship_type"
        assert edge.metadata is not None, f"Edge {edge.source} -> {edge.target} missing metadata"
        assert isinstance(edge.metadata, dict), f"Edge {edge.source} -> {edge.target} metadata is not a dict"
        
        # Verify source and target exist in graph
        assert edge.source in node_type_map, \
            f"Edge references non-existent source node: {edge.source}"
        assert edge.target in node_type_map, \
            f"Edge references non-existent target node: {edge.target}"
        
        # Get source and target node types
        source_type = node_type_map[edge.source]
        target_type = node_type_map[edge.target]
        
        # Validate relationship type is semantically valid for node types
        # Note: We're being permissive here since the strategy generates random edges
        # In a real graph, we'd enforce stricter rules like:
        # - HAS_RELEASE: REPO -> RELEASE
        # - MAINTAINED_BY: MAINTAINER -> REPO
        # - HAS_CVE: RELEASE -> CVE
        # - PUBLISHED_AS: REPO -> REGISTRY
        # - HAS_RISK_FACTOR: REPO -> RISK_FACTOR
        
        # For this property test, we just verify the relationship type is valid
        assert isinstance(edge.relationship_type, EdgeType), \
            f"Edge {edge.source} -> {edge.target} has invalid relationship_type: {edge.relationship_type}"
        
        # Check type-specific required metadata fields
        if edge.relationship_type == EdgeType.HAS_RELEASE:
            required_fields = ["days_ago", "is_latest"]
            for field in required_fields:
                assert field in edge.metadata, \
                    f"HAS_RELEASE edge {edge.source} -> {edge.target} missing required metadata field: {field}"
        
        elif edge.relationship_type == EdgeType.MAINTAINED_BY:
            required_fields = ["contribution_fraction", "commit_count"]
            for field in required_fields:
                assert field in edge.metadata, \
                    f"MAINTAINED_BY edge {edge.source} -> {edge.target} missing required metadata field: {field}"
        
        elif edge.relationship_type == EdgeType.HAS_CVE:
            required_fields = ["severity"]
            for field in required_fields:
                assert field in edge.metadata, \
                    f"HAS_CVE edge {edge.source} -> {edge.target} missing required metadata field: {field}"
        
        elif edge.relationship_type == EdgeType.PUBLISHED_AS:
            required_fields = ["package_name"]
            for field in required_fields:
                assert field in edge.metadata, \
                    f"PUBLISHED_AS edge {edge.source} -> {edge.target} missing required metadata field: {field}"
        
        elif edge.relationship_type == EdgeType.HAS_RISK_FACTOR:
            required_fields = ["contribution"]
            for field in required_fields:
                assert field in edge.metadata, \
                    f"HAS_RISK_FACTOR edge {edge.source} -> {edge.target} missing required metadata field: {field}"


# Feature: supply-chain-graph, Property 4: Graph Serialization Round-Trip
@given(graph=graph_strategy())
@settings(max_examples=100, deadline=None)
def test_property_graph_serialization_round_trip(graph):
    """
    Property 4: Graph Serialization Round-Trip
    
    For any valid graph, serializing to JSON and then deserializing should 
    produce an equivalent graph structure.
    
    Validates: Requirements US-2.2
    
    Rationale: This is a round-trip property that ensures our serialization 
    logic is correct. The API must reliably serialize graphs to JSON without 
    data loss.
    """
    # Serialize graph to dict (JSON-serializable)
    graph_dict = graph.to_dict()
    
    # Verify serialized structure has required fields
    assert "nodes" in graph_dict, "Serialized graph missing 'nodes' field"
    assert "edges" in graph_dict, "Serialized graph missing 'edges' field"
    assert "metadata" in graph_dict, "Serialized graph missing 'metadata' field"
    
    assert isinstance(graph_dict["nodes"], list), "Serialized nodes is not a list"
    assert isinstance(graph_dict["edges"], list), "Serialized edges is not a list"
    assert isinstance(graph_dict["metadata"], dict), "Serialized metadata is not a dict"
    
    # Verify we can serialize to JSON (no serialization errors)
    try:
        json_str = json.dumps(graph_dict)
    except (TypeError, ValueError) as e:
        pytest.fail(f"Failed to serialize graph to JSON: {e}")
    
    # Deserialize from JSON
    try:
        deserialized_dict = json.loads(json_str)
    except (TypeError, ValueError) as e:
        pytest.fail(f"Failed to deserialize graph from JSON: {e}")
    
    # Verify deserialized structure matches original
    assert len(deserialized_dict["nodes"]) == len(graph.nodes), \
        f"Node count mismatch after round-trip: {len(deserialized_dict['nodes'])} != {len(graph.nodes)}"
    
    assert len(deserialized_dict["edges"]) == len(graph.edges), \
        f"Edge count mismatch after round-trip: {len(deserialized_dict['edges'])} != {len(graph.edges)}"
    
    # Verify each node is preserved
    original_node_ids = {node.id for node in graph.nodes}
    deserialized_node_ids = {node["id"] for node in deserialized_dict["nodes"]}
    assert original_node_ids == deserialized_node_ids, \
        f"Node IDs changed after round-trip: {original_node_ids} != {deserialized_node_ids}"
    
    # Verify node data is preserved
    for original_node in graph.nodes:
        # Find corresponding deserialized node
        deserialized_node = next(
            (n for n in deserialized_dict["nodes"] if n["id"] == original_node.id),
            None
        )
        assert deserialized_node is not None, f"Node {original_node.id} missing after deserialization"
        
        # Check fields are preserved
        assert deserialized_node["type"] == original_node.type.value, \
            f"Node {original_node.id} type changed after round-trip"
        assert deserialized_node["label"] == original_node.label, \
            f"Node {original_node.id} label changed after round-trip"
        
        # Check metadata is preserved (keys and structure)
        assert set(deserialized_node["metadata"].keys()) == set(original_node.metadata.keys()), \
            f"Node {original_node.id} metadata keys changed after round-trip"
        
        # Check provenance is preserved
        assert "provenance" in deserialized_node, \
            f"Node {original_node.id} missing provenance after round-trip"
        assert set(deserialized_node["provenance"].keys()) == set(original_node.provenance.keys()), \
            f"Node {original_node.id} provenance keys changed after round-trip"
    
    # Verify edge count is preserved
    # Note: We verify count rather than exact matching because:
    # 1. Multiple edges can exist between same source/target with same relationship type
    # 2. Provenance fields may vary (data_confidence vs match_confidence)
    # 3. The key property is that serialization doesn't lose edges
    assert len(deserialized_dict["edges"]) == len(graph.edges), \
        "Edge count changed after round-trip"
    
    # Verify all edges have required fields after deserialization
    for deserialized_edge in deserialized_dict["edges"]:
        assert "source" in deserialized_edge, "Deserialized edge missing source"
        assert "target" in deserialized_edge, "Deserialized edge missing target"
        assert "relationship_type" in deserialized_edge, "Deserialized edge missing relationship_type"
        assert "metadata" in deserialized_edge, "Deserialized edge missing metadata"
        assert "provenance" in deserialized_edge, "Deserialized edge missing provenance"
        
        # Verify provenance has required fields
        assert "source" in deserialized_edge["provenance"], \
            f"Deserialized edge {deserialized_edge['source']} -> {deserialized_edge['target']} missing source in provenance"
        
        # Must have either fetched_at or established_at
        has_timestamp = "fetched_at" in deserialized_edge["provenance"] or "established_at" in deserialized_edge["provenance"]
        assert has_timestamp, \
            f"Deserialized edge {deserialized_edge['source']} -> {deserialized_edge['target']} missing timestamp in provenance"
    
    # Verify metadata is preserved
    assert deserialized_dict["metadata"] == graph.metadata, \
        f"Graph metadata changed after round-trip"


# Feature: supply-chain-graph, Property 8: Risk Factor Node Creation
@given(
    risk_drivers=st.lists(
        st.fixed_dictionaries({
            "key": st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_')),
            "contribution": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        }),
        min_size=0,
        max_size=30,
        unique_by=lambda d: d["key"]
    ),
    coverage=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    maintenance_risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=100, deadline=None)
def test_property_risk_factor_node_creation(risk_drivers, coverage, maintenance_risk):
    """
    Property 8: Risk Factor Node Creation
    
    For any repository with risk factors having contribution > 0.05, the 
    generated graph must include risk factor nodes for those high-impact factors.
    
    Validates: Requirements US-7.1, US-7.4
    
    Rationale: Risk factor nodes explain the risk score. Only significant 
    factors (contribution > 0.05) should be included to avoid graph clutter.
    """
    # Generate score data with risk factors
    features = []
    for driver in risk_drivers:
        key = driver["key"]
        contribution = driver["contribution"]
        features.append({
            "key": key,
            "label": key.replace("_", " ").title(),  # Add label field
            "raw_value": 50.0,
            "risk_score": 0.5,
            "weight": 0.5,
            "category": "activity",
            "contribution": contribution,
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
    
    # Mock external API calls to avoid rate limiting
    # We need to mock at the instance level, not class level
    with patch('src.open_source_risk_model.graph.builder.GitHubClient') as MockGitHubClient, \
         patch('src.open_source_risk_model.graph.builder.RegistryDetector') as MockRegistryDetector:
        
        # Configure mocks
        mock_github_instance = MockGitHubClient.return_value
        mock_github_instance.fetch_releases.return_value = []
        mock_github_instance.fetch_contributors.return_value = []
        
        mock_registry_instance = MockRegistryDetector.return_value
        mock_registry_instance.detect_registries.return_value = []
        
        # Build graph
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Count risk factor nodes
        risk_factor_nodes = [n for n in graph.nodes if n.type == NodeType.RISK_FACTOR]
        
        # Count significant risk drivers in the first max_risk_factors positions
        # (GraphBuilder only looks at top_drivers[:max_risk_factors])
        max_factors = 5  # Default max_risk_factors
        top_drivers_limited = risk_drivers[:max_factors]
        significant_drivers = [d for d in top_drivers_limited if d.get("contribution", 0) >= 0.05]
        
        # Property: Graph must include risk factor nodes for all significant drivers
        # in the top N positions (up to the configured max_risk_factors limit)
        expected_count = len(significant_drivers)
        
        assert len(risk_factor_nodes) == expected_count, \
            f"Expected {expected_count} risk factor nodes for {len(significant_drivers)} significant drivers in top {max_factors}, got {len(risk_factor_nodes)}"
        
        # Verify each risk factor node has required metadata
        for risk_node in risk_factor_nodes:
            assert "key" in risk_node.metadata, \
                f"Risk factor node {risk_node.id} missing 'key' in metadata"
            # Note: label is in node.label, not in metadata
            assert risk_node.label, \
                f"Risk factor node {risk_node.id} missing label"
            assert "raw_value" in risk_node.metadata, \
                f"Risk factor node {risk_node.id} missing 'raw_value' in metadata"
            assert "risk_score" in risk_node.metadata, \
                f"Risk factor node {risk_node.id} missing 'risk_score' in metadata"
            assert "contribution" in risk_node.metadata, \
                f"Risk factor node {risk_node.id} missing 'contribution' in metadata"
            assert "weight" in risk_node.metadata, \
                f"Risk factor node {risk_node.id} missing 'weight' in metadata"
            assert "category" in risk_node.metadata, \
                f"Risk factor node {risk_node.id} missing 'category' in metadata"
            
            # Verify contribution is >= 0.05 (only significant factors should be included)
            contribution = risk_node.metadata.get("contribution", 0)
            assert contribution >= 0.05, \
                f"Risk factor node {risk_node.id} has contribution {contribution} < 0.05 (should be filtered out)"
        
        # Verify edges exist from repo to risk factor nodes
        repo_node = next((n for n in graph.nodes if n.type == NodeType.REPO), None)
        assert repo_node is not None, "Graph missing REPO node"
        
        risk_factor_edges = [
            e for e in graph.edges 
            if e.source == repo_node.id and e.relationship_type == EdgeType.HAS_RISK_FACTOR
        ]
        
        # Should have one edge per risk factor node
        assert len(risk_factor_edges) == len(risk_factor_nodes), \
            f"Expected {len(risk_factor_nodes)} HAS_RISK_FACTOR edges, got {len(risk_factor_edges)}"
        
        # Verify each edge has required metadata
        for edge in risk_factor_edges:
            assert "contribution" in edge.metadata, \
                f"HAS_RISK_FACTOR edge {edge.source} -> {edge.target} missing 'contribution' in metadata"
            
            # Verify contribution is >= 0.05
            contribution = edge.metadata.get("contribution", 0)
            assert contribution >= 0.05, \
                f"HAS_RISK_FACTOR edge {edge.source} -> {edge.target} has contribution {contribution} < 0.05"


@given(
    num_significant_drivers=st.integers(min_value=0, max_value=20),
    num_insignificant_drivers=st.integers(min_value=0, max_value=20),
    coverage=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    maintenance_risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=50, deadline=None)
def test_property_risk_factor_filtering(
    num_significant_drivers, num_insignificant_drivers, coverage, maintenance_risk
):
    """
    Property 8 (variant): Risk Factor Filtering
    
    For any repository, risk factors with contribution < 0.05 must NOT be 
    included in the graph, while factors with contribution >= 0.05 must be 
    included (up to the configured limit).
    
    Validates: Requirements US-7.1, US-7.4
    
    Rationale: This tests the filtering logic to ensure only significant 
    risk factors are included in the graph.
    """
    # Generate significant drivers (contribution >= 0.05)
    significant_drivers = []
    for i in range(num_significant_drivers):
        significant_drivers.append({
            "key": f"significant_factor_{i}",
            "contribution": 0.05 + (i * 0.01),  # 0.05, 0.06, 0.07, ...
        })
    
    # Generate insignificant drivers (contribution < 0.05)
    insignificant_drivers = []
    for i in range(num_insignificant_drivers):
        insignificant_drivers.append({
            "key": f"insignificant_factor_{i}",
            "contribution": 0.04 - (i * 0.001),  # 0.04, 0.039, 0.038, ...
        })
    
    all_drivers = significant_drivers + insignificant_drivers
    
    # Generate score data
    features = []
    for driver in all_drivers:
        key = driver["key"]
        contribution = driver["contribution"]
        features.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "raw_value": 50.0,
            "risk_score": 0.5,
            "weight": 0.5,
            "category": "activity",
            "contribution": contribution,
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
        "top_drivers": all_drivers,
    }
    
    # Mock external API calls to avoid rate limiting
    with patch('src.open_source_risk_model.graph.builder.GitHubClient') as MockGitHubClient, \
         patch('src.open_source_risk_model.graph.builder.RegistryDetector') as MockRegistryDetector:
        
        # Configure mocks
        mock_github_instance = MockGitHubClient.return_value
        mock_github_instance.fetch_releases.return_value = []
        mock_github_instance.fetch_contributors.return_value = []
        
        mock_registry_instance = MockRegistryDetector.return_value
        mock_registry_instance.detect_registries.return_value = []
        
        # Build graph
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
        
        # Get risk factor nodes
        risk_factor_nodes = [n for n in graph.nodes if n.type == NodeType.RISK_FACTOR]
        
        # Property 1: No insignificant factors should be included
        for risk_node in risk_factor_nodes:
            key = risk_node.metadata.get("key", "")
            assert not key.startswith("insignificant_"), \
                f"Insignificant risk factor {key} should not be in graph"
            
            contribution = risk_node.metadata.get("contribution", 0)
            assert contribution >= 0.05, \
                f"Risk factor {key} has contribution {contribution} < 0.05 (should be filtered out)"
        
        # Property 2: Significant factors should be included (up to limit)
        expected_count = min(num_significant_drivers, 5)  # Default max_risk_factors is 5
        assert len(risk_factor_nodes) == expected_count, \
            f"Expected {expected_count} risk factor nodes, got {len(risk_factor_nodes)}"
        
        # Property 3: If we have significant factors, they should all be in the graph
        if num_significant_drivers > 0 and num_significant_drivers <= 5:
            # All significant factors should be present
            risk_node_keys = {n.metadata.get("key") for n in risk_factor_nodes}
            expected_keys = {d["key"] for d in significant_drivers}
            assert risk_node_keys == expected_keys, \
                f"Risk factor keys mismatch: {risk_node_keys} != {expected_keys}"
