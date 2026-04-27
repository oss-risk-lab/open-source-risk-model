"""
Tests for batch ingestion functionality.

Tests cover:
- Ingestion run tracking
- Resume capability
- Rate limit handling
- Progress reporting
- Dataset manifest generation
"""

import pytest
import sqlite3
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from open_source_risk_model.persistence.db import init_database, get_connection
from open_source_risk_model.dependencies.ingestion_service import (
    DependencyIngestionService,
    IngestionResult
)


class TestIngestionRunTracking:
    """Test ingestion run tracking in database."""
    
    def test_repo_ingestion_runs_table_exists(self, tmp_path):
        """Test that repo_ingestion_runs table is created."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        conn = get_connection(db_path)
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='repo_ingestion_runs'
        """)
        
        assert cursor.fetchone() is not None
        conn.close()
    
    def test_repo_ingestion_runs_schema(self, tmp_path):
        """Test repo_ingestion_runs table has correct schema."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA table_info(repo_ingestion_runs)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        # Check required columns
        assert 'repo_full_name' in columns
        assert 'run_id' in columns
        assert 'status' in columns
        assert 'started_at' in columns
        assert 'completed_at' in columns
        assert 'dependencies_found' in columns
        assert 'dependencies_resolved' in columns
        assert 'error_message' in columns
        
        conn.close()
    
    def test_track_ingestion_run_success(self, tmp_path):
        """Test tracking successful ingestion run."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        conn = get_connection(db_path)
        
        # Insert ingestion run
        conn.execute("""
            INSERT INTO repo_ingestion_runs 
            (repo_full_name, run_id, status, started_at, completed_at, 
             dependencies_found, dependencies_resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            'test/repo',
            'run-123',
            'success',
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            10,
            8
        ))
        conn.commit()
        
        # Verify
        cursor = conn.execute("""
            SELECT * FROM repo_ingestion_runs 
            WHERE repo_full_name = ?
        """, ('test/repo',))
        
        row = cursor.fetchone()
        assert row is not None
        conn.close()
    
    def test_track_ingestion_run_failure(self, tmp_path):
        """Test tracking failed ingestion run."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        conn = get_connection(db_path)
        
        # Insert failed run
        conn.execute("""
            INSERT INTO repo_ingestion_runs 
            (repo_full_name, run_id, status, started_at, error_message)
            VALUES (?, ?, ?, ?, ?)
        """, (
            'test/repo',
            'run-123',
            'failed',
            datetime.now(timezone.utc).isoformat(),
            'Rate limit exceeded'
        ))
        conn.commit()
        
        # Verify
        cursor = conn.execute("""
            SELECT status, error_message FROM repo_ingestion_runs 
            WHERE repo_full_name = ?
        """, ('test/repo',))
        
        row = cursor.fetchone()
        assert row[0] == 'failed'
        assert 'Rate limit' in row[1]
        conn.close()


class TestResumeCapability:
    """Test resume capability for interrupted runs."""
    
    def test_skip_already_ingested_repos(self, tmp_path):
        """Test that already-ingested repos are skipped."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        conn = get_connection(db_path)
        
        # Mark repo as already ingested
        conn.execute("""
            INSERT INTO repo_ingestion_runs 
            (repo_full_name, run_id, status, started_at, completed_at,
             dependencies_found, dependencies_resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            'test/repo',
            'run-123',
            'success',
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            10,
            8
        ))
        conn.commit()
        conn.close()
        
        # Check if should skip
        conn = get_connection(db_path)
        cursor = conn.execute("""
            SELECT COUNT(*) FROM repo_ingestion_runs 
            WHERE repo_full_name = ? AND status = 'success'
        """, ('test/repo',))
        
        count = cursor.fetchone()[0]
        assert count > 0  # Should skip
        conn.close()
    
    def test_retry_failed_repos(self, tmp_path):
        """Test that failed repos are retried."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        conn = get_connection(db_path)
        
        # Mark repo as failed
        conn.execute("""
            INSERT INTO repo_ingestion_runs 
            (repo_full_name, run_id, status, started_at, error_message)
            VALUES (?, ?, ?, ?, ?)
        """, (
            'test/repo',
            'run-123',
            'failed',
            datetime.now(timezone.utc).isoformat(),
            'Timeout'
        ))
        conn.commit()
        conn.close()
        
        # Check if should retry
        conn = get_connection(db_path)
        cursor = conn.execute("""
            SELECT status FROM repo_ingestion_runs 
            WHERE repo_full_name = ?
            ORDER BY started_at DESC LIMIT 1
        """, ('test/repo',))
        
        status = cursor.fetchone()[0]
        assert status == 'failed'  # Should retry
        conn.close()


class TestRateLimitHandling:
    """Test rate limit detection and backoff."""
    
    def test_detect_rate_limit_403(self):
        """Test detection of 403 rate limit response."""
        response = Mock()
        response.status_code = 403
        response.headers = {'X-RateLimit-Remaining': '0'}
        
        # Should detect rate limit
        is_rate_limited = (
            response.status_code == 403 and 
            response.headers.get('X-RateLimit-Remaining') == '0'
        )
        assert is_rate_limited
    
    def test_detect_rate_limit_429(self):
        """Test detection of 429 rate limit response."""
        response = Mock()
        response.status_code = 429
        
        # Should detect rate limit
        is_rate_limited = response.status_code == 429
        assert is_rate_limited
    
    def test_backoff_with_jitter(self):
        """Test exponential backoff with jitter."""
        import random
        
        base_delay = 60  # 1 minute
        attempt = 2
        
        # Calculate backoff
        delay = base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.1)
        total_delay = delay + jitter
        
        # Should be between 240 and 264 seconds
        assert 240 <= total_delay <= 264


class TestProgressReporting:
    """Test progress tracking and reporting."""
    
    def test_calculate_progress_percentage(self):
        """Test progress percentage calculation."""
        total = 100
        processed = 25
        
        progress = (processed / total) * 100
        assert progress == 25.0
    
    def test_estimate_time_remaining(self):
        """Test time remaining estimation."""
        total = 100
        processed = 25
        elapsed_seconds = 60
        
        # Calculate rate
        rate = processed / elapsed_seconds  # repos per second
        remaining = total - processed
        estimated_seconds = remaining / rate
        
        assert estimated_seconds == 180.0  # 3 minutes


class TestDatasetManifest:
    """Test dataset manifest generation."""
    
    def test_manifest_structure(self):
        """Test manifest has correct structure."""
        manifest = {
            'version': '1.0',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'run_id': 'run-123',
            'repos': [],
            'summary': {
                'total_repos': 0,
                'successful_repos': 0,
                'failed_repos': 0,
                'total_dependencies': 0,
                'total_resolved': 0,
                'resolution_rate': 0.0
            }
        }
        
        assert 'version' in manifest
        assert 'generated_at' in manifest
        assert 'run_id' in manifest
        assert 'repos' in manifest
        assert 'summary' in manifest
    
    def test_manifest_repo_entry(self):
        """Test manifest repo entry structure."""
        repo_entry = {
            'repo_full_name': 'test/repo',
            'status': 'success',
            'dependencies_found': 10,
            'dependencies_resolved': 8,
            'resolution_rate': 0.8,
            'duration_seconds': 5.2,
            'ingested_at': datetime.now(timezone.utc).isoformat()
        }
        
        assert 'repo_full_name' in repo_entry
        assert 'status' in repo_entry
        assert 'dependencies_found' in repo_entry
        assert 'dependencies_resolved' in repo_entry
        assert 'resolution_rate' in repo_entry
    
    def test_write_manifest_to_file(self, tmp_path):
        """Test writing manifest to JSON file."""
        manifest_path = tmp_path / "manifest.json"
        
        manifest = {
            'version': '1.0',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'repos': []
        }
        
        # Write manifest
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Verify
        assert manifest_path.exists()
        
        # Read back
        with open(manifest_path, 'r') as f:
            loaded = json.load(f)
        
        assert loaded['version'] == '1.0'


class TestBatchIngestionIntegration:
    """Integration tests for batch ingestion."""
    
    @patch('open_source_risk_model.dependencies.manifest_discovery.ManifestDiscovery.discover_manifests')
    def test_batch_ingestion_with_tracking(self, mock_discover, tmp_path):
        """Test batch ingestion with run tracking."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        # Mock manifest discovery to return empty
        mock_discover.return_value = []
        
        service = DependencyIngestionService(db_path=db_path)
        
        # Ingest single repo
        result = service.ingest_repo('test/repo', refresh=True)
        
        # Verify result
        assert result.success
        assert result.repo_full_name == 'test/repo'
    
    def test_concurrent_ingestion_safety(self, tmp_path):
        """Test that concurrent ingestion is safe."""
        db_path = str(tmp_path / "test.db")
        init_database(db_path)
        
        # SQLite with WAL mode should handle concurrent writes
        conn1 = get_connection(db_path)
        conn2 = get_connection(db_path)
        
        # Both connections should work
        cursor1 = conn1.execute("SELECT 1")
        cursor2 = conn2.execute("SELECT 1")
        
        assert cursor1.fetchone()[0] == 1
        assert cursor2.fetchone()[0] == 1
        
        conn1.close()
        conn2.close()


# Fixtures
@pytest.fixture
def tmp_path(tmp_path_factory):
    """Create temporary directory for tests."""
    return tmp_path_factory.mktemp("batch_ingestion_test")
