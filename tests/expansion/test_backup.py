"""Property tests for database backup creation."""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime
from pathlib import Path
from hypothesis import given, strategies as st, settings
from scripts.backup_database import backup_database


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Create schema with some data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            language TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE ingestion_jobs (
            id INTEGER PRIMARY KEY,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE repo_maintainers (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE repo_cves (
            id INTEGER PRIMARY KEY,
            cve_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE repo_registries (
            id INTEGER PRIMARY KEY,
            registry TEXT
        )
    """)
    
    # Add some test data
    cursor.execute("INSERT INTO repo_graphs VALUES ('owner/repo1', 'Python')")
    cursor.execute("INSERT INTO repo_graphs VALUES ('owner/repo2', 'JavaScript')")
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_backup_dir():
    """Create temporary backup directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestBackupCreation:
    """Property 27: Backup Creation - Feature: dataset-expansion-200-repos"""
    
    def test_backup_is_created_before_expansion(self, temp_db, temp_backup_dir):
        """
        Property 27: Backup Creation
        For any expansion start, a database backup must be created before ingestion begins.
        
        **Validates: Requirements 7.1**
        """
        # Create backup
        backup_path = backup_database(
            db_path=temp_db,
            output_dir=temp_backup_dir,
            compress=False,
            keep_days=30
        )
        
        # Property: Backup file must exist
        assert os.path.exists(backup_path), f"Backup file not created: {backup_path}"
        
        # Property: Backup must be a valid SQLite database
        try:
            conn = sqlite3.connect(backup_path)
            cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
            count = cursor.fetchone()[0]
            conn.close()
            
            assert count == 2, f"Backup has incorrect data: expected 2 repos, got {count}"
        except Exception as e:
            pytest.fail(f"Backup is not a valid SQLite database: {e}")
    
    @given(
        repo_count=st.integers(min_value=1, max_value=100)
    )
    @settings(max_examples=50, deadline=None)
    def test_backup_preserves_all_data(self, repo_count):
        """Test backup preserves all data from source database."""
        # Create temp database with data
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        # Create temp backup directory
        with tempfile.TemporaryDirectory() as temp_backup_dir:
            try:
                # Create schema and add data
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE repo_graphs (
                        repo_full_name TEXT PRIMARY KEY,
                        language TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE ingestion_jobs (
                        id INTEGER PRIMARY KEY,
                        status TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE repo_maintainers (
                        id INTEGER PRIMARY KEY,
                        name TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE repo_cves (
                        id INTEGER PRIMARY KEY,
                        cve_id TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE repo_registries (
                        id INTEGER PRIMARY KEY,
                        registry TEXT
                    )
                """)
                
                # Add repos
                for i in range(repo_count):
                    cursor.execute("INSERT INTO repo_graphs VALUES (?, ?)", (f'owner/repo{i}', 'Python'))
                
                conn.commit()
                conn.close()
                
                # Create backup
                backup_path = backup_database(
                    db_path=temp_db,
                    output_dir=temp_backup_dir,
                    compress=False,
                    keep_days=30
                )
                
                # Verify backup has same data
                backup_conn = sqlite3.connect(backup_path)
                backup_cursor = backup_conn.execute("SELECT COUNT(*) FROM repo_graphs")
                backup_count = backup_cursor.fetchone()[0]
                backup_conn.close()
                
                # Property: Backup must have same number of repos as source
                assert backup_count == repo_count, \
                    f"Backup has {backup_count} repos, expected {repo_count}"
            
            finally:
                # Cleanup
                Path(temp_db).unlink(missing_ok=True)


class TestBackupTimestampNaming:
    """Property 28: Backup Timestamp Naming - Feature: dataset-expansion-200-repos"""
    
    def test_backup_filename_contains_timestamp(self, temp_db, temp_backup_dir):
        """
        Property 28: Backup Timestamp Naming
        For any created backup, the filename must contain a timestamp identifier.
        
        **Validates: Requirements 7.2**
        """
        # Create backup
        backup_path = backup_database(
            db_path=temp_db,
            output_dir=temp_backup_dir,
            compress=False,
            keep_days=30
        )
        
        # Property: Filename must contain timestamp
        filename = os.path.basename(backup_path)
        
        # Expected format: graphs_YYYYMMDD_HHMMSS.db
        assert filename.startswith('graphs_'), f"Backup filename doesn't start with 'graphs_': {filename}"
        assert filename.endswith('.db'), f"Backup filename doesn't end with '.db': {filename}"
        
        # Extract timestamp part
        timestamp_part = filename.replace('graphs_', '').replace('.db', '')
        
        # Verify timestamp format (YYYYMMDD_HHMMSS)
        try:
            datetime.strptime(timestamp_part, '%Y%m%d_%H%M%S')
        except ValueError:
            pytest.fail(f"Backup filename doesn't contain valid timestamp: {filename}")
    
    @given(
        backup_count=st.integers(min_value=2, max_value=5)
    )
    @settings(max_examples=20, deadline=None)
    def test_multiple_backups_have_unique_timestamps(self, backup_count):
        """Test multiple backups have unique timestamp identifiers."""
        import time
        
        # Create temp database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        # Create temp backup directory
        with tempfile.TemporaryDirectory() as temp_backup_dir:
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
                    CREATE TABLE ingestion_jobs (
                        id INTEGER PRIMARY KEY,
                        status TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE repo_maintainers (
                        id INTEGER PRIMARY KEY,
                        name TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE repo_cves (
                        id INTEGER PRIMARY KEY,
                        cve_id TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE repo_registries (
                        id INTEGER PRIMARY KEY,
                        registry TEXT
                    )
                """)
                cursor.execute("INSERT INTO repo_graphs VALUES ('owner/repo1', 'Python')")
                conn.commit()
                conn.close()
                
                backup_paths = []
                
                # Create multiple backups
                for i in range(backup_count):
                    backup_path = backup_database(
                        db_path=temp_db,
                        output_dir=temp_backup_dir,
                        compress=False,
                        keep_days=30
                    )
                    backup_paths.append(backup_path)
                    
                    # Sleep briefly to ensure different timestamps
                    if i < backup_count - 1:
                        time.sleep(1.1)
                
                # Property: All backup filenames should be unique
                filenames = [os.path.basename(p) for p in backup_paths]
                unique_filenames = set(filenames)
                
                assert len(unique_filenames) == backup_count, \
                    f"Expected {backup_count} unique filenames, got {len(unique_filenames)}: {filenames}"
            
            finally:
                # Cleanup
                Path(temp_db).unlink(missing_ok=True)


class TestBackupIntegrity:
    """Test backup integrity verification."""
    
    def test_backup_integrity_is_verified(self, temp_db, temp_backup_dir):
        """Test backup integrity is verified after creation."""
        # Create backup
        backup_path = backup_database(
            db_path=temp_db,
            output_dir=temp_backup_dir,
            compress=False,
            keep_days=30
        )
        
        # Verify backup integrity manually
        conn = sqlite3.connect(backup_path)
        cursor = conn.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        conn.close()
        
        # Property: Backup must pass integrity check
        assert result == "ok", f"Backup integrity check failed: {result}"
    
    def test_backup_is_readable(self, temp_db, temp_backup_dir):
        """Test backup can be read and queried."""
        # Create backup
        backup_path = backup_database(
            db_path=temp_db,
            output_dir=temp_backup_dir,
            compress=False,
            keep_days=30
        )
        
        # Try to read from backup
        try:
            conn = sqlite3.connect(backup_path)
            
            # Query all tables
            cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
            assert cursor.fetchone()[0] == 2
            
            cursor = conn.execute("SELECT COUNT(*) FROM ingestion_jobs")
            assert cursor.fetchone()[0] == 0
            
            conn.close()
        except Exception as e:
            pytest.fail(f"Failed to read from backup: {e}")


class TestBackupDirectory:
    """Test backup directory handling."""
    
    def test_backup_creates_directory_if_not_exists(self, temp_db):
        """Test backup creates output directory if it doesn't exist."""
        # Use non-existent directory
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = os.path.join(tmpdir, 'nested', 'backup', 'dir')
            
            # Directory should not exist yet
            assert not os.path.exists(backup_dir)
            
            # Create backup
            backup_path = backup_database(
                db_path=temp_db,
                output_dir=backup_dir,
                compress=False,
                keep_days=30
            )
            
            # Property: Directory should be created
            assert os.path.exists(backup_dir), "Backup directory not created"
            
            # Property: Backup should be in the directory
            assert os.path.dirname(backup_path) == backup_dir, \
                f"Backup not in correct directory: {backup_path}"
    
    def test_backup_handles_existing_directory(self, temp_db, temp_backup_dir):
        """Test backup handles existing directory gracefully."""
        # Directory already exists (from fixture)
        assert os.path.exists(temp_backup_dir)
        
        # Create backup
        backup_path = backup_database(
            db_path=temp_db,
            output_dir=temp_backup_dir,
            compress=False,
            keep_days=30
        )
        
        # Property: Backup should be created successfully
        assert os.path.exists(backup_path), "Backup not created in existing directory"


class TestBackupErrorHandling:
    """Test backup error handling."""
    
    def test_backup_fails_on_nonexistent_database(self, temp_backup_dir):
        """Test backup fails gracefully on nonexistent database."""
        nonexistent_db = "/tmp/nonexistent_database_12345.db"
        
        # Property: Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            backup_database(
                db_path=nonexistent_db,
                output_dir=temp_backup_dir,
                compress=False,
                keep_days=30
            )
    
    def test_backup_cleans_up_on_failure(self, temp_backup_dir):
        """Test backup cleans up partial files on failure."""
        # Create invalid database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            invalid_db = f.name
            f.write(b'invalid database content')
        
        try:
            # Try to backup invalid database
            with pytest.raises(Exception):
                backup_database(
                    db_path=invalid_db,
                    output_dir=temp_backup_dir,
                    compress=False,
                    keep_days=30
                )
            
            # Property: No partial backup files should remain
            backup_files = [f for f in os.listdir(temp_backup_dir) if f.startswith('graphs_')]
            assert len(backup_files) == 0, f"Partial backup files not cleaned up: {backup_files}"
        
        finally:
            # Cleanup
            Path(invalid_db).unlink(missing_ok=True)
