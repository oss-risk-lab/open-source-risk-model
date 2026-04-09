"""
Unit tests for REST client.

Tests basic functionality, retry logic, pagination, and error handling.
"""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from src.open_source_risk_model.ingestion.rest_client import RESTClient


@pytest.fixture
def rest_client():
    """Create REST client for testing."""
    return RESTClient(token="test_token", config={
        "retry_attempts": 3,
        "retry_backoff_base": 2,
        "retry_max_wait": 60,
        "timeout_seconds": 30,
    })


class TestRESTClientGet:
    """Tests for the get method."""

    def test_successful_get_request(self, rest_client):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "test"}

        with patch.object(rest_client.session, "get", return_value=mock_response):
            result = rest_client.get("/repos/owner/repo")

        assert result == {"data": "test"}

    def test_get_with_params(self, rest_client):
        """Test GET request with query parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "test"}

        with patch.object(rest_client.session, "get", return_value=mock_response) as mock_get:
            result = rest_client.get("/repos/owner/repo/issues", params={"state": "all"})

        assert result == {"data": "test"}
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"] == {"state": "all"}

    def test_get_adds_leading_slash(self, rest_client):
        """Test that endpoint without leading slash gets one added."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "test"}

        with patch.object(rest_client.session, "get", return_value=mock_response) as mock_get:
            rest_client.get("repos/owner/repo")

        # Check that the URL has the leading slash
        call_args = mock_get.call_args[0]
        assert call_args[0] == "https://api.github.com/repos/owner/repo"

    def test_get_respects_timeout(self, rest_client):
        """Test that timeout parameter is passed correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "test"}

        with patch.object(rest_client.session, "get", return_value=mock_response) as mock_get:
            rest_client.get("/repos/owner/repo", timeout=15)

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["timeout"] == 15

    def test_get_retry_on_403(self, rest_client):
        """Test retry logic on 403 rate limit error."""
        # First two attempts fail with 403, third succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 403
        mock_response_fail.ok = False

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.ok = True
        mock_response_success.json.return_value = {"data": "test"}

        with patch.object(
            rest_client.session,
            "get",
            side_effect=[mock_response_fail, mock_response_fail, mock_response_success]
        ):
            with patch("time.sleep"):  # Mock sleep to speed up test
                result = rest_client.get("/repos/owner/repo")

        assert result == {"data": "test"}

    def test_get_retry_on_429(self, rest_client):
        """Test retry logic on 429 rate limit error."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 429
        mock_response_fail.ok = False

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.ok = True
        mock_response_success.json.return_value = {"data": "test"}

        with patch.object(
            rest_client.session,
            "get",
            side_effect=[mock_response_fail, mock_response_success]
        ):
            with patch("time.sleep"):
                result = rest_client.get("/repos/owner/repo")

        assert result == {"data": "test"}

    def test_get_retry_on_500(self, rest_client):
        """Test retry logic on 500 server error."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.ok = False

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.ok = True
        mock_response_success.json.return_value = {"data": "test"}

        with patch.object(
            rest_client.session,
            "get",
            side_effect=[mock_response_fail, mock_response_success]
        ):
            with patch("time.sleep"):
                result = rest_client.get("/repos/owner/repo")

        assert result == {"data": "test"}

    def test_get_retry_on_timeout(self, rest_client):
        """Test retry logic on timeout."""
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.ok = True
        mock_response_success.json.return_value = {"data": "test"}

        with patch.object(
            rest_client.session,
            "get",
            side_effect=[requests.exceptions.Timeout(), mock_response_success]
        ):
            with patch("time.sleep"):
                result = rest_client.get("/repos/owner/repo")

        assert result == {"data": "test"}

    def test_get_fails_after_max_retries(self, rest_client):
        """Test that get fails after exhausting retries."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.ok = False

        with patch.object(
            rest_client.session,
            "get",
            return_value=mock_response_fail
        ):
            with patch("time.sleep"):
                with pytest.raises(Exception, match="failed after 3 attempts"):
                    rest_client.get("/repos/owner/repo")

    def test_get_exponential_backoff(self, rest_client):
        """Test that exponential backoff is applied correctly."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 429
        mock_response_fail.ok = False

        with patch.object(rest_client.session, "get", return_value=mock_response_fail):
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(Exception):
                    rest_client.get("/repos/owner/repo")

                # Check that sleep was called with exponential backoff
                # Attempts: 0 (2^0=1), 1 (2^1=2), 2 (2^2=4)
                sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                assert sleep_calls == [1, 2, 4]


class TestRESTClientPaginate:
    """Tests for the paginate method."""

    def test_single_page_pagination(self, rest_client):
        """Test pagination with single page."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response.headers = {}  # No Link header

        with patch.object(rest_client.session, "get", return_value=mock_response):
            pages = list(rest_client.paginate("/repos/owner/repo/issues"))

        assert len(pages) == 1
        assert pages[0] == [{"id": 1}, {"id": 2}]

    def test_multi_page_pagination(self, rest_client):
        """Test pagination with multiple pages."""
        # First page
        mock_response_1 = Mock()
        mock_response_1.status_code = 200
        mock_response_1.ok = True
        mock_response_1.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response_1.headers = {
            "Link": '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
        }

        # Second page
        mock_response_2 = Mock()
        mock_response_2.status_code = 200
        mock_response_2.ok = True
        mock_response_2.json.return_value = [{"id": 3}, {"id": 4}]
        mock_response_2.headers = {}  # No next link

        with patch.object(
            rest_client.session,
            "get",
            side_effect=[mock_response_1, mock_response_2]
        ):
            pages = list(rest_client.paginate("/repos/owner/repo/issues"))

        assert len(pages) == 2
        assert pages[0] == [{"id": 1}, {"id": 2}]
        assert pages[1] == [{"id": 3}, {"id": 4}]

    def test_pagination_with_max_pages(self, rest_client):
        """Test pagination respects max_pages limit."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = [{"id": 1}]
        mock_response.headers = {
            "Link": '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
        }

        with patch.object(rest_client.session, "get", return_value=mock_response):
            pages = list(rest_client.paginate("/repos/owner/repo/issues", max_pages=2))

        assert len(pages) == 2

    def test_pagination_with_params(self, rest_client):
        """Test pagination with query parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = [{"id": 1}]
        mock_response.headers = {}

        with patch.object(rest_client.session, "get", return_value=mock_response) as mock_get:
            list(rest_client.paginate("/repos/owner/repo/issues", params={"state": "all"}))

        # First call should include params
        first_call_kwargs = mock_get.call_args_list[0][1]
        assert first_call_kwargs["params"] == {"state": "all"}

    def test_pagination_retry_on_error(self, rest_client):
        """Test pagination retries on error."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.ok = False

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.ok = True
        mock_response_success.json.return_value = [{"id": 1}]
        mock_response_success.headers = {}

        with patch.object(
            rest_client.session,
            "get",
            side_effect=[mock_response_fail, mock_response_success]
        ):
            with patch("time.sleep"):
                pages = list(rest_client.paginate("/repos/owner/repo/issues"))

        assert len(pages) == 1

    def test_pagination_fails_after_retries(self, rest_client):
        """Test pagination fails after exhausting retries."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.ok = False

        with patch.object(rest_client.session, "get", return_value=mock_response_fail):
            with patch("time.sleep"):
                with pytest.raises(Exception, match="pagination failed"):
                    list(rest_client.paginate("/repos/owner/repo/issues"))


class TestLinkHeaderParsing:
    """Tests for Link header parsing."""

    def test_parse_next_link_with_double_quotes(self, rest_client):
        """Test parsing Link header with double quotes."""
        link_header = '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
        next_url = rest_client._parse_next_link(link_header)
        assert next_url == "https://api.github.com/repos/owner/repo/issues?page=2"

    def test_parse_next_link_with_single_quotes(self, rest_client):
        """Test parsing Link header with single quotes."""
        link_header = "<https://api.github.com/repos/owner/repo/issues?page=2>; rel='next'"
        next_url = rest_client._parse_next_link(link_header)
        assert next_url == "https://api.github.com/repos/owner/repo/issues?page=2"

    def test_parse_next_link_with_multiple_links(self, rest_client):
        """Test parsing Link header with multiple links."""
        link_header = (
            '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next", '
            '<https://api.github.com/repos/owner/repo/issues?page=10>; rel="last"'
        )
        next_url = rest_client._parse_next_link(link_header)
        assert next_url == "https://api.github.com/repos/owner/repo/issues?page=2"

    def test_parse_next_link_no_next(self, rest_client):
        """Test parsing Link header without next link."""
        link_header = '<https://api.github.com/repos/owner/repo/issues?page=1>; rel="prev"'
        next_url = rest_client._parse_next_link(link_header)
        assert next_url is None

    def test_parse_next_link_empty(self, rest_client):
        """Test parsing empty Link header."""
        next_url = rest_client._parse_next_link(None)
        assert next_url is None

    def test_parse_next_link_malformed(self, rest_client):
        """Test parsing malformed Link header."""
        link_header = "not a valid link header"
        next_url = rest_client._parse_next_link(link_header)
        assert next_url is None
