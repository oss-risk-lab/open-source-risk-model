"""
Unit tests for RateLimiter.

Tests rate limit tracking, warning thresholds, pause behavior, and exponential backoff.
"""

import time
from unittest.mock import patch

import pytest

from src.open_source_risk_model.ingestion.rate_limiter import RateLimiter


class TestRateLimiterBasics:
    """Test basic rate limiter functionality."""

    def test_initialization_with_defaults(self):
        """Test rate limiter initializes with default values."""
        limiter = RateLimiter()
        
        assert limiter.rest_remaining == 5000
        assert limiter.graphql_remaining == 5000
        assert limiter.rest_reset_time == 0
        assert limiter.graphql_reset_time == 0
        assert limiter.warning_threshold == 100

    def test_initialization_with_config(self):
        """Test rate limiter initializes with custom config."""
        config = {
            "rate_limiting": {
                "warning_threshold": 50,
                "rest_limit": 4000,
                "graphql_limit": 3000,
            }
        }
        limiter = RateLimiter(config)
        
        assert limiter.rest_remaining == 4000
        assert limiter.graphql_remaining == 3000
        assert limiter.warning_threshold == 50

    def test_get_remaining_rest(self):
        """Test getting remaining quota for REST API."""
        limiter = RateLimiter()
        limiter.rest_remaining = 1234
        
        assert limiter.get_remaining("rest") == 1234

    def test_get_remaining_graphql(self):
        """Test getting remaining quota for GraphQL API."""
        limiter = RateLimiter()
        limiter.graphql_remaining = 4567
        
        assert limiter.get_remaining("graphql") == 4567


class TestHeaderParsing:
    """Test parsing rate limit headers."""

    def test_update_from_headers_rest(self):
        """Test updating REST rate limit from headers."""
        limiter = RateLimiter()
        headers = {
            "X-RateLimit-Remaining": "4500",
            "X-RateLimit-Reset": "1234567890",
        }
        
        limiter.update_from_headers(headers, "rest")
        
        assert limiter.rest_remaining == 4500
        assert limiter.rest_reset_time == 1234567890

    def test_update_from_headers_graphql(self):
        """Test updating GraphQL rate limit from headers."""
        limiter = RateLimiter()
        headers = {
            "X-RateLimit-Remaining": "3500",
            "X-RateLimit-Reset": "9876543210",
        }
        
        limiter.update_from_headers(headers, "graphql")
        
        assert limiter.graphql_remaining == 3500
        assert limiter.graphql_reset_time == 9876543210

    def test_update_from_headers_lowercase(self):
        """Test parsing headers with lowercase keys."""
        limiter = RateLimiter()
        headers = {
            "x-ratelimit-remaining": "2500",
            "x-ratelimit-reset": "1111111111",
        }
        
        limiter.update_from_headers(headers, "rest")
        
        assert limiter.rest_remaining == 2500
        assert limiter.rest_reset_time == 1111111111

    def test_update_from_headers_invalid_remaining(self):
        """Test handling invalid remaining header value."""
        limiter = RateLimiter()
        limiter.rest_remaining = 5000
        headers = {
            "X-RateLimit-Remaining": "invalid",
            "X-RateLimit-Reset": "1234567890",
        }
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger") as mock_logger:
            limiter.update_from_headers(headers, "rest")
            mock_logger.warning.assert_called_once()
        
        # Should not update remaining on parse error
        assert limiter.rest_remaining == 5000
        assert limiter.rest_reset_time == 1234567890

    def test_update_from_headers_invalid_reset(self):
        """Test handling invalid reset header value."""
        limiter = RateLimiter()
        limiter.rest_reset_time = 0
        headers = {
            "X-RateLimit-Remaining": "4500",
            "X-RateLimit-Reset": "not-a-timestamp",
        }
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger") as mock_logger:
            limiter.update_from_headers(headers, "rest")
            mock_logger.warning.assert_called_once()
        
        # Should update remaining but not reset time
        assert limiter.rest_remaining == 4500
        assert limiter.rest_reset_time == 0

    def test_update_from_headers_missing_headers(self):
        """Test handling missing rate limit headers."""
        limiter = RateLimiter()
        limiter.rest_remaining = 5000
        limiter.rest_reset_time = 0
        headers = {}
        
        limiter.update_from_headers(headers, "rest")
        
        # Should not change state
        assert limiter.rest_remaining == 5000
        assert limiter.rest_reset_time == 0

    def test_update_from_headers_resets_backoff(self):
        """Test that successful header update resets backoff attempts."""
        limiter = RateLimiter()
        limiter.backoff_attempts["rest"] = 3
        headers = {
            "X-RateLimit-Remaining": "4500",
            "X-RateLimit-Reset": "1234567890",
        }
        
        limiter.update_from_headers(headers, "rest")
        
        assert limiter.backoff_attempts["rest"] == 0


class TestWarningThreshold:
    """Test warning threshold behavior."""

    def test_check_and_wait_logs_warning_at_threshold(self):
        """Test that warning is logged when remaining falls below threshold."""
        config = {"rate_limiting": {"warning_threshold": 100}}
        limiter = RateLimiter(config)
        limiter.rest_remaining = 99
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger") as mock_logger:
            limiter.check_and_wait("rest")
            mock_logger.warning.assert_called_once()
            assert "rate limit low" in mock_logger.warning.call_args[0][0].lower()

    def test_check_and_wait_no_warning_above_threshold(self):
        """Test that no warning is logged when remaining is above threshold."""
        config = {"rate_limiting": {"warning_threshold": 100}}
        limiter = RateLimiter(config)
        limiter.rest_remaining = 101
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger") as mock_logger:
            limiter.check_and_wait("rest")
            mock_logger.warning.assert_not_called()

    def test_check_and_wait_no_warning_at_zero(self):
        """Test that warning threshold check doesn't trigger at zero."""
        config = {"rate_limiting": {"warning_threshold": 100}}
        limiter = RateLimiter(config)
        limiter.rest_remaining = 0
        limiter.rest_reset_time = 0
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger") as mock_logger:
            limiter.check_and_wait("rest")
            # Should not log the "low" warning, only exhausted warning if applicable
            warning_calls = [call for call in mock_logger.warning.call_args_list 
                           if "rate limit low" in str(call).lower()]
            assert len(warning_calls) == 0


class TestPauseBehavior:
    """Test pause behavior when quota exhausted."""

    def test_check_and_wait_pauses_when_exhausted(self):
        """Test that check_and_wait pauses when quota is exhausted."""
        limiter = RateLimiter()
        limiter.rest_remaining = 0
        limiter.rest_reset_time = time.time() + 2  # Reset in 2 seconds
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger") as mock_logger:
            with patch("time.sleep") as mock_sleep:
                limiter.check_and_wait("rest")
                
                # Should log warning
                mock_logger.warning.assert_called_once()
                assert "exhausted" in mock_logger.warning.call_args[0][0].lower()
                
                # Should sleep for approximately 2 seconds
                mock_sleep.assert_called_once()
                sleep_time = mock_sleep.call_args[0][0]
                assert 1.5 < sleep_time < 2.5

    def test_check_and_wait_resets_quota_after_pause(self):
        """Test that quota is reset after waiting."""
        config = {"rate_limiting": {"rest_limit": 5000}}
        limiter = RateLimiter(config)
        limiter.rest_remaining = 0
        limiter.rest_reset_time = time.time() + 0.1  # Reset in 0.1 seconds
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
            limiter.check_and_wait("rest")
        
        # Should reset to configured limit
        assert limiter.rest_remaining == 5000

    def test_check_and_wait_no_pause_if_reset_time_passed(self):
        """Test that no pause occurs if reset time has already passed."""
        limiter = RateLimiter()
        limiter.rest_remaining = 0
        limiter.rest_reset_time = time.time() - 10  # Reset time in the past
        
        with patch("time.sleep") as mock_sleep:
            limiter.check_and_wait("rest")
            mock_sleep.assert_not_called()

    def test_check_and_wait_no_pause_if_no_reset_time(self):
        """Test that no pause occurs if reset time is not set."""
        limiter = RateLimiter()
        limiter.rest_remaining = 0
        limiter.rest_reset_time = 0
        
        with patch("time.sleep") as mock_sleep:
            limiter.check_and_wait("rest")
            mock_sleep.assert_not_called()


class TestExponentialBackoff:
    """Test exponential backoff for 403/429 errors."""

    def test_handle_rate_limit_error_403(self):
        """Test exponential backoff for 403 error."""
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger") as mock_logger:
                limiter.handle_rate_limit_error("rest", 403)
                
                # Should sleep for 2^1 = 2 seconds on first attempt
                mock_sleep.assert_called_once_with(2)
                mock_logger.warning.assert_called_once()
                assert "403" in mock_logger.warning.call_args[0][0]

    def test_handle_rate_limit_error_429(self):
        """Test exponential backoff for 429 error."""
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                limiter.handle_rate_limit_error("graphql", 429)
                
                # Should sleep for 2^1 = 2 seconds on first attempt
                mock_sleep.assert_called_once_with(2)

    def test_handle_rate_limit_error_exponential_increase(self):
        """Test that backoff time increases exponentially."""
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                # First attempt: 2^1 = 2 seconds
                limiter.handle_rate_limit_error("rest", 403)
                assert mock_sleep.call_args_list[0][0][0] == 2
                
                # Second attempt: 2^2 = 4 seconds
                limiter.handle_rate_limit_error("rest", 403)
                assert mock_sleep.call_args_list[1][0][0] == 4
                
                # Third attempt: 2^3 = 8 seconds
                limiter.handle_rate_limit_error("rest", 403)
                assert mock_sleep.call_args_list[2][0][0] == 8

    def test_handle_rate_limit_error_max_60_seconds(self):
        """Test that backoff time is capped at 60 seconds."""
        limiter = RateLimiter()
        limiter.backoff_attempts["rest"] = 10  # Would be 2^10 = 1024 seconds
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                limiter.handle_rate_limit_error("rest", 403)
                
                # Should be capped at 60 seconds
                assert mock_sleep.call_args[0][0] == 60

    def test_handle_rate_limit_error_separate_tracking(self):
        """Test that REST and GraphQL backoff are tracked separately."""
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
                # REST first attempt: 2 seconds
                limiter.handle_rate_limit_error("rest", 403)
                assert mock_sleep.call_args_list[0][0][0] == 2
                
                # GraphQL first attempt: also 2 seconds (separate tracking)
                limiter.handle_rate_limit_error("graphql", 429)
                assert mock_sleep.call_args_list[1][0][0] == 2
                
                # REST second attempt: 4 seconds
                limiter.handle_rate_limit_error("rest", 403)
                assert mock_sleep.call_args_list[2][0][0] == 4

    def test_handle_rate_limit_error_ignores_other_status_codes(self):
        """Test that non-rate-limit errors are ignored."""
        limiter = RateLimiter()
        
        with patch("time.sleep") as mock_sleep:
            limiter.handle_rate_limit_error("rest", 404)
            limiter.handle_rate_limit_error("rest", 500)
            
            mock_sleep.assert_not_called()


class TestSeparateTracking:
    """Test that REST and GraphQL are tracked separately."""

    def test_rest_and_graphql_independent(self):
        """Test that REST and GraphQL rate limits are independent."""
        limiter = RateLimiter()
        
        # Update REST
        limiter.update_from_headers(
            {"X-RateLimit-Remaining": "1000", "X-RateLimit-Reset": "1111111111"},
            "rest"
        )
        
        # Update GraphQL
        limiter.update_from_headers(
            {"X-RateLimit-Remaining": "2000", "X-RateLimit-Reset": "2222222222"},
            "graphql"
        )
        
        # Verify independence
        assert limiter.rest_remaining == 1000
        assert limiter.rest_reset_time == 1111111111
        assert limiter.graphql_remaining == 2000
        assert limiter.graphql_reset_time == 2222222222

    def test_check_and_wait_rest_does_not_affect_graphql(self):
        """Test that checking REST does not affect GraphQL."""
        limiter = RateLimiter()
        limiter.rest_remaining = 50
        limiter.graphql_remaining = 5000
        
        with patch("src.open_source_risk_model.ingestion.rate_limiter.logger"):
            limiter.check_and_wait("rest")
        
        # GraphQL should be unchanged
        assert limiter.graphql_remaining == 5000


class TestInputValidation:
    """Test input validation."""

    def test_check_and_wait_invalid_api_type(self):
        """Test that invalid api_type raises ValueError."""
        limiter = RateLimiter()
        
        with pytest.raises(ValueError, match="Invalid api_type"):
            limiter.check_and_wait("invalid")

    def test_update_from_headers_invalid_api_type(self):
        """Test that invalid api_type raises ValueError."""
        limiter = RateLimiter()
        
        with pytest.raises(ValueError, match="Invalid api_type"):
            limiter.update_from_headers({}, "invalid")

    def test_handle_rate_limit_error_invalid_api_type(self):
        """Test that invalid api_type raises ValueError."""
        limiter = RateLimiter()
        
        with pytest.raises(ValueError, match="Invalid api_type"):
            limiter.handle_rate_limit_error("invalid", 403)
