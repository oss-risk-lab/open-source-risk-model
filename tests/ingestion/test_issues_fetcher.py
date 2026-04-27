"""
Unit tests for IssuesFetcher.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from src.open_source_risk_model.ingestion.issues_fetcher import IssuesFetcher
from src.open_source_risk_model.ingestion.models import IssueRecord


class TestIssuesFetcher:
    """Test suite for IssuesFetcher."""

    @pytest.fixture
    def mock_rest_client(self):
        """Create a mock REST client."""
        return Mock()

    @pytest.fixture
    def fetcher(self, mock_rest_client):
        """Create an IssuesFetcher instance."""
        return IssuesFetcher(mock_rest_client)

    def test_fetch_issues_basic(self, fetcher, mock_rest_client):
        """Test fetching issues with basic data."""
        # Mock paginate to return issue data
        mock_rest_client.paginate.return_value = iter([
            [
                {
                    "number": 1,
                    "state": "open",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "updated_at": "2023-01-02T00:00:00Z",
                    "comments": 5,
                    "author_association": "CONTRIBUTOR",
                    "labels": [{"name": "bug"}, {"name": "help wanted"}],
                },
                {
                    "number": 2,
                    "state": "closed",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": "2023-01-03T00:00:00Z",
                    "updated_at": "2023-01-03T00:00:00Z",
                    "comments": 2,
                    "author_association": "OWNER",
                    "labels": [],
                },
            ]
        ])

        # Fetch issues
        records = fetcher.fetch_issues("owner/repo", state="all")

        # Verify results
        assert len(records) == 2
        assert records[0].number == 1
        assert records[0].state == "open"
        assert records[0].comments == 5
        assert records[0].author_association == "CONTRIBUTOR"
        assert records[0].labels == ["bug", "help wanted"]
        assert records[0].closed_at is None


        assert records[1].number == 2
        assert records[1].state == "closed"
        assert records[1].closed_at is not None

    def test_fetch_issues_filters_pull_requests(self, fetcher, mock_rest_client):
        """Test that pull requests are filtered out."""
        # Mock paginate to return issues and pull requests
        mock_rest_client.paginate.return_value = iter([
            [
                {
                    "number": 1,
                    "state": "open",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "updated_at": "2023-01-02T00:00:00Z",
                    "comments": 5,
                    "author_association": "CONTRIBUTOR",
                    "labels": [],
                },
                {
                    "number": 2,
                    "state": "open",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "updated_at": "2023-01-02T00:00:00Z",
                    "comments": 3,
                    "author_association": "CONTRIBUTOR",
                    "labels": [],
                    "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/2"},
                },
            ]
        ])

        # Fetch issues
        records = fetcher.fetch_issues("owner/repo")

        # Verify only issue is returned (PR filtered out)
        assert len(records) == 1
        assert records[0].number == 1

    def test_fetch_issues_pagination(self, fetcher, mock_rest_client):
        """Test pagination handling."""
        # Mock paginate to return multiple pages
        mock_rest_client.paginate.return_value = iter([
            [
                {
                    "number": 1,
                    "state": "open",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "updated_at": "2023-01-02T00:00:00Z",
                    "comments": 5,
                    "author_association": "CONTRIBUTOR",
                    "labels": [],
                }
            ],
            [
                {
                    "number": 2,
                    "state": "closed",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": "2023-01-03T00:00:00Z",
                    "updated_at": "2023-01-03T00:00:00Z",
                    "comments": 2,
                    "author_association": "OWNER",
                    "labels": [],
                }
            ],
        ])

        # Fetch issues
        records = fetcher.fetch_issues("owner/repo")

        # Verify results
        assert len(records) == 2
        assert records[0].number == 1
        assert records[1].number == 2

    def test_fetch_issues_max_cap(self, fetcher, mock_rest_client):
        """Test that issue fetching respects max_issues cap."""
        # Create fetcher with low max_issues
        fetcher_with_cap = IssuesFetcher(
            mock_rest_client, config={"max_issues_per_repo": 2}
        )

        # Mock paginate to return more issues than cap
        mock_rest_client.paginate.return_value = iter([
            [
                {
                    "number": i,
                    "state": "open",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "updated_at": "2023-01-02T00:00:00Z",
                    "comments": 0,
                    "author_association": "NONE",
                    "labels": [],
                }
                for i in range(1, 6)  # 5 issues
            ]
        ])

        # Fetch issues
        records = fetcher_with_cap.fetch_issues("owner/repo")

        # Verify only max_issues are returned
        assert len(records) == 2

    def test_fetch_issues_invalid_repo(self, fetcher, mock_rest_client):
        """Test error handling for invalid repository identifier."""
        with pytest.raises(ValueError, match="Invalid repository identifier"):
            fetcher.fetch_issues("invalid-repo")

    def test_fetch_issues_missing_number(self, fetcher, mock_rest_client):
        """Test handling of issues with missing number field."""
        # Mock paginate to return data with missing number
        mock_rest_client.paginate.return_value = iter([
            [
                {
                    "number": 1,
                    "state": "open",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "updated_at": "2023-01-02T00:00:00Z",
                    "comments": 5,
                    "author_association": "CONTRIBUTOR",
                    "labels": [],
                },
                {
                    # Missing number
                    "state": "open",
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "updated_at": "2023-01-02T00:00:00Z",
                    "comments": 3,
                    "author_association": "CONTRIBUTOR",
                    "labels": [],
                },
            ]
        ])

        # Fetch issues
        records = fetcher.fetch_issues("owner/repo")

        # Verify only valid issue is returned
        assert len(records) == 1
        assert records[0].number == 1

    def test_fetch_issue_events(self, fetcher, mock_rest_client):
        """Test fetching issue events."""
        # Mock paginate to return event data
        mock_rest_client.paginate.return_value = iter([
            [
                {
                    "id": 1,
                    "event": "labeled",
                    "created_at": "2023-01-01T00:00:00Z",
                },
                {
                    "id": 2,
                    "event": "closed",
                    "created_at": "2023-01-02T00:00:00Z",
                },
            ]
        ])

        # Fetch events
        events = fetcher.fetch_issue_events("owner/repo", 1)

        # Verify results
        assert len(events) == 2
        assert events[0]["event"] == "labeled"
        assert events[1]["event"] == "closed"

    def test_fetch_issue_events_invalid_repo(self, fetcher, mock_rest_client):
        """Test error handling for invalid repository identifier."""
        with pytest.raises(ValueError, match="Invalid repository identifier"):
            fetcher.fetch_issue_events("invalid-repo", 1)
