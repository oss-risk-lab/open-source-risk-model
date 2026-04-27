"""Tests for expansion report generator."""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from hypothesis import given, strategies as st, settings

# Import the report generator
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.generate_expansion_report import (
    generate_expansion_report,
    generate_executive_summary,
    generate_newly_added_section,
    generate_failed_ingestions_section,
    generate_ecosystem_distribution_section,
    generate_query_performance_section,
    generate_insights_section,
    generate_duplicate_graphs_section,
    generate_validation_section
)


def create_test_database(db_path: str, repo_count: int = 10, dep_count: int = 50):
    """Create a minimal test database."""
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
    
    # Insert dependencies
    for i in range(dep_count):
        repo_idx = i % repo_count
        cursor.execute(
            """INSERT INTO repo_dependencies 
               (repo_full_name, package_name, registry_type, specifier, resolved_repo, resolution_confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (f"owner{repo_idx}/repo{repo_idx}", f"package-{i}", 'npm', '1.0.0', 'owner/repo', 1.0)
        )
    
    conn.commit()
    conn.close()


# Feature: dataset-expansion-200-repos, Property 30: Expansion Report Completeness
def test_report_completeness_unit():
    """
    Property 30: Expansion Report Completeness
    
    For any completed expansion, the report must contain all required sections.
    
    Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5
    """
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        # Create test database
        create_test_database(db_path, repo_count=200, dep_count=20000)
        
        # Generate report
        report_path = generate_expansion_report(
            db_path=db_path,
            repos_added=149,
            repos_failed=0,
            added_repos=[
                {'name': 'owner1/repo1', 'stars': 5000, 'ecosystem': 'npm'},
                {'name': 'owner2/repo2', 'stars': 3000, 'ecosystem': 'pypi'}
            ],
            failed_repos=[],
            performance_metrics={
                'pattern_results': {
                    'single_repo_deps': {'cold': 0.5, 'median': 0.3, 'p95': 0.4}
                },
                'max_duration': 0.5,
                'avg_duration': 0.3
            }
        )
        
        # Read report
        report_text = Path(report_path).read_text()
        
        # Verify all required sections are present
        required_sections = [
            '# Dataset Expansion Report',
            '## Executive Summary',
            '## Newly Added Repositories',
            '## Failed Ingestions',
            '## Ecosystem Distribution',
            '## Query Performance',
            '## Cross-Repository Insights',
            '## Duplicate Graph Detection',
            '## Validation Status'
        ]
        
        for section in required_sections:
            assert section in report_text, f"Missing required section: {section}"
        
        # Verify key metrics are present
        assert 'Total Repositories:' in report_text
        assert 'Total Dependencies:' in report_text
        assert 'Resolution Rate:' in report_text
        assert 'Repositories Added:' in report_text
        
        # Clean up
        Path(report_path).unlink(missing_ok=True)
    
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_report_doesnt_crash_with_minimal_data():
    """Test that report generator doesn't crash with minimal data."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        # Create minimal database
        create_test_database(db_path, repo_count=1, dep_count=1)
        
        # Generate report - should not crash
        report_path = generate_expansion_report(
            db_path=db_path,
            repos_added=0,
            repos_failed=0
        )
        
        # Verify report was created
        assert Path(report_path).exists()
        
        # Verify it has content
        report_text = Path(report_path).read_text()
        assert len(report_text) > 100
        
        # Clean up
        Path(report_path).unlink(missing_ok=True)
    
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_report_handles_failed_ingestions():
    """Test that report properly displays failed ingestions."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        create_test_database(db_path)
        
        failed_repos = [
            {'name': 'owner1/failed1', 'reason': 'Manifest not found'},
            {'name': 'owner2/failed2', 'reason': 'Rate limit exceeded'}
        ]
        
        report_path = generate_expansion_report(
            db_path=db_path,
            repos_added=8,
            repos_failed=2,
            failed_repos=failed_repos
        )
        
        report_text = Path(report_path).read_text()
        
        # Verify failed repos are listed
        assert 'owner1/failed1' in report_text
        assert 'Manifest not found' in report_text
        assert 'owner2/failed2' in report_text
        assert 'Rate limit exceeded' in report_text
        
        Path(report_path).unlink(missing_ok=True)
    
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_executive_summary_generation():
    """Test executive summary section generation."""
    summary = generate_executive_summary(
        repo_count=200,
        dependency_count=25000,
        resolution_rate=0.873,
        repos_added=149,
        repos_failed=0
    )
    
    assert '200' in summary
    assert '25,000' in summary
    assert '87.3%' in summary
    assert '149' in summary
    assert 'SUCCESS' in summary


def test_newly_added_section():
    """Test newly added repositories section."""
    added_repos = [
        {'name': 'owner1/repo1', 'stars': 5000, 'ecosystem': 'npm'},
        {'name': 'owner2/repo2', 'stars': 3000, 'ecosystem': 'pypi'},
        {'name': 'owner3/repo3', 'stars': 2000, 'ecosystem': 'npm'}
    ]
    
    section = generate_newly_added_section(added_repos)
    
    assert 'owner1/repo1' in section
    assert '5,000' in section
    assert 'NPM' in section
    assert 'PYPI' in section


def test_failed_ingestions_section():
    """Test failed ingestions section."""
    # No failures
    section = generate_failed_ingestions_section([])
    assert 'successfully' in section.lower()
    
    # With failures
    failed = [
        {'name': 'owner/repo', 'reason': 'Error message'}
    ]
    section = generate_failed_ingestions_section(failed)
    assert 'owner/repo' in section
    assert 'Error message' in section


def test_ecosystem_distribution_section():
    """Test ecosystem distribution section."""
    distribution = {
        'npm': 0.35,
        'pypi': 0.30,
        'go': 0.15,
        'maven': 0.12,
        'rubygems': 0.08
    }
    
    section = generate_ecosystem_distribution_section(distribution, 200)
    
    assert 'npm' in section
    assert '35.0%' in section
    assert '70' in section  # 35% of 200
    assert '✅' in section  # Should meet targets


def test_query_performance_section():
    """Test query performance section."""
    metrics = {
        'pattern_results': {
            'single_repo_deps': {'cold': 0.5, 'median': 0.3, 'p95': 0.4},
            'package_dependents': {'cold': 1.2, 'median': 0.8, 'p95': 1.0}
        },
        'max_duration': 1.0,
        'avg_duration': 0.55
    }
    
    section = generate_query_performance_section(metrics)
    
    assert 'single_repo_deps' in section
    assert '0.50s' in section
    assert '0.30s' in section
    assert '✅' in section  # All under 5s


def test_validation_section():
    """Test validation status section."""
    # Passed validation
    section = generate_validation_section(True, {
        'checks': [
            {'name': 'Repo Count', 'passed': True, 'message': '200 repos'},
            {'name': 'Resolution Rate', 'passed': True, 'message': '87.3%'}
        ]
    })
    
    assert 'PASSED' in section
    assert 'Repo Count' in section
    assert '✅' in section
    
    # Failed validation
    section = generate_validation_section(False, {
        'checks': [
            {'name': 'Repo Count', 'passed': False, 'message': 'Expected 200, got 195'}
        ]
    })
    
    assert 'FAILED' in section
    assert '❌' in section


@given(
    repo_count=st.integers(min_value=50, max_value=300),
    dep_count=st.integers(min_value=1000, max_value=50000)
)
@settings(max_examples=20, deadline=None)
def test_report_generation_property(repo_count, dep_count):
    """
    Property test: Report generation should work for any valid repo/dep counts.
    """
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        create_test_database(db_path, repo_count=repo_count, dep_count=dep_count)
        
        # Should not crash
        report_path = generate_expansion_report(
            db_path=db_path,
            repos_added=repo_count - 51,
            repos_failed=0
        )
        
        # Should create a file
        assert Path(report_path).exists()
        
        # Should have content
        report_text = Path(report_path).read_text()
        assert len(report_text) > 100
        
        # Should have all sections
        assert '# Dataset Expansion Report' in report_text
        assert '## Executive Summary' in report_text
        
        Path(report_path).unlink(missing_ok=True)
    
    finally:
        Path(db_path).unlink(missing_ok=True)
