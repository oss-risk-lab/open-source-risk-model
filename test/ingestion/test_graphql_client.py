"""
Unit tests for GraphQL client.

Tests query execution, retry logic, error handling, and query cost tracking.
"""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from src.open_source_risk_model.ingestion.graphql_client import GraphQLClient


class TestGraphQLClient:
    """Test suite for GraphQL client."""

    def test_init(self):
        """Test client initialization."""
        client = GraphQLClient(token="test_token")
        assert client.token == "test_token"
        assert client.endpoint == "https://api.github.com/graphql"
        assert "Authorization" in client.session.headers
        assert client.session.headers["Authorization"] == "Bearer test_token"

    @patch("requests.Session.post")
    def test_execute_query_success(self, mock_post):
        """Test successful query execution."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"X-RateLimit-Cost": "1"}
        mock_response.json.return_value = {
            "data": {
                "repository": {
                    "name": "test-repo",
                    "stargazerCount": 100
                }
            }
        }
        mock_post.return_value = mock_response

        client = GraphQLClient(token="test_token")
        query = "query { repository(owner: \"test\", name: \"repo\") { name } }"
        variables = {}

        result = client.execute_query(query, variables)

        assert "data" in result
        assert result["data"]["repository"]["name"] == "test-repo"
        assert client.last_query_cost == 1

    @patch("requests.Session.post")
    def test_execute_query_with_graphql_errors(self, mock_post):
        """Test query execution with GraphQL errors."""
        # Mock response with GraphQL errors
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "errors": [
                {
                    "message": "Could not resolve to a Repository",
                    "path": ["repo_owner_name", "name"]
                }
            ]
        }
        mock_post.return_value = mock_response

        client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
        query = "query { repository(owner: \"test\", name: \"repo\") { name } }"
        variables = {}

        with pytest.raises(Exception) as exc_info:
            client.execute_query(query, variables)

        assert "GraphQL errors" in str(exc_info.value)
        assert "owner/name" in str(exc_info.value)

    @patch("requests.Session.post")
    @patch("time.sleep")
    def test_execute_query_retry_on_rate_limit(self, mock_sleep, mock_post):
        """Test retry logic on rate limit errors."""
        # First call returns 429, second succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.headers = {"X-RateLimit-Cost": "1"}
        mock_response_success.json.return_value = {"data": {"test": "success"}}

        mock_post.side_effect = [mock_response_429, mock_response_success]

        client = GraphQLClient(token="test_token", config={"retry_attempts": 3})
        query = "query { test }"
        variables = {}

        result = client.execute_query(query, variables)

        assert result["data"]["test"] == "success"
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("requests.Session.post")
    @patch("time.sleep")
    def test_execute_query_exponential_backoff(self, mock_sleep, mock_post):
        """Test exponential backoff on retries."""
        # All calls fail with 429
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_post.return_value = mock_response

        client = GraphQLClient(
            token="test_token",
            config={
                "retry_attempts": 3,
                "retry_backoff_base": 2,
                "retry_max_wait": 60
            }
        )
        query = "query { test }"
        variables = {}

        with pytest.raises(Exception):
            client.execute_query(query, variables)

        # Should have called sleep with exponential backoff: 1, 2, 4
        assert mock_sleep.call_count == 3
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls[0] == 1  # 2^0
        assert sleep_calls[1] == 2  # 2^1
        assert sleep_calls[2] == 4  # 2^2

    @patch("requests.Session.post")
    def test_execute_query_timeout(self, mock_post):
        """Test timeout handling."""
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
        query = "query { test }"
        variables = {}

        with pytest.raises(Exception) as exc_info:
            client.execute_query(query, variables)

        assert "failed after 1 attempts" in str(exc_info.value)

    def test_parse_graphql_errors_with_path(self):
        """Test parsing GraphQL errors with repository path."""
        client = GraphQLClient(token="test_token")
        errors = [
            {
                "message": "Could not resolve to a Repository",
                "path": ["repo_owner_name", "name"]
            }
        ]

        result = client._parse_graphql_errors(errors)

        assert "owner/name" in result
        assert "Could not resolve to a Repository" in result

    def test_parse_graphql_errors_without_path(self):
        """Test parsing GraphQL errors without path."""
        client = GraphQLClient(token="test_token")
        errors = [
            {
                "message": "Query complexity too high"
            }
        ]

        result = client._parse_graphql_errors(errors)

        assert "Query complexity too high" in result

    def test_parse_graphql_errors_multiple(self):
        """Test parsing multiple GraphQL errors."""
        client = GraphQLClient(token="test_token")
        errors = [
            {
                "message": "Error 1",
                "path": ["repo_owner_repo1", "field"]
            },
            {
                "message": "Error 2",
                "path": ["repo_owner_repo2", "field"]
            }
        ]

        result = client._parse_graphql_errors(errors)

        assert "owner/repo1" in result
        assert "owner/repo2" in result
        assert "Error 1" in result
        assert "Error 2" in result

    def test_track_query_cost_with_header(self):
        """Test tracking query cost from response headers."""
        client = GraphQLClient(token="test_token")
        
        mock_response = Mock()
        mock_response.headers = {"X-RateLimit-Cost": "5"}

        client.track_query_cost(mock_response)

        assert client.last_query_cost == 5

    def test_track_query_cost_without_header(self):
        """Test tracking query cost when header is missing."""
        client = GraphQLClient(token="test_token")
        
        mock_response = Mock()
        mock_response.headers = {}

        client.track_query_cost(mock_response)

        assert client.last_query_cost is None

    def test_track_query_cost_invalid_header(self):
        """Test tracking query cost with invalid header value."""
        client = GraphQLClient(token="test_token")
        
        mock_response = Mock()
        mock_response.headers = {"X-RateLimit-Cost": "invalid"}

        client.track_query_cost(mock_response)

        assert client.last_query_cost is None

    @patch("requests.Session.post")
    def test_execute_query_with_variables(self, mock_post):
        """Test query execution with variables."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"data": {"test": "success"}}
        mock_post.return_value = mock_response

        client = GraphQLClient(token="test_token")
        query = "query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { name } }"
        variables = {"owner": "test", "name": "repo"}

        result = client.execute_query(query, variables)

        # Verify the request was made with correct payload
        call_args = mock_post.call_args
        assert call_args[1]["json"]["query"] == query
        assert call_args[1]["json"]["variables"] == variables

    @patch("requests.Session.post")
    def test_execute_query_custom_timeout(self, mock_post):
        """Test query execution with custom timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"data": {"test": "success"}}
        mock_post.return_value = mock_response

        client = GraphQLClient(token="test_token")
        query = "query { test }"
        variables = {}

        client.execute_query(query, variables, timeout=60)

        # Verify timeout was passed
        call_args = mock_post.call_args
        assert call_args[1]["timeout"] == 60
