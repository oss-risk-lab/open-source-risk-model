"""
Property-based tests for coverage checker.

These tests validate universal properties that should hold across all valid inputs.
Each test runs 100 iterations with randomized inputs.
"""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.query.coverage_checker import CoverageChecker


# Strategy for generating valid repository identifiers
@st.composite
def valid_repo_identifier(draw):
    """Generate valid repository identifier in owner/repo format."""
    owner = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_.-'),
        min_size=1,
        max_size=39  # GitHub username max length
    ))
    repo = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_.-'),
        min_size=1,
        max_size=100  # GitHub repo name max length
    ))
    return f"{owner}/{repo}"


# Strategy for generating invalid repository identifiers
@st.composite
def invalid_repo_identifier(draw):
    """Generate invalid repository identifier."""
    # Various invalid formats
    invalid_formats = [
        st.just("no-slash"),  # Missing slash
        st.just("/no-owner"),  # Missing owner
        st.just("no-repo/"),  # Missing repo
        st.just("owner/repo/extra"),  # Too many slashes
        st.just(""),  # Empty string
        st.just("owner with spaces/repo"),  # Spaces
        st.just("owner/repo with spaces"),  # Spaces in repo
    ]
    return draw(st.one_of(invalid_formats))


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


# Feature: github-api-optimization-query-coverage, Property 24: Coverage Status Validity
@given(
    in_db_repos=st.lists(valid_repo_identifier(), min_size=0, max_size=10),
    missing_repos=st.lists(valid_repo_identifier(), min_size=0, max_size=10),
    invalid_repos=st.lists(invalid_repo_identifier(), min_size=0, max_size=5)
)
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_coverage_status_validity(in_db_repos, missing_repos, invalid_repos):
    """
    Property 24: Coverage Status Validity
    
    For any repository checked by Coverage_Checker, its status should be one of:
    in_database, missing, or invalid.
    
    Validates: Requirements 8.2
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        create_test_database(db_path, in_db_repos)
        
        # Create coverage checker
        checker = CoverageChecker(db_path=db_path)
        
        # Combine all repos
        all_repos = in_db_repos + missing_repos + invalid_repos
        
        # Check coverage
        report = checker.check_coverage(all_repos)
        
        # Verify all repos are categorized
        categorized_count = (
            len(report.in_database) +
            len(report.missing) +
            len(report.invalid)
        )
        assert categorized_count == len(all_repos), \
            "All repositories must be categorized as in_database, missing, or invalid"
        
        # Verify no duplicates across categories
        in_db_names = {status.repo_full_name for status in report.in_database}
        missing_names = set(report.missing)
        invalid_names = set(report.invalid)
        
        assert len(in_db_names & missing_names) == 0, \
            "No repository should be both in_database and missing"
        assert len(in_db_names & invalid_names) == 0, \
            "No repository should be both in_database and invalid"
        assert len(missing_names & invalid_names) == 0, \
            "No repository should be both missing and invalid"


# Feature: github-api-optimization-query-coverage, Property 25: Coverage Mode Determination
@given(
    in_db_count=st.integers(min_value=0, max_value=10),
    missing_count=st.integers(min_value=0, max_value=10)
)
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_coverage_mode_determination(in_db_count, missing_count):
    """
    Property 25: Coverage Mode Determination
    
    For any set of repositories:
    - If all are in_database then coverage_mode should be database_only
    - If all are missing then live_ingestion_required
    - If mixed then hybrid
    
    Validates: Requirements 8.3, 8.4, 8.5
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        
        # Generate unique repo identifiers
        in_db_repos = [f"owner{i}/repo{i}" for i in range(in_db_count)]
        missing_repos = [f"missing{i}/repo{i}" for i in range(missing_count)]
        
        create_test_database(db_path, in_db_repos)
        
        # Create coverage checker
        checker = CoverageChecker(db_path=db_path)
        
        # Check coverage
        all_repos = in_db_repos + missing_repos
        report = checker.check_coverage(all_repos)
        
        # Verify coverage mode logic
        has_database = in_db_count > 0
        has_missing = missing_count > 0
        
        if has_database and not has_missing:
            assert report.coverage_mode == "database_only", \
                "All repos in database should result in database_only mode"
        elif has_missing and not has_database:
            assert report.coverage_mode == "live_ingestion_required", \
                "All repos missing should result in live_ingestion_required mode"
        elif has_database and has_missing:
            assert report.coverage_mode == "hybrid", \
                "Mix of database and missing repos should result in hybrid mode"
        else:
            # No valid repos (all invalid or empty list)
            assert report.coverage_mode == "live_ingestion_required", \
                "No valid repos should result in live_ingestion_required mode"


# Feature: github-api-optimization-query-coverage, Property 26: Database Timestamp Presence
@given(
    repo_count=st.integers(min_value=1, max_value=20)
)
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_database_timestamp_presence(repo_count):
    """
    Property 26: Database Timestamp Presence
    
    For any repository found in the database, the Coverage_Checker should
    include a last_updated timestamp.
    
    Validates: Requirements 8.6
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        
        # Generate unique repo identifiers
        repos = [f"owner{i}/repo{i}" for i in range(repo_count)]
        create_test_database(db_path, repos)
        
        # Create coverage checker
        checker = CoverageChecker(db_path=db_path)
        
        # Check coverage
        report = checker.check_coverage(repos)
        
        # Verify all database repos have timestamps
        assert len(report.in_database) == repo_count, \
            "All repos should be found in database"
        
        for repo_status in report.in_database:
            assert repo_status.last_updated is not None, \
                f"Repository {repo_status.repo_full_name} must have last_updated timestamp"
            assert isinstance(repo_status.last_updated, datetime), \
                f"last_updated must be a datetime object for {repo_status.repo_full_name}"
            
            # Verify score_completeness is set
            assert repo_status.score_completeness in ["full", "provisional"], \
                f"score_completeness must be 'full' or 'provisional' for {repo_status.repo_full_name}"
