"""Unit tests for the GET /api/stats endpoint.

Tests cover:
- Empty DB returns zeros (total_repos=0, fully_analyzed_repos=0, coverage_ratio=0.00)
- Single repo in both tables returns correct values
- Mixed state (repo in graphs but not deps) returns correct fully_analyzed count
- DB unavailable returns 503

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app, raise_server_exceptions=False)

# ── Shared DB helpers (same pattern as test_stats_computation_properties.py) ──

_db_counter = 0


def _setup_in_memory_db(
    graph_repos: list[str], dep_repos: list[str]
) -> tuple[str, sqlite3.Connection]:
    """Create a named in-memory SQLite DB and return (uri, keep-alive conn)."""
    global _db_counter
    _db_counter += 1
    db_name = f"test_stats_unit_{_db_counter}"
    uri = f"file:{db_name}?mode=memory&cache=shared"

    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            graph_json TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            data_sources TEXT NOT NULL,
            warnings TEXT,
            generation_time_ms INTEGER
        )
    """)
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
            UNIQUE(repo_full_name, package_name, manifest_path)
        )
    """)
    for repo in graph_repos:
        conn.execute(
            "INSERT OR IGNORE INTO repo_graphs VALUES "
            "(?, '{}', '1.0', 1, 0, '', '', '[]', NULL, 0)",
            (repo,),
        )
    for repo in dep_repos:
        conn.execute(
            "INSERT OR IGNORE INTO repo_dependencies "
            "(repo_full_name, package_name, registry_type, "
            "is_direct, is_optional, manifest_path, confidence, created_at) "
            "VALUES (?, 'pkg', 'pypi', 1, 0, 'requirements.txt', 1.0, '')",
            (repo,),
        )
    conn.commit()
    return uri, conn


def _make_get_connection(uri: str):
    """Return a factory that creates new connections to the shared in-memory DB."""
    def _get_connection(db_path=None):
        return sqlite3.connect(uri, uri=True, check_same_thread=False)
    return _get_connection


# ── Tests ─────────────────────────────────────────────────────────────


def test_empty_db_returns_zeros():
    """Empty database should return total_repos=0, fully_analyzed_repos=0, coverage_ratio=0.00.

    Validates: Requirements 4.1, 4.2, 4.5
    """
    uri, seed_conn = _setup_in_memory_db([], [])
    try:
        with patch("api.app.get_connection", side_effect=_make_get_connection(uri)):
            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_repos"] == 0
        assert data["fully_analyzed_repos"] == 0
        assert data["coverage_ratio"] == 0.00
    finally:
        seed_conn.close()


def test_single_repo_in_both_tables():
    """A repo present in both repo_graphs and repo_dependencies should be counted correctly.

    Validates: Requirements 4.2, 4.3, 4.4
    """
    uri, seed_conn = _setup_in_memory_db(
        graph_repos=["owner/repo"],
        dep_repos=["owner/repo"],
    )
    try:
        with patch("api.app.get_connection", side_effect=_make_get_connection(uri)):
            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_repos"] == 1
        assert data["fully_analyzed_repos"] == 1
        assert data["coverage_ratio"] == 1.00
    finally:
        seed_conn.close()


def test_mixed_state_repo_in_graphs_but_not_deps():
    """Repos only in repo_graphs (not in repo_dependencies) should not count as fully analyzed.

    Validates: Requirements 4.3, 4.4
    """
    uri, seed_conn = _setup_in_memory_db(
        graph_repos=["owner/alpha", "owner/beta", "owner/gamma"],
        dep_repos=["owner/alpha"],  # only alpha has deps
    )
    try:
        with patch("api.app.get_connection", side_effect=_make_get_connection(uri)):
            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_repos"] == 3
        assert data["fully_analyzed_repos"] == 1
        assert data["coverage_ratio"] == 0.33  # round(1/3, 2)
    finally:
        seed_conn.close()


def test_db_unavailable_returns_503():
    """When the database connection fails, the endpoint should return HTTP 503.

    Validates: Requirement 4.1 (error handling)
    """
    def _failing_get_connection(db_path=None):
        raise Exception("Database is not available")

    with patch("api.app.get_connection", side_effect=_failing_get_connection):
        response = client.get("/api/stats")

    assert response.status_code == 503
    assert "Database is not available" in response.json()["detail"]
