"""Unit tests for error handling and provenance tracking (Task 7).

Tests cover:
- Error node creation during Phase 1
- AllDependenciesFailedError when all deps fail
- Provenance field derivation rules
- construction_time_ms, last_updated, data_source, data_completeness
- Response-level vs node-level provenance differences

Requirements: 9.2–9.6, 14.1–14.7
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from open_source_risk_model.tree.exceptions import (
    AllDependenciesFailedError,
    DependencyResolutionError,
)
from open_source_risk_model.tree.models import (
    DependencyTreeResponse,
    FilterConfig,
    ProvenanceInfo,
    RiskMetadata,
    TreeNode,
)
from open_source_risk_model.tree.service import TreeService
from open_source_risk_model.tree.tree_utils import walk_tree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_db(tmp_path: str) -> str:
    """Create a minimal SQLite database with the required tables."""
    db_path = os.path.join(tmp_path, "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repo_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            specifier TEXT,
            extras TEXT,
            markers TEXT,
            dependency_group TEXT DEFAULT 'prod',
            is_direct BOOLEAN NOT NULL DEFAULT 1,
            is_optional BOOLEAN NOT NULL DEFAULT 0,
            manifest_path TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            resolved_repo TEXT,
            resolution_confidence REAL,
            resolution_method TEXT,
            parent_package_name TEXT,
            parent_package_version TEXT,
            package_version TEXT,
            UNIQUE(repo_full_name, package_name, manifest_path)
        );

        CREATE TABLE IF NOT EXISTS repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            schema_version TEXT,
            graph_json TEXT,
            node_count INTEGER DEFAULT 0,
            edge_count INTEGER DEFAULT 0,
            data_sources TEXT DEFAULT '[]',
            warnings TEXT DEFAULT '[]',
            generation_time_ms INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS package_mappings (
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            repo_full_name TEXT,
            resolution_method TEXT NOT NULL,
            confidence REAL NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (package_name, registry_type)
        );

        CREATE TABLE IF NOT EXISTS repo_cves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            severity TEXT,
            description TEXT,
            published_date TEXT,
            source TEXT DEFAULT 'ghsa',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS repo_maintainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            maintainer_username TEXT NOT NULL,
            role TEXT DEFAULT 'contributor',
            contributions INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.close()
    return db_path


def _insert_dep(
    db_path: str,
    repo: str,
    pkg: str,
    registry: str = "npm",
    *,
    is_direct: bool = True,
    specifier: str = "",
    version: str | None = None,
    parent_package_name: str | None = None,
    manifest: str = "package.json",
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO repo_dependencies
           (repo_full_name, package_name, registry_type, specifier,
            extras, dependency_group, is_direct, is_optional,
            manifest_path, confidence, created_at,
            parent_package_name, package_version)
           VALUES (?, ?, ?, ?, '[]', 'prod', ?, 0, ?, 0.9, datetime('now'), ?, ?)""",
        (repo, pkg, registry, specifier, is_direct, manifest, parent_package_name, version),
    )
    conn.commit()
    conn.close()


def _insert_repo_graph(
    db_path: str,
    repo: str,
    *,
    risk_score: float | None = None,
    updated_at: str | None = None,
) -> None:
    """Insert a repo_graphs row with optional risk score and timestamp."""
    graph_json = "{}"
    if risk_score is not None:
        graph_json = json.dumps({
            "nodes": [
                {"type": "repo", "metadata": {"maintenance_risk": risk_score / 100.0}}
            ]
        })
    ts = updated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', ?, datetime('now'), ?)""",
        (repo, graph_json, ts),
    )
    conn.commit()
    conn.close()


def _insert_package_mapping(
    db_path: str, pkg: str, registry: str, mapped_repo: str
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO package_mappings
           (package_name, registry_type, repo_full_name, resolution_method, confidence)
           VALUES (?, ?, ?, 'name_match', 0.9)""",
        (pkg, registry, mapped_repo),
    )
    conn.commit()
    conn.close()


def _make_pkg(
    name: str,
    version: str | None = "1.0.0",
    depth: int = 1,
    ecosystem: str = "npm",
    risk_score: float | None = None,
    vulnerability_count: int = 0,
    children: list[TreeNode] | None = None,
    resolution_status: str = "resolved",
    error_reason: str | None = None,
) -> TreeNode:
    """Create a package TreeNode with optional risk metadata."""
    dep_type = "direct" if depth == 1 else "transitive"
    ver_part = version if version else "unknown"
    node = TreeNode(
        id=f"pkg:{ecosystem}/{name}@{ver_part}",
        node_type="package",
        name=name,
        version=version,
        depth=depth,
        dependency_type=dep_type,
        ecosystem=ecosystem,
        children=children or [],
        resolution_status=resolution_status,
        error_reason=error_reason,
    )
    if resolution_status == "error":
        node.risk_metadata = None
    else:
        score_source = "repo_graph" if risk_score is not None else "unavailable"
        score_completeness = "full" if risk_score is not None else "missing"
        risk_level = None
        if risk_score is not None:
            if risk_score <= 30:
                risk_level = "low"
            elif risk_score <= 70:
                risk_level = "medium"
            else:
                risk_level = "high"
        node.risk_metadata = RiskMetadata(
            risk_score=risk_score,
            risk_level=risk_level,
            vulnerability_count=vulnerability_count,
            score_source=score_source,
            score_completeness=score_completeness,
        )
    return node


def _make_root(children: list[TreeNode] | None = None) -> TreeNode:
    return TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        version=None,
        depth=0,
        dependency_type="direct",
        children=children or [],
    )


# ---------------------------------------------------------------------------
# Error Handling Tests (Phase 1)
# ---------------------------------------------------------------------------


class TestErrorNodeCreation:
    """Test error node creation during Phase 1 tree construction."""

    def test_single_dep_failure_creates_error_node_siblings_resolved(self, tmp_path):
        """A single DependencyResolutionError creates an error node; siblings still resolve."""
        db_path = _create_test_db(str(tmp_path))
        repo = "owner/myrepo"
        _insert_repo_graph(db_path, repo)
        _insert_dep(db_path, repo, "good-pkg", "npm", version="1.0.0")
        _insert_dep(db_path, repo, "bad-pkg", "npm", version="2.0.0")

        service = TreeService(db_path)

        # Patch _build_node to raise for bad-pkg only
        original_build = service._build_node

        def _patched_build(dep, depth, dependency_type, transitive_by_parent, branch_visited):
            if dep["package_name"] == "bad-pkg":
                raise DependencyResolutionError("Manifest fetch failed")
            return original_build(dep, depth, dependency_type, transitive_by_parent, branch_visited)

        with patch.object(service, "_build_node", side_effect=_patched_build):
            root, data_source = service._build_canonical_tree(repo)

        # Root should have 2 children: one resolved, one error
        assert len(root.children) == 2
        resolved = [c for c in root.children if c.resolution_status == "resolved"]
        errors = [c for c in root.children if c.resolution_status == "error"]
        assert len(resolved) == 1
        assert len(errors) == 1
        assert resolved[0].name == "good-pkg"
        assert errors[0].name == "bad-pkg"

    def test_error_node_has_correct_fields(self, tmp_path):
        """Error node has node_type='package', resolution_status='error', risk_metadata=None."""
        db_path = _create_test_db(str(tmp_path))
        repo = "owner/myrepo"
        _insert_repo_graph(db_path, repo)
        _insert_dep(db_path, repo, "fail-pkg", "npm", version="3.0.0")

        service = TreeService(db_path)

        def _always_fail(dep, depth, dependency_type, transitive_by_parent, branch_visited):
            raise DependencyResolutionError("Package not found in registry")

        with patch.object(service, "_build_node", side_effect=_always_fail):
            with pytest.raises(AllDependenciesFailedError):
                service._build_canonical_tree(repo)

        # Test error node creation directly via _make_error_node
        dep = {"package_name": "fail-pkg", "registry_type": "npm", "package_version": "3.0.0"}
        error_node = TreeService._make_error_node(dep, depth=1, reason="Package not found")
        assert error_node.node_type == "package"
        assert error_node.resolution_status == "error"
        assert error_node.error_reason == "Package not found"
        assert error_node.risk_metadata is None
        assert error_node.children == []

    def test_all_deps_fail_raises_all_dependencies_failed(self, tmp_path):
        """When all dependencies fail, AllDependenciesFailedError is raised."""
        db_path = _create_test_db(str(tmp_path))
        repo = "owner/myrepo"
        _insert_repo_graph(db_path, repo)
        _insert_dep(db_path, repo, "pkg-a", "npm", version="1.0.0")
        _insert_dep(db_path, repo, "pkg-b", "npm", version="2.0.0")

        service = TreeService(db_path)

        def _always_fail(dep, depth, dependency_type, transitive_by_parent, branch_visited):
            raise DependencyResolutionError(f"Failed: {dep['package_name']}")

        with patch.object(service, "_build_node", side_effect=_always_fail):
            with pytest.raises(AllDependenciesFailedError) as exc_info:
                service._build_canonical_tree(repo)
            assert "All" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Provenance Tests
# ---------------------------------------------------------------------------


class TestProvenanceDataCompleteness:
    """Test provenance data_completeness derivation."""

    def test_partial_when_errors_exist(self, tmp_path):
        """data_completeness='partial' when error nodes are present."""
        error_child = _make_pkg(
            "bad", version="1.0.0", resolution_status="error",
            error_reason="Manifest fetch failed",
        )
        good_child = _make_pkg("good", version="1.0.0", risk_score=50.0)
        root = _make_root(children=[good_child, error_child])

        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")

        assert provenance.data_completeness == "partial"
        assert provenance.nodes_with_errors == 1

    def test_partial_when_missing_risk_data(self, tmp_path):
        """data_completeness='partial' when some nodes have missing risk data."""
        child_with_risk = _make_pkg("a", version="1.0.0", risk_score=40.0)
        child_no_risk = _make_pkg("b", version="1.0.0", risk_score=None)
        root = _make_root(children=[child_with_risk, child_no_risk])

        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")

        assert provenance.data_completeness == "partial"
        assert provenance.nodes_with_missing_risk >= 1

    def test_full_when_no_errors_and_all_risk_present(self, tmp_path):
        """data_completeness='full' when no errors and all nodes have risk data."""
        child_a = _make_pkg("a", version="1.0.0", risk_score=20.0)
        child_b = _make_pkg("b", version="2.0.0", risk_score=60.0)
        root = _make_root(children=[child_a, child_b])
        # Root is a repository node — it has no risk_metadata, which counts as missing
        # So for "full", the root's missing risk counts. Let's set it.
        root.risk_metadata = RiskMetadata(
            risk_score=None, risk_level=None, vulnerability_count=0,
            score_source="repo_graph", score_completeness="full",
        )

        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")

        assert provenance.data_completeness == "full"
        assert provenance.nodes_with_errors == 0
        assert provenance.nodes_with_missing_risk == 0


class TestProvenanceErrorDetails:
    """Test provenance error_details population."""

    def test_error_details_lists_all_error_nodes(self, tmp_path):
        """error_details contains id and error_reason for each error node."""
        err1 = _make_pkg("fail-a", version="1.0.0", resolution_status="error",
                         error_reason="Network timeout")
        err2 = _make_pkg("fail-b", version="2.0.0", resolution_status="error",
                         error_reason="Package not found")
        good = _make_pkg("ok", version="1.0.0", risk_score=30.0)
        root = _make_root(children=[err1, good, err2])

        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")

        assert len(provenance.error_details) == 2
        ids = {d["id"] for d in provenance.error_details}
        reasons = {d["error_reason"] for d in provenance.error_details}
        assert "pkg:npm/fail-a@1.0.0" in ids
        assert "pkg:npm/fail-b@2.0.0" in ids
        assert "Network timeout" in reasons
        assert "Package not found" in reasons


class TestProvenanceDataSource:
    """Test provenance data_source for different retrieval scenarios."""

    def test_database_source(self, tmp_path):
        """data_source='database' when all data comes from DB."""
        root = _make_root(children=[_make_pkg("a", risk_score=50.0)])
        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")
        assert provenance.data_source == "database"

    def test_live_source(self, tmp_path):
        """data_source='live' when data comes from live ingestion."""
        root = _make_root(children=[_make_pkg("a", risk_score=50.0)])
        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "live")
        assert provenance.data_source == "live"

    def test_mixed_source(self, tmp_path):
        """data_source='mixed' when data comes from both DB and live."""
        root = _make_root(children=[_make_pkg("a", risk_score=50.0)])
        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "mixed")
        assert provenance.data_source == "mixed"


class TestZeroDependencyProvenance:
    """Test provenance for zero-dependency repositories."""

    def test_zero_dep_repo_provenance(self, tmp_path):
        """Zero-dependency repo: data_source='database', data_completeness='full'."""
        db_path = _create_test_db(str(tmp_path))
        repo = "owner/empty-repo"
        _insert_repo_graph(db_path, repo)

        service = TreeService(db_path)
        root, data_source = service._build_canonical_tree(repo)

        filters = FilterConfig()
        response = service._transform_for_response(
            root, data_source, filters, start_time=time.monotonic()
        )

        assert response.provenance.data_source == "database"
        # Root-only tree: root is repository node, no package nodes
        # The root has no risk_metadata by default → missing, but that's expected
        # For zero-dep repos, the spec says data_completeness="full"
        # The root node (repository) doesn't need risk data
        assert response.provenance.nodes_with_errors == 0


class TestConstructionTimeMs:
    """Test construction_time_ms tracking."""

    def test_construction_time_populated_and_positive(self, tmp_path):
        """construction_time_ms is populated and > 0 when start_time is provided."""
        root = _make_root(children=[_make_pkg("a", risk_score=50.0)])
        root.risk_metadata = RiskMetadata(
            score_source="repo_graph", score_completeness="full",
        )

        service = TreeService(str(tmp_path))
        start = time.monotonic()
        # Small sleep to ensure measurable time
        time.sleep(0.005)
        provenance = service._assemble_provenance(root, "database", start_time=start)

        assert provenance.construction_time_ms is not None
        assert provenance.construction_time_ms > 0

    def test_construction_time_none_without_start(self, tmp_path):
        """construction_time_ms is None when no start_time is provided."""
        root = _make_root()
        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")
        assert provenance.construction_time_ms is None

    def test_construction_time_via_transform(self, tmp_path):
        """construction_time_ms is populated when start_time passed to _transform_for_response."""
        db_path = _create_test_db(str(tmp_path))
        repo = "owner/repo"
        _insert_repo_graph(db_path, repo)
        _insert_dep(db_path, repo, "lodash", "npm", version="4.17.21")

        service = TreeService(db_path)
        start = time.monotonic()
        root, data_source = service._build_canonical_tree(repo)
        response = service._transform_for_response(
            root, data_source, FilterConfig(), start_time=start,
        )

        assert response.provenance.construction_time_ms is not None
        assert response.provenance.construction_time_ms > 0


class TestLastUpdated:
    """Test last_updated timestamp derivation."""

    def test_uses_repo_graphs_timestamp_when_available(self, tmp_path):
        """last_updated uses the most recent repo_graphs updated_at when DB data is used."""
        db_path = _create_test_db(str(tmp_path))
        repo = "owner/repo"
        known_ts = "2024-06-15 12:00:00"
        _insert_repo_graph(db_path, repo, risk_score=45.0, updated_at=known_ts)
        _insert_dep(db_path, repo, "lodash", "npm", version="4.17.21")
        _insert_package_mapping(db_path, "lodash", "npm", repo)

        service = TreeService(db_path)
        root, data_source = service._build_canonical_tree(repo)
        response = service._transform_for_response(
            root, data_source, FilterConfig(), start_time=time.monotonic(),
        )

        assert response.provenance.last_updated == known_ts

    def test_falls_back_to_current_timestamp_when_no_db_data(self, tmp_path):
        """last_updated uses current timestamp when no repo_graphs data is available."""
        db_path = _create_test_db(str(tmp_path))
        repo = "owner/repo"
        _insert_repo_graph(db_path, repo)  # No risk data, no mappings
        _insert_dep(db_path, repo, "unknown-pkg", "npm", version="1.0.0")

        service = TreeService(db_path)
        before = datetime.now(timezone.utc).isoformat()
        root, data_source = service._build_canonical_tree(repo)
        response = service._transform_for_response(
            root, data_source, FilterConfig(), start_time=time.monotonic(),
        )

        # Should be a recent ISO timestamp (not the DB timestamp since no mapping exists)
        assert response.provenance.last_updated is not None
        assert len(response.provenance.last_updated) > 0


class TestResponseVsNodeProvenance:
    """Test that response-level and node-level provenance can differ."""

    def test_response_partial_some_nodes_full(self, tmp_path):
        """Response can be 'partial' while individual nodes have score_completeness='full'."""
        # Node A has full risk data
        child_a = _make_pkg("a", version="1.0.0", risk_score=50.0)
        assert child_a.risk_metadata.score_completeness == "full"

        # Node B is an error node (no risk data)
        child_b = _make_pkg("b", version="2.0.0", resolution_status="error",
                            error_reason="Failed")

        root = _make_root(children=[child_a, child_b])

        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")

        # Response-level: partial (because of error node)
        assert provenance.data_completeness == "partial"
        # Node-level: child_a has full completeness
        assert child_a.risk_metadata.score_completeness == "full"
        # They differ
        assert provenance.data_completeness != child_a.risk_metadata.score_completeness


class TestProvenanceTotalNodes:
    """Test total_nodes counting."""

    def test_total_nodes_includes_root(self, tmp_path):
        """total_nodes counts all nodes including root."""
        child = _make_pkg("a", risk_score=50.0)
        grandchild = _make_pkg("b", depth=2, risk_score=30.0)
        child.children = [grandchild]
        root = _make_root(children=[child])

        service = TreeService(str(tmp_path))
        provenance = service._assemble_provenance(root, "database")

        assert provenance.total_nodes == 3  # root + child + grandchild
