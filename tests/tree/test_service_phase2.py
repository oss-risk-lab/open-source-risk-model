"""Unit tests for TreeService Phase 2: Response Transformation."""

from __future__ import annotations

import copy

import pytest

from open_source_risk_model.tree.models import (
    DependencyTreeResponse,
    FilterConfig,
    ProvenanceInfo,
    RiskMetadata,
    SummaryMetrics,
    TreeNode,
)
from open_source_risk_model.tree.service import TreeService
from open_source_risk_model.tree.tree_utils import clone_tree, walk_tree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pkg(
    name: str,
    version: str | None = "1.0.0",
    depth: int = 1,
    ecosystem: str = "npm",
    risk_score: float | None = None,
    vulnerability_count: int = 0,
    children: list[TreeNode] | None = None,
) -> TreeNode:
    """Create a package TreeNode with optional risk metadata."""
    dep_type = "direct" if depth == 1 else "transitive"
    ver_part = version if version else "unknown"
    node = TreeNode(
        id=f"pkg:{ecosystem}/{name}@{ver_part}",
        node_type="package",
        name=name,
        version=version,
        depth=depth,
        dependency_type=dep_type,
        ecosystem=ecosystem,
        children=children or [],
    )
    node.risk_metadata = RiskMetadata(
        risk_score=risk_score,
        risk_level=_classify(risk_score),
        vulnerability_count=vulnerability_count,
        score_source="repo_graph" if risk_score is not None else "unavailable",
        score_completeness="full" if risk_score is not None else "missing",
    )
    return node


def _classify(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 30:
        return "low"
    if score <= 70:
        return "medium"
    return "high"


def _make_root(children: list[TreeNode] | None = None) -> TreeNode:
    """Create a repository root node."""
    return TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        version=None,
        depth=0,
        dependency_type="direct",
        children=children or [],
    )


def _service() -> TreeService:
    """Create a TreeService (db_path unused for Phase 2 tests)."""
    return TreeService(db_path=":memory:")


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


class TestFilterDirectOnly:
    def test_removes_depth_gt_1(self):
        grandchild = _make_pkg("gc", depth=2, risk_score=50)
        child = _make_pkg("child", depth=1, risk_score=30, children=[grandchild])
        root = _make_root([child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(direct_only=True)
        )
        tree = resp.tree
        assert len(tree.children) == 1
        assert tree.children[0].name == "child"
        assert tree.children[0].children == []

    def test_does_not_set_children_truncated(self):
        grandchild = _make_pkg("gc", depth=2, risk_score=50)
        child = _make_pkg("child", depth=1, risk_score=30, children=[grandchild])
        root = _make_root([child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(direct_only=True)
        )
        # direct_only does NOT set children_truncated
        assert resp.tree.children[0].children_truncated is False
        assert resp.tree.children[0].child_count is None


class TestFilterByDepth:
    def test_removes_deep_nodes(self):
        gc = _make_pkg("gc", depth=2, risk_score=10)
        child = _make_pkg("child", depth=1, risk_score=30, children=[gc])
        root = _make_root([child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(max_depth=1)
        )
        assert resp.tree.children[0].children == []

    def test_sets_children_truncated_on_boundary(self):
        gc = _make_pkg("gc", depth=2, risk_score=10)
        child = _make_pkg("child", depth=1, risk_score=30, children=[gc])
        root = _make_root([child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(max_depth=1)
        )
        boundary = resp.tree.children[0]
        assert boundary.children_truncated is True
        assert boundary.child_count == 1

    def test_no_truncation_flag_when_no_children(self):
        child = _make_pkg("child", depth=1, risk_score=30)
        root = _make_root([child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(max_depth=1)
        )
        assert resp.tree.children[0].children_truncated is False


class TestDirectOnlyVsMaxDepth1:
    def test_difference(self):
        """direct_only does NOT set children_truncated; max_depth=1 DOES."""
        gc = _make_pkg("gc", depth=2, risk_score=10)
        child = _make_pkg("child", depth=1, risk_score=30, children=[gc])

        svc = _service()

        # direct_only
        root1 = _make_root([clone_tree(child)])
        resp1 = svc._transform_for_response(
            root1, "database", FilterConfig(direct_only=True)
        )
        assert resp1.tree.children[0].children_truncated is False
        assert resp1.tree.children[0].child_count is None

        # max_depth=1
        root2 = _make_root([clone_tree(child)])
        resp2 = svc._transform_for_response(
            root2, "database", FilterConfig(max_depth=1)
        )
        assert resp2.tree.children[0].children_truncated is True
        assert resp2.tree.children[0].child_count == 1


class TestHighRiskOnlyFilter:
    def test_preserves_ancestor_paths(self):
        """Low-risk ancestor of high-risk node is included."""
        high_risk_gc = _make_pkg("risky", depth=2, risk_score=85, vulnerability_count=3)
        low_risk_child = _make_pkg("safe", depth=1, risk_score=20, children=[high_risk_gc])
        root = _make_root([low_risk_child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(high_risk_only=True)
        )
        # Root + low_risk_child (ancestor) + high_risk_gc (match)
        assert len(resp.tree.children) == 1
        assert resp.tree.children[0].name == "safe"
        assert len(resp.tree.children[0].children) == 1
        assert resp.tree.children[0].children[0].name == "risky"

    def test_removes_non_matching_branches(self):
        low_child = _make_pkg("low", depth=1, risk_score=10)
        high_child = _make_pkg("high", depth=1, risk_score=80)
        root = _make_root([low_child, high_child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(high_risk_only=True)
        )
        assert len(resp.tree.children) == 1
        assert resp.tree.children[0].name == "high"


class TestVulnerableOnlyFilter:
    def test_preserves_ancestor_paths(self):
        vuln_gc = _make_pkg("vuln", depth=2, risk_score=50, vulnerability_count=5)
        parent = _make_pkg("parent", depth=1, risk_score=20, vulnerability_count=0, children=[vuln_gc])
        root = _make_root([parent])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(vulnerable_only=True)
        )
        assert len(resp.tree.children) == 1
        assert resp.tree.children[0].name == "parent"
        assert len(resp.tree.children[0].children) == 1
        assert resp.tree.children[0].children[0].name == "vuln"


class TestCombinedFilters:
    def test_and_logic(self):
        """A leaf must satisfy ALL active criteria."""
        # high risk but not vulnerable → excluded
        high_no_vuln = _make_pkg("a", depth=1, risk_score=90, vulnerability_count=0)
        # high risk AND vulnerable → included
        high_and_vuln = _make_pkg("b", depth=1, risk_score=85, vulnerability_count=2)
        # vulnerable but not high risk → excluded
        vuln_no_high = _make_pkg("c", depth=1, risk_score=30, vulnerability_count=1)
        root = _make_root([high_no_vuln, high_and_vuln, vuln_no_high])

        svc = _service()
        resp = svc._transform_for_response(
            root,
            "database",
            FilterConfig(high_risk_only=True, vulnerable_only=True),
        )
        names = [c.name for c in resp.tree.children]
        assert names == ["b"]


class TestRootAlwaysIncluded:
    def test_root_included_regardless_of_filters(self):
        root = _make_root([])
        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(high_risk_only=True, vulnerable_only=True)
        )
        assert resp.tree is not None
        assert resp.tree.node_type == "repository"
        assert resp.tree.depth == 0


# ---------------------------------------------------------------------------
# Sorting tests
# ---------------------------------------------------------------------------


class TestSorting:
    def test_sort_by_risk_score_desc(self):
        a = _make_pkg("a", depth=1, risk_score=30)
        b = _make_pkg("b", depth=1, risk_score=80)
        c = _make_pkg("c", depth=1, risk_score=50)
        root = _make_root([a, b, c])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="risk_score"
        )
        names = [c.name for c in resp.tree.children]
        assert names == ["b", "c", "a"]

    def test_sort_by_risk_score_nulls_last(self):
        a = _make_pkg("a", depth=1, risk_score=None)
        b = _make_pkg("b", depth=1, risk_score=50)
        root = _make_root([a, b])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="risk_score"
        )
        names = [c.name for c in resp.tree.children]
        assert names == ["b", "a"]

    def test_sort_by_risk_score_tiebreak_name_version(self):
        a = _make_pkg("beta", version="2.0.0", depth=1, risk_score=50)
        b = _make_pkg("alpha", version="1.0.0", depth=1, risk_score=50)
        root = _make_root([a, b])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="risk_score"
        )
        names = [c.name for c in resp.tree.children]
        assert names == ["alpha", "beta"]

    def test_sort_by_name(self):
        c = _make_pkg("charlie", depth=1, risk_score=90)
        a = _make_pkg("alpha", depth=1, risk_score=10)
        b = _make_pkg("bravo", depth=1, risk_score=50)
        root = _make_root([c, a, b])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="name"
        )
        names = [ch.name for ch in resp.tree.children]
        assert names == ["alpha", "bravo", "charlie"]

    def test_sort_by_vulnerability_count_desc(self):
        a = _make_pkg("a", depth=1, vulnerability_count=1)
        b = _make_pkg("b", depth=1, vulnerability_count=5)
        c = _make_pkg("c", depth=1, vulnerability_count=0)
        root = _make_root([a, b, c])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="vulnerability_count"
        )
        names = [ch.name for ch in resp.tree.children]
        assert names == ["b", "a", "c"]

    def test_sort_by_vulnerability_count_nulls_as_zero(self):
        a = _make_pkg("a", depth=1, vulnerability_count=3)
        b = _make_pkg("b", depth=1, vulnerability_count=0)
        b.risk_metadata = None  # null risk metadata → treated as 0
        root = _make_root([b, a])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="vulnerability_count"
        )
        names = [ch.name for ch in resp.tree.children]
        assert names == ["a", "b"]

    def test_default_sort_name_then_version(self):
        a = _make_pkg("alpha", version="2.0.0", depth=1)
        b = _make_pkg("alpha", version="1.0.0", depth=1)
        c = _make_pkg("bravo", version="1.0.0", depth=1)
        root = _make_root([c, a, b])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig()
        )
        result = [(ch.name, ch.version) for ch in resp.tree.children]
        assert result == [("alpha", "1.0.0"), ("alpha", "2.0.0"), ("bravo", "1.0.0")]

    def test_version_none_sorts_last(self):
        a = _make_pkg("alpha", version="1.0.0", depth=1)
        b = _make_pkg("alpha", version=None, depth=1)
        root = _make_root([b, a])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig()
        )
        versions = [ch.version for ch in resp.tree.children]
        assert versions == ["1.0.0", None]

    def test_sorting_applied_recursively(self):
        gc_b = _make_pkg("b_gc", depth=2, risk_score=10)
        gc_a = _make_pkg("a_gc", depth=2, risk_score=20)
        child = _make_pkg("child", depth=1, children=[gc_b, gc_a])
        root = _make_root([child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="name"
        )
        gc_names = [gc.name for gc in resp.tree.children[0].children]
        assert gc_names == ["a_gc", "b_gc"]


# ---------------------------------------------------------------------------
# Truncation tests
# ---------------------------------------------------------------------------


class TestTruncation:
    def test_keeps_first_n_from_sorted_order(self):
        children = [_make_pkg(f"pkg{i}", depth=1, risk_score=i * 10) for i in range(5)]
        root = _make_root(children)

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="risk_score", truncate_after_children=2
        )
        # risk_score DESC → pkg4 (40), pkg3 (30) kept
        names = [c.name for c in resp.tree.children]
        assert names == ["pkg4", "pkg3"]

    def test_sets_child_count_and_children_truncated(self):
        children = [_make_pkg(f"pkg{i}", depth=1) for i in range(5)]
        root = _make_root(children)

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), truncate_after_children=3
        )
        assert resp.tree.children_truncated is True
        assert resp.tree.child_count == 5
        assert len(resp.tree.children) == 3

    def test_no_truncation_when_within_limit(self):
        children = [_make_pkg(f"pkg{i}", depth=1) for i in range(3)]
        root = _make_root(children)

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), truncate_after_children=5
        )
        assert resp.tree.children_truncated is False
        assert resp.tree.child_count is None
        assert len(resp.tree.children) == 3

    def test_truncation_with_default_sort(self):
        """Truncation uses default sort (name+version), not risk-first."""
        a = _make_pkg("alpha", depth=1, risk_score=10)
        b = _make_pkg("bravo", depth=1, risk_score=90)
        c = _make_pkg("charlie", depth=1, risk_score=50)
        root = _make_root([c, a, b])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), truncate_after_children=2
        )
        # Default sort: name ASC → alpha, bravo, charlie → keep first 2
        names = [ch.name for ch in resp.tree.children]
        assert names == ["alpha", "bravo"]

    def test_truncation_applied_recursively(self):
        gc1 = _make_pkg("gc1", depth=2)
        gc2 = _make_pkg("gc2", depth=2)
        gc3 = _make_pkg("gc3", depth=2)
        child = _make_pkg("child", depth=1, children=[gc1, gc2, gc3])
        root = _make_root([child])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(), truncate_after_children=2
        )
        inner = resp.tree.children[0]
        assert len(inner.children) == 2
        assert inner.children_truncated is True
        assert inner.child_count == 3


# ---------------------------------------------------------------------------
# Summary metrics tests
# ---------------------------------------------------------------------------


class TestSummaryMetrics:
    def test_metrics_reflect_filtered_tree(self):
        """Metrics should reflect the filtered tree, not the canonical tree."""
        high = _make_pkg("high", depth=1, risk_score=90)
        low = _make_pkg("low", depth=1, risk_score=10)
        root = _make_root([high, low])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(high_risk_only=True)
        )
        assert resp.summary_metrics.total_dependencies == 1
        assert resp.summary_metrics.high_risk_count == 1

    def test_preserved_ancestors_count_in_totals_not_high_risk(self):
        """Preserved ancestors count in totals but NOT in high_risk_count."""
        high_gc = _make_pkg("risky", depth=2, risk_score=85)
        low_parent = _make_pkg("safe", depth=1, risk_score=20, children=[high_gc])
        root = _make_root([low_parent])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(high_risk_only=True)
        )
        # total_dependencies = 2 (safe + risky)
        assert resp.summary_metrics.total_dependencies == 2
        # high_risk_count = 1 (only risky, not safe)
        assert resp.summary_metrics.high_risk_count == 1
        # direct = 1 (safe), transitive = 1 (risky)
        assert resp.summary_metrics.direct_dependencies == 1
        assert resp.summary_metrics.transitive_dependencies == 1


# ---------------------------------------------------------------------------
# Copy-safety tests
# ---------------------------------------------------------------------------


class TestCopySafety:
    def test_filters_do_not_mutate_original(self):
        gc = _make_pkg("gc", depth=2, risk_score=10)
        child = _make_pkg("child", depth=1, risk_score=30, children=[gc])
        root = _make_root([child])
        original_children_count = len(root.children[0].children)

        svc = _service()
        svc._transform_for_response(
            root, "database", FilterConfig(direct_only=True)
        )
        # Original tree should still have the grandchild
        assert len(root.children[0].children) == original_children_count
        assert root.children[0].children[0].name == "gc"

    def test_sorting_does_not_mutate_original(self):
        c = _make_pkg("charlie", depth=1)
        a = _make_pkg("alpha", depth=1)
        b = _make_pkg("bravo", depth=1)
        root = _make_root([c, a, b])
        original_order = [ch.name for ch in root.children]

        svc = _service()
        svc._transform_for_response(
            root, "database", FilterConfig(), sort_by="name"
        )
        # Original order should be unchanged
        assert [ch.name for ch in root.children] == original_order

    def test_truncation_does_not_mutate_original(self):
        children = [_make_pkg(f"pkg{i}", depth=1) for i in range(5)]
        root = _make_root(children)
        original_count = len(root.children)

        svc = _service()
        svc._transform_for_response(
            root, "database", FilterConfig(), truncate_after_children=2
        )
        assert len(root.children) == original_count


# ---------------------------------------------------------------------------
# Ancestor preservation with tree-occurrence context
# ---------------------------------------------------------------------------


class TestAncestorPreservationTreeOccurrence:
    def test_two_branches_same_canonical_id_preserved_independently(self):
        """Two branches with same canonical ID should be preserved independently."""
        # Branch 1: child_a → shared_pkg (high risk)
        shared1 = _make_pkg("shared", version="1.0.0", depth=2, risk_score=85)
        child_a = _make_pkg("branch_a", depth=1, risk_score=20, children=[shared1])

        # Branch 2: child_b → shared_pkg (same canonical ID, high risk)
        shared2 = _make_pkg("shared", version="1.0.0", depth=2, risk_score=85)
        child_b = _make_pkg("branch_b", depth=1, risk_score=20, children=[shared2])

        root = _make_root([child_a, child_b])

        svc = _service()
        resp = svc._transform_for_response(
            root, "database", FilterConfig(high_risk_only=True)
        )
        # Both branches should be preserved (each has a high-risk descendant)
        assert len(resp.tree.children) == 2
        branch_names = sorted(c.name for c in resp.tree.children)
        assert branch_names == ["branch_a", "branch_b"]
        # Each branch should still have its shared child
        for branch in resp.tree.children:
            assert len(branch.children) == 1
            assert branch.children[0].name == "shared"
