"""
Unit tests for RepoSnapshotFetcher.

Tests specific examples and edge cases for repository snapshot fetching.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from src.open_source_risk_model.ingestion.repo_snapshot_fetcher import RepoSnapshotFetcher
from src.open_source_risk_model.ingestion.models import RepositorySnapshot
from src.open_source_risk_model.ingestion.config import IngestionConfig


def test_fetch_single_success():
    """Test successful single repository fetch."""
    # Create mock GraphQL client
    mock_client = Mock()
    mock_client.execute_query = Mock(return_value={
        "data": {
            "repository": {
                "nameWithOwner": "facebook/react",
                "pushedAt": "2024-01-15T10:30:00Z",
                "latestRelease": {
                    "publishedAt": "2024-01-01T00:00:00Z"
                },
                "stargazerCount": 50000,
                "isArchived": False,
                "licenseInfo": {
                    "spdxId": "MIT"
                },
                "issues": {
                    "totalCount": 100
                }
            }
        }
    })
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Fetch snapshot
    snapshot = fetcher.fetch_single("facebook/react")
    
    # Verify result
    assert isinstance(snapshot, RepositorySnapshot)
    assert snapshot.repo_full_name == "facebook/react"
    assert snapshot.stargazer_count == 50000
    assert snapshot.is_archived is False
    assert snapshot.license_info == "MIT"
    assert snapshot.open_issues_count == 100
    assert isinstance(snapshot.pushed_at, datetime)
    assert isinstance(snapshot.latest_release, datetime)


def test_fetch_single_no_release():
    """Test single repository fetch with no release."""
    # Create mock GraphQL client
    mock_client = Mock()
    mock_client.execute_query = Mock(return_value={
        "data": {
            "repository": {
                "nameWithOwner": "owner/repo",
                "pushedAt": "2024-01-15T10:30:00Z",
                "latestRelease": None,
                "stargazerCount": 10,
                "isArchived": False,
                "licenseInfo": None,
                "issues": {
                    "totalCount": 5
                }
            }
        }
    })
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Fetch snapshot
    snapshot = fetcher.fetch_single("owner/repo")
    
    # Verify result
    assert snapshot.repo_full_name == "owner/repo"
    assert snapshot.latest_release is None
    assert snapshot.license_info is None


def test_fetch_single_invalid_identifier():
    """Test single repository fetch with invalid identifier."""
    mock_client = Mock()
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Should raise ValueError for invalid format
    with pytest.raises(ValueError, match="Invalid repository identifier"):
        fetcher.fetch_single("invalid-format")


def test_fetch_single_not_found():
    """Test single repository fetch when repository not found."""
    # Create mock GraphQL client that returns no data
    mock_client = Mock()
    mock_client.execute_query = Mock(return_value={
        "data": {
            "repository": None
        }
    })
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Should raise exception
    with pytest.raises(Exception, match="Repository not found"):
        fetcher.fetch_single("owner/nonexistent")


def test_fetch_snapshots_empty_list():
    """Test fetching with empty repository list."""
    mock_client = Mock()
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Should return empty list
    snapshots = fetcher.fetch_snapshots([])
    assert snapshots == []


def test_fetch_snapshots_with_batch_size():
    """Test fetching with explicit batch size."""
    # Create mock GraphQL client
    mock_client = Mock()
    
    def mock_execute(query, variables):
        # Return data for batch query
        return {
            "data": {
                "repo_0": {
                    "nameWithOwner": "owner1/repo1",
                    "pushedAt": "2024-01-01T00:00:00Z",
                    "latestRelease": None,
                    "stargazerCount": 100,
                    "isArchived": False,
                    "licenseInfo": None,
                    "issues": {"totalCount": 10}
                },
                "repo_1": {
                    "nameWithOwner": "owner2/repo2",
                    "pushedAt": "2024-01-02T00:00:00Z",
                    "latestRelease": None,
                    "stargazerCount": 200,
                    "isArchived": False,
                    "licenseInfo": None,
                    "issues": {"totalCount": 20}
                }
            }
        }
    
    mock_client.execute_query = Mock(side_effect=mock_execute)
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Fetch with batch size
    snapshots = fetcher.fetch_snapshots(
        ["owner1/repo1", "owner2/repo2"],
        batch_size=2
    )
    
    # Verify results
    assert len(snapshots) == 2
    assert snapshots[0].repo_full_name == "owner1/repo1"
    assert snapshots[1].repo_full_name == "owner2/repo2"


def test_adaptive_batch_size_increase():
    """Test that batch size increases on success."""
    mock_client = Mock()
    config = IngestionConfig()
    fetcher = RepoSnapshotFetcher(mock_client, config)
    
    initial_size = fetcher.current_batch_size
    
    # Simulate success
    fetcher._adjust_batch_size_on_success()
    
    # Batch size should increase
    assert fetcher.current_batch_size > initial_size
    assert fetcher.current_batch_size <= fetcher.max_batch_size


def test_adaptive_batch_size_decrease():
    """Test that batch size decreases on failure."""
    mock_client = Mock()
    config = IngestionConfig()
    fetcher = RepoSnapshotFetcher(mock_client, config)
    
    initial_size = fetcher.current_batch_size
    
    # Simulate failure
    fetcher._adjust_batch_size_on_failure()
    
    # Batch size should decrease
    assert fetcher.current_batch_size < initial_size
    assert fetcher.current_batch_size >= fetcher.min_batch_size


def test_adaptive_batch_size_max_bound():
    """Test that batch size doesn't exceed maximum."""
    mock_client = Mock()
    config = IngestionConfig()
    fetcher = RepoSnapshotFetcher(mock_client, config)
    
    # Set to near max
    fetcher.current_batch_size = fetcher.max_batch_size - 1
    
    # Simulate multiple successes
    for _ in range(10):
        fetcher._adjust_batch_size_on_success()
    
    # Should not exceed max
    assert fetcher.current_batch_size == fetcher.max_batch_size


def test_adaptive_batch_size_min_bound():
    """Test that batch size doesn't go below minimum."""
    mock_client = Mock()
    config = IngestionConfig()
    fetcher = RepoSnapshotFetcher(mock_client, config)
    
    # Set to near min
    fetcher.current_batch_size = fetcher.min_batch_size + 1
    
    # Simulate multiple failures
    for _ in range(10):
        fetcher._adjust_batch_size_on_failure()
    
    # Should not go below min
    assert fetcher.current_batch_size == fetcher.min_batch_size


def test_fetch_snapshots_with_fallback():
    """Test that batch failure triggers individual fallback."""
    mock_client = Mock()
    
    call_count = [0]
    
    def mock_execute(query, variables):
        call_count[0] += 1
        
        # First call (batch) fails
        if call_count[0] == 1:
            raise Exception("Batch query failed")
        
        # Subsequent calls (individual) succeed
        if "owner" in variables and "repo" in variables:
            repo_id = f"{variables['owner']}/{variables['repo']}"
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
    
    mock_client.execute_query = Mock(side_effect=mock_execute)
    
    # Create fetcher
    fetcher = RepoSnapshotFetcher(mock_client)
    
    # Fetch with small batch
    snapshots = fetcher.fetch_snapshots(
        ["owner1/repo1", "owner2/repo2"],
        batch_size=2
    )
    
    # Should have fallen back to individual fetches
    assert len(snapshots) == 2
    # Should have made 3 calls: 1 batch (failed) + 2 individual
    assert call_count[0] == 3
