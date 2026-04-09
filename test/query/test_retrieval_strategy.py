"""
Unit tests for retrieval strategy selector.

Tests specific scenarios and edge cases for retrieval strategy selection.
"""

from datetime import datetime

import pytest

from src.open_source_risk_model.query.models import CoverageReport, RepoStatus
from src.open_source_risk_model.query.retrieval_strategy import RetrievalStrategy


def test_database_only_mode():
    """Test strategy selection for database-only coverage."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="database_only",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            ),
            RepoStatus(
                repo_full_name="pandas-dev/pandas",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=[],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.use_database is True
    assert plan.use_live_ingestion is False
    assert len(plan.repos_from_database) == 2
    assert len(plan.repos_for_ingestion) == 0
    assert plan.cost_classification == "low"
    assert plan.evidence_scope.includes_database_results is True
    assert plan.evidence_scope.includes_live_fetch is False


def test_live_ingestion_required_mode():
    """Test strategy selection for live ingestion required."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo1", "missing/repo2"],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.use_database is False
    assert plan.use_live_ingestion is True
    assert len(plan.repos_from_database) == 0
    assert len(plan.repos_for_ingestion) == 2
    assert plan.live_ingestion_mode == "provisional"  # Default
    assert plan.cost_classification == "medium"
    assert plan.evidence_scope.includes_database_results is False
    assert plan.evidence_scope.includes_live_fetch is True


def test_hybrid_mode():
    """Test strategy selection for hybrid coverage."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="hybrid",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.use_database is True
    assert plan.use_live_ingestion is True
    assert len(plan.repos_from_database) == 1
    assert len(plan.repos_for_ingestion) == 1
    assert plan.live_ingestion_mode == "provisional"  # Default
    assert plan.cost_classification == "medium"
    assert plan.evidence_scope.includes_database_results is True
    assert plan.evidence_scope.includes_live_fetch is True
    assert plan.evidence_scope.source_level == "hybrid"


def test_provisional_score_preference():
    """Test that provisional score preference is respected."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "provisional"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.live_ingestion_mode == "provisional"
    assert plan.cost_classification == "medium"


def test_full_score_preference():
    """Test that full score preference is respected."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "full"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.live_ingestion_mode == "full"
    assert plan.cost_classification == "high"


def test_cost_classification_database_only():
    """Test cost classification for database-only mode."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="database_only",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=[],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.cost_classification == "low"


def test_cost_classification_hybrid_provisional():
    """Test cost classification for hybrid mode with provisional scores."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="hybrid",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "provisional"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.cost_classification == "medium"


def test_cost_classification_hybrid_full():
    """Test cost classification for hybrid mode with full scores."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="hybrid",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "full"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.cost_classification == "high"


def test_cost_classification_live_ingestion_provisional():
    """Test cost classification for live ingestion with provisional scores."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "provisional"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.cost_classification == "medium"


def test_cost_classification_live_ingestion_full():
    """Test cost classification for live ingestion with full scores."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "full"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.cost_classification == "high"


def test_evidence_scope_database_only():
    """Test evidence scope for database-only retrieval."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="database_only",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=[],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.evidence_scope.source_level == "scored_features"
    assert plan.evidence_scope.includes_database_results is True
    assert plan.evidence_scope.includes_live_fetch is False
    assert plan.evidence_scope.includes_cached_results is False


def test_evidence_scope_live_provisional():
    """Test evidence scope for live ingestion with provisional mode."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "provisional"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.evidence_scope.source_level == "raw_ingestion"
    assert plan.evidence_scope.includes_database_results is False
    assert plan.evidence_scope.includes_live_fetch is True
    assert plan.evidence_scope.includes_cached_results is False


def test_evidence_scope_live_full():
    """Test evidence scope for live ingestion with full mode."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "full"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.evidence_scope.source_level == "scored_features"
    assert plan.evidence_scope.includes_database_results is False
    assert plan.evidence_scope.includes_live_fetch is True
    assert plan.evidence_scope.includes_cached_results is False


def test_evidence_scope_hybrid():
    """Test evidence scope for hybrid retrieval."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="hybrid",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.evidence_scope.source_level == "hybrid"
    assert plan.evidence_scope.includes_database_results is True
    assert plan.evidence_scope.includes_live_fetch is True
    assert plan.evidence_scope.includes_cached_results is False


def test_empty_preferences():
    """Test that empty preferences use defaults."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify - should default to provisional
    assert plan.live_ingestion_mode == "provisional"


def test_invalid_score_mode_defaults_to_provisional():
    """Test that invalid score mode defaults to provisional."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo"],
        invalid=[]
    )
    preferences = {"score_mode": "invalid_mode"}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify - should default to provisional
    assert plan.live_ingestion_mode == "provisional"


def test_repos_from_database_extraction():
    """Test that repos_from_database correctly extracts repo names."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="database_only",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            ),
            RepoStatus(
                repo_full_name="pandas-dev/pandas",
                last_updated=datetime.now(),
                score_completeness="full"
            ),
            RepoStatus(
                repo_full_name="django/django",
                last_updated=datetime.now(),
                score_completeness="provisional"
            )
        ],
        missing=[],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert len(plan.repos_from_database) == 3
    assert "numpy/numpy" in plan.repos_from_database
    assert "pandas-dev/pandas" in plan.repos_from_database
    assert "django/django" in plan.repos_from_database


def test_repos_for_ingestion_extraction():
    """Test that repos_for_ingestion correctly extracts missing repos."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="live_ingestion_required",
        in_database=[],
        missing=["missing/repo1", "missing/repo2", "missing/repo3"],
        invalid=[]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert len(plan.repos_for_ingestion) == 3
    assert "missing/repo1" in plan.repos_for_ingestion
    assert "missing/repo2" in plan.repos_for_ingestion
    assert "missing/repo3" in plan.repos_for_ingestion


def test_invalid_repos_not_included():
    """Test that invalid repos are not included in retrieval plan."""
    # Setup
    strategy = RetrievalStrategy()
    coverage = CoverageReport(
        coverage_mode="hybrid",
        in_database=[
            RepoStatus(
                repo_full_name="numpy/numpy",
                last_updated=datetime.now(),
                score_completeness="full"
            )
        ],
        missing=["missing/repo"],
        invalid=["invalid-format", "another/invalid/format"]
    )
    preferences = {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify - invalid repos should not appear in either list
    assert len(plan.repos_from_database) == 1
    assert len(plan.repos_for_ingestion) == 1
    assert "invalid-format" not in plan.repos_from_database
    assert "invalid-format" not in plan.repos_for_ingestion
    assert "another/invalid/format" not in plan.repos_from_database
    assert "another/invalid/format" not in plan.repos_for_ingestion
