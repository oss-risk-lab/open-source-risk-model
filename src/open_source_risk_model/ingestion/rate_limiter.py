"""
Rate limiter for GitHub API.

Monitors and enforces rate limits with separate tracking for REST and GraphQL APIs.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for GitHub API with separate REST/GraphQL tracking."""

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize rate limiter.

        Args:
            config: Optional configuration dict with rate_limiting settings
        """
        self.config = config or {}
        
        # Get configuration values
        rate_config = self.config.get("rate_limiting", {})
        self.warning_threshold = rate_config.get("warning_threshold", 100)
        
        # Initialize rate limit state for REST API
        self.rest_remaining = rate_config.get("rest_limit", 5000)
        self.rest_reset_time = 0
        
        # Initialize rate limit state for GraphQL API
        self.graphql_remaining = rate_config.get("graphql_limit", 5000)
        self.graphql_reset_time = 0
        
        # Track backoff state for 403/429 errors
        self.backoff_attempts = {"rest": 0, "graphql": 0}

    def check_and_wait(self, api_type: str) -> None:
        """
        Check rate limit and wait if necessary.

        Args:
            api_type: "rest" or "graphql"
        """
        if api_type not in ["rest", "graphql"]:
            raise ValueError(f"Invalid api_type: {api_type}. Must be 'rest' or 'graphql'")
        
        remaining = self.get_remaining(api_type)
        reset_time = self.rest_reset_time if api_type == "rest" else self.graphql_reset_time
        
        # Log warning if remaining quota is below threshold
        if remaining < self.warning_threshold and remaining > 0:
            logger.warning(
                f"GitHub {api_type.upper()} API rate limit low: {remaining} requests remaining"
            )
        
        # If quota exhausted, wait until reset time
        if remaining <= 0 and reset_time > 0:
            current_time = time.time()
            wait_time = reset_time - current_time
            
            if wait_time > 0:
                logger.warning(
                    f"GitHub {api_type.upper()} API rate limit exhausted. "
                    f"Waiting {wait_time:.0f} seconds until reset."
                )
                time.sleep(wait_time)
                
                # Reset the remaining count after waiting
                if api_type == "rest":
                    self.rest_remaining = self.config.get("rate_limiting", {}).get("rest_limit", 5000)
                else:
                    self.graphql_remaining = self.config.get("rate_limiting", {}).get("graphql_limit", 5000)

    def update_from_headers(self, headers: dict[str, str], api_type: str) -> None:
        """
        Update rate limit state from response headers.

        Args:
            headers: Response headers from GitHub API
            api_type: "rest" or "graphql"
        """
        if api_type not in ["rest", "graphql"]:
            raise ValueError(f"Invalid api_type: {api_type}. Must be 'rest' or 'graphql'")
        
        # Parse X-RateLimit-Remaining header
        remaining_header = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        if remaining_header is not None:
            try:
                remaining = int(remaining_header)
                if api_type == "rest":
                    self.rest_remaining = remaining
                else:
                    self.graphql_remaining = remaining
            except ValueError:
                logger.warning(f"Failed to parse X-RateLimit-Remaining header: {remaining_header}")
        
        # Parse X-RateLimit-Reset header (Unix timestamp)
        reset_header = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
        if reset_header is not None:
            try:
                reset_time = int(reset_header)
                if api_type == "rest":
                    self.rest_reset_time = reset_time
                else:
                    self.graphql_reset_time = reset_time
            except ValueError:
                logger.warning(f"Failed to parse X-RateLimit-Reset header: {reset_header}")
        
        # Reset backoff attempts on successful request
        self.backoff_attempts[api_type] = 0

    def get_remaining(self, api_type: str) -> int:
        """
        Get remaining quota for API type.

        Args:
            api_type: "rest" or "graphql"

        Returns:
            Remaining requests
        """
        if api_type == "rest":
            return self.rest_remaining
        return self.graphql_remaining

    def handle_rate_limit_error(self, api_type: str, status_code: int) -> None:
        """
        Handle rate limit errors (403/429) with exponential backoff.

        Args:
            api_type: "rest" or "graphql"
            status_code: HTTP status code (403 or 429)
        """
        if api_type not in ["rest", "graphql"]:
            raise ValueError(f"Invalid api_type: {api_type}. Must be 'rest' or 'graphql'")
        
        if status_code not in [403, 429]:
            return
        
        # Increment backoff attempts
        self.backoff_attempts[api_type] += 1
        attempt = self.backoff_attempts[api_type]
        
        # Calculate exponential backoff with max 60 seconds
        wait_time = min(2 ** attempt, 60)
        
        logger.warning(
            f"GitHub {api_type.upper()} API rate limit error (HTTP {status_code}). "
            f"Backing off for {wait_time} seconds (attempt {attempt})"
        )
        
        time.sleep(wait_time)
