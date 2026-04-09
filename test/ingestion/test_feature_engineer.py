"""
Unit tests for FeatureEngineer.

Tests specific examples and edge cases for feature computation.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.open_source_risk_model.ingestion.feature_engineer import FeatureEngineer
from src.open_source_risk_model.ingestion.models import (
    ContributorRecord,
    IssueRecord,
    RepositorySnapshot,
    WeeklyActivity,
)


@pytest.fixture
def engineer():
    """Create a FeatureEngineer instance."""
    return FeatureEngineer()


@pytest.fixture
def sample_snapshot():
    """Create a sample repository snapshot."""
    now = datetime.now(timezone.utc)
    return RepositorySnapshot(
        repo_full_name="test/repo",
        pushed_at=now - timedelta(days=7),
        latest_release=now - timedelta(days=30),
        stargazer_count=1000,
        is_archived=False,
        license_info="MIT",
        open_issues_count=50,
        fetched_at=now,
    )


@pytest.fixture
def sample_contributors():
    """Create sample contributor records."""
    now = datetime.now(timezone.utc)
    twelve_months_ago = now.timestamp() - (365 * 86400)
    
    return [
        ContributorRecord(
            login="contributor1",
            contributions=100,
            weeks=[
                WeeklyActivity(
                    week_timestamp=int(twelve_months_ago + (i * 7 * 86400)),
                    additions=50,
                    deletions=20,
                    commits=5,
                )
                for i in range(52)
            ],
            fetched_at=now,
        ),
        ContributorRecord(
            login="contributor2",
            contributions=50,
            weeks=[
                WeeklyActivity(
                    week_timestamp=int(twelve_months_ago + (i * 7 * 86400)),
                    additions=25,
                    deletions=10,
                    commits=2,
                )
                for i in range(52)
            ],
            fetched_at=now,
        ),
    ]


@pytest.fixture
def sample_issues():
    """Create sample issue records."""
    now = datetime.now(timezone.utc)
    
    return [
        # Recent closed issue
        IssueRecord(
            number=1,
            state="closed",
            created_at=now - timedelta(days=30),
            closed_at=now - timedelta(days=20),
            updated_at=now - timedelta(days=20),
            comments=5,
            author_association="CONTRIBUTOR",
            labels=["bug"],
            fetched_at=now,
        ),
        # Recent open issue
        IssueRecord(
            number=2,
            state="open",
            created_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=5),
            closed_at=None,
            comments=2,
            author_association="NONE",
            labels=["feature"],
            fetched_at=now,
        ),
        # Stale open issue
        IssueRecord(
            number=3,
            state="open",
            created_at=now - timedelta(days=200),
            updated_at=now - timedelta(days=190),
            closed_at=None,
            comments=0,
            author_association="NONE",
            labels=[],
            fetched_at=now,
        ),
    ]


def test_compute_snapshot_features(engineer, sample_snapshot):
    """Test snapshot feature computation."""
    features = engineer._compute_snapshot_features(sample_snapshot)
    
    assert "days_since_last_push" in features
    assert features["days_since_last_push"] >= 7.0  # At least 7 days
    
    assert "days_since_last_release" in features
    assert features["days_since_last_release"] >= 30.0  # At least 30 days
    
    assert features["stars_count"] == 1000.0
    assert features["archived"] == 0.0  # Not archived
    # open_issues_count is not in the feature weights, so it's not included


def test_compute_snapshot_features_archived(engineer):
    """Test snapshot features for archived repository."""
    now = datetime.now(timezone.utc)
    snapshot = RepositorySnapshot(
        repo_full_name="test/archived",
        pushed_at=now - timedelta(days=365),
        latest_release=None,  # No release
        stargazer_count=100,
        is_archived=True,
        license_info="MIT",
        open_issues_count=0,
        fetched_at=now,
    )
    
    features = engineer._compute_snapshot_features(snapshot)
    
    assert features["archived"] == 1.0  # Archived
    assert features["days_since_last_release"] == 730.0  # Default for no release


def test_compute_contributor_features(engineer, sample_contributors):
    """Test contributor feature computation."""
    features = engineer._compute_contributor_features(sample_contributors)
    
    assert features["contributors_count"] == 2.0
    assert features["contributors_last_12mo"] > 0.0
    assert 0.0 <= features["top_contributor_fraction_12mo"] <= 1.0


def test_compute_contributor_features_no_contributors(engineer):
    """Test contributor features with no contributors."""
    features = engineer._compute_contributor_features([])
    
    assert features["contributors_count"] == 0.0
    assert features["contributors_last_12mo"] == 0.0
    assert features["top_contributor_fraction_12mo"] == 1.0  # High risk


def test_compute_issue_features(engineer, sample_issues, sample_contributors):
    """Test issue feature computation."""
    features = engineer._compute_issue_features(sample_issues, sample_contributors)
    
    assert "issues_per_contributor" in features
    assert features["issues_per_contributor"] == 3.0 / 2.0  # 3 issues, 2 contributors
    
    assert "fraction_issues_closed_12mo" in features
    assert 0.0 <= features["fraction_issues_closed_12mo"] <= 1.0
    
    assert "fraction_open_issues_stale_180d" in features
    assert features["fraction_open_issues_stale_180d"] > 0.0  # Has stale issue
    
    assert "median_time_to_close_days" in features
    assert features["median_time_to_close_days"] > 0.0


def test_compute_issue_features_no_issues(engineer, sample_contributors):
    """Test issue features with no issues."""
    features = engineer._compute_issue_features([], sample_contributors)
    
    # All issue features should be None
    assert features["issues_per_contributor"] is None
    assert features["fraction_issues_closed_12mo"] is None
    assert features["fraction_open_issues_stale_180d"] is None
    assert features["avg_time_to_first_maintainer_response_days"] is None
    assert features["median_time_to_close_days"] is None
    assert features["open_issue_age_p90_days"] is None


def test_compute_features_full(engineer, sample_snapshot, sample_contributors, sample_issues):
    """Test full feature computation."""
    features = engineer.compute_features(sample_snapshot, sample_contributors, sample_issues)
    
    # Should have snapshot features
    assert "days_since_last_push" in features
    assert "stars_count" in features
    
    # Should have contributor features
    assert "contributors_count" in features
    assert "contributors_last_12mo" in features
    
    # Should have issue features
    assert "issues_per_contributor" in features
    assert "fraction_issues_closed_12mo" in features


def test_compute_provisional_features(engineer, sample_snapshot, sample_contributors):
    """Test provisional feature computation."""
    features = engineer.compute_provisional_features(sample_snapshot, sample_contributors)
    
    # Should have snapshot features
    assert "days_since_last_push" in features
    assert "stars_count" in features
    
    # Should have contributor features
    assert "contributors_count" in features
    assert "contributors_last_12mo" in features
    
    # Should NOT have issue features
    assert "issues_per_contributor" not in features
    assert "fraction_issues_closed_12mo" not in features


def test_check_feature_coverage_full(engineer, sample_snapshot, sample_contributors, sample_issues):
    """Test feature coverage checking with full features."""
    features = engineer.compute_features(sample_snapshot, sample_contributors, sample_issues)
    coverage, missing_categories = engineer.check_feature_coverage(features)
    
    # Full features should have high coverage
    assert coverage > 0.8  # Should be close to 100%
    
    # Should have minimal missing categories
    assert isinstance(missing_categories, list)


def test_check_feature_coverage_provisional(engineer, sample_snapshot, sample_contributors):
    """Test feature coverage checking with provisional features."""
    features = engineer.compute_provisional_features(sample_snapshot, sample_contributors)
    coverage, missing_categories = engineer.check_feature_coverage(features)
    
    # Provisional features should have lower coverage
    assert 0.0 < coverage < 1.0
    
    # Should identify missing issue lifecycle metrics
    assert "issue_lifecycle_metrics" in missing_categories


def test_check_feature_coverage_below_threshold(engineer):
    """Test feature coverage below threshold."""
    # Only provide minimal features
    features = {
        "stars_count": 100.0,
    }
    
    coverage, missing_categories = engineer.check_feature_coverage(features)
    
    # Coverage should be low
    assert coverage < 0.6  # Below default threshold
    
    # Should identify multiple missing categories
    assert len(missing_categories) > 0


def test_weighted_coverage_calculation(engineer, sample_snapshot, sample_contributors):
    """Test that coverage is weighted, not raw count."""
    # Create features with only high-weight features
    high_weight_features = {
        "days_since_last_push": 7.0,  # weight: 0.19
        "contributors_last_12mo": 5.0,  # weight: 0.12
        "fraction_issues_closed_12mo": 0.8,  # weight: 0.15
    }
    
    coverage_high, _ = engineer.check_feature_coverage(high_weight_features)
    
    # Create features with only low-weight features
    low_weight_features = {
        "stars_count": 1000.0,  # weight: 0.05
        "avg_time_to_first_maintainer_response_days": 1.0,  # weight: 0.02
        "median_time_to_close_days": 7.0,  # weight: 0.02
    }
    
    coverage_low, _ = engineer.check_feature_coverage(low_weight_features)
    
    # High-weight features should give higher coverage despite fewer features
    assert coverage_high > coverage_low


def test_identify_missing_categories(engineer):
    """Test missing category identification."""
    # All snapshot features but no contributor or issue features
    features = {
        "days_since_last_push": 7.0,
        "days_since_last_release": 30.0,
        "stars_count": 1000.0,
        "archived": 0.0,
        "open_issues_count": 50.0,
    }
    
    _, missing = engineer.check_feature_coverage(features)
    
    # Should identify missing contributor and issue categories
    assert "contributor_metrics" in missing
    assert "issue_lifecycle_metrics" in missing
    assert "snapshot_metrics" not in missing


def test_feature_computation_with_edge_cases(engineer):
    """Test feature computation with edge case data."""
    now = datetime.now(timezone.utc)
    
    # Repository with no activity
    snapshot = RepositorySnapshot(
        repo_full_name="test/inactive",
        pushed_at=now - timedelta(days=1000),  # Very old
        latest_release=None,
        stargazer_count=0,
        is_archived=True,
        license_info=None,
        open_issues_count=0,
        fetched_at=now,
    )
    
    features = engineer._compute_snapshot_features(snapshot)
    
    assert features["days_since_last_push"] >= 1000.0
    assert features["days_since_last_release"] == 730.0  # Default
    assert features["stars_count"] == 0.0
    assert features["archived"] == 1.0
