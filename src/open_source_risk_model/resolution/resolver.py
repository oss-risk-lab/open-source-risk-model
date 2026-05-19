import logging
import time
import sqlite3
from datetime import datetime, timezone

from .models import PackageIdentity, ResolutionEdge, ResolutionSummary, make_node_key
from .cache import ResolutionCache
from .budget_tracker import BudgetTracker, BudgetConfig
from .registry_factory import get_registry_client
from open_source_risk_model.persistence.db import get_connection

logger = logging.getLogger(__name__)


class TransitiveResolver:
    def __init__(
        self,
        db_path: str = "data/graphs.db",
        max_depth: int = 5,
        budget_config: BudgetConfig | None = None,
        ecosystem_filter: set[str] | None = None,
    ):
        self.db_path = db_path
        self.max_depth = max_depth
        self.budget = BudgetTracker(budget_config or BudgetConfig())
        self.cache = ResolutionCache(db_path)
        self.ecosystem_filter = ecosystem_filter
        self._cache_hits = 0

    def resolve_repo(
        self, repo_full_name: str
    ) -> tuple[list[ResolutionEdge], ResolutionSummary]:
        start = time.monotonic()
        direct_deps = self._get_direct_deps(repo_full_name)
        edges: list[ResolutionEdge] = []

        for dep in sorted(direct_deps, key=lambda d: d["package_name"]):
            ecosystem = dep.get("registry_type") or dep.get("ecosystem") or "unknown"
            if self.ecosystem_filter and ecosystem not in self.ecosystem_filter:
                continue
            # Read direct dep scope from repo_dependencies (Req 6.3, 6.4)
            parent_scope = dep.get("dependency_scope") or "unknown"
            parent_scope_confidence = dep.get("scope_confidence") or "low"
            branch_path: set[tuple] = set()
            self._resolve_recursive(
                repo_full_name=repo_full_name,
                parent_ecosystem=None,
                parent_package=repo_full_name,
                child_name=dep["package_name"],
                child_ecosystem=ecosystem,
                declared_specifier=dep.get("specifier") or dep.get("version_spec"),
                depth=1,
                branch_path=branch_path,
                edges=edges,
                parent_scope=parent_scope,
                parent_scope_confidence=parent_scope_confidence,
            )

        elapsed = time.monotonic() - start
        summary = ResolutionSummary.from_edges(
            repo_full_name, edges,
            self.budget.api_calls_made, self._cache_hits, elapsed,
        )
        return edges, summary

    def _resolve_recursive(
        self,
        repo_full_name: str,
        parent_ecosystem: str | None,
        parent_package: str,
        child_name: str,
        child_ecosystem: str,
        declared_specifier: str | None,
        depth: int,
        branch_path: set[tuple],
        edges: list[ResolutionEdge],
        parent_scope: str = "unknown",
        parent_scope_confidence: str = "low",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        child_key = make_node_key(child_ecosystem, child_name)

        # Check 1: Max depth
        if depth > self.max_depth:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "max_depth_reached", None, None, now,
                parent_scope, parent_scope_confidence,
            ))
            return

        # Check 2: Cycle detection — branch-local
        if child_key in branch_path:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "cycle_detected", None, None, now,
                parent_scope, parent_scope_confidence,
            ))
            return

        # Check 3: Registry client availability
        client = get_registry_client(child_ecosystem)
        if client is None:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "unsupported_ecosystem", None, None, now,
                parent_scope, parent_scope_confidence,
            ))
            return

        # Step 4: Cache lookup
        metadata, cache_found = self.cache.lookup(child_ecosystem, child_name)
        if cache_found:
            self._cache_hits += 1
        else:
            # Step 5: Budget check
            if not self.budget.can_make_call(child_ecosystem):
                edges.append(self._make_edge(
                    repo_full_name, parent_ecosystem, parent_package,
                    child_ecosystem, child_name, declared_specifier,
                    None, depth, "budget_exhausted", None,
                    child_ecosystem, now,
                    parent_scope, parent_scope_confidence,
                ))
                return

            # Step 6: Delay + fetch + record
            self.budget.wait_if_needed(child_ecosystem)
            metadata = client.get_package_metadata(child_name, declared_specifier)
            self.budget.record_call(child_ecosystem)
            self.cache.store(child_ecosystem, child_name, metadata)

        # Check 7: Registry returned None
        if metadata is None:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "error", "Package not found in registry",
                child_ecosystem, now,
                parent_scope, parent_scope_confidence,
            ))
            return

        # Success: record resolved edge
        edges.append(self._make_edge(
            repo_full_name, parent_ecosystem, parent_package,
            child_ecosystem, child_name, declared_specifier,
            metadata.version, depth, "resolved", None,
            child_ecosystem, now,
            parent_scope, parent_scope_confidence,
        ))

        # Recurse into sub-dependencies — thread same scope (Req 3.1)
        new_branch_path = branch_path | {child_key}
        for sub_dep in sorted(metadata.dependencies, key=lambda d: d.name):
            self._resolve_recursive(
                repo_full_name=repo_full_name,
                parent_ecosystem=child_ecosystem,
                parent_package=child_name,
                child_name=sub_dep.name,
                child_ecosystem=child_ecosystem,
                declared_specifier=sub_dep.specifier,
                depth=depth + 1,
                branch_path=new_branch_path,
                edges=edges,
                parent_scope=parent_scope,
                parent_scope_confidence=parent_scope_confidence,
            )

    @staticmethod
    def _make_edge(repo, p_eco, p_pkg, c_eco, c_pkg, spec, ver,
                   depth, status, err, src, ts,
                   scope="unknown", confidence="low") -> ResolutionEdge:
        return ResolutionEdge(
            repo_full_name=repo, parent_ecosystem=p_eco,
            parent_package=p_pkg, child_ecosystem=c_eco,
            child_package=c_pkg, declared_specifier=spec,
            resolved_version=ver, depth=depth,
            resolution_status=status, error_reason=err,
            source_registry=src, resolved_at=ts,
            dependency_scope=scope, scope_confidence=confidence,
        )

    def _get_direct_deps(self, repo_full_name: str) -> list[dict]:
        conn = get_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM repo_dependencies WHERE repo_full_name = ? "
                "ORDER BY package_name",
                (repo_full_name,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
