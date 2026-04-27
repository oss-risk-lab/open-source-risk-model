"""Unit tests for SummaryMetricsCalculator."""

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
    ecosystem: str = "npm",
    version: str = "1.0.0",
) -> TreeNode:
    """Create a package node with optional risk metadata."""
    dep_type = "direct" if depth == 1 else "transitive"
    risk_metadata = RiskMetadata(
        risk_score=risk_score,
        risk_level=_classify(risk_score),
        vulnerability_count=vulnerability_count,
        score_source="repo_graph" if risk_score is not None else "unavailable",
        score_completeness="full" if risk_score is not None else "missing",
    )
    return TreeNode(
        id=f"pkg:{ecosystem}/{name}@{version}",
        node_type="package",
        name=name,
        version=version,
        depth=depth,
        dependency_type=dep_type,
        ecosystem=ecosystem,
        risk_metadata=risk_metadata,
        children=children or [],
    )


def _classify(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 30:
        return "low"
    if score <= 70:
        return "medium"
    return "high"


# ======================================================================
# Tests
# ======================================================================

calculator = SummaryMetricsCalculator()


class TestTotalDirectTransitiveInvariant:
    """Test total = direct + transitive invariant."""

    def test_simple_tree(self):
        child_a = _make_pkg("a", 1, risk_score=50)
        child_b = _make_pkg("b", 1, risk_score=30)
        grandchild = _make_pkg("c", 2, risk_score=80)
        child_a.children = [grandchild]
        root = _make_root([child_a, child_b])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.total_dependencies == 3
        assert metrics.direct_dependencies == 2
        assert metrics.transitive_dependencies == 1
        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies

    def test_deep_tree(self):
        d3 = _make_pkg("d3", 3, risk_score=10)
        d2 = _make_pkg("d2", 2, risk_score=20, children=[d3])
        d1 = _make_pkg("d1", 1, risk_score=30, children=[d2])
        root = _make_root([d1])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.total_dependencies == 3
        assert metrics.direct_dependencies == 1
        assert metrics.transitive_dependencies == 2
        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies


class TestHighRiskCount:
    """Test high_risk_count only counts nodes with score > 70."""

    def test_counts_only_above_70(self):
        low = _make_pkg("low", 1, risk_score=30)
        medium = _make_pkg("med", 1, risk_score=70)
        high = _make_pkg("high", 1, risk_score=71)
        very_high = _make_pkg("vhigh", 1, risk_score=100)
        root = _make_root([low, medium, high, very_high])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.high_risk_count == 2  # 71 and 100

    def test_boundary_70_not_high_risk(self):
        at_70 = _make_pkg("at70", 1, risk_score=70)
        root = _make_root([at_70])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.high_risk_count == 0

    def test_boundary_71_is_high_risk(self):
        at_71 = _make_pkg("at71", 1, risk_score=71)
        root = _make_root([at_71])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.high_risk_count == 1


class TestPreservedAncestorNotCountedInHighRisk:
    """Test preserved ancestor not counted in high_risk_count.

    A preserved ancestor (low-risk) that is only in the tree because
    it's on the path to a high-risk descendant should NOT be counted
    in high_risk_count.
    """

    def test_low_risk_ancestor_of_high_risk_node(self):
        """Ancestor with low risk_score should not count as high risk."""
        high_risk_child = _make_pkg("risky", 2, risk_score=90)
        low_risk_ancestor = _make_pkg("safe", 1, risk_score=20, children=[high_risk_child])
        root = _make_root([low_risk_ancestor])

        metrics = calculator.calculate_metrics(root, ["high_risk_only"])

        # Only the high-risk node counts, not the ancestor
        assert metrics.high_risk_count == 1
        # But both count in totals
        assert metrics.total_dependencies == 2

    def test_ancestor_with_high_risk_counts(self):
        """Ancestor that independently has risk_score > 70 DOES count."""
        high_risk_child = _make_pkg("risky", 2, risk_score=90)
        high_risk_ancestor = _make_pkg("also_risky", 1, risk_score=85, children=[high_risk_child])
        root = _make_root([high_risk_ancestor])

        metrics = calculator.calculate_metrics(root, ["high_risk_only"])

        assert metrics.high_risk_count == 2


class TestRiskiestBranch:
    """Test riskiest branch identification."""

    def test_single_branch(self):
        child = _make_pkg("a", 1, risk_score=50)
        root = _make_root([child])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.riskiest_branch is not None
        assert metrics.riskiest_branch["path"] == ["owner/repo", "pkg:npm/a@1.0.0"]
        assert metrics.riskiest_branch["cumulative_risk"] == 50.0

    def test_two_branches_picks_higher(self):
        low_branch = _make_pkg("low", 1, risk_score=20)
        high_branch = _make_pkg("high", 1, risk_score=80)
        root = _make_root([low_branch, high_branch])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.riskiest_branch is not None
        assert metrics.riskiest_branch["cumulative_risk"] == 80.0
        assert "pkg:npm/high@1.0.0" in metrics.riskiest_branch["path"]

    def test_deep_branch_cumulative(self):
        grandchild = _make_pkg("gc", 2, risk_score=40)
        child = _make_pkg("c", 1, risk_score=50, children=[grandchild])
        root = _make_root([child])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.riskiest_branch is not None
        # cumulative = 50 + 40 = 90
        assert metrics.riskiest_branch["cumulative_risk"] == 90.0
        assert metrics.riskiest_branch["path"] == [
            "owner/repo",
            "pkg:npm/c@1.0.0",
            "pkg:npm/gc@1.0.0",
        ]

    def test_riskiest_branch_cumulative_gte_any_individual(self):
        """Riskiest branch cumulative score >= any individual node's risk_score."""
        gc = _make_pkg("gc", 2, risk_score=60)
        child = _make_pkg("c", 1, risk_score=50, children=[gc])
        root = _make_root([child])

        metrics = calculator.calculate_metrics(root, [])

        max_individual = 60.0
        assert metrics.riskiest_branch is not None
        assert metrics.riskiest_branch["cumulative_risk"] >= max_individual


class TestZeroDependencyTree:
    """Test zero-dependency tree (root only, all counts zero)."""

    def test_root_only(self):
        root = _make_root([])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.total_dependencies == 0
        assert metrics.direct_dependencies == 0
        assert metrics.transitive_dependencies == 0
        assert metrics.high_risk_count == 0
        assert metrics.vulnerable_count == 0
        assert metrics.max_depth == 0
        assert metrics.riskiest_branch is None


class TestNodesWithRiskScoreNone:
    """Test with nodes having risk_score=None."""

    def test_none_risk_score_not_counted_as_high_risk(self):
        node = _make_pkg("unknown", 1, risk_score=None)
        root = _make_root([node])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.high_risk_count == 0

    def test_none_risk_score_contributes_zero_to_riskiest_branch(self):
        none_child = _make_pkg("none_risk", 1, risk_score=None)
        scored_child = _make_pkg("scored", 1, risk_score=50)
        root = _make_root([none_child, scored_child])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.riskiest_branch is not None
        # The scored branch should win (50 > 0)
        assert metrics.riskiest_branch["cumulative_risk"] == 50.0
        assert "pkg:npm/scored@1.0.0" in metrics.riskiest_branch["path"]

    def test_all_none_risk_scores_riskiest_branch_zero(self):
        a = _make_pkg("a", 1, risk_score=None)
        b = _make_pkg("b", 1, risk_score=None)
        root = _make_root([a, b])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.riskiest_branch is not None
        assert metrics.riskiest_branch["cumulative_risk"] == 0.0


class TestFiltersApplied:
    """Test filters_applied is populated correctly."""

    def test_empty_filters(self):
        root = _make_root([_make_pkg("a", 1, risk_score=50)])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.filters_applied == []

    def test_single_filter(self):
        root = _make_root([_make_pkg("a", 1, risk_score=80)])

        metrics = calculator.calculate_metrics(root, ["high_risk_only"])

        assert metrics.filters_applied == ["high_risk_only"]

    def test_multiple_filters(self):
        root = _make_root([_make_pkg("a", 1, risk_score=80, vulnerability_count=3)])

        filters = ["high_risk_only", "max_depth"]
        metrics = calculator.calculate_metrics(root, filters)

        assert metrics.filters_applied == ["high_risk_only", "max_depth"]

    def test_filters_are_copied(self):
        """Modifying the input list after calculation should not affect metrics."""
        root = _make_root([_make_pkg("a", 1, risk_score=50)])
        filters = ["high_risk_only"]

        metrics = calculator.calculate_metrics(root, filters)
        filters.append("vulnerable_only")

        assert metrics.filters_applied == ["high_risk_only"]


class TestVulnerableCount:
    """Test vulnerable_count counts nodes with vulnerability_count > 0."""

    def test_counts_vulnerable_nodes(self):
        vuln = _make_pkg("vuln", 1, risk_score=50, vulnerability_count=3)
        safe = _make_pkg("safe", 1, risk_score=50, vulnerability_count=0)
        root = _make_root([vuln, safe])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.vulnerable_count == 1

    def test_zero_vuln_not_counted(self):
        node = _make_pkg("pkg", 1, risk_score=50, vulnerability_count=0)
        root = _make_root([node])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.vulnerable_count == 0


class TestMaxDepth:
    """Test max_depth calculation."""

    def test_flat_tree(self):
        a = _make_pkg("a", 1, risk_score=10)
        b = _make_pkg("b", 1, risk_score=20)
        root = _make_root([a, b])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.max_depth == 1

    def test_deep_tree(self):
        d4 = _make_pkg("d4", 4, risk_score=10)
        d3 = _make_pkg("d3", 3, risk_score=10, children=[d4])
        d2 = _make_pkg("d2", 2, risk_score=10, children=[d3])
        d1 = _make_pkg("d1", 1, risk_score=10, children=[d2])
        root = _make_root([d1])

        metrics = calculator.calculate_metrics(root, [])

        assert metrics.max_depth == 4
