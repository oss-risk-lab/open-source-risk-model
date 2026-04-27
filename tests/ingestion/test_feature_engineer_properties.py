"""
Property-based tests for FeatureEngineer.

Tests Properties 16, 17, and 35 from the design document.
"""

from datetime import datetime, timedelta, timezone

import hypothesis
import pytest
from hypothesis import given, settings, strategies as st, Phase

from src.open_source_risk_model.ingestion.feature_engineer import FeatureEngineer
from src.open_source_risk_model.ingestion.models import (
    ContributorRecord,
    IssueRecord,
    RepositorySnapshot,
    WeeklyActivity,
)


# Strategies for generating test data
@st.composite
def repository_snapshot_strategy(draw):
    """Generate valid RepositorySnapshot instances."""
    now = datetime.now(timezone.utc)
    days_ago = draw(st.integers(min_value=0, max_value=730))
    
    # Generate owner/repo format
    owner = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_")))
    repo = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_")))
    repo_full_name = f"{owner}/{repo}"
    
    return RepositorySnapshot(
        repo_full_name=repo_full_name,
        pushed_at=now - timedelta(days=days_ago),
        latest_release=draw(
            st.one_of(
                st.none(),
                st.just(now - timedelta(days=draw(st.integers(min_value=0, max_value=730)))),
            )
        ),
        stargazer_count=draw(st.integers(min_value=0, max_value=200000)),
        is_archived=draw(st.booleans()),
        license_info=draw(st.one_of(st.none(), st.sampled_from(["MIT", "Apache-2.0", "GPL-3.0"]))),
        open_issues_count=draw(st.integers(min_value=0, max_value=20000)),
        fetched_at=now,
    )


@st.composite
def weekly_activity_strategy(draw):
    """Generate valid WeeklyActivity instances."""
    now = datetime.now(timezone.utc)
    weeks_ago = draw(st.integers(min_value=0, max_value=104))  # Up to 2 years
    
    return WeeklyActivity(
        week_timestamp=int((now - timedelta(weeks=weeks_ago)).timestamp()),
        additions=draw(st.integers(min_value=0, max_value=10000)),
        deletions=draw(st.integers(min_value=0, max_value=10000)),
        commits=draw(st.integers(min_value=0, max_value=100)),
    )


@st.composite
def contributor_record_strategy(draw):
    """Generate valid ContributorRecord instances."""
    now = datetime.now(timezone.utc)
    num_weeks = draw(st.integers(min_value=0, max_value=52))
    
    # Generate username
    login = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_")))
    
    return ContributorRecord(
        login=login,
        contributions=draw(st.integers(min_value=0, max_value=10000)),
        weeks=[draw(weekly_activity_strategy()) for _ in range(num_weeks)],
        fetched_at=now,
    )


@st.composite
def issue_record_strategy(draw):
    """Generate valid IssueRecord instances."""
    now = datetime.now(timezone.utc)
    days_ago = draw(st.integers(min_value=0, max_value=730))
    created_at = now - timedelta(days=days_ago)
    
    state = draw(st.sampled_from(["open", "closed"]))
    closed_at = None
    if state == "closed":
        days_to_close = draw(st.integers(min_value=0, max_value=min(days_ago, 365)))
        closed_at = created_at + timedelta(days=days_to_close)
    
    # Updated_at is between created_at and now
    days_since_update = draw(st.integers(min_value=0, max_value=days_ago))
    updated_at = now - timedelta(days=days_since_update)
    
    return IssueRecord(
        number=draw(st.integers(min_value=1, max_value=100000)),
        state=state,
        created_at=created_at,
        closed_at=closed_at,
        updated_at=updated_at,
        comments=draw(st.integers(min_value=0, max_value=100)),
        author_association=draw(
            st.sampled_from(["OWNER", "MEMBER", "CONTRIBUTOR", "NONE"])
        ),
        labels=draw(st.lists(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))), max_size=10)),
        fetched_at=now,
    )


# Feature: github-api-optimization-query-coverage, Property 16: Feature Computation Determinism
@given(
    snapshot=repository_snapshot_strategy(),
    contributors=st.lists(contributor_record_strategy(), min_size=0, max_size=20),
    issues=st.lists(issue_record_strategy(), min_size=0, max_size=50),
)
@settings(max_examples=100, deadline=None, phases=[Phase.generate, Phase.target])
@pytest.mark.property_test
def test_feature_computation_determinism(snapshot, contributors, issues):
    """
    For any set of raw data (snapshot, contributors, issues), computing features
    twice should produce identical results.
    
    Validates: Requirements 5.1-5.10
    """
    engineer = FeatureEngineer()
    
    # Compute features twice
    features1 = engineer.compute_features(snapshot, contributors, issues)
    features2 = engineer.compute_features(snapshot, contributors, issues)
    
    # Results should be identical
    assert features1.keys() == features2.keys(), "Feature keys should be identical"
    
    for key in features1:
        val1 = features1[key]
        val2 = features2[key]
        
        # Handle None values
        if val1 is None and val2 is None:
            continue
        
        assert val1 == val2, f"Feature {key} should have identical values: {val1} vs {val2}"


# Feature: github-api-optimization-query-coverage, Property 17: Feature Schema Compatibility
@given(
    snapshot=repository_snapshot_strategy(),
    contributors=st.lists(contributor_record_strategy(), min_size=0, max_size=20),
    issues=st.lists(issue_record_strategy(), min_size=0, max_size=50),
)
@settings(max_examples=100, deadline=None, phases=[Phase.generate, Phase.target])
@pytest.mark.property_test
def test_feature_schema_compatibility(snapshot, contributors, issues):
    """
    For any computed feature set, all feature names should exist in
    feature_mapping_config.py and all values should be numeric or None.
    
    Validates: Requirements 5.11, 17.1
    """
    engineer = FeatureEngineer()
    features = engineer.compute_features(snapshot, contributors, issues)
    
    # Get valid feature names from config (including features with 0 weight)
    from src.open_source_risk_model.config.feature_mapping_config import FEATURE_MAPPINGS
    valid_features = set(FEATURE_MAPPINGS.keys())
    
    # Check all feature names are valid (or are intermediate features)
    # Some features like contributors_count may not be in the final scoring but are used for computation
    intermediate_features = {"contributors_count"}  # Features used for computation but not in final scoring
    
    for feature_name in features:
        assert (
            feature_name in valid_features or feature_name in intermediate_features
        ), f"Feature {feature_name} not in feature_mapping_config.py or intermediate features"
    
    # Check all values are numeric or None
    for feature_name, value in features.items():
        if value is not None:
            assert isinstance(
                value, (int, float)
            ), f"Feature {feature_name} has non-numeric value: {value}"


# Feature: github-api-optimization-query-coverage, Property 35: Feature Coverage Threshold Enforcement
@given(
    snapshot=repository_snapshot_strategy(),
    contributors=st.lists(contributor_record_strategy(), min_size=0, max_size=20),
    # Intentionally omit issues to test partial coverage
)
@settings(max_examples=100, deadline=None, phases=[Phase.generate, Phase.target])
@pytest.mark.property_test
def test_feature_coverage_threshold_enforcement(snapshot, contributors):
    """
    For any repository where feature coverage (weighted) is below the minimum
    threshold (default 60%), the system should identify missing categories.
    
    Validates: Requirements 22.1, 22.3, 22.4
    """
    engineer = FeatureEngineer()
    
    # Compute provisional features (no issues)
    features = engineer.compute_provisional_features(snapshot, contributors)
    
    # Check coverage
    coverage, missing_categories = engineer.check_feature_coverage(features)
    
    # Coverage should be between 0 and 1
    assert 0.0 <= coverage <= 1.0, f"Coverage should be 0-1, got {coverage}"
    
    # Missing categories should be a list
    assert isinstance(missing_categories, list), "Missing categories should be a list"
    
    # If coverage is below threshold, missing categories should be identified
    threshold = 0.6
    if coverage < threshold:
        assert len(missing_categories) > 0, (
            f"Coverage {coverage} is below threshold {threshold}, "
            "but no missing categories identified"
        )
    
    # Missing categories should be valid category names
    valid_categories = {
        "snapshot_metrics",
        "contributor_metrics",
        "issue_lifecycle_metrics",
    }
    for category in missing_categories:
        assert category in valid_categories, f"Invalid category: {category}"


# Additional test: Weighted coverage calculation
@given(
    snapshot=repository_snapshot_strategy(),
    contributors=st.lists(contributor_record_strategy(), min_size=1, max_size=20),
    issues=st.lists(issue_record_strategy(), min_size=1, max_size=50),
)
@settings(max_examples=100, deadline=None, phases=[Phase.generate, Phase.target])
@pytest.mark.property_test
def test_weighted_coverage_calculation(snapshot, contributors, issues):
    """
    Test that coverage is based on WEIGHTED features, not raw count.
    
    Full features should have higher coverage than provisional features.
    """
    engineer = FeatureEngineer()
    
    # Compute full features
    full_features = engineer.compute_features(snapshot, contributors, issues)
    full_coverage, _ = engineer.check_feature_coverage(full_features)
    
    # Compute provisional features
    provisional_features = engineer.compute_provisional_features(snapshot, contributors)
    provisional_coverage, _ = engineer.check_feature_coverage(provisional_features)
    
    # Full coverage should be >= provisional coverage
    assert full_coverage >= provisional_coverage, (
        f"Full coverage {full_coverage} should be >= "
        f"provisional coverage {provisional_coverage}"
    )
    
    # Both should be valid percentages
    assert 0.0 <= full_coverage <= 1.0
    assert 0.0 <= provisional_coverage <= 1.0


# Additional test: Provisional features subset
@given(
    snapshot=repository_snapshot_strategy(),
    contributors=st.lists(contributor_record_strategy(), min_size=0, max_size=20),
    issues=st.lists(issue_record_strategy(), min_size=0, max_size=50),
)
@settings(max_examples=100, deadline=None, phases=[Phase.generate, Phase.target])
@pytest.mark.property_test
def test_provisional_features_subset(snapshot, contributors, issues):
    """
    Test that provisional features are a subset of full features.
    
    Provisional mode should not compute issue lifecycle features.
    """
    engineer = FeatureEngineer()
    
    # Compute both feature sets
    full_features = engineer.compute_features(snapshot, contributors, issues)
    provisional_features = engineer.compute_provisional_features(snapshot, contributors)
    
    # Provisional features should be a subset of full features
    for feature_name in provisional_features:
        assert feature_name in full_features, (
            f"Provisional feature {feature_name} not in full features"
        )
    
    # Issue lifecycle features should not be in provisional
    issue_features = {
        "issues_per_contributor",
        "fraction_issues_closed_12mo",
        "fraction_open_issues_stale_180d",
        "avg_time_to_first_maintainer_response_days",
        "median_time_to_close_days",
        "open_issue_age_p90_days",
    }
    
    for feature_name in issue_features:
        assert feature_name not in provisional_features, (
            f"Issue feature {feature_name} should not be in provisional features"
        )
