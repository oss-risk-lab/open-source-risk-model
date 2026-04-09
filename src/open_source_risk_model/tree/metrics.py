"""Summary metrics calculator for dependency trees."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from open_source_risk_model.tree.models import SummaryMetrics, TreeNode
from open_source_risk_model.tree.tree_utils import walk_tree


class SummaryMetricsCalculator:
    """Calculate aggregate statistics for a (post-transformation) dependency tree.

    Metrics are computed on the tree as-is (post-filter, post-sort, post-truncation).
    Preserved ancestor nodes ARE counted in total dependency counts but are NOT
    counted in high_risk_count or vulnerable_count unless they independently
    satisfy those criteria.
    """

    def calculate_metrics(
        self,
        tree_root: TreeNode,
        filters_applied: List[str],
    ) -> SummaryMetrics:
        """Calculate summary metrics for the given tree.

        Args:
            tree_root: Root node of the (possibly filtered) tree.
            filters_applied: List of filter names that were applied.

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

        return SummaryMetrics(
            total_dependencies=total,
            direct_dependencies=direct,
            transitive_dependencies=transitive,
            high_risk_count=high_risk,
            vulnerable_count=vulnerable,
            max_depth=max_depth,
            riskiest_branch=riskiest_branch,
            filters_applied=list(filters_applied),
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
