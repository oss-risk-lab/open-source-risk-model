"""Property-based tests for demo repo validation correctness.

Property 1: Demo Repo Validation Correctness
For any demo repo configuration and any database state, validate_demo_repos
returns exactly those repos where all three conditions hold:
  (a) repo exists in repo_graphs
  (b) repo has at least one entry in repo_dependencies
  (c) compute_repo_insight returns a non-null score
Furthermore, for every repo that fails validation, a warning is logged
containing the repo name and the specific missing data category.

**Validates: Requirements 2.4, 2.5, 2.6, 2.7**
"""
from __future__ import annotations

import logging
import sqlite3
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from open_source_risk_model.config.demo_repos import (
    DemoRepo,
    DemoRepoConfig,
    validate_demo_repos,
)


# ── Strategies ────────────────────────────────────────────────────────

# Generate owner/repo style names
_repo_name_st = st.builds(
    lambda owner, name: f"{owner}/{name}",
    owner=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"),
    name=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"),
)

_tags_st = st.lists(
    st.sampled_from(["high-risk", "deep-tree", "well-maintained", "popular", "vulnerable"]),
    min_size=0,
    max_size=3,
    unique=True,
)

_demo_repo_st = st.builds(DemoRepo, repo=_repo_name_st, tags=_tags_st)


def _demo_repo_config_st():
    """Generate a DemoRepoConfig with 1-30 unique repos."""
    return st.lists(
        _demo_repo_st, min_size=1, max_size=30, unique_by=lambda r: r.repo
    ).map(lambda repos: DemoRepoConfig(repos=repos))


def _db_state_st(repo_names):
    """Given a list of repo names, generate random subsets for graph/deps tables."""
    names = list(repo_names)
    return st.fixed_dictionaries({
        "in_graphs": st.lists(st.sampled_from(names), unique=True) if names else st.just([]),
        "in_deps": st.lists(st.sampled_from(names), unique=True) if names else st.just([]),
        "has_insight": st.lists(st.sampled_from(names), unique=True) if names else st.just([]),
    })


def _setup_in_memory_db(in_graphs: list[str], in_deps: list[str]) -> str:
    """Create an in-memory SQLite DB with repo_graphs and repo_dependencies tables.

    Returns the special ':memory:' path. We patch get_connection to return
    the same connection so validate_demo_repos uses our in-memory DB.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE repo_graphs (
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
        CREATE TABLE repo_dependencies (
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
    for repo in in_graphs:
        conn.execute(
            "INSERT INTO repo_graphs VALUES (?, '{}', '1.0', 1, 0, '', '', '[]', NULL, 0)",
            (repo,),
        )
    for repo in in_deps:
        conn.execute(
            "INSERT INTO repo_dependencies (repo_full_name, package_name, registry_type, "
            "is_direct, is_optional, manifest_path, confidence, created_at) "
            "VALUES (?, 'pkg', 'pypi', 1, 0, 'requirements.txt', 1.0, '')",
            (repo,),
        )
    conn.commit()
    return conn


# ── Property 1: Demo Repo Validation Correctness ─────────────────────
# **Validates: Requirements 2.4, 2.5, 2.6, 2.7**


@given(data=st.data())
@settings(max_examples=100)
def test_validated_repos_match_expected_intersection(data):
    """validate_demo_repos returns exactly the repos passing all three checks."""
    config = data.draw(_demo_repo_config_st())
    repo_names = [r.repo for r in config.repos]

    db_state = data.draw(_db_state_st(repo_names))
    in_graphs = set(db_state["in_graphs"])
    in_deps = set(db_state["in_deps"])
    has_insight = set(db_state["has_insight"])

    mem_conn = _setup_in_memory_db(list(in_graphs), list(in_deps))

    # Build expected set: intersection of all three conditions
    expected = {r.repo for r in config.repos
                if r.repo in in_graphs and r.repo in in_deps and r.repo in has_insight}

    def mock_compute(repo_name, graph_repo):
        """Return insight with non-null score if repo is in has_insight set."""
        insight = MagicMock()
        if repo_name in has_insight:
            insight.graph_signal_score = 0.5
        else:
            insight.graph_signal_score = None
        return insight

    with patch("open_source_risk_model.config.demo_repos.load_demo_repos", return_value=config), \
         patch("open_source_risk_model.config.demo_repos.get_connection", return_value=mem_conn), \
         patch("open_source_risk_model.config.demo_repos.GraphRepository"), \
         patch("open_source_risk_model.config.demo_repos.compute_repo_insight", side_effect=mock_compute):
        result = validate_demo_repos(":memory:")

    actual = {r.repo for r in result}
    assert actual == expected, (
        f"Expected {expected}, got {actual}. "
        f"graphs={in_graphs}, deps={in_deps}, insight={has_insight}"
    )

    mem_conn.close()


@given(data=st.data())
@settings(max_examples=100)
def test_warnings_logged_for_failing_repos(data):
    """A warning is logged for each repo failing validation with the correct category."""
    config = data.draw(_demo_repo_config_st())
    repo_names = [r.repo for r in config.repos]

    db_state = data.draw(_db_state_st(repo_names))
    in_graphs = set(db_state["in_graphs"])
    in_deps = set(db_state["in_deps"])
    has_insight = set(db_state["has_insight"])

    mem_conn = _setup_in_memory_db(list(in_graphs), list(in_deps))

    def mock_compute(repo_name, graph_repo):
        insight = MagicMock()
        if repo_name in has_insight:
            insight.graph_signal_score = 0.5
        else:
            insight.graph_signal_score = None
        return insight

    with patch("open_source_risk_model.config.demo_repos.load_demo_repos", return_value=config), \
         patch("open_source_risk_model.config.demo_repos.get_connection", return_value=mem_conn), \
         patch("open_source_risk_model.config.demo_repos.GraphRepository"), \
         patch("open_source_risk_model.config.demo_repos.compute_repo_insight", side_effect=mock_compute), \
         patch("open_source_risk_model.config.demo_repos.logger") as mock_logger:
        validate_demo_repos(":memory:")

    # Collect all warning calls
    warning_calls = [
        call.args for call in mock_logger.warning.call_args_list
    ]
    warning_messages = [args[0] % args[1:] for args in warning_calls]

    for demo in config.repos:
        repo = demo.repo
        if repo not in in_graphs:
            assert any(repo in msg and "missing graph data" in msg for msg in warning_messages), \
                f"Expected 'missing graph data' warning for {repo}"
        if repo not in in_deps:
            assert any(repo in msg and "missing dependencies data" in msg for msg in warning_messages), \
                f"Expected 'missing dependencies data' warning for {repo}"
        if repo not in has_insight:
            assert any(repo in msg and "missing insight score" in msg for msg in warning_messages), \
                f"Expected 'missing insight score' warning for {repo}"
