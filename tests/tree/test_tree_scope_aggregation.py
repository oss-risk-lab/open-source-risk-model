"""Tests for tree node scope aggregation and transitive runtime metrics.

Covers:
- Task 7.3: Unit test for tree node aggregation (runtime-over-dev)
- Task 7.4: Property test for node aggregated scope correctness (Property 4)
- Task 8.5: Unit test for transitive runtime count correctness
- Task 8.6: Unit test for scope_counts_are_direct_only flag
"""

from __future__ import annotations

import os
import sqlite3
from typing import List

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.open_source_risk_model.dependencies.scope_classifier import (
    CONFIDENCE_PRIORITY,
    SCOPE_PRIORITY,
    aggregate_node_scope,
)
from src.open_source_risk_model.resolution.models import ResolutionEdge
from src.open_source_risk_model.tree.metrics import SummaryMetricsCalculator
from src.open_source_risk_model.tree.models import SummaryMetrics, TreeNode
from src.open_source_risk_model.tree.service import TreeService
from src.open_source_risk_model.tree.tree_utils import walk_tree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO = "owner/test-repo"
TS = "2024-01-01T00:00:00+00:00"

VALID_SCOPES = list(SCOPE_PRIORITY.keys())
VALID_CONFIDENCES = list(CONFIDENCE_PRIORITY.keys())


def _create_test_db(tmp_path: str) -> str:
    """Create a minimal SQLite database with the required tables."""
    db_path = os.path.join(tmp_path, "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repo_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            specifier TEXT,
            extras TEXT,
            markers TEXT,
            dependency_group TEXT DEFAULT 'prod',
            is_direct BOOLEAN NOT NULL DEFAULT 1,
            is_optional BOOLEAN NOT NULL DEFAULT 0,
            manifest_path TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            resolved_repo TEXT,
            resolution_confidence REAL,
            resolution_method TEXT,
            parent_package_name TEXT,
            parent_package_version TEXT,
            package_version TEXT,
            dependency_scope TEXT DEFAULT 'unknown',
            scope_confidence TEXT DEFAULT 'low',
            UNIQUE(repo_full_name, package_name, manifest_path)
        );

        CREATE TABLE IF NOT EXISTS repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            schema_version TEXT,
            graph_json TEXT,
            node_count INTEGER DEFAULT 0,
            edge_count INTEGER DEFAULT 0,
            data_sources TEXT DEFAULT '[]',
            warnings TEXT DEFAULT '[]',
            generation_time_ms INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS package_mappings (
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            repo_full_name TEXT,
            resolution_method TEXT NOT NULL,
            confidence REAL NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (package_name, registry_type)
        );

        CREATE TABLE IF NOT EXISTS repo_cves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            severity TEXT,
            description TEXT,
            published_date TEXT,
            source TEXT DEFAULT 'ghsa',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS repo_maintainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            maintainer_username TEXT NOT NULL,
            role TEXT DEFAULT 'contributor',
            contributions INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS resolved_dependencies (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name   TEXT NOT NULL,
            parent_ecosystem TEXT,
            parent_package   TEXT NOT NULL,
            child_ecosystem  TEXT,
            child_package    TEXT NOT NULL,
            declared_specifier TEXT,
            resolved_version TEXT,
            depth            INTEGER NOT NULL,
            resolution_status TEXT NOT NULL DEFAULT 'resolved',
            error_reason     TEXT,
            source_registry  TEXT,
            resolved_at      TEXT NOT NULL,
            dependency_scope TEXT DEFAULT 'unknown',
            scope_confidence TEXT DEFAULT 'low'
        );
    """)
    conn.close()
    return db_path


def _insert_repo_graph(db_path: str, repo: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', '{}', datetime('now'), datetime('now'))""",
        (repo,),
    )
    conn.commit()
    conn.close()


def _insert_resolved_edge(db_path: str, edge: ResolutionEdge) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO resolved_dependencies
           (repo_full_name, parent_ecosystem, parent_package,
            child_ecosystem, child_package, declared_specifier,
            resolved_version, depth, resolution_status,
            error_reason, source_registry, resolved_at,
            dependency_scope, scope_confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (edge.repo_full_name, edge.parent_ecosystem, edge.parent_package,
         edge.child_ecosystem, edge.child_package, edge.declared_specifier,
         edge.resolved_version, edge.depth, edge.resolution_status,
         edge.error_reason, edge.source_registry, edge.resolved_at,
         edge.dependency_scope, edge.scope_confidence),
    )
    conn.commit()
    conn.close()


def _make_edge(**kwargs) -> ResolutionEdge:
    """Create a ResolutionEdge with sensible defaults."""
    defaults = dict(
        repo_full_name=REPO,
        parent_ecosystem=None,
        parent_package=REPO,
        child_ecosystem="pypi",
        child_package="pkg-a",
        declared_specifier=">=1.0",
        resolved_version="1.0.0",
        depth=1,
        resolution_status="resolved",
        error_reason=None,
        source_registry="pypi",
        resolved_at=TS,
        dependency_scope="unknown",
        scope_confidence="low",
    )
    defaults.update(kwargs)
    return ResolutionEdge(**defaults)


# ---------------------------------------------------------------------------
# Task 7.3: Unit test for tree node aggregation (runtime-over-dev)
# ---------------------------------------------------------------------------

class TestTreeNodeScopeAggregation:
    """Tree node scope aggregation: highest priority scope wins (Req 9.1, 4.2)."""

    def test_runtime_over_dev_aggregation(self, tmp_path):
        """When X is reached via runtime and dev paths, TreeNode shows runtime."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # parent_A (runtime) → X, parent_B (dev) → X
        # Both parent_A and parent_B are direct deps of the repo
        edges = [
            _make_edge(
                child_package="parent-a", child_ecosystem="pypi",
                depth=1, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                child_package="parent-b", child_ecosystem="pypi",
                depth=1, dependency_scope="dev", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="parent-a",
                child_package="pkg-x", child_ecosystem="pypi",
                depth=2, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="parent-b",
                child_package="pkg-x", child_ecosystem="pypi",
                depth=2, dependency_scope="dev", scope_confidence="high",
            ),
        ]

        for edge in edges:
            _insert_resolved_edge(db_path, edge)

        service = TreeService(db_path=db_path)
        root = service._build_tree_from_resolved(REPO, edges)

        # Find the TreeNode for pkg-x (it appears under both parent-a and parent-b)
        x_nodes = [n for n in walk_tree(root) if n.name == "pkg-x"]
        assert len(x_nodes) >= 1

        # All occurrences of pkg-x should show aggregated scope = runtime
        for x_node in x_nodes:
            assert x_node.dependency_scope == "runtime"
            assert x_node.scope_confidence == "high"

    def test_to_dict_includes_scope(self, tmp_path):
        """Verify to_dict() includes dependency_scope and scope_confidence."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        edges = [
            _make_edge(
                child_package="pkg-a", child_ecosystem="pypi",
                depth=1, dependency_scope="runtime", scope_confidence="high",
            ),
        ]
        for edge in edges:
            _insert_resolved_edge(db_path, edge)

        service = TreeService(db_path=db_path)
        root = service._build_tree_from_resolved(REPO, edges)

        root_dict = root.to_dict()
        child_dict = root_dict["children"][0]
        assert child_dict["dependency_scope"] == "runtime"
        assert child_dict["scope_confidence"] == "high"

    def test_unknown_scope_not_in_to_dict(self, tmp_path):
        """When scope is None, to_dict() omits dependency_scope."""
        node = TreeNode(name="test", dependency_scope=None, scope_confidence=None)
        d = node.to_dict()
        assert "dependency_scope" not in d
        assert "scope_confidence" not in d


# ---------------------------------------------------------------------------
# Task 7.4: Property test for node aggregated scope correctness (Property 4)
# ---------------------------------------------------------------------------

scope_strategy = st.sampled_from(VALID_SCOPES)
confidence_strategy = st.sampled_from(VALID_CONFIDENCES)
scope_tuple_strategy = st.tuples(scope_strategy, confidence_strategy)


class TestNodeAggregatedScopeProperty:
    """Property 4: Node Aggregated Scope Correctness.

    **Validates: Requirements 4.2, 4.3, 5.2, 9.1**
    """

    @given(tuples=st.lists(scope_tuple_strategy, min_size=1, max_size=20))
    @settings(max_examples=200)
    def test_aggregate_returns_max_priority_scope(self, tuples):
        """Aggregated scope has max SCOPE_PRIORITY; among ties, max confidence."""
        result_scope, result_confidence = aggregate_node_scope(tuples)

        # Expected: max scope priority
        max_scope_pri = max(SCOPE_PRIORITY.get(s, 0) for s, _ in tuples)
        assert SCOPE_PRIORITY.get(result_scope, 0) == max_scope_pri

        # Among tuples with max scope priority, confidence should be max
        tied_tuples = [
            (s, c) for s, c in tuples
            if SCOPE_PRIORITY.get(s, 0) == max_scope_pri
        ]
        max_conf_pri = max(CONFIDENCE_PRIORITY.get(c, 0) for _, c in tied_tuples)
        assert CONFIDENCE_PRIORITY.get(result_confidence, 0) == max_conf_pri


# ---------------------------------------------------------------------------
# Task 8.5: Unit test for transitive runtime count correctness
# ---------------------------------------------------------------------------

class TestTransitiveRuntimeCount:
    """Transitive runtime dependency count (Req 10.1, 10.4)."""

    def test_counts_transitive_runtime_deps(self):
        """3 transitive runtime, 2 transitive dev, 1 transitive unknown → count=3."""
        edges = [
            # 3 transitive runtime deps (depth > 1)
            _make_edge(child_package="rt-1", depth=2, dependency_scope="runtime", scope_confidence="high"),
            _make_edge(child_package="rt-2", depth=3, dependency_scope="runtime", scope_confidence="high"),
            _make_edge(child_package="rt-3", depth=2, dependency_scope="runtime", scope_confidence="medium"),
            # 2 transitive dev deps
            _make_edge(child_package="dev-1", depth=2, dependency_scope="dev", scope_confidence="high"),
            _make_edge(child_package="dev-2", depth=2, dependency_scope="dev", scope_confidence="high"),
            # 1 transitive unknown dep
            _make_edge(child_package="unk-1", depth=2, dependency_scope="unknown", scope_confidence="low"),
        ]
        count = SummaryMetricsCalculator._compute_transitive_runtime_count(edges)
        assert count == 3

    def test_depth_1_runtime_not_counted(self):
        """Depth-1 (direct) runtime edge is NOT counted as transitive."""
        edges = [
            _make_edge(child_package="direct-rt", depth=1, dependency_scope="runtime", scope_confidence="high"),
            _make_edge(child_package="trans-rt", depth=2, dependency_scope="runtime", scope_confidence="high"),
        ]
        count = SummaryMetricsCalculator._compute_transitive_runtime_count(edges)
        assert count == 1  # Only the transitive one

    def test_unresolved_edge_not_counted(self):
        """Unresolved edges are NOT counted."""
        edges = [
            _make_edge(
                child_package="unresolved-rt", depth=2,
                dependency_scope="runtime", scope_confidence="high",
                resolution_status="error", error_reason="fetch failed",
            ),
        ]
        count = SummaryMetricsCalculator._compute_transitive_runtime_count(edges)
        assert count == 0

    def test_empty_edges_returns_zero(self):
        """Empty edge list returns 0."""
        count = SummaryMetricsCalculator._compute_transitive_runtime_count([])
        assert count == 0

    def test_multi_path_aggregation_runtime_wins(self):
        """Same child via runtime and dev paths → counted as runtime."""
        edges = [
            _make_edge(child_package="pkg-x", depth=2, dependency_scope="runtime", scope_confidence="high"),
            _make_edge(child_package="pkg-x", depth=3, dependency_scope="dev", scope_confidence="high"),
        ]
        count = SummaryMetricsCalculator._compute_transitive_runtime_count(edges)
        assert count == 1  # pkg-x aggregates to runtime


# ---------------------------------------------------------------------------
# Task 8.6: Unit test for scope_counts_are_direct_only flag
# ---------------------------------------------------------------------------

class TestScopeCountsAreDirectOnlyFlag:
    """scope_counts_are_direct_only flag behavior (Req 11.3)."""

    def test_flag_true_when_no_resolved_edges(self):
        """Flag is True when no resolved_edges are provided."""
        root = TreeNode(id="repo", node_type="repository", name="repo", depth=0)
        calc = SummaryMetricsCalculator()
        metrics = calc.calculate_metrics(root, [])
        assert metrics.scope_counts_are_direct_only is True

    def test_flag_true_when_all_unknown_scopes(self):
        """Flag stays True when all transitive edges have unknown scope."""
        root = TreeNode(id="repo", node_type="repository", name="repo", depth=0)
        edges = [
            _make_edge(child_package="pkg-a", depth=2, dependency_scope="unknown", scope_confidence="low"),
        ]
        calc = SummaryMetricsCalculator()
        metrics = calc.calculate_metrics(root, [], resolved_edges=edges)
        assert metrics.scope_counts_are_direct_only is True

    def test_flag_false_when_transitive_scope_available(self):
        """Flag flips to False when transitive scope data is available."""
        root = TreeNode(id="repo", node_type="repository", name="repo", depth=0)
        edges = [
            _make_edge(child_package="pkg-a", depth=2, dependency_scope="runtime", scope_confidence="high"),
        ]
        calc = SummaryMetricsCalculator()
        metrics = calc.calculate_metrics(root, [], resolved_edges=edges)
        assert metrics.scope_counts_are_direct_only is False

    def test_flag_true_when_only_direct_non_unknown(self):
        """Flag stays True when only depth-1 edges have non-unknown scope."""
        root = TreeNode(id="repo", node_type="repository", name="repo", depth=0)
        edges = [
            _make_edge(child_package="pkg-a", depth=1, dependency_scope="runtime", scope_confidence="high"),
        ]
        calc = SummaryMetricsCalculator()
        metrics = calc.calculate_metrics(root, [], resolved_edges=edges)
        # depth-1 edges with non-unknown scope don't count as "transitive scope data"
        assert metrics.scope_counts_are_direct_only is True


# ---------------------------------------------------------------------------
# Task 10.2: Verify API response includes all new fields
# ---------------------------------------------------------------------------

class TestAPIResponseIncludesNewFields:
    """Verify end-to-end wiring: get_dependency_tree() response includes
    dependency_scope, scope_confidence on nodes and
    transitive_runtime_dependency_count in summary_metrics.

    Requirements: 11.1, 11.2, 11.3
    """

    def test_response_includes_scope_on_transitive_nodes(self, tmp_path):
        """dependency_scope and scope_confidence appear on transitive tree nodes."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        edges = [
            _make_edge(
                child_package="direct-a", child_ecosystem="pypi",
                depth=1, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-b", child_ecosystem="pypi",
                depth=2, dependency_scope="runtime", scope_confidence="high",
            ),
        ]
        for edge in edges:
            _insert_resolved_edge(db_path, edge)

        service = TreeService(db_path=db_path)
        response = service.get_dependency_tree(REPO)
        resp_dict = response.to_dict()

        # Check transitive node has scope fields
        tree = resp_dict["tree"]
        direct_child = tree["children"][0]
        assert direct_child["dependency_scope"] == "runtime"
        assert direct_child["scope_confidence"] == "high"

        trans_child = direct_child["children"][0]
        assert trans_child["dependency_scope"] == "runtime"
        assert trans_child["scope_confidence"] == "high"

    def test_response_includes_transitive_runtime_count(self, tmp_path):
        """transitive_runtime_dependency_count appears in summary_metrics."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        edges = [
            _make_edge(
                child_package="direct-a", child_ecosystem="pypi",
                depth=1, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-rt", child_ecosystem="pypi",
                depth=2, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-dev", child_ecosystem="pypi",
                depth=2, dependency_scope="dev", scope_confidence="high",
            ),
        ]
        for edge in edges:
            _insert_resolved_edge(db_path, edge)

        service = TreeService(db_path=db_path)
        response = service.get_dependency_tree(REPO)
        metrics = response.summary_metrics

        assert metrics.transitive_runtime_dependency_count == 1  # only trans-rt

    def test_scope_counts_are_direct_only_false_with_transitive_data(self, tmp_path):
        """scope_counts_are_direct_only is False when transitive scope data available."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        edges = [
            _make_edge(
                child_package="direct-a", child_ecosystem="pypi",
                depth=1, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-rt", child_ecosystem="pypi",
                depth=2, dependency_scope="runtime", scope_confidence="high",
            ),
        ]
        for edge in edges:
            _insert_resolved_edge(db_path, edge)

        service = TreeService(db_path=db_path)
        response = service.get_dependency_tree(REPO)
        metrics = response.summary_metrics

        assert metrics.scope_counts_are_direct_only is False


# ---------------------------------------------------------------------------
# Task 11.2: Property test for transitive runtime count correctness (Property 6)
# ---------------------------------------------------------------------------

_valid_scopes_list = list(SCOPE_PRIORITY.keys())
_valid_confs_list = list(CONFIDENCE_PRIORITY.keys())
_resolution_statuses = ["resolved", "error", "cycle_detected", "max_depth_reached"]


@st.composite
def random_resolved_edges(draw):
    """Generate a random set of resolved edges with varying scopes, depths, statuses.

    Returns a list of ResolutionEdge objects.
    """
    num_packages = draw(st.integers(min_value=1, max_value=8))
    edges = []
    for i in range(num_packages):
        pkg_name = f"pkg-{i}"
        ecosystem = draw(st.sampled_from(["pypi", "npm"]))
        # Each package may have 1-3 edges (multi-path)
        num_edges = draw(st.integers(min_value=1, max_value=3))
        for _ in range(num_edges):
            depth = draw(st.integers(min_value=1, max_value=5))
            scope = draw(st.sampled_from(_valid_scopes_list))
            confidence = draw(st.sampled_from(_valid_confs_list))
            status = draw(st.sampled_from(_resolution_statuses))
            edge = _make_edge(
                child_package=pkg_name,
                child_ecosystem=ecosystem,
                depth=depth,
                dependency_scope=scope,
                scope_confidence=confidence,
                resolution_status=status,
                error_reason="err" if status != "resolved" else None,
            )
            edges.append(edge)
    return edges


class TestTransitiveRuntimeCountProperty:
    """Property 6: Transitive Runtime Count Correctness.

    For any set of resolved edges, transitive_runtime_dependency_count equals
    the number of unique child packages (by ecosystem + name) where:
    (a) min depth > 1, (b) aggregated scope is "runtime", (c) at least one
    edge has resolution_status == "resolved".

    **Validates: Requirements 10.1, 10.4**
    """

    @given(edges=random_resolved_edges())
    @settings(max_examples=200)
    def test_count_matches_manual_computation(self, edges):
        """Computed count matches manual grouping + aggregation."""
        # Manual computation
        from collections import defaultdict
        children = defaultdict(list)
        for e in edges:
            children[(e.child_ecosystem, e.child_package)].append(e)

        expected_count = 0
        for child_key, child_edges in children.items():
            min_depth = min(e.depth for e in child_edges)
            if min_depth <= 1:
                continue
            has_resolved = any(e.resolution_status == "resolved" for e in child_edges)
            if not has_resolved:
                continue
            scope_tuples = [(e.dependency_scope, e.scope_confidence) for e in child_edges]
            agg_scope, _ = aggregate_node_scope(scope_tuples)
            if agg_scope == "runtime":
                expected_count += 1

        actual_count = SummaryMetricsCalculator._compute_transitive_runtime_count(edges)
        assert actual_count == expected_count


# ---------------------------------------------------------------------------
# Task 11.3: Property test for existing metrics preservation (Property 7)
# ---------------------------------------------------------------------------

@st.composite
def random_dependency_tree_with_scope(draw):
    """Generate a random dependency tree (TreeNode) with scope data and
    matching resolved edges.

    Returns (root, resolved_edges, repo_full_name).
    """
    repo = "owner/prop-test-repo"
    root = TreeNode(
        id=repo, node_type="repository", name=repo, depth=0,
        dependency_type="direct",
    )

    num_direct = draw(st.integers(min_value=0, max_value=5))
    resolved_edges = []

    for i in range(num_direct):
        pkg_name = f"direct-{i}"
        scope = draw(st.sampled_from(_valid_scopes_list))
        confidence = draw(st.sampled_from(_valid_confs_list))

        child_node = TreeNode(
            id=f"pypi:{pkg_name}",
            node_type="package",
            name=pkg_name,
            version="1.0.0",
            depth=1,
            dependency_type="direct",
            ecosystem="pypi",
            dependency_scope=scope,
            scope_confidence=confidence,
        )

        # Direct edge (depth=1)
        resolved_edges.append(_make_edge(
            repo_full_name=repo,
            child_package=pkg_name,
            child_ecosystem="pypi",
            depth=1,
            dependency_scope=scope,
            scope_confidence=confidence,
        ))

        # Each direct dep may have 0-3 transitive children
        num_trans = draw(st.integers(min_value=0, max_value=3))
        for j in range(num_trans):
            trans_name = f"trans-{i}-{j}"
            trans_scope = draw(st.sampled_from(_valid_scopes_list))
            trans_conf = draw(st.sampled_from(_valid_confs_list))

            trans_node = TreeNode(
                id=f"pypi:{trans_name}",
                node_type="package",
                name=trans_name,
                version="1.0.0",
                depth=2,
                dependency_type="transitive",
                ecosystem="pypi",
                dependency_scope=trans_scope,
                scope_confidence=trans_conf,
            )
            child_node.children.append(trans_node)

            resolved_edges.append(_make_edge(
                repo_full_name=repo,
                parent_ecosystem="pypi",
                parent_package=pkg_name,
                child_package=trans_name,
                child_ecosystem="pypi",
                depth=2,
                dependency_scope=trans_scope,
                scope_confidence=trans_conf,
            ))

        root.children.append(child_node)

    return root, resolved_edges, repo


class TestExistingMetricsPreservationProperty:
    """Property 7: Existing Metrics Preservation.

    After scope propagation, total_dependencies == direct_dependencies +
    transitive_dependencies. Direct scope counts remain unchanged.

    **Validates: Requirements 12.2, 12.3**
    """

    @given(data=random_dependency_tree_with_scope())
    @settings(max_examples=200)
    def test_total_equals_direct_plus_transitive(self, data):
        """total_dependencies == direct_dependencies + transitive_dependencies."""
        root, resolved_edges, repo = data

        calc = SummaryMetricsCalculator()
        metrics = calc.calculate_metrics(
            root, [], resolved_edges=resolved_edges,
        )

        assert metrics.total_dependencies == (
            metrics.direct_dependencies + metrics.transitive_dependencies
        )

    @given(data=random_dependency_tree_with_scope())
    @settings(max_examples=200)
    def test_direct_scope_counts_unchanged(self, data):
        """Direct scope counts are the same with or without resolved_edges."""
        root, resolved_edges, repo = data

        calc = SummaryMetricsCalculator()

        # Metrics WITHOUT resolved_edges (Phase 1 behavior)
        metrics_without = calc.calculate_metrics(root, [])

        # Metrics WITH resolved_edges (Phase 2 behavior)
        metrics_with = calc.calculate_metrics(
            root, [], resolved_edges=resolved_edges,
        )

        # Direct counts should be identical
        assert metrics_with.direct_dependencies == metrics_without.direct_dependencies
        assert metrics_with.transitive_dependencies == metrics_without.transitive_dependencies
        assert metrics_with.total_dependencies == metrics_without.total_dependencies


# ---------------------------------------------------------------------------
# Task 11.4: Regression test confirming existing dependency counts unchanged
# ---------------------------------------------------------------------------

class TestRegressionExistingDependencyCounts:
    """Regression test: adding transitive scope propagation does not change
    total_dependencies, direct_dependencies, or transitive_dependencies.

    Requirements: 12.2, 12.3
    """

    def test_known_tree_counts_unchanged_with_scope(self, tmp_path):
        """Build a known dependency tree, add scope data, verify counts identical."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # Known tree structure:
        # repo → direct-a (runtime) → trans-a1 (runtime)
        #                            → trans-a2 (runtime)
        # repo → direct-b (dev)     → trans-b1 (dev)
        # repo → direct-c (test)
        edges = [
            # Direct deps
            _make_edge(
                child_package="direct-a", child_ecosystem="pypi",
                depth=1, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                child_package="direct-b", child_ecosystem="pypi",
                depth=1, dependency_scope="dev", scope_confidence="high",
            ),
            _make_edge(
                child_package="direct-c", child_ecosystem="pypi",
                depth=1, dependency_scope="test", scope_confidence="high",
            ),
            # Transitive deps
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-a1", child_ecosystem="pypi",
                depth=2, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-a2", child_ecosystem="pypi",
                depth=2, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-b",
                child_package="trans-b1", child_ecosystem="pypi",
                depth=2, dependency_scope="dev", scope_confidence="high",
            ),
        ]

        for edge in edges:
            _insert_resolved_edge(db_path, edge)

        service = TreeService(db_path=db_path)
        response = service.get_dependency_tree(REPO)
        metrics = response.summary_metrics

        # Verify counts
        assert metrics.direct_dependencies == 3
        assert metrics.transitive_dependencies == 3
        assert metrics.total_dependencies == 6

        # Verify transitive runtime count
        assert metrics.transitive_runtime_dependency_count == 2  # trans-a1, trans-a2

        # Verify scope flag
        assert metrics.scope_counts_are_direct_only is False

    def test_counts_match_tree_without_scope(self, tmp_path):
        """Counts with scope data match counts from equivalent tree without scope."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # Same structure but with unknown scope (simulating pre-Phase-2)
        edges_no_scope = [
            _make_edge(
                child_package="direct-a", child_ecosystem="pypi",
                depth=1, dependency_scope="unknown", scope_confidence="low",
            ),
            _make_edge(
                child_package="direct-b", child_ecosystem="pypi",
                depth=1, dependency_scope="unknown", scope_confidence="low",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-a1", child_ecosystem="pypi",
                depth=2, dependency_scope="unknown", scope_confidence="low",
            ),
        ]

        for edge in edges_no_scope:
            _insert_resolved_edge(db_path, edge)

        service = TreeService(db_path=db_path)
        response_no_scope = service.get_dependency_tree(REPO)

        # Now add scope data to a fresh DB
        sub_dir = tmp_path / "sub"
        sub_dir.mkdir()
        db_path2 = _create_test_db(str(sub_dir))
        _insert_repo_graph(db_path2, REPO)

        edges_with_scope = [
            _make_edge(
                child_package="direct-a", child_ecosystem="pypi",
                depth=1, dependency_scope="runtime", scope_confidence="high",
            ),
            _make_edge(
                child_package="direct-b", child_ecosystem="pypi",
                depth=1, dependency_scope="dev", scope_confidence="high",
            ),
            _make_edge(
                parent_ecosystem="pypi", parent_package="direct-a",
                child_package="trans-a1", child_ecosystem="pypi",
                depth=2, dependency_scope="runtime", scope_confidence="high",
            ),
        ]

        for edge in edges_with_scope:
            _insert_resolved_edge(db_path2, edge)

        service2 = TreeService(db_path=db_path2)
        response_with_scope = service2.get_dependency_tree(REPO)

        # Core counts must be identical
        m1 = response_no_scope.summary_metrics
        m2 = response_with_scope.summary_metrics
        assert m1.total_dependencies == m2.total_dependencies
        assert m1.direct_dependencies == m2.direct_dependencies
        assert m1.transitive_dependencies == m2.transitive_dependencies
