from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Valid resolution statuses (Req 5.4)
RESOLUTION_STATUSES = frozenset({
    "resolved",
    "error",
    "cycle_detected",
    "max_depth_reached",
    "unsupported_ecosystem",
    "budget_exhausted",
})


@dataclass(frozen=True)
class PackageIdentity:
    """Canonical identity for cycle detection and cache keys.
    Version is NOT part of identity for MVP because the resolver always
    resolves to the latest version and does not perform specifier-aware
    version solving."""
    ecosystem: str
    name: str


def make_node_key(
    ecosystem: str | None, name: str, version: str | None = None
) -> tuple[str | None, str] | tuple[str | None, str, str | None]:
    """Centralized identity key factory.

    MVP returns (ecosystem, name) — version is ignored because the
    resolver always resolves to latest.

    All call sites (cycle detection, cache keys, tree reconstruction
    grouping, branch_visited guards) MUST use this function instead of
    constructing raw tuples. When post-MVP adds version-aware resolution,
    this single function is the only place that needs to change to
    return (ecosystem, name, version).
    """
    # MVP: version excluded from identity
    return (ecosystem, name)


@dataclass
class DependencyDeclaration:
    """A single dependency as declared by a parent package."""
    name: str
    specifier: Optional[str] = None  # Declared_Specifier, e.g. ">=1.0,<2.0"


@dataclass
class NormalizedPackageMetadata:
    """Structured result of a registry lookup.
    This is what the Resolution_Cache stores (Req 6.1)."""
    name: str
    version: str                          # Resolved_Version
    ecosystem: str
    dependencies: list[DependencyDeclaration]  # declared deps of this package
    source_url: str                       # full registry URL used for fetch
    fetched_at: str                       # ISO 8601 timestamp


@dataclass
class ResolutionEdge:
    """A single parent→child edge in the resolved graph (Req 4.2, 7.2).
    Carries both declared specifier and resolved version (Req 2.3, 3.3).
    Parent identity includes ecosystem + package name (Req 7.3)."""
    repo_full_name: str
    parent_ecosystem: Optional[str]  # NULL for depth-1 edges (parent is repo)
    parent_package: str              # repo_full_name for depth-1 edges
    child_ecosystem: Optional[str]
    child_package: str
    declared_specifier: Optional[str]  # what the parent declared
    resolved_version: Optional[str]    # concrete version from registry
    depth: int                         # Node_Depth: 1=direct, 2=first transitive
    resolution_status: str = "resolved"
    error_reason: Optional[str] = None
    source_registry: Optional[str] = None  # ecosystem name, e.g. "pypi"
    resolved_at: str = ""              # ISO 8601, set by resolver


@dataclass
class ResolutionSummary:
    """Run-level summary returned by the resolver (Req 11.5)."""
    repo_full_name: str
    total_edges: int = 0
    resolved_count: int = 0
    error_count: int = 0
    cycle_count: int = 0
    max_depth_reached_count: int = 0
    unsupported_ecosystem_count: int = 0
    budget_exhausted_count: int = 0
    actual_max_depth: int = 0
    api_calls_made: int = 0
    cache_hits: int = 0
    elapsed_seconds: float = 0.0
    edges_per_depth: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_edges(cls, repo: str, edges: list[ResolutionEdge],
                   api_calls: int, cache_hits: int,
                   elapsed: float) -> ResolutionSummary:
        summary = cls(repo_full_name=repo, total_edges=len(edges),
                      api_calls_made=api_calls, cache_hits=cache_hits,
                      elapsed_seconds=elapsed)
        for e in edges:
            match e.resolution_status:
                case "resolved": summary.resolved_count += 1
                case "error": summary.error_count += 1
                case "cycle_detected": summary.cycle_count += 1
                case "max_depth_reached": summary.max_depth_reached_count += 1
                case "unsupported_ecosystem": summary.unsupported_ecosystem_count += 1
                case "budget_exhausted": summary.budget_exhausted_count += 1
            summary.actual_max_depth = max(summary.actual_max_depth, e.depth)
            summary.edges_per_depth[e.depth] = summary.edges_per_depth.get(e.depth, 0) + 1
        return summary
