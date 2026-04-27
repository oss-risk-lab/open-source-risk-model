"""
Property-based tests for retrieval strategy selector.

These tests validate universal properties that should hold across all valid inputs.
Each test runs 100 iterations with randomized inputs.
"""

from datetime import datetime

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.query.models import CoverageReport, RepoStatus
from src.open_source_risk_model.query.retrieval_strategy import RetrievalStrategy


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


# Strategy for generating RepoStatus objects
@st.composite
def repo_status(draw):
    """Generate RepoStatus object."""
    repo_name = draw(valid_repo_identifier())
    score_completeness = draw(st.sampled_from(["full", "provisional"]))
    return RepoStatus(
        repo_full_name=repo_name,
        last_updated=datetime.now(),
        score_completeness=score_completeness
    )


# Strategy for generating CoverageReport objects
@st.composite
def coverage_report(draw):
    """Generate CoverageReport object."""
    # Generate lists of repos
    in_database = draw(st.lists(repo_status(), min_size=0, max_size=10))
    missing = draw(st.lists(valid_repo_identifier(), min_size=0, max_size=10))
    invalid = draw(st.lists(st.text(min_size=0, max_size=20), min_size=0, max_size=5))
    
    # Determine coverage mode based on what we have
    has_database = len(in_database) > 0
    has_missing = len(missing) > 0
    
    if has_database and not has_missing:
        coverage_mode = "database_only"
    elif has_missing and not has_database:
        coverage_mode = "live_ingestion_required"
    elif has_database and has_missing:
        coverage_mode = "hybrid"
    else:
        # No valid repos (all invalid or empty)
        coverage_mode = "live_ingestion_required"
    
    return CoverageReport(
        coverage_mode=coverage_mode,
        in_database=in_database,
        missing=missing,
        invalid=invalid
    )


# Feature: github-api-optimization-query-coverage, Property 27: Retrieval Strategy Consistency
@given(
    coverage=coverage_report(),
    score_mode=st.sampled_from(["provisional", "full", None])
)
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_retrieval_strategy_consistency(coverage, score_mode):
    """
    Property 27: Retrieval Strategy Consistency
    
    For any coverage_mode, the selected retrieval strategy should match:
    - database_only → DB_Retriever only (use_database=True, use_live_ingestion=False)
    - live_ingestion_required → Live_Repo_Ingestor only (use_database=False, use_live_ingestion=True)
    - hybrid → both (use_database=True, use_live_ingestion=True)
    
    Validates: Requirements 9.1, 9.2, 9.3
    """
    # Setup
    strategy = RetrievalStrategy()
    preferences = {"score_mode": score_mode} if score_mode else {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify strategy consistency
    if coverage.coverage_mode == "database_only":
        assert plan.use_database is True, \
            "database_only mode must use database"
        assert plan.use_live_ingestion is False, \
            "database_only mode must not use live ingestion"
        assert len(plan.repos_from_database) > 0, \
            "database_only mode must have repos from database"
        assert len(plan.repos_for_ingestion) == 0, \
            "database_only mode must not have repos for ingestion"
    
    elif coverage.coverage_mode == "live_ingestion_required":
        assert plan.use_database is False, \
            "live_ingestion_required mode must not use database"
        assert plan.use_live_ingestion is True, \
            "live_ingestion_required mode must use live ingestion"
        assert len(plan.repos_from_database) == 0, \
            "live_ingestion_required mode must not have repos from database"
        # Note: repos_for_ingestion can be 0 if all repos are invalid
    
    elif coverage.coverage_mode == "hybrid":
        assert plan.use_database is True, \
            "hybrid mode must use database"
        assert plan.use_live_ingestion is True, \
            "hybrid mode must use live ingestion"
        assert len(plan.repos_from_database) > 0, \
            "hybrid mode must have repos from database"
        assert len(plan.repos_for_ingestion) > 0, \
            "hybrid mode must have repos for ingestion"
    
    # Verify repos_from_database matches in_database
    expected_db_repos = {status.repo_full_name for status in coverage.in_database}
    actual_db_repos = set(plan.repos_from_database)
    assert actual_db_repos == expected_db_repos, \
        "repos_from_database must match in_database repos"
    
    # Verify repos_for_ingestion matches missing
    expected_missing_repos = set(coverage.missing)
    actual_missing_repos = set(plan.repos_for_ingestion)
    assert actual_missing_repos == expected_missing_repos, \
        "repos_for_ingestion must match missing repos"
    
    # Verify invalid repos are not included
    for invalid_repo in coverage.invalid:
        assert invalid_repo not in plan.repos_from_database, \
            "Invalid repos must not be in repos_from_database"
        assert invalid_repo not in plan.repos_for_ingestion, \
            "Invalid repos must not be in repos_for_ingestion"


# Feature: github-api-optimization-query-coverage, Property 28: Score Mode Propagation
@given(
    coverage=coverage_report(),
    score_mode=st.sampled_from(["provisional", "full"])
)
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_score_mode_propagation(coverage, score_mode):
    """
    Property 28: Score Mode Propagation
    
    For any user preference for provisional or full scores, the Live_Repo_Ingestor
    should be configured with the matching mode.
    
    Validates: Requirements 9.4, 9.5
    """
    # Setup
    strategy = RetrievalStrategy()
    preferences = {"score_mode": score_mode}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify score mode propagation
    if score_mode == "provisional":
        assert plan.live_ingestion_mode == "provisional", \
            "provisional score_mode must result in provisional live_ingestion_mode"
    elif score_mode == "full":
        assert plan.live_ingestion_mode == "full", \
            "full score_mode must result in full live_ingestion_mode"
    
    # Verify cost classification matches mode
    if plan.use_live_ingestion:
        if plan.live_ingestion_mode == "full":
            assert plan.cost_classification == "high", \
                "full mode with live ingestion must have high cost"
        elif plan.live_ingestion_mode == "provisional":
            if coverage.coverage_mode == "database_only":
                assert plan.cost_classification == "low", \
                    "database_only must have low cost"
            else:
                assert plan.cost_classification == "medium", \
                    "provisional mode with live ingestion must have medium cost"
    else:
        # Database only
        assert plan.cost_classification == "low", \
            "database-only must have low cost"


# Additional property: Cost classification is always valid
@given(coverage=coverage_report(), score_mode=st.sampled_from(["provisional", "full", None]))
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_cost_classification_validity(coverage, score_mode):
    """
    Property: Cost Classification Validity
    
    For any coverage and score mode, the cost classification should always be
    one of: "low", "medium", or "high".
    """
    # Setup
    strategy = RetrievalStrategy()
    preferences = {"score_mode": score_mode} if score_mode else {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.cost_classification in ["low", "medium", "high"], \
        f"cost_classification must be low, medium, or high, got {plan.cost_classification}"


# Additional property: Evidence scope is always complete
@given(coverage=coverage_report(), score_mode=st.sampled_from(["provisional", "full", None]))
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_evidence_scope_completeness(coverage, score_mode):
    """
    Property: Evidence Scope Completeness
    
    For any coverage and score mode, the evidence scope should always have
    all required fields set correctly.
    """
    # Setup
    strategy = RetrievalStrategy()
    preferences = {"score_mode": score_mode} if score_mode else {}
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify evidence scope fields
    assert plan.evidence_scope.source_level in ["scored_features", "raw_ingestion", "hybrid"], \
        f"source_level must be valid, got {plan.evidence_scope.source_level}"
    
    assert isinstance(plan.evidence_scope.includes_live_fetch, bool), \
        "includes_live_fetch must be boolean"
    
    assert isinstance(plan.evidence_scope.includes_cached_results, bool), \
        "includes_cached_results must be boolean"
    
    assert isinstance(plan.evidence_scope.includes_database_results, bool), \
        "includes_database_results must be boolean"
    
    # Verify consistency with retrieval plan
    assert plan.evidence_scope.includes_database_results == plan.use_database, \
        "includes_database_results must match use_database"
    
    assert plan.evidence_scope.includes_live_fetch == plan.use_live_ingestion, \
        "includes_live_fetch must match use_live_ingestion"


# Additional property: Default score mode is provisional
@given(coverage=coverage_report())
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_default_score_mode_is_provisional(coverage):
    """
    Property: Default Score Mode
    
    When no score_mode preference is provided, the system should default to
    provisional mode (fast).
    """
    # Setup
    strategy = RetrievalStrategy()
    preferences = {}  # No score_mode specified
    
    # Execute
    plan = strategy.select_strategy(coverage, preferences)
    
    # Verify
    assert plan.live_ingestion_mode == "provisional", \
        "Default live_ingestion_mode must be provisional when no preference specified"


# Additional property: Retrieval plan is deterministic
@given(coverage=coverage_report(), score_mode=st.sampled_from(["provisional", "full", None]))
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_retrieval_plan_determinism(coverage, score_mode):
    """
    Property: Retrieval Plan Determinism
    
    For the same coverage and preferences, select_strategy should always
    return the same plan.
    """
    # Setup
    strategy = RetrievalStrategy()
    preferences = {"score_mode": score_mode} if score_mode else {}
    
    # Execute twice
    plan1 = strategy.select_strategy(coverage, preferences)
    plan2 = strategy.select_strategy(coverage, preferences)
    
    # Verify all fields match
    assert plan1.use_database == plan2.use_database
    assert plan1.use_live_ingestion == plan2.use_live_ingestion
    assert plan1.live_ingestion_mode == plan2.live_ingestion_mode
    assert plan1.repos_from_database == plan2.repos_from_database
    assert plan1.repos_for_ingestion == plan2.repos_for_ingestion
    assert plan1.cost_classification == plan2.cost_classification
    assert plan1.evidence_scope.source_level == plan2.evidence_scope.source_level
    assert plan1.evidence_scope.includes_live_fetch == plan2.evidence_scope.includes_live_fetch
    assert plan1.evidence_scope.includes_cached_results == plan2.evidence_scope.includes_cached_results
    assert plan1.evidence_scope.includes_database_results == plan2.evidence_scope.includes_database_results
