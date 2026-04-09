"""Tree traversal and manipulation utilities."""

from __future__ import annotations

import copy
from typing import Callable, Iterator, List

from open_source_risk_model.tree.models import TreeNode


def walk_tree(root: TreeNode) -> Iterator[TreeNode]:
    """Yield all nodes depth-first (pre-order), starting with root."""
    yield root
    for child in root.children:
        yield from walk_tree(child)


def clone_tree(root: TreeNode) -> TreeNode:
    """Deep copy a tree, preserving all fields.

    Returns a completely independent copy — mutating the clone
    does not affect the original.
    """
    return copy.deepcopy(root)


def collect_nodes(root: TreeNode, predicate: Callable[[TreeNode], bool]) -> List[TreeNode]:
    """Collect all nodes matching a predicate via depth-first traversal."""
    return [node for node in walk_tree(root) if predicate(node)]


def map_tree(root: TreeNode, fn: Callable[[TreeNode], TreeNode]) -> TreeNode:
    """Apply fn to each node in a cloned tree (depth-first, pre-order).

    Returns a new tree — the original is not modified.
    """
    cloned = clone_tree(root)
    _map_in_place(cloned, fn)
    return cloned


def _map_in_place(node: TreeNode, fn: Callable[[TreeNode], TreeNode]) -> None:
    """Apply fn to node in-place, then recurse into children."""
    result = fn(node)
    # Copy fields from result back to node if fn returned a different object
    if result is not node:
        for attr in vars(result):
            setattr(node, attr, getattr(result, attr))
    for child in node.children:
        _map_in_place(child, fn)


def count_nodes(root: TreeNode) -> int:
    """Count all nodes in the tree, including root."""
    return sum(1 for _ in walk_tree(root))
