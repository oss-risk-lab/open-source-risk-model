"""
Property-based tests for RateLimiter.

Tests universal properties that should hold across all valid inputs:
- Property 8: Rate Limit Header Parsing
- Property 9: Rate Limit Separation
- Property 10: Exponential Backoff Bounds
"""

import time
from unittest.mock import patch

import pytest
from hypothesis import given, strategies as st, settings

from src.open_source_risk_model.ingestion.rate_limiter import RateLimiter


# Custom strategies for generating test data
@st.composite
def rate_limit_headers(draw):
    """Generate valid rate limit headers."""
    remaining = draw(st.integers(min_value=0, max_value=10000))
    # Use a fixed base time to avoid flakiness
    base_time = 1700000000  # Fixed timestamp
    reset_time = draw(st.integers(min_value=base_time, max_value=base_time + 7200))
    
    # Randomly choose header case (uppercase or lowercase)
    use_uppercase = draw(st.booleans())
    
    if use_uppercase:
        return {
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }, remaining, reset_time
    else:
        return {
            "x-ratelimit-remaining": str(remaining),
            "x-ratelimit-reset": str(reset_time),
        }, remaining, reset_time


@st.composite
def api_call_sequence(draw):
    """Generate a sequence of API calls with types."""
    length = draw(st.integers(min_value=1, max_value=20))
    return [draw(st.sampled_from(["rest", "graphql"])) for _ in range(length)]


@st.composite
def rate_limit_error_sequence(draw):
    """Generate a sequence of rate limit errors."""
    length = draw(st.integers(min_value=1, max_value=15))
    api_type = draw(st.sampled_from(["rest", "graphql"]))
    status_code = draw(st.sampled_from([403, 429]))
    return [(api_type, status_code) for _ in range(length)]


class TestProperty8RateLimitHeaderParsing:
    """
    Property 8: Rate Limit Header Parsing
    
    For any API response containing X-RateLimit-Remaining and X-RateLimit-Reset headers,
    the Rate_Limiter should correctly extract and store both values.
    
    Validates: Requirements 3.1, 3.2
    """
    
    # Feature: github-api-optimization-query-coverage, Property 8: Rate Limit Header Parsing
    @given(
        headers_data=rate_limit_headers(),
        api_type=st.sampled_from(["rest", "graphql"])
    )
    @settings(max_examples=100)
    def test_header_parsing_correctness(self, headers_data, api_type):
        """
        For any valid rate limit headers, the limiter should correctly parse and store
        both remaining and reset values.
        """
        headers, expected_remaining, expected_reset = headers_data
        limiter = RateLimiter()
        
        # Update from headers
        limiter.update_from_headers(headers, api_type)
        
        # Verify correct extraction
        if api_type == "rest":
            assert limiter.rest_remaining == expected_remaining, \
                f"REST remaining should be {expected_remaining}, got {limiter.rest_remaining}"
            assert limiter.rest_reset_time == expected_reset, \
                f"REST reset time should be {expected_reset}, got {limiter.rest_reset_time}"
        else:
            assert limiter.graphql_remaining == expected_remaining, \
                f"GraphQL remaining should be {expected_remaining}, got {limiter.graphql_remaining}"
            assert limiter.graphql_reset_time == expected_reset, \
                f"GraphQL reset time should be {expected_reset}, got {limiter.graphql_reset_time}"
    
    # Feature: github-api-optimization-query-coverage, Property 8: Rate Limit Header Parsing
    @given(
        remaining=st.integers(min_value=0, max_value=10000),
        reset_time=st.integers(min_value=int(time.time()), max_value=int(time.time()) + 7200),
        api_type=st.sampled_from(["rest", "graphql"])
    )
    @settings(max_examples=100)
    def test_header_parsing_both_values_stored(self, remaining, reset_time, api_type):
        """
        For any API response with rate limit headers, both remaining and reset
        values should be stored (not just one).
        """
        headers = {
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }
        limiter = RateLimiter()
        
        limiter.update_from_headers(headers, api_type)
        
        # Both values should be updated
        actual_remaining = limiter.get_remaining(api_type)
        actual_reset = limiter.rest_reset_time if api_type == "rest" else limiter.graphql_reset_time
        
        assert actual_remaining == remaining, "Remaining value should be stored"
        assert actual_reset == reset_time, "Reset time should be stored"
    
    # Feature: github-api-optimization-query-coverage, Property 8: Rate Limit Header Parsing
    @given(
        headers_sequence=st.lists(rate_limit_headers(), min_size=1, max_size=10),
        api_type=st.sampled_from(["rest", "graphql"])
    )
    @settings(max_examples=100)
    def test_header_parsing_updates_state(self, headers_sequence, api_type):
        """
        For any sequence of header updates, the limiter should always reflect
        the most recent values.
        """
        limiter = RateLimiter()
        
        for headers, expected_remaining, expected_reset in headers_sequence:
            limiter.update_from_headers(headers, api_type)
            
            # Should always reflect the most recent update
            actual_remaining = limiter.get_remaining(api_type)
            actual_reset = limiter.rest_reset_time if api_type == "rest" else limiter.graphql_reset_time
            
            assert actual_remaining == expected_remaining, \
                "Should reflect most recent remaining value"
            assert actual_reset == expected_reset, \
                "Should reflect most recent reset time"


class TestProperty9RateLimitSeparation:
    """
    Property 9: Rate Limit Separation
    
    For any sequence of REST and GraphQL API calls, the rate limit tracking for REST
    should be independent of GraphQL tracking (modifying one should not affect the other).
    
    Validates: Requirements 3.5
    """
    
    # Feature: github-api-optimization-query-coverage, Property 9: Rate Limit Separation
    @given(
        rest_headers=rate_limit_headers(),
        graphql_headers=rate_limit_headers()
    )
    @settings(max_examples=100)
    def test_rest_graphql_independence(self, rest_headers, graphql_headers):
        """
        For any REST and GraphQL header updates, updating one should not affect the other.
        """
        limiter = RateLimiter()
        
        rest_hdrs, rest_remaining, rest_reset = rest_headers
        graphql_hdrs, graphql_remaining, graphql_reset = graphql_headers
        
        # Update REST
        limiter.update_from_headers(rest_hdrs, "rest")
        
        # Update GraphQL
        limiter.update_from_headers(graphql_hdrs, "graphql")
        
        # Verify independence - REST should not be affected by GraphQL update
        assert limiter.rest_remaining == rest_remaining, \
            "REST remaining should not be affected by GraphQL update"
        assert limiter.rest_reset_time == rest_reset, \
            "REST reset time should not be affected by GraphQL update"
        
        # Verify independence - GraphQL should not be affected by REST update
        assert limiter.graphql_remaining == graphql_remaining, \
            "GraphQL remaining should not be affected by REST update"
        assert limiter.graphql_reset_time == graphql_reset, \
            "GraphQL reset time should not be affected by REST update"
    
    # Feature: github-api-optimization-query-coverage, Property 9: Rate Limit Separation
    @given(
        call_sequence=api_call_sequence(),
        headers_list=st.lists(rate_limit_headers(), min_size=1, max_size=20)
    )
    @settings(max_examples=100)
    def test_interleaved_updates_maintain_separation(self, call_sequence, headers_list):
        """
        For any interleaved sequence of REST and GraphQL updates, each API type
        should maintain its own independent state.
        """
        limiter = RateLimiter()
        
        # Track expected state for each API type
        expected_rest_remaining = limiter.rest_remaining
        expected_rest_reset = limiter.rest_reset_time
        expected_graphql_remaining = limiter.graphql_remaining
        expected_graphql_reset = limiter.graphql_reset_time
        
        # Process interleaved updates
        for i, api_type in enumerate(call_sequence):
            if i >= len(headers_list):
                break
            
            headers, remaining, reset_time = headers_list[i]
            limiter.update_from_headers(headers, api_type)
            
            # Update expected state for the API type being updated
            if api_type == "rest":
                expected_rest_remaining = remaining
                expected_rest_reset = reset_time
            else:
                expected_graphql_remaining = remaining
                expected_graphql_reset = reset_time
            
            # Verify both API types maintain correct state
            assert limiter.rest_remaining == expected_rest_remaining, \
                f"REST remaining should be {expected_rest_remaining} after {api_type} update"
            assert limiter.rest_reset_time == expected_rest_reset, \
                f"REST reset should be {expected_rest_reset} after {api_type} update"
            assert limiter.graphql_remaining == expected_graphql_remaining, \
                f"GraphQL remaining should be {expected_graphql_remaining} after {api_type} update"
            assert limiter.graphql_reset_time == expected_graphql_reset, \
                f"GraphQL reset should be {expected_graphql_reset} after {api_type} update"
    
    # Feature: github-api-optimization-query-coverage, Property 9: Rate Limit Separation
    @given(
        rest_remaining=st.integers(min_value=0, max_value=5000),
        graphql_remaining=st.integers(min_value=0, max_value=5000)
    )
    @settings(max_examples=100)
    def test_get_remaining_returns_correct_api_type(self, rest_remaining, graphql_remaining):
        """
        For any REST and GraphQL remaining values, get_remaining should return
        the correct value for the requested API type.
        """
        limiter = RateLimiter()
        limiter.rest_remaining = rest_remaining
        limiter.graphql_remaining = graphql_remaining
        
        # Verify correct values are returned for each API type
        assert limiter.get_remaining("rest") == rest_remaining, \
            "get_remaining('rest') should return REST value"
        assert limiter.get_remaining("graphql") == graphql_remaining, \
            "get_remaining('graphql') should return GraphQL value"
        
        # Verify they are different (unless they happen to be equal)
        if rest_remaining != graphql_remaining:
            assert limiter.get_remaining("rest") != limiter.get_remaining("graphql"), \
                "REST and GraphQL should have independent values"


class TestProperty10ExponentialBackoffBounds:
    """
    Property 10: Exponential Backoff Bounds
    
    For any sequence of rate limit errors, the exponential backoff wait times should
    increase exponentially but never exceed 60 seconds.
    
    Validates: Requirements 3.6
    """
    
    # Feature: github-api-optimization-query-coverage, Property 10: Exponential Backoff Bounds
    @given(
        error_sequence=rate_limit_error_sequence()
    )
    @settings(max_examples=100)
    def test_exponential_backoff_never_exceeds_60_seconds(self, error_sequence):
        """
        For any sequence of rate limit errors, the backoff time should never exceed 60 seconds.
        """
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                for api_type, status_code in error_sequence:
                    limiter.handle_rate_limit_error(api_type, status_code)
        
        # Check all sleep calls
        for call in mock_sleep.call_args_list:
            wait_time = call[0][0]
            assert wait_time <= 60, \
                f"Backoff time {wait_time} exceeds maximum of 60 seconds"
    
    # Feature: github-api-optimization-query-coverage, Property 10: Exponential Backoff Bounds
    @given(
        num_errors=st.integers(min_value=1, max_value=15),
        api_type=st.sampled_from(["rest", "graphql"]),
        status_code=st.sampled_from([403, 429])
    )
    @settings(max_examples=100)
    def test_exponential_backoff_increases_exponentially(self, num_errors, api_type, status_code):
        """
        For any sequence of errors, backoff times should increase exponentially
        (2^n) until hitting the 60-second cap.
        """
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                for _ in range(num_errors):
                    limiter.handle_rate_limit_error(api_type, status_code)
        
        # Verify exponential growth pattern
        wait_times = [call[0][0] for call in mock_sleep.call_args_list]
        
        for i, wait_time in enumerate(wait_times):
            attempt = i + 1
            expected_uncapped = 2 ** attempt
            expected_capped = min(expected_uncapped, 60)
            
            assert wait_time == expected_capped, \
                f"Attempt {attempt}: expected {expected_capped}s, got {wait_time}s"
    
    # Feature: github-api-optimization-query-coverage, Property 10: Exponential Backoff Bounds
    @given(
        rest_errors=st.integers(min_value=1, max_value=10),
        graphql_errors=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=100)
    def test_exponential_backoff_separate_tracking(self, rest_errors, graphql_errors):
        """
        For any sequence of REST and GraphQL errors, backoff should be tracked
        separately for each API type.
        """
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                # Generate REST errors
                for _ in range(rest_errors):
                    limiter.handle_rate_limit_error("rest", 403)
                
                rest_wait_times = [call[0][0] for call in mock_sleep.call_args_list]
                mock_sleep.reset_mock()
                
                # Generate GraphQL errors (should start from attempt 1 again)
                for _ in range(graphql_errors):
                    limiter.handle_rate_limit_error("graphql", 429)
                
                graphql_wait_times = [call[0][0] for call in mock_sleep.call_args_list]
        
        # Verify REST backoff pattern
        for i, wait_time in enumerate(rest_wait_times):
            expected = min(2 ** (i + 1), 60)
            assert wait_time == expected, \
                f"REST attempt {i+1}: expected {expected}s, got {wait_time}s"
        
        # Verify GraphQL backoff pattern (should start from 2^1 again)
        for i, wait_time in enumerate(graphql_wait_times):
            expected = min(2 ** (i + 1), 60)
            assert wait_time == expected, \
                f"GraphQL attempt {i+1}: expected {expected}s, got {wait_time}s"
    
    # Feature: github-api-optimization-query-coverage, Property 10: Exponential Backoff Bounds
    @given(
        num_errors=st.integers(min_value=1, max_value=20),
        api_type=st.sampled_from(["rest", "graphql"])
    )
    @settings(max_examples=100)
    def test_exponential_backoff_bounds_are_tight(self, num_errors, api_type):
        """
        For any sequence of errors, once backoff reaches 60 seconds, it should
        stay at 60 seconds (not go lower).
        """
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                for _ in range(num_errors):
                    limiter.handle_rate_limit_error(api_type, 403)
        
        wait_times = [call[0][0] for call in mock_sleep.call_args_list]
        
        # Find when we hit 60 seconds
        hit_max = False
        for wait_time in wait_times:
            if wait_time == 60:
                hit_max = True
            
            # Once we hit max, all subsequent waits should be 60
            if hit_max:
                assert wait_time == 60, \
                    "After hitting 60s cap, all subsequent waits should be 60s"
    
    # Feature: github-api-optimization-query-coverage, Property 10: Exponential Backoff Bounds
    @given(
        status_code=st.integers(min_value=400, max_value=599).filter(lambda x: x not in [403, 429])
    )
    @settings(max_examples=100)
    def test_exponential_backoff_only_for_rate_limit_errors(self, status_code):
        """
        For any non-rate-limit error status code, no backoff should occur.
        """
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            limiter.handle_rate_limit_error("rest", status_code)
            limiter.handle_rate_limit_error("graphql", status_code)
        
        # Should not sleep for non-rate-limit errors
        mock_sleep.assert_not_called()
