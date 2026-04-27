"""Property-based tests for rollback functionality."""

import pytest
import tempfile
import sqlite3
import shutil
from pathlib import Path
from hypothesis import given, strategies as st, settings

# Import rollback function
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.expand_dataset import rollback_expansion


def create_test_database(db_path: str, repo_count: int):
    """Create a test database with specified repo count."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            created_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repo_dependencies (
            repo_full_name TEXT,
            package_name TEXT,
            registry_type TEXT,
            specifier TEXT,
            resolved_repo TEXT,
            resolution_confidence REAL
        )
    """)
    
    # Insert repos
    for i in range(repo_count):
        cursor.execute(
            "INSERT INTO repo_graphs (repo_full_name) VALUES (?)",
            (f"owner{i}/repo{i}",)
        )
    
    # Insert some dependencies
    for i in range(repo_count * 5):
        repo_idx = i % repo_count
        cursor.execute(
            """INSERT INTO repo_dependencies 
               (repo_full_name, package_name, registry_type, specifier, resolved_repo, resolution_confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (f"owner{repo_idx}/repo{repo_idx}", f"package-{i}", 'npm', '1.0.0', 'owner/repo', 1.0)
        )
    
    conn.commit()
    conn.close()


def get_database_state(db_path: str) -> dict:
    """Get database state for comparison."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get repo count
    cursor.execute("SELECT COUNT(*) FROM repo_graphs")
    repo_count = cursor.fetchone()[0]
    
    # Get dependency count
    cursor.execute("SELECT COUNT(*) FROM repo_dependencies")
    dep_count = cursor.fetchone()[0]
    
    # Get repo names
    cursor.execute("SELECT repo_full_name FROM repo_graphs ORDER BY repo_full_name")
    repos = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'repo_count': repo_count,
        'dep_count': dep_count,
        'repos': repos
    }


# Feature: dataset-expansion-200-repos, Property 29: Rollback Round-Trip
@given(
    initial_repo_count=st.integers(min_value=10, max_value=100),
    added_repo_count=st.integers(min_value=1, max_value=50)
)
@settings(max_examples=50, deadline=None)
def test_rollback_round_trip(initial_repo_count, added_repo_count):
    """
    Property 29: Rollback Round-Trip
    
    For any database state S, after backup, modification, and rollback,
    the restored state must equal S.
    
    Validates: Requirements 7.4
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create initial database state
        create_test_database(str(db_path), initial_repo_count)
        
        # Capture original state
        original_state = get_database_state(str(db_path))
        
        # Create backup
        shutil.copy(str(db_path), str(backup_path))
        
        # Modify database (add more repos)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        for i in range(initial_repo_count, initial_repo_count + added_repo_count):
            cursor.execute(
                "INSERT INTO repo_graphs (repo_full_name) VALUES (?)",
                (f"owner{i}/repo{i}",)
            )
        conn.commit()
        conn.close()
        
        # Verify modification happened
        modified_state = get_database_state(str(db_path))
        assert modified_state['repo_count'] == initial_repo_count + added_repo_count
        
        # Rollback
        success = rollback_expansion(
            backup_path=str(backup_path),
            db_path=str(db_path),
            expected_repo_count=initial_repo_count
        )
        
        assert success, "Rollback should succeed"
        
        # Verify restored state matches original
        restored_state = get_database_state(str(db_path))
        
        assert restored_state['repo_count'] == original_state['repo_count'], \
            f"Repo count mismatch: expected {original_state['repo_count']}, got {restored_state['repo_count']}"
        
        assert restored_state['dep_count'] == original_state['dep_count'], \
            f"Dependency count mismatch: expected {original_state['dep_count']}, got {restored_state['dep_count']}"
        
        assert restored_state['repos'] == original_state['repos'], \
            "Repository list mismatch after rollback"


def test_rollback_unit():
    """Unit test: Rollback with known data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create initial database with 51 repos
        create_test_database(str(db_path), 51)
        
        # Create backup
        shutil.copy(str(db_path), str(backup_path))
        
        # Add 149 more repos (expand to 200)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        for i in range(51, 200):
            cursor.execute(
                "INSERT INTO repo_graphs (repo_full_name) VALUES (?)",
                (f"owner{i}/repo{i}",)
            )
        conn.commit()
        conn.close()
        
        # Verify expansion
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
        assert cursor.fetchone()[0] == 200
        conn.close()
        
        # Rollback
        success = rollback_expansion(
            backup_path=str(backup_path),
            db_path=str(db_path),
            expected_repo_count=51
        )
        
        assert success
        
        # Verify rollback
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
        assert cursor.fetchone()[0] == 51
        conn.close()


def test_rollback_fails_with_invalid_backup():
    """Test that rollback fails gracefully with invalid backup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "nonexistent.db"
        
        create_test_database(str(db_path), 10)
        
        # Rollback with nonexistent backup should fail
        success = rollback_expansion(
            backup_path=str(backup_path),
            db_path=str(db_path),
            expected_repo_count=5
        )
        
        assert not success


def test_rollback_fails_with_wrong_repo_count():
    """Test that rollback fails if restored count doesn't match expected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create database with 51 repos
        create_test_database(str(db_path), 51)
        
        # Create backup
        shutil.copy(str(db_path), str(backup_path))
        
        # Modify database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("INSERT INTO repo_graphs (repo_full_name) VALUES (?)", ("owner/new",))
        conn.commit()
        conn.close()
        
        # Rollback with wrong expected count should fail
        success = rollback_expansion(
            backup_path=str(backup_path),
            db_path=str(db_path),
            expected_repo_count=100  # Wrong count
        )
        
        assert not success


def test_rollback_preserves_dependencies():
    """Test that rollback preserves dependency data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create initial database
        create_test_database(str(db_path), 10)
        
        # Get original dependency count
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM repo_dependencies")
        original_dep_count = cursor.fetchone()[0]
        conn.close()
        
        # Create backup
        shutil.copy(str(db_path), str(backup_path))
        
        # Add more repos and dependencies
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        for i in range(10, 20):
            cursor.execute(
                "INSERT INTO repo_graphs (repo_full_name) VALUES (?)",
                (f"owner{i}/repo{i}",)
            )
            cursor.execute(
                """INSERT INTO repo_dependencies 
                   (repo_full_name, package_name, registry_type, specifier, resolved_repo, resolution_confidence)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"owner{i}/repo{i}", f"package-{i}", 'npm', '1.0.0', 'owner/repo', 1.0)
            )
        conn.commit()
        conn.close()
        
        # Rollback
        success = rollback_expansion(
            backup_path=str(backup_path),
            db_path=str(db_path),
            expected_repo_count=10
        )
        
        assert success
        
        # Verify dependency count restored
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM repo_dependencies")
        restored_dep_count = cursor.fetchone()[0]
        conn.close()
        
        assert restored_dep_count == original_dep_count
