"""
Regression tests for Phase C dependency node/edge construction.

Two bugs made parse_dependencies=True unusable, which is why dependency
coverage sat at 0%:

1. Type mismatch — PackageMappingRepository.get_mapping() returns a dict, but
   PackageResolver.resolve() returns a PackageResolution dataclass. The builder
   called .get() on both, so any freshly-resolved package raised
       AttributeError: 'PackageResolution' object has no attribute 'get'

2. Dangling edge — the builder emitted a RESOLVES_TO edge targeting
   "repo:<resolved_repo>", a node that does not exist in the graph. Graph.validate
   requires exactly one REPO node, so the resolved repo can never be added as a
   second repo node either. The invalid graph was tolerated by build_graph but
   REJECTED by save_graph, which failed the entire scan.

The resolution is now recorded as PACKAGE node metadata instead of an edge.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.open_source_risk_model.dependencies.package_resolver import PackageResolution
from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.schema import (
    GraphConfig,
    Node,
    NodeType,
    EdgeType,
)


def _make_builder():
    """Builder with a single repo node, ready for the Phase C step."""
    now = datetime.now(timezone.utc).isoformat()
    builder = GraphBuilder.__new__(GraphBuilder)  # bypass network in __init__
    builder.full_name = "psf/requests"
    builder.config = GraphConfig(parse_dependencies=True)
    builder.rate_limiter = MagicMock()
    builder.dependency_repo = MagicMock()

    from src.open_source_risk_model.graph.schema import Graph

    builder.graph = Graph(
        nodes=[
            Node(
                id="repo:psf/requests",
                type=NodeType.REPO,
                label="psf/requests",
                metadata={},
                provenance={"source": "github_api", "fetched_at": now, "data_confidence": 1.0},
            )
        ],
        edges=[],
        metadata={"schema_version": "1.0", "generated_at": now},
    )
    return builder


_DEPS = [
    {
        "package_name": "urllib3",
        "registry_type": "pypi",
        "specifier": ">=1.21.1",
        "dependency_group": "prod",
        "is_optional": False,
        "manifest_path": "setup.py",
        "confidence": 0.9,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
]


def _run_phase_c(builder, resolve_return, cached_return=None):
    """Invoke _add_dependency_nodes_and_edges with mocked repos/resolver."""
    dep_repo = MagicMock()
    dep_repo.get_dependencies.return_value = _DEPS

    mapping_repo = MagicMock()
    mapping_repo.get_mapping.return_value = cached_return

    resolver = MagicMock()
    resolver.resolve.return_value = resolve_return

    with patch(
        "src.open_source_risk_model.persistence.dependency_repo.DependencyRepository",
        return_value=dep_repo,
    ), patch(
        "src.open_source_risk_model.persistence.dependency_repo.PackageMappingRepository",
        return_value=mapping_repo,
    ), patch(
        "src.open_source_risk_model.dependencies.PackageResolver",
        return_value=resolver,
    ):
        builder._add_dependency_nodes_and_edges()


def test_fresh_resolution_dataclass_does_not_raise():
    """resolver.resolve() returns a dataclass — must not crash on .get()."""
    builder = _make_builder()
    resolution = PackageResolution(
        package_name="urllib3",
        registry_type="pypi",
        repo_full_name="urllib3/urllib3",
        resolution_method="pypi_metadata",
        confidence=0.95,
        metadata={},
    )

    # Before the fix: AttributeError: 'PackageResolution' object has no attribute 'get'
    _run_phase_c(builder, resolve_return=resolution)

    pkg = [n for n in builder.graph.nodes if n.type == NodeType.PACKAGE]
    assert len(pkg) == 1
    assert pkg[0].metadata["resolved_repo"] == "urllib3/urllib3"
    assert pkg[0].metadata["resolution_method"] == "pypi_metadata"


def test_cached_resolution_dict_still_works():
    """get_mapping() returns a dict — the dict path must keep working."""
    builder = _make_builder()
    cached = {
        "package_name": "urllib3",
        "registry_type": "pypi",
        "repo_full_name": "urllib3/urllib3",
        "resolution_method": "cache",
        "confidence": 0.9,
    }

    _run_phase_c(builder, resolve_return=None, cached_return=cached)

    pkg = [n for n in builder.graph.nodes if n.type == NodeType.PACKAGE]
    assert len(pkg) == 1
    assert pkg[0].metadata["resolved_repo"] == "urllib3/urllib3"


def test_graph_stays_valid_and_has_no_dangling_resolves_edge():
    """The graph must remain persistable: one repo node, no dangling edges."""
    builder = _make_builder()
    resolution = PackageResolution(
        package_name="urllib3",
        registry_type="pypi",
        repo_full_name="urllib3/urllib3",
        resolution_method="pypi_metadata",
        confidence=0.95,
        metadata={},
    )

    _run_phase_c(builder, resolve_return=resolution)

    # This is the assertion that matters: save_graph rejects invalid graphs.
    assert builder.graph.validate() == []

    # No RESOLVES_TO edge pointing at a non-existent repo node.
    node_ids = {n.id for n in builder.graph.nodes}
    for edge in builder.graph.edges:
        assert edge.target in node_ids
        assert edge.source in node_ids
    assert not [e for e in builder.graph.edges if e.relationship_type == EdgeType.RESOLVES_TO]

    # Exactly one repo node (schema invariant).
    assert len([n for n in builder.graph.nodes if n.type == NodeType.REPO]) == 1

    # The DEPENDS_ON edge to the package is still present.
    depends = [e for e in builder.graph.edges if e.relationship_type == EdgeType.DEPENDS_ON]
    assert len(depends) == 1
    assert depends[0].target == "package:pypi:urllib3"


def test_unresolved_package_still_added():
    """A package that cannot be resolved must still appear as a node."""
    builder = _make_builder()
    _run_phase_c(builder, resolve_return=None)

    pkg = [n for n in builder.graph.nodes if n.type == NodeType.PACKAGE]
    assert len(pkg) == 1
    assert "resolved_repo" not in pkg[0].metadata
    assert builder.graph.validate() == []
