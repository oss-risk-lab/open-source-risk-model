"""
Property-based tests for SummaryMetricsCalculator.

Feature: dependency-tree-view
Property 7: Summary Metrics Accuracy
Property 8: Riskiest Branch Identification

Validates: Requirements 3.1–3.7, 15.1–15.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from open_source_risk_model.tree.metrics import SummaryMetricsCalculator
from open_source_risk_model.tree.models import RiskMetadata, TreeNode
from open_source_risk_model.tree.tree_utils import count_nodes, walk_tree


# ======================================================================
# Strategies
# ======================================================================

risk_scores = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)

ecosystems = st.sampled_from(["npm", "pypi", "maven", "go"])

package_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=12,
).filter(lambda s: s[0].isalpha())

vuln_counts = st.integers(min_value=0, max_value=10)


def _classify(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 30:
        return "low"
    if score <= 70:
        return "medium"
    return "high"



def _make_risk_metadata(
    risk_score: float | None,
    vulnerability_count: int = 0,
) -> RiskMetadata:
    return RiskMetadata(
        risk_score=risk_score,
        risk_level=_classify(risk_score),
        vulnerability_count=vulnerability_count,
        score_source="repo_graph" if risk_score is not None else "unavailable",
        score_completeness="full" if risk_score is not None else "missing",
    )


@st.composite
def tree_strategy(draw, max_depth=4, max_children=4):
    """Generate a random dependency tree with a repository root.

    Produces trees with varying depths, branching factors, and risk scores.
    Each node gets a random risk_score (or None) and vulnerability_count.
    """
    counter = [0]

    def build_node(depth: int) -> TreeNode:
        counter[0] += 1
        name = f"pkg{counter[0]}"
        eco = draw(ecosystems)
        version = f"{draw(st.integers(min_value=0, max_value=9))}.{draw(st.integers(min_value=0, max_value=9))}.{draw(st.integers(min_value=0, max_value=9))}"
        score = draw(risk_scores)
        vulns = draw(vuln_counts)

        dep_type = "direct" if depth == 1 else "transitive"

        children = []
        if depth < max_depth:
            num_children = draw(st.integers(min_value=0, max_value=max_children))
            for _ in range(num_children):
                children.append(build_node(depth + 1))

        return TreeNode(
            id=f"pkg:{eco}/{name}@{version}",
            node_type="package",
            name=name,
            version=version,
            depth=depth,
            dependency_type=dep_type,
            ecosystem=eco,
            risk_metadata=_make_risk_metadata(score, vulns),
            children=children,
        )

    # Build root
    num_direct = draw(st.integers(min_value=0, max_value=5))
    direct_children = [build_node(1) for _ in range(num_direct)]

    root = TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        depth=0,
        dependency_type="direct",
        children=direct_children,
    )
    return root


# ======================================================================
# Property 7: Summary Metrics Accuracy
# ======================================================================


calculator = SummaryMetricsCalculator()


class TestSummaryMetricsAccuracy:
    """
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 15.1, 15.2, 15.3, 15.4**

    Property 7: Summary Metrics Accuracy — For any dependency tree:
      - total_dependencies = direct_dependencies + transitive_dependencies
      - total_dependencies = count_nodes(root) - 1
      - high_risk_count = count of nodes with risk_score > 70
      - vulnerable_count = count of nodes with vulnerability_count > 0
      - max_depth = depth of deepest node
    """

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_total_equals_direct_plus_transitive(self, root):
        """**Validates: Requirements 3.1, 3.2, 15.1**

        total_dependencies must equal direct_dependencies + transitive_dependencies.
        """
        metrics = calculator.calculate_metrics(root, [])
        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_total_equals_node_count_minus_one(self, root):
        """**Validates: Requirements 3.1, 3.2, 15.1**

        total_dependencies must equal count_nodes(root) - 1 (excluding root).
        """
        metrics = calculator.calculate_metrics(root, [])
        assert metrics.total_dependencies == count_nodes(root) - 1

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_direct_count_matches_depth_1_nodes(self, root):
        """**Validates: Requirements 3.1**

        direct_dependencies must equal the number of depth-1 nodes.
        """
        metrics = calculator.calculate_metrics(root, [])
        depth_1_count = sum(1 for n in walk_tree(root) if n.depth == 1)
        assert metrics.direct_dependencies == depth_1_count

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_transitive_count_matches_depth_gte_2_nodes(self, root):
        """**Validates: Requirements 3.2**

        transitive_dependencies must equal the number of nodes at depth >= 2.
        """
        metrics = calculator.calculate_metrics(root, [])
        deep_count = sum(1 for n in walk_tree(root) if n.depth >= 2)
        assert metrics.transitive_dependencies == deep_count

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_high_risk_count_matches_nodes_above_70(self, root):
        """**Validates: Requirements 3.3, 15.2**

        high_risk_count must equal the count of non-root nodes with risk_score > 70.
        """
        metrics = calculator.calculate_metrics(root, [])
        expected = sum(
            1
            for n in walk_tree(root)
            if n.depth > 0
            and n.risk_metadata is not None
            and n.risk_metadata.risk_score is not None
            and n.risk_metadata.risk_score > 70
        )
        assert metrics.high_risk_count == expected

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_vulnerable_count_matches_nodes_with_vulns(self, root):
        """**Validates: Requirements 3.4, 15.3**

        vulnerable_count must equal the count of non-root nodes with vulnerability_count > 0.
        """
        metrics = calculator.calculate_metrics(root, [])
        expected = sum(
            1
            for n in walk_tree(root)
            if n.depth > 0
            and n.risk_metadata is not None
            and n.risk_metadata.vulnerability_count > 0
        )
        assert metrics.vulnerable_count == expected

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_max_depth_matches_deepest_node(self, root):
        """**Validates: Requirements 3.5, 15.4**

        max_depth must equal the depth of the deepest node in the tree.
        """
        metrics = calculator.calculate_metrics(root, [])
        expected_max = max(n.depth for n in walk_tree(root))
        assert metrics.max_depth == expected_max

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_metrics_included_in_summary(self, root):
        """**Validates: Requirements 3.7**

        All calculated metrics must be present in the SummaryMetrics object.
        """
        metrics = calculator.calculate_metrics(root, [])
        assert hasattr(metrics, "total_dependencies")
        assert hasattr(metrics, "direct_dependencies")
        assert hasattr(metrics, "transitive_dependencies")
        assert hasattr(metrics, "high_risk_count")
        assert hasattr(metrics, "vulnerable_count")
        assert hasattr(metrics, "max_depth")
        assert hasattr(metrics, "riskiest_branch")
        assert hasattr(metrics, "filters_applied")


# ======================================================================
# Property 8: Riskiest Branch Identification
# ======================================================================


class TestRiskiestBranchIdentification:
    """
    **Validates: Requirements 3.6, 15.5**

    Property 8: Riskiest Branch Identification — For any dependency tree,
    the riskiest branch cumulative score >= any individual node's risk_score.
    Nodes with risk_score=None contribute 0 to cumulative score.
    """

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_cumulative_risk_gte_any_individual_score(self, root):
        """**Validates: Requirements 3.6, 15.5**

        The riskiest branch cumulative_risk must be >= the risk_score
        of any individual node in the tree.
        """
        metrics = calculator.calculate_metrics(root, [])

        if not root.children:
            # Root-only tree has no riskiest branch
            assert metrics.riskiest_branch is None
            return

        assert metrics.riskiest_branch is not None
        cumulative = metrics.riskiest_branch["cumulative_risk"]

        # Collect all individual risk scores (None → 0)
        for node in walk_tree(root):
            if node.risk_metadata is not None and node.risk_metadata.risk_score is not None:
                assert cumulative >= node.risk_metadata.risk_score, (
                    f"Cumulative risk {cumulative} < individual score "
                    f"{node.risk_metadata.risk_score} on node {node.id}"
                )

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_riskiest_branch_none_for_root_only(self, root):
        """**Validates: Requirements 3.6**

        When the tree has no children (root only), riskiest_branch is None.
        """
        # Force root-only by clearing children
        root.children = []
        metrics = calculator.calculate_metrics(root, [])
        assert metrics.riskiest_branch is None

    @given(root=tree_strategy(max_depth=3, max_children=3))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_riskiest_branch_path_starts_with_root(self, root):
        """**Validates: Requirements 3.6**

        When riskiest_branch exists, its path must start with the root node ID.
        """
        metrics = calculator.calculate_metrics(root, [])

        if metrics.riskiest_branch is None:
            return

        path = metrics.riskiest_branch["path"]
        assert len(path) >= 1
        assert path[0] == root.id

    @given(root=tree_strategy(max_depth=3, max_children=3))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_riskiest_branch_cumulative_is_non_negative(self, root):
        """**Validates: Requirements 3.6**

        Cumulative risk score must be non-negative since all risk_scores
        are in [0, 100] and None contributes 0.
        """
        metrics = calculator.calculate_metrics(root, [])

        if metrics.riskiest_branch is None:
            return

        assert metrics.riskiest_branch["cumulative_risk"] >= 0.0


# ======================================================================
# Property 26: Filtered Metrics Accuracy
# ======================================================================


def _filter_tree_by_depth(root: TreeNode, max_depth: int) -> TreeNode:
    """Simulate depth filtering: remove nodes deeper than max_depth.

    Returns a deep-cloned tree with nodes beyond max_depth removed.
    Sets children_truncated=True on boundary nodes that had children.
    """
    from open_source_risk_model.tree.tree_utils import clone_tree

    cloned = clone_tree(root)

    def _prune(node: TreeNode) -> None:
        if node.depth >= max_depth:
            if node.children:
                node.child_count = len(node.children)
                node.children_truncated = True
                node.children = []
        else:
            for child in node.children:
                _prune(child)

    _prune(cloned)
    return cloned


def _filter_tree_high_risk_only(root: TreeNode) -> TreeNode:
    """Simulate high_risk_only filtering: keep nodes with risk_score > 70
    and their ancestors from root.

    Returns a deep-cloned tree with non-matching leaf branches removed.
    """
    from open_source_risk_model.tree.tree_utils import clone_tree

    cloned = clone_tree(root)

    def _has_high_risk_descendant(node: TreeNode) -> bool:
        """Check if node or any descendant has risk_score > 70."""
        if (
            node.risk_metadata is not None
            and node.risk_metadata.risk_score is not None
            and node.risk_metadata.risk_score > 70
            and node.depth > 0  # root doesn't count as matching
        ):
            return True
        return any(_has_high_risk_descendant(c) for c in node.children)

    def _prune_non_matching(node: TreeNode) -> None:
        """Remove children that don't lead to high-risk nodes."""
        node.children = [c for c in node.children if _has_high_risk_descendant(c)]
        for child in node.children:
            _prune_non_matching(child)

    _prune_non_matching(cloned)
    return cloned


class TestFilteredMetricsAccuracy:
    """
    **Validates: Requirements 15.6**

    Property 26: Filtered Metrics Accuracy — For any tree with filters applied,
    the summary_metrics SHALL reflect only the filtered subset of nodes,
    not the complete unfiltered tree.
    """

    @given(root=tree_strategy(), max_depth=st.integers(min_value=1, max_value=4))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_depth_filtered_metrics_match_filtered_tree(self, root, max_depth):
        """**Validates: Requirements 15.6**

        After depth filtering, metrics must reflect only the remaining nodes.
        total_dependencies = count of non-root nodes in filtered tree.
        """
        filtered = _filter_tree_by_depth(root, max_depth)
        metrics = calculator.calculate_metrics(filtered, ["max_depth"])

        # Count non-root nodes in filtered tree
        all_nodes = list(walk_tree(filtered))
        non_root = [n for n in all_nodes if n.depth > 0]

        assert metrics.total_dependencies == len(non_root)
        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies

        # All nodes must be at depth <= max_depth
        for n in all_nodes:
            assert n.depth <= max_depth

        # max_depth in metrics must match deepest node in filtered tree
        if non_root:
            expected_max = max(n.depth for n in non_root)
        else:
            expected_max = 0
        assert metrics.max_depth == expected_max

        # high_risk and vulnerable counts must match filtered tree
        expected_high_risk = sum(
            1 for n in non_root
            if n.risk_metadata is not None
            and n.risk_metadata.risk_score is not None
            and n.risk_metadata.risk_score > 70
        )
        assert metrics.high_risk_count == expected_high_risk

        expected_vulnerable = sum(
            1 for n in non_root
            if n.risk_metadata is not None
            and n.risk_metadata.vulnerability_count > 0
        )
        assert metrics.vulnerable_count == expected_vulnerable

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_high_risk_filtered_metrics_match_filtered_tree(self, root):
        """**Validates: Requirements 15.6**

        After high_risk_only filtering, metrics must reflect only the
        remaining nodes. Preserved ancestors count in totals but NOT
        in high_risk_count unless they independently qualify.
        """
        filtered = _filter_tree_high_risk_only(root)
        metrics = calculator.calculate_metrics(filtered, ["high_risk_only"])

        all_nodes = list(walk_tree(filtered))
        non_root = [n for n in all_nodes if n.depth > 0]

        # total must match filtered node count
        assert metrics.total_dependencies == len(non_root)
        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies

        # high_risk_count must match nodes with risk_score > 70 in filtered tree
        expected_high_risk = sum(
            1 for n in non_root
            if n.risk_metadata is not None
            and n.risk_metadata.risk_score is not None
            and n.risk_metadata.risk_score > 70
        )
        assert metrics.high_risk_count == expected_high_risk

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_filtered_metrics_differ_from_unfiltered_when_nodes_removed(self, root):
        """**Validates: Requirements 15.6**

        When filtering removes nodes, the filtered metrics must differ
        from unfiltered metrics (unless the filter happens to keep all nodes).
        """
        unfiltered_metrics = calculator.calculate_metrics(root, [])
        filtered = _filter_tree_by_depth(root, 1)
        filtered_metrics = calculator.calculate_metrics(filtered, ["max_depth"])

        # Count nodes removed
        unfiltered_count = count_nodes(root)
        filtered_count = count_nodes(filtered)

        if filtered_count < unfiltered_count:
            # Some nodes were removed, so total_dependencies must be smaller
            assert filtered_metrics.total_dependencies < unfiltered_metrics.total_dependencies
        else:
            # No nodes removed, metrics should match
            assert filtered_metrics.total_dependencies == unfiltered_metrics.total_dependencies

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_filters_applied_list_populated(self, root):
        """**Validates: Requirements 15.6**

        When filters are applied, the filters_applied list in metrics
        must contain the filter names.
        """
        filters = ["high_risk_only", "max_depth"]
        metrics = calculator.calculate_metrics(root, filters)
        assert metrics.filters_applied == filters
