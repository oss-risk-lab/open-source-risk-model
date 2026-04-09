"""Tests for ResolutionCache — two-tier cache for registry lookup results."""

import sqlite3
import tempfile
import os
from unittest.mock import patch, MagicMock

import pytest

from open_source_risk_model.resolution.cache import (
    ResolutionCache,
    _CACHE_MISS,
    DEFAULT_TTL_HOURS,
    NEGATIVE_TTL_HOURS,
)
from open_source_risk_model.resolution.models import (
    NormalizedPackageMetadata,
    DependencyDeclaration,
)


def _make_metadata(name="requests", version="2.31.0", ecosystem="pypi"):
    """Helper to create test metadata."""
    return NormalizedPackageMetadata(
        name=name,
        version=version,
        ecosystem=ecosystem,
        dependencies=[
            DependencyDeclaration(name="urllib3", specifier=">=1.21.1,<3"),
            DependencyDeclaration(name="certifi", specifier=">=2017.4.17"),
        ],
        source_url=f"https://pypi.org/pypi/{name}/json",
        fetched_at="2024-01-15T10:00:00+00:00",
    )


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_cache.db")


@pytest.fixture
def cache(db_path):
    return ResolutionCache(db_path)


class TestSessionCacheHit:
    """Session cache hit returns (metadata, True) without DB access."""

    def test_session_hit_returns_metadata(self, cache):
        meta = _make_metadata()
        cache._session[("pypi", "requests")] = meta
        result, found = cache.lookup("pypi", "requests")
        assert found is True
        assert result is meta

    def test_session_hit_does_not_access_db(self, cache):
        meta = _make_metadata()
        cache._session[("pypi", "requests")] = meta
        with patch.object(cache, "_read_db_cache") as mock_db:
            result, found = cache.lookup("pypi", "requests")
            mock_db.assert_not_called()
        assert found is True


class TestDBCacheHit:
    """DB cache hit returns (metadata, True) and populates session cache."""

    def test_db_hit_returns_metadata(self, cache):
        meta = _make_metadata()
        cache.store("pypi", "requests", meta)
        # Clear session cache to force DB lookup
        cache._session.clear()
        result, found = cache.lookup("pypi", "requests")
        assert found is True
        assert result.name == "requests"
        assert result.version == "2.31.0"

    def test_db_hit_populates_session(self, cache):
        meta = _make_metadata()
        cache.store("pypi", "requests", meta)
        cache._session.clear()
        cache.lookup("pypi", "requests")
        assert ("pypi", "requests") in cache._session


class TestCacheMiss:
    """Cache miss returns (None, False)."""

    def test_miss_returns_none_false(self, cache):
        result, found = cache.lookup("pypi", "nonexistent")
        assert result is None
        assert found is False


class TestStoreAndLookupRoundTrip:
    """store() then lookup() round-trips NormalizedPackageMetadata correctly."""

    def test_roundtrip_preserves_all_fields(self, cache):
        meta = _make_metadata()
        cache.store("pypi", "requests", meta)
        # Clear session to test DB round-trip
        cache._session.clear()
        result, found = cache.lookup("pypi", "requests")
        assert found is True
        assert result.name == meta.name
        assert result.version == meta.version
        assert result.ecosystem == meta.ecosystem
        assert result.source_url == meta.source_url
        assert result.fetched_at == meta.fetched_at
        assert len(result.dependencies) == len(meta.dependencies)
        for orig, loaded in zip(meta.dependencies, result.dependencies):
            assert loaded.name == orig.name
            assert loaded.specifier == orig.specifier

    def test_roundtrip_with_no_dependencies(self, cache):
        meta = NormalizedPackageMetadata(
            name="simple", version="1.0", ecosystem="pypi",
            dependencies=[], source_url="https://pypi.org/pypi/simple/json",
            fetched_at="2024-01-15T10:00:00+00:00",
        )
        cache.store("pypi", "simple", meta)
        cache._session.clear()
        result, found = cache.lookup("pypi", "simple")
        assert found is True
        assert result.dependencies == []


class TestNegativeCache:
    """store(eco, name, None) then lookup() returns (None, True) — cache hit with None."""

    def test_negative_cache_hit(self, cache):
        cache.store("pypi", "nonexistent-pkg", None)
        result, found = cache.lookup("pypi", "nonexistent-pkg")
        assert found is True
        assert result is None

    def test_negative_cache_db_roundtrip(self, cache):
        cache.store("pypi", "nonexistent-pkg", None)
        cache._session.clear()
        result, found = cache.lookup("pypi", "nonexistent-pkg")
        assert found is True
        assert result is None


class TestExpiredPositiveEntries:
    """Expired positive entries are treated as misses (TTL=168h)."""

    def test_expired_positive_is_miss(self, cache, db_path):
        meta = _make_metadata()
        cache.store("pypi", "requests", meta)
        cache._session.clear()
        # Manually set expires_at to the past in DB
        from open_source_risk_model.persistence.db import get_connection
        conn = get_connection(db_path)
        try:
            conn.execute(
                """UPDATE package_metadata_cache
                   SET expires_at = '2020-01-01T00:00:00+00:00'
                   WHERE ecosystem = 'pypi' AND package_name = 'requests'"""
            )
            conn.commit()
        finally:
            conn.close()
        result, found = cache.lookup("pypi", "requests")
        assert found is False
        assert result is None


class TestExpiredNegativeEntries:
    """Expired negative entries are treated as misses (TTL=1h)."""

    def test_expired_negative_is_miss(self, cache, db_path):
        cache.store("pypi", "gone-pkg", None)
        cache._session.clear()
        from open_source_risk_model.persistence.db import get_connection
        conn = get_connection(db_path)
        try:
            conn.execute(
                """UPDATE package_metadata_cache
                   SET expires_at = '2020-01-01T00:00:00+00:00'
                   WHERE ecosystem = 'pypi' AND package_name = 'gone-pkg'"""
            )
            conn.commit()
        finally:
            conn.close()
        result, found = cache.lookup("pypi", "gone-pkg")
        assert found is False
        assert result is None


class TestSessionBeforeDB:
    """Session cache is checked before DB cache (verify with mock)."""

    def test_session_checked_first(self, cache):
        meta = _make_metadata()
        cache._session[("pypi", "requests")] = meta
        with patch.object(cache, "_read_db_cache") as mock_db:
            result, found = cache.lookup("pypi", "requests")
            mock_db.assert_not_called()
        assert found is True
        assert result is meta


class TestEnsureTableIdempotent:
    """_ensure_table() is idempotent."""

    def test_calling_ensure_table_twice_no_error(self, db_path):
        cache1 = ResolutionCache(db_path)
        # Second call should not raise
        cache2 = ResolutionCache(db_path)
        # Both should work
        cache1.store("pypi", "pkg1", _make_metadata("pkg1"))
        cache2.store("pypi", "pkg2", _make_metadata("pkg2"))
        r1, f1 = cache2.lookup("pypi", "pkg1")
        r2, f2 = cache1.lookup("pypi", "pkg2")
        assert f1 is True
        assert f2 is True


class TestCacheKeyEcosystemSeparation:
    """Cache key is (ecosystem, package_name) — same name in different ecosystems are separate."""

    def test_same_name_different_ecosystems(self, cache):
        pypi_meta = _make_metadata(name="debug", ecosystem="pypi")
        npm_meta = _make_metadata(name="debug", ecosystem="npm", version="4.3.4")
        cache.store("pypi", "debug", pypi_meta)
        cache.store("npm", "debug", npm_meta)

        pypi_result, pypi_found = cache.lookup("pypi", "debug")
        npm_result, npm_found = cache.lookup("npm", "debug")

        assert pypi_found is True
        assert npm_found is True
        assert pypi_result.ecosystem == "pypi"
        assert npm_result.ecosystem == "npm"
        assert pypi_result.version == "2.31.0"
        assert npm_result.version == "4.3.4"

    def test_same_name_different_ecosystems_db_roundtrip(self, cache):
        pypi_meta = _make_metadata(name="debug", ecosystem="pypi")
        npm_meta = _make_metadata(name="debug", ecosystem="npm", version="4.3.4")
        cache.store("pypi", "debug", pypi_meta)
        cache.store("npm", "debug", npm_meta)
        cache._session.clear()

        pypi_result, pypi_found = cache.lookup("pypi", "debug")
        npm_result, npm_found = cache.lookup("npm", "debug")

        assert pypi_found is True
        assert npm_found is True
        assert pypi_result.ecosystem == "pypi"
        assert npm_result.ecosystem == "npm"
