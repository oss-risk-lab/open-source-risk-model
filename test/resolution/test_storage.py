"""Tests for ResolvedDependencyStorage."""
import sqlite3
import pytest
from open_source_risk_model.resolution.storage import ResolvedDependencyStorage
from open_source_risk_model.resolution.models import ResolutionEdge


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
    )


@pytest.fixture
def storage(tmp_path):
    db_path = str(tmp_path / "test.db")
    return ResolvedDependencyStorage(db_path)


class TestEnsureTables:
    def test_creates_table_and_indexes(self, storage):
        """ensure_tables() creates table and indexes without error."""
        conn = sqlite3.connect(storage.db_path)
        # Check table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='resolved_dependencies'"
        ).fetchone()
        assert row is not None

        # Check indexes exist
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_resolved_deps_repo" in indexes
        assert "idx_resolved_deps_parent" in indexes
        assert "idx_resolved_deps_depth" in indexes
        conn.close()

    def test_idempotent(self, storage):
        """Calling ensure_tables() twice does not error."""
        storage.ensure_tables()
        storage.ensure_tables()


class TestStoreAndGetEdges:
    def test_round_trip_all_fields(self, storage):
        """store_edges() then get_edges() round-trips all fields correctly."""
        edge = _make_edge(
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
        )
        storage.store_edges("owner/repo", [edge])
        result = storage.get_edges("owner/repo")

        assert len(result) == 1
        r = result[0]
        assert r.repo_full_name == "owner/repo"
        assert r.parent_ecosystem is None
        assert r.parent_package == "owner/repo"
        assert r.child_ecosystem == "pypi"
        assert r.child_package == "requests"
        assert r.declared_specifier == ">=2.0"
        assert r.resolved_version == "2.31.0"
        assert r.depth == 1
        assert r.resolution_status == "resolved"
        assert r.error_reason is None
        assert r.source_registry == "pypi"
        assert r.resolved_at == "2024-01-15T10:00:00+00:00"

    def test_replaces_previous_edges(self, storage):
        """store_edges() replaces previous edges for same repo."""
        edge1 = _make_edge(child_package="old-pkg")
        storage.store_edges("owner/repo", [edge1])

        edge2 = _make_edge(child_package="new-pkg")
        storage.store_edges("owner/repo", [edge2])

        result = storage.get_edges("owner/repo")
        assert len(result) == 1
        assert result[0].child_package == "new-pkg"

    def test_empty_list_clears_edges(self, storage):
        """store_edges() with empty list clears existing edges."""
        edge = _make_edge()
        storage.store_edges("owner/repo", [edge])
        assert len(storage.get_edges("owner/repo")) == 1

        storage.store_edges("owner/repo", [])
        assert len(storage.get_edges("owner/repo")) == 0

    def test_deterministic_order(self, storage):
        """get_edges() returns depth ASC, parent_ecosystem ASC (NULLs first),
        parent_package ASC, child_package ASC."""
        edges = [
            # depth 2, parent_ecosystem="pypi"
            _make_edge(parent_ecosystem="pypi", parent_package="flask",
                       child_package="zlib", depth=2),
            # depth 1, parent_ecosystem=None (should come first)
            _make_edge(parent_ecosystem=None, parent_package="owner/repo",
                       child_package="flask", depth=1),
            # depth 2, parent_ecosystem="pypi", same parent, different child
            _make_edge(parent_ecosystem="pypi", parent_package="flask",
                       child_package="click", depth=2),
            # depth 1, parent_ecosystem=None, different child
            _make_edge(parent_ecosystem=None, parent_package="owner/repo",
                       child_package="django", depth=1),
        ]
        storage.store_edges("owner/repo", edges)
        result = storage.get_edges("owner/repo")

        assert len(result) == 4
        # depth 1 first (NULLs first for parent_ecosystem), sorted by child_package
        assert result[0].depth == 1
        assert result[0].child_package == "django"
        assert result[1].depth == 1
        assert result[1].child_package == "flask"
        # depth 2, parent_ecosystem="pypi", sorted by child_package
        assert result[2].depth == 2
        assert result[2].child_package == "click"
        assert result[3].depth == 2
        assert result[3].child_package == "zlib"


class TestHasResolvedData:
    def test_true_when_resolved_edges_exist(self, storage):
        edge = _make_edge(resolution_status="resolved")
        storage.store_edges("owner/repo", [edge])
        assert storage.has_resolved_data("owner/repo") is True

    def test_false_when_only_error_edges(self, storage):
        edge = _make_edge(resolution_status="error", error_reason="not found")
        storage.store_edges("owner/repo", [edge])
        assert storage.has_resolved_data("owner/repo") is False

    def test_false_when_no_edges(self, storage):
        assert storage.has_resolved_data("owner/repo") is False


class TestGetOldestResolvedAt:
    def test_returns_earliest_timestamp(self, storage):
        edges = [
            _make_edge(child_package="a", resolved_at="2024-01-15T10:00:00+00:00"),
            _make_edge(child_package="b", resolved_at="2024-01-10T08:00:00+00:00"),
            _make_edge(child_package="c", resolved_at="2024-01-20T12:00:00+00:00"),
        ]
        storage.store_edges("owner/repo", edges)
        assert storage.get_oldest_resolved_at("owner/repo") == "2024-01-10T08:00:00+00:00"

    def test_returns_none_when_no_edges(self, storage):
        assert storage.get_oldest_resolved_at("owner/repo") is None


class TestDeleteResolved:
    def test_removes_all_edges_returns_count(self, storage):
        edges = [
            _make_edge(child_package="a"),
            _make_edge(child_package="b"),
            _make_edge(child_package="c"),
        ]
        storage.store_edges("owner/repo", edges)
        count = storage.delete_resolved("owner/repo")
        assert count == 3
        assert len(storage.get_edges("owner/repo")) == 0

    def test_returns_zero_when_no_edges(self, storage):
        count = storage.delete_resolved("owner/repo")
        assert count == 0


class TestDuplicateParentChild:
    def test_duplicate_pairs_across_branches_allowed(self, storage):
        """Same parent-child pair can appear multiple times (no UNIQUE constraint)."""
        edge1 = _make_edge(
            parent_ecosystem="pypi", parent_package="flask",
            child_package="markupsafe", depth=2,
        )
        edge2 = _make_edge(
            parent_ecosystem="pypi", parent_package="jinja2",
            child_package="markupsafe", depth=2,
        )
        storage.store_edges("owner/repo", [edge1, edge2])
        result = storage.get_edges("owner/repo")
        assert len(result) == 2
        assert all(r.child_package == "markupsafe" for r in result)


class TestParentEcosystemNullability:
    def test_depth1_parent_ecosystem_is_null(self, storage):
        """parent_ecosystem is NULL for depth-1 edges."""
        edge = _make_edge(parent_ecosystem=None, depth=1)
        storage.store_edges("owner/repo", [edge])
        result = storage.get_edges("owner/repo")
        assert result[0].parent_ecosystem is None

    def test_deeper_edges_parent_ecosystem_non_null(self, storage):
        """parent_ecosystem is non-NULL for deeper edges."""
        edge = _make_edge(
            parent_ecosystem="pypi", parent_package="flask",
            child_package="markupsafe", depth=2,
        )
        storage.store_edges("owner/repo", [edge])
        result = storage.get_edges("owner/repo")
        assert result[0].parent_ecosystem == "pypi"
