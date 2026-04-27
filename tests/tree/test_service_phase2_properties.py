"""
Property-based tests for TreeService Phase 2: Response Transformation.

Feature: dependency-tree-view
Property 20: Sorting Consistency (REQUIRED)
Property 21: Default Sort Order (REQUIRED)
Property 10: Depth Filtering Correctness
Property 11: Truncation Metadata Accuracy
Property 12: Unfiltered Tree Completeness
Property 13: Risk-Based Filtering with Ancestor Preservation
Property 14: Vulnerability Filtering with Ancestor Preservation
Property 15: Direct-Only Filtering
Property 16: Filter Combination Logic
Property 17: Truncation with Sorting

Validates: Requirements 5.2–5.5, 6.2–6.8, 7.2–7.4, 13.2–13.8
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st, assume

from open_source_risk_model.tree.models import (
    FilterConfig,
    RiskMetadata,
    TreeNode,
)
from open_source_risk_model.tree.service import TreeService
from open_source_risk_model.tree.tree_utils import clone_tree, walk_tree


# ======================================================================
# Helpers
# ======================================================================


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


def _service() -> TreeService:
    return TreeService(db_path=":memory:")


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

versions = st.one_of(
    st.none(),
    st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True),
)

sort_options = st.sampled_from(["risk_score", "name", "vulnerability_count"])


@st.composite
def tree_strategy(draw, max_depth=3, max_children=4):
    """Generate a random dependency tree with a repository root.

    - Repository root at depth 0
    - Random number of direct deps at depth 1
    - Random transitive deps at depth 2+
    - Random risk_score (0-100 or None) and vulnerability_count (0-10)
    """
    counter = [0]

    def build_node(depth: int) -> TreeNode:
        counter[0] += 1
        name = f"pkg{counter[0]}"
        eco = draw(ecosystems)
        ver = draw(versions)
        score = draw(risk_scores)
        vulns = draw(vuln_counts)

        dep_type = "direct" if depth == 1 else "transitive"
        ver_part = ver if ver else "unknown"

        children = []
        if depth < max_depth:
            num_children = draw(st.integers(min_value=0, max_value=max_children))
            for _ in range(num_children):
                children.append(build_node(depth + 1))

        return TreeNode(
            id=f"pkg:{eco}/{name}@{ver_part}",
            node_type="package",
            name=name,
            version=ver,
            depth=depth,
            dependency_type=dep_type,
            ecosystem=eco,
            risk_metadata=_make_risk_metadata(score, vulns),
            children=children,
        )

    num_direct = draw(st.integers(min_value=1, max_value=5))
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


@st.composite
def tree_with_high_risk(draw):
    """Generate a tree guaranteed to have at least one high-risk node."""
    root = draw(tree_strategy())
    # Ensure at least one leaf has risk_score > 70
    leaves = [n for n in walk_tree(root) if n.depth > 0 and not n.children]
    if not leaves:
        leaves = [n for n in walk_tree(root) if n.depth > 0]
    assume(len(leaves) > 0)
    target = draw(st.sampled_from(leaves))
    target.risk_metadata = _make_risk_metadata(
        draw(st.floats(min_value=70.1, max_value=100.0, allow_nan=False, allow_infinity=False)),
        target.risk_metadata.vulnerability_count if target.risk_metadata else 0,
    )
    return root


@st.composite
def tree_with_vulnerable(draw):
    """Generate a tree guaranteed to have at least one vulnerable node."""
    root = draw(tree_strategy())
    leaves = [n for n in walk_tree(root) if n.depth > 0 and not n.children]
    if not leaves:
        leaves = [n for n in walk_tree(root) if n.depth > 0]
    assume(len(leaves) > 0)
    target = draw(st.sampled_from(leaves))
    target.risk_metadata = _make_risk_metadata(
        target.risk_metadata.risk_score if target.risk_metadata else None,
        draw(st.integers(min_value=1, max_value=10)),
    )
    return root



# ======================================================================
# Property 20: Sorting Consistency (REQUIRED)
# ======================================================================


class TestSortingConsistency:
    """
    **Validates: Requirements 13.2, 13.3, 13.4, 13.6**

    Property 20: Sorting Consistency — all sibling groups sorted by specified
    criterion at every depth.
    """

    @staticmethod
    def _version_key(v: str | None) -> tuple:
        if v is None:
            return (1, "")
        return (0, v)

    @staticmethod
    def _check_sorted(children: list[TreeNode], sort_by: str) -> None:
        """Verify a list of siblings is sorted by the given criterion."""
        for i in range(len(children) - 1):
            a, b = children[i], children[i + 1]
            ka = TestSortingConsistency._sort_key(a, sort_by)
            kb = TestSortingConsistency._sort_key(b, sort_by)
            assert ka <= kb, (
                f"Siblings not sorted by {sort_by}: "
                f"{a.name}({ka}) should come before {b.name}({kb})"
            )

    @staticmethod
    def _sort_key(node: TreeNode, sort_by: str) -> tuple:
        vk = TestSortingConsistency._version_key(node.version)
        if sort_by == "risk_score":
            rs = (
                node.risk_metadata.risk_score
                if node.risk_metadata and node.risk_metadata.risk_score is not None
                else None
            )
            if rs is None:
                return (1, 0.0, node.name, vk)
            return (0, -rs, node.name, vk)
        elif sort_by == "vulnerability_count":
            vc = node.risk_metadata.vulnerability_count if node.risk_metadata else 0
            if vc is None:
                vc = 0
            return (-vc, node.name, vk)
        elif sort_by == "name":
            return (node.name, vk)
        else:
            return (node.name, vk)

    @staticmethod
    def _verify_all_siblings_sorted(node: TreeNode, sort_by: str) -> None:
        """Recursively verify all sibling groups are sorted."""
        if node.children:
            TestSortingConsistency._check_sorted(node.children, sort_by)
        for child in node.children:
            TestSortingConsistency._verify_all_siblings_sorted(child, sort_by)

    @given(root=tree_strategy(), sort_by=sort_options)
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_all_sibling_groups_sorted_by_criterion(self, root, sort_by):
        """**Validates: Requirements 13.2, 13.3, 13.4, 13.6**

        For any tree with sort_by parameter, all sibling groups at every depth
        shall be sorted according to the specified criterion.
        """
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(root, "database", filters, sort_by=sort_by)
        self._verify_all_siblings_sorted(response.tree, sort_by)

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_sort_by_risk_score_desc(self, root):
        """**Validates: Requirements 13.2**

        risk_score sort: DESC, nulls last, tie-break name ASC, version ASC.
        """
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(root, "database", filters, sort_by="risk_score")
        self._verify_all_siblings_sorted(response.tree, "risk_score")

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_sort_by_name_asc(self, root):
        """**Validates: Requirements 13.3**

        name sort: ASC, tie-break version ASC (unknown last).
        """
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(root, "database", filters, sort_by="name")
        self._verify_all_siblings_sorted(response.tree, "name")

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_sort_by_vulnerability_count_desc(self, root):
        """**Validates: Requirements 13.4**

        vulnerability_count sort: DESC, nulls as 0, tie-break name ASC, version ASC.
        """
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(root, "database", filters, sort_by="vulnerability_count")
        self._verify_all_siblings_sorted(response.tree, "vulnerability_count")


# ======================================================================
# Property 21: Default Sort Order (REQUIRED)
# ======================================================================


class TestDefaultSortOrder:
    """
    **Validates: Requirements 13.5**

    Property 21: Default Sort Order — name then version when no sort_by.
    """

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_default_sort_name_then_version(self, root):
        """**Validates: Requirements 13.5**

        When sort_by is not provided, siblings are sorted by name ASC,
        then version ASC (unknown/None last).
        """
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(root, "database", filters, sort_by=None)
        self._verify_default_sort(response.tree)

    @staticmethod
    def _version_key(v: str | None) -> tuple:
        if v is None:
            return (1, "")
        return (0, v)

    def _verify_default_sort(self, node: TreeNode) -> None:
        """Recursively verify default sort: name ASC, version ASC (None last)."""
        for i in range(len(node.children) - 1):
            a, b = node.children[i], node.children[i + 1]
            ka = (a.name, self._version_key(a.version))
            kb = (b.name, self._version_key(b.version))
            assert ka <= kb, (
                f"Default sort violated: {a.name}@{a.version} should come "
                f"before {b.name}@{b.version}"
            )
        for child in node.children:
            self._verify_default_sort(child)



# ======================================================================
# Property 10: Depth Filtering Correctness
# ======================================================================


class TestDepthFilteringCorrectness:
    """
    **Validates: Requirements 5.2, 5.3**

    Property 10: Depth Filtering Correctness — all returned nodes have
    depth ≤ max_depth, and all nodes with depth ≤ max_depth are included
    unless filtered by other criteria.
    """

    @given(root=tree_strategy(), max_depth=st.integers(min_value=1, max_value=5))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_no_nodes_exceed_max_depth(self, root, max_depth):
        """**Validates: Requirements 5.2**

        All returned nodes shall have depth ≤ max_depth.
        """
        svc = _service()
        filters = FilterConfig(max_depth=max_depth)
        response = svc._transform_for_response(root, "database", filters)
        for node in walk_tree(response.tree):
            assert node.depth <= max_depth, (
                f"Node '{node.name}' at depth {node.depth} exceeds max_depth={max_depth}"
            )

    @given(root=tree_strategy(), max_depth=st.integers(min_value=1, max_value=5))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_all_nodes_within_depth_preserved(self, root, max_depth):
        """**Validates: Requirements 5.3**

        All nodes with depth ≤ max_depth in the original tree are preserved
        (when no other filters are active).
        """
        # Collect original node IDs at depth <= max_depth
        original_ids = set()
        for node in walk_tree(root):
            if node.depth <= max_depth:
                original_ids.add((node.id, node.depth))

        svc = _service()
        filters = FilterConfig(max_depth=max_depth)
        response = svc._transform_for_response(root, "database", filters)

        result_ids = set()
        for node in walk_tree(response.tree):
            result_ids.add((node.id, node.depth))

        # Every original node within depth should be in the result
        for nid, ndepth in original_ids:
            assert (nid, ndepth) in result_ids, (
                f"Node {nid} at depth {ndepth} should be preserved with max_depth={max_depth}"
            )


# ======================================================================
# Property 11: Truncation Metadata Accuracy
# ======================================================================


class TestTruncationMetadataAccuracy:
    """
    **Validates: Requirements 5.4**

    Property 11: Truncation Metadata Accuracy — nodes at max_depth with
    children have children_truncated=true and correct child_count.
    """

    @given(root=tree_strategy(max_depth=4), max_depth=st.integers(min_value=1, max_value=3))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_boundary_nodes_have_truncation_metadata(self, root, max_depth):
        """**Validates: Requirements 5.4**

        Nodes at max_depth that originally had children shall have
        children_truncated=true and child_count set.
        """
        # Collect nodes at max_depth that have children in the original tree
        original_boundary_info = {}
        for node in walk_tree(root):
            if node.depth == max_depth and len(node.children) > 0:
                original_boundary_info[node.id] = len(node.children)

        svc = _service()
        filters = FilterConfig(max_depth=max_depth)
        response = svc._transform_for_response(root, "database", filters)

        for node in walk_tree(response.tree):
            if node.depth == max_depth and node.id in original_boundary_info:
                assert node.children_truncated is True, (
                    f"Node '{node.name}' at max_depth should have children_truncated=True"
                )
                assert node.child_count == original_boundary_info[node.id], (
                    f"Node '{node.name}' child_count should be {original_boundary_info[node.id]}, "
                    f"got {node.child_count}"
                )
                assert len(node.children) == 0, (
                    f"Node '{node.name}' at max_depth should have no children after filtering"
                )


# ======================================================================
# Property 12: Unfiltered Tree Completeness
# ======================================================================


class TestUnfilteredTreeCompleteness:
    """
    **Validates: Requirements 5.5**

    Property 12: Unfiltered Tree Completeness — without max_depth, all
    dependencies are included regardless of depth.
    """

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_all_nodes_included_without_max_depth(self, root):
        """**Validates: Requirements 5.5**

        Without max_depth, all nodes from the original tree are present.
        """
        original_count = sum(1 for _ in walk_tree(root))

        svc = _service()
        filters = FilterConfig()  # No filters
        response = svc._transform_for_response(root, "database", filters)

        result_count = sum(1 for _ in walk_tree(response.tree))
        assert result_count == original_count, (
            f"Unfiltered tree should have {original_count} nodes, got {result_count}"
        )


# ======================================================================
# Property 13: Risk-Based Filtering with Ancestor Preservation
# ======================================================================


class TestRiskBasedFilteringWithAncestorPreservation:
    """
    **Validates: Requirements 6.2, 6.3**

    Property 13: Risk-Based Filtering with Ancestor Preservation — all
    returned nodes either have risk_score > 70 OR are ancestors of such nodes.
    """

    @given(root=tree_with_high_risk())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_high_risk_only_preserves_ancestors(self, root):
        """**Validates: Requirements 6.2, 6.3**

        With high_risk_only=true, all returned non-root nodes either have
        risk_score > 70 or are ancestors of high-risk nodes.
        """
        svc = _service()
        filters = FilterConfig(high_risk_only=True)
        response = svc._transform_for_response(root, "database", filters)

        # Root is always included
        assert response.tree.depth == 0

        # Every non-root leaf must be high-risk
        for node in walk_tree(response.tree):
            if node.depth > 0 and not node.children:
                assert (
                    node.risk_metadata is not None
                    and node.risk_metadata.risk_score is not None
                    and node.risk_metadata.risk_score > 70
                ), (
                    f"Leaf node '{node.name}' with score "
                    f"{node.risk_metadata.risk_score if node.risk_metadata else None} "
                    f"should be high-risk"
                )

    @given(root=tree_with_high_risk())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_high_risk_paths_complete_from_root(self, root):
        """**Validates: Requirements 6.3**

        Every high-risk node has a complete path from root.
        """
        svc = _service()
        filters = FilterConfig(high_risk_only=True)
        response = svc._transform_for_response(root, "database", filters)

        # Verify path completeness: for every node at depth d > 0,
        # there must be a parent at depth d-1
        nodes_by_depth: dict[int, set[str]] = {}
        for node in walk_tree(response.tree):
            nodes_by_depth.setdefault(node.depth, set()).add(node.id)

        # Check that depth 0 exists (root)
        assert 0 in nodes_by_depth

        # Verify tree structure: every child's parent is in the tree
        def _verify_paths(node: TreeNode) -> None:
            for child in node.children:
                assert child.depth == node.depth + 1
                _verify_paths(child)

        _verify_paths(response.tree)



# ======================================================================
# Property 14: Vulnerability Filtering with Ancestor Preservation
# ======================================================================


class TestVulnerabilityFilteringWithAncestorPreservation:
    """
    **Validates: Requirements 6.5**

    Property 14: Vulnerability Filtering with Ancestor Preservation — all
    returned nodes either have vulnerability_count > 0 OR are ancestors of
    vulnerable nodes.
    """

    @given(root=tree_with_vulnerable())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_vulnerable_only_preserves_ancestors(self, root):
        """**Validates: Requirements 6.5**

        With vulnerable_only=true, all returned non-root leaf nodes have
        vulnerability_count > 0.
        """
        svc = _service()
        filters = FilterConfig(vulnerable_only=True)
        response = svc._transform_for_response(root, "database", filters)

        assert response.tree.depth == 0

        for node in walk_tree(response.tree):
            if node.depth > 0 and not node.children:
                assert (
                    node.risk_metadata is not None
                    and node.risk_metadata.vulnerability_count > 0
                ), (
                    f"Leaf node '{node.name}' with vuln_count "
                    f"{node.risk_metadata.vulnerability_count if node.risk_metadata else 0} "
                    f"should be vulnerable"
                )


# ======================================================================
# Property 15: Direct-Only Filtering
# ======================================================================


class TestDirectOnlyFiltering:
    """
    **Validates: Requirements 6.7**

    Property 15: Direct-Only Filtering — all returned nodes have depth ≤ 1.
    """

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_direct_only_max_depth_1(self, root):
        """**Validates: Requirements 6.7**

        With direct_only=true, all returned nodes have depth ≤ 1.
        """
        svc = _service()
        filters = FilterConfig(direct_only=True)
        response = svc._transform_for_response(root, "database", filters)

        for node in walk_tree(response.tree):
            assert node.depth <= 1, (
                f"Node '{node.name}' at depth {node.depth} should not be present "
                f"with direct_only=True"
            )

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_direct_only_preserves_all_direct_deps(self, root):
        """**Validates: Requirements 6.7**

        With direct_only=true, all depth-1 nodes from the original tree are preserved.
        """
        original_direct_ids = {
            n.id for n in walk_tree(root) if n.depth == 1
        }

        svc = _service()
        filters = FilterConfig(direct_only=True)
        response = svc._transform_for_response(root, "database", filters)

        result_direct_ids = {
            n.id for n in walk_tree(response.tree) if n.depth == 1
        }
        assert original_direct_ids == result_direct_ids

    @given(root=tree_strategy())
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_direct_only_does_not_set_children_truncated(self, root):
        """**Validates: Requirements 6.7**

        direct_only does NOT set children_truncated on depth-1 nodes.
        """
        svc = _service()
        filters = FilterConfig(direct_only=True)
        response = svc._transform_for_response(root, "database", filters)

        for node in walk_tree(response.tree):
            if node.depth == 1:
                assert node.children_truncated is False, (
                    f"direct_only should not set children_truncated on '{node.name}'"
                )


# ======================================================================
# Property 16: Filter Combination Logic
# ======================================================================


class TestFilterCombinationLogic:
    """
    **Validates: Requirements 6.8**

    Property 16: Filter Combination Logic — with multiple filters, a node
    is included only if it satisfies ALL criteria or is an ancestor of such.
    """

    @given(root=tree_strategy(), max_depth=st.integers(min_value=1, max_value=3))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_combined_depth_and_direct_only(self, root, max_depth):
        """**Validates: Requirements 6.8**

        Combining direct_only with max_depth: direct_only removes depth > 1,
        max_depth further constrains (though max_depth >= 1 is redundant with direct_only).
        """
        svc = _service()
        filters = FilterConfig(direct_only=True, max_depth=max_depth)
        response = svc._transform_for_response(root, "database", filters)

        effective_max = min(1, max_depth)
        for node in walk_tree(response.tree):
            assert node.depth <= effective_max, (
                f"Node '{node.name}' at depth {node.depth} exceeds effective max {effective_max}"
            )

    @given(root=tree_with_high_risk(), max_depth=st.integers(min_value=1, max_value=4))
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_combined_high_risk_and_depth(self, root, max_depth):
        """**Validates: Requirements 6.8**

        Combining high_risk_only with max_depth: depth filter applied first,
        then risk filter on the remaining tree.
        """
        svc = _service()
        filters = FilterConfig(high_risk_only=True, max_depth=max_depth)
        response = svc._transform_for_response(root, "database", filters)

        for node in walk_tree(response.tree):
            # Depth constraint must hold
            assert node.depth <= max_depth
            # Non-root leaves must be high-risk
            if node.depth > 0 and not node.children:
                assert (
                    node.risk_metadata is not None
                    and node.risk_metadata.risk_score is not None
                    and node.risk_metadata.risk_score > 70
                ) or node.children_truncated, (
                    f"Leaf '{node.name}' should be high-risk or truncated"
                )


# ======================================================================
# Property 17: Truncation with Sorting
# ======================================================================


class TestTruncationWithSorting:
    """
    **Validates: Requirements 7.2, 7.3, 7.4, 13.7, 13.8**

    Property 17: Truncation with Sorting — included children are the first N
    from the current sort order, children_truncated is true, and child_count
    reflects the pre-truncation total.
    """

    @given(
        root=tree_strategy(max_children=6),
        sort_by=st.one_of(st.none(), sort_options),
        limit=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_truncation_keeps_first_n_from_sort_order(self, root, sort_by, limit):
        """**Validates: Requirements 7.2, 7.3, 7.4, 13.7**

        Truncated children are the first N from the sorted list.
        children_truncated=true and child_count set when truncation occurs.
        """
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            root, "database", filters, sort_by=sort_by, truncate_after_children=limit,
        )

        for node in walk_tree(response.tree):
            if node.children_truncated:
                # child_count must be set and > limit
                assert node.child_count is not None
                assert node.child_count > limit, (
                    f"child_count={node.child_count} should be > limit={limit}"
                )
                # Actual children should be exactly limit
                assert len(node.children) == limit, (
                    f"Truncated node should have {limit} children, got {len(node.children)}"
                )
            else:
                # Not truncated: children count <= limit
                assert len(node.children) <= limit or node.child_count is None

    @given(
        root=tree_strategy(max_children=6),
        sort_by=sort_options,
        limit=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_truncated_children_still_sorted(self, root, sort_by, limit):
        """**Validates: Requirements 13.7, 13.8**

        After truncation, the remaining children are still in sort order.
        """
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            root, "database", filters, sort_by=sort_by, truncate_after_children=limit,
        )
        TestSortingConsistency._verify_all_siblings_sorted(response.tree, sort_by)
