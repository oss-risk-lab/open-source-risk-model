"""
Unit tests for DBRetriever.

Tests database retrieval with split responsibilities:
- retrieve_summary for fast query-time access
- retrieve_full_evidence for detailed inspection
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.open_source_risk_model.query.db_retriever import DBRetriever


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        yield db_path


@pytest.fixture
def db_with_data(temp_db):
    """Create database with sample ingestion results."""
    conn = sqlite3.connect(temp_db)

    # Create table
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

    # Insert sample data
    now = datetime.now(timezone.utc).isoformat()

    repos = [
        {
            "repo_full_name": "numpy/numpy",
            "maintenance_risk_score": 0.15,
            "risk_band": "low",
            "features": {
                "days_since_last_push": 5.0,
                "stars_count": 25000.0,
                "contributors_count": 500.0,
            },
            "score_completeness": "full",
            "snapshot": {"owner": "numpy", "name": "numpy", "stars": 25000},
            "contributors": [{"login": "user1", "contributions": 100}],
            "issues": [{"number": 1, "state": "open"}],
            "metadata": {"api_calls": 10, "duration_ms": 5000},
        },
        {
            "repo_full_name": "flask/flask",
            "maintenance_risk_score": 0.25,
            "risk_band": "low",
            "features": {
                "days_since_last_push": 10.0,
                "stars_count": 60000.0,
                "contributors_count": 800.0,
            },
            "score_completeness": "provisional",
            "snapshot": {"owner": "flask", "name": "flask", "stars": 60000},
            "contributors": [{"login": "user2", "contributions": 200}],
            "issues": [],
            "metadata": {"api_calls": 5, "duration_ms": 2000},
        },
    ]

    for repo in repos:
        conn.execute(
            """
            INSERT INTO ingestion_results
            (repo_full_name, maintenance_risk_score, risk_band, features_json,
             score_completeness, ingested_at, snapshot_json, contributors_json,
             issues_json, metadata_json, api_calls_used, ingestion_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                repo["repo_full_name"],
                repo["maintenance_risk_score"],
                repo["risk_band"],
                json.dumps(repo["features"]),
                repo["score_completeness"],
                now,
                json.dumps(repo["snapshot"]),
                json.dumps(repo["contributors"]),
                json.dumps(repo["issues"]),
                json.dumps(repo["metadata"]),
                repo["metadata"]["api_calls"],
                repo["metadata"]["duration_ms"],
            ),
        )

    conn.commit()
    conn.close()

    return temp_db


def test_retrieve_summary_single_repo(db_with_data):
    """Test retrieving summary for single repository."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["numpy/numpy"])

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.repo_full_name == "numpy/numpy"
    assert summary.maintenance_risk_score == 0.15
    assert summary.risk_band == "low"
    assert "days_since_last_push" in summary.features
    assert summary.features["days_since_last_push"] == 5.0
    assert summary.provenance.source == "database"
    assert summary.provenance.score_completeness == "full"


def test_retrieve_summary_multiple_repos(db_with_data):
    """Test retrieving summary for multiple repositories."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["numpy/numpy", "flask/flask"])

    assert len(summaries) == 2
    repo_names = {s.repo_full_name for s in summaries}
    assert repo_names == {"numpy/numpy", "flask/flask"}


def test_retrieve_summary_missing_repo(db_with_data):
    """Test retrieving summary for non-existent repository."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["missing/repo"])

    assert len(summaries) == 0


def test_retrieve_summary_mixed_found_and_missing(db_with_data):
    """Test retrieving summary with mix of found and missing repos."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["numpy/numpy", "missing/repo", "flask/flask"])

    assert len(summaries) == 2
    repo_names = {s.repo_full_name for s in summaries}
    assert repo_names == {"numpy/numpy", "flask/flask"}


def test_retrieve_summary_empty_input(db_with_data):
    """Test retrieving summary with empty input."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary([])

    assert len(summaries) == 0


def test_retrieve_full_evidence_found(db_with_data):
    """Test retrieving full evidence for existing repository."""
    retriever = DBRetriever(db_with_data)

    evidence = retriever.retrieve_full_evidence("numpy/numpy")

    assert evidence is not None
    assert evidence.summary.repo_full_name == "numpy/numpy"
    assert evidence.summary.maintenance_risk_score == 0.15
    assert evidence.snapshot["owner"] == "numpy"
    assert len(evidence.contributors) == 1
    assert evidence.contributors[0]["login"] == "user1"
    assert len(evidence.issues) == 1
    assert evidence.ingestion_metadata["api_calls"] == 10


def test_retrieve_full_evidence_not_found(db_with_data):
    """Test retrieving full evidence for non-existent repository."""
    retriever = DBRetriever(db_with_data)

    evidence = retriever.retrieve_full_evidence("missing/repo")

    assert evidence is None


def test_retrieve_full_evidence_provisional_score(db_with_data):
    """Test retrieving full evidence for provisional score."""
    retriever = DBRetriever(db_with_data)

    evidence = retriever.retrieve_full_evidence("flask/flask")

    assert evidence is not None
    assert evidence.summary.provenance.score_completeness == "provisional"
    assert len(evidence.issues) == 0  # Provisional mode has no issues


def test_summary_includes_all_features(db_with_data):
    """Test that summary includes all feature values."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["numpy/numpy"])

    assert len(summaries) == 1
    features = summaries[0].features
    assert "days_since_last_push" in features
    assert "stars_count" in features
    assert "contributors_count" in features


def test_provenance_timestamp_parsing(db_with_data):
    """Test that provenance timestamp is correctly parsed."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["numpy/numpy"])

    assert len(summaries) == 1
    last_updated = summaries[0].provenance.last_updated
    assert isinstance(last_updated, datetime)
    assert last_updated.tzinfo is not None  # Should have timezone


def test_full_evidence_includes_summary(db_with_data):
    """Test that full evidence includes complete summary."""
    retriever = DBRetriever(db_with_data)

    evidence = retriever.retrieve_full_evidence("numpy/numpy")

    assert evidence is not None
    assert evidence.summary.repo_full_name == "numpy/numpy"
    assert evidence.summary.maintenance_risk_score == 0.15
    assert evidence.summary.risk_band == "low"
    assert len(evidence.summary.features) > 0


def test_empty_json_fields_handled(temp_db):
    """Test handling of NULL/empty JSON fields."""
    conn = sqlite3.connect(temp_db)

    # Create table
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

    # Insert repo with NULL JSON fields
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO ingestion_results
        (repo_full_name, maintenance_risk_score, risk_band, features_json,
         score_completeness, ingested_at, snapshot_json, contributors_json,
         issues_json, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
    """,
        ("test/repo", 0.5, "medium", json.dumps({"feature1": 1.0}), "full", now),
    )

    conn.commit()
    conn.close()

    retriever = DBRetriever(temp_db)
    evidence = retriever.retrieve_full_evidence("test/repo")

    assert evidence is not None
    assert evidence.snapshot == {}
    assert evidence.contributors == []
    assert evidence.issues == []
    assert evidence.ingestion_metadata == {}


def test_risk_band_values(db_with_data):
    """Test that risk band values are correctly retrieved."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["numpy/numpy", "flask/flask"])

    assert len(summaries) == 2
    for summary in summaries:
        assert summary.risk_band in ["low", "medium", "high", "critical"]


def test_score_range_validation(db_with_data):
    """Test that scores are within valid range."""
    retriever = DBRetriever(db_with_data)

    summaries = retriever.retrieve_summary(["numpy/numpy", "flask/flask"])

    assert len(summaries) == 2
    for summary in summaries:
        assert 0.0 <= summary.maintenance_risk_score <= 1.0
