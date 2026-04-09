"""Risk metadata enricher for dependency tree nodes.

Maps package nodes to repository-level risk data via package_mappings → repo_graphs.
This is an MVP approximation: risk scores are repo-level, not package-version-native.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from open_source_risk_model.tree.models import RiskMetadata, TreeNode

logger = logging.getLogger(__name__)


class RiskMetadataEnricher:
    """Attach risk metadata to tree nodes using database lookups.

    Enrichment hierarchy (per node):
      1. Look up package in package_mappings → mapped repo_full_name
      2. Fetch risk data from repo_graphs for that repo
      3. If mapping or repo data is missing, mark as unavailable
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def enrich_nodes(nodes: List[TreeNode], db_path: str) -> List[TreeNode]:
        """Enrich *nodes* in-place with risk metadata.

        Batch queries are used for efficiency.  Nodes sharing the same
        canonical ``id`` are enriched once and receive identical metadata
        values (separate ``RiskMetadata`` instances).

        Args:
            nodes: Flat list of tree nodes to enrich (typically from walk_tree).
            db_path: Path to the SQLite database.

        Returns:
            The same list, with ``risk_metadata`` populated on each node.
        """
        if not nodes:
            return nodes

        # Collect unique canonical IDs (skip repository root nodes)
        id_to_nodes: Dict[str, List[TreeNode]] = {}
        for node in nodes:
            if node.node_type == "repository":
                continue
            id_to_nodes.setdefault(node.id, []).append(node)

        if not id_to_nodes:
            return nodes

        # Parse canonical IDs into (package_name, registry_type) pairs
        pkg_keys = _parse_canonical_ids(list(id_to_nodes.keys()))

        # Batch query package_mappings → repo_full_name
        pkg_to_repo = _batch_resolve_mappings(pkg_keys, db_path)

        # Collect unique repos that need risk data
        repos_needed = set(pkg_to_repo.values())

        # Batch query repo_graphs + repo_cves + repo_maintainers
        repo_risk_data = _batch_fetch_risk_data(repos_needed, db_path)

        # Apply risk metadata to each node
        for canonical_id, node_list in id_to_nodes.items():
            metadata = _build_risk_metadata(canonical_id, pkg_keys, pkg_to_repo, repo_risk_data)
            for node in node_list:
                node.risk_metadata = RiskMetadata(
                    risk_score=metadata.risk_score,
                    risk_level=metadata.risk_level,
                    vulnerability_count=metadata.vulnerability_count,
                    release_recency_days=metadata.release_recency_days,
                    maintainer_count=metadata.maintainer_count,
                    score_source=metadata.score_source,
                    score_completeness=metadata.score_completeness,
                )

        return nodes

    # ------------------------------------------------------------------
    # Risk level classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_risk_level(score: Optional[float]) -> Optional[str]:
        """Classify a 0-100 risk score into low / medium / high.

        Returns None when *score* is None.
        """
        if score is None:
            return None
        if score <= 30:
            return "low"
        if score <= 70:
            return "medium"
        return "high"

    @staticmethod
    def get_latest_updated_at(nodes: List[TreeNode], db_path: str) -> Optional[str]:
        """Return the most recent ``updated_at`` timestamp from repo_graphs rows used in enrichment.

        Returns None if no DB data was used (e.g. all nodes are repository roots or have no mappings).
        """
        if not nodes:
            return None

        # Collect unique canonical IDs (skip repository root nodes)
        canonical_ids: List[str] = []
        for node in nodes:
            if node.node_type != "repository":
                canonical_ids.append(node.id)

        if not canonical_ids:
            return None

        unique_ids = list(set(canonical_ids))
        pkg_keys = _parse_canonical_ids(unique_ids)
        pkg_to_repo = _batch_resolve_mappings(pkg_keys, db_path)

        repos_needed = set(pkg_to_repo.values())
        if not repos_needed:
            return None

        repo_risk_data = _batch_fetch_risk_data(repos_needed, db_path)
        if not repo_risk_data:
            return None

        latest: Optional[str] = None
        for _repo, data in repo_risk_data.items():
            ts = data.get("updated_at")
            if ts is not None:
                if latest is None or ts > latest:
                    latest = ts

        return latest



# ======================================================================
# Internal helpers (module-private)
# ======================================================================


def _parse_canonical_ids(
    canonical_ids: List[str],
) -> Dict[str, Tuple[str, str]]:
    """Parse ``pkg:{ecosystem}/{name}@{version}`` into (package_name, registry_type).

    Returns a mapping from canonical_id → (package_name, registry_type).
    """
    result: Dict[str, Tuple[str, str]] = {}
    for cid in canonical_ids:
        # Format: pkg:{ecosystem}/{name}@{version}
        try:
            without_prefix = cid
            if cid.startswith("pkg:"):
                without_prefix = cid[4:]
            slash_idx = without_prefix.index("/")
            ecosystem = without_prefix[:slash_idx]
            rest = without_prefix[slash_idx + 1 :]
            at_idx = rest.rfind("@")
            if at_idx != -1:
                name = rest[:at_idx]
            else:
                name = rest
            result[cid] = (name, ecosystem)
        except (ValueError, IndexError):
            logger.warning("Could not parse canonical ID: %s", cid)
    return result


def _batch_resolve_mappings(
    pkg_keys: Dict[str, Tuple[str, str]],
    db_path: str,
) -> Dict[str, str]:
    """Batch query ``package_mappings`` to resolve package → repo.

    Returns a mapping from canonical_id → repo_full_name.
    """
    if not pkg_keys:
        return {}

    result: Dict[str, str] = {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Build batch query with placeholders
            pairs = list(pkg_keys.items())
            placeholders = ",".join(["(?, ?)"] * len(pairs))
            params: List[Any] = []
            for _cid, (name, registry) in pairs:
                params.extend([name, registry])

            query = f"""
                SELECT package_name, registry_type, repo_full_name
                FROM package_mappings
                WHERE (package_name, registry_type) IN ({placeholders})
                  AND repo_full_name IS NOT NULL
            """
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            # Build reverse lookup: (name, registry) → repo
            mapping_lookup: Dict[Tuple[str, str], str] = {}
            for row in rows:
                mapping_lookup[(row["package_name"], row["registry_type"])] = row["repo_full_name"]

            # Map canonical IDs to repos
            for cid, (name, registry) in pairs:
                repo = mapping_lookup.get((name, registry))
                if repo:
                    result[cid] = repo
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to batch resolve package mappings")

    return result


def _batch_fetch_risk_data(
    repo_names: set,
    db_path: str,
) -> Dict[str, Dict[str, Any]]:
    """Batch fetch risk data for a set of repositories.

    Returns a mapping from repo_full_name → risk data dict with keys:
      risk_score, vulnerability_count, release_recency_days, maintainer_count
    """
    if not repo_names:
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            repo_list = list(repo_names)
            placeholders = ",".join(["?"] * len(repo_list))

            # 1. Fetch graph JSON for risk score and release info
            graph_query = f"""
                SELECT repo_full_name, graph_json, updated_at
                FROM repo_graphs
                WHERE repo_full_name IN ({placeholders})
            """
            cursor = conn.execute(graph_query, repo_list)
            graph_rows = {row["repo_full_name"]: row for row in cursor.fetchall()}

            # 2. Fetch vulnerability counts from repo_cves
            cve_query = f"""
                SELECT repo_full_name, COUNT(*) as cve_count
                FROM repo_cves
                WHERE repo_full_name IN ({placeholders})
                GROUP BY repo_full_name
            """
            cursor = conn.execute(cve_query, repo_list)
            cve_counts = {row["repo_full_name"]: row["cve_count"] for row in cursor.fetchall()}

            # 3. Fetch maintainer counts from repo_maintainers
            maint_query = f"""
                SELECT repo_full_name, COUNT(*) as maintainer_count
                FROM repo_maintainers
                WHERE repo_full_name IN ({placeholders})
                GROUP BY repo_full_name
            """
            cursor = conn.execute(maint_query, repo_list)
            maint_counts = {row["repo_full_name"]: row["maintainer_count"] for row in cursor.fetchall()}

            # Build result for each repo
            for repo in repo_list:
                graph_row = graph_rows.get(repo)
                if graph_row is None:
                    continue  # No repo_graphs entry

                risk_score = _extract_risk_score(graph_row["graph_json"])
                release_recency = _extract_release_recency(graph_row["graph_json"])

                result[repo] = {
                    "risk_score": risk_score,
                    "vulnerability_count": cve_counts.get(repo, 0),
                    "release_recency_days": release_recency,
                    "maintainer_count": maint_counts.get(repo),
                    "updated_at": graph_row["updated_at"],
                }
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to batch fetch risk data")

    return result


def _extract_risk_score(graph_json: str) -> Optional[float]:
    """Extract the overall risk score from graph JSON.

    The repo node stores ``maintenance_risk`` as a 0-1 float.
    We scale it to 0-100 for the tree view.
    """
    try:
        graph = json.loads(graph_json)
        for node in graph.get("nodes", []):
            if node.get("type") == "repo":
                raw = node.get("metadata", {}).get("maintenance_risk")
                if raw is not None:
                    return round(float(raw) * 100, 1)
        return None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _extract_release_recency(graph_json: str) -> Optional[int]:
    """Extract days since last release from graph JSON release nodes."""
    try:
        graph = json.loads(graph_json)
        for node in graph.get("nodes", []):
            if node.get("type") == "release":
                days = node.get("metadata", {}).get("days_since_release")
                if days is not None:
                    return int(days)
        return None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _build_risk_metadata(
    canonical_id: str,
    pkg_keys: Dict[str, Tuple[str, str]],
    pkg_to_repo: Dict[str, str],
    repo_risk_data: Dict[str, Dict[str, Any]],
) -> RiskMetadata:
    """Build a RiskMetadata instance for a single canonical ID."""
    repo = pkg_to_repo.get(canonical_id)

    # No mapping → unavailable
    if repo is None:
        return RiskMetadata(
            risk_score=None,
            risk_level=None,
            vulnerability_count=0,
            score_source="unavailable",
            score_completeness="missing",
        )

    risk_data = repo_risk_data.get(repo)

    # Mapping exists but no repo_graphs data → unavailable
    if risk_data is None:
        return RiskMetadata(
            risk_score=None,
            risk_level=None,
            vulnerability_count=0,
            score_source="unavailable",
            score_completeness="missing",
        )

    risk_score = risk_data.get("risk_score")
    vuln_count = risk_data.get("vulnerability_count", 0)
    release_recency = risk_data.get("release_recency_days")
    maintainer_count = risk_data.get("maintainer_count")

    # Determine completeness
    has_score = risk_score is not None
    has_vulns = True  # vulnerability_count always has a value (0 default)
    has_optional = release_recency is not None or maintainer_count is not None

    if has_score:
        completeness = "full" if has_optional else "partial"
    else:
        completeness = "missing"

    score_source = "repo_graph" if has_score else "unavailable"

    return RiskMetadata(
        risk_score=risk_score,
        risk_level=RiskMetadataEnricher._classify_risk_level(risk_score),
        vulnerability_count=vuln_count,
        release_recency_days=release_recency,
        maintainer_count=maintainer_count,
        score_source=score_source,
        score_completeness=completeness,
    )
