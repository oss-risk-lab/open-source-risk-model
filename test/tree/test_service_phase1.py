"""Unit tests for TreeService Phase 1: Canonical Tree Assembly."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from open_source_risk_model.tree.exceptions import (
    AllDependenciesFailedError,
    RepositoryNotFoundError,
)
from open_source_risk_model.tree.models import TreeNode
from open_source_risk_model.tree.service import TreeService, _make_canonical_id
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


def _insert_repo_graph(db_path: str, repo: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', '{}', datetime('now'), datetime('now'))""",
        (repo,),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRetrieveDependencyRelationships:
    """Test _retrieve_dependency_relationships."""

    def test_rows_found_returns_database(self, tmp_path):
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "lodash", "npm", version="4.17.21")
        svc = TreeService(db)
        deps, source = svc._retrieve_dependency_relationships("owner/repo")
        assert source == "database"
        assert len(deps) == 1
        assert deps[0]["package_name"] == "lodash"

    def test_zero_deps_repo_exists(self, tmp_path):
        db = _create_test_db(str(tmp_path))
        _insert_repo_graph(db, "owner/empty-repo")
        svc = TreeService(db)
        deps, source = svc._retrieve_dependency_relationships("owner/empty-repo")
        assert source == "database"
        assert deps == []

    def test_repo_not_found_raises(self, tmp_path):
        db = _create_test_db(str(tmp_path))
        svc = TreeService(db)
        with pytest.raises(RepositoryNotFoundError):
            svc._retrieve_dependency_relationships("owner/nonexistent")


class TestBuildCanonicalTree:
    """Test _build_canonical_tree."""

    def test_direct_and_transitive_deps(self, tmp_path):
        db = _create_test_db(str(tmp_path))
        # Direct dep: express
        _insert_dep(db, "owner/repo", "express", "npm", is_direct=True, version="4.18.0")
        # Transitive dep: body-parser (child of express)
        _insert_dep(
            db, "owner/repo", "body-parser", "npm",
            is_direct=False, version="1.20.0",
            parent_package_name="express",
        )
        svc = TreeService(db)
        root, source = svc._build_canonical_tree("owner/repo")

        assert source == "database"
        assert root.node_type == "repository"
        assert root.depth == 0
        assert root.id == "owner/repo"
        assert len(root.children) == 1

        express = root.children[0]
        assert express.name == "express"
        assert express.depth == 1
        assert express.dependency_type == "direct"
        assert len(express.children) == 1

        bp = express.children[0]
        assert bp.name == "body-parser"
        assert bp.depth == 2
        assert bp.dependency_type == "transitive"

    def test_zero_dependency_repo(self, tmp_path):
        db = _create_test_db(str(tmp_path))
        _insert_repo_graph(db, "owner/empty")
        svc = TreeService(db)
        root, source = svc._build_canonical_tree("owner/empty")

        assert root.node_type == "repository"
        assert root.children == []
        assert source == "database"

    def test_repo_not_found(self, tmp_path):
        db = _create_test_db(str(tmp_path))
        svc = TreeService(db)
        with pytest.raises(RepositoryNotFoundError):
            svc._build_canonical_tree("owner/missing")

    def test_cycle_detection(self, tmp_path):
        """Cycle: A → B → A should terminate."""
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "A", "npm", is_direct=True, version="1.0")
        _insert_dep(db, "owner/repo", "B", "npm", is_direct=False, version="1.0",
                     parent_package_name="A")
        # B depends on A (cycle)
        _insert_dep(
            db, "owner/repo", "A", "npm", is_direct=False, version="1.0",
            parent_package_name="B", manifest="cycle.json",
        )
        svc = TreeService(db)
        root, _ = svc._build_canonical_tree("owner/repo")

        # Root → A → B → (A stops due to cycle)
        a_node = root.children[0]
        assert a_node.name == "A"
        b_node = a_node.children[0]
        assert b_node.name == "B"
        # B should have A as child but with no further recursion
        cycle_a = b_node.children[0]
        assert cycle_a.name == "A"
        assert cycle_a.children == []  # Cycle terminated

    def test_canonical_id_same_package_different_branches(self, tmp_path):
        """Same package in two branches gets same id, different TreeNode instances."""
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "express", "npm", is_direct=True, version="4.0")
        _insert_dep(db, "owner/repo", "koa", "npm", is_direct=True, version="2.0",
                     manifest="package2.json")
        # shared transitive dep under both
        _insert_dep(db, "owner/repo", "shared-lib", "npm", is_direct=False, version="1.0",
                     parent_package_name="express")
        _insert_dep(db, "owner/repo", "shared-lib", "npm", is_direct=False, version="1.0",
                     parent_package_name="koa", manifest="package2.json")

        svc = TreeService(db)
        root, _ = svc._build_canonical_tree("owner/repo")

        # Find all shared-lib nodes
        shared_nodes = [n for n in walk_tree(root) if n.name == "shared-lib"]
        assert len(shared_nodes) == 2
        # Same canonical ID
        assert shared_nodes[0].id == shared_nodes[1].id
        # Different TreeNode instances
        assert shared_nodes[0] is not shared_nodes[1]

    def test_depth_is_computed(self, tmp_path):
        """Depth values match traversal position, not stored data."""
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "A", "npm", is_direct=True, version="1.0")
        _insert_dep(db, "owner/repo", "B", "npm", is_direct=False, version="1.0",
                     parent_package_name="A")
        _insert_dep(db, "owner/repo", "C", "npm", is_direct=False, version="1.0",
                     parent_package_name="B")

        svc = TreeService(db)
        root, _ = svc._build_canonical_tree("owner/repo")

        assert root.depth == 0
        assert root.children[0].depth == 1  # A
        assert root.children[0].children[0].depth == 2  # B
        assert root.children[0].children[0].children[0].depth == 3  # C

    def test_single_dep_failure_creates_error_node(self, tmp_path):
        """A single dependency failure creates an error node; siblings still resolved."""
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "good-pkg", "npm", is_direct=True, version="1.0")
        _insert_dep(db, "owner/repo", "bad-pkg", "npm", is_direct=True, version="1.0",
                     manifest="bad.json")

        svc = TreeService(db)

        # Monkey-patch _build_node to raise for bad-pkg
        original_build = svc._build_node

        def patched_build(dep, depth, dependency_type, transitive_by_parent, branch_visited):
            if dep["package_name"] == "bad-pkg":
                raise DependencyResolutionError("Manifest fetch failed")
            return original_build(dep, depth, dependency_type, transitive_by_parent, branch_visited)

        from open_source_risk_model.tree.exceptions import DependencyResolutionError
        svc._build_node = patched_build

        root, _ = svc._build_canonical_tree("owner/repo")

        names = {c.name for c in root.children}
        assert "good-pkg" in names
        assert "bad-pkg" in names

        error_node = next(c for c in root.children if c.name == "bad-pkg")
        assert error_node.resolution_status == "error"
        assert error_node.error_reason == "Manifest fetch failed"
        assert error_node.node_type == "package"

        good_node = next(c for c in root.children if c.name == "good-pkg")
        assert good_node.resolution_status == "resolved"

    def test_all_deps_fail_raises(self, tmp_path):
        """All dependencies failing raises AllDependenciesFailedError."""
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "bad1", "npm", is_direct=True, version="1.0")
        _insert_dep(db, "owner/repo", "bad2", "npm", is_direct=True, version="1.0",
                     manifest="bad2.json")

        svc = TreeService(db)

        from open_source_risk_model.tree.exceptions import DependencyResolutionError

        def always_fail(dep, depth, dependency_type, transitive_by_parent, branch_visited):
            raise DependencyResolutionError("fail")

        svc._build_node = always_fail

        with pytest.raises(AllDependenciesFailedError):
            svc._build_canonical_tree("owner/repo")

    def test_canonical_id_unknown_version(self, tmp_path):
        """Missing version uses @unknown in canonical ID."""
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "no-version-pkg", "npm", is_direct=True)

        svc = TreeService(db)
        root, _ = svc._build_canonical_tree("owner/repo")

        child = root.children[0]
        assert child.id == "pkg:npm/no-version-pkg@unknown"

    def test_data_source_is_database(self, tmp_path):
        """data_source is 'database' for DB path."""
        db = _create_test_db(str(tmp_path))
        _insert_dep(db, "owner/repo", "lodash", "npm", version="4.17.21")
        svc = TreeService(db)
        _, source = svc._build_canonical_tree("owner/repo")
        assert source == "database"


class TestMakeCanonicalId:
    def test_normal(self):
        assert _make_canonical_id("npm", "lodash", "4.17.21") == "pkg:npm/lodash@4.17.21"

    def test_missing_version(self):
        assert _make_canonical_id("npm", "lodash", None) == "pkg:npm/lodash@unknown"

    def test_empty_version(self):
        assert _make_canonical_id("npm", "lodash", "") == "pkg:npm/lodash@unknown"

    def test_missing_ecosystem(self):
        assert _make_canonical_id(None, "lodash", "1.0") == "pkg:unknown/lodash@1.0"
