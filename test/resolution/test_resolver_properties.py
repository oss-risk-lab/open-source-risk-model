"""Property-based tests for the transitive dependency resolution system.

Uses Hypothesis to verify invariants across randomly generated inputs.
"""
import tempfile
import os
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from open_source_risk_model.resolution.resolver import TransitiveResolver
from open_source_risk_model.resolution.models import (
    NormalizedPackageMetadata,
    DependencyDeclaration,
    ResolutionEdge,
    ResolutionSummary,
    RESOLUTION_STATUSES,
    make_node_key,
)
from open_source_risk_model.resolution.budget_tracker import BudgetConfig, BudgetTracker
from open_source_risk_model.resolution.cache import ResolutionCache


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

pkg_name_st = st.from_regex(r"[a-z][a-z0-9_-]{0,20}", fullmatch=True)
version_st = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True)
ecosystem_st = st.sampled_from(["pypi", "npm"])
specifier_st = st.one_of(st.none(), st.from_regex(r">=[0-9]\.[0-9]", fullmatch=True))
depth_st = st.integers(min_value=1, max_value=10)


def _dep_list_st():
    """Strategy for a list of unique dependency declarations (sub-deps)."""
    return st.lists(
        pkg_name_st,
        min_size=0,
        max_size=3,
        unique=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata(name, version="1.0.0", ecosystem="pypi", deps=None):
    """Create NormalizedPackageMetadata with optional sub-dependencies."""
    return NormalizedPackageMetadata(
        name=name,
        version=version,
        ecosystem=ecosystem,
        dependencies=[
            DependencyDeclaration(name=d, specifier=None)
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


def _setup_resolver_with_deps(direct_dep_names, metadata_map, max_depth=5,
                               budget_config=None, ecosystem="pypi"):
    """Set up a fully mocked resolver with given direct deps and metadata map.

    Returns (resolver, mock_client) ready for resolve_repo().
    """
    db_path = "/tmp/fake.db"
    resolver = _make_resolver(
        db_path, max_depth=max_depth,
        budget_config=budget_config or BudgetConfig(min_delay_ms=0),
    )

    # Mock _get_direct_deps
    resolver._get_direct_deps = MagicMock(return_value=[
        {"package_name": name, "ecosystem": ecosystem, "version_spec": None}
        for name in sorted(direct_dep_names)
    ])

    # Mock registry client
    mock_client = MagicMock()
    mock_client.ecosystem = ecosystem

    def get_metadata(name, specifier=None):
        return metadata_map.get(name)

    mock_client.get_package_metadata.side_effect = get_metadata

    return resolver, mock_client


# ---------------------------------------------------------------------------
# Property 1: Determinism — resolve_repo() twice → identical edge lists
# Validates: Requirements 14.1
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=5, unique=True),
    version=version_st,
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_determinism_property(mock_get_client, dep_names, version):
    """Running resolve_repo() twice with same mocked deps/registry produces
    identical edge lists.

    **Validates: Requirements 14.1**
    """
    metadata_map = {
        name: _make_metadata(name, version=version, ecosystem="pypi")
        for name in dep_names
    }
    resolver1, _ = _setup_resolver_with_deps(dep_names, metadata_map)
    resolver2, _ = _setup_resolver_with_deps(dep_names, metadata_map)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges1, summary1 = resolver1.resolve_repo("owner/repo")
    edges2, summary2 = resolver2.resolve_repo("owner/repo")

    assert len(edges1) == len(edges2)
    for e1, e2 in zip(edges1, edges2):
        assert e1.child_package == e2.child_package
        assert e1.depth == e2.depth
        assert e1.resolution_status == e2.resolution_status
        assert e1.resolved_version == e2.resolved_version
        assert e1.parent_package == e2.parent_package


# ---------------------------------------------------------------------------
# Property 2: Edge count — total edges >= number of direct deps
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=5, unique=True),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_edge_count_property(mock_get_client, dep_names):
    """Total edges >= number of direct deps (every direct dep produces at
    least one edge).

    **Validates: Requirements 4.1**
    """
    metadata_map = {
        name: _make_metadata(name, ecosystem="pypi")
        for name in dep_names
    }
    resolver, _ = _setup_resolver_with_deps(dep_names, metadata_map)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")
    assert len(edges) >= len(dep_names)


# ---------------------------------------------------------------------------
# Property 3: Depth bounds — no edge has depth > max_depth
# Validates: Requirements 4.3
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=4, unique=True),
    max_depth=st.integers(min_value=1, max_value=5),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_depth_bounds_property(mock_get_client, dep_names, max_depth):
    """No edge has depth > max_depth; depth == max_depth+1 is impossible.

    **Validates: Requirements 4.3**
    """
    # Create a chain: each package depends on the next to force deep recursion
    chain_names = [f"chain-{i}" for i in range(max_depth + 3)]
    all_names = list(set(dep_names + chain_names))

    metadata_map = {}
    for i, name in enumerate(chain_names):
        next_dep = [chain_names[i + 1]] if i + 1 < len(chain_names) else []
        metadata_map[name] = _make_metadata(name, ecosystem="pypi", deps=next_dep)
    for name in dep_names:
        if name not in metadata_map:
            metadata_map[name] = _make_metadata(name, ecosystem="pypi",
                                                 deps=[chain_names[0]] if chain_names else [])

    resolver, _ = _setup_resolver_with_deps(dep_names, metadata_map, max_depth=max_depth)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")

    for edge in edges:
        assert edge.depth <= max_depth + 1, (
            f"Edge depth {edge.depth} exceeds max_depth+1={max_depth + 1}"
        )
    # No edge should have depth > max_depth except max_depth_reached at max_depth+1
    # Actually, the resolver checks `depth > self.max_depth` so edges at max_depth+1
    # get status max_depth_reached. But depth > max_depth+1 is impossible.
    for edge in edges:
        if edge.depth > max_depth:
            assert edge.resolution_status == "max_depth_reached"


# ---------------------------------------------------------------------------
# Property 4: Status completeness — every edge has valid status
# Validates: Requirements 5.3, 5.4
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=5, unique=True),
    include_none=st.booleans(),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_status_completeness_property(mock_get_client, dep_names, include_none):
    """Every edge has a resolution_status in RESOLUTION_STATUSES.

    **Validates: Requirements 5.3, 5.4**
    """
    metadata_map = {}
    for i, name in enumerate(dep_names):
        if include_none and i == 0:
            metadata_map[name] = None  # will produce error edge
        else:
            metadata_map[name] = _make_metadata(name, ecosystem="pypi")

    resolver, _ = _setup_resolver_with_deps(dep_names, metadata_map)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")

    for edge in edges:
        assert edge.resolution_status in RESOLUTION_STATUSES, (
            f"Invalid status: {edge.resolution_status}"
        )


# ---------------------------------------------------------------------------
# Property 5: Branch-local cycle — cycle on one branch doesn't block another
# Validates: Requirements 4.5, 4.6
# ---------------------------------------------------------------------------

@given(
    shared_pkg=pkg_name_st,
    branch_a_root=pkg_name_st,
    branch_b_root=pkg_name_st,
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_branch_local_cycle_property(mock_get_client, shared_pkg, branch_a_root, branch_b_root):
    """If a cycle exists on one branch, the same package can still be resolved
    on a different branch.

    **Validates: Requirements 4.5, 4.6**
    """
    assume(shared_pkg != branch_a_root)
    assume(shared_pkg != branch_b_root)
    assume(branch_a_root != branch_b_root)

    # branch_a_root -> shared_pkg -> branch_a_root (cycle)
    # branch_b_root -> shared_pkg (no cycle)
    metadata_map = {
        branch_a_root: _make_metadata(branch_a_root, ecosystem="pypi", deps=[shared_pkg]),
        branch_b_root: _make_metadata(branch_b_root, ecosystem="pypi", deps=[shared_pkg]),
        shared_pkg: _make_metadata(shared_pkg, ecosystem="pypi", deps=[branch_a_root]),
    }

    direct_deps = [branch_a_root, branch_b_root]
    resolver, _ = _setup_resolver_with_deps(direct_deps, metadata_map)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")

    # shared_pkg should appear as resolved in both branches
    shared_resolved = [
        e for e in edges
        if e.child_package == shared_pkg and e.resolution_status == "resolved"
    ]
    assert len(shared_resolved) >= 2, (
        f"Expected shared_pkg '{shared_pkg}' resolved in both branches, "
        f"got {len(shared_resolved)} resolved edges"
    )

    # branch_a_root should have a cycle_detected edge (when shared_pkg tries to recurse back)
    cycle_edges = [
        e for e in edges
        if e.child_package == branch_a_root and e.resolution_status == "cycle_detected"
    ]
    assert len(cycle_edges) >= 1, "Expected cycle_detected for branch_a_root"


# ---------------------------------------------------------------------------
# Property 6: Summary consistency — counts match
# Validates: Requirements 11.5
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=5, unique=True),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_summary_consistency_property(mock_get_client, dep_names):
    """summary.total_edges == len(edges) and status counts sum to total_edges.

    **Validates: Requirements 11.5**
    """
    metadata_map = {
        name: _make_metadata(name, ecosystem="pypi")
        for name in dep_names
    }
    resolver, _ = _setup_resolver_with_deps(dep_names, metadata_map)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")

    assert summary.total_edges == len(edges)

    status_sum = (
        summary.resolved_count
        + summary.error_count
        + summary.cycle_count
        + summary.max_depth_reached_count
        + summary.unsupported_ecosystem_count
        + summary.budget_exhausted_count
    )
    assert status_sum == summary.total_edges, (
        f"Status counts sum {status_sum} != total_edges {summary.total_edges}"
    )


# ---------------------------------------------------------------------------
# Property 7: Provenance — resolved_at, source_registry, depth
# Validates: Requirements 8.1-8.3
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=5, unique=True),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_provenance_property(mock_get_client, dep_names):
    """Every edge has non-empty resolved_at; resolved edges have source_registry
    set; depth >= 1.

    **Validates: Requirements 8.1, 8.2, 8.3**
    """
    metadata_map = {
        name: _make_metadata(name, ecosystem="pypi")
        for name in dep_names
    }
    resolver, _ = _setup_resolver_with_deps(dep_names, metadata_map)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")

    for edge in edges:
        # Every edge has non-empty resolved_at
        assert edge.resolved_at, f"Edge {edge.child_package} has empty resolved_at"
        # Depth >= 1 (root is depth 0 but not stored as edge)
        assert edge.depth >= 1, f"Edge {edge.child_package} has depth {edge.depth} < 1"
        # Resolved edges have source_registry set
        if edge.resolution_status == "resolved":
            assert edge.source_registry is not None, (
                f"Resolved edge {edge.child_package} has no source_registry"
            )


# ---------------------------------------------------------------------------
# Property 8: Cache idempotency — store then lookup returns equivalent result
# Validates: Requirements 6.8
# ---------------------------------------------------------------------------

@given(
    name=pkg_name_st,
    version=version_st,
    eco=ecosystem_st,
    sub_deps=_dep_list_st(),
)
@settings(database=None, max_examples=50)
def test_cache_idempotency_property(name, version, eco, sub_deps):
    """Storing then looking up metadata returns equivalent result.

    **Validates: Requirements 6.8**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "cache_test.db")
        cache = ResolutionCache(db_path)

        original = NormalizedPackageMetadata(
            name=name,
            version=version,
            ecosystem=eco,
            dependencies=[DependencyDeclaration(name=d) for d in sub_deps],
            source_url=f"https://example.com/{name}",
            fetched_at="2024-01-01T00:00:00+00:00",
        )

        cache.store(eco, name, original)
        result, found = cache.lookup(eco, name)

        assert found is True
        assert result is not None
        assert result.name == original.name
        assert result.version == original.version
        assert result.ecosystem == original.ecosystem
        assert len(result.dependencies) == len(original.dependencies)
        for r_dep, o_dep in zip(result.dependencies, original.dependencies):
            assert r_dep.name == o_dep.name
            assert r_dep.specifier == o_dep.specifier
        assert result.source_url == original.source_url
        assert result.fetched_at == original.fetched_at


# ---------------------------------------------------------------------------
# Property 9: Budget monotonicity — api_calls_made never decreases
# Validates: Requirements 9.2
# ---------------------------------------------------------------------------

@given(
    call_counts=st.lists(
        st.tuples(ecosystem_st, st.integers(min_value=1, max_value=10)),
        min_size=1,
        max_size=10,
    ),
)
@settings(database=None, max_examples=50)
def test_budget_monotonicity_property(call_counts):
    """budget.api_calls_made never decreases; after N record_call() invocations,
    api_calls_made == N.

    **Validates: Requirements 9.2**
    """
    tracker = BudgetTracker(BudgetConfig(global_budget=10000, min_delay_ms=0))

    total_calls = 0
    prev_count = 0
    for eco, n in call_counts:
        for _ in range(n):
            tracker.record_call(eco)
            total_calls += 1
            current = tracker.api_calls_made
            assert current >= prev_count, (
                f"api_calls_made decreased from {prev_count} to {current}"
            )
            prev_count = current

    assert tracker.api_calls_made == total_calls


# ---------------------------------------------------------------------------
# Property 10: MVP resolution semantics — same resolved_version regardless
# of declared specifier
# ---------------------------------------------------------------------------

@given(
    pkg_name=pkg_name_st,
    version=version_st,
    specifiers=st.lists(specifier_st, min_size=2, max_size=5),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_mvp_resolution_semantics_property(mock_get_client, pkg_name, version, specifiers):
    """Different declared specifiers for the same package result in the same
    resolved_version (latest), confirming MVP always-latest semantics.

    **Validates: Requirements 2.2, 3.2**
    """
    metadata = _make_metadata(pkg_name, version=version, ecosystem="pypi")

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.return_value = metadata
    mock_get_client.return_value = mock_client

    resolved_versions = set()
    for spec in specifiers:
        db_path = "/tmp/fake.db"
        resolver = _make_resolver(db_path)
        resolver._get_direct_deps = MagicMock(return_value=[
            {"package_name": pkg_name, "ecosystem": "pypi", "version_spec": spec}
        ])

        edges, _ = resolver.resolve_repo("owner/repo")
        resolved_edges = [e for e in edges if e.resolution_status == "resolved"]
        assert len(resolved_edges) >= 1
        for e in resolved_edges:
            resolved_versions.add(e.resolved_version)

    # All specifiers should produce the same resolved version (MVP: always latest)
    assert len(resolved_versions) == 1, (
        f"Expected single resolved version, got {resolved_versions}"
    )
    assert version in resolved_versions


# ---------------------------------------------------------------------------
# Property 11: edges_per_depth consistency
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=5, unique=True),
    sub_dep_names=st.lists(pkg_name_st, min_size=0, max_size=3, unique=True),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_edges_per_depth_consistency_property(mock_get_client, dep_names, sub_dep_names):
    """sum(summary.edges_per_depth.values()) == summary.total_edges and all
    depth keys >= 1.

    **Validates: Requirements 11.5**
    """
    # Filter sub_deps to avoid overlap with direct deps
    sub_deps = [s for s in sub_dep_names if s not in dep_names]

    metadata_map = {}
    for name in dep_names:
        metadata_map[name] = _make_metadata(name, ecosystem="pypi", deps=sub_deps)
    for name in sub_deps:
        metadata_map[name] = _make_metadata(name, ecosystem="pypi")

    resolver, _ = _setup_resolver_with_deps(dep_names, metadata_map)

    mock_client = MagicMock()
    mock_client.ecosystem = "pypi"
    mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
    mock_get_client.return_value = mock_client

    edges, summary = resolver.resolve_repo("owner/repo")

    # All depth keys >= 1
    for depth_key in summary.edges_per_depth:
        assert depth_key >= 1, f"edges_per_depth has invalid key {depth_key}"

    # Sum of edges_per_depth values == total_edges
    assert sum(summary.edges_per_depth.values()) == summary.total_edges, (
        f"edges_per_depth sum {sum(summary.edges_per_depth.values())} "
        f"!= total_edges {summary.total_edges}"
    )


# ---------------------------------------------------------------------------
# Property 12: source_registry invariant — never a URL
# ---------------------------------------------------------------------------

@given(
    dep_names=st.lists(pkg_name_st, min_size=1, max_size=5, unique=True),
    include_unsupported=st.booleans(),
)
@settings(database=None, max_examples=50)
@patch("open_source_risk_model.resolution.resolver.get_registry_client")
def test_source_registry_invariant_property(mock_get_client, dep_names, include_unsupported):
    """For every edge, source_registry is either None or a short ecosystem
    identifier string — never a URL.

    **Validates: Requirements 8.1**
    """
    VALID_REGISTRIES = {"pypi", "npm"}

    metadata_map = {
        name: _make_metadata(name, ecosystem="pypi")
        for name in dep_names
    }

    ecosystem = "pypi"
    if include_unsupported:
        # Use unsupported ecosystem for some deps to get None source_registry
        ecosystem = "rubygems"
        mock_get_client.return_value = None
    else:
        mock_client = MagicMock()
        mock_client.ecosystem = "pypi"
        mock_client.get_package_metadata.side_effect = lambda n, s=None: metadata_map.get(n)
        mock_get_client.return_value = mock_client

    resolver, _ = _setup_resolver_with_deps(dep_names, metadata_map, ecosystem=ecosystem)

    edges, summary = resolver.resolve_repo("owner/repo")

    for edge in edges:
        if edge.source_registry is not None:
            # Must be a short identifier, not a URL
            assert not edge.source_registry.startswith("http"), (
                f"source_registry is a URL: {edge.source_registry}"
            )
            assert edge.source_registry in VALID_REGISTRIES, (
                f"source_registry '{edge.source_registry}' not in {VALID_REGISTRIES}"
            )
        # source_registry is either None or a valid short string
        assert edge.source_registry is None or len(edge.source_registry) < 20, (
            f"source_registry too long: {edge.source_registry}"
        )
