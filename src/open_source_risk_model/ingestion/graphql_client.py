"""
GraphQL client for GitHub API v4.

Executes GraphQL queries with retry logic, error handling, and adaptive batching.
"""

import json
import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class GraphQLClient:
    """Client for executing GraphQL queries against GitHub API v4."""

    def __init__(self, token: str, config: Optional[dict] = None):
        """
        Initialize GraphQL client.

        Args:
            token: GitHub API token
            config: Optional configuration dict
        """
        self.token = token
        self.config = config or {}
        self.endpoint = "https://api.github.com/graphql"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        
        # Track query costs for adaptive batching
        self.last_query_cost: Optional[int] = None

    def execute_query(
        self, query: str, variables: dict[str, Any], timeout: int = 30
    ) -> dict[str, Any]:
        """
        Execute GraphQL query with retry logic.

        Args:
            query: GraphQL query string
            variables: Query variables
            timeout: Request timeout in seconds

        Returns:
            Query response data

        Raises:
            Exception: If query fails after retries
        """
        retry_attempts = self.config.get("retry_attempts", 3)
        retry_backoff_base = self.config.get("retry_backoff_base", 2)
        retry_max_wait = self.config.get("retry_max_wait", 60)
        
        last_error = None
        
        for attempt in range(retry_attempts):
            try:
                # Prepare request payload
                payload = {
                    "query": query,
                    "variables": variables
                }
                
                # Execute request
                response = self.session.post(
                    self.endpoint,
                    json=payload,
                    timeout=timeout
                )
                
                # Track query cost from response headers
                self.track_query_cost(response)
                
                # Check for HTTP errors
                if response.status_code == 403 or response.status_code == 429:
                    # Rate limit error - use exponential backoff
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    logger.warning(
                        f"Rate limit error (HTTP {response.status_code}), "
                        f"waiting {wait_time}s before retry {attempt + 1}/{retry_attempts}"
                    )
                    time.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                
                # Parse response
                response_data = response.json()
                
                # Check for GraphQL errors
                if "errors" in response_data:
                    errors = response_data["errors"]
                    error_messages = self._parse_graphql_errors(errors)
                    
                    # If this is the last attempt, raise the error
                    if attempt == retry_attempts - 1:
                        raise Exception(f"GraphQL errors: {error_messages}")
                    
                    # Otherwise, log and retry
                    logger.warning(
                        f"GraphQL errors on attempt {attempt + 1}/{retry_attempts}: {error_messages}"
                    )
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    time.sleep(wait_time)
                    continue
                
                # Success - return data
                return response_data
                
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(
                    f"Request timeout on attempt {attempt + 1}/{retry_attempts}: {e}"
                )
                if attempt < retry_attempts - 1:
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    time.sleep(wait_time)
                    
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(
                    f"Request error on attempt {attempt + 1}/{retry_attempts}: {e}"
                )
                if attempt < retry_attempts - 1:
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    time.sleep(wait_time)
                    
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Unexpected error on attempt {attempt + 1}/{retry_attempts}: {e}"
                )
                if attempt < retry_attempts - 1:
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    time.sleep(wait_time)
        
        # All retries exhausted
        raise Exception(f"GraphQL query failed after {retry_attempts} attempts: {last_error}")

    def _parse_graphql_errors(self, errors: list[dict[str, Any]]) -> str:
        """
        Parse GraphQL errors and extract failing repository identifiers.

        Args:
            errors: List of GraphQL error objects

        Returns:
            Formatted error message with repository identifiers
        """
        error_messages = []
        
        for error in errors:
            message = error.get("message", "Unknown error")
            
            # Try to extract repository identifier from error path
            path = error.get("path", [])
            repo_identifier = None
            
            # Path typically looks like: ["repository_alias", "field"]
            # The alias often contains the repo identifier
            if path and len(path) > 0:
                alias = path[0]
                # Try to extract repo from alias (e.g., "repo_owner_name" -> "owner/name")
                if isinstance(alias, str) and alias.startswith("repo_"):
                    repo_identifier = alias[5:].replace("_", "/", 1)
            
            if repo_identifier:
                error_messages.append(f"{repo_identifier}: {message}")
            else:
                error_messages.append(message)
        
        return "; ".join(error_messages)

    def track_query_cost(self, response: requests.Response) -> None:
        """
        Track query cost from response headers for adaptive batching.

        Args:
            response: HTTP response object with headers
        """
        # GitHub GraphQL API returns query cost in X-RateLimit-Cost header
        cost_header = response.headers.get("X-RateLimit-Cost")
        
        if cost_header:
            try:
                cost = int(cost_header)
                self.last_query_cost = cost
                logger.debug(f"Query cost: {cost}")
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse query cost from header: {cost_header}")
        else:
            # No cost header - might be an error response
            self.last_query_cost = None

    def batch_repo_query(
        self, repo_identifiers: list[str], batch_size: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """
        Batch query multiple repositories using aliases with adaptive sizing.

        Args:
            repo_identifiers: List of repo identifiers (owner/repo format)
            batch_size: Optional batch size override

        Returns:
            List of repository data dicts
        """
        # TODO: Implement in Task 5.1
        raise NotImplementedError("Batch query not yet implemented")
