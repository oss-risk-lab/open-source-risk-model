"""
Unit tests for coverage checker.

Tests specific scenarios and edge cases for repository coverage detection.
"""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.open_source_risk_model.query.coverage_checker import CoverageChecker


def create_test_database(db_path: str, repos: list[str]):
    """
    Create a test database with specified repositories.
    
    Args:
        db_path: Path to database file
        repos: List of repository identifiers to insert
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create minimal schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            graph_json TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            data_sources TEXT NOT NULL
        )
    """)
    
    # Insert test repositories
    now = datetime.now().isoformat()
    for repo in repos:
        cursor.execute("""
            INSERT OR IGNORE INTO repo_graphs 
            (repo_full_name, graph_json, schema_version, node_count, edge_count, 
             created_at, updated_at, data_sources)
            VALUES (?, '{}', '1.0', 0, 0, ?, ?, 'test')
        """, (repo, now, now))
    
    conn.commit()
    conn.close()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        yield db_path


def test_all_repos_in_database(temp_db):
    """Test coverage when all repositories are in database."""
    # Setup
    repos = ["numpy/numpy", "pandas-dev/pandas", "django/django"]
    create_test_database(temp_db, repos)
    checker = CoverageChecker(db_path=temp_db)
    
    # Execute
    report = checker.check_coverage(repos)
    
    # Verify
    assert report.coverage_mode == "database_only"
    assert len(report.in_database) == 3
    assert len(report.missing) == 0
    assert len(report.invalid) == 0
    
    # Verify all repos have timestamps
    for status in report.in_database:
        assert status.last_updated is not None
        assert status.score_completeness == "full"


def test_all_repos_missing(temp_db):
    """Test coverage when all repositories are missing from database."""
    # Setup
    create_test_database(temp_db, [])  # Empty database
    checker = CoverageChecker(db_path=temp_db)
    repos = ["missing/repo1", "missing/repo2", "missing/repo3"]
    
    # Execute
    report = checker.check_coverage(repos)
    
    # Verify
    assert report.coverage_mode == "live_ingestion_required"
    assert len(report.in_database) == 0
    assert len(report.missing) == 3
    assert len(report.invalid) == 0


def test_mixed_coverage(temp_db):
    """Test coverage when some repos are in database and some are missing."""
    # Setup
    in_db = ["numpy/numpy", "pandas-dev/pandas"]
    missing = ["missing/repo1", "missing/repo2"]
    create_test_database(temp_db, in_db)
    checker = CoverageChecker(db_path=temp_db)
    
    # Execute
    all_repos = in_db + missing
    report = checker.check_coverage(all_repos)
    
    # Verify
    assert report.coverage_mode == "hybrid"
    assert len(report.in_database) == 2
    assert len(report.missing) == 2
    assert len(report.invalid) == 0
    
    # Verify correct categorization
    in_db_names = {status.repo_full_name for status in report.in_database}
    assert in_db_names == set(in_db)
    assert set(report.missing) == set(missing)


def test_invalid_identifiers(temp_db):
    """Test coverage with invalid repository identifiers."""
    # Setup
    create_test_database(temp_db, ["numpy/numpy"])
    checker = CoverageChecker(db_path=temp_db)
    
    # Test various invalid formats
    invalid_repos = [
        "no-slash",  # Missing slash
        "/no-owner",  # Missing owner
        "no-repo/",  # Missing repo
        "owner/repo/extra",  # Too many slashes
        "",  # Empty string
        "owner with spaces/repo",  # Spaces
        "owner/repo with spaces",  # Spaces in repo
    ]
    
    # Execute
    report = checker.check_coverage(invalid_repos)
    
    # Verify
    assert len(report.invalid) == len(invalid_repos)
    assert len(report.in_database) == 0
    assert len(report.missing) == 0


def test_mixed_with_invalid(temp_db):
    """Test coverage with mix of valid and invalid identifiers."""
    # Setup
    in_db = ["numpy/numpy"]
    missing = ["missing/repo"]
    invalid = ["no-slash", "owner/repo/extra"]
    
    create_test_database(temp_db, in_db)
    checker = CoverageChecker(db_path=temp_db)
    
    # Execute
    all_repos = in_db + missing + invalid
    report = checker.check_coverage(all_repos)
    
    # Verify
    assert report.coverage_mode == "hybrid"
    assert len(report.in_database) == 1
    assert len(report.missing) == 1
    assert len(report.invalid) == 2


def test_empty_input(temp_db):
    """Test coverage with empty repository list."""
    # Setup
    create_test_database(temp_db, ["numpy/numpy"])
    checker = CoverageChecker(db_path=temp_db)
    
    # Execute
    report = checker.check_coverage([])
    
    # Verify
    assert report.coverage_mode == "live_ingestion_required"
    assert len(report.in_database) == 0
    assert len(report.missing) == 0
    assert len(report.invalid) == 0


def test_duplicate_repos(temp_db):
    """Test coverage with duplicate repository identifiers."""
    # Setup
    repos = ["numpy/numpy"]
    create_test_database(temp_db, repos)
    checker = CoverageChecker(db_path=temp_db)
    
    # Execute with duplicates
    report = checker.check_coverage(["numpy/numpy", "numpy/numpy", "missing/repo", "missing/repo"])
    
    # Verify - duplicates should be processed (not deduplicated by checker)
    assert len(report.in_database) == 2  # Both numpy entries found
    assert len(report.missing) == 2  # Both missing entries


def test_case_sensitivity(temp_db):
    """Test that repository identifiers are case-sensitive."""
    # Setup
    create_test_database(temp_db, ["NumPy/NumPy"])
    checker = CoverageChecker(db_path=temp_db)
    
    # Execute
    report = checker.check_coverage(["numpy/numpy", "NumPy/NumPy"])
    
    # Verify - case matters
    assert len(report.in_database) == 1
    assert report.in_database[0].repo_full_name == "NumPy/NumPy"
    assert len(report.missing) == 1
    assert report.missing[0] == "numpy/numpy"


def test_special_characters_in_names(temp_db):
    """Test repositories with special characters (dots, dashes, underscores)."""
    # Setup
    repos = [
        "my-org/my-repo",
        "my.org/my.repo",
        "my_org/my_repo",
        "org-1.2/repo_3.4"
    ]
    create_test_database(temp_db, repos)
    checker = CoverageChecker(db_path=temp_db)
    
    # Execute
    report = checker.check_coverage(repos)
    
    # Verify
    assert report.coverage_mode == "database_only"
    assert len(report.in_database) == 4
    assert len(report.invalid) == 0


def test_database_connection_error():
    """Test handling of database connection errors."""
    # Setup with non-existent database path
    checker = CoverageChecker(db_path="/nonexistent/path/db.db")
    
    # Execute
    report = checker.check_coverage(["numpy/numpy"])
    
    # Verify - should treat as missing (graceful degradation)
    assert len(report.missing) == 1
    assert len(report.in_database) == 0


def test_malformed_timestamp_in_database(temp_db):
    """Test handling of malformed timestamps in database."""
    # Setup database with invalid timestamp
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            graph_json TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            data_sources TEXT NOT NULL
        )
    """)
    
    # Insert with invalid timestamp
    cursor.execute("""
        INSERT INTO repo_graphs 
        (repo_full_name, graph_json, schema_version, node_count, edge_count, 
         created_at, updated_at, data_sources)
        VALUES (?, '{}', '1.0', 0, 0, 'invalid', 'invalid', 'test')
    """, ("numpy/numpy",))
    
    conn.commit()
    conn.close()
    
    # Execute
    checker = CoverageChecker(db_path=temp_db)
    report = checker.check_coverage(["numpy/numpy"])
    
    # Verify - should still find repo with fallback timestamp
    assert len(report.in_database) == 1
    assert report.in_database[0].last_updated is not None
    assert isinstance(report.in_database[0].last_updated, datetime)
