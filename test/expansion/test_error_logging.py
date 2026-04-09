"""Property tests for error logging and continuation."""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, settings
from src.open_source_risk_model.cli.ingest import (
    IngestionRunTracker,
    ingest_single_repo
)
from src.open_source_risk_model.dependencies.ingestion_service import (
    DependencyIngestionService,
    IngestionResult
)
from datetime import datetime, timezone


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Create schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create repo_graphs table
    cursor.execute("""
        CREATE TABLE repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            language TEXT
        )
    """)
    
    # Create repo_ingestion_runs table
    cursor.execute("""
        CREATE TABLE repo_ingestion_runs (
            repo_full_name TEXT,
            run_id TEXT,
            status TEXT,
            started_at TEXT,
            completed_at TEXT,
            dependencies_found INTEGER,
            dependencies_resolved INTEGER,
            manifests_discovered INTEGER,
            duration_seconds REAL,
            error_message TEXT,
            PRIMARY KEY (repo_full_name, run_id)
        )
    """)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestErrorLoggingAndContinuation:
    """Property 12: Error Logging and Continuation - Feature: dataset-expansion-200-repos"""
    
    @given(
        error_message=st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs', 'Pd')))
    )
    @settings(max_examples=100, deadline=None)
    def test_error_is_logged_and_processing_continues(self, error_message):
        """
        Property 12: Error Logging and Continuation
        For any repository ingestion failure, the pipeline must log the error
        and continue processing remaining repositories.
        
        **Validates: Requirements 3.4**
        """
        # Create temp database inside test
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Create schema
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE repo_graphs (
                    repo_full_name TEXT PRIMARY KEY,
                    language TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE repo_ingestion_runs (
                    repo_full_name TEXT,
                    run_id TEXT,
                    status TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    dependencies_found INTEGER,
                    dependencies_resolved INTEGER,
                    manifests_discovered INTEGER,
                    duration_seconds REAL,
                    error_message TEXT,
                    PRIMARY KEY (repo_full_name, run_id)
                )
            """)
            
            conn.commit()
            conn.close()
            
            run_id = "test-run-123"
            tracker = IngestionRunTracker(temp_db, run_id)
            
            # Mock service that raises an error
            mock_service = Mock(spec=DependencyIngestionService)
            mock_service.ingest_repo.side_effect = Exception(error_message)
            
            # Attempt ingestion
            status, result, error = ingest_single_repo(
                repo_full_name="owner/failing-repo",
                service=mock_service,
                tracker=tracker,
                resume=False,
                sleep_on_ratelimit=False
            )
            
            # Property: Status should be 'failed'
            assert status == 'failed', f"Expected status 'failed', got '{status}'"
            
            # Property: Error should be logged in database
            conn = sqlite3.connect(temp_db)
            cursor = conn.execute("""
                SELECT status, error_message FROM repo_ingestion_runs
                WHERE repo_full_name = ? AND run_id = ?
            """, ("owner/failing-repo", run_id))
            
            row = cursor.fetchone()
            conn.close()
            
            assert row is not None, "Error not logged in database"
            assert row[0] == 'failed', f"Status not set to 'failed': {row[0]}"
            assert row[1] is not None, "Error message not logged"
            assert len(row[1]) > 0, "Error message is empty"
        
        finally:
            # Cleanup
            Path(temp_db).unlink(missing_ok=True)
    
    def test_processing_continues_after_failure(self, temp_db):
        """Test processing continues to next repo after failure."""
        run_id = "test-run-456"
        tracker = IngestionRunTracker(temp_db, run_id)
        
        # Mock service that fails for first repo, succeeds for second
        mock_service = Mock(spec=DependencyIngestionService)
        
        # First call fails
        now = datetime.now(timezone.utc)
        mock_service.ingest_repo.side_effect = [
            Exception("First repo failed"),
            IngestionResult(
                repo_full_name="owner/success-repo",
                success=True,
                dependencies_found=10,
                dependencies_resolved=8,
                manifests_discovered=1,
                started_at=now,
                completed_at=now,
                errors=[]
            )
        ]
        
        # Process first repo (fails)
        status1, result1, error1 = ingest_single_repo(
            repo_full_name="owner/failing-repo",
            service=mock_service,
            tracker=tracker,
            resume=False,
            sleep_on_ratelimit=False
        )
        
        # Property: First repo should fail
        assert status1 == 'failed'
        
        # Process second repo (succeeds)
        status2, result2, error2 = ingest_single_repo(
            repo_full_name="owner/success-repo",
            service=mock_service,
            tracker=tracker,
            resume=False,
            sleep_on_ratelimit=False
        )
        
        # Property: Second repo should succeed (processing continued)
        assert status2 == 'success', "Processing did not continue after failure"
        assert result2 is not None
        assert result2.success
    
    def test_multiple_failures_are_all_logged(self, temp_db):
        """Test multiple failures are all logged independently."""
        run_id = "test-run-789"
        tracker = IngestionRunTracker(temp_db, run_id)
        
        # Mock service that always fails
        mock_service = Mock(spec=DependencyIngestionService)
        
        failed_repos = []
        error_messages = []
        
        # Process multiple failing repos
        for i in range(5):
            repo_name = f"owner/failing-repo-{i}"
            error_msg = f"Error for repo {i}"
            
            mock_service.ingest_repo.side_effect = Exception(error_msg)
            
            status, result, error = ingest_single_repo(
                repo_full_name=repo_name,
                service=mock_service,
                tracker=tracker,
                resume=False,
                sleep_on_ratelimit=False
            )
            
            failed_repos.append(repo_name)
            error_messages.append(error_msg)
        
        # Property: All failures should be logged
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("""
            SELECT repo_full_name, error_message FROM repo_ingestion_runs
            WHERE run_id = ? AND status = 'failed'
            ORDER BY repo_full_name
        """, (run_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 5, f"Expected 5 logged failures, got {len(rows)}"
        
        # Verify all repos are logged
        logged_repos = [row[0] for row in rows]
        for repo in failed_repos:
            assert repo in logged_repos, f"Repo {repo} not logged"


class TestIngestionRunTracker:
    """Test ingestion run tracker functionality."""
    
    def test_tracker_records_failure_with_message(self, temp_db):
        """Test tracker records failure with error message."""
        run_id = "test-run-abc"
        tracker = IngestionRunTracker(temp_db, run_id)
        
        repo_name = "owner/test-repo"
        error_msg = "Test error message"
        
        # Record start
        tracker.record_start(repo_name)
        
        # Record failure
        tracker.record_failure(repo_name, error_msg)
        
        # Verify in database
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("""
            SELECT status, error_message FROM repo_ingestion_runs
            WHERE repo_full_name = ? AND run_id = ?
        """, (repo_name, run_id))
        
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == 'failed'
        assert row[1] == error_msg
    
    def test_tracker_records_success(self, temp_db):
        """Test tracker records successful ingestion."""
        run_id = "test-run-def"
        tracker = IngestionRunTracker(temp_db, run_id)
        
        repo_name = "owner/success-repo"
        
        # Record start
        tracker.record_start(repo_name)
        
        # Create success result
        now = datetime.now(timezone.utc)
        result = IngestionResult(
            repo_full_name=repo_name,
            success=True,
            dependencies_found=15,
            dependencies_resolved=12,
            manifests_discovered=2,
            started_at=now,
            completed_at=now,
            errors=[]
        )
        
        # Record success
        tracker.record_success(result)
        
        # Verify in database
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("""
            SELECT status, dependencies_found, dependencies_resolved, error_message
            FROM repo_ingestion_runs
            WHERE repo_full_name = ? AND run_id = ?
        """, (repo_name, run_id))
        
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == 'success'
        assert row[1] == 15
        assert row[2] == 12
        assert row[3] is None  # No error message for success
    
    def test_tracker_handles_multiple_runs(self, temp_db):
        """Test tracker handles multiple runs for same repo."""
        repo_name = "owner/multi-run-repo"
        
        # First run - failure
        run_id_1 = "run-1"
        tracker_1 = IngestionRunTracker(temp_db, run_id_1)
        tracker_1.record_start(repo_name)
        tracker_1.record_failure(repo_name, "First attempt failed")
        
        # Second run - success
        run_id_2 = "run-2"
        tracker_2 = IngestionRunTracker(temp_db, run_id_2)
        tracker_2.record_start(repo_name)
        
        now = datetime.now(timezone.utc)
        result = IngestionResult(
            repo_full_name=repo_name,
            success=True,
            dependencies_found=5,
            dependencies_resolved=5,
            manifests_discovered=1,
            started_at=now,
            completed_at=now,
            errors=[]
        )
        tracker_2.record_success(result)
        
        # Verify both runs are recorded
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("""
            SELECT run_id, status FROM repo_ingestion_runs
            WHERE repo_full_name = ?
            ORDER BY run_id
        """, (repo_name,))
        
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 2
        assert rows[0][0] == "run-1"
        assert rows[0][1] == "failed"
        assert rows[1][0] == "run-2"
        assert rows[1][1] == "success"


class TestResumeCapability:
    """Test resume capability (skip already-ingested repos)."""
    
    def test_resume_skips_already_ingested_repos(self, temp_db):
        """Test resume skips repos that were already successfully ingested."""
        run_id = "test-run-resume"
        tracker = IngestionRunTracker(temp_db, run_id)
        
        repo_name = "owner/already-ingested"
        
        # First ingestion - success
        mock_service = Mock(spec=DependencyIngestionService)
        now = datetime.now(timezone.utc)
        result = IngestionResult(
            repo_full_name=repo_name,
            success=True,
            dependencies_found=10,
            dependencies_resolved=8,
            manifests_discovered=1,
            started_at=now,
            completed_at=now,
            errors=[]
        )
        mock_service.ingest_repo.return_value = result
        
        status1, result1, error1 = ingest_single_repo(
            repo_full_name=repo_name,
            service=mock_service,
            tracker=tracker,
            resume=False,
            sleep_on_ratelimit=False
        )
        
        assert status1 == 'success'
        
        # Second ingestion with resume=True - should skip
        status2, result2, error2 = ingest_single_repo(
            repo_full_name=repo_name,
            service=mock_service,
            tracker=tracker,
            resume=True,  # Resume enabled
            sleep_on_ratelimit=False
        )
        
        # Property: Should be skipped
        assert status2 == 'skipped', "Already-ingested repo not skipped with resume=True"
        
        # Property: Service should not be called again
        assert mock_service.ingest_repo.call_count == 1, "Service called again for already-ingested repo"
    
    def test_resume_does_not_skip_failed_repos(self, temp_db):
        """Test resume does not skip repos that previously failed."""
        run_id = "test-run-retry"
        tracker = IngestionRunTracker(temp_db, run_id)
        
        repo_name = "owner/previously-failed"
        
        # First ingestion - failure
        tracker.record_start(repo_name)
        tracker.record_failure(repo_name, "First attempt failed")
        
        # Second ingestion with resume=True - should retry
        mock_service = Mock(spec=DependencyIngestionService)
        now = datetime.now(timezone.utc)
        result = IngestionResult(
            repo_full_name=repo_name,
            success=True,
            dependencies_found=5,
            dependencies_resolved=5,
            manifests_discovered=1,
            started_at=now,
            completed_at=now,
            errors=[]
        )
        mock_service.ingest_repo.return_value = result
        
        status, result_obj, error = ingest_single_repo(
            repo_full_name=repo_name,
            service=mock_service,
            tracker=tracker,
            resume=True,  # Resume enabled
            sleep_on_ratelimit=False
        )
        
        # Property: Should not be skipped (failed repos are retried)
        assert status == 'success', "Failed repo was skipped instead of retried"
        
        # Property: Service should be called
        assert mock_service.ingest_repo.call_count == 1, "Service not called for previously-failed repo"
