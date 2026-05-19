"""Tests for ResolvedDependencyStorage scope persistence (Req 7.1, 7.2, 12.1)."""
import sqlite3
import pytest
from src.open_source_risk_model.resolution.storage import ResolvedDependencyStorage
from src.open_source_risk_model.resolution.models import ResolutionEdge


def _make_edge(
    repo="owner/repo",
    parent_ecosystem=None,
    parent_package="owner/repo",
    child_ecosystem="pypi",
    child_package="requests",
    declared_specifier=">=2.0",
    resolved_version="2.31.0",
    depth=1,
    resolution_status="resolved",
    error_reason=None,
    source_registry="pypi",
    resolved_at="2024-01-15T10:00:00+00:00",
    dependency_scope="unknown",
    scope_confidence="low",
) -> ResolutionEdge:
    return ResolutionEdge(
        repo_full_name=repo,
        parent_ecosystem=parent_ecosystem,
        parent_package=parent_package,
        child_ecosystem=child_ecosystem,
        child_package=child_package,
        declared_specifier=declared_specifier,
        resolved_version=resolved_version,
        depth=depth,
        resolution_status=resolution_status,
        error_reason=error_reason,
        source_registry=source_registry,
        resolved_at=resolved_at,
        dependency_scope=dependency_scope,
        scope_confidence=scope_confidence,
    )


@pytest.fixture
def storage(tmp_path):
    db_path = str(tmp_path / "test.db")
    return ResolvedDependencyStorage(db_path)


class TestScopeSchemaColumns:
    """Verify schema migration adds scope columns and index (Req 1.1, 1.2, 1.4)."""

    def test_scope_columns_exist(self, storage):
        conn = sqlite3.connect(storage.db_path)
        cursor = conn.execute("PRAGMA table_info(resolved_dependencies)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert "dependency_scope" in columns
        assert "scope_confidence" in columns

    def test_scope_index_exists(self, storage):
        conn = sqlite3.connect(storage.db_path)
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        conn.close()
        assert "idx_resolved_deps_scope" in indexes

    def test_migration_idempotent(self, storage):
        """Calling ensure_tables() multiple times does not error."""
        storage.ensure_tables()
        storage.ensure_tables()


class TestScopeRoundTrip:
    """Store edges with scope fields, read back, verify preserved (Req 7.1, 7.2)."""

    def test_runtime_high_round_trip(self, storage):
        edge = _make_edge(dependency_scope="runtime", scope_confidence="high")
        storage.store_edges("owner/repo", [edge])
        result = storage.get_edges("owner/repo")
        assert len(result) == 1
        assert result[0].dependency_scope == "runtime"
        assert result[0].scope_confidence == "high"

    def test_dev_medium_round_trip(self, storage):
        edge = _make_edge(dependency_scope="dev", scope_confidence="medium")
        storage.store_edges("owner/repo", [edge])
        result = storage.get_edges("owner/repo")
        assert result[0].dependency_scope == "dev"
        assert result[0].scope_confidence == "medium"

    def test_multiple_edges_different_scopes(self, storage):
        edges = [
            _make_edge(child_package="a", dependency_scope="runtime", scope_confidence="high"),
            _make_edge(child_package="b", dependency_scope="dev", scope_confidence="low"),
            _make_edge(child_package="c", dependency_scope="test", scope_confidence="medium"),
        ]
        storage.store_edges("owner/repo", edges)
        result = storage.get_edges("owner/repo")
        scopes = {r.child_package: (r.dependency_scope, r.scope_confidence) for r in result}
        assert scopes["a"] == ("runtime", "high")
        assert scopes["b"] == ("dev", "low")
        assert scopes["c"] == ("test", "medium")

    def test_default_scope_round_trip(self, storage):
        """Edge with default scope values round-trips correctly."""
        edge = _make_edge()  # defaults: unknown / low
        storage.store_edges("owner/repo", [edge])
        result = storage.get_edges("owner/repo")
        assert result[0].dependency_scope == "unknown"
        assert result[0].scope_confidence == "low"


class TestPreMigrationBackwardsCompatibility:
    """Rows without scope columns get defaults (Req 12.1)."""

    def test_pre_migration_rows_get_defaults(self, storage):
        """Rows inserted without scope columns should read back as unknown/low."""
        # Directly insert a row without scope columns to simulate pre-migration data
        conn = sqlite3.connect(storage.db_path)
        conn.execute(
            """INSERT INTO resolved_dependencies
               (repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_package, declared_specifier,
                resolved_version, depth, resolution_status,
                error_reason, source_registry, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("owner/repo", None, "owner/repo", "pypi", "requests",
             ">=2.0", "2.31.0", 1, "resolved", None, "pypi",
             "2024-01-15T10:00:00+00:00"),
        )
        conn.commit()
        conn.close()

        result = storage.get_edges("owner/repo")
        assert len(result) == 1
        assert result[0].dependency_scope == "unknown"
        assert result[0].scope_confidence == "low"

    def test_null_scope_columns_get_defaults(self, storage):
        """Rows with explicit NULL scope columns read back as unknown/low."""
        conn = sqlite3.connect(storage.db_path)
        conn.execute(
            """INSERT INTO resolved_dependencies
               (repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_package, declared_specifier,
                resolved_version, depth, resolution_status,
                error_reason, source_registry, resolved_at,
                dependency_scope, scope_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("owner/repo", None, "owner/repo", "pypi", "requests",
             ">=2.0", "2.31.0", 1, "resolved", None, "pypi",
             "2024-01-15T10:00:00+00:00", None, None),
        )
        conn.commit()
        conn.close()

        result = storage.get_edges("owner/repo")
        assert len(result) == 1
        assert result[0].dependency_scope == "unknown"
        assert result[0].scope_confidence == "low"
