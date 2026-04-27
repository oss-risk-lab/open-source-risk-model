"""Unit tests for the dependency tree API endpoint and TreeService.get_dependency_tree()."""

from __future__ import annotations

import os
import sqlite3
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app
from open_source_risk_model.tree.exceptions import (
    AllDependenciesFailedError,
    RepositoryNotFoundError,
    TreeConstructionTimeoutError,
)
from open_source_risk_model.tree.models import (
    DependencyTreeResponse,
    FilterConfig,
    ProvenanceInfo,
    SummaryMetrics,
    TreeNode,
)
from open_source_risk_model.tree.service import TreeService


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


def _insert_repo_graph(db_path: str, repo: str, *, risk_score: float = 45.0) -> None:
    graph_json = f'{{"risk_score": {risk_score}}}'
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', ?, datetime('now'), datetime('now'))""",
        (repo, graph_json),
    )
    conn.commit()
    conn.close()


def _insert_package_mapping(
    db_path: str, pkg: str, registry: str, mapped_repo: str
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO package_mappings
           (package_name, registry_type, repo_full_name, resolution_method, confidence)
           VALUES (?, ?, ?, 'name_match', 0.9)""",
        (pkg, registry, mapped_repo),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# TestClient fixture
# ---------------------------------------------------------------------------

client = TestClient(app)


# ---------------------------------------------------------------------------
# TreeService.get_dependency_tree() unit tests
# ---------------------------------------------------------------------------


class TestGetDependencyTree:
    """Tests for the public entry point method."""

    def test_returns_response_for_valid_repo(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        svc = TreeService(db_path=db_path)
        resp = svc.get_dependency_tree("owner/repo")

        assert isinstance(resp, DependencyTreeResponse)
        assert resp.repo == "owner/repo"
        assert resp.tree is not None
        assert resp.tree.depth == 0
        assert resp.tree.node_type == "repository"
        assert len(resp.tree.children) == 1
        assert resp.summary_metrics is not None
        assert resp.provenance is not None

    def test_zero_dependency_repo(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/empty")

        svc = TreeService(db_path=db_path)
        resp = svc.get_dependency_tree("owner/empty")

        assert resp.repo == "owner/empty"
        assert resp.tree.children == []
        assert resp.summary_metrics.total_dependencies == 0
        # Root node (repository) has no risk metadata, so provenance is partial
        assert resp.provenance.data_source == "database"

    def test_repo_not_found_raises(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        svc = TreeService(db_path=db_path)

        with pytest.raises(RepositoryNotFoundError):
            svc.get_dependency_tree("nonexistent/repo")

    def test_timeout_raises(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        svc = TreeService(db_path=db_path)
        # Use an extremely small timeout to trigger the error
        with pytest.raises(TreeConstructionTimeoutError):
            svc.get_dependency_tree("owner/repo", timeout_seconds=0.0)

    def test_filters_passed_through(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        svc = TreeService(db_path=db_path)
        resp = svc.get_dependency_tree(
            "owner/repo",
            direct_only=True,
        )

        assert "direct_only" in resp.summary_metrics.filters_applied

    def test_sort_by_passed_through(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "b-pkg", "npm", version="1.0.0")
        _insert_dep(db_path, "owner/repo", "a-pkg", "npm", version="2.0.0",
                     manifest="package2.json")

        svc = TreeService(db_path=db_path)
        resp = svc.get_dependency_tree("owner/repo", sort_by="name")

        names = [c.name for c in resp.tree.children]
        assert names == sorted(names)

    def test_max_depth_passed_through(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "a", "npm", version="1.0")
        _insert_dep(db_path, "owner/repo", "b", "npm", is_direct=False,
                     parent_package_name="a", version="2.0",
                     manifest="package2.json")

        svc = TreeService(db_path=db_path)
        resp = svc.get_dependency_tree("owner/repo", max_depth=1)

        assert "max_depth" in resp.summary_metrics.filters_applied
        # All nodes should be at depth <= 1
        for child in resp.tree.children:
            assert child.depth <= 1

    def test_truncate_after_children_passed_through(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        for i in range(5):
            _insert_dep(db_path, "owner/repo", f"pkg-{i}", "npm",
                         version="1.0", manifest=f"m{i}.json")

        svc = TreeService(db_path=db_path)
        resp = svc.get_dependency_tree("owner/repo", truncate_after_children=2)

        assert len(resp.tree.children) == 2
        assert resp.tree.children_truncated is True
        assert resp.tree.child_count == 5


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDependencyTreeEndpoint:
    """Tests for GET /repos/{repo_id}/dependency-tree."""

    def test_valid_repo_returns_200(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "facebook/react")
        _insert_dep(db_path, "facebook/react", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/facebook/react/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()
        assert "repo" in data
        assert "tree" in data
        assert "summary_metrics" in data
        assert "provenance" in data
        assert data["repo"] == "facebook/react"
        assert data["tree"]["node_type"] == "repository"
        assert data["tree"]["depth"] == 0

    def test_zero_dependency_repo_returns_200(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/empty")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/empty/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tree"]["children"] == []
        assert data["summary_metrics"]["total_dependencies"] == 0
        assert data["provenance"]["data_source"] == "database"

    def test_unknown_repo_returns_404(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/nonexistent/repo/dependency-tree")

        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data["detail"]

    def test_invalid_max_depth_zero_returns_422(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?max_depth=0")

        # FastAPI returns 422 for validation errors on Query params
        assert resp.status_code == 422

    def test_invalid_max_depth_eleven_returns_422(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?max_depth=11")

        assert resp.status_code == 422

    def test_invalid_sort_by_returns_400(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?sort_by=invalid")

        assert resp.status_code == 400
        data = resp.json()
        assert "INVALID_PARAMETER" in data["detail"]["error"]["code"]

    def test_timeout_returns_503(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            with patch.object(
                TreeService,
                "get_dependency_tree",
                side_effect=TreeConstructionTimeoutError("Timeout"),
            ):
                resp = client.get("/repos/owner/repo/dependency-tree")

        assert resp.status_code == 503
        assert "TIMEOUT" in resp.json()["detail"]["error"]["code"]

    def test_all_deps_failed_returns_503(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            with patch.object(
                TreeService,
                "get_dependency_tree",
                side_effect=AllDependenciesFailedError("All failed"),
            ):
                resp = client.get("/repos/owner/repo/dependency-tree")

        assert resp.status_code == 503
        assert "ALL_DEPS_FAILED" in resp.json()["detail"]["error"]["code"]

    def test_unexpected_error_returns_500(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            with patch.object(
                TreeService,
                "get_dependency_tree",
                side_effect=RuntimeError("Unexpected"),
            ):
                resp = client.get("/repos/owner/repo/dependency-tree")

        assert resp.status_code == 500

    def test_partial_failure_returns_200_with_error_nodes(self, tmp_path):
        """When some deps fail, we still get 200 with error nodes in the tree."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "good-pkg", "npm", version="1.0.0")
        _insert_dep(db_path, "owner/repo", "bad-pkg", "npm", version="2.0.0",
                     manifest="m2.json")

        # Build a response with an error node
        error_node = TreeNode(
            id="pkg:npm/bad-pkg@2.0.0",
            node_type="package",
            name="bad-pkg",
            version="2.0.0",
            depth=1,
            dependency_type="direct",
            ecosystem="npm",
            resolution_status="error",
            error_reason="Resolution failed",
            children=[],
        )
        good_node = TreeNode(
            id="pkg:npm/good-pkg@1.0.0",
            node_type="package",
            name="good-pkg",
            version="1.0.0",
            depth=1,
            dependency_type="direct",
            ecosystem="npm",
            resolution_status="resolved",
        )
        root = TreeNode(
            id="owner/repo",
            node_type="repository",
            name="owner/repo",
            depth=0,
            dependency_type="direct",
            children=[good_node, error_node],
        )
        mock_response = DependencyTreeResponse(
            repo="owner/repo",
            tree=root,
            summary_metrics=SummaryMetrics(
                total_dependencies=2,
                direct_dependencies=2,
                transitive_dependencies=0,
            ),
            provenance=ProvenanceInfo(
                data_source="database",
                data_completeness="partial",
                last_updated="2024-01-01T00:00:00Z",
                nodes_with_errors=1,
                error_details=[{"id": "pkg:npm/bad-pkg@2.0.0", "error_reason": "Resolution failed"}],
            ),
        )

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            with patch.object(
                TreeService, "get_dependency_tree", return_value=mock_response
            ):
                resp = client.get("/repos/owner/repo/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()
        assert data["provenance"]["data_completeness"] == "partial"
        assert data["provenance"]["nodes_with_errors"] == 1

    def test_query_params_high_risk_only(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?high_risk_only=true")

        assert resp.status_code == 200
        data = resp.json()
        assert "high_risk_only" in data["summary_metrics"]["filters_applied"]

    def test_query_params_vulnerable_only(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?vulnerable_only=true")

        assert resp.status_code == 200
        data = resp.json()
        assert "vulnerable_only" in data["summary_metrics"]["filters_applied"]

    def test_query_params_direct_only(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?direct_only=true")

        assert resp.status_code == 200
        data = resp.json()
        assert "direct_only" in data["summary_metrics"]["filters_applied"]

    def test_query_params_sort_by(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "b-pkg", "npm", version="1.0.0")
        _insert_dep(db_path, "owner/repo", "a-pkg", "npm", version="2.0.0",
                     manifest="m2.json")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?sort_by=name")

        assert resp.status_code == 200
        data = resp.json()
        names = [c["name"] for c in data["tree"]["children"]]
        assert names == sorted(names)

    def test_query_params_truncate_after_children(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        for i in range(5):
            _insert_dep(db_path, "owner/repo", f"pkg-{i}", "npm",
                         version="1.0", manifest=f"m{i}.json")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?truncate_after_children=2")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tree"]["children"]) == 2

    def test_query_params_max_depth(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "a", "npm", version="1.0")
        _insert_dep(db_path, "owner/repo", "b", "npm", is_direct=False,
                     parent_package_name="a", version="2.0",
                     manifest="m2.json")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree?max_depth=1")

        assert resp.status_code == 200
        data = resp.json()
        assert "max_depth" in data["summary_metrics"]["filters_applied"]


class TestResponseSchemaValidation:
    """Validate the response structure matches the canonical schema."""

    def test_response_has_all_top_level_fields(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        data = resp.json()
        assert "repo" in data
        assert "tree" in data
        assert "summary_metrics" in data
        assert "provenance" in data

    def test_tree_node_has_canonical_fields(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        tree = resp.json()["tree"]
        # Root node fields
        assert "id" in tree
        assert "node_type" in tree
        assert "name" in tree
        assert "version" in tree  # Always included even if None
        assert "depth" in tree
        assert "children" in tree
        assert "dependency_type" in tree

        # Child node fields
        if tree["children"]:
            child = tree["children"][0]
            assert "id" in child
            assert "node_type" in child
            assert "name" in child
            assert "version" in child
            assert "depth" in child
            assert "dependency_type" in child

    def test_summary_metrics_has_required_fields(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        metrics = resp.json()["summary_metrics"]
        assert "total_dependencies" in metrics
        assert "direct_dependencies" in metrics
        assert "transitive_dependencies" in metrics
        assert "high_risk_count" in metrics
        assert "vulnerable_count" in metrics
        assert "max_depth" in metrics
        assert "filters_applied" in metrics

    def test_provenance_has_required_fields(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        prov = resp.json()["provenance"]
        assert "data_source" in prov
        assert "data_completeness" in prov
        assert "last_updated" in prov
        assert "total_nodes" in prov
        assert "nodes_with_risk_data" in prov
        assert "nodes_with_missing_risk" in prov
        assert "nodes_with_errors" in prov
        assert "error_details" in prov

    def test_nested_tree_serialization(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "a", "npm", version="1.0")
        _insert_dep(db_path, "owner/repo", "b", "npm", is_direct=False,
                     parent_package_name="a", version="2.0",
                     manifest="m2.json")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        assert resp.status_code == 200
        tree = resp.json()["tree"]
        assert tree["depth"] == 0
        assert len(tree["children"]) >= 1
        # Find the child "a" and check it has a nested child "b"
        a_node = next((c for c in tree["children"] if c["name"] == "a"), None)
        assert a_node is not None
        assert a_node["depth"] == 1
        if a_node["children"]:
            b_node = a_node["children"][0]
            assert b_node["depth"] == 2
            assert b_node["name"] == "b"

    def test_valid_sort_by_values_accepted(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep(db_path, "owner/repo", "lodash", "npm", version="4.17.21")

        for sort_val in ["risk_score", "name", "vulnerability_count"]:
            with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
                resp = client.get(f"/repos/owner/repo/dependency-tree?sort_by={sort_val}")
            assert resp.status_code == 200, f"sort_by={sort_val} should be accepted"
