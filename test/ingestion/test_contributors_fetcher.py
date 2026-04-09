"""
Unit tests for ContributorsFetcher.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from src.open_source_risk_model.ingestion.contributors_fetcher import (
    ContributorsFetcher,
)
from src.open_source_risk_model.ingestion.models import ContributorRecord, WeeklyActivity


class TestContributorsFetcher:
    """Test suite for ContributorsFetcher."""

    @pytest.fixture
    def mock_rest_client(self):
        """Create a mock REST client."""
        return Mock()

    @pytest.fixture
    def fetcher(self, mock_rest_client):
        """Create a ContributorsFetcher instance."""
        return ContributorsFetcher(mock_rest_client)

    def test_fetch_contributors_basic(self, fetcher, mock_rest_client):
        """Test fetching contributors with basic data."""
        # Mock paginate to return contributor data
        mock_rest_client.paginate.return_value = iter([
            [
                {"login": "user1", "contributions": 100},
                {"login": "user2", "contributions": 50},
            ]
        ])

        # Mock get to return empty stats (simulating failure)
        mock_rest_client.get.side_effect = Exception("Stats not available")

        # Fetch contributors
        records = fetcher.fetch_contributors("owner/repo")

        # Verify results
        assert len(records) == 2
        assert records[0].login == "user1"
        assert records[0].contributions == 100
        assert records[1].login == "user2"
        assert records[1].contributions == 50

        # Verify REST client was called correctly
        mock_rest_client.paginate.assert_called_once()


    def test_fetch_contributors_with_stats(self, fetcher, mock_rest_client):
        """Test fetching contributors with detailed statistics."""
        # Mock paginate to return contributor data
        mock_rest_client.paginate.return_value = iter([
            [{"login": "user1", "contributions": 100}]
        ])

        # Mock get to return stats data
        mock_rest_client.get.return_value = [
            {
                "login": "user1",
                "weeks": [
                    {"w": 1609459200, "a": 100, "d": 50, "c": 5},
                    {"w": 1610064000, "a": 200, "d": 100, "c": 10},
                ],
            }
        ]

        # Fetch contributors
        records = fetcher.fetch_contributors("owner/repo")

        # Verify results
        assert len(records) == 1
        assert records[0].login == "user1"
        assert records[0].contributions == 100
        assert len(records[0].weeks) == 2
        assert records[0].weeks[0].week_timestamp == 1609459200
        assert records[0].weeks[0].additions == 100
        assert records[0].weeks[0].deletions == 50
        assert records[0].weeks[0].commits == 5

    def test_fetch_contributors_pagination(self, fetcher, mock_rest_client):
        """Test pagination handling."""
        # Mock paginate to return multiple pages
        mock_rest_client.paginate.return_value = iter([
            [{"login": "user1", "contributions": 100}],
            [{"login": "user2", "contributions": 50}],
        ])

        # Mock get to return empty stats
        mock_rest_client.get.side_effect = Exception("Stats not available")

        # Fetch contributors
        records = fetcher.fetch_contributors("owner/repo")

        # Verify results
        assert len(records) == 2
        assert records[0].login == "user1"
        assert records[1].login == "user2"

    def test_fetch_contributors_invalid_repo(self, fetcher, mock_rest_client):
        """Test error handling for invalid repository identifier."""
        with pytest.raises(ValueError, match="Invalid repository identifier"):
            fetcher.fetch_contributors("invalid-repo")

    def test_fetch_contributors_missing_login(self, fetcher, mock_rest_client):
        """Test handling of contributors with missing login field."""
        # Mock paginate to return data with missing login
        mock_rest_client.paginate.return_value = iter([
            [
                {"login": "user1", "contributions": 100},
                {"contributions": 50},  # Missing login
            ]
        ])

        # Mock get to return empty stats
        mock_rest_client.get.side_effect = Exception("Stats not available")

        # Fetch contributors
        records = fetcher.fetch_contributors("owner/repo")

        # Verify only valid contributor is returned
        assert len(records) == 1
        assert records[0].login == "user1"

    def test_fetch_contributor_stats(self, fetcher, mock_rest_client):
        """Test fetching contributor statistics."""
        # Mock get to return stats data
        mock_rest_client.get.return_value = [
            {
                "login": "user1",
                "weeks": [{"w": 1609459200, "a": 100, "d": 50, "c": 5}],
            }
        ]

        # Fetch stats
        stats = fetcher.fetch_contributor_stats("owner/repo")

        # Verify results
        assert len(stats) == 1
        assert stats[0]["login"] == "user1"
        assert len(stats[0]["weeks"]) == 1

    def test_fetch_contributor_stats_invalid_repo(self, fetcher, mock_rest_client):
        """Test error handling for invalid repository identifier."""
        with pytest.raises(ValueError, match="Invalid repository identifier"):
            fetcher.fetch_contributor_stats("invalid-repo")
