"""
Property-based tests for REST client.

Feature: github-api-optimization-query-coverage

Property 6: REST Endpoint Construction
For any repository identifier and REST endpoint type (contributors, issues, etc.),
the constructed URL should match the GitHub API v3 specification format.

Property 7: REST Pagination Completeness
For any REST endpoint requiring pagination, following Link header pagination through
all pages should return all available items exactly once.

Validates: Requirements 2.1-2.6
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.ingestion.rest_client import RESTClient


# Hypothesis strategies for generating test data

@st.composite
def valid_repo_identifiers(draw):
    """Generate valid repository identifiers in owner/repo format."""
    # Generate owner and repo names with valid GitHub naming rules
    owner = draw(st.text(
        min_size=1,
        max_size=39,
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-"
    ).filter(lambda x: x and not x.startswith("-") and not x.endswith("-")))
    
    repo = draw(st.text(
        min_size=1,
        max_size=100,
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    ).filter(lambda x: x and not x.startswith(".") and not x.endswith(".")))
    
    return f"{owner}/{repo}"


@st.composite
def rest_endpoint_types(draw):
    """Generate REST endpoint types."""
    endpoints = [
        "contributors",
        "issues",
        "stats/contributors",
        "issues/comments",
        "issues/events",
        "pulls",
        "commits",
        "releases",
    ]
    return draw(st.sampled_from(endpoints))


@st.composite
def mock_rest_success_response(draw):
    """Generate mock successful REST responses."""
    # Generate various successful response structures
    response_data = draw(st.one_of(
        st.just([{"id": 1, "login": "user1"}, {"id": 2, "login": "user2"}]),
        st.just([{"number": 1, "title": "Issue 1"}, {"number": 2, "title": "Issue 2"}]),
        st.just([{"id": 1, "body": "Comment 1"}]),
        st.just([]),  # Empty response
    ))
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = Mock()
    mock_response.headers = {}
    
    return mock_response


@st.composite
def paginated_responses(draw):
    """Generate a sequence of paginated responses."""
    # Generate 1-5 pages
    num_pages = draw(st.integers(min_value=1, max_value=5))
    
    responses = []
    for page_num in range(num_pages):
        # Generate items for this page (1-10 items per page)
        num_items = draw(st.integers(min_value=1, max_value=10))
        items = [
            {"id": page_num * 100 + i, "data": f"item_{page_num}_{i}"}
            for i in range(num_items)
        ]
        
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = items
        mock_response.raise_for_status = Mock()
        
        # Add Link header if not the last page
        if page_num < num_pages - 1:
            next_page = page_num + 2
            mock_response.headers = {
                "Link": f'<https://api.github.com/repos/owner/repo/issues?page={next_page}>; rel="next"'
            }
        else:
            mock_response.headers = {}
        
        responses.append(mock_response)
    
    return responses


# Property 6: REST Endpoint Construction
# Tag format: Feature: github-api-optimization-query-coverage, Property 6: REST Endpoint Construction

@settings(max_examples=100, deadline=None)
@given(
    repo_identifier=valid_repo_identifiers(),
    endpoint_type=rest_endpoint_types()
)
def test_property_rest_endpoint_construction(repo_identifier, endpoint_type):
    """
    Property 6: REST Endpoint Construction
    
    For any repository identifier and REST endpoint type (contributors, issues, etc.),
    the constructed URL should match the GitHub API v3 specification format.
    
    This property ensures:
    1. URLs are properly formatted with base URL + /repos/ + owner/repo + endpoint
    2. Leading slashes are handled correctly
    3. URLs match GitHub API v3 specification
    
    **Validates: Requirements 2.1-2.6**
    """
    client = RESTClient(token="test_token", config={"retry_attempts": 1})
    
    # Construct endpoint path
    endpoint = f"/repos/{repo_identifier}/{endpoint_type}"
    
    # Mock successful response
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.json.return_value = []
    mock_response.raise_for_status = Mock()
    
    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        try:
            client.get(endpoint)
        except Exception:
            # Ignore errors, we're just checking URL construction
            pass
        
        # Verify the URL was constructed correctly
        assert mock_get.called, "Session.get was not called"
        call_args = mock_get.call_args[0]
        called_url = call_args[0]
        
        # Verify URL format matches GitHub API v3 specification
        assert called_url.startswith("https://api.github.com/"), \
            f"URL doesn't start with GitHub API base: {called_url}"
        
        assert f"/repos/{repo_identifier}/" in called_url, \
            f"URL doesn't contain /repos/{repo_identifier}/: {called_url}"
        
        assert endpoint_type in called_url, \
            f"URL doesn't contain endpoint type {endpoint_type}: {called_url}"
        
        # Verify no double slashes (except in https://)
        url_path = called_url.replace("https://", "")
        assert "//" not in url_path, \
            f"URL contains double slashes: {called_url}"


@settings(max_examples=100, deadline=None)
@given(
    repo_identifier=valid_repo_identifiers(),
    endpoint_type=rest_endpoint_types(),
    has_leading_slash=st.booleans()
)
def test_property_endpoint_leading_slash_handling(repo_identifier, endpoint_type, has_leading_slash):
    """
    Property: Endpoint paths with or without leading slashes are handled correctly.
    
    The client should handle endpoints with or without leading slashes and
    construct valid URLs in both cases.
    
    **Validates: Requirements 2.1-2.6**
    """
    client = RESTClient(token="test_token", config={"retry_attempts": 1})
    
    # Construct endpoint with or without leading slash
    if has_leading_slash:
        endpoint = f"/repos/{repo_identifier}/{endpoint_type}"
    else:
        endpoint = f"repos/{repo_identifier}/{endpoint_type}"
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.json.return_value = []
    mock_response.raise_for_status = Mock()
    
    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        try:
            client.get(endpoint)
        except Exception:
            pass
        
        # Verify URL is valid regardless of leading slash
        assert mock_get.called
        called_url = mock_get.call_args[0][0]
        
        # Should have exactly one slash between base URL and repos
        assert called_url.startswith("https://api.github.com/repos/"), \
            f"URL not properly formatted: {called_url}"


# Property 7: REST Pagination Completeness
# Tag format: Feature: github-api-optimization-query-coverage, Property 7: REST Pagination Completeness

@settings(max_examples=100, deadline=None)
@given(
    responses=paginated_responses()
)
def test_property_rest_pagination_completeness(responses):
    """
    Property 7: REST Pagination Completeness
    
    For any REST endpoint requiring pagination, following Link header pagination
    through all pages should return all available items exactly once.
    
    This property ensures:
    1. All pages are fetched
    2. All items are returned
    3. No items are duplicated
    4. No items are skipped
    
    **Validates: Requirements 2.6**
    """
    client = RESTClient(token="test_token", config={"retry_attempts": 1})
    
    # Calculate expected items from all pages
    expected_items = []
    for response in responses:
        expected_items.extend(response.json.return_value)
    
    # Extract all item IDs for comparison
    expected_ids = [item["id"] for item in expected_items]
    
    with patch.object(client.session, "get", side_effect=responses):
        # Paginate through all pages
        actual_pages = list(client.paginate("/repos/owner/repo/issues"))
    
    # Flatten actual items from all pages
    actual_items = []
    for page in actual_pages:
        actual_items.extend(page)
    
    actual_ids = [item["id"] for item in actual_items]
    
    # Verify completeness: all items returned exactly once
    assert len(actual_ids) == len(expected_ids), \
        f"Expected {len(expected_ids)} items, got {len(actual_ids)}"
    
    # Verify no duplicates
    assert len(actual_ids) == len(set(actual_ids)), \
        f"Duplicate items found: {actual_ids}"
    
    # Verify all expected items are present
    assert sorted(actual_ids) == sorted(expected_ids), \
        f"Items mismatch. Expected: {sorted(expected_ids)}, Got: {sorted(actual_ids)}"


@settings(max_examples=100, deadline=None)
@given(
    num_pages=st.integers(min_value=1, max_value=10),
    items_per_page=st.integers(min_value=1, max_value=20)
)
def test_property_pagination_returns_all_items_exactly_once(num_pages, items_per_page):
    """
    Property: Pagination returns all items exactly once, no duplicates or omissions.
    
    For any number of pages and items per page, pagination should return
    all items exactly once without duplicates or omissions.
    
    **Validates: Requirements 2.6**
    """
    client = RESTClient(token="test_token", config={"retry_attempts": 1})
    
    # Generate paginated responses
    responses = []
    all_expected_ids = []
    
    for page_num in range(num_pages):
        items = [
            {"id": page_num * items_per_page + i, "data": f"item_{page_num}_{i}"}
            for i in range(items_per_page)
        ]
        all_expected_ids.extend([item["id"] for item in items])
        
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = items
        mock_response.raise_for_status = Mock()
        
        # Add Link header if not the last page
        if page_num < num_pages - 1:
            next_page = page_num + 2
            mock_response.headers = {
                "Link": f'<https://api.github.com/repos/owner/repo/issues?page={next_page}>; rel="next"'
            }
        else:
            mock_response.headers = {}
        
        responses.append(mock_response)
    
    with patch.object(client.session, "get", side_effect=responses):
        pages = list(client.paginate("/repos/owner/repo/issues"))
    
    # Collect all items
    actual_items = []
    for page in pages:
        actual_items.extend(page)
    
    actual_ids = [item["id"] for item in actual_items]
    
    # Verify all items returned exactly once
    assert len(actual_ids) == len(all_expected_ids), \
        f"Expected {len(all_expected_ids)} items, got {len(actual_ids)}"
    
    assert len(actual_ids) == len(set(actual_ids)), \
        "Duplicate items found in pagination results"
    
    assert sorted(actual_ids) == sorted(all_expected_ids), \
        "Items mismatch between expected and actual"


@settings(max_examples=100, deadline=None)
@given(
    num_pages=st.integers(min_value=2, max_value=5),
    max_pages_limit=st.integers(min_value=1, max_value=3)
)
def test_property_pagination_respects_max_pages(num_pages, max_pages_limit):
    """
    Property: Pagination respects max_pages limit.
    
    When max_pages is specified, pagination should stop after that many pages
    even if more pages are available.
    
    **Validates: Requirements 2.6**
    """
    client = RESTClient(token="test_token", config={"retry_attempts": 1})
    
    # Generate enough pages to exceed the limit
    # We need to generate at least max_pages_limit pages
    total_pages_to_generate = max(num_pages, max_pages_limit + 1)
    responses = []
    
    for page_num in range(total_pages_to_generate):
        items = [{"id": page_num * 10 + i} for i in range(5)]
        
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = items
        mock_response.raise_for_status = Mock()
        
        # Always add Link header to simulate more pages available
        next_page = page_num + 2
        mock_response.headers = {
            "Link": f'<https://api.github.com/repos/owner/repo/issues?page={next_page}>; rel="next"'
        }
        
        responses.append(mock_response)
    
    with patch.object(client.session, "get", side_effect=responses):
        pages = list(client.paginate("/repos/owner/repo/issues", max_pages=max_pages_limit))
    
    # Verify pagination stopped at max_pages
    assert len(pages) == max_pages_limit, \
        f"Expected exactly {max_pages_limit} pages, got {len(pages)}"


@settings(max_examples=100, deadline=None)
@given(
    repo_identifier=valid_repo_identifiers(),
    endpoint_type=rest_endpoint_types()
)
def test_property_single_page_returns_all_items(repo_identifier, endpoint_type):
    """
    Property: Single page pagination returns all items.
    
    When there's only one page (no Link header), pagination should return
    all items from that single page.
    
    **Validates: Requirements 2.6**
    """
    client = RESTClient(token="test_token", config={"retry_attempts": 1})
    
    # Generate single page response
    items = [{"id": i, "data": f"item_{i}"} for i in range(10)]
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.json.return_value = items
    mock_response.raise_for_status = Mock()
    mock_response.headers = {}  # No Link header
    
    endpoint = f"/repos/{repo_identifier}/{endpoint_type}"
    
    with patch.object(client.session, "get", return_value=mock_response):
        pages = list(client.paginate(endpoint))
    
    # Verify single page returned
    assert len(pages) == 1, f"Expected 1 page, got {len(pages)}"
    
    # Verify all items returned
    assert len(pages[0]) == len(items), \
        f"Expected {len(items)} items, got {len(pages[0])}"
    
    # Verify items match
    assert pages[0] == items, "Items don't match expected"


@settings(max_examples=100, deadline=None)
@given(
    num_pages=st.integers(min_value=1, max_value=5)
)
def test_property_empty_pages_handled_correctly(num_pages):
    """
    Property: Empty pages are handled correctly in pagination.
    
    Pagination should handle empty pages (empty arrays) without errors
    and continue to subsequent pages if available.
    
    **Validates: Requirements 2.6**
    """
    client = RESTClient(token="test_token", config={"retry_attempts": 1})
    
    # Generate responses with some empty pages
    responses = []
    for page_num in range(num_pages):
        # Randomly make some pages empty
        if page_num % 2 == 0:
            items = []
        else:
            items = [{"id": page_num * 10 + i} for i in range(3)]
        
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = items
        mock_response.raise_for_status = Mock()
        
        # Add Link header if not the last page
        if page_num < num_pages - 1:
            next_page = page_num + 2
            mock_response.headers = {
                "Link": f'<https://api.github.com/repos/owner/repo/issues?page={next_page}>; rel="next"'
            }
        else:
            mock_response.headers = {}
        
        responses.append(mock_response)
    
    with patch.object(client.session, "get", side_effect=responses):
        # Should not raise an error
        pages = list(client.paginate("/repos/owner/repo/issues"))
    
    # Verify all pages returned (including empty ones)
    assert len(pages) == num_pages, \
        f"Expected {num_pages} pages, got {len(pages)}"
    
    # Verify empty pages are actually empty
    for page_num, page in enumerate(pages):
        if page_num % 2 == 0:
            assert len(page) == 0, f"Page {page_num} should be empty"
        else:
            assert len(page) > 0, f"Page {page_num} should not be empty"
