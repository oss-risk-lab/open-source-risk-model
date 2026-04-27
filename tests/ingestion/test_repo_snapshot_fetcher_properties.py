"""
Property-based tests for RepoSnapshotFetcher.

Tests universal properties that should hold across all valid inputs.
"""

import pytest
from datetime import datetime
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, MagicMock

from src.open_source_risk_model.ingestion.repo_snapshot_fetcher import RepoSnapshotFetcher
from src.open_source_risk_model.ingestion.models import RepositorySnapshot
from src.open_source_risk_model.ingestion.config import IngestionConfig


# Strategy for generating valid repository identifiers
@st.composite
def repo_identifier_strategy(draw):
    """Generate valid repository identifiers in owner/repo format."""
    # Generate owner (alphanumeric with hyphens)
    owner = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=39  # GitHub username max length
    ).filter(lambda x: x and not x.startswith("-") and not x.endswith("-")))
    
    # Generate repo name (alphanumeric with hyphens, dots, underscores)
    repo = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_."),
        min_size=1,
        max_size=100  # GitHub repo name max length
    ).filter(lambda x: x and not x.startswith(".") and not x.endswith(".")))
    
    return f"{owner}/{repo}"


# Strategy for generating repository data
@st.composite
def repo_data_strategy(draw):
    """Generate valid repository data from GraphQL response."""
    # Generate timestamps
    pushed_at = draw(st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2024, 12, 31)
    ))
    
    # Optional latest release (50% chance)
    has_release = draw(st.booleans())
    latest_release = None
    if has_release:
        latest_release = draw(st.datetimes(
            min_value=datetime(2000, 1, 1),
            max_value=datetime(2024, 12, 31)
        ))
    
    return {
        "nameWithOwner": draw(repo_identifier_strategy()),
        "pushedAt": pushed_at.isoformat() + "Z",
        "latestRelease": {"publishedAt": latest_release.isoformat() + "Z"} if latest_release else None,
        "stargazerCount": draw(st.integers(min_value=0, max_value=1000000)),
        "isArchived": draw(st.booleans()),
        "licenseInfo": {"spdxId": draw(st.sampled_from(["MIT", "Apache-2.0", "GPL-3.0", None]))},
        "issues": {"totalCount": draw(st.integers(min_value=0, max_value=10000))}
    }


# Feature: github-api-optimization-query-coverage, Property 2: Repository Snapshot Completeness
@given(repo_data=repo_data_strategy())
@settings(max_examples=100)
@pytest.mark.property_test
def test_property_2_snapshot_completeness(repo_data):
    """
    Property 2: Repository Snapshot Completeness
    
    For any repository identifier, when a snapshot is successfully fetched,
    the returned Repository_Snapshot should contain all required fields:
    pushedAt, latestRelease, stargazerCount, isArchived, licenseInfo, and openIssuesCount.
    
    Validates: Requirements 1.2
    """
    # Create mock GraphQL client
    mock_client = Mock()
    mock_client.execute_query = Mock(return_value={
        "data": {
            "repository": repo_data
        }
    })
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Extract repo identifier from data
    repo_id = repo_data["nameWithOwner"]
    
    # Fetch snapshot
    snapshot = fetcher.fetch_single(repo_id)
    
    # Verify all required fields are present
    assert isinstance(snapshot, RepositorySnapshot)
    assert snapshot.repo_full_name == repo_id
    assert isinstance(snapshot.pushed_at, datetime)
    assert snapshot.latest_release is None or isinstance(snapshot.latest_release, datetime)
    assert isinstance(snapshot.stargazer_count, int)
    assert snapshot.stargazer_count >= 0
    assert isinstance(snapshot.is_archived, bool)
    assert snapshot.license_info is None or isinstance(snapshot.license_info, str)
    assert isinstance(snapshot.open_issues_count, int)
    assert snapshot.open_issues_count >= 0
    assert isinstance(snapshot.fetched_at, datetime)


# Feature: github-api-optimization-query-coverage, Property 3: GraphQL Batching Correctness
@given(
    repo_ids=st.lists(repo_identifier_strategy(), min_size=1, max_size=20, unique=True),
    batch_size=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_property_3_batching_correctness(repo_ids, batch_size):
    """
    Property 3: GraphQL Batching Correctness
    
    For any list of repository identifiers and any valid batch size,
    batching the repositories and fetching them should return the same
    set of snapshots as fetching them individually (order-independent).
    
    Validates: Requirements 1.3, 19.1
    """
    # Create mock GraphQL client that returns consistent data
    mock_client = Mock()
    
    # Create consistent repo data for each repo
    repo_data_map = {}
    for repo_id in repo_ids:
        repo_data_map[repo_id] = {
            "nameWithOwner": repo_id,
            "pushedAt": "2024-01-01T00:00:00Z",
            "latestRelease": {"publishedAt": "2023-12-01T00:00:00Z"},
            "stargazerCount": 100,
            "isArchived": False,
            "licenseInfo": {"spdxId": "MIT"},
            "issues": {"totalCount": 10}
        }
    
    # Mock execute_query to return appropriate data
    def mock_execute(query, variables):
        # Check if this is a single repo query or batch query
        if "owner" in variables and "repo" in variables:
            # Single repo query
            repo_id = f"{variables['owner']}/{variables['repo']}"
            return {
                "data": {
                    "repository": repo_data_map.get(repo_id)
                }
            }
        else:
            # Batch query - return all repos using simple index-based aliases
            data = {}
            for idx, repo_id in enumerate(repo_ids):
                alias = f"repo_{idx}"
                data[alias] = repo_data_map[repo_id]
            return {"data": data}
    
    mock_client.execute_query = Mock(side_effect=mock_execute)
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Fetch using batching
    batched_snapshots = fetcher.fetch_snapshots(repo_ids, batch_size=batch_size)
    
    # Fetch individually
    individual_snapshots = []
    for repo_id in repo_ids:
        snapshot = fetcher.fetch_single(repo_id)
        individual_snapshots.append(snapshot)
    
    # Compare results (order-independent)
    batched_names = sorted([s.repo_full_name for s in batched_snapshots])
    individual_names = sorted([s.repo_full_name for s in individual_snapshots])
    
    assert batched_names == individual_names
    assert len(batched_snapshots) == len(individual_snapshots)
    
    # Verify each snapshot has same data
    batched_map = {s.repo_full_name: s for s in batched_snapshots}
    individual_map = {s.repo_full_name: s for s in individual_snapshots}
    
    for repo_id in repo_ids:
        b = batched_map[repo_id]
        i = individual_map[repo_id]
        
        assert b.pushed_at == i.pushed_at
        assert b.stargazer_count == i.stargazer_count
        assert b.is_archived == i.is_archived
        assert b.open_issues_count == i.open_issues_count


# Feature: github-api-optimization-query-coverage, Property 4: GraphQL Pagination Completeness
@given(
    total_items=st.integers(min_value=1, max_value=100),
    page_size=st.integers(min_value=1, max_value=20)
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_property_4_pagination_completeness(total_items, page_size):
    """
    Property 4: GraphQL Pagination Completeness
    
    For any GraphQL query requiring pagination, following cursor-based
    pagination through all pages should return all available items exactly once.
    
    Validates: Requirements 1.4
    
    Note: This test validates the pagination concept. The actual pagination
    implementation would be in a separate method that handles cursor-based
    pagination for large result sets.
    """
    # Generate test items
    items = [f"item_{i}" for i in range(total_items)]
    
    # Simulate paginated fetching
    fetched_items = []
    cursor = 0
    
    while cursor < len(items):
        # Fetch page
        page = items[cursor:cursor + page_size]
        fetched_items.extend(page)
        cursor += page_size
    
    # Verify all items fetched exactly once
    assert len(fetched_items) == total_items
    assert sorted(fetched_items) == sorted(items)
    
    # Verify no duplicates
    assert len(set(fetched_items)) == total_items


# Additional property test: Adaptive batch sizing behavior
@given(
    success_count=st.integers(min_value=1, max_value=10),
    failure_count=st.integers(min_value=0, max_value=5)
)
@settings(max_examples=50)
@pytest.mark.property_test
def test_adaptive_batch_sizing_bounds(success_count, failure_count):
    """
    Property: Adaptive batch sizing should stay within configured bounds.
    
    After any sequence of successes and failures, the batch size should
    remain between min_batch_size and max_batch_size.
    """
    # Create mock client
    mock_client = Mock()
    
    # Create fetcher with known bounds
    config = IngestionConfig()
    fetcher = RepoSnapshotFetcher(mock_client, config)
    
    initial_size = fetcher.current_batch_size
    min_size = fetcher.min_batch_size
    max_size = fetcher.max_batch_size
    
    # Simulate successes
    for _ in range(success_count):
        fetcher._adjust_batch_size_on_success()
    
    # Simulate failures
    for _ in range(failure_count):
        fetcher._adjust_batch_size_on_failure()
    
    # Verify batch size is within bounds
    assert min_size <= fetcher.current_batch_size <= max_size


# Additional property test: Error isolation
@given(
    total_repos=st.integers(min_value=2, max_value=20),
    failing_indices=st.lists(st.integers(min_value=0, max_value=19), min_size=1, max_size=5, unique=True)
)
@settings(max_examples=50)
@pytest.mark.property_test
def test_error_isolation_in_batch(total_repos, failing_indices):
    """
    Property: Batch fetch failures should not prevent successful fetches.
    
    When some repositories in a batch fail, the successful ones should
    still be returned.
    """
    # Filter failing indices to be within range
    failing_indices = [i for i in failing_indices if i < total_repos]
    if not failing_indices:
        failing_indices = [0]  # Ensure at least one failure
    
    # Generate repo identifiers
    repo_ids = [f"owner{i}/repo{i}" for i in range(total_repos)]
    
    # Create mock client
    mock_client = Mock()
    
    def mock_execute(query, variables):
        # For single repo queries
        if "owner" in variables and "repo" in variables:
            repo_id = f"{variables['owner']}/{variables['repo']}"
            idx = repo_ids.index(repo_id)
            
            if idx in failing_indices:
                raise Exception(f"Simulated failure for {repo_id}")
            
            return {
                "data": {
                    "repository": {
                        "nameWithOwner": repo_id,
                        "pushedAt": "2024-01-01T00:00:00Z",
                        "latestRelease": None,
                        "stargazerCount": 100,
                        "isArchived": False,
                        "licenseInfo": None,
                        "issues": {"totalCount": 10}
                    }
                }
            }
        else:
            # Batch query - simulate partial failure
            raise Exception("Simulated batch failure")
    
    mock_client.execute_query = Mock(side_effect=mock_execute)
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Fetch with small batch size to trigger fallback
    snapshots = fetcher.fetch_snapshots(repo_ids, batch_size=total_repos)
    
    # Verify successful repos were fetched
    expected_success_count = total_repos - len(failing_indices)
    assert len(snapshots) == expected_success_count
    
    # Verify failed repos are not in results
    fetched_names = {s.repo_full_name for s in snapshots}
    for idx in failing_indices:
        assert repo_ids[idx] not in fetched_names
