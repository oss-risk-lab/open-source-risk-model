"""Property-based tests for stats computation correctness.

Property 2: Stats Computation Correctness
For any database state with an arbitrary set of repos in repo_graphs and an
arbitrary (possibly overlapping) set of repos in repo_dependencies, the stats
computation SHALL return:
  - total_repos == distinct count of repos in repo_graphs
  - fully_analyzed_repos == distinct count of repos present in BOTH tables
  - coverage_ratio == round(fully_analyzed / total, 2) when total > 0, or 0.00

**Validates: Requirements 4.2, 4.3, 4.4, 4.5**
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from api.app import app

client = TestClient(app, raise_server_exceptions=False)

# ── Strategies ────────────────────────────────────────────────────────

_repo_name_st = st.builds(
    lambda owner, name: f"{owner}/{name}",
    owner=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"),
    name=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"),
)

_repo_set_st = st.lists(_repo_name_st, min_size=0, max_size=50, unique=True)


# Use a counter to give each test invocation a unique shared-cache DB name
_db_counter = 0


def _setup_in_memory_db(graph_repos: list[str], dep_repos: list[str]) -> str:
    """Create a named in-memory SQLite DB and return its URI name.

    Uses SQLite shared-cache URIs so that multiple connections (across threads)
    can access the same in-memory database.  The endpoint calls get_connection
    which returns a new connection, and then closes it — so we need a shared
    in-memory DB rather than passing a single connection object.
    """
    global _db_counter
    _db_counter += 1
    db_name = f"test_stats_{_db_counter}"
    uri = f"file:{db_name}?mode=memory&cache=shared"

    # Seed the database via a setup connection
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
    return uri, conn  # keep conn alive so shared-cache DB persists


def _make_get_connection(uri: str):
    """Return a factory that creates new connections to the shared in-memory DB."""
    def _get_connection(db_path=None):
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        return conn
    return _get_connection


# ── Property 2: Stats Computation Correctness ─────────────────────────
# **Validates: Requirements 4.2, 4.3, 4.4, 4.5**


@given(graph_repos=_repo_set_st, dep_repos=_repo_set_st)
@settings(max_examples=100)
def test_stats_computation_correctness(graph_repos: list[str], dep_repos: list[str]):
    """Stats endpoint returns correct total_repos, fully_analyzed_repos, and coverage_ratio."""
    uri, seed_conn = _setup_in_memory_db(graph_repos, dep_repos)

    try:
        # Expected values
        expected_total = len(set(graph_repos))
        expected_fully = len(set(graph_repos) & set(dep_repos))
        if expected_total > 0:
            expected_ratio = round(expected_fully / expected_total, 2)
        else:
            expected_ratio = 0.00

        with patch("api.app.get_connection", side_effect=_make_get_connection(uri)):
            response = client.get("/api/stats")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()

        assert data["total_repos"] == expected_total, (
            f"total_repos: expected {expected_total}, got {data['total_repos']}. "
            f"graph_repos={graph_repos}"
        )
        assert data["fully_analyzed_repos"] == expected_fully, (
            f"fully_analyzed_repos: expected {expected_fully}, "
            f"got {data['fully_analyzed_repos']}. "
            f"graph_repos={graph_repos}, dep_repos={dep_repos}"
        )
        assert data["coverage_ratio"] == expected_ratio, (
            f"coverage_ratio: expected {expected_ratio}, "
            f"got {data['coverage_ratio']}. "
            f"total={expected_total}, fully={expected_fully}"
        )
    finally:
        seed_conn.close()


@given(dep_repos=_repo_set_st)
@settings(max_examples=100)
def test_fully_analyzed_only_counts_repos_in_both_tables(dep_repos: list[str]):
    """fully_analyzed_repos counts only repos present in BOTH repo_graphs AND repo_dependencies."""
    graph_repos = ["owner/alpha", "owner/beta", "owner/gamma"]
    uri, seed_conn = _setup_in_memory_db(graph_repos, dep_repos)

    try:
        graph_set = set(graph_repos)
        dep_set = set(dep_repos)
        expected_fully = len(graph_set & dep_set)

        with patch("api.app.get_connection", side_effect=_make_get_connection(uri)):
            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["fully_analyzed_repos"] == expected_fully, (
            f"Expected {expected_fully} repos in both tables, "
            f"got {data['fully_analyzed_repos']}. "
            f"graph={graph_set}, deps={dep_set}, "
            f"intersection={graph_set & dep_set}"
        )
    finally:
        seed_conn.close()
