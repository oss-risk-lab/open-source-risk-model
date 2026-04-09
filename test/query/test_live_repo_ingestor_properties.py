"""
Property-based tests for LiveRepoIngestor.

Property 31: Live Ingestion Mode Correctness (REQUIRED FOR MVP)
- Provisional mode returns provisional scores
- Full mode returns full scores
- Mode is correctly propagated to pipeline

Property 32: Persistence Mode Enforcement (REQUIRED FOR MVP)
- Temporary mode does not persist
- Cache mode persists to cache with TTL
- Database mode persists to database
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.open_source_risk_model.ingestion.models import IngestionResult
from src.open_source_risk_model.query.live_repo_ingestor import LiveRepoIngestor


@pytest.mark.property_test
@given(
    repo_name=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ).map(lambda s: f"{s[:10]}/{s[10:]}"),
    mode=st.sampled_from(["provisional", "full"]),
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_live_ingestion_mode_correctness(repo_name, mode, score):
    """
    Property 31: Live Ingestion Mode Correctness (REQUIRED FOR MVP).

    Validates:
    - Provisional mode returns provisional scores
    - Full mode returns full scores
    - Mode is correctly propagated to pipeline
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = str(Path(tmpdir) / "cache")
        db_path = str(Path(tmpdir) / "test.db")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        with patch(
            "src.open_source_risk_model.query.live_repo_ingestor.IngestionPipeline"
        ) as mock_pipeline:
            # Mock successful ingestion
            mock_instance = mock_pipeline.return_value
            mock_instance.ingest_single.return_value = IngestionResult(
                repo_full_name=repo_name,
                success=True,
                features={"days_since_last_push": 5.0},
                maintenance_risk_score=score,
                score_completeness=mode,  # Should match requested mode
                api_calls_made=5 if mode == "provisional" else 15,
                ingestion_time_seconds=2.5,
                missing_feature_categories=[] if mode == "full" else ["issue_lifecycle"],
            )

            ingestor = LiveRepoIngestor(
                github_token="test_token", cache_dir=cache_dir, db_path=db_path
            )

            summaries = ingestor.ingest(
                [repo_name], mode=mode, persistence_mode="temporary"
            )

            # Property 1: Pipeline called with correct mode
            mock_instance.ingest_single.assert_called_once()
            call_args = mock_instance.ingest_single.call_args
            assert call_args[1]["mode"] == mode

            # Property 2: Returned summary has correct score_completeness
            assert len(summaries) == 1
            assert summaries[0].provenance.score_completeness == mode

            # Property 3: Provisional mode has missing categories, full mode doesn't
            if mode == "provisional":
                assert len(summaries[0].provenance.missing_feature_categories) > 0
            else:
                assert len(summaries[0].provenance.missing_feature_categories) == 0


@pytest.mark.property_test
@given(
    repo_name=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ).map(lambda s: f"{s[:10]}/{s[10:]}"),
    persistence_mode=st.sampled_from(["temporary", "cache", "database"]),
)
@settings(max_examples=100, deadline=None)
def test_persistence_mode_enforcement(repo_name, persistence_mode):
    """
    Property 32: Persistence Mode Enforcement (REQUIRED FOR MVP).

    Validates:
    - Temporary mode does not persist
    - Cache mode persists to cache
    - Database mode persists to database
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = str(Path(tmpdir) / "cache")
        db_path = str(Path(tmpdir) / "test.db")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        with patch(
            "src.open_source_risk_model.query.live_repo_ingestor.IngestionPipeline"
        ) as mock_pipeline:
            # Mock successful ingestion
            mock_instance = mock_pipeline.return_value
            mock_instance.ingest_single.return_value = IngestionResult(
                repo_full_name=repo_name,
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

            # First ingestion
            summaries1 = ingestor.ingest(
                [repo_name], mode="provisional", persistence_mode=persistence_mode
            )
            assert len(summaries1) == 1
            first_call_count = mock_instance.ingest_single.call_count

            # Second ingestion - check if cached
            summaries2 = ingestor.ingest(
                [repo_name], mode="provisional", persistence_mode=persistence_mode
            )
            assert len(summaries2) == 1
            second_call_count = mock_instance.ingest_single.call_count

            # Property: Persistence behavior matches mode
            if persistence_mode == "temporary":
                # Should re-ingest (no caching)
                assert second_call_count == first_call_count + 1
            else:
                # Should use cache (no re-ingestion)
                assert second_call_count == first_call_count

            # Property: Database mode persists to database
            if persistence_mode == "database":
                conn = sqlite3.connect(db_path)
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM ingestion_results WHERE repo_full_name = ?",
                    (repo_name,),
                )
                count = cursor.fetchone()[0]
                conn.close()
                assert count == 1
            else:
                # Temporary and cache modes don't persist to database
                conn = sqlite3.connect(db_path)
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='ingestion_results'"
                )
                table_exists = cursor.fetchone() is not None
                if table_exists:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM ingestion_results WHERE repo_full_name = ?",
                        (repo_name,),
                    )
                    count = cursor.fetchone()[0]
                    assert count == 0
                conn.close()


@pytest.mark.property_test
@given(
    repos=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    mode=st.sampled_from(["provisional", "full"]),
)
@settings(max_examples=100, deadline=None)
def test_batch_ingestion_mode_consistency(repos, mode):
    """
    Property 31: Batch Ingestion Mode Consistency.

    Validates:
    - All repos in batch use same mode
    - Mode is consistently applied across batch
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = str(Path(tmpdir) / "cache")
        db_path = str(Path(tmpdir) / "test.db")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        with patch(
            "src.open_source_risk_model.query.live_repo_ingestor.IngestionPipeline"
        ) as mock_pipeline:
            # Mock successful ingestions
            mock_instance = mock_pipeline.return_value

            def mock_ingest_single(repo_id, mode):
                return IngestionResult(
                    repo_full_name=repo_id,
                    success=True,
                    features={"days_since_last_push": 5.0},
                    maintenance_risk_score=0.15,
                    score_completeness=mode,
                    api_calls_made=5,
                    ingestion_time_seconds=2.5,
                    missing_feature_categories=[] if mode == "full" else ["issue_lifecycle"],
                )

            mock_instance.ingest_single.side_effect = mock_ingest_single

            ingestor = LiveRepoIngestor(
                github_token="test_token", cache_dir=cache_dir, db_path=db_path
            )

            summaries = ingestor.ingest(repos, mode=mode, persistence_mode="temporary")

            # Property: All summaries have same mode
            assert len(summaries) == len(repos)
            for summary in summaries:
                assert summary.provenance.score_completeness == mode


@pytest.mark.property_test
@given(
    repo_name=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ).map(lambda s: f"{s[:10]}/{s[10:]}"),
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_risk_band_consistency(repo_name, score):
    """
    Property: Risk Band Consistency.

    Validates:
    - Risk band matches score range
    - Risk band is deterministic
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = str(Path(tmpdir) / "cache")
        db_path = str(Path(tmpdir) / "test.db")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        with patch(
            "src.open_source_risk_model.query.live_repo_ingestor.IngestionPipeline"
        ) as mock_pipeline:
            # Mock successful ingestion
            mock_instance = mock_pipeline.return_value
            mock_instance.ingest_single.return_value = IngestionResult(
                repo_full_name=repo_name,
                success=True,
                features={"days_since_last_push": 5.0},
                maintenance_risk_score=score,
                score_completeness="provisional",
                api_calls_made=5,
                ingestion_time_seconds=2.5,
                missing_feature_categories=[],
            )

            ingestor = LiveRepoIngestor(
                github_token="test_token", cache_dir=cache_dir, db_path=db_path
            )

            summaries = ingestor.ingest(
                [repo_name], mode="provisional", persistence_mode="temporary"
            )

            assert len(summaries) == 1
            risk_band = summaries[0].risk_band

            # Property: Risk band matches score range
            if score < 0.3:
                assert risk_band == "low"
            elif score < 0.6:
                assert risk_band == "medium"
            elif score < 0.8:
                assert risk_band == "high"
            else:
                assert risk_band == "critical"


@pytest.mark.property_test
@given(
    repo_name=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ).map(lambda s: f"{s[:10]}/{s[10:]}"),
)
@settings(max_examples=100, deadline=None)
def test_failed_ingestion_returns_empty(repo_name):
    """
    Property: Failed Ingestion Handling.

    Validates:
    - Failed ingestions return empty list
    - No partial results returned
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = str(Path(tmpdir) / "cache")
        db_path = str(Path(tmpdir) / "test.db")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        with patch(
            "src.open_source_risk_model.query.live_repo_ingestor.IngestionPipeline"
        ) as mock_pipeline:
            # Mock failed ingestion
            mock_instance = mock_pipeline.return_value
            mock_instance.ingest_single.return_value = IngestionResult(
                repo_full_name=repo_name,
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
                [repo_name], mode="provisional", persistence_mode="temporary"
            )

            # Property: Failed ingestion returns empty list
            assert len(summaries) == 0
