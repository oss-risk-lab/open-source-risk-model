"""
Unit tests for LiveRepoIngestor.

Tests on-demand ingestion with flexible persistence modes:
- temporary: In-query use only
- cache: Store with 1-hour TTL
- database: Promote to main database
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.open_source_risk_model.ingestion.models import IngestionResult
from src.open_source_risk_model.query.live_repo_ingestor import LiveRepoIngestor


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = str(Path(tmpdir) / "cache")
        db_path = str(Path(tmpdir) / "test.db")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        yield cache_dir, db_path


@pytest.fixture
def mock_pipeline():
    """Create mock ingestion pipeline."""
    with patch(
        "src.open_source_risk_model.query.live_repo_ingestor.IngestionPipeline"
    ) as mock:
        yield mock


def test_ingest_provisional_mode_temporary(temp_dirs, mock_pipeline):
    """Test ingesting in provisional mode with temporary persistence."""
    cache_dir, db_path = temp_dirs

    # Mock successful ingestion
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="numpy/numpy",
        success=True,
        features={"days_since_last_push": 5.0, "stars_count": 25000.0},
        maintenance_risk_score=0.15,
        score_completeness="provisional",
        api_calls_made=5,
        ingestion_time_seconds=2.5,
        missing_feature_categories=[],
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="temporary"
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.repo_full_name == "numpy/numpy"
    assert summary.maintenance_risk_score == 0.15
    assert summary.risk_band == "low"
    assert summary.provenance.source == "live_fetch"
    assert summary.provenance.score_completeness == "provisional"


def test_ingest_full_mode_temporary(temp_dirs, mock_pipeline):
    """Test ingesting in full mode with temporary persistence."""
    cache_dir, db_path = temp_dirs

    # Mock successful ingestion
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="flask/flask",
        success=True,
        features={
            "days_since_last_push": 10.0,
            "stars_count": 60000.0,
            "fraction_issues_closed_12mo": 0.8,
        },
        maintenance_risk_score=0.25,
        score_completeness="full",
        api_calls_made=15,
        ingestion_time_seconds=8.5,
        missing_feature_categories=[],
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["flask/flask"], mode="full", persistence_mode="temporary"
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.provenance.score_completeness == "full"
    assert summary.provenance.api_calls_made == 15


def test_ingest_cache_persistence(temp_dirs, mock_pipeline):
    """Test ingesting with cache persistence."""
    cache_dir, db_path = temp_dirs

    # Mock successful ingestion
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="numpy/numpy",
        success=True,
        features={"days_since_last_push": 5.0},
        maintenance_risk_score=0.15,
        score_completeness="provisional",
        api_calls_made=5,
        ingestion_time_seconds=2.5,
        missing_feature_categories=[],
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    # First ingestion - should call pipeline
    summaries1 = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="cache"
    )
    assert len(summaries1) == 1
    assert mock_instance.ingest_single.call_count == 1

    # Second ingestion - should use cache
    summaries2 = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="cache"
    )
    assert len(summaries2) == 1
    assert mock_instance.ingest_single.call_count == 1  # Not called again


def test_ingest_database_persistence(temp_dirs, mock_pipeline):
    """Test ingesting with database persistence."""
    cache_dir, db_path = temp_dirs

    # Mock successful ingestion
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="numpy/numpy",
        success=True,
        features={"days_since_last_push": 5.0},
        maintenance_risk_score=0.15,
        score_completeness="provisional",
        api_calls_made=5,
        ingestion_time_seconds=2.5,
        missing_feature_categories=[],
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="database"
    )

    assert len(summaries) == 1

    # Verify database entry
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT repo_full_name, maintenance_risk_score FROM ingestion_results WHERE repo_full_name = ?",
        ("numpy/numpy",),
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "numpy/numpy"
    assert row[1] == 0.15


def test_ingest_multiple_repos(temp_dirs, mock_pipeline):
    """Test ingesting multiple repositories."""
    cache_dir, db_path = temp_dirs

    # Mock successful ingestions
    mock_instance = mock_pipeline.return_value

    def mock_ingest_single(repo_id, mode):
        if repo_id == "numpy/numpy":
            return IngestionResult(
                repo_full_name="numpy/numpy",
                success=True,
                features={"days_since_last_push": 5.0},
                maintenance_risk_score=0.15,
                score_completeness="provisional",
                api_calls_made=5,
                ingestion_time_seconds=2.5,
                missing_feature_categories=[],
            )
        elif repo_id == "flask/flask":
            return IngestionResult(
                repo_full_name="flask/flask",
                success=True,
                features={"days_since_last_push": 10.0},
                maintenance_risk_score=0.25,
                score_completeness="provisional",
                api_calls_made=5,
                ingestion_time_seconds=2.5,
                missing_feature_categories=[],
            )

    mock_instance.ingest_single.side_effect = mock_ingest_single

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["numpy/numpy", "flask/flask"], mode="provisional", persistence_mode="temporary"
    )

    assert len(summaries) == 2
    repo_names = {s.repo_full_name for s in summaries}
    assert repo_names == {"numpy/numpy", "flask/flask"}


def test_ingest_failed_ingestion_skipped(temp_dirs, mock_pipeline):
    """Test that failed ingestions are skipped."""
    cache_dir, db_path = temp_dirs

    # Mock failed ingestion
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="invalid/repo",
        success=False,
        features=None,
        maintenance_risk_score=None,
        score_completeness="provisional",
        api_calls_made=1,
        ingestion_time_seconds=0.5,
        error="Repository not found",
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["invalid/repo"], mode="provisional", persistence_mode="temporary"
    )

    assert len(summaries) == 0


def test_ingest_mixed_success_and_failure(temp_dirs, mock_pipeline):
    """Test ingesting with mix of successful and failed repos."""
    cache_dir, db_path = temp_dirs

    # Mock mixed results
    mock_instance = mock_pipeline.return_value

    def mock_ingest_single(repo_id, mode):
        if repo_id == "numpy/numpy":
            return IngestionResult(
                repo_full_name="numpy/numpy",
                success=True,
                features={"days_since_last_push": 5.0},
                maintenance_risk_score=0.15,
                score_completeness="provisional",
                api_calls_made=5,
                ingestion_time_seconds=2.5,
                missing_feature_categories=[],
            )
        else:
            return IngestionResult(
                repo_full_name="invalid/repo",
                success=False,
                features=None,
                maintenance_risk_score=None,
                score_completeness="provisional",
                api_calls_made=1,
                ingestion_time_seconds=0.5,
                error="Repository not found",
            )

    mock_instance.ingest_single.side_effect = mock_ingest_single

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["numpy/numpy", "invalid/repo"], mode="provisional", persistence_mode="temporary"
    )

    assert len(summaries) == 1
    assert summaries[0].repo_full_name == "numpy/numpy"


def test_ingest_empty_input(temp_dirs, mock_pipeline):
    """Test ingesting with empty input."""
    cache_dir, db_path = temp_dirs

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest([], mode="provisional", persistence_mode="temporary")

    assert len(summaries) == 0


def test_risk_band_calculation(temp_dirs, mock_pipeline):
    """Test risk band calculation from scores."""
    cache_dir, db_path = temp_dirs

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    assert ingestor._calculate_risk_band(0.1) == "low"
    assert ingestor._calculate_risk_band(0.29) == "low"
    assert ingestor._calculate_risk_band(0.3) == "medium"
    assert ingestor._calculate_risk_band(0.59) == "medium"
    assert ingestor._calculate_risk_band(0.6) == "high"
    assert ingestor._calculate_risk_band(0.79) == "high"
    assert ingestor._calculate_risk_band(0.8) == "critical"
    assert ingestor._calculate_risk_band(1.0) == "critical"


def test_provenance_includes_api_calls(temp_dirs, mock_pipeline):
    """Test that provenance includes API call count."""
    cache_dir, db_path = temp_dirs

    # Mock successful ingestion
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="numpy/numpy",
        success=True,
        features={"days_since_last_push": 5.0},
        maintenance_risk_score=0.15,
        score_completeness="provisional",
        api_calls_made=5,
        ingestion_time_seconds=2.5,
        missing_feature_categories=[],
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="temporary"
    )

    assert len(summaries) == 1
    assert summaries[0].provenance.api_calls_made == 5
    assert summaries[0].provenance.ingestion_time_seconds == 2.5


def test_provenance_includes_missing_categories(temp_dirs, mock_pipeline):
    """Test that provenance includes missing feature categories."""
    cache_dir, db_path = temp_dirs

    # Mock ingestion with missing categories
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="numpy/numpy",
        success=True,
        features={"days_since_last_push": 5.0},
        maintenance_risk_score=0.15,
        score_completeness="provisional",
        api_calls_made=5,
        ingestion_time_seconds=2.5,
        missing_feature_categories=["issue_lifecycle"],
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    summaries = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="temporary"
    )

    assert len(summaries) == 1
    assert "issue_lifecycle" in summaries[0].provenance.missing_feature_categories


def test_database_persistence_also_caches(temp_dirs, mock_pipeline):
    """Test that database persistence also saves to cache."""
    cache_dir, db_path = temp_dirs

    # Mock successful ingestion
    mock_instance = mock_pipeline.return_value
    mock_instance.ingest_single.return_value = IngestionResult(
        repo_full_name="numpy/numpy",
        success=True,
        features={"days_since_last_push": 5.0},
        maintenance_risk_score=0.15,
        score_completeness="provisional",
        api_calls_made=5,
        ingestion_time_seconds=2.5,
        missing_feature_categories=[],
    )

    ingestor = LiveRepoIngestor(
        github_token="test_token", cache_dir=cache_dir, db_path=db_path
    )

    # First ingestion with database persistence
    summaries1 = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="database"
    )
    assert len(summaries1) == 1
    assert mock_instance.ingest_single.call_count == 1

    # Second ingestion - should use cache
    summaries2 = ingestor.ingest(
        ["numpy/numpy"], mode="provisional", persistence_mode="database"
    )
    assert len(summaries2) == 1
    assert mock_instance.ingest_single.call_count == 1  # Not called again
