"""
Property-based tests for DBRetriever.

Property 29: Database Retrieval Completeness
- All requested repos that exist in database are returned
- No repos are returned that weren't requested
- Full evidence contains all summary data
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.open_source_risk_model.query.db_retriever import DBRetriever


def create_test_db_with_repos(db_path: str, repos: list[str]) -> None:
    """Create test database with specified repositories."""
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE ingestion_results (
            repo_full_name TEXT PRIMARY KEY,
            maintenance_risk_score REAL NOT NULL,
            risk_band TEXT NOT NULL,
            features_json TEXT NOT NULL,
            score_completeness TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            snapshot_json TEXT,
            contributors_json TEXT,
            issues_json TEXT,
            metadata_json TEXT,
            api_calls_used INTEGER,
            ingestion_time_ms INTEGER
        )
    """)

    now = datetime.now(timezone.utc).isoformat()

    for repo in repos:
        conn.execute(
            """
            INSERT INTO ingestion_results
            (repo_full_name, maintenance_risk_score, risk_band, features_json,
             score_completeness, ingested_at, snapshot_json, contributors_json,
             issues_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                repo,
                0.5,
                "medium",
                json.dumps({"feature1": 1.0}),
                "full",
                now,
                json.dumps({"owner": repo.split("/")[0], "name": repo.split("/")[1]}),
                json.dumps([{"login": "user1"}]),
                json.dumps([{"number": 1}]),
                json.dumps({"api_calls": 10}),
            ),
        )

    conn.commit()
    conn.close()


@pytest.mark.property_test
@given(
    db_repos=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=0,
        max_size=20,
        unique=True,
    ),
    requested_repos=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=0,
        max_size=20,
        unique=True,
    ),
)
@settings(max_examples=100, deadline=None)
def test_database_retrieval_completeness(db_repos, requested_repos):
    """
    Property 29: Database Retrieval Completeness.

    Validates:
    - All requested repos that exist in database are returned
    - No repos are returned that weren't requested
    - Returned repos are subset of requested repos
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        create_test_db_with_repos(db_path, db_repos)

        retriever = DBRetriever(db_path)
        summaries = retriever.retrieve_summary(requested_repos)

        # Extract returned repo names
        returned_repos = {s.repo_full_name for s in summaries}

        # Property 1: All returned repos were requested
        assert returned_repos.issubset(set(requested_repos))

        # Property 2: All returned repos exist in database
        assert returned_repos.issubset(set(db_repos))

        # Property 3: All repos that are both requested AND in database are returned
        expected_repos = set(requested_repos) & set(db_repos)
        assert returned_repos == expected_repos


@pytest.mark.property_test
@given(
    repo_name=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ).map(lambda s: f"{s[:10]}/{s[10:]}"),
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    features=st.dictionaries(
        st.text(min_size=1, max_size=20),
        st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    ),
)
@settings(max_examples=100, deadline=None)
def test_full_evidence_contains_summary_data(repo_name, score, features):
    """
    Property 29: Full Evidence Completeness.

    Validates:
    - Full evidence contains all summary data
    - Summary within full evidence matches standalone summary
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE ingestion_results (
                repo_full_name TEXT PRIMARY KEY,
                maintenance_risk_score REAL NOT NULL,
                risk_band TEXT NOT NULL,
                features_json TEXT NOT NULL,
                score_completeness TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                snapshot_json TEXT,
                contributors_json TEXT,
                issues_json TEXT,
                metadata_json TEXT,
                api_calls_used INTEGER,
                ingestion_time_ms INTEGER
            )
        """)

        now = datetime.now(timezone.utc).isoformat()
        risk_band = "low" if score < 0.3 else "medium" if score < 0.6 else "high"

        conn.execute(
            """
            INSERT INTO ingestion_results
            (repo_full_name, maintenance_risk_score, risk_band, features_json,
             score_completeness, ingested_at, snapshot_json, contributors_json,
             issues_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                repo_name,
                score,
                risk_band,
                json.dumps(features),
                "full",
                now,
                json.dumps({"owner": "test"}),
                json.dumps([{"login": "user1"}]),
                json.dumps([{"number": 1}]),
                json.dumps({"api_calls": 10}),
            ),
        )

        conn.commit()
        conn.close()

        retriever = DBRetriever(db_path)

        # Get standalone summary
        summaries = retriever.retrieve_summary([repo_name])
        assert len(summaries) == 1
        standalone_summary = summaries[0]

        # Get full evidence
        full_evidence = retriever.retrieve_full_evidence(repo_name)
        assert full_evidence is not None

        # Property: Full evidence summary matches standalone summary
        assert full_evidence.summary.repo_full_name == standalone_summary.repo_full_name
        assert (
            full_evidence.summary.maintenance_risk_score
            == standalone_summary.maintenance_risk_score
        )
        assert full_evidence.summary.risk_band == standalone_summary.risk_band
        assert full_evidence.summary.features == standalone_summary.features
        assert (
            full_evidence.summary.provenance.source == standalone_summary.provenance.source
        )
        assert (
            full_evidence.summary.provenance.score_completeness
            == standalone_summary.provenance.score_completeness
        )


@pytest.mark.property_test
@given(
    repos=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=1,
        max_size=10,
        unique=True,
    )
)
@settings(max_examples=100, deadline=None)
def test_summary_retrieval_order_independence(repos):
    """
    Property 29: Order Independence.

    Validates:
    - Retrieval results are independent of request order
    - Same repos returned regardless of order
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        create_test_db_with_repos(db_path, repos)

        retriever = DBRetriever(db_path)

        # Retrieve in original order
        summaries1 = retriever.retrieve_summary(repos)
        repos1 = {s.repo_full_name for s in summaries1}

        # Retrieve in reverse order
        summaries2 = retriever.retrieve_summary(list(reversed(repos)))
        repos2 = {s.repo_full_name for s in summaries2}

        # Property: Same repos returned regardless of order
        assert repos1 == repos2
        assert len(summaries1) == len(summaries2)


@pytest.mark.property_test
@given(
    repo_name=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ).map(lambda s: f"{s[:10]}/{s[10:]}"),
)
@settings(max_examples=100, deadline=None)
def test_missing_repo_returns_none(repo_name):
    """
    Property 29: Missing Repo Handling.

    Validates:
    - retrieve_full_evidence returns None for missing repos
    - retrieve_summary returns empty list for missing repos
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")

        # Create empty database
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE ingestion_results (
                repo_full_name TEXT PRIMARY KEY,
                maintenance_risk_score REAL NOT NULL,
                risk_band TEXT NOT NULL,
                features_json TEXT NOT NULL,
                score_completeness TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                snapshot_json TEXT,
                contributors_json TEXT,
                issues_json TEXT,
                metadata_json TEXT,
                api_calls_used INTEGER,
                ingestion_time_ms INTEGER
            )
        """)
        conn.commit()
        conn.close()

        retriever = DBRetriever(db_path)

        # Property: Missing repo returns None for full evidence
        full_evidence = retriever.retrieve_full_evidence(repo_name)
        assert full_evidence is None

        # Property: Missing repo returns empty list for summary
        summaries = retriever.retrieve_summary([repo_name])
        assert len(summaries) == 0
