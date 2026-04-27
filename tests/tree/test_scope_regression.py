"""
Regression tests confirming existing dependency counting logic is unchanged
after adding scope classification fields.

Validates: Requirements 14.1, 14.2, 14.3, 14.4, 15.7
"""

from __future__ import annotations

import pytest

from open_source_risk_model.tree.metrics import SummaryMetricsCalculator
from open_source_risk_model.tree.models import RiskMetadata, SummaryMetrics, TreeNode


# ======================================================================
# Helpers
# ======================================================================


def _make_root(children: list[TreeNode] | None = None) -> TreeNode:
    """Create a repository root node."""
    return TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        depth=0,
        dependency_type="direct",
        children=children or [],
    )


def _make_pkg(
    name: str,
    depth: int,
    *,
    risk_score: float | None = None,
    vulnerability_count: int = 0,
    children: list[TreeNode] | None = None,
    dependency_scope: str | None = None,
    scope_confidence: str | None = None,
) -> TreeNode:
    """Create a package node with optional risk metadata and scope fields."""
    dep_type = "direct" if depth == 1 else "transitive"
    risk_level = None
    if risk_score is not None:
        risk_level = "low" if risk_score <= 30 else ("medium" if risk_score <= 70 else "high")
    risk_metadata = RiskMetadata(
        risk_score=risk_score,
        risk_level=risk_level,
        vulnerability_count=vulnerability_count,
        score_source="repo_graph" if risk_score is not None else "unavailable",
        score_completeness="full" if risk_score is not None else "missing",
    )
    return TreeNode(
        id=f"pkg:npm/{name}@1.0.0",
        node_type="package",
        name=name,
        version="1.0.0",
        depth=depth,
        dependency_type=dep_type,
        ecosystem="npm",
        risk_metadata=risk_metadata,
        children=children or [],
        dependency_scope=dependency_scope,
        scope_confidence=scope_confidence,
    )


calculator = SummaryMetricsCalculator(db_path=":memory:")


# ======================================================================
# Test 1: 3 direct deps, 0 transitive → total=3, direct=3, transitive=0
# ======================================================================


class TestThreeDirectZeroTransitive:
    """Validates: Requirements 14.2, 15.7"""

    def test_counts(self):
        root = _make_root([
            _make_pkg("a", depth=1),
            _make_pkg("b", depth=1),
            _make_pkg("c", depth=1),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == 3
        assert metrics.direct_dependencies == 3
        assert metrics.transitive_dependencies == 0

    def test_total_invariant(self):
        root = _make_root([
            _make_pkg("a", depth=1),
            _make_pkg("b", depth=1),
            _make_pkg("c", depth=1),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies


# ======================================================================
# Test 2: 2 direct deps, each with 2 transitive → total=6, direct=2, transitive=4
# ======================================================================


class TestTwoDirectWithTransitive:
    """Validates: Requirements 14.2, 15.7"""

    def test_counts(self):
        root = _make_root([
            _make_pkg("a", depth=1, children=[
                _make_pkg("a-t1", depth=2),
                _make_pkg("a-t2", depth=2),
            ]),
            _make_pkg("b", depth=1, children=[
                _make_pkg("b-t1", depth=2),
                _make_pkg("b-t2", depth=2),
            ]),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == 6
        assert metrics.direct_dependencies == 2
        assert metrics.transitive_dependencies == 4

    def test_total_invariant(self):
        root = _make_root([
            _make_pkg("a", depth=1, children=[
                _make_pkg("a-t1", depth=2),
                _make_pkg("a-t2", depth=2),
            ]),
            _make_pkg("b", depth=1, children=[
                _make_pkg("b-t1", depth=2),
                _make_pkg("b-t2", depth=2),
            ]),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies


# ======================================================================
# Test 3: Dependencies with dependency_scope="unknown" still counted correctly
# ======================================================================


class TestUnknownScopeDependenciesCounted:
    """Validates: Requirements 14.1, 14.2, 15.7

    Dependencies with scope='unknown' must be included in all views
    and calculations without error.
    """

    def test_unknown_scope_counted_in_totals(self):
        root = _make_root([
            _make_pkg("a", depth=1, dependency_scope="unknown", scope_confidence="low"),
            _make_pkg("b", depth=1, dependency_scope="unknown", scope_confidence="low"),
            _make_pkg("c", depth=1, dependency_scope="runtime", scope_confidence="high",
                       children=[
                           _make_pkg("c-t1", depth=2, dependency_scope="unknown", scope_confidence="low"),
                       ]),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == 4
        assert metrics.direct_dependencies == 3
        assert metrics.transitive_dependencies == 1

    def test_unknown_scope_total_invariant(self):
        root = _make_root([
            _make_pkg("a", depth=1, dependency_scope="unknown", scope_confidence="low"),
            _make_pkg("b", depth=1, dependency_scope="unknown", scope_confidence="low"),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies

    def test_unknown_scope_no_error(self):
        """Ensure no exception is raised when all deps have unknown scope."""
        root = _make_root([
            _make_pkg("x", depth=1, dependency_scope="unknown", scope_confidence="low",
                       children=[
                           _make_pkg("x-t1", depth=2, dependency_scope="unknown", scope_confidence="low"),
                           _make_pkg("x-t2", depth=2, dependency_scope="unknown", scope_confidence="low"),
                       ]),
        ])
        # Should not raise
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)
        assert metrics.total_dependencies == 3


# ======================================================================
# Test 4: Empty tree (root only) → total=0, direct=0, transitive=0
# ======================================================================


class TestEmptyTree:
    """Validates: Requirements 14.2, 15.7"""

    def test_counts(self):
        root = _make_root()
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == 0
        assert metrics.direct_dependencies == 0
        assert metrics.transitive_dependencies == 0

    def test_total_invariant(self):
        root = _make_root()
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies


# ======================================================================
# Test 5: high_risk_count and vulnerable_count still work with scope fields
# ======================================================================


class TestRiskMetricsWithScopeFields:
    """Validates: Requirements 14.2, 14.4, 15.7

    Existing risk/vulnerability counting must still function correctly
    when scope fields are present on nodes.
    """

    def test_high_risk_count_with_scope(self):
        root = _make_root([
            _make_pkg("safe", depth=1, risk_score=20.0,
                       dependency_scope="runtime", scope_confidence="high"),
            _make_pkg("risky", depth=1, risk_score=85.0,
                       dependency_scope="dev", scope_confidence="high"),
            _make_pkg("borderline", depth=1, risk_score=70.0,
                       dependency_scope="test", scope_confidence="medium"),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        # Only risk_score > 70 counts as high risk
        assert metrics.high_risk_count == 1
        assert metrics.total_dependencies == 3

    def test_vulnerable_count_with_scope(self):
        root = _make_root([
            _make_pkg("vuln-a", depth=1, vulnerability_count=3,
                       dependency_scope="runtime", scope_confidence="high"),
            _make_pkg("clean", depth=1, vulnerability_count=0,
                       dependency_scope="dev", scope_confidence="high"),
            _make_pkg("vuln-b", depth=1, vulnerability_count=1,
                       dependency_scope="unknown", scope_confidence="low",
                       children=[
                           _make_pkg("vuln-t", depth=2, vulnerability_count=2,
                                      dependency_scope="unknown", scope_confidence="low"),
                       ]),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.vulnerable_count == 3  # vuln-a, vuln-b, vuln-t
        assert metrics.total_dependencies == 4

    def test_existing_metrics_fields_populated(self):
        """All existing metrics fields must still be populated and accurate."""
        root = _make_root([
            _make_pkg("a", depth=1, risk_score=80.0, vulnerability_count=1,
                       dependency_scope="runtime", scope_confidence="high",
                       children=[
                           _make_pkg("a-t1", depth=2, risk_score=10.0,
                                      dependency_scope="runtime", scope_confidence="high"),
                       ]),
            _make_pkg("b", depth=1, risk_score=50.0,
                       dependency_scope="dev", scope_confidence="high"),
        ])
        metrics = calculator.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == 3
        assert metrics.direct_dependencies == 2
        assert metrics.transitive_dependencies == 1
        assert metrics.high_risk_count == 1  # only "a" with score 80
        assert metrics.vulnerable_count == 1  # only "a" with vuln_count=1
        assert metrics.max_depth == 2
        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies
