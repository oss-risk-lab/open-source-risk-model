"""TreeService: Canonical Tree Assembly (Phase 1) and Response Transformation (Phase 2).

Orchestrates dependency retrieval, tree construction, risk enrichment,
filtering, sorting, truncation, metrics calculation, and provenance assembly.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from open_source_risk_model.persistence.db import get_connection
from open_source_risk_model.tree.enricher import RiskMetadataEnricher
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
    SummaryMetrics,
    TreeNode,
)
from open_source_risk_model.tree.tree_utils import clone_tree, walk_tree

from open_source_risk_model.resolution.storage import ResolvedDependencyStorage
from open_source_risk_model.resolution.models import ResolutionEdge, make_node_key
from open_source_risk_model.dependencies.scope_classifier import aggregate_node_scope


# Registry type → ecosystem mapping
_REGISTRY_TO_ECOSYSTEM = {
    "pypi": "pypi",
    "npm": "npm",
    "maven": "maven",
    "go": "go",
}


def _make_canonical_id(ecosystem: Optional[str], name: str, version: Optional[str]) -> str:
    """Build a canonical package ID: ``pkg:{ecosystem}/{name}@{version}``.

    Uses ``@unknown`` when *version* is ``None`` or empty.
    """
    eco = ecosystem or "unknown"
    ver = version if version else "unknown"
    return f"pkg:{eco}/{name}@{ver}"


class TreeService:
    """Builds canonical dependency trees from the database."""

    def __init__(self, db_path: str = "data/graphs.db") -> None:
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def get_dependency_tree(
        self,
        repo_full_name: str,
        max_depth: Optional[int] = None,
        high_risk_only: bool = False,
        vulnerable_only: bool = False,
        direct_only: bool = False,
        sort_by: Optional[str] = None,
        truncate_after_children: Optional[int] = None,
        timeout_seconds: float = 10.0,
    ) -> DependencyTreeResponse:
        """Build and return a dependency tree for *repo_full_name*.

        Orchestrates the two-phase pipeline:
          Phase 1 – ``_build_canonical_tree`` (assembly + enrichment)
          Phase 2 – ``_transform_for_response`` (filter, sort, truncate, metrics, provenance)

        Raises:
            RepositoryNotFoundError: repo not in database.
            TreeConstructionTimeoutError: wall-clock time exceeded *timeout_seconds*.
            AllDependenciesFailedError: every dependency failed to resolve.
        """
        start_time = time.monotonic()

        # Phase 1: Canonical Tree Assembly
        canonical_tree, data_source, resolved_edges = self._build_canonical_tree(repo_full_name)

        # Phase 2: Response Transformation
        filters = FilterConfig(
            max_depth=max_depth,
            high_risk_only=high_risk_only,
            vulnerable_only=vulnerable_only,
            direct_only=direct_only,
        )
        response = self._transform_for_response(
            canonical_tree,
            data_source,
            filters,
            sort_by=sort_by,
            truncate_after_children=truncate_after_children,
            start_time=start_time,
            resolved_edges=resolved_edges,
        )

        # Timeout check after both phases complete
        elapsed = time.monotonic() - start_time
        if elapsed > timeout_seconds:
            raise TreeConstructionTimeoutError(
                f"Tree construction exceeded timeout of {timeout_seconds}s "
                f"(took {elapsed:.1f}s) for '{repo_full_name}'"
            )

        return response

    # ------------------------------------------------------------------
    # Phase 1 – Dependency retrieval
    # ------------------------------------------------------------------

    def _retrieve_dependency_relationships(
        self, repo_full_name: str
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Retrieve dependency rows for *repo_full_name*.

        Follows the Repository Existence Decision Tree:
        1. Query ``repo_dependencies`` for the repo.
        2. Rows found → return (rows, "database").
        3. No rows → check ``repo_graphs`` for repo existence.
        4. Repo exists with zero deps → return ([], "database").
        5. Repo not in local data → raise ``RepositoryNotFoundError``.

        Returns:
            (dependency_list, data_source) where data_source is "database".
        """
        conn = get_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM repo_dependencies WHERE repo_full_name = ? ORDER BY package_name",
                (repo_full_name,),
            )
            rows = [dict(row) for row in cursor.fetchall()]

            if rows:
                return rows, "database"

            # No dependency rows – check if the repo exists at all
            cursor = conn.execute(
                "SELECT 1 FROM repo_graphs WHERE repo_full_name = ?",
                (repo_full_name,),
            )
            if cursor.fetchone():
                # Repo exists but has zero dependencies
                return [], "database"

            # Repo not in local data at all – post-MVP live ingestion would go here
            raise RepositoryNotFoundError(
                f"Repository '{repo_full_name}' not found in database"
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Phase 1 – Canonical tree construction
    # ------------------------------------------------------------------

    def _build_canonical_tree(
        self, repo_full_name: str
    ) -> Tuple[TreeNode, str, Optional[List[ResolutionEdge]]]:
        """Build the full canonical tree for *repo_full_name*.

        Steps:
        0. Check for resolved transitive data (Req 10.1).
        1. Retrieve dependency relationships.
        2. Create root ``TreeNode`` (node_type="repository", depth=0).
        3. Build children recursively, computing depth during assembly.
        4. Enrich all nodes with risk metadata.

        Returns:
            (root_node, data_source, resolved_edges_or_None)

        Raises:
            RepositoryNotFoundError: repo not in database.
            AllDependenciesFailedError: every dependency failed to resolve.
        """
        # Check for resolved transitive data first (Req 10.1)
        try:
            storage = ResolvedDependencyStorage(self.db_path)
            if storage.has_resolved_data(repo_full_name):
                edges = storage.get_edges(repo_full_name)
                root = self._build_tree_from_resolved(repo_full_name, edges)
                all_nodes = list(walk_tree(root))
                RiskMetadataEnricher.enrich_nodes(all_nodes, self.db_path)
                return root, "database", edges
        except Exception:
            pass  # Fall through to existing logic on any error

        # Existing flat-tree logic (Req 10.3)
        deps, data_source = self._retrieve_dependency_relationships(repo_full_name)

        # Root node
        root = TreeNode(
            id=repo_full_name,
            node_type="repository",
            name=repo_full_name,
            version=None,
            depth=0,
            dependency_type="direct",
        )

        if not deps:
            # Zero-dependency repo – valid, not an error
            # Still enrich (no-op for root-only tree)
            all_nodes = list(walk_tree(root))
            RiskMetadataEnricher.enrich_nodes(all_nodes, self.db_path)
            return root, data_source, None

        # Organise deps: separate direct from transitive, index by parent
        direct_deps: List[Dict[str, Any]] = []
        transitive_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        error_count = 0
        total_count = 0

        for dep in deps:
            total_count += 1
            is_direct = dep.get("is_direct", True)
            if is_direct:
                direct_deps.append(dep)
            else:
                parent_key = dep.get("parent_package_name", "")
                transitive_by_parent.setdefault(parent_key, []).append(dep)

        # Build direct children
        for dep in direct_deps:
            try:
                child = self._build_node(dep, depth=1, dependency_type="direct",
                                         transitive_by_parent=transitive_by_parent,
                                         branch_visited=set())
                root.children.append(child)
            except DependencyResolutionError as exc:
                error_count += 1
                root.children.append(self._make_error_node(dep, depth=1, reason=str(exc)))

        if error_count > 0 and error_count == total_count:
            raise AllDependenciesFailedError(
                f"All {total_count} dependencies failed to resolve for '{repo_full_name}'"
            )

        # Enrich all nodes with risk metadata
        all_nodes = list(walk_tree(root))
        RiskMetadataEnricher.enrich_nodes(all_nodes, self.db_path)

        return root, data_source, None

    def _build_node(
        self,
        dep: Dict[str, Any],
        depth: int,
        dependency_type: str,
        transitive_by_parent: Dict[str, List[Dict[str, Any]]],
        branch_visited: Set[str],
    ) -> TreeNode:
        """Create a ``TreeNode`` for *dep* and recursively attach children.

        Cycle detection: *branch_visited* tracks canonical IDs along the
        current branch path.  If a canonical ID is already visited, recursion
        stops for that branch.
        """
        name = dep["package_name"]
        registry = dep.get("registry_type", "")
        ecosystem = _REGISTRY_TO_ECOSYSTEM.get(registry, registry) if registry else None
        version = dep.get("package_version") or dep.get("specifier") or None
        # Treat empty strings as None
        if version == "":
            version = None
        canonical_id = _make_canonical_id(ecosystem, name, version)

        node = TreeNode(
            id=canonical_id,
            node_type="package",
            name=name,
            version=version,
            depth=depth,
            dependency_type=dependency_type,
            ecosystem=ecosystem,
            specifier=dep.get("specifier"),
            resolution_status="resolved",
            dependency_scope=dep.get("dependency_scope"),
            scope_confidence=dep.get("scope_confidence"),
        )

        # Cycle detection – stop recursion if we've seen this ID on this branch
        if canonical_id in branch_visited:
            return node

        # Track this node on the current branch path
        new_visited = branch_visited | {canonical_id}

        # Attach transitive children (keyed by parent package name)
        children_deps = transitive_by_parent.get(name, [])
        for child_dep in children_deps:
            try:
                child = self._build_node(
                    child_dep,
                    depth=depth + 1,
                    dependency_type="transitive",
                    transitive_by_parent=transitive_by_parent,
                    branch_visited=new_visited,
                )
                node.children.append(child)
            except DependencyResolutionError as exc:
                node.children.append(
                    self._make_error_node(child_dep, depth=depth + 1, reason=str(exc))
                )

        return node

    @staticmethod
    def _make_error_node(dep: Dict[str, Any], depth: int, reason: str) -> TreeNode:
        """Create an error node for a failed dependency resolution."""
        name = dep.get("package_name", "unknown")
        registry = dep.get("registry_type", "")
        ecosystem = _REGISTRY_TO_ECOSYSTEM.get(registry, registry) if registry else None
        version = dep.get("package_version") or dep.get("specifier") or None
        if version == "":
            version = None
        canonical_id = _make_canonical_id(ecosystem, name, version)

        return TreeNode(
            id=canonical_id,
            node_type="package",
            name=name,
            version=version,
            depth=depth,
            dependency_type="direct" if depth == 1 else "transitive",
            ecosystem=ecosystem,
            resolution_status="error",
            error_reason=reason,
            risk_metadata=None,
            children=[],
        )

    # ------------------------------------------------------------------
    # Phase 1 – Resolved tree construction (Req 10.2)
    # ------------------------------------------------------------------

    def _build_tree_from_resolved(
        self, repo_full_name: str, edges: list[ResolutionEdge]
    ) -> TreeNode:
        """Build multi-level tree from resolved edges (Req 10.2)."""
        root = TreeNode(
            id=repo_full_name,
            node_type="repository",
            name=repo_full_name,
            depth=0,
            dependency_type="direct",
        )

        # Group edges by make_node_key(parent_ecosystem, parent_package)
        children_by_parent: dict[tuple, list[ResolutionEdge]] = {}
        for edge in edges:
            key = make_node_key(edge.parent_ecosystem, edge.parent_package)
            children_by_parent.setdefault(key, []).append(edge)

        # Build scope aggregation map: (ecosystem, package_name) → list of (scope, confidence)
        scope_agg_map: dict[tuple, list[tuple[str, str]]] = {}
        for edge in edges:
            child_key = (edge.child_ecosystem, edge.child_package)
            scope_agg_map.setdefault(child_key, []).append(
                (edge.dependency_scope, edge.scope_confidence)
            )

        # Pre-compute aggregated scope per child using aggregate_node_scope()
        aggregated_scopes: dict[tuple, tuple[str, str]] = {}
        for child_key, scope_tuples in scope_agg_map.items():
            aggregated_scopes[child_key] = aggregate_node_scope(scope_tuples)

        # Direct children: parent is repo (ecosystem=None, package=repo_full_name)
        direct_edges = children_by_parent.get(make_node_key(None, repo_full_name), [])
        for edge in sorted(direct_edges, key=lambda e: e.child_package):
            child = self._edge_to_node(edge, children_by_parent, branch_visited=set(),
                                       aggregated_scopes=aggregated_scopes)
            root.children.append(child)

        return root

    def _edge_to_node(
        self,
        edge: ResolutionEdge,
        children_by_parent: dict[tuple, list[ResolutionEdge]],
        branch_visited: set[tuple],
        aggregated_scopes: dict[tuple, tuple[str, str]] | None = None,
    ) -> TreeNode:
        """Convert a ResolutionEdge to a TreeNode, recursively attaching children."""
        canonical_id = _make_canonical_id(
            edge.child_ecosystem, edge.child_package, edge.resolved_version
        )

        node_status, error_reason = self._map_resolution_status(edge)
        dep_type = "direct" if edge.depth == 1 else "transitive"

        # Apply aggregated scope from pre-computed map (Req 9.1)
        agg_scope: str | None = None
        agg_confidence: str | None = None
        if aggregated_scopes is not None:
            child_key = (edge.child_ecosystem, edge.child_package)
            if child_key in aggregated_scopes:
                agg_scope, agg_confidence = aggregated_scopes[child_key]

        node = TreeNode(
            id=canonical_id,
            node_type="package",
            name=edge.child_package,
            version=edge.resolved_version,
            depth=edge.depth,
            dependency_type=dep_type,
            ecosystem=edge.child_ecosystem,
            specifier=edge.declared_specifier,
            resolution_status=node_status,
            error_reason=error_reason,
            dependency_scope=agg_scope,
            scope_confidence=agg_confidence,
        )

        # Terminal statuses: no children
        if edge.resolution_status in (
            "error", "cycle_detected", "max_depth_reached",
            "budget_exhausted", "unsupported_ecosystem",
        ):
            return node

        # Safety guard against reconstruction loops
        visit_key = make_node_key(edge.child_ecosystem, edge.child_package, edge.resolved_version)
        if visit_key in branch_visited:
            return node
        new_visited = branch_visited | {visit_key}

        # Find children using ecosystem-qualified parent key
        child_key = make_node_key(edge.child_ecosystem, edge.child_package)
        child_edges = children_by_parent.get(child_key, [])
        for child_edge in sorted(child_edges, key=lambda e: e.child_package):
            child_node = self._edge_to_node(child_edge, children_by_parent, new_visited,
                                            aggregated_scopes=aggregated_scopes)
            node.children.append(child_node)

        return node

    @staticmethod
    def _map_resolution_status(
        edge: ResolutionEdge,
    ) -> tuple[str, str | None]:
        """Map edge resolution_status to TreeNode fields (Req 10.4)."""
        match edge.resolution_status:
            case "resolved":
                return "resolved", None
            case "error":
                return "error", edge.error_reason
            case "cycle_detected":
                return "cycle_detected", None
            case "max_depth_reached":
                return "max_depth_reached", None
            case "unsupported_ecosystem":
                return "unsupported_ecosystem", "Ecosystem not supported for resolution"
            case "budget_exhausted":
                return "budget_exhausted", "Resolution budget exhausted"
            case _:
                return "resolved", None

    # ------------------------------------------------------------------
    # Phase 2 – Response Transformation
    # ------------------------------------------------------------------

    def _transform_for_response(
        self,
        canonical_tree: TreeNode,
        data_source: str,
        filters: FilterConfig,
        sort_by: Optional[str] = None,
        truncate_after_children: Optional[int] = None,
        start_time: Optional[float] = None,
        resolved_edges: Optional[List[ResolutionEdge]] = None,
    ) -> DependencyTreeResponse:
        """Phase 2: Transform the canonical tree for the API response.

        Steps:
        0. Deep-clone the canonical tree.
        4. Apply filters in order: direct_only → max_depth → high_risk_only → vulnerable_only.
        5. Apply sorting.
        6. Apply truncation.
        7. Calculate summary metrics on the transformed tree.
        8. Assemble ProvenanceInfo.

        Returns:
            DependencyTreeResponse
        """
        # Step 0: Deep-clone
        tree = clone_tree(canonical_tree)

        # Build filters_applied list
        filters_applied: List[str] = []
        if filters.direct_only:
            filters_applied.append("direct_only")
        if filters.max_depth is not None:
            filters_applied.append("max_depth")
        if filters.high_risk_only:
            filters_applied.append("high_risk_only")
        if filters.vulnerable_only:
            filters_applied.append("vulnerable_only")

        # Step 4: Apply filters in defined order
        if filters.direct_only:
            self._filter_direct_only(tree)
        if filters.max_depth is not None:
            self._filter_by_depth(tree, filters.max_depth)
        if filters.high_risk_only or filters.vulnerable_only:
            self._filter_by_criteria(tree, filters.high_risk_only, filters.vulnerable_only)

        # Step 5: Apply sorting
        self._sort_siblings(tree, sort_by)

        # Step 6: Apply truncation
        if truncate_after_children is not None:
            self._truncate_children(tree, truncate_after_children)

        # Step 7: Calculate summary metrics
        calculator = SummaryMetricsCalculator(db_path=self.db_path)
        repo_full_name = canonical_tree.id if canonical_tree else None
        summary_metrics = calculator.calculate_metrics(
            tree, filters_applied,
            repo_full_name=repo_full_name,
            resolved_edges=resolved_edges,
        )

        # Step 8: Assemble provenance
        provenance = self._assemble_provenance(tree, data_source, start_time=start_time)

        return DependencyTreeResponse(
            repo=tree.id,
            tree=tree,
            summary_metrics=summary_metrics,
            provenance=provenance,
        )

    # -- Filtering helpers --

    @staticmethod
    def _filter_direct_only(tree: TreeNode) -> None:
        """Remove nodes with depth > 1. Does NOT set children_truncated."""
        for node in list(walk_tree(tree)):
            if node.depth <= 0:
                # Root: keep depth-1 children, strip their children
                for child in node.children:
                    child.children = []
            elif node.depth == 1:
                node.children = []

    @staticmethod
    def _filter_by_depth(tree: TreeNode, max_depth: int) -> None:
        """Remove nodes deeper than max_depth.

        Sets children_truncated=true and child_count on boundary nodes
        that had children.
        """
        def _prune(node: TreeNode) -> None:
            if node.depth >= max_depth:
                if node.children:
                    node.child_count = len(node.children)
                    node.children_truncated = True
                    node.children = []
            else:
                for child in node.children:
                    _prune(child)

        _prune(tree)

    @staticmethod
    def _filter_by_criteria(
        tree: TreeNode,
        high_risk_only: bool,
        vulnerable_only: bool,
    ) -> None:
        """Filter by high_risk_only and/or vulnerable_only with ancestor preservation.

        Uses depth-first tree-occurrence traversal with parent→child propagation
        of "keep" flags. Does NOT use flat canonical ID sets.

        AND logic: a leaf must satisfy ALL active criteria to be a matching node.
        """

        def _matches(node: TreeNode) -> bool:
            """Check if a node independently matches all active filter criteria."""
            if high_risk_only:
                if (
                    node.risk_metadata is None
                    or node.risk_metadata.risk_score is None
                    or node.risk_metadata.risk_score <= 70
                ):
                    return False
            if vulnerable_only:
                if (
                    node.risk_metadata is None
                    or node.risk_metadata.vulnerability_count <= 0
                ):
                    return False
            return True

        def _mark_keep(node: TreeNode) -> bool:
            """DFS: returns True if this node or any descendant should be kept.

            Root is always kept.
            """
            if node.depth == 0:
                # Root always included; still recurse to mark children
                any_child_kept = False
                kept_children: List[TreeNode] = []
                for child in node.children:
                    if _mark_keep(child):
                        kept_children.append(child)
                        any_child_kept = True
                node.children = kept_children
                return True

            # Check if this node matches
            self_matches = _matches(node)

            # Check if any descendant matches (recurse first)
            kept_children: List[TreeNode] = []
            any_descendant_kept = False
            for child in node.children:
                if _mark_keep(child):
                    kept_children.append(child)
                    any_descendant_kept = True

            node.children = kept_children

            # Keep this node if it matches or if any descendant is kept (ancestor preservation)
            return self_matches or any_descendant_kept

        _mark_keep(tree)

    # -- Sorting helpers --

    @staticmethod
    def _sort_siblings(node: TreeNode, sort_by: Optional[str]) -> None:
        """Sort children recursively according to sort_by parameter.

        Sort rules:
        - risk_score: DESC, nulls last, tie-break name ASC, version ASC (unknown last)
        - name: ASC, tie-break version ASC (unknown last)
        - vulnerability_count: DESC, nulls treated as 0, tie-break name ASC, version ASC (unknown last)
        - Default (no sort_by): name ASC, version ASC (unknown last)
        """

        def _version_key(v: Optional[str]) -> Tuple[int, str]:
            """Version sort key: known versions first (sorted ASC), None/unknown last."""
            if v is None:
                return (1, "")
            return (0, v)

        def _sort_key(child: TreeNode) -> Any:
            if sort_by == "risk_score":
                # DESC risk_score: negate for descending, nulls last
                rs = child.risk_metadata.risk_score if child.risk_metadata and child.risk_metadata.risk_score is not None else None
                if rs is None:
                    risk_key = (1, 0.0)  # nulls last
                else:
                    risk_key = (0, -rs)  # negate for DESC
                vk = _version_key(child.version)
                return (risk_key, child.name, vk)

            elif sort_by == "vulnerability_count":
                # DESC vulnerability_count: nulls treated as 0
                vc = child.risk_metadata.vulnerability_count if child.risk_metadata else 0
                if vc is None:
                    vc = 0
                vk = _version_key(child.version)
                return (-vc, child.name, vk)

            elif sort_by == "name":
                vk = _version_key(child.version)
                return (child.name, vk)

            else:
                # Default: name ASC, version ASC (unknown last)
                vk = _version_key(child.version)
                return (child.name, vk)

        node.children.sort(key=_sort_key)
        for child in node.children:
            TreeService._sort_siblings(child, sort_by)

    # -- Truncation helpers --

    @staticmethod
    def _truncate_children(node: TreeNode, limit: int) -> None:
        """Truncate children per parent node independently.

        child_count = number of children after filtering/sorting, before truncation.
        children_truncated=true only when actual truncation occurred.
        Keeps first N from sorted list. Applied recursively.
        """
        if len(node.children) > limit:
            node.child_count = len(node.children)
            node.children_truncated = True
            node.children = node.children[:limit]

        for child in node.children:
            TreeService._truncate_children(child, limit)

    # -- Provenance assembly --

    def _assemble_provenance(
        self,
        tree: TreeNode,
        data_source: str,
        start_time: Optional[float] = None,
    ) -> ProvenanceInfo:
        """Assemble ProvenanceInfo using Provenance Field Derivation Rules.

        Args:
            tree: The (possibly filtered) tree root.
            data_source: "database", "live", or "mixed".
            start_time: Wall-clock start time (from ``time.monotonic()``) for
                construction_time_ms calculation.  If None, construction_time_ms
                is not populated.
        """
        total_nodes = 0
        nodes_with_risk_data = 0
        nodes_with_missing_risk = 0
        nodes_with_errors = 0
        error_details: List[Dict[str, str]] = []

        all_nodes = list(walk_tree(tree))
        for node in all_nodes:
            total_nodes += 1
            if node.resolution_status == "error":
                nodes_with_errors += 1
                error_details.append({
                    "id": node.id,
                    "error_reason": node.error_reason or "Unknown error",
                })
            if (
                node.risk_metadata is not None
                and node.risk_metadata.score_completeness != "missing"
            ):
                nodes_with_risk_data += 1
            else:
                nodes_with_missing_risk += 1

        # data_completeness: "full" only if no missing risk AND no errors
        data_completeness = "full" if (nodes_with_missing_risk == 0 and nodes_with_errors == 0) else "partial"

        # last_updated: most recent updated_at from repo_graphs rows used in enrichment
        # If no DB data used, fall back to current request timestamp
        db_timestamp = RiskMetadataEnricher.get_latest_updated_at(all_nodes, self.db_path)
        if db_timestamp is not None:
            last_updated = db_timestamp
        else:
            last_updated = datetime.now(timezone.utc).isoformat()

        # construction_time_ms: wall-clock ms from start of Phase 1 to end of Phase 2
        construction_time_ms: Optional[int] = None
        if start_time is not None:
            elapsed = time.monotonic() - start_time
            construction_time_ms = max(1, int(elapsed * 1000))

        return ProvenanceInfo(
            data_source=data_source,
            data_completeness=data_completeness,
            last_updated=last_updated,
            total_nodes=total_nodes,
            nodes_with_risk_data=nodes_with_risk_data,
            nodes_with_missing_risk=nodes_with_missing_risk,
            nodes_with_errors=nodes_with_errors,
            error_details=error_details,
            construction_time_ms=construction_time_ms,
        )
