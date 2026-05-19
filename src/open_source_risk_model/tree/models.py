"""Data models for the dependency tree module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RiskMetadata:
    """Risk metadata for a dependency node."""

    risk_score: Optional[float] = None
    risk_level: Optional[str] = None  # "low" (<=30), "medium" (31-70), "high" (>70)
    vulnerability_count: int = 0

    release_recency_days: Optional[int] = None
    maintainer_count: Optional[int] = None

    score_source: str = "unavailable"  # "repo_graph", "unavailable"
    score_completeness: str = "missing"  # "full", "partial", "missing"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict, omitting None optional fields."""
        d: Dict[str, Any] = {}
        d["risk_score"] = self.risk_score
        d["risk_level"] = self.risk_level
        d["vulnerability_count"] = self.vulnerability_count
        if self.release_recency_days is not None:
            d["release_recency_days"] = self.release_recency_days
        if self.maintainer_count is not None:
            d["maintainer_count"] = self.maintainer_count
        d["score_source"] = self.score_source
        d["score_completeness"] = self.score_completeness
        return d


@dataclass
class TreeNode:
    """A node in the dependency tree."""

    # Identity
    id: str = ""
    node_type: str = "package"  # "repository" or "package"
    name: str = ""
    version: Optional[str] = None

    # Tree structure
    depth: int = 0
    children: List["TreeNode"] = field(default_factory=list)
    children_truncated: bool = False
    child_count: Optional[int] = None

    # Dependency metadata
    dependency_type: str = "direct"  # "direct" or "transitive"
    ecosystem: Optional[str] = None
    specifier: Optional[str] = None

    # Risk metadata
    risk_metadata: Optional[RiskMetadata] = None

    # Scope classification (Phase 1 — direct deps only)
    dependency_scope: Optional[str] = None
    scope_confidence: Optional[str] = None

    # Resolution status
    resolution_status: str = "resolved"  # "resolved" or "error"
    error_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict with stable field ordering.

        - Recursively serializes nested trees.
        - Omits optional fields that are None, EXCEPT version (always included).
        - Error nodes include resolution_status and error_reason.
        """
        d: Dict[str, Any] = {}

        # Identity fields (stable order)
        d["id"] = self.id
        d["node_type"] = self.node_type
        d["name"] = self.name
        d["version"] = self.version  # Always included, even if None

        # Tree structure
        d["depth"] = self.depth
        d["children"] = [child.to_dict() for child in self.children]
        if self.children_truncated:
            d["children_truncated"] = self.children_truncated
        if self.child_count is not None:
            d["child_count"] = self.child_count

        # Dependency metadata
        d["dependency_type"] = self.dependency_type
        if self.ecosystem is not None:
            d["ecosystem"] = self.ecosystem
        if self.specifier is not None:
            d["specifier"] = self.specifier

        # Risk metadata
        if self.risk_metadata is not None:
            d["risk_metadata"] = self.risk_metadata.to_dict()

        # Resolution status — always include for error nodes
        if self.resolution_status == "error":
            d["resolution_status"] = self.resolution_status
            d["error_reason"] = self.error_reason
        elif self.resolution_status != "resolved":
            d["resolution_status"] = self.resolution_status

        # Scope classification — include only when set
        if self.dependency_scope is not None:
            d["dependency_scope"] = self.dependency_scope
        if self.scope_confidence is not None:
            d["scope_confidence"] = self.scope_confidence

        return d


@dataclass
class SummaryMetrics:
    """Summary metrics for the returned dependency tree."""

    total_dependencies: int = 0
    direct_dependencies: int = 0
    transitive_dependencies: int = 0
    high_risk_count: int = 0
    vulnerable_count: int = 0
    max_depth: int = 0
    riskiest_branch: Optional[Dict[str, Any]] = None
    filters_applied: List[str] = field(default_factory=list)

    # Phase 1 — Direct dependency scope counts
    direct_runtime_dependency_count: int = 0
    direct_dev_dependency_count: int = 0
    direct_test_dependency_count: int = 0
    direct_build_dependency_count: int = 0
    direct_optional_dependency_count: int = 0
    direct_peer_dependency_count: int = 0
    direct_unknown_dependency_count: int = 0
    direct_total_dependency_count: int = 0
    scope_counts_are_direct_only: bool = True
    scope_classification_label: str = "Direct dependencies, classified from manifests"
    scope_note: str = "Dependency scope is classified from manifests and may not reflect actual runtime usage."
    transitive_runtime_dependency_count: int = 0

    # Phase 4 — Scope exposure metrics
    runtime_dependency_exposure: float = 0.0
    transitive_runtime_dependency_exposure: float = 0.0
    scope_weighted_dependency_exposure: float = 0.0
    vulnerable_runtime_dependency_count: int = 0
    vulnerable_transitive_runtime_dependency_count: int = 0
    high_risk_runtime_dependency_count: int = 0
    unknown_scope_dependency_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        d: Dict[str, Any] = {
            "total_dependencies": self.total_dependencies,
            "direct_dependencies": self.direct_dependencies,
            "transitive_dependencies": self.transitive_dependencies,
            "high_risk_count": self.high_risk_count,
            "vulnerable_count": self.vulnerable_count,
            "max_depth": self.max_depth,
        }
        if self.riskiest_branch is not None:
            d["riskiest_branch"] = self.riskiest_branch
        d["filters_applied"] = self.filters_applied
        # Phase 1 — Direct dependency scope counts
        d["direct_runtime_dependency_count"] = self.direct_runtime_dependency_count
        d["direct_dev_dependency_count"] = self.direct_dev_dependency_count
        d["direct_test_dependency_count"] = self.direct_test_dependency_count
        d["direct_build_dependency_count"] = self.direct_build_dependency_count
        d["direct_optional_dependency_count"] = self.direct_optional_dependency_count
        d["direct_peer_dependency_count"] = self.direct_peer_dependency_count
        d["direct_unknown_dependency_count"] = self.direct_unknown_dependency_count
        d["direct_total_dependency_count"] = self.direct_total_dependency_count
        d["scope_counts_are_direct_only"] = self.scope_counts_are_direct_only
        d["scope_classification_label"] = self.scope_classification_label
        d["scope_note"] = self.scope_note
        d["transitive_runtime_dependency_count"] = self.transitive_runtime_dependency_count
        # Phase 4 — Scope exposure metrics
        d["runtime_dependency_exposure"] = self.runtime_dependency_exposure
        d["transitive_runtime_dependency_exposure"] = self.transitive_runtime_dependency_exposure
        d["scope_weighted_dependency_exposure"] = self.scope_weighted_dependency_exposure
        d["vulnerable_runtime_dependency_count"] = self.vulnerable_runtime_dependency_count
        d["vulnerable_transitive_runtime_dependency_count"] = self.vulnerable_transitive_runtime_dependency_count
        d["high_risk_runtime_dependency_count"] = self.high_risk_runtime_dependency_count
        d["unknown_scope_dependency_ratio"] = self.unknown_scope_dependency_ratio
        return d


@dataclass
class ProvenanceInfo:
    """Provenance information for the tree response."""

    data_source: str = "database"  # "database", "live", "mixed"
    data_completeness: str = "full"  # "full", "partial"
    last_updated: str = ""

    total_nodes: int = 0
    nodes_with_risk_data: int = 0
    nodes_with_missing_risk: int = 0
    nodes_with_errors: int = 0
    error_details: List[Dict[str, str]] = field(default_factory=list)

    live_fetched_nodes: List[str] = field(default_factory=list)

    construction_time_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        d: Dict[str, Any] = {
            "data_source": self.data_source,
            "data_completeness": self.data_completeness,
            "last_updated": self.last_updated,
            "total_nodes": self.total_nodes,
            "nodes_with_risk_data": self.nodes_with_risk_data,
            "nodes_with_missing_risk": self.nodes_with_missing_risk,
            "nodes_with_errors": self.nodes_with_errors,
            "error_details": self.error_details,
            "live_fetched_nodes": self.live_fetched_nodes,
        }
        if self.construction_time_ms is not None:
            d["construction_time_ms"] = self.construction_time_ms
        return d


@dataclass
class DependencyTreeResponse:
    """Complete dependency tree API response."""

    repo: str = ""
    tree: Optional[TreeNode] = None
    summary_metrics: Optional[SummaryMetrics] = None
    provenance: Optional[ProvenanceInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        d: Dict[str, Any] = {"repo": self.repo}
        if self.tree is not None:
            d["tree"] = self.tree.to_dict()
        if self.summary_metrics is not None:
            d["summary_metrics"] = self.summary_metrics.to_dict()
        if self.provenance is not None:
            d["provenance"] = self.provenance.to_dict()
        return d


@dataclass
class FilterConfig:
    """Configuration for tree filtering."""

    max_depth: Optional[int] = None
    high_risk_only: bool = False
    vulnerable_only: bool = False
    direct_only: bool = False
