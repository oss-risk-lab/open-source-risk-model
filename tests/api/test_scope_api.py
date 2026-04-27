"""API response tests for dependency scope classification fields.

Validates: Requirements 10.1, 10.2, 15.6

Tests verify that:
- Scope fields appear in dependency list endpoint responses
- Scope fields appear in tree endpoint responses (TreeNode, SummaryMetrics)
- scope_counts_are_direct_only is True
- scope_classification_label is present
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from open_source_risk_model.tree.models import SummaryMetrics, TreeNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_db(tmp_path: str) -> str:
    """Create a minimal SQLite database with scope columns."""
    db_path = os.path.join(tmp_path, "scope_test.db")
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
            dependency_scope TEXT DEFAULT 'unknown',
            scope_confidence TEXT DEFAULT 'low',
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


def _insert_dep_with_scope(
    db_path: str,
    repo: str,
    pkg: str,
    registry: str = "npm",
    *,
    scope: str = "runtime",
    scope_conf: str = "high",
    group: str = "prod",
    manifest: str = "package.json",
    version: str | None = None,
) -> None:
    """Insert a dependency row with scope fields."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO repo_dependencies
           (repo_full_name, package_name, registry_type, specifier,
            extras, dependency_group, is_direct, is_optional,
            manifest_path, confidence, created_at,
            dependency_scope, scope_confidence, package_version)
           VALUES (?, ?, ?, '', '[]', ?, 1, 0, ?, 0.9, ?, ?, ?, ?)""",
        (repo, pkg, registry, group, manifest, now, scope, scope_conf, version),
    )
    conn.commit()
    conn.close()


def _insert_repo_graph(db_path: str, repo: str) -> None:
    """Insert a minimal repo_graphs row so the repo is 'known'."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', '{}', datetime('now'), datetime('now'))""",
        (repo,),
    )
    conn.commit()
    conn.close()


client = TestClient(app)


# ---------------------------------------------------------------------------
# Model serialization tests
# ---------------------------------------------------------------------------


class TestSummaryMetricsScopeFields:
    """Verify SummaryMetrics.to_dict() includes scope classification fields."""

    def test_scope_counts_are_direct_only_is_true(self):
        metrics = SummaryMetrics()
        d = metrics.to_dict()
        assert d["scope_counts_are_direct_only"] is True

    def test_scope_classification_label_present(self):
        metrics = SummaryMetrics()
        d = metrics.to_dict()
        assert d["scope_classification_label"] == "Direct dependencies, classified from manifests"

    def test_scope_note_present(self):
        metrics = SummaryMetrics()
        d = metrics.to_dict()
        assert "scope_note" in d
        assert "classified from manifests" in d["scope_note"]

    def test_direct_scope_count_fields_present(self):
        metrics = SummaryMetrics(
            direct_runtime_dependency_count=3,
            direct_dev_dependency_count=2,
            direct_test_dependency_count=1,
            direct_build_dependency_count=0,
            direct_optional_dependency_count=1,
            direct_peer_dependency_count=0,
            direct_unknown_dependency_count=0,
            direct_total_dependency_count=7,
        )
        d = metrics.to_dict()
        assert d["direct_runtime_dependency_count"] == 3
        assert d["direct_dev_dependency_count"] == 2
        assert d["direct_test_dependency_count"] == 1
        assert d["direct_build_dependency_count"] == 0
        assert d["direct_optional_dependency_count"] == 1
        assert d["direct_peer_dependency_count"] == 0
        assert d["direct_unknown_dependency_count"] == 0
        assert d["direct_total_dependency_count"] == 7


class TestTreeNodeScopeFields:
    """Verify TreeNode.to_dict() includes scope fields when set."""

    def test_scope_included_when_set(self):
        node = TreeNode(
            id="pkg:npm/lodash@4.17.21",
            name="lodash",
            dependency_scope="runtime",
            scope_confidence="high",
        )
        d = node.to_dict()
        assert d["dependency_scope"] == "runtime"
        assert d["scope_confidence"] == "high"

    def test_scope_omitted_when_none(self):
        node = TreeNode(id="pkg:npm/lodash@4.17.21", name="lodash")
        d = node.to_dict()
        assert "dependency_scope" not in d
        assert "scope_confidence" not in d


# ---------------------------------------------------------------------------
# Data layer tests — DependencyRepository returns scope fields
# ---------------------------------------------------------------------------


class TestDependencyRepositoryScopeFields:
    """Verify get_dependencies() returns scope fields from the database."""

    def test_scope_fields_returned(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_dep_with_scope(
            db_path, "owner/repo", "lodash", scope="runtime", scope_conf="high"
        )

        from open_source_risk_model.persistence.dependency_repo import DependencyRepository

        repo = DependencyRepository(db_path=db_path)
        deps = repo.get_dependencies("owner/repo")

        assert len(deps) == 1
        assert deps[0]["dependency_scope"] == "runtime"
        assert deps[0]["scope_confidence"] == "high"

    def test_default_scope_for_unclassified(self, tmp_path):
        """Rows inserted without explicit scope get defaults."""
        db_path = _create_test_db(str(tmp_path))
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO repo_dependencies
               (repo_full_name, package_name, registry_type, specifier,
                extras, dependency_group, is_direct, is_optional,
                manifest_path, confidence, created_at)
               VALUES (?, ?, ?, '', '[]', 'prod', 1, 0, 'package.json', 0.9, ?)""",
            ("owner/repo", "express", "npm", now),
        )
        conn.commit()
        conn.close()

        from open_source_risk_model.persistence.dependency_repo import DependencyRepository

        repo = DependencyRepository(db_path=db_path)
        deps = repo.get_dependencies("owner/repo")

        assert len(deps) == 1
        assert deps[0]["dependency_scope"] == "unknown"
        assert deps[0]["scope_confidence"] == "low"


# ---------------------------------------------------------------------------
# API endpoint tests — dependency list
# ---------------------------------------------------------------------------


class TestDependencyListEndpointScopeFields:
    """Verify GET /api/repos/{owner}/{repo}/dependencies includes scope fields."""

    def test_scope_fields_in_dependency_response(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_dep_with_scope(
            db_path, "test/repo", "react", scope="runtime", scope_conf="high"
        )
        _insert_dep_with_scope(
            db_path, "test/repo", "jest", scope="dev", scope_conf="high",
            group="dev", manifest="package.json",
        )

        from open_source_risk_model.persistence.dependency_repo import DependencyRepository

        mock_repo = DependencyRepository(db_path=db_path)

        with patch("api.app.dependency_repo", mock_repo):
            resp = client.get("/api/repos/test/repo/dependencies")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

        deps_by_name = {d["package_name"]: d for d in data["dependencies"]}

        assert deps_by_name["react"]["dependency_scope"] == "runtime"
        assert deps_by_name["react"]["scope_confidence"] == "high"
        assert deps_by_name["jest"]["dependency_scope"] == "dev"
        assert deps_by_name["jest"]["scope_confidence"] == "high"


# ---------------------------------------------------------------------------
# API endpoint tests — dependency tree
# ---------------------------------------------------------------------------


class TestDependencyTreeEndpointScopeFields:
    """Verify GET /repos/{repo_id}/dependency-tree includes scope fields."""

    def test_tree_node_has_scope_fields(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep_with_scope(
            db_path, "owner/repo", "lodash", scope="runtime", scope_conf="high",
            version="4.17.21",
        )

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()
        children = data["tree"]["children"]
        assert len(children) == 1
        assert children[0]["dependency_scope"] == "runtime"
        assert children[0]["scope_confidence"] == "high"

    def test_summary_metrics_scope_counts(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep_with_scope(db_path, "owner/repo", "react", scope="runtime", scope_conf="high")
        _insert_dep_with_scope(db_path, "owner/repo", "jest", scope="dev", scope_conf="high",
                               group="dev")
        _insert_dep_with_scope(db_path, "owner/repo", "mocha", scope="test", scope_conf="medium",
                               group="test")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        assert resp.status_code == 200
        metrics = resp.json()["summary_metrics"]

        # Scope metadata fields are always present with correct defaults
        assert metrics["scope_counts_are_direct_only"] is True
        assert metrics["scope_classification_label"] == "Direct dependencies, classified from manifests"
        assert "scope_note" in metrics

        # Scope count fields are present in the response
        assert "direct_runtime_dependency_count" in metrics
        assert "direct_dev_dependency_count" in metrics
        assert "direct_test_dependency_count" in metrics
        assert "direct_build_dependency_count" in metrics
        assert "direct_optional_dependency_count" in metrics
        assert "direct_peer_dependency_count" in metrics
        assert "direct_unknown_dependency_count" in metrics
        assert "direct_total_dependency_count" in metrics

    def test_scope_counts_conservation(self, tmp_path):
        """Sum of all direct_* scope counts equals direct_total_dependency_count."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, "owner/repo")
        _insert_dep_with_scope(db_path, "owner/repo", "a", scope="runtime", scope_conf="high")
        _insert_dep_with_scope(db_path, "owner/repo", "b", scope="dev", scope_conf="high",
                               group="dev")
        _insert_dep_with_scope(db_path, "owner/repo", "c", scope="optional", scope_conf="high")
        _insert_dep_with_scope(db_path, "owner/repo", "d", scope="unknown", scope_conf="low")

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/owner/repo/dependency-tree")

        metrics = resp.json()["summary_metrics"]
        scope_sum = (
            metrics["direct_runtime_dependency_count"]
            + metrics["direct_dev_dependency_count"]
            + metrics["direct_test_dependency_count"]
            + metrics["direct_build_dependency_count"]
            + metrics["direct_optional_dependency_count"]
            + metrics["direct_peer_dependency_count"]
            + metrics["direct_unknown_dependency_count"]
        )
        assert scope_sum == metrics["direct_total_dependency_count"]
