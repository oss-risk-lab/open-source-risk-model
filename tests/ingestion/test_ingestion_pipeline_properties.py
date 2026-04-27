"""
Property-based tests for IngestionPipeline.

Tests universal properties that should hold across all valid inputs.
"""

import pytest
from datetime import datetime
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, MagicMock, patch

from src.open_source_risk_model.ingestion.ingestion_pipeline import IngestionPipeline
from src.open_source_risk_model.ingestion.models import (
    RepositorySnapshot,
    ContributorRecord,
    IssueRecord,
    IngestionResult,
    IngestionSummary,
)


# Strategy for generating valid repository identifiers
@st.composite
def repo_identifier_strategy(draw):
    """Generate valid repository identifiers in owner/repo format."""
    owner = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
            min_size=1,
            max_size=39,
        ).filter(lambda x: x and not x.startswith("-") and not x.endswith("-"))
    )

    repo = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_."
            ),
            min_size=1,
            max_size=100,
        ).filter(lambda x: x and not x.startswith(".") and not x.endswith("."))
    )

    return f"{owner}/{repo}"


# Feature: github-api-optimization-query-coverage, Property 18: Ingestion Pipeline Ordering
@given(repo_id=repo_identifier_strategy(), mode=st.sampled_from(["full", "provisional"]))
@settings(max_examples=100)
@pytest.mark.property_test
def test_property_18_pipeline_ordering(repo_id, mode):
    """
    Property 18: Ingestion Pipeline Ordering

    For any repository, the ingestion pipeline should execute steps in order:
    snapshot fetch → contributors fetch → issues fetch → feature engineering → persistence.

    Validates: Requirements 6.1-6.5
    """
    # Track call order
    call_order = []

    # Create mock components
    with patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.GraphQLClient"
    ) as MockGraphQL, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RESTClient"
    ) as MockREST, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RepoSnapshotFetcher"
    ) as MockSnapshot, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.ContributorsFetcher"
    ) as MockContributors, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.IssuesFetcher"
    ) as MockIssues, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.FeatureEngineer"
    ) as MockEngineer:

        # Setup mock snapshot fetcher
        mock_snapshot_instance = MockSnapshot.return_value
        mock_snapshot_instance.fetch_single.side_effect = lambda x: (
            call_order.append("snapshot"),
            RepositorySnapshot(
                repo_full_name=x,
                pushed_at=datetime(2024, 1, 1),
                latest_release=None,
                stargazer_count=100,
                is_archived=False,
                license_info="MIT",
                open_issues_count=10,
                fetched_at=datetime.utcnow(),
            ),
        )[1]

        # Setup mock contributors fetcher
        mock_contributors_instance = MockContributors.return_value
        mock_contributors_instance.fetch_contributors.side_effect = lambda x: (
            call_order.append("contributors"),
            [
                ContributorRecord(
                    login="user1",
                    contributions=100,
                    weeks=[],
                    fetched_at=datetime.utcnow(),
                )
            ],
        )[1]

        # Setup mock issues fetcher
        mock_issues_instance = MockIssues.return_value
        mock_issues_instance.fetch_issues.side_effect = lambda x: (
            call_order.append("issues"),
            [
                IssueRecord(
                    number=1,
                    state="open",
                    created_at=datetime(2024, 1, 1),
                    closed_at=None,
                    updated_at=datetime(2024, 1, 1),
                    comments=0,
                    author_association="NONE",
                    labels=[],
                    fetched_at=datetime.utcnow(),
                )
            ],
        )[1]

        # Setup mock feature engineer
        mock_engineer_instance = MockEngineer.return_value
        mock_engineer_instance.feature_weights = {
            "days_since_last_push": 0.2,
            "contributors_count": 0.2,
        }

        def mock_compute_features(*args):
            call_order.append("features")
            return {
                "days_since_last_push": 10.0,
                "contributors_count": 1.0,
            }

        def mock_compute_provisional(*args):
            call_order.append("features")
            return {
                "days_since_last_push": 10.0,
                "contributors_count": 1.0,
            }

        mock_engineer_instance.compute_features.side_effect = mock_compute_features
        mock_engineer_instance.compute_provisional_features.side_effect = (
            mock_compute_provisional
        )
        mock_engineer_instance.check_feature_coverage.return_value = (0.8, [])

        # Create pipeline
        pipeline = IngestionPipeline(github_token="test_token")

        # Ingest repository
        result = pipeline.ingest_single(repo_id, mode=mode)

        # Verify call order
        assert call_order[0] == "snapshot", "Snapshot fetch should be first"
        assert call_order[1] == "contributors", "Contributors fetch should be second"

        if mode == "full":
            assert call_order[2] == "issues", "Issues fetch should be third in full mode"
            assert (
                call_order[3] == "features"
            ), "Feature engineering should be fourth in full mode"
        else:
            # In provisional mode, issues are skipped
            assert (
                call_order[2] == "features"
            ), "Feature engineering should be third in provisional mode"
            assert "issues" not in call_order, "Issues should not be fetched in provisional mode"


# Feature: github-api-optimization-query-coverage, Property 19: Ingestion Error Isolation
@given(
    total_repos=st.integers(min_value=2, max_value=10),
    failing_indices=st.lists(
        st.integers(min_value=0, max_value=9), min_size=1, max_size=3, unique=True
    ),
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_property_19_error_isolation(total_repos, failing_indices):
    """
    Property 19: Ingestion Error Isolation

    For any list of repositories where some fail to ingest, the failures
    should not prevent successful ingestion of other repositories in the list.

    Validates: Requirements 6.6, 16.3
    """
    # Filter failing indices to be within range
    failing_indices = [i for i in failing_indices if i < total_repos]
    if not failing_indices:
        failing_indices = [0]  # Ensure at least one failure

    # Generate repo identifiers
    repo_ids = [f"owner{i}/repo{i}" for i in range(total_repos)]

    # Create mock components
    with patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.GraphQLClient"
    ), patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RESTClient"
    ), patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RepoSnapshotFetcher"
    ) as MockSnapshot, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.ContributorsFetcher"
    ) as MockContributors, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.IssuesFetcher"
    ) as MockIssues, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.FeatureEngineer"
    ) as MockEngineer:

        # Setup mock snapshot fetcher
        mock_snapshot_instance = MockSnapshot.return_value

        def mock_fetch_single(repo_id):
            idx = repo_ids.index(repo_id)
            if idx in failing_indices:
                raise Exception(f"Simulated failure for {repo_id}")

            return RepositorySnapshot(
                repo_full_name=repo_id,
                pushed_at=datetime(2024, 1, 1),
                latest_release=None,
                stargazer_count=100,
                is_archived=False,
                license_info="MIT",
                open_issues_count=10,
                fetched_at=datetime.utcnow(),
            )

        mock_snapshot_instance.fetch_single.side_effect = mock_fetch_single

        # Setup other mocks
        mock_contributors_instance = MockContributors.return_value
        mock_contributors_instance.fetch_contributors.return_value = [
            ContributorRecord(
                login="user1",
                contributions=100,
                weeks=[],
                fetched_at=datetime.utcnow(),
            )
        ]

        mock_issues_instance = MockIssues.return_value
        mock_issues_instance.fetch_issues.return_value = []

        mock_engineer_instance = MockEngineer.return_value
        mock_engineer_instance.feature_weights = {
            "days_since_last_push": 0.5,
            "contributors_count": 0.5,
        }
        mock_engineer_instance.compute_provisional_features.return_value = {
            "days_since_last_push": 10.0,
            "contributors_count": 1.0,
        }
        mock_engineer_instance.check_feature_coverage.return_value = (0.8, [])

        # Create pipeline
        pipeline = IngestionPipeline(github_token="test_token")

        # Ingest repositories
        summary = pipeline.ingest_repositories(repo_ids, mode="provisional")

        # Verify error isolation
        expected_success = total_repos - len(failing_indices)
        expected_failed = len(failing_indices)

        assert summary.successful == expected_success, (
            f"Expected {expected_success} successful ingestions, "
            f"got {summary.successful}"
        )
        assert summary.failed == expected_failed, (
            f"Expected {expected_failed} failed ingestions, " f"got {summary.failed}"
        )
        assert summary.total_repos == total_repos


# Feature: github-api-optimization-query-coverage, Property 20: Ingestion Summary Completeness
@given(
    total_repos=st.integers(min_value=1, max_value=20),
    success_rate=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_property_20_summary_completeness(total_repos, success_rate):
    """
    Property 20: Ingestion Summary Completeness

    For any ingestion operation, the returned summary should contain
    success_count, failure_count, total_api_calls, and these counts
    should sum correctly (success_count + failure_count = total_repos).

    Validates: Requirements 6.8
    """
    # Generate repo identifiers
    repo_ids = [f"owner{i}/repo{i}" for i in range(total_repos)]

    # Determine which repos should fail
    num_failures = int(total_repos * (1 - success_rate))
    failing_indices = set(range(num_failures))

    # Create mock components
    with patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.GraphQLClient"
    ), patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RESTClient"
    ), patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RepoSnapshotFetcher"
    ) as MockSnapshot, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.ContributorsFetcher"
    ) as MockContributors, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.IssuesFetcher"
    ) as MockIssues, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.FeatureEngineer"
    ) as MockEngineer:

        # Setup mock snapshot fetcher
        mock_snapshot_instance = MockSnapshot.return_value

        def mock_fetch_single(repo_id):
            idx = repo_ids.index(repo_id)
            if idx in failing_indices:
                raise Exception(f"Simulated failure for {repo_id}")

            return RepositorySnapshot(
                repo_full_name=repo_id,
                pushed_at=datetime(2024, 1, 1),
                latest_release=None,
                stargazer_count=100,
                is_archived=False,
                license_info="MIT",
                open_issues_count=10,
                fetched_at=datetime.utcnow(),
            )

        mock_snapshot_instance.fetch_single.side_effect = mock_fetch_single

        # Setup other mocks
        mock_contributors_instance = MockContributors.return_value
        mock_contributors_instance.fetch_contributors.return_value = [
            ContributorRecord(
                login="user1",
                contributions=100,
                weeks=[],
                fetched_at=datetime.utcnow(),
            )
        ]

        mock_issues_instance = MockIssues.return_value
        mock_issues_instance.fetch_issues.return_value = []

        mock_engineer_instance = MockEngineer.return_value
        mock_engineer_instance.feature_weights = {
            "days_since_last_push": 0.5,
            "contributors_count": 0.5,
        }
        mock_engineer_instance.compute_provisional_features.return_value = {
            "days_since_last_push": 10.0,
            "contributors_count": 1.0,
        }
        mock_engineer_instance.check_feature_coverage.return_value = (0.8, [])

        # Create pipeline
        pipeline = IngestionPipeline(github_token="test_token")

        # Ingest repositories
        summary = pipeline.ingest_repositories(repo_ids, mode="provisional")

        # Verify summary completeness
        assert isinstance(summary, IngestionSummary)
        assert hasattr(summary, "total_repos")
        assert hasattr(summary, "successful")
        assert hasattr(summary, "failed")
        assert hasattr(summary, "total_api_calls")
        assert hasattr(summary, "total_time_seconds")
        assert hasattr(summary, "avg_api_calls_per_repo")
        assert hasattr(summary, "avg_time_per_repo")
        assert hasattr(summary, "rate_limit_remaining")

        # Verify counts sum correctly
        assert summary.successful + summary.failed == summary.total_repos
        assert summary.total_repos == total_repos

        # Verify non-negative values
        assert summary.successful >= 0
        assert summary.failed >= 0
        assert summary.total_api_calls >= 0
        assert summary.total_time_seconds >= 0.0
        assert summary.avg_api_calls_per_repo >= 0.0
        assert summary.avg_time_per_repo >= 0.0

        # Verify rate limit remaining is a dict with expected keys
        assert isinstance(summary.rate_limit_remaining, dict)
        assert "rest" in summary.rate_limit_remaining
        assert "graphql" in summary.rate_limit_remaining


# Additional property test: Progress reporting interval
@given(
    total_repos=st.integers(min_value=10, max_value=50),
    progress_interval=st.integers(min_value=5, max_value=15),
)
@settings(max_examples=50)
@pytest.mark.property_test
def test_progress_reporting_interval(total_repos, progress_interval):
    """
    Property: Progress should be reported at configured intervals.

    For any batch ingestion, progress should be logged every N repositories
    where N is the configured progress_report_interval.
    """
    # Generate repo identifiers
    repo_ids = [f"owner{i}/repo{i}" for i in range(total_repos)]

    # Track progress reports
    progress_reports = []

    # Create mock components
    with patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.GraphQLClient"
    ), patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RESTClient"
    ), patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.RepoSnapshotFetcher"
    ) as MockSnapshot, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.ContributorsFetcher"
    ) as MockContributors, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.IssuesFetcher"
    ) as MockIssues, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.FeatureEngineer"
    ) as MockEngineer, patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.logger"
    ) as mock_logger:

        # Track progress log calls
        def track_progress(msg, *args, **kwargs):
            if "Progress:" in msg:
                progress_reports.append(msg)

        mock_logger.info.side_effect = track_progress

        # Setup mocks
        mock_snapshot_instance = MockSnapshot.return_value
        mock_snapshot_instance.fetch_single.return_value = RepositorySnapshot(
            repo_full_name="test/repo",
            pushed_at=datetime(2024, 1, 1),
            latest_release=None,
            stargazer_count=100,
            is_archived=False,
            license_info="MIT",
            open_issues_count=10,
            fetched_at=datetime.utcnow(),
        )

        mock_contributors_instance = MockContributors.return_value
        mock_contributors_instance.fetch_contributors.return_value = [
            ContributorRecord(
                login="user1",
                contributions=100,
                weeks=[],
                fetched_at=datetime.utcnow(),
            )
        ]

        mock_issues_instance = MockIssues.return_value
        mock_issues_instance.fetch_issues.return_value = []

        mock_engineer_instance = MockEngineer.return_value
        mock_engineer_instance.feature_weights = {
            "days_since_last_push": 0.5,
            "contributors_count": 0.5,
        }
        mock_engineer_instance.compute_provisional_features.return_value = {
            "days_since_last_push": 10.0,
            "contributors_count": 1.0,
        }
        mock_engineer_instance.check_feature_coverage.return_value = (0.8, [])

        # Create pipeline with custom progress interval
        pipeline = IngestionPipeline(github_token="test_token")
        pipeline.progress_interval = progress_interval

        # Ingest repositories
        pipeline.ingest_repositories(repo_ids, mode="provisional")

        # Verify progress reports
        expected_reports = total_repos // progress_interval
        assert len(progress_reports) == expected_reports, (
            f"Expected {expected_reports} progress reports, "
            f"got {len(progress_reports)}"
        )


# Additional property test: Mode validation
@given(repo_id=repo_identifier_strategy(), invalid_mode=st.text().filter(lambda x: x not in ["full", "provisional"]))
@settings(max_examples=50)
@pytest.mark.property_test
def test_mode_validation(repo_id, invalid_mode):
    """
    Property: Invalid ingestion modes should raise ValueError.

    For any mode that is not "full" or "provisional", the pipeline
    should raise a ValueError.
    """
    # Create pipeline
    with patch(
        "src.open_source_risk_model.ingestion.ingestion_pipeline.GraphQLClient"
    ), patch("src.open_source_risk_model.ingestion.ingestion_pipeline.RESTClient"):
        pipeline = IngestionPipeline(github_token="test_token")

        # Verify invalid mode raises error
        with pytest.raises(ValueError, match="Invalid mode"):
            pipeline.ingest_single(repo_id, mode=invalid_mode)

        with pytest.raises(ValueError, match="Invalid mode"):
            pipeline.ingest_repositories([repo_id], mode=invalid_mode)
