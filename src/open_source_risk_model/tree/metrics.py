"""Summary metrics calculator for dependency trees."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any, Dict, List, Optional

from open_source_risk_model.tree.models import SummaryMetrics, TreeNode
from open_source_risk_model.tree.tree_utils import walk_tree

# Mapping from dependency_scope DB values to SummaryMetrics field names
_SCOPE_TO_FIELD = {
    "runtime": "direct_runtime_dependency_count",
    "dev": "direct_dev_dependency_count",
    "test": "direct_test_dependency_count",
    "build": "direct_build_dependency_count",
    "optional": "direct_optional_dependency_count",
    "peer": "direct_peer_dependency_count",
    "unknown": "direct_unknown_dependency_count",
}


class SummaryMetricsCalculator:
    """Calculate aggregate statistics for a (post-transformation) dependency tree.

    Metrics are computed on the tree as-is (post-filter, post-sort, post-truncation).
    Preserved ancestor nodes ARE counted in total dependency counts but are NOT
    counted in high_risk_count or vulnerable_count unless they independently
    satisfy those criteria.
    """

    def __init__(self, db_path: str = "data/graphs.db") -> None:
        self.db_path = db_path

    def calculate_metrics(
        self,
        tree_root: TreeNode,
        filters_applied: List[str],
        repo_full_name: Optional[str] = None,
    ) -> SummaryMetrics:
        """Calculate summary metrics for the given tree.

        Args:
            tree_root: Root node of the (possibly filtered) tree.
            filters_applied: List of filter names that were applied.
            repo_full_name: Optional repo identifier. When provided, scope
                breakdown counts are computed directly from the
                ``repo_dependencies`` table (not from tree nodes).

        Returns:
            SummaryMetrics with aggregate statistics.
        """
        direct = 0
        transitive = 0
        high_risk = 0
        vulnerable = 0
        max_depth = 0

        for node in walk_tree(tree_root):
            # Skip the root node for dependency counts
            if node.depth == 0:
                continue

            if node.depth == 1:
                direct += 1
            else:
                transitive += 1

            if node.depth > max_depth:
                max_depth = node.depth

            # high_risk_count: only nodes with risk_score > 70
            if (
                node.risk_metadata is not None
                and node.risk_metadata.risk_score is not None
                and node.risk_metadata.risk_score > 70
            ):
                high_risk += 1

            # vulnerable_count: only nodes with vulnerability_count > 0
            if (
                node.risk_metadata is not None
                and node.risk_metadata.vulnerability_count > 0
            ):
                vulnerable += 1

        total = direct + transitive
        riskiest_branch = self._find_riskiest_branch(tree_root)

        # Compute scope breakdown counts from repo_dependencies table
        scope_kwargs: Dict[str, Any] = {}
        if repo_full_name is not None:
            scope_kwargs = self._compute_scope_counts(repo_full_name)

        return SummaryMetrics(
            total_dependencies=total,
            direct_dependencies=direct,
            transitive_dependencies=transitive,
            high_risk_count=high_risk,
            vulnerable_count=vulnerable,
            max_depth=max_depth,
            riskiest_branch=riskiest_branch,
            filters_applied=list(filters_applied),
            **scope_kwargs,
        )

    def _find_riskiest_branch(
        self, root: TreeNode
    ) -> Optional[Dict[str, Any]]:
        """DFS to find the path from root with the highest cumulative risk_score.

        Nodes with risk_score=None contribute 0 to the cumulative score.

        Returns:
            Dict with "path" (list of node IDs) and "cumulative_risk" (float),
            or None if the tree has no children (root only).
        """
        if not root.children:
            return None

        best_path: List[str] = []
        best_score = 0.0

        def _node_risk(n: TreeNode) -> float:
            if n.risk_metadata is not None and n.risk_metadata.risk_score is not None:
                return n.risk_metadata.risk_score
            return 0.0

        def dfs(node: TreeNode, path: List[str], cumulative: float) -> None:
            nonlocal best_path, best_score

            if not node.children:
                # Leaf node — check if this is the best path so far
                if cumulative > best_score or (cumulative == best_score and not best_path):
                    best_score = cumulative
                    best_path = list(path)
                return

            for child in node.children:
                child_risk = _node_risk(child)
                path.append(child.id)
                dfs(child, path, cumulative + child_risk)
                path.pop()

        # Start DFS from root; root's own risk contributes to cumulative score
        root_risk = _node_risk(root)
        dfs(root, [root.id], root_risk)

        return {"path": best_path, "cumulative_risk": best_score}

    # ------------------------------------------------------------------
    # Scope breakdown counts (Phase 1 — direct dependencies only)
    # ------------------------------------------------------------------

    def _compute_scope_counts(self, repo_full_name: str) -> Dict[str, Any]:
        """Query ``repo_dependencies`` for *repo_full_name* and return scope counts.

        Counts are derived strictly from the ``repo_dependencies`` table
        (``WHERE repo_full_name = ?``).  Each row is counted exactly once
        toward its ``dependency_scope`` bucket.  No tree-node or
        resolved-dependency logic is involved.

        Returns a dict suitable for unpacking into the ``SummaryMetrics``
        constructor (field-name → int).
        """
        counts: Counter[str] = Counter()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT dependency_scope FROM repo_dependencies "
                "WHERE repo_full_name = ?",
                (repo_full_name,),
            )
            for (scope_value,) in cursor:
                # Normalise NULL / empty to "unknown"
                scope_value = scope_value or "unknown"
                counts[scope_value] += 1
            conn.close()
        except Exception:
            # On any DB error, leave counts at zero (safe default)
            pass

        result: Dict[str, Any] = {}
        total = 0
        for scope, field_name in _SCOPE_TO_FIELD.items():
            count = counts.get(scope, 0)
            result[field_name] = count
            total += count

        result["direct_total_dependency_count"] = total
        return result
