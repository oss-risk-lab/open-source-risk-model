"""Dependency tree module for building and transforming dependency trees."""

from open_source_risk_model.tree.exceptions import (
    AllDependenciesFailedError,
    DependencyResolutionError,
    RepositoryNotFoundError,
    TreeConstructionTimeoutError,
)
from open_source_risk_model.tree.metrics import SummaryMetricsCalculator
from open_source_risk_model.tree.models import (
    DependencyTreeResponse,
    FilterConfig,
    ProvenanceInfo,
    RiskMetadata,
    SummaryMetrics,
    TreeNode,
)
from open_source_risk_model.tree.tree_utils import (
    clone_tree,
    collect_nodes,
    count_nodes,
    map_tree,
    walk_tree,
)

__all__ = [
    # Exceptions
    "AllDependenciesFailedError",
    "DependencyResolutionError",
    "RepositoryNotFoundError",
    "TreeConstructionTimeoutError",
    # Calculator
    "SummaryMetricsCalculator",
    # Models
    "DependencyTreeResponse",
    "FilterConfig",
    "ProvenanceInfo",
    "RiskMetadata",
    "SummaryMetrics",
    "TreeNode",
    # Utilities
    "clone_tree",
    "collect_nodes",
    "count_nodes",
    "map_tree",
    "walk_tree",
]
