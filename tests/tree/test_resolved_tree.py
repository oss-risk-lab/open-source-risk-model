"""Unit tests for TreeService resolved data path (Task 10).

Tests tree construction from resolved transitive dependency edges,
fallback to flat tree, status mapping, and reconstruction safety.
"""

from __future__ import annotations

import os
import sqlite3

import pytest
from unittest.mock import patch, MagicMock

from open_source_risk_model.resolution.models import ResolutionEdge, make_node_key
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

        CREATE TABLE IF NOT EXISTS resolved_dependencies (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name   TEXT NOT NULL,
            parent_ecosystem TEXT,
            parent_package   TEXT NOT NULL,
            child_ecosystem  TEXT,
            child_package    TEXT NOT NULL,
            declared_specifier TEXT,
            resolved_version TEXT,
            depth            INTEGER NOT NULL,
            resolution_status TEXT NOT NULL DEFAULT 'resolved',
            error_reason     TEXT,
            source_registry  TEXT,
            resolved_at      TEXT NOT NULL
        );
    """)
    conn.close()
    return db_path


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


def _insert_dep(db_path: str, repo: str, pkg: str, registry: str = "pypi",
                *, specifier: str = "", manifest: str = "requirements.txt") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO repo_dependencies
           (repo_full_name, package_name, registry_type, specifier,
            extras, dependency_group, is_direct, is_optional,
            manifest_path, confidence, created_at)
           VALUES (?, ?, ?, ?, '[]', 'prod', 1, 0, ?, 0.9, datetime('now'))""",
        (repo, pkg, registry, specifier, manifest),
    )
    conn.commit()
    conn.close()


def _insert_resolved_edge(db_path: str, edge: ResolutionEdge) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO resolved_dependencies
           (repo_full_name, parent_ecosystem, parent_package,
            child_ecosystem, child_package, declared_specifier,
            resolved_version, depth, resolution_status,
            error_reason, source_registry, resolved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (edge.repo_full_name, edge.parent_ecosystem, edge.parent_package,
         edge.child_ecosystem, edge.child_package, edge.declared_specifier,
         edge.resolved_version, edge.depth, edge.resolution_status,
         edge.error_reason, edge.source_registry, edge.resolved_at),
    )
    conn.commit()
    conn.close()


REPO = "owner/test-repo"
TS = "2024-01-01T00:00:00+00:00"


def _make_edge(**kwargs) -> ResolutionEdge:
    """Create a ResolutionEdge with sensible defaults."""
    defaults = dict(
        repo_full_name=REPO,
        parent_ecosystem=None,
        parent_package=REPO,
        child_ecosystem="pypi",
        child_package="pkg-a",
        declared_specifier=">=1.0",
        resolved_version="1.2.0",
        depth=1,
        resolution_status="resolved",
        error_reason=None,
        source_registry="pypi",
        resolved_at=TS,
    )
    defaults.update(kwargs)
    return ResolutionEdge(**defaults)


# ---------------------------------------------------------------------------
# Tests: Resolved data present → multi-level tree
# ---------------------------------------------------------------------------

class TestResolvedDataPath:
    """Resolved data present → multi-level tree built from edges (Req 10.1, 10.2)."""

    def test_multi_level_tree_from_resolved_edges(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # repo -> jinja2 (depth 1) -> markupsafe (depth 2)
        edges = [
            _make_edge(child_package="jinja2", declared_specifier=">=3.0",
                       resolved_version="3.1.3", depth=1),
            _make_edge(parent_ecosystem="pypi", parent_package="jinja2",
                       child_package="markupsafe", declared_specifier=">=2.0",
                       resolved_version="2.1.5", depth=2),
        ]
        for e in edges:
            _insert_resolved_edge(db_path, e)

        svc = TreeService(db_path)
        root, source = svc._build_canonical_tree(REPO)

        assert source == "database"
        assert root.node_type == "repository"
        assert root.depth == 0
        assert len(root.children) == 1

        jinja2 = root.children[0]
        assert jinja2.name == "jinja2"
        assert jinja2.depth == 1
        assert jinja2.dependency_type == "direct"
        assert jinja2.version == "3.1.3"
        assert jinja2.specifier == ">=3.0"
        assert len(jinja2.children) == 1

        markupsafe = jinja2.children[0]
        assert markupsafe.name == "markupsafe"
        assert markupsafe.depth == 2
        assert markupsafe.dependency_type == "transitive"
        assert markupsafe.version == "2.1.5"


class TestFallbackToFlatTree:
    """No resolved data → falls back to flat tree from repo_dependencies (Req 10.3)."""

    def test_no_resolved_data_uses_flat_tree(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)
        _insert_dep(db_path, REPO, "requests", "pypi")

        svc = TreeService(db_path)
        root, source = svc._build_canonical_tree(REPO)

        assert source == "database"
        assert root.node_type == "repository"
        assert len(root.children) == 1
        assert root.children[0].name == "requests"
        assert root.children[0].depth == 1


class TestSeparateNodeOccurrences:
    """Same package under different parents → separate TreeNode instances (Req 4.7)."""

    def test_shared_transitive_produces_separate_nodes(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # repo -> jinja2, repo -> werkzeug
        # jinja2 -> markupsafe, werkzeug -> markupsafe
        edges = [
            _make_edge(child_package="jinja2", resolved_version="3.1.3", depth=1),
            _make_edge(child_package="werkzeug", resolved_version="2.3.0", depth=1),
            _make_edge(parent_ecosystem="pypi", parent_package="jinja2",
                       child_package="markupsafe", resolved_version="2.1.5", depth=2),
            _make_edge(parent_ecosystem="pypi", parent_package="werkzeug",
                       child_package="markupsafe", resolved_version="2.1.5", depth=2),
        ]
        for e in edges:
            _insert_resolved_edge(db_path, e)

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)

        # Both jinja2 and werkzeug should have markupsafe as a child
        jinja2 = next(c for c in root.children if c.name == "jinja2")
        werkzeug = next(c for c in root.children if c.name == "werkzeug")

        assert len(jinja2.children) == 1
        assert jinja2.children[0].name == "markupsafe"
        assert len(werkzeug.children) == 1
        assert werkzeug.children[0].name == "markupsafe"

        # They should be separate instances
        assert jinja2.children[0] is not werkzeug.children[0]


# ---------------------------------------------------------------------------
# Tests: _map_resolution_status
# ---------------------------------------------------------------------------

class TestMapResolutionStatus:
    """_map_resolution_status maps all 6 statuses correctly (Req 10.4)."""

    def test_resolved(self):
        edge = _make_edge(resolution_status="resolved")
        status, reason = TreeService._map_resolution_status(edge)
        assert status == "resolved"
        assert reason is None

    def test_error(self):
        edge = _make_edge(resolution_status="error", error_reason="Not found")
        status, reason = TreeService._map_resolution_status(edge)
        assert status == "error"
        assert reason == "Not found"

    def test_cycle_detected(self):
        edge = _make_edge(resolution_status="cycle_detected")
        status, reason = TreeService._map_resolution_status(edge)
        assert status == "cycle_detected"
        assert reason is None

    def test_max_depth_reached(self):
        edge = _make_edge(resolution_status="max_depth_reached")
        status, reason = TreeService._map_resolution_status(edge)
        assert status == "max_depth_reached"
        assert reason is None

    def test_unsupported_ecosystem(self):
        """unsupported_ecosystem maps to visible status, NOT 'resolved'."""
        edge = _make_edge(resolution_status="unsupported_ecosystem")
        status, reason = TreeService._map_resolution_status(edge)
        assert status == "unsupported_ecosystem"
        assert status != "resolved"
        assert reason == "Ecosystem not supported for resolution"

    def test_budget_exhausted(self):
        """budget_exhausted maps to 'budget_exhausted' with reason string."""
        edge = _make_edge(resolution_status="budget_exhausted")
        status, reason = TreeService._map_resolution_status(edge)
        assert status == "budget_exhausted"
        assert reason == "Resolution budget exhausted"

    def test_unknown_status_defaults_to_resolved(self):
        edge = _make_edge(resolution_status="some_future_status")
        status, reason = TreeService._map_resolution_status(edge)
        assert status == "resolved"
        assert reason is None


# ---------------------------------------------------------------------------
# Tests: Terminal statuses produce leaf nodes
# ---------------------------------------------------------------------------

class TestTerminalStatuses:
    """Terminal statuses produce leaf nodes with no children."""

    @pytest.mark.parametrize("status", [
        "error", "cycle_detected", "max_depth_reached",
        "budget_exhausted", "unsupported_ecosystem",
    ])
    def test_terminal_status_produces_leaf(self, tmp_path, status):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # repo -> pkg-a (terminal) and pkg-a -> pkg-b (should NOT appear)
        edges = [
            _make_edge(child_package="pkg-a", resolution_status=status,
                       resolved_version=None, depth=1),
            _make_edge(parent_ecosystem="pypi", parent_package="pkg-a",
                       child_package="pkg-b", resolved_version="1.0.0", depth=2),
        ]
        for e in edges:
            _insert_resolved_edge(db_path, e)

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)

        pkg_a = root.children[0]
        assert pkg_a.name == "pkg-a"
        assert len(pkg_a.children) == 0  # Terminal: no children attached


# ---------------------------------------------------------------------------
# Tests: Version and specifier fields
# ---------------------------------------------------------------------------

class TestVersionAndSpecifier:
    """version populated from resolved_version, specifier from declared_specifier (Req 10.6)."""

    def test_version_and_specifier_populated(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        edge = _make_edge(child_package="requests", declared_specifier=">=2.28",
                          resolved_version="2.31.0", depth=1)
        _insert_resolved_edge(db_path, edge)

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)

        node = root.children[0]
        assert node.version == "2.31.0"
        assert node.specifier == ">=2.28"

    def test_none_version_and_specifier(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # Need at least one resolved edge for has_resolved_data to return True
        _insert_resolved_edge(db_path, _make_edge(
            child_package="good-pkg", resolved_version="1.0.0", depth=1))
        edge = _make_edge(child_package="unknown-pkg", declared_specifier=None,
                          resolved_version=None, resolution_status="error",
                          error_reason="Not found", depth=1)
        _insert_resolved_edge(db_path, edge)

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)

        # Find the error node (unknown-pkg)
        node = next(c for c in root.children if c.name == "unknown-pkg")
        assert node.version is None
        assert node.specifier is None


# ---------------------------------------------------------------------------
# Tests: Children sorted alphabetically
# ---------------------------------------------------------------------------

class TestChildrenSorting:
    """Children sorted alphabetically by package name (Req 14.3)."""

    def test_direct_children_sorted(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # Insert in reverse alphabetical order
        for pkg in ["werkzeug", "jinja2", "click"]:
            _insert_resolved_edge(db_path, _make_edge(
                child_package=pkg, resolved_version="1.0.0", depth=1))

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)

        names = [c.name for c in root.children]
        assert names == ["click", "jinja2", "werkzeug"]


# ---------------------------------------------------------------------------
# Tests: Depth and dependency_type
# ---------------------------------------------------------------------------

class TestDepthAndDependencyType:
    """Depth-1 edges produce dependency_type='direct', deeper produce 'transitive'."""

    def test_depth_1_is_direct(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)
        _insert_resolved_edge(db_path, _make_edge(child_package="pkg-a", depth=1))

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)
        assert root.children[0].dependency_type == "direct"

    def test_depth_2_is_transitive(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)
        _insert_resolved_edge(db_path, _make_edge(child_package="pkg-a", depth=1))
        _insert_resolved_edge(db_path, _make_edge(
            parent_ecosystem="pypi", parent_package="pkg-a",
            child_package="pkg-b", depth=2))

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)
        assert root.children[0].children[0].dependency_type == "transitive"


# ---------------------------------------------------------------------------
# Tests: Root node properties
# ---------------------------------------------------------------------------

class TestRootNode:
    """Root node has depth=0, node_type='repository'."""

    def test_root_properties(self, tmp_path):
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)
        _insert_resolved_edge(db_path, _make_edge(child_package="pkg-a", depth=1))

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)

        assert root.depth == 0
        assert root.node_type == "repository"
        assert root.name == REPO
        assert root.id == REPO


# ---------------------------------------------------------------------------
# Tests: Reconstruction safety guard
# ---------------------------------------------------------------------------

class TestReconstructionSafetyGuard:
    """Reconstruction safety guard prevents infinite loops from inconsistent data."""

    def test_safety_guard_prevents_loop(self, tmp_path):
        """If edges form a cycle (inconsistent data), the guard stops recursion."""
        db_path = _create_test_db(str(tmp_path))
        _insert_repo_graph(db_path, REPO)

        # repo -> A (depth 1), A -> B (depth 2), B -> A (depth 3, cycle in edges)
        edges = [
            _make_edge(child_package="pkg-a", resolved_version="1.0", depth=1),
            _make_edge(parent_ecosystem="pypi", parent_package="pkg-a",
                       child_package="pkg-b", resolved_version="2.0", depth=2),
            _make_edge(parent_ecosystem="pypi", parent_package="pkg-b",
                       child_package="pkg-a", resolved_version="1.0", depth=3),
        ]
        for e in edges:
            _insert_resolved_edge(db_path, e)

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(REPO)

        # Should not hang. pkg-a at depth 3 should be a leaf (guard stops it).
        pkg_a = root.children[0]
        assert pkg_a.name == "pkg-a"
        pkg_b = pkg_a.children[0]
        assert pkg_b.name == "pkg-b"
        # pkg-a under pkg-b should exist but have no children (guard)
        pkg_a_again = pkg_b.children[0]
        assert pkg_a_again.name == "pkg-a"
        assert len(pkg_a_again.children) == 0
