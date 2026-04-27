"""
Property-based tests for GraphQL client.

Feature: github-api-optimization-query-coverage
Property 1: GraphQL Query Execution

For any valid GraphQL query and variables, executing the query through GraphQL_Client
should either return a successful response or a descriptive error, never silently fail.

Validates: Requirements 1.1, 1.6
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest
import requests
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.ingestion.graphql_client import GraphQLClient


# Hypothesis strategies for generating test data

@st.composite
def valid_graphql_queries(draw):
    """Generate valid GraphQL query strings."""
    # Generate simple but valid GraphQL queries
    query_templates = [
        "query { viewer { login } }",
        "query { repository(owner: \"test\", name: \"repo\") { name } }",
        "query($owner: String!) { repository(owner: $owner, name: \"repo\") { name } }",
        "query { rateLimit { limit remaining } }",
        "query { organization(login: \"test\") { name } }",
    ]
    return draw(st.sampled_from(query_templates))


@st.composite
def valid_variables(draw):
    """Generate valid variable dictionaries for GraphQL queries."""
    # Generate various valid variable structures
    var_types = [
        {},  # Empty variables
        {"owner": draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"))},
        {"name": draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"))},
        {
            "owner": draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz")),
            "name": draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"))
        },
    ]
    return draw(st.sampled_from(var_types))


@st.composite
def mock_success_response(draw):
    """Generate mock successful GraphQL responses."""
    # Generate various successful response structures
    response_data = draw(st.one_of(
        st.just({"data": {"viewer": {"login": "testuser"}}}),
        st.just({"data": {"repository": {"name": "test-repo", "stargazerCount": 100}}}),
        st.just({"data": {"rateLimit": {"limit": 5000, "remaining": 4999}}}),
        st.just({"data": {"organization": {"name": "Test Org"}}}),
    ))
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.headers = {"X-RateLimit-Cost": str(draw(st.integers(min_value=1, max_value=100)))}
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = Mock()
    
    return mock_response


@st.composite
def mock_graphql_error_response(draw):
    """Generate mock GraphQL error responses."""
    error_messages = [
        "Could not resolve to a Repository",
        "Query complexity too high",
        "Field 'invalid' doesn't exist on type 'Repository'",
        "Variable '$owner' of required type 'String!' was not provided",
    ]
    
    error_data = {
        "errors": [
            {
                "message": draw(st.sampled_from(error_messages)),
                "path": draw(st.one_of(
                    st.just([]),
                    st.just(["repository"]),
                    st.just(["repo_owner_name", "field"]),
                ))
            }
        ]
    }
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.json.return_value = error_data
    mock_response.raise_for_status = Mock()
    
    return mock_response


@st.composite
def mock_http_error_response(draw):
    """Generate mock HTTP error responses."""
    status_codes = [403, 429, 500, 502, 503]
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = draw(st.sampled_from(status_codes))
    mock_response.headers = {}
    mock_response.raise_for_status = Mock(side_effect=requests.exceptions.HTTPError())
    
    return mock_response


@st.composite
def mock_timeout_exception(draw):
    """Generate mock timeout exceptions."""
    return requests.exceptions.Timeout("Request timed out")


# Property 1: GraphQL Query Execution
# Tag format: Feature: github-api-optimization-query-coverage, Property 1: GraphQL Query Execution

@settings(max_examples=100, deadline=None)
@given(
    query=valid_graphql_queries(),
    variables=valid_variables(),
    response_type=st.sampled_from(["success", "graphql_error", "http_error", "timeout"])
)
@patch("time.sleep")  # Mock sleep to speed up tests
def test_property_graphql_query_execution_never_silent_fails(
    mock_sleep, query, variables, response_type
):
    """
    Property 1: GraphQL Query Execution
    
    For any valid GraphQL query and variables, executing the query through GraphQL_Client
    should either return a successful response or raise a descriptive error, never silently fail.
    
    This property ensures:
    1. The client always returns either a successful response dict OR raises an exception
    2. No silent failures occur (no None returns, no unhandled exceptions)
    3. Error messages are descriptive when failures occur
    
    **Validates: Requirements 1.1, 1.6**
    """
    # Create client with minimal retry attempts for faster testing
    client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
    
    with patch("requests.Session.post") as mock_post:
        # Set up mock response based on response type
        if response_type == "success":
            mock_response = Mock(spec=requests.Response)
            mock_response.status_code = 200
            mock_response.headers = {"X-RateLimit-Cost": "1"}
            mock_response.json.return_value = {"data": {"test": "success"}}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            # Should return a successful response dict
            result = client.execute_query(query, variables)
            
            # Verify result is a dict and not None
            assert result is not None, "Client returned None instead of a response"
            assert isinstance(result, dict), f"Client returned {type(result)} instead of dict"
            assert "data" in result, "Successful response missing 'data' key"
            
        elif response_type == "graphql_error":
            mock_response = Mock(spec=requests.Response)
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.json.return_value = {
                "errors": [{"message": "GraphQL error occurred"}]
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            # Should raise an exception with descriptive error
            with pytest.raises(Exception) as exc_info:
                client.execute_query(query, variables)
            
            # Verify error message is descriptive
            error_message = str(exc_info.value)
            assert error_message, "Exception raised with empty error message"
            assert len(error_message) > 0, "Error message is empty"
            assert "GraphQL" in error_message or "error" in error_message.lower(), \
                f"Error message not descriptive: {error_message}"
            
        elif response_type == "http_error":
            mock_response = Mock(spec=requests.Response)
            mock_response.status_code = 429
            mock_response.headers = {}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            # Should raise an exception with descriptive error
            with pytest.raises(Exception) as exc_info:
                client.execute_query(query, variables)
            
            # Verify error message is descriptive
            error_message = str(exc_info.value)
            assert error_message, "Exception raised with empty error message"
            assert len(error_message) > 0, "Error message is empty"
            
        elif response_type == "timeout":
            mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
            
            # Should raise an exception with descriptive error
            with pytest.raises(Exception) as exc_info:
                client.execute_query(query, variables)
            
            # Verify error message is descriptive
            error_message = str(exc_info.value)
            assert error_message, "Exception raised with empty error message"
            assert len(error_message) > 0, "Error message is empty"
            assert "failed" in error_message.lower() or "timeout" in error_message.lower(), \
                f"Error message not descriptive for timeout: {error_message}"


@settings(max_examples=100, deadline=None)
@given(
    query=valid_graphql_queries(),
    variables=valid_variables(),
    mock_response=mock_success_response()
)
@patch("time.sleep")
def test_property_successful_responses_are_dicts(mock_sleep, query, variables, mock_response):
    """
    Property: Successful responses are always dictionaries.
    
    When a GraphQL query succeeds, the client must return a dictionary containing
    the response data, never None or other types.
    
    **Validates: Requirements 1.1**
    """
    client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
    
    with patch("requests.Session.post", return_value=mock_response):
        result = client.execute_query(query, variables)
        
        # Verify result is a dict
        assert result is not None, "Client returned None for successful response"
        assert isinstance(result, dict), f"Client returned {type(result)} instead of dict"
        assert "data" in result or "errors" in result, \
            "Response missing both 'data' and 'errors' keys"


@settings(max_examples=100, deadline=None)
@given(
    query=valid_graphql_queries(),
    variables=valid_variables(),
    mock_response=mock_graphql_error_response()
)
@patch("time.sleep")
def test_property_graphql_errors_raise_exceptions(mock_sleep, query, variables, mock_response):
    """
    Property: GraphQL errors always raise exceptions with descriptive messages.
    
    When a GraphQL query returns errors, the client must raise an exception
    with a descriptive error message, never return None or silently fail.
    
    **Validates: Requirements 1.6**
    """
    client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
    
    with patch("requests.Session.post", return_value=mock_response):
        with pytest.raises(Exception) as exc_info:
            client.execute_query(query, variables)
        
        # Verify exception has descriptive message
        error_message = str(exc_info.value)
        assert error_message, "Exception raised with empty error message"
        assert len(error_message) > 0, "Error message is empty"
        
        # Verify error message contains useful information
        assert "GraphQL" in error_message or "error" in error_message.lower(), \
            f"Error message not descriptive: {error_message}"


@settings(max_examples=100, deadline=None)
@given(
    query=valid_graphql_queries(),
    variables=valid_variables(),
    status_code=st.sampled_from([403, 429, 500, 502, 503])
)
@patch("time.sleep")
def test_property_http_errors_raise_exceptions(mock_sleep, query, variables, status_code):
    """
    Property: HTTP errors always raise exceptions.
    
    When an HTTP error occurs (rate limit, server error, etc.), the client must
    raise an exception, never return None or silently fail.
    
    **Validates: Requirements 1.1, 1.6**
    """
    client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = status_code
    mock_response.headers = {}
    mock_response.raise_for_status = Mock()
    
    with patch("requests.Session.post", return_value=mock_response):
        with pytest.raises(Exception) as exc_info:
            client.execute_query(query, variables)
        
        # Verify exception was raised (not None returned)
        assert exc_info.value is not None, "No exception raised for HTTP error"
        error_message = str(exc_info.value)
        assert len(error_message) > 0, "Error message is empty"


@settings(max_examples=100, deadline=None)
@given(
    query=valid_graphql_queries(),
    variables=valid_variables()
)
@patch("time.sleep")
def test_property_timeout_errors_raise_exceptions(mock_sleep, query, variables):
    """
    Property: Timeout errors always raise exceptions.
    
    When a request times out, the client must raise an exception with a
    descriptive error message, never return None or silently fail.
    
    **Validates: Requirements 1.1, 1.6**
    """
    client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
    
    with patch("requests.Session.post", side_effect=requests.exceptions.Timeout("Request timed out")):
        with pytest.raises(Exception) as exc_info:
            client.execute_query(query, variables)
        
        # Verify exception was raised with descriptive message
        assert exc_info.value is not None, "No exception raised for timeout"
        error_message = str(exc_info.value)
        assert len(error_message) > 0, "Error message is empty"
        assert "failed" in error_message.lower() or "timeout" in error_message.lower(), \
            f"Error message not descriptive for timeout: {error_message}"


@settings(max_examples=100, deadline=None)
@given(
    query=valid_graphql_queries(),
    variables=valid_variables()
)
@patch("time.sleep")
def test_property_no_none_returns(mock_sleep, query, variables):
    """
    Property: Client never returns None.
    
    The client must either return a valid response dict or raise an exception,
    never return None which would be a silent failure.
    
    **Validates: Requirements 1.1, 1.6**
    """
    client = GraphQLClient(token="test_token", config={"retry_attempts": 1})
    
    # Test with successful response
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.headers = {"X-RateLimit-Cost": "1"}
    mock_response.json.return_value = {"data": {"test": "success"}}
    mock_response.raise_for_status = Mock()
    
    with patch("requests.Session.post", return_value=mock_response):
        result = client.execute_query(query, variables)
        assert result is not None, "Client returned None for successful response"
        assert isinstance(result, dict), f"Client returned {type(result)} instead of dict"
