"""Tests for TransitiveResolver — the core resolution algorithm."""
import tempfile
import os
from unittest.mock import patch, MagicMock, call

import pytest

from open_source_risk_model.resolution.resolver import TransitiveResolver
from open_source_risk_model.resolution.models import (
    NormalizedPackageMetadata,
    DependencyDeclaration,
    ResolutionEdge,
    ResolutionSummary,
    RESOLUTION_STATUSES,
)
from open_source_risk_model.resolution.budget_tracker import BudgetConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata(name, version="1.0.0", ecosystem="pypi", deps=None):
    """Create a NormalizedPackageMetadata with optional sub-dependencies."""
    return NormalizedPackageMetadata(
        name=name,
        version=version,
        ecosystem=ecosystem,
        dependencies=[
            DependencyDeclaration(name=d[0], specifier=d[1] if len(d) > 1 else None)
            for d in (deps or [])
        ],
        source_url=f"https://example.com/{name}",
        fetched_at="2024-01-01T00:00:00+00:00",
    )


def _make_resolver(db_path, max_depth=5, budget_config=None, ecosystem_filter=None):
    """Create a TransitiveResolver with mocked cache to avoid DB table creation."""
    with patch(
        "open_source_risk_model.resolution.resolver.ResolutionCache"
    ) as MockCache:
        mock_cache = MagicMock()
        mock_cache.lookup.return_value = (None, False)
        MockCache.return_value = mock_cache
        resolver = TransitiveResolver(
            db_path=db_path,
            max_depth=max_depth,
            budget_config=budget_config or BudgetConfig(min_delay_ms=0),
            ecosystem_filter=ecosystem_filter,
        )
    return resolver


def _setup_mock_registry(mock_get_client, metadata_map):
    """Configure mock registry client to return metadata from a map.

    metadata_map: dict mapping package_name -> NormalizedPackageMetadata or None
    """
    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"

    def get_metadata(name, specifier=None):
        return metadata_map.get(name)

    mock_client.get_package_metadata.side_effect = get_metadata
    mock_get_client.return_value = mock_client
    return mock_client


# ---------------------------------------------------------------------------
# Test: Direct deps at depth 1
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_resolves_direct_deps_at_depth_1(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "requests", "ecosystem": "pypi", "version_spec": ">=2.0"},
    ])

    metadata_map = {
        "requests": _make_metadata("requests", "2.31.0"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    assert len(edges) == 1
    edge = edges[0]
    assert edge.depth == 1
    assert edge.parent_ecosystem is None
    assert edge.parent_package == "owner/repo"
    assert edge.child_package == "requests"
    assert edge.child_ecosystem == "pypi"
    assert edge.declared_specifier == ">=2.0"
    assert edge.resolved_version == "2.31.0"
    assert edge.resolution_status == "resolved"


# ---------------------------------------------------------------------------
# Test: Transitive deps at depth 2+ with correct parent identity
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_resolves_transitive_deps_with_correct_parent(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "requests", "ecosystem": "pypi", "version_spec": None},
    ])

    metadata_map = {
        "requests": _make_metadata("requests", "2.31.0", deps=[("urllib3", ">=1.21")]),
        "urllib3": _make_metadata("urllib3", "2.0.0"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    assert len(edges) == 2
    # Direct dep
    assert edges[0].parent_ecosystem is None
    assert edges[0].parent_package == "owner/repo"
    assert edges[0].child_package == "requests"
    assert edges[0].depth == 1
    # Transitive dep
    assert edges[1].parent_ecosystem == "pypi"
    assert edges[1].parent_package == "requests"
    assert edges[1].child_package == "urllib3"
    assert edges[1].depth == 2
    assert edges[1].declared_specifier == ">=1.21"


# ---------------------------------------------------------------------------
# Test: Cycle detection A→B→A
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_cycle_detection(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "A", "ecosystem": "pypi"},
    ])

    metadata_map = {
        "A": _make_metadata("A", deps=[("B",)]),
        "B": _make_metadata("B", deps=[("A",)]),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    assert len(edges) == 3  # A(resolved), B(resolved), A(cycle)
    cycle_edges = [e for e in edges if e.resolution_status == "cycle_detected"]
    assert len(cycle_edges) == 1
    assert cycle_edges[0].child_package == "A"
    assert cycle_edges[0].depth == 3
    assert summary.cycle_count == 1


# ---------------------------------------------------------------------------
# Test: Cycle detection is branch-local
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_cycle_detection_is_branch_local(mock_get_client):
    """Same package in different branches is resolved independently."""
    resolver = _make_resolver("/tmp/test.db")
    # Two direct deps: X and Y, both depend on shared_pkg
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "X", "ecosystem": "pypi"},
        {"package_name": "Y", "ecosystem": "pypi"},
    ])

    metadata_map = {
        "X": _make_metadata("X", deps=[("shared_pkg",)]),
        "Y": _make_metadata("Y", deps=[("shared_pkg",)]),
        "shared_pkg": _make_metadata("shared_pkg"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    # shared_pkg should appear resolved in BOTH branches
    shared_edges = [e for e in edges if e.child_package == "shared_pkg"]
    assert len(shared_edges) == 2
    assert all(e.resolution_status == "resolved" for e in shared_edges)
    # One under X, one under Y
    parents = {e.parent_package for e in shared_edges}
    assert parents == {"X", "Y"}


# ---------------------------------------------------------------------------
# Test: Max depth
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_max_depth_stops_recursion(mock_get_client):
    resolver = _make_resolver("/tmp/test.db", max_depth=2)
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "A", "ecosystem": "pypi"},
    ])

    # A→B→C (C would be depth 3, exceeding max_depth=2)
    metadata_map = {
        "A": _make_metadata("A", deps=[("B",)]),
        "B": _make_metadata("B", deps=[("C",)]),
        "C": _make_metadata("C"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    assert len(edges) == 3  # A(resolved), B(resolved), C(max_depth)
    max_depth_edges = [e for e in edges if e.resolution_status == "max_depth_reached"]
    assert len(max_depth_edges) == 1
    assert max_depth_edges[0].child_package == "C"
    assert max_depth_edges[0].depth == 3
    assert summary.max_depth_reached_count == 1


# ---------------------------------------------------------------------------
# Test: Unsupported ecosystem
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_unsupported_ecosystem(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "some-gem", "ecosystem": "rubygems"},
    ])

    mock_get_client.return_value = None  # unsupported

    edges, summary = resolver.resolve_repo("owner/repo")

    assert len(edges) == 1
    assert edges[0].resolution_status == "unsupported_ecosystem"
    assert edges[0].child_package == "some-gem"
    assert edges[0].source_registry is None
    assert summary.unsupported_ecosystem_count == 1


# ---------------------------------------------------------------------------
# Test: Budget exhaustion
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_budget_exhaustion(mock_get_client):
    resolver = _make_resolver(
        "/tmp/test.db",
        budget_config=BudgetConfig(global_budget=1, min_delay_ms=0),
    )
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "A", "ecosystem": "pypi"},
        {"package_name": "B", "ecosystem": "pypi"},
    ])

    metadata_map = {
        "A": _make_metadata("A"),
        "B": _make_metadata("B"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    statuses = [e.resolution_status for e in edges]
    assert "resolved" in statuses
    assert "budget_exhausted" in statuses
    assert summary.budget_exhausted_count == 1


# ---------------------------------------------------------------------------
# Test: Cache hit skips budget check and API call
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_cache_hit_skips_budget_and_api(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "cached_pkg", "ecosystem": "pypi"},
    ])

    cached_meta = _make_metadata("cached_pkg", "3.0.0")
    resolver.cache.lookup.return_value = (cached_meta, True)

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")

    assert len(edges) == 1
    assert edges[0].resolution_status == "resolved"
    assert edges[0].resolved_version == "3.0.0"
    # API should NOT have been called
    mock_client.get_package_metadata.assert_not_called()
    # Cache hits counter
    assert resolver._cache_hits == 1
    assert summary.cache_hits == 1


# ---------------------------------------------------------------------------
# Test: Failed API call (None return) records error edge
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_failed_api_records_error_edge(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "missing_pkg", "ecosystem": "pypi"},
    ])

    metadata_map = {"missing_pkg": None}
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    assert len(edges) == 1
    assert edges[0].resolution_status == "error"
    assert edges[0].error_reason == "Package not found in registry"
    assert edges[0].source_registry == "pypi"
    assert edges[0].resolved_version is None
    assert summary.error_count == 1


# ---------------------------------------------------------------------------
# Test: Authoritative flow order
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_authoritative_flow_order(mock_get_client):
    """cache lookup → budget check → delay → fetch → record → store"""
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "pkg", "ecosystem": "pypi"},
    ])

    # Cache miss
    resolver.cache.lookup.return_value = (None, False)

    meta = _make_metadata("pkg")
    mock_client = MagicMock()
    mock_client.get_package_metadata.return_value = meta
    mock_get_client.return_value = mock_client

    # Spy on budget methods
    resolver.budget = MagicMock()
    resolver.budget.can_make_call.return_value = True
    resolver.budget.api_calls_made = 0

    edges, _ = resolver.resolve_repo("owner/repo")

    # Verify call order
    resolver.cache.lookup.assert_called_once_with("pypi", "pkg")
    resolver.budget.can_make_call.assert_called_once_with("pypi")
    resolver.budget.wait_if_needed.assert_called_once_with("pypi")
    mock_client.get_package_metadata.assert_called_once()
    resolver.budget.record_call.assert_called_once_with("pypi")
    resolver.cache.store.assert_called_once_with("pypi", "pkg", meta)


# ---------------------------------------------------------------------------
# Test: Deterministic output — sorted direct deps, sorted sub-deps
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_deterministic_output(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    # Direct deps in non-alphabetical order
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "zebra", "ecosystem": "pypi"},
        {"package_name": "alpha", "ecosystem": "pypi"},
    ])

    metadata_map = {
        "alpha": _make_metadata("alpha", deps=[("charlie",), ("bravo",)]),
        "zebra": _make_metadata("zebra"),
        "bravo": _make_metadata("bravo"),
        "charlie": _make_metadata("charlie"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, _ = resolver.resolve_repo("owner/repo")

    # Direct deps should be sorted: alpha before zebra
    direct_edges = [e for e in edges if e.depth == 1]
    assert [e.child_package for e in direct_edges] == ["alpha", "zebra"]

    # Sub-deps of alpha should be sorted: bravo before charlie
    alpha_children = [e for e in edges if e.parent_package == "alpha"]
    assert [e.child_package for e in alpha_children] == ["bravo", "charlie"]


# ---------------------------------------------------------------------------
# Test: ResolutionSummary has correct counts
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_summary_correct_counts(mock_get_client):
    resolver = _make_resolver("/tmp/test.db", max_depth=1)
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "A", "ecosystem": "pypi"},
    ])

    # A resolves, but its child B hits max_depth
    metadata_map = {
        "A": _make_metadata("A", deps=[("B",)]),
        "B": _make_metadata("B"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    assert summary.total_edges == 2
    assert summary.resolved_count == 1
    assert summary.max_depth_reached_count == 1
    assert summary.repo_full_name == "owner/repo"


# ---------------------------------------------------------------------------
# Test: source_registry semantics
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_source_registry_semantics(mock_get_client):
    resolver = _make_resolver("/tmp/test.db", max_depth=1)
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "good", "ecosystem": "pypi"},
        {"package_name": "bad", "ecosystem": "pypi"},
        {"package_name": "gem", "ecosystem": "rubygems"},
    ])

    def get_client(eco):
        if eco == "pypi":
            client = MagicMock()
            client.ecosystem = "pypi"
            def get_meta(name, specifier=None):
                if name == "good":
                    return _make_metadata("good", deps=[("child",)])
                return None
            client.get_package_metadata.side_effect = get_meta
            return client
        return None

    mock_get_client.side_effect = get_client

    edges, _ = resolver.resolve_repo("owner/repo")

    edge_map = {e.child_package: e for e in edges}
    # Resolved edge: source_registry = ecosystem name
    assert edge_map["good"].source_registry == "pypi"
    # Error edge: source_registry = ecosystem name
    assert edge_map["bad"].source_registry == "pypi"
    # Unsupported: source_registry = None
    assert edge_map["gem"].source_registry is None
    # max_depth_reached child: source_registry = None
    assert edge_map["child"].source_registry is None


# ---------------------------------------------------------------------------
# Test: resolved_at is set on all edges
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_resolved_at_set_on_all_edges(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "pkg", "ecosystem": "pypi"},
    ])

    metadata_map = {"pkg": _make_metadata("pkg")}
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, _ = resolver.resolve_repo("owner/repo")

    for edge in edges:
        assert edge.resolved_at != ""
        assert "T" in edge.resolved_at  # ISO 8601 format


# ---------------------------------------------------------------------------
# Test: declared_specifier flows through from parent metadata
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_declared_specifier_flows_through(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "parent", "ecosystem": "pypi", "version_spec": ">=1.0"},
    ])

    metadata_map = {
        "parent": _make_metadata("parent", deps=[("child", "^2.0")]),
        "child": _make_metadata("child"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, _ = resolver.resolve_repo("owner/repo")

    parent_edge = [e for e in edges if e.child_package == "parent"][0]
    child_edge = [e for e in edges if e.child_package == "child"][0]
    assert parent_edge.declared_specifier == ">=1.0"
    assert child_edge.declared_specifier == "^2.0"


# ---------------------------------------------------------------------------
# Test: resolved_version set for resolved, None for non-resolved
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_resolved_version_semantics(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "good", "ecosystem": "pypi"},
        {"package_name": "bad", "ecosystem": "pypi"},
    ])

    metadata_map = {
        "good": _make_metadata("good", "5.0.0"),
        "bad": None,
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, _ = resolver.resolve_repo("owner/repo")

    good_edge = [e for e in edges if e.child_package == "good"][0]
    bad_edge = [e for e in edges if e.child_package == "bad"][0]
    assert good_edge.resolved_version == "5.0.0"
    assert bad_edge.resolved_version is None


# ---------------------------------------------------------------------------
# Test: Empty direct deps returns empty edges
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_empty_direct_deps(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[])

    edges, summary = resolver.resolve_repo("owner/repo")

    assert edges == []
    assert summary.total_edges == 0


# ---------------------------------------------------------------------------
# Test: Ecosystem filter excludes non-matching ecosystems
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_ecosystem_filter(mock_get_client):
    resolver = _make_resolver("/tmp/test.db", ecosystem_filter={"pypi"})
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "py_pkg", "ecosystem": "pypi"},
        {"package_name": "js_pkg", "ecosystem": "npm"},
    ])

    metadata_map = {
        "py_pkg": _make_metadata("py_pkg"),
        "js_pkg": _make_metadata("js_pkg", ecosystem="npm"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    # Only pypi package should be resolved
    assert len(edges) == 1
    assert edges[0].child_package == "py_pkg"


# ---------------------------------------------------------------------------
# Test: Sub-dependencies inherit parent's ecosystem
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_sub_deps_inherit_ecosystem(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "parent", "ecosystem": "npm"},
    ])

    mock_client = MagicMock()
    mock_client.ecosystem = "npm"

    def get_meta(name, specifier=None):
        if name == "parent":
            return _make_metadata("parent", ecosystem="npm", deps=[("child",)])
        if name == "child":
            return _make_metadata("child", ecosystem="npm")
        return None

    mock_client.get_package_metadata.side_effect = get_meta
    mock_get_client.return_value = mock_client

    edges, _ = resolver.resolve_repo("owner/repo")

    child_edge = [e for e in edges if e.child_package == "child"][0]
    assert child_edge.child_ecosystem == "npm"
    assert child_edge.parent_ecosystem == "npm"


# ---------------------------------------------------------------------------
# Test: edges_per_depth in summary
# ---------------------------------------------------------------------------

@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_summary_edges_per_depth(mock_get_client):
    resolver = _make_resolver("/tmp/test.db")
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": "A", "ecosystem": "pypi"},
        {"package_name": "B", "ecosystem": "pypi"},
    ])

    metadata_map = {
        "A": _make_metadata("A", deps=[("C",)]),
        "B": _make_metadata("B"),
        "C": _make_metadata("C"),
    }
    _setup_mock_registry(mock_get_client, metadata_map)

    edges, summary = resolver.resolve_repo("owner/repo")

    # 2 edges at depth 1 (A, B), 1 edge at depth 2 (C)
    assert summary.edges_per_depth == {1: 2, 2: 1}
    assert sum(summary.edges_per_depth.values()) == summary.total_edges
