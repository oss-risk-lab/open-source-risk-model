"""
Property-based tests for cross-repo query system.

Tests Properties 9-12:
- Property 9: Multi-Repo Query Completeness
- Property 10: Query Pagination Consistency
- Property 11: Filter Correctness
- Property 12: Index-Based Lookup Consistency
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
from hypothesis import given, settings, strategies as st, assume, HealthCheck

from src.open_source_risk_model.graph.schema import (
    Graph,
    Node,
    Edge,
    NodeType,
    EdgeType,
)
from src.open_source_risk_model.persistence.db import init_database
from src.open_source_risk_model.persistence.graph_repo import GraphRepository
from src.open_source_risk_model.persistence.index_repo import IndexRepository

# Test strategies for generating valid graph data

@st.composite
def provenance_strategy(draw):
    """Generate valid provenance metadata."""
    source = draw(st.sampled_from(["github_api", "osv", "heuristic", "registry"]))
    timestamp = datetime.now(timezone.utc).isoformat()
    confidence = draw(st.floats(min_value=0.0, max_value=1.0))
    
    return {
        "source": source,
        "fetched_at": timestamp,
        "data_confidence": confidence,
    }


@st.composite
def node_strategy(draw, node_type=None):
    """Generate a valid node."""
    if node_type is None:
        node_type = draw(st.sampled_from(list(NodeType)))
    
    # Generate appropriate metadata based on node type
    metadata = {}
    if node_type == NodeType.REPO:
        metadata = {
            "url": f"https://github.com/{draw(st.text(min_size=3, max_size=20))}/{draw(st.text(min_size=3, max_size=20))}",
            "maintenance_risk": draw(st.floats(min_value=0.0, max_value=1.0)),
            "maintenance_label": draw(st.sampled_from(["low", "medium", "high"])),
        }
    elif node_type == NodeType.MAINTAINER:
        metadata = {
            "username": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"))),
            "contribution_fraction": draw(st.floats(min_value=0.0, max_value=1.0)),
            "commit_count": draw(st.integers(min_value=1, max_value=10000)),
        }
    elif node_type == NodeType.CVE:
        cve_year = draw(st.integers(min_value=2000, max_value=2026))
        cve_num = draw(st.integers(min_value=1, max_value=99999))
        metadata = {
            "cve_id": f"CVE-{cve_year}-{cve_num}",
            "severity": draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
            "cvss_score": draw(st.floats(min_value=0.0, max_value=10.0)),
        }
    elif node_type == NodeType.REGISTRY:
        metadata = {
            "registry_type": draw(st.sampled_from(["pypi", "npm", "maven", "rubygems"])),
            "package_name": draw(st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-_"))),
            "latest_version": f"{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=50))}.{draw(st.integers(min_value=0, max_value=100))}",
        }
    elif node_type == NodeType.RELEASE:
        metadata = {
            "tag_name": f"v{draw(st.integers(min_value=0, max_value=10))}.{draw(st.integers(min_value=0, max_value=50))}.{draw(st.integers(min_value=0, max_value=100))}",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
    
    node_id_suffix = draw(st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_/:')))
    node_id = f"{node_type.value}:{node_id_suffix}"
    label = draw(st.text(min_size=3, max_size=50))
    
    return Node(
        id=node_id,
        type=node_type,
        label=label,
        metadata=metadata,
        provenance=draw(provenance_strategy())
    )


@st.composite
def edge_strategy(draw, node_ids):
    """Generate a valid edge between existing nodes."""
    if len(node_ids) < 2:
        # Need at least 2 nodes for an edge
        return None
    
    source = draw(st.sampled_from(node_ids))
    target = draw(st.sampled_from([nid for nid in node_ids if nid != source]))
    relationship_type = draw(st.sampled_from(list(EdgeType)))
    
    return Edge(
        source=source,
        target=target,
        relationship_type=relationship_type,
        metadata={},
        provenance=draw(provenance_strategy())
    )


@st.composite
def valid_graph_strategy(draw):
    """
    Generate a valid graph with at least one repo node.
    
    Ensures the graph passes validation by:
    - Having exactly one repo node
    - Having unique node IDs
    - Having edges that reference valid nodes
    - Having unique CVE IDs (to avoid index constraint violations)
    - Having unique maintainer usernames (to avoid index constraint violations)
    """
    # Always start with one repo node
    repo_node = draw(node_strategy(node_type=NodeType.REPO))
    nodes = [repo_node]
    
    # Track used CVE IDs and maintainer usernames to ensure uniqueness
    used_cve_ids = set()
    used_maintainer_usernames = set()
    
    # Add additional nodes (0-10 of various types)
    num_additional_nodes = draw(st.integers(min_value=0, max_value=10))
    for _ in range(num_additional_nodes):
        # Don't add more repo nodes
        node_type = draw(st.sampled_from([
            NodeType.RELEASE,
            NodeType.MAINTAINER,
            NodeType.CVE,
            NodeType.REGISTRY,
            NodeType.RISK_FACTOR,
        ]))
        
        node = draw(node_strategy(node_type=node_type))
        
        # For CVE nodes, ensure unique cve_id
        if node_type == NodeType.CVE:
            cve_id = node.metadata.get("cve_id")
            if cve_id in used_cve_ids:
                # Skip this node if CVE ID already used
                continue
            used_cve_ids.add(cve_id)
        
        # For maintainer nodes, ensure unique username
        if node_type == NodeType.MAINTAINER:
            username = node.metadata.get("username")
            if username in used_maintainer_usernames:
                # Skip this node if username already used
                continue
            used_maintainer_usernames.add(username)
        
        nodes.append(node)
    
    # Ensure unique node IDs
    seen_ids = set()
    unique_nodes = []
    for node in nodes:
        if node.id not in seen_ids:
            seen_ids.add(node.id)
            unique_nodes.append(node)
    
    node_ids = [n.id for n in unique_nodes]
    
    # Generate edges (0-15 edges)
    edges = []
    num_edges = draw(st.integers(min_value=0, max_value=min(15, len(node_ids) * 2)))
    for _ in range(num_edges):
        edge = draw(edge_strategy(node_ids))
        if edge:
            edges.append(edge)
    
    # Create graph with metadata
    metadata = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": draw(st.lists(
            st.sampled_from(["github_api", "osv", "heuristic"]),
            min_size=1,
            max_size=3,
            unique=True
        )),
        "warnings": draw(st.lists(st.text(min_size=5, max_size=50), max_size=3)),
    }
    
    return Graph(nodes=unique_nodes, edges=edges, metadata=metadata)


@st.composite
def repo_name_strategy(draw):
    """Generate valid repository names in owner/repo format."""
    owner = draw(st.text(
        min_size=3,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")
    ))
    repo = draw(st.text(
        min_size=3,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")
    ))
    return f"{owner}/{repo}"


# Additional strategies for query tests

@st.composite
def graph_with_maintainer_strategy(draw, username):
    """Generate a graph that includes a specific maintainer."""
    # Start with a valid graph
    graph = draw(valid_graph_strategy())
    
    # Add a maintainer node with the specified username
    maintainer_node = Node(
        id=f"maintainer:{username}",
        type=NodeType.MAINTAINER,
        label=username,
        metadata={
            "username": username,
            "contribution_fraction": draw(st.floats(min_value=0.1, max_value=1.0)),
            "commit_count": draw(st.integers(min_value=10, max_value=5000)),
        },
        provenance=draw(provenance_strategy())
    )
    
    # Replace any existing maintainer with same username or add new one
    graph.nodes = [n for n in graph.nodes if not (n.type == NodeType.MAINTAINER and n.metadata.get("username") == username)]
    graph.nodes.append(maintainer_node)
    
    return graph


@st.composite
def graph_with_cve_strategy(draw, cve_id):
    """Generate a graph that includes a specific CVE."""
    # Start with a valid graph
    graph = draw(valid_graph_strategy())
    
    # Add a CVE node with the specified ID
    cve_node = Node(
        id=f"cve:{cve_id}",
        type=NodeType.CVE,
        label=cve_id,
        metadata={
            "cve_id": cve_id,
            "severity": draw(st.sampled_from(["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
            "cvss_score": draw(st.floats(min_value=0.0, max_value=10.0)),
        },
        provenance=draw(provenance_strategy())
    )
    
    # Replace any existing CVE with same ID or add new one
    graph.nodes = [n for n in graph.nodes if not (n.type == NodeType.CVE and n.metadata.get("cve_id") == cve_id)]
    graph.nodes.append(cve_node)
    
    return graph


@st.composite
def graph_with_package_strategy(draw, registry_type, package_name):
    """Generate a graph that includes a specific package."""
    # Start with a valid graph
    graph = draw(valid_graph_strategy())
    
    # Add a registry node with the specified package
    registry_node = Node(
        id=f"registry:{registry_type}:{package_name}",
        type=NodeType.REGISTRY,
        label=f"{registry_type}:{package_name}",
        metadata={
            "registry_type": registry_type,
            "package_name": package_name,
            "latest_version": f"{draw(st.integers(min_value=1, max_value=5))}.{draw(st.integers(min_value=0, max_value=20))}.{draw(st.integers(min_value=0, max_value=50))}",
        },
        provenance=draw(provenance_strategy())
    )
    
    # Replace any existing registry with same package or add new one
    graph.nodes = [n for n in graph.nodes if not (
        n.type == NodeType.REGISTRY and 
        n.metadata.get("registry_type") == registry_type and 
        n.metadata.get("package_name") == package_name
    )]
    graph.nodes.append(registry_node)
    
    return graph


# Property Tests

@settings(max_examples=100, deadline=None)
@given(
    repo_names=st.lists(repo_name_strategy(), min_size=2, max_size=10, unique=True),
    graphs=st.data()
)
def test_property_9_multi_repo_query_completeness(repo_names, graphs):
    """
    Feature: multi-repo-persistent-graph, Property 9: Multi-Repo Query Completeness
    
    For any set of repository identifiers where some exist in the database and
    some don't, querying for all of them should return data for existing repos
    and indicate which repos are missing.
    
    Validates: Requirements 4.1, 4.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        graph_repo = GraphRepository(db_path)
        
        # Decide which repos to save (at least 1, but not all)
        num_to_save = graphs.draw(st.integers(min_value=1, max_value=len(repo_names) - 1))
        repos_to_save = repo_names[:num_to_save]
        repos_not_saved = repo_names[num_to_save:]
        
        # Save some repos
        for repo_name in repos_to_save:
            graph = graphs.draw(valid_graph_strategy())
            graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Query for all repos
        found_repos = []
        missing_repos = []
        
        for repo_name in repo_names:
            result = graph_repo.get_graph(repo_name)
            if result is not None:
                found_repos.append(repo_name)
            else:
                missing_repos.append(repo_name)
        
        # Verify completeness: all saved repos are found
        assert set(found_repos) == set(repos_to_save)
        
        # Verify missing repos are correctly identified
        assert set(missing_repos) == set(repos_not_saved)
        
        # Verify no false positives or false negatives
        assert len(found_repos) + len(missing_repos) == len(repo_names)


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
@given(
    num_repos=st.integers(min_value=5, max_value=20),
    page_size=st.integers(min_value=2, max_value=5),
    data=st.data()
)
def test_property_10_query_pagination_consistency(num_repos, page_size, data):
    """
    Feature: multi-repo-persistent-graph, Property 10: Query Pagination Consistency
    
    For any query result set, paginating through it with different limit/offset
    values should return all results exactly once without duplicates or omissions.
    
    Validates: Requirements 4.4
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        graph_repo = GraphRepository(db_path)
        
        # Generate and save repos
        repo_names = []
        for i in range(num_repos):
            repo_name = data.draw(repo_name_strategy())
            # Ensure unique repo names
            while repo_name in repo_names:
                repo_name = data.draw(repo_name_strategy())
            repo_names.append(repo_name)
            
            graph = data.draw(valid_graph_strategy())
            graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Paginate through all repos
        all_paginated_repos = []
        offset = 0
        
        while True:
            page = graph_repo.list_repos(limit=page_size, offset=offset)
            if not page:
                break
            
            all_paginated_repos.extend([r["repo_full_name"] for r in page])
            offset += page_size
            
            # Safety check to prevent infinite loops
            if offset > num_repos * 2:
                break
        
        # Verify all repos returned exactly once
        assert len(all_paginated_repos) == num_repos
        assert len(set(all_paginated_repos)) == num_repos  # No duplicates
        assert set(all_paginated_repos) == set(repo_names)  # All repos present


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
@given(
    username=st.text(min_size=3, max_size=15, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")),
    num_repos_with_maintainer=st.integers(min_value=1, max_value=5),
    num_repos_without_maintainer=st.integers(min_value=1, max_value=5),
    data=st.data()
)
def test_property_11_filter_correctness_maintainer(username, num_repos_with_maintainer, num_repos_without_maintainer, data):
    """
    Feature: multi-repo-persistent-graph, Property 11: Filter Correctness (Maintainer)
    
    For any query with filters by maintainer, all returned results should match
    the filter criteria and no matching results should be omitted.
    
    Validates: Requirements 4.2, 7.3, 10.1
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        graph_repo = GraphRepository(db_path)
        index_repo = IndexRepository(db_path)
        
        # Save repos with the maintainer
        repos_with_maintainer = []
        for i in range(num_repos_with_maintainer):
            repo_name = data.draw(repo_name_strategy())
            while repo_name in repos_with_maintainer:
                repo_name = data.draw(repo_name_strategy())
            repos_with_maintainer.append(repo_name)
            
            graph = data.draw(graph_with_maintainer_strategy(username))
            graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Save repos without the maintainer
        repos_without_maintainer = []
        for i in range(num_repos_without_maintainer):
            repo_name = data.draw(repo_name_strategy())
            while repo_name in repos_with_maintainer or repo_name in repos_without_maintainer:
                repo_name = data.draw(repo_name_strategy())
            repos_without_maintainer.append(repo_name)
            
            # Generate graph without the specific maintainer
            graph = data.draw(valid_graph_strategy())
            # Remove any nodes with the target username
            graph.nodes = [n for n in graph.nodes if not (
                n.type == NodeType.MAINTAINER and n.metadata.get("username") == username
            )]
            graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Query by maintainer
        results = index_repo.find_repos_by_maintainer(username)
        result_repo_names = [r["repo_full_name"] for r in results]
        
        # Verify all repos with maintainer are returned
        assert set(result_repo_names) == set(repos_with_maintainer)
        
        # Verify no repos without maintainer are returned
        for repo_name in repos_without_maintainer:
            assert repo_name not in result_repo_names


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
@given(
    cve_year=st.integers(min_value=2020, max_value=2026),
    cve_num=st.integers(min_value=1000, max_value=9999),
    num_repos_with_cve=st.integers(min_value=1, max_value=5),
    num_repos_without_cve=st.integers(min_value=1, max_value=5),
    data=st.data()
)
def test_property_11_filter_correctness_cve(cve_year, cve_num, num_repos_with_cve, num_repos_without_cve, data):
    """
    Feature: multi-repo-persistent-graph, Property 11: Filter Correctness (CVE)
    
    For any query with filters by CVE, all returned results should match
    the filter criteria and no matching results should be omitted.
    
    Validates: Requirements 4.2, 7.3, 10.2
    """
    # Generate valid CVE ID
    cve_id = f"CVE-{cve_year}-{cve_num}"
    
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        graph_repo = GraphRepository(db_path)
        index_repo = IndexRepository(db_path)
        
        # Save repos with the CVE
        repos_with_cve = []
        for i in range(num_repos_with_cve):
            repo_name = data.draw(repo_name_strategy())
            while repo_name in repos_with_cve:
                repo_name = data.draw(repo_name_strategy())
            repos_with_cve.append(repo_name)
            
            graph = data.draw(graph_with_cve_strategy(cve_id))
            graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Save repos without the CVE
        repos_without_cve = []
        for i in range(num_repos_without_cve):
            repo_name = data.draw(repo_name_strategy())
            while repo_name in repos_with_cve or repo_name in repos_without_cve:
                repo_name = data.draw(repo_name_strategy())
            repos_without_cve.append(repo_name)
            
            # Generate graph without the specific CVE
            graph = data.draw(valid_graph_strategy())
            # Remove any nodes with the target CVE ID
            graph.nodes = [n for n in graph.nodes if not (
                n.type == NodeType.CVE and n.metadata.get("cve_id") == cve_id
            )]
            graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Query by CVE
        results = index_repo.find_repos_by_cve(cve_id)
        result_repo_names = [r["repo_full_name"] for r in results]
        
        # Verify all repos with CVE are returned
        assert set(result_repo_names) == set(repos_with_cve)
        
        # Verify no repos without CVE are returned
        for repo_name in repos_without_cve:
            assert repo_name not in result_repo_names


@settings(max_examples=100, deadline=None)
@given(
    registry_type=st.sampled_from(["pypi", "npm", "maven", "rubygems"]),
    package_name=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-_")),
    data=st.data()
)
def test_property_12_index_based_lookup_consistency(registry_type, package_name, data):
    """
    Feature: multi-repo-persistent-graph, Property 12: Index-Based Lookup Consistency
    
    For any repository graph stored in the database, querying by indexed
    properties (maintainer username, CVE ID, or package name) should return
    that repository if and only if the graph contains nodes matching those properties.
    
    Validates: Requirements 5.5, 10.1, 10.2, 10.3
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_database(db_path)
        graph_repo = GraphRepository(db_path)
        index_repo = IndexRepository(db_path)
        
        # Generate repo with specific package
        repo_name = data.draw(repo_name_strategy())
        graph = data.draw(graph_with_package_strategy(registry_type, package_name))
        
        # Save graph
        graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
        
        # Query by package
        result = index_repo.find_repo_by_package(registry_type, package_name)
        
        # Verify repo is found
        assert result is not None
        assert result["repo_full_name"] == repo_name
        assert result["registry_type"] == registry_type
        assert result["package_name"] == package_name
        
        # Verify the graph actually contains the package node
        retrieved_graph_data = graph_repo.get_graph(repo_name)
        assert retrieved_graph_data is not None
        
        graph_nodes = retrieved_graph_data["graph"]["nodes"]
        registry_nodes = [
            n for n in graph_nodes
            if n["type"] == "registry" and
            n["metadata"].get("registry_type") == registry_type and
            n["metadata"].get("package_name") == package_name
        ]
        
        # Should have exactly one matching registry node
        assert len(registry_nodes) == 1
        
        # Query for non-existent package should return None
        fake_package = f"nonexistent-{package_name}-fake"
        result_fake = index_repo.find_repo_by_package(registry_type, fake_package)
        assert result_fake is None
