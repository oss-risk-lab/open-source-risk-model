"""Unit tests for tree traversal and manipulation utilities."""

import pytest

from open_source_risk_model.tree.models import TreeNode
from open_source_risk_model.tree.tree_utils import (
    clone_tree,
    collect_nodes,
    count_nodes,
    map_tree,
    walk_tree,
)


def _build_sample_tree():
    """Build a sample tree for testing.

    Structure:
        root (depth=0)
        ├── A (depth=1)
        │   ├── C (depth=2)
        │   └── D (depth=2)
        └── B (depth=1)
            └── E (depth=2)
    """
    c = TreeNode(id="pkg:npm/c@1.0", name="c", version="1.0", depth=2, dependency_type="transitive")
    d = TreeNode(id="pkg:npm/d@2.0", name="d", version="2.0", depth=2, dependency_type="transitive")
    e = TreeNode(id="pkg:npm/e@1.0", name="e", version="1.0", depth=2, dependency_type="transitive")
    a = TreeNode(id="pkg:npm/a@1.0", name="a", version="1.0", depth=1, children=[c, d])
    b = TreeNode(id="pkg:npm/b@1.0", name="b", version="1.0", depth=1, children=[e])
    root = TreeNode(
        id="owner/repo", node_type="repository", name="owner/repo", depth=0, children=[a, b]
    )
    return root


class TestWalkTree:
    """Test walk_tree visits all nodes depth-first."""

    def test_walk_visits_all_nodes(self):
        root = _build_sample_tree()
        names = [n.name for n in walk_tree(root)]
        assert len(names) == 6
        assert names[0] == "owner/repo"  # root first

    def test_walk_depth_first_order(self):
        root = _build_sample_tree()
        names = [n.name for n in walk_tree(root)]
        # Pre-order DFS: root, A, C, D, B, E
        assert names == ["owner/repo", "a", "c", "d", "b", "e"]

    def test_walk_single_node(self):
        node = TreeNode(id="single", name="single")
        nodes = list(walk_tree(node))
        assert len(nodes) == 1
        assert nodes[0].name == "single"

    def test_walk_empty_children(self):
        root = TreeNode(id="root", name="root", children=[])
        nodes = list(walk_tree(root))
        assert len(nodes) == 1


class TestCloneTree:
    """Test clone_tree produces independent copy."""

    def test_clone_produces_equal_structure(self):
        root = _build_sample_tree()
        cloned = clone_tree(root)

        orig_names = [n.name for n in walk_tree(root)]
        clone_names = [n.name for n in walk_tree(cloned)]
        assert orig_names == clone_names

    def test_clone_is_independent(self):
        root = _build_sample_tree()
        cloned = clone_tree(root)

        # Mutate the clone
        cloned.children[0].name = "MUTATED"
        cloned.children.append(TreeNode(id="new", name="new_node"))

        # Original should be unaffected
        assert root.children[0].name == "a"
        assert len(root.children) == 2

    def test_clone_deep_independence(self):
        root = _build_sample_tree()
        cloned = clone_tree(root)

        # Mutate a grandchild in the clone
        cloned.children[0].children[0].version = "99.99"

        # Original grandchild unaffected
        assert root.children[0].children[0].version == "1.0"

    def test_clone_preserves_all_fields(self):
        from open_source_risk_model.tree.models import RiskMetadata

        node = TreeNode(
            id="pkg:npm/test@1.0",
            node_type="package",
            name="test",
            version="1.0",
            depth=1,
            children_truncated=True,
            child_count=5,
            dependency_type="direct",
            ecosystem="npm",
            specifier="^1.0.0",
            risk_metadata=RiskMetadata(risk_score=75.0, risk_level="high"),
            resolution_status="resolved",
        )
        cloned = clone_tree(node)

        assert cloned.id == node.id
        assert cloned.children_truncated == node.children_truncated
        assert cloned.child_count == node.child_count
        assert cloned.ecosystem == node.ecosystem
        assert cloned.specifier == node.specifier
        assert cloned.risk_metadata.risk_score == 75.0
        assert cloned.risk_metadata is not node.risk_metadata  # different object


class TestCollectNodes:
    """Test collect_nodes with various predicates."""

    def test_collect_all_packages(self):
        root = _build_sample_tree()
        packages = collect_nodes(root, lambda n: n.node_type == "package")
        assert len(packages) == 5  # a, b, c, d, e

    def test_collect_by_depth(self):
        root = _build_sample_tree()
        depth_2 = collect_nodes(root, lambda n: n.depth == 2)
        assert len(depth_2) == 3
        names = {n.name for n in depth_2}
        assert names == {"c", "d", "e"}

    def test_collect_transitive(self):
        root = _build_sample_tree()
        transitive = collect_nodes(root, lambda n: n.dependency_type == "transitive")
        assert len(transitive) == 3

    def test_collect_none_matching(self):
        root = _build_sample_tree()
        result = collect_nodes(root, lambda n: n.name == "nonexistent")
        assert result == []

    def test_collect_root_only(self):
        root = _build_sample_tree()
        repos = collect_nodes(root, lambda n: n.node_type == "repository")
        assert len(repos) == 1
        assert repos[0].name == "owner/repo"


class TestMapTree:
    """Test map_tree applies function to all nodes."""

    def test_map_modifies_all_nodes(self):
        root = _build_sample_tree()
        result = map_tree(root, lambda n: _set_name_upper(n))

        names = [n.name for n in walk_tree(result)]
        assert all(n == n.upper() for n in names)

    def test_map_does_not_modify_original(self):
        root = _build_sample_tree()
        _ = map_tree(root, lambda n: _set_name_upper(n))

        # Original unchanged
        assert root.name == "owner/repo"
        assert root.children[0].name == "a"

    def test_map_preserves_structure(self):
        root = _build_sample_tree()
        result = map_tree(root, lambda n: n)  # identity

        assert count_nodes(result) == count_nodes(root)
        orig_names = [n.name for n in walk_tree(root)]
        result_names = [n.name for n in walk_tree(result)]
        assert orig_names == result_names


def _set_name_upper(node: TreeNode) -> TreeNode:
    node.name = node.name.upper()
    return node


class TestCountNodes:
    """Test count_nodes counts all nodes including root."""

    def test_count_full_tree(self):
        root = _build_sample_tree()
        assert count_nodes(root) == 6

    def test_count_single_node(self):
        node = TreeNode(id="single", name="single")
        assert count_nodes(node) == 1

    def test_count_root_with_children(self):
        child1 = TreeNode(id="c1", name="c1")
        child2 = TreeNode(id="c2", name="c2")
        root = TreeNode(id="root", name="root", children=[child1, child2])
        assert count_nodes(root) == 3
