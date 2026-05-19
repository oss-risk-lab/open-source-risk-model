"""
Unit tests for ResolutionEdge scope fields and validation.

Feature: transitive-scope-propagation
Requirements: 8.1, 8.2, 8.3
"""

import pytest

from src.open_source_risk_model.resolution.models import (
    ResolutionEdge,
    VALID_DEPENDENCY_SCOPES,
    VALID_SCOPE_CONFIDENCES,
)


def _make_edge(**overrides) -> ResolutionEdge:
    """Helper to create a ResolutionEdge with sensible defaults."""
    defaults = dict(
        repo_full_name="owner/repo",
        parent_ecosystem=None,
        parent_package="owner/repo",
        child_ecosystem="pypi",
        child_package="requests",
        declared_specifier=">=2.0",
        resolved_version="2.31.0",
        depth=1,
    )
    defaults.update(overrides)
    return ResolutionEdge(**defaults)


class TestResolutionEdgeScopeDefaults:
    """Test that ResolutionEdge defaults to unknown/low scope (Req 8.1, 8.2)."""

    def test_default_dependency_scope(self):
        edge = _make_edge()
        assert edge.dependency_scope == "unknown"

    def test_default_scope_confidence(self):
        edge = _make_edge()
        assert edge.scope_confidence == "low"

    def test_explicit_valid_scope_values(self):
        """All valid scope values are accepted without error."""
        for scope in VALID_DEPENDENCY_SCOPES:
            edge = _make_edge(dependency_scope=scope)
            assert edge.dependency_scope == scope

    def test_explicit_valid_confidence_values(self):
        """All valid confidence values are accepted without error."""
        for conf in VALID_SCOPE_CONFIDENCES:
            edge = _make_edge(scope_confidence=conf)
            assert edge.scope_confidence == conf


class TestResolutionEdgeScopeValidation:
    """Test that invalid scope/confidence values raise ValueError (Req 8.3)."""

    def test_invalid_scope_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid dependency_scope"):
            _make_edge(dependency_scope="production")

    def test_empty_scope_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid dependency_scope"):
            _make_edge(dependency_scope="")

    def test_invalid_confidence_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid scope_confidence"):
            _make_edge(scope_confidence="very_high")

    def test_empty_confidence_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid scope_confidence"):
            _make_edge(scope_confidence="")

    def test_case_sensitive_scope(self):
        """Scope validation is case-sensitive — 'Runtime' is invalid."""
        with pytest.raises(ValueError, match="Invalid dependency_scope"):
            _make_edge(dependency_scope="Runtime")

    def test_case_sensitive_confidence(self):
        """Confidence validation is case-sensitive — 'High' is invalid."""
        with pytest.raises(ValueError, match="Invalid scope_confidence"):
            _make_edge(scope_confidence="High")


# ---------------------------------------------------------------------------
# Task 5.5: Unit tests for resolver scope inheritance (single path)
# Task 5.6: Unit tests for diamond graph multi-path edge immutability
# ---------------------------------------------------------------------------

import sqlite3
import os
import tempfile
from unittest.mock import patch, MagicMock

from src.open_source_risk_model.resolution.resolver import TransitiveResolver
from src.open_source_risk_model.resolution.models import (
    NormalizedPackageMetadata,
    DependencyDeclaration,
)
from src.open_source_risk_model.resolution.budget_tracker import BudgetConfig


def _setup_test_db(db_path: str, deps: list[dict]) -> None:
    """Create repo_dependencies table and insert test rows."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
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
            UNIQUE(repo_full_name, package_name, manifest_path)
        )
    """)
    for dep in deps:
        conn.execute(
            """INSERT INTO repo_dependencies
               (repo_full_name, package_name, registry_type, specifier,
                manifest_path, confidence, created_at,
                dependency_scope, scope_confidence)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
            (
                dep["repo_full_name"],
                dep["package_name"],
                dep["registry_type"],
                dep.get("specifier"),
                dep.get("manifest_path", "requirements.txt"),
                dep.get("confidence", 1.0),
                dep.get("dependency_scope"),
                dep.get("scope_confidence"),
            ),
        )
    conn.commit()
    conn.close()


def _make_metadata(name: str, ecosystem: str, version: str = "1.0.0",
                   deps: list[DependencyDeclaration] | None = None) -> NormalizedPackageMetadata:
    return NormalizedPackageMetadata(
        name=name,
        version=version,
        ecosystem=ecosystem,
        dependencies=deps or [],
        source_url=f"https://registry.example.com/{name}",
        fetched_at="2025-01-01T00:00:00Z",
    )


class TestResolverScopeInheritanceSinglePath:
    """Task 5.5: Verify edges inherit parent scope through single-path resolution.

    Requirements: 3.1, 3.2, 3.3, 6.2
    """

    def _make_resolver(self, db_path: str) -> TransitiveResolver:
        return TransitiveResolver(
            db_path=db_path,
            max_depth=5,
            budget_config=BudgetConfig(global_budget=100, min_delay_ms=0),
        )

    def test_runtime_high_propagates_to_transitive(self, tmp_path):
        """Direct dep with runtime/high → transitive child edge has runtime/high."""
        db_path = str(tmp_path / "test.db")
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-a",
                "registry_type": "pypi",
                "dependency_scope": "runtime",
                "scope_confidence": "high",
            },
        ])

        # pkg-a depends on pkg-b
        meta_a = _make_metadata("pkg-a", "pypi", deps=[
            DependencyDeclaration(name="pkg-b", specifier=None),
        ])
        meta_b = _make_metadata("pkg-b", "pypi")

        def mock_lookup(eco, name):
            cache = {"pkg-a": meta_a, "pkg-b": meta_b}
            if name in cache:
                return cache[name], True
            return None, False

        resolver = self._make_resolver(db_path)
        resolver.cache.lookup = mock_lookup

        edges, _ = resolver.resolve_repo("owner/repo")

        assert len(edges) == 2
        # Direct edge: owner/repo → pkg-a
        edge_a = [e for e in edges if e.child_package == "pkg-a"][0]
        assert edge_a.dependency_scope == "runtime"
        assert edge_a.scope_confidence == "high"
        # Transitive edge: pkg-a → pkg-b
        edge_b = [e for e in edges if e.child_package == "pkg-b"][0]
        assert edge_b.dependency_scope == "runtime"
        assert edge_b.scope_confidence == "high"

    def test_dev_high_propagates_to_transitive(self, tmp_path):
        """Direct dep with dev/high → transitive child edge has dev/high."""
        db_path = str(tmp_path / "test.db")
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-a",
                "registry_type": "pypi",
                "dependency_scope": "dev",
                "scope_confidence": "high",
            },
        ])

        meta_a = _make_metadata("pkg-a", "pypi", deps=[
            DependencyDeclaration(name="pkg-b", specifier=None),
        ])
        meta_b = _make_metadata("pkg-b", "pypi")

        def mock_lookup(eco, name):
            cache = {"pkg-a": meta_a, "pkg-b": meta_b}
            if name in cache:
                return cache[name], True
            return None, False

        resolver = self._make_resolver(db_path)
        resolver.cache.lookup = mock_lookup

        edges, _ = resolver.resolve_repo("owner/repo")

        edge_a = [e for e in edges if e.child_package == "pkg-a"][0]
        assert edge_a.dependency_scope == "dev"
        assert edge_a.scope_confidence == "high"

        edge_b = [e for e in edges if e.child_package == "pkg-b"][0]
        assert edge_b.dependency_scope == "dev"
        assert edge_b.scope_confidence == "high"

    def test_null_scope_defaults_to_unknown_low(self, tmp_path):
        """Direct dep with NULL scope → transitive child edge has unknown/low."""
        db_path = str(tmp_path / "test.db")
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-a",
                "registry_type": "pypi",
                "dependency_scope": None,
                "scope_confidence": None,
            },
        ])

        meta_a = _make_metadata("pkg-a", "pypi", deps=[
            DependencyDeclaration(name="pkg-b", specifier=None),
        ])
        meta_b = _make_metadata("pkg-b", "pypi")

        def mock_lookup(eco, name):
            cache = {"pkg-a": meta_a, "pkg-b": meta_b}
            if name in cache:
                return cache[name], True
            return None, False

        resolver = self._make_resolver(db_path)
        resolver.cache.lookup = mock_lookup

        edges, _ = resolver.resolve_repo("owner/repo")

        edge_a = [e for e in edges if e.child_package == "pkg-a"][0]
        assert edge_a.dependency_scope == "unknown"
        assert edge_a.scope_confidence == "low"

        edge_b = [e for e in edges if e.child_package == "pkg-b"][0]
        assert edge_b.dependency_scope == "unknown"
        assert edge_b.scope_confidence == "low"


class TestResolverDiamondGraphEdgeImmutability:
    """Task 5.6: Diamond graph multi-path edge immutability.

    Diamond: A(runtime)→B→D, A(dev)→C→D
    Each edge retains its parent's scope — no retroactive mutation.

    Requirements: 4.1
    """

    def test_diamond_edges_retain_parent_scope(self, tmp_path):
        """Edge B→D has runtime scope, edge C→D has dev scope."""
        db_path = str(tmp_path / "test.db")
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-b",
                "registry_type": "pypi",
                "dependency_scope": "runtime",
                "scope_confidence": "high",
            },
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-c",
                "registry_type": "pypi",
                "dependency_scope": "dev",
                "scope_confidence": "high",
            },
        ])

        # B depends on D, C depends on D
        meta_b = _make_metadata("pkg-b", "pypi", deps=[
            DependencyDeclaration(name="pkg-d", specifier=None),
        ])
        meta_c = _make_metadata("pkg-c", "pypi", deps=[
            DependencyDeclaration(name="pkg-d", specifier=None),
        ])
        meta_d = _make_metadata("pkg-d", "pypi")

        def mock_lookup(eco, name):
            cache = {"pkg-b": meta_b, "pkg-c": meta_c, "pkg-d": meta_d}
            if name in cache:
                return cache[name], True
            return None, False

        resolver = TransitiveResolver(
            db_path=db_path,
            max_depth=5,
            budget_config=BudgetConfig(global_budget=100, min_delay_ms=0),
        )
        resolver.cache.lookup = mock_lookup

        edges, _ = resolver.resolve_repo("owner/repo")

        # Direct edges
        edge_b = [e for e in edges if e.child_package == "pkg-b" and e.depth == 1][0]
        assert edge_b.dependency_scope == "runtime"
        assert edge_b.scope_confidence == "high"

        edge_c = [e for e in edges if e.child_package == "pkg-c" and e.depth == 1][0]
        assert edge_c.dependency_scope == "dev"
        assert edge_c.scope_confidence == "high"

        # Transitive edges to D — there should be two, one from each path
        edges_to_d = [e for e in edges if e.child_package == "pkg-d"]
        assert len(edges_to_d) == 2

        # Edge from B→D should have runtime scope
        edge_bd = [e for e in edges_to_d if e.parent_package == "pkg-b"][0]
        assert edge_bd.dependency_scope == "runtime"
        assert edge_bd.scope_confidence == "high"

        # Edge from C→D should have dev scope
        edge_cd = [e for e in edges_to_d if e.parent_package == "pkg-c"][0]
        assert edge_cd.dependency_scope == "dev"
        assert edge_cd.scope_confidence == "high"

    def test_no_retroactive_mutation(self, tmp_path):
        """After resolution, re-check that earlier edges were not mutated."""
        db_path = str(tmp_path / "test.db")
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-b",
                "registry_type": "pypi",
                "dependency_scope": "runtime",
                "scope_confidence": "high",
            },
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-c",
                "registry_type": "pypi",
                "dependency_scope": "dev",
                "scope_confidence": "high",
            },
        ])

        meta_b = _make_metadata("pkg-b", "pypi", deps=[
            DependencyDeclaration(name="pkg-d", specifier=None),
        ])
        meta_c = _make_metadata("pkg-c", "pypi", deps=[
            DependencyDeclaration(name="pkg-d", specifier=None),
        ])
        meta_d = _make_metadata("pkg-d", "pypi")

        def mock_lookup(eco, name):
            cache = {"pkg-b": meta_b, "pkg-c": meta_c, "pkg-d": meta_d}
            if name in cache:
                return cache[name], True
            return None, False

        resolver = TransitiveResolver(
            db_path=db_path,
            max_depth=5,
            budget_config=BudgetConfig(global_budget=100, min_delay_ms=0),
        )
        resolver.cache.lookup = mock_lookup

        edges, _ = resolver.resolve_repo("owner/repo")

        # Snapshot all edge scopes
        scope_snapshot = [
            (e.parent_package, e.child_package, e.dependency_scope, e.scope_confidence)
            for e in edges
        ]

        # Verify no edge has been mutated — each edge's scope matches its parent path
        for parent, child, scope, conf in scope_snapshot:
            if parent == "owner/repo" and child == "pkg-b":
                assert scope == "runtime"
            elif parent == "owner/repo" and child == "pkg-c":
                assert scope == "dev"
            elif parent == "pkg-b" and child == "pkg-d":
                assert scope == "runtime"
            elif parent == "pkg-c" and child == "pkg-d":
                assert scope == "dev"


# ---------------------------------------------------------------------------
# Task 10.3: Integration test for end-to-end resolution with scope
# ---------------------------------------------------------------------------

from src.open_source_risk_model.resolution.storage import ResolvedDependencyStorage
from src.open_source_risk_model.tree.service import TreeService
from src.open_source_risk_model.tree.tree_utils import walk_tree
from src.open_source_risk_model.tree.metrics import SummaryMetricsCalculator


def _create_full_test_db(db_path: str) -> None:
    """Create a full test database with all tables needed for TreeService."""
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
            resolved_at      TEXT NOT NULL,
            dependency_scope TEXT DEFAULT 'unknown',
            scope_confidence TEXT DEFAULT 'low'
        );
    """)
    conn.execute(
        """INSERT OR IGNORE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', '{}', datetime('now'), datetime('now'))""",
        ("owner/repo",),
    )
    conn.commit()
    conn.close()


class TestEndToEndResolutionWithScope:
    """Task 10.3: Integration test for end-to-end resolution with scope.

    Exercises the full pipeline: resolve → store → build tree → compute metrics.

    Requirements: 3.1, 4.2, 9.1, 10.1
    """

    def test_resolve_store_and_verify_edge_scopes(self, tmp_path):
        """Resolve repo with known scopes, store edges, verify propagated scopes."""
        db_path = str(tmp_path / "test.db")
        _create_full_test_db(db_path)

        # Set up direct deps with known scopes
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "web-framework",
                "registry_type": "pypi",
                "dependency_scope": "runtime",
                "scope_confidence": "high",
            },
            {
                "repo_full_name": "owner/repo",
                "package_name": "test-lib",
                "registry_type": "pypi",
                "dependency_scope": "test",
                "scope_confidence": "high",
            },
        ])

        # web-framework → http-client (transitive runtime)
        # test-lib → mock-helper (transitive test)
        meta_web = _make_metadata("web-framework", "pypi", deps=[
            DependencyDeclaration(name="http-client", specifier=None),
        ])
        meta_test = _make_metadata("test-lib", "pypi", deps=[
            DependencyDeclaration(name="mock-helper", specifier=None),
        ])
        meta_http = _make_metadata("http-client", "pypi")
        meta_mock = _make_metadata("mock-helper", "pypi")

        def mock_lookup(eco, name):
            cache = {
                "web-framework": meta_web,
                "test-lib": meta_test,
                "http-client": meta_http,
                "mock-helper": meta_mock,
            }
            if name in cache:
                return cache[name], True
            return None, False

        # Resolve
        resolver = TransitiveResolver(
            db_path=db_path,
            max_depth=5,
            budget_config=BudgetConfig(global_budget=100, min_delay_ms=0),
        )
        resolver.cache.lookup = mock_lookup
        edges, summary = resolver.resolve_repo("owner/repo")

        # Verify edge scopes
        assert len(edges) == 4

        edge_web = [e for e in edges if e.child_package == "web-framework"][0]
        assert edge_web.dependency_scope == "runtime"
        assert edge_web.scope_confidence == "high"

        edge_http = [e for e in edges if e.child_package == "http-client"][0]
        assert edge_http.dependency_scope == "runtime"
        assert edge_http.scope_confidence == "high"

        edge_test = [e for e in edges if e.child_package == "test-lib"][0]
        assert edge_test.dependency_scope == "test"
        assert edge_test.scope_confidence == "high"

        edge_mock = [e for e in edges if e.child_package == "mock-helper"][0]
        assert edge_mock.dependency_scope == "test"
        assert edge_mock.scope_confidence == "high"

        # Store and read back
        storage = ResolvedDependencyStorage(db_path=db_path)
        storage.store_edges("owner/repo", edges)
        stored_edges = storage.get_edges("owner/repo")

        assert len(stored_edges) == 4
        stored_http = [e for e in stored_edges if e.child_package == "http-client"][0]
        assert stored_http.dependency_scope == "runtime"
        assert stored_http.scope_confidence == "high"

    def test_tree_shows_highest_priority_scope_for_multi_path(self, tmp_path):
        """Build tree from multi-path edges, verify node shows highest-priority scope."""
        db_path = str(tmp_path / "test.db")
        _create_full_test_db(db_path)

        # Diamond: repo → A(runtime) → D, repo → B(dev) → D
        # D should show runtime (highest priority) in tree
        edges = [
            ResolutionEdge(
                repo_full_name="owner/repo",
                parent_ecosystem=None, parent_package="owner/repo",
                child_ecosystem="pypi", child_package="pkg-a",
                declared_specifier=None, resolved_version="1.0.0",
                depth=1, dependency_scope="runtime", scope_confidence="high",
                source_registry="pypi", resolved_at="2025-01-01T00:00:00Z",
            ),
            ResolutionEdge(
                repo_full_name="owner/repo",
                parent_ecosystem=None, parent_package="owner/repo",
                child_ecosystem="pypi", child_package="pkg-b",
                declared_specifier=None, resolved_version="1.0.0",
                depth=1, dependency_scope="dev", scope_confidence="high",
                source_registry="pypi", resolved_at="2025-01-01T00:00:00Z",
            ),
            ResolutionEdge(
                repo_full_name="owner/repo",
                parent_ecosystem="pypi", parent_package="pkg-a",
                child_ecosystem="pypi", child_package="pkg-d",
                declared_specifier=None, resolved_version="2.0.0",
                depth=2, dependency_scope="runtime", scope_confidence="high",
                source_registry="pypi", resolved_at="2025-01-01T00:00:00Z",
            ),
            ResolutionEdge(
                repo_full_name="owner/repo",
                parent_ecosystem="pypi", parent_package="pkg-b",
                child_ecosystem="pypi", child_package="pkg-d",
                declared_specifier=None, resolved_version="2.0.0",
                depth=2, dependency_scope="dev", scope_confidence="high",
                source_registry="pypi", resolved_at="2025-01-01T00:00:00Z",
            ),
        ]

        # Store edges
        storage = ResolvedDependencyStorage(db_path=db_path)
        storage.store_edges("owner/repo", edges)

        # Build tree via TreeService
        service = TreeService(db_path=db_path)
        root = service._build_tree_from_resolved("owner/repo", edges)

        # Find all occurrences of pkg-d in the tree
        d_nodes = [n for n in walk_tree(root) if n.name == "pkg-d"]
        assert len(d_nodes) >= 1

        # All occurrences should show aggregated scope = runtime (highest priority)
        for d_node in d_nodes:
            assert d_node.dependency_scope == "runtime"
            assert d_node.scope_confidence == "high"

    def test_transitive_runtime_count_matches_expected(self, tmp_path):
        """Verify transitive_runtime_dependency_count matches expected value."""
        db_path = str(tmp_path / "test.db")
        _create_full_test_db(db_path)

        # Set up direct deps
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "framework",
                "registry_type": "pypi",
                "dependency_scope": "runtime",
                "scope_confidence": "high",
            },
            {
                "repo_full_name": "owner/repo",
                "package_name": "devtool",
                "registry_type": "pypi",
                "dependency_scope": "dev",
                "scope_confidence": "high",
            },
        ])

        # framework → util-a (runtime), framework → util-b (runtime)
        # devtool → lint-helper (dev)
        meta_framework = _make_metadata("framework", "pypi", deps=[
            DependencyDeclaration(name="util-a", specifier=None),
            DependencyDeclaration(name="util-b", specifier=None),
        ])
        meta_devtool = _make_metadata("devtool", "pypi", deps=[
            DependencyDeclaration(name="lint-helper", specifier=None),
        ])
        meta_util_a = _make_metadata("util-a", "pypi")
        meta_util_b = _make_metadata("util-b", "pypi")
        meta_lint = _make_metadata("lint-helper", "pypi")

        def mock_lookup(eco, name):
            cache = {
                "framework": meta_framework,
                "devtool": meta_devtool,
                "util-a": meta_util_a,
                "util-b": meta_util_b,
                "lint-helper": meta_lint,
            }
            if name in cache:
                return cache[name], True
            return None, False

        resolver = TransitiveResolver(
            db_path=db_path,
            max_depth=5,
            budget_config=BudgetConfig(global_budget=100, min_delay_ms=0),
        )
        resolver.cache.lookup = mock_lookup
        edges, _ = resolver.resolve_repo("owner/repo")

        # Store edges so TreeService can find them
        storage = ResolvedDependencyStorage(db_path=db_path)
        storage.store_edges("owner/repo", edges)

        # Use TreeService to get the full response
        service = TreeService(db_path=db_path)
        response = service.get_dependency_tree("owner/repo")

        # Verify transitive_runtime_dependency_count
        # Transitive runtime deps: util-a, util-b (both inherit runtime from framework)
        # lint-helper inherits dev from devtool → NOT counted
        assert response.summary_metrics.transitive_runtime_dependency_count == 2

        # scope_counts_are_direct_only should be False (transitive scope data available)
        assert response.summary_metrics.scope_counts_are_direct_only is False


# ---------------------------------------------------------------------------
# Task 11.1: Property test for edge immutability across multi-path resolution
# ---------------------------------------------------------------------------

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.open_source_risk_model.resolution.models import VALID_DEPENDENCY_SCOPES, VALID_SCOPE_CONFIDENCES

# Strategies for generating random scopes/confidences
_valid_scopes_list = sorted(VALID_DEPENDENCY_SCOPES - {"unknown"})  # exclude unknown for meaningful diamond tests
_valid_confs_list = sorted(VALID_SCOPE_CONFIDENCES)

_scope_st = st.sampled_from(_valid_scopes_list)
_conf_st = st.sampled_from(_valid_confs_list)


class TestEdgeImmutabilityProperty:
    """Property 3: Edge Immutability Across Multi-Path Resolution.

    Generate diamond graphs with different scopes on two direct deps that
    both depend on a shared child. Resolve and verify each edge to the
    shared child retains its parent's scope — no retroactive mutation.

    **Validates: Requirements 4.1**
    """

    @given(
        scope_b=_scope_st,
        conf_b=_conf_st,
        scope_c=_scope_st,
        conf_c=_conf_st,
    )
    @settings(max_examples=200, deadline=None)
    def test_diamond_edges_retain_parent_scope(
        self, scope_b, conf_b, scope_c, conf_c, tmp_path_factory
    ):
        """Each edge to the shared child retains its own parent's scope."""
        # Ensure the two paths have different scopes so the test is meaningful
        assume(scope_b != scope_c or conf_b != conf_c)

        tmp_dir = tmp_path_factory.mktemp("diamond")
        db_path = str(tmp_dir / "test.db")

        # Diamond: repo → pkg-b(scope_b) → pkg-d, repo → pkg-c(scope_c) → pkg-d
        _setup_test_db(db_path, [
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-b",
                "registry_type": "pypi",
                "dependency_scope": scope_b,
                "scope_confidence": conf_b,
            },
            {
                "repo_full_name": "owner/repo",
                "package_name": "pkg-c",
                "registry_type": "pypi",
                "dependency_scope": scope_c,
                "scope_confidence": conf_c,
            },
        ])

        meta_b = _make_metadata("pkg-b", "pypi", deps=[
            DependencyDeclaration(name="pkg-d", specifier=None),
        ])
        meta_c = _make_metadata("pkg-c", "pypi", deps=[
            DependencyDeclaration(name="pkg-d", specifier=None),
        ])
        meta_d = _make_metadata("pkg-d", "pypi")

        def mock_lookup(eco, name):
            cache = {"pkg-b": meta_b, "pkg-c": meta_c, "pkg-d": meta_d}
            if name in cache:
                return cache[name], True
            return None, False

        resolver = TransitiveResolver(
            db_path=db_path,
            max_depth=5,
            budget_config=BudgetConfig(global_budget=100, min_delay_ms=0),
        )
        resolver.cache.lookup = mock_lookup

        edges, _ = resolver.resolve_repo("owner/repo")

        # Direct edges retain their own scope
        edge_b = [e for e in edges if e.child_package == "pkg-b" and e.depth == 1][0]
        assert edge_b.dependency_scope == scope_b
        assert edge_b.scope_confidence == conf_b

        edge_c = [e for e in edges if e.child_package == "pkg-c" and e.depth == 1][0]
        assert edge_c.dependency_scope == scope_c
        assert edge_c.scope_confidence == conf_c

        # Transitive edges to pkg-d — there should be two, one from each path
        edges_to_d = [e for e in edges if e.child_package == "pkg-d"]
        assert len(edges_to_d) == 2

        # Edge from pkg-b → pkg-d retains pkg-b's scope
        edge_bd = [e for e in edges_to_d if e.parent_package == "pkg-b"][0]
        assert edge_bd.dependency_scope == scope_b
        assert edge_bd.scope_confidence == conf_b

        # Edge from pkg-c → pkg-d retains pkg-c's scope
        edge_cd = [e for e in edges_to_d if e.parent_package == "pkg-c"][0]
        assert edge_cd.dependency_scope == scope_c
        assert edge_cd.scope_confidence == conf_c
