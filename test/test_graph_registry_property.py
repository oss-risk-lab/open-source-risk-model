"""
Property-based tests for registry node creation in graph builder.

Tests Property 6: Registry Node Creation
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, settings, assume

from src.open_source_risk_model.graph.schema import Node, Edge, Graph, NodeType, EdgeType, GraphConfig
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.registry_detector import RegistryDetector, RegistryInfo


# Hypothesis strategies for generating test data

@st.composite
def registry_info_strategy(draw, registry_type=None):
    """Strategy for generating valid RegistryInfo objects."""
    if registry_type is None:
        registry_type = draw(st.sampled_from(["pypi", "npm", "maven", "rubygems", "crates"]))
    
    # Generate package name based on registry type conventions
    if registry_type == "npm":
        # npm allows scoped packages like @scope/package
        has_scope = draw(st.booleans())
        if has_scope:
            scope = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'
            )))
            package = draw(st.text(min_size=1, max_size=30, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'
            )))
            package_name = f"@{scope}/{package}"
        else:
            package_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'
            )))
    elif registry_type == "pypi":
        # PyPI uses underscores and hyphens
        package_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'
        )))
    else:
        # Other registries
        package_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_.'
        )))
    
    # Determine detected_from based on registry type
    detected_from_map = {
        "pypi": draw(st.sampled_from(["setup.py", "pyproject.toml"])),
        "npm": "package.json",
        "maven": "pom.xml",
        "rubygems": draw(st.sampled_from(["Gemfile", "test.gemspec"])),
        "crates": "Cargo.toml",
    }
    detected_from = detected_from_map.get(registry_type, "unknown")
    
    # Match confidence varies by detection method
    if detected_from in ["package.json"]:
        match_confidence = 0.95
    elif detected_from in ["pyproject.toml", "pom.xml", "Cargo.toml", "test.gemspec"]:
        match_confidence = 0.9
    elif detected_from in ["setup.py"]:
        match_confidence = 0.7
    else:
        match_confidence = draw(st.floats(min_value=0.6, max_value=0.95, allow_nan=False))
    
    return RegistryInfo(
        registry_type=registry_type,
        package_name=package_name,
        detected_from=detected_from,
        match_confidence=match_confidence,
        latest_version=draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        download_count=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=1000000))),
    )


@st.composite
def registry_list_strategy(draw):
    """Strategy for generating a list of RegistryInfo objects."""
    num_registries = draw(st.integers(min_value=0, max_value=5))
    registries = []
    used_types = set()
    
    for _ in range(num_registries):
        # Ensure unique registry types (a repo can't be published to PyPI twice)
        available_types = ["pypi", "npm", "maven", "rubygems", "crates"]
        available_types = [t for t in available_types if t not in used_types]
        
        if not available_types:
            break
        
        registry_type = draw(st.sampled_from(available_types))
        used_types.add(registry_type)
        
        registry = draw(registry_info_strategy(registry_type=registry_type))
        registries.append(registry)
    
    return registries


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

# Feature: supply-chain-graph, Property 6: Registry Node Creation
@given(
    registries=registry_list_strategy(),
    score_data=score_data_strategy()
)
@settings(max_examples=100, deadline=None)
def test_property_registry_nodes_created_when_manifests_exist(registries, score_data):
    """
    Property 6: Registry Node Creation
    
    For any repository containing package manifest files (setup.py, package.json, 
    pom.xml, etc.), the generated graph must include a registry node for the 
    detected package ecosystem.
    
    **Validates: Requirements US-4.1, US-4.2**
    
    Rationale: Registry detection is key to understanding distribution channels. 
    The detection logic must reliably identify package ecosystems from manifest files.
    """
    # Skip if no registries (tested separately)
    assume(len(registries) > 0)
    
    # Mock registry detection to return our test registries
    with patch.object(RegistryDetector, 'detect_registries', return_value=registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    # Should have registry nodes for all detected registries
    assert len(registry_nodes) == len(registries), \
        f"Expected {len(registries)} registry nodes, got {len(registry_nodes)}"
    
    # Each registry node should have required metadata and provenance
    registry_ids_in_graph = set()
    for node in registry_nodes:
        assert node.id.startswith("registry:"), \
            f"Registry node ID should start with 'registry:', got {node.id}"
        
        registry_ids_in_graph.add(node.id)
        
        # Check required metadata fields
        assert "registry_type" in node.metadata, \
            f"Registry node {node.id} missing registry_type"
        assert "package_name" in node.metadata, \
            f"Registry node {node.id} missing package_name"
        assert "detected_from" in node.metadata, \
            f"Registry node {node.id} missing detected_from"
        
        # Validate registry_type is valid
        assert node.metadata["registry_type"] in ["pypi", "npm", "maven", "rubygems", "crates"], \
            f"Registry node {node.id} has invalid registry_type: {node.metadata['registry_type']}"
        
        # Validate package_name is non-empty
        assert node.metadata["package_name"], \
            f"Registry node {node.id} has empty package_name"
        
        # Validate detected_from is non-empty
        assert node.metadata["detected_from"], \
            f"Registry node {node.id} has empty detected_from"
        
        # Provenance should be complete
        assert node.provenance, f"Registry node {node.id} missing provenance"
        assert node.provenance.get("source") == "heuristic", \
            f"Registry node {node.id} should have source='heuristic' in provenance"
        assert node.provenance.get("data_confidence") == 0.8, \
            f"Registry node {node.id} should have data_confidence=0.8"
        assert "match_confidence" in node.provenance, \
            f"Registry node {node.id} missing match_confidence in provenance"
        assert 0.0 <= node.provenance.get("match_confidence", 0) <= 1.0, \
            f"Registry node {node.id} has invalid match_confidence"
        assert "fetched_at" in node.provenance, \
            f"Registry node {node.id} missing fetched_at in provenance"
    
    # Verify all registries from input are represented in graph
    expected_registry_ids = {
        f"registry:{r.registry_type}:{r.package_name}" for r in registries
    }
    assert registry_ids_in_graph == expected_registry_ids, \
        f"Registry IDs in graph {registry_ids_in_graph} don't match expected {expected_registry_ids}"
    
    # Should have PUBLISHED_AS edges for each registry
    published_as_edges = [e for e in graph.edges if e.relationship_type == EdgeType.PUBLISHED_AS]
    assert len(published_as_edges) == len(registries), \
        f"Expected {len(registries)} PUBLISHED_AS edges, got {len(published_as_edges)}"
    
    # All edges should point from repo to registry
    for edge in published_as_edges:
        assert edge.source == "repo:test/repo", \
            f"PUBLISHED_AS edge should start from repo node, got {edge.source}"
        assert edge.target.startswith("registry:"), \
            f"PUBLISHED_AS edge should point to registry node, got {edge.target}"
        
        # Edge should have required metadata
        assert "package_name" in edge.metadata, \
            f"PUBLISHED_AS edge missing package_name"
        
        # Edge provenance should be complete
        assert edge.provenance, f"PUBLISHED_AS edge missing provenance"
        assert edge.provenance.get("source") == "heuristic", \
            f"PUBLISHED_AS edge should have source='heuristic'"
        assert edge.provenance.get("confidence") == 0.8, \
            f"PUBLISHED_AS edge should have confidence=0.8"
        assert "match_confidence" in edge.provenance, \
            f"PUBLISHED_AS edge missing match_confidence in provenance"
        assert "established_at" in edge.provenance, \
            f"PUBLISHED_AS edge missing established_at in provenance"


@given(
    score_data=score_data_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_no_registry_nodes_when_no_manifests(score_data):
    """
    Property 6 (edge case): No registry nodes when no manifest files exist
    
    For any repository with no package manifest files, the generated graph 
    should not include registry nodes.
    
    **Validates: Requirements US-4.1, US-4.2**
    """
    # Mock registry detection to return empty list
    with patch.object(RegistryDetector, 'detect_registries', return_value=[]):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    # Should have no registry nodes
    assert len(registry_nodes) == 0, \
        f"Expected no registry nodes when no manifests exist, got {len(registry_nodes)}"
    
    # Should have no PUBLISHED_AS edges
    published_as_edges = [e for e in graph.edges if e.relationship_type == EdgeType.PUBLISHED_AS]
    assert len(published_as_edges) == 0, \
        f"Expected no PUBLISHED_AS edges when no manifests exist, got {len(published_as_edges)}"


@given(
    registries=registry_list_strategy(),
    score_data=score_data_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_registry_node_id_format(registries, score_data):
    """
    Property 6 (ID format): Registry node IDs follow correct format
    
    For any registry node, the ID must follow the format:
    registry:{registry_type}:{package_name}
    
    **Validates: Requirements US-4.1**
    """
    # Skip if no registries
    assume(len(registries) > 0)
    
    # Mock registry detection
    with patch.object(RegistryDetector, 'detect_registries', return_value=registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    for node in registry_nodes:
        # ID should have format: registry:{type}:{name}
        parts = node.id.split(":", 2)
        assert len(parts) == 3, \
            f"Registry node ID should have 3 parts separated by ':', got {node.id}"
        assert parts[0] == "registry", \
            f"Registry node ID should start with 'registry', got {parts[0]}"
        
        # Type and name should match metadata
        assert parts[1] == node.metadata["registry_type"], \
            f"Registry type in ID {parts[1]} doesn't match metadata {node.metadata['registry_type']}"
        assert parts[2] == node.metadata["package_name"], \
            f"Package name in ID {parts[2]} doesn't match metadata {node.metadata['package_name']}"


@given(
    registries=registry_list_strategy(),
    score_data=score_data_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_registry_node_label_format(registries, score_data):
    """
    Property 6 (label format): Registry node labels are human-readable
    
    For any registry node, the label should be in the format:
    {registry_type}: {package_name}
    
    **Validates: Requirements US-4.1**
    """
    # Skip if no registries
    assume(len(registries) > 0)
    
    # Mock registry detection
    with patch.object(RegistryDetector, 'detect_registries', return_value=registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    for node in registry_nodes:
        # Label should be human-readable
        expected_label = f"{node.metadata['registry_type']}: {node.metadata['package_name']}"
        assert node.label == expected_label, \
            f"Registry node label should be '{expected_label}', got '{node.label}'"


@given(
    registries=registry_list_strategy(),
    score_data=score_data_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_registry_match_confidence_range(registries, score_data):
    """
    Property 6 (confidence): Match confidence is in valid range
    
    For any registry node, the match_confidence in provenance should be 
    between 0.0 and 1.0, reflecting the confidence in package name extraction.
    
    **Validates: Requirements US-4.4**
    """
    # Skip if no registries
    assume(len(registries) > 0)
    
    # Mock registry detection
    with patch.object(RegistryDetector, 'detect_registries', return_value=registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    for node in registry_nodes:
        match_confidence = node.provenance.get("match_confidence")
        assert match_confidence is not None, \
            f"Registry node {node.id} missing match_confidence"
        assert 0.0 <= match_confidence <= 1.0, \
            f"Registry node {node.id} has match_confidence {match_confidence} outside valid range [0.0, 1.0]"


@given(
    registries=registry_list_strategy(),
    score_data=score_data_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_registry_node_uniqueness(registries, score_data):
    """
    Property 6 (uniqueness): Registry nodes are unique per registry type
    
    For any repository, there should be at most one registry node per 
    registry type (e.g., only one PyPI node, one npm node, etc.).
    
    **Validates: Requirements US-4.1**
    """
    # Skip if no registries
    assume(len(registries) > 0)
    
    # Mock registry detection
    with patch.object(RegistryDetector, 'detect_registries', return_value=registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    # Count registry types
    registry_types = [n.metadata["registry_type"] for n in registry_nodes]
    
    # Each registry type should appear at most once
    assert len(registry_types) == len(set(registry_types)), \
        f"Registry types should be unique, got duplicates: {registry_types}"


@given(
    registries=registry_list_strategy(),
    score_data=score_data_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_registry_edges_match_nodes(registries, score_data):
    """
    Property 6 (edge consistency): PUBLISHED_AS edges match registry nodes
    
    For any registry node in the graph, there should be exactly one 
    PUBLISHED_AS edge from the repo to that registry node.
    
    **Validates: Requirements US-4.3**
    """
    # Skip if no registries
    assume(len(registries) > 0)
    
    # Mock registry detection
    with patch.object(RegistryDetector, 'detect_registries', return_value=registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    registry_node_ids = {n.id for n in registry_nodes}
    
    # Find all PUBLISHED_AS edges
    published_as_edges = [e for e in graph.edges if e.relationship_type == EdgeType.PUBLISHED_AS]
    edge_targets = {e.target for e in published_as_edges}
    
    # Every registry node should have exactly one edge pointing to it
    assert registry_node_ids == edge_targets, \
        f"Registry node IDs {registry_node_ids} don't match edge targets {edge_targets}"
    
    # Every edge should point from the repo node
    for edge in published_as_edges:
        assert edge.source == "repo:test/repo", \
            f"PUBLISHED_AS edge should originate from repo node, got {edge.source}"


@given(
    registries=registry_list_strategy(),
    score_data=score_data_strategy()
)
@settings(max_examples=50, deadline=None)
def test_property_registry_metadata_completeness(registries, score_data):
    """
    Property 6 (metadata): Registry nodes have complete metadata
    
    For any registry node, all required metadata fields must be present:
    - registry_type
    - package_name
    - detected_from
    
    Optional fields (latest_version, download_count) may be None.
    
    **Validates: Requirements US-4.4**
    """
    # Skip if no registries
    assume(len(registries) > 0)
    
    # Mock registry detection
    with patch.object(RegistryDetector, 'detect_registries', return_value=registries):
        builder = GraphBuilder("test/repo", score_data)
        graph = builder.build()
    
    # Find all registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    required_fields = ["registry_type", "package_name", "detected_from"]
    optional_fields = ["latest_version", "download_count"]
    
    for node in registry_nodes:
        # Check required fields are present and non-empty
        for field in required_fields:
            assert field in node.metadata, \
                f"Registry node {node.id} missing required field {field}"
            assert node.metadata[field], \
                f"Registry node {node.id} has empty required field {field}"
        
        # Check optional fields are present (but may be None)
        for field in optional_fields:
            assert field in node.metadata, \
                f"Registry node {node.id} missing optional field {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
