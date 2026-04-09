"""GitHub API client with rate limiting and exponential backoff."""

import time
import random
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """GitHub API error."""
    pass


class RateLimitError(GitHubAPIError):
    """Rate limit exceeded error."""
    pass


class GitHubClient:
    """GitHub API client with rate limiting and exponential backoff."""
    
    def __init__(self, token: str, base_delay: float = 60.0, max_retries: int = 3):
        """
        Initialize GitHub API client.
        
        Args:
            token: GitHub personal access token
            base_delay: Base delay in seconds for exponential backoff
            max_retries: Maximum number of retry attempts
        """
        self.token = token
        self.base_delay = base_delay
        self.max_retries = max_retries
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        })
    
    def calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.
        
        Args:
            attempt: Retry attempt number (0-indexed)
        
        Returns:
            Delay in seconds with 0-10% jitter
        """
        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, 0.1 * delay)
        return delay + jitter
    
    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic.
        
        Args:
            url: API endpoint URL
            params: Query parameters
        
        Returns:
            JSON response
        
        Raises:
            GitHubAPIError: On API errors
            RateLimitError: On rate limit exceeded
        """
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, params=params)
                
                # Check for rate limiting
                if response.status_code in (403, 429):
                    if attempt < self.max_retries - 1:
                        delay = self.calculate_backoff_delay(attempt)
                        logger.warning(
                            f"Rate limit hit, backing off {delay:.1f}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        raise RateLimitError(f"Rate limit exceeded after {self.max_retries} attempts")
                
                # Check for other errors
                if response.status_code == 404:
                    raise GitHubAPIError(f"Resource not found: {url}")
                
                if response.status_code == 401:
                    raise GitHubAPIError("Authentication failed - check GitHub token")
                
                response.raise_for_status()
                return response.json()
            
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    delay = self.calculate_backoff_delay(attempt)
                    logger.warning(f"Request timeout, retrying in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                else:
                    raise GitHubAPIError(f"Request timeout after {self.max_retries} attempts")
            
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    delay = self.calculate_backoff_delay(attempt)
                    logger.warning(f"Request failed: {e}, retrying in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                else:
                    raise GitHubAPIError(f"Request failed after {self.max_retries} attempts: {e}")
        
        raise GitHubAPIError("Unexpected error in request retry loop")
    
    def search_repositories(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 100,
        max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Search repositories on GitHub.
        
        Args:
            query: Search query (e.g., "stars:>1000 language:python")
            sort: Sort field (stars, forks, updated)
            order: Sort order (asc, desc)
            per_page: Results per page (max 100)
            max_results: Maximum total results to fetch
        
        Returns:
            List of repository dictionaries
        """
        repos = []
        page = 1
        
        while len(repos) < max_results:
            url = f"{self.base_url}/search/repositories"
            params = {
                "q": query,
                "sort": sort,
                "order": order,
                "per_page": min(per_page, max_results - len(repos)),
                "page": page
            }
            
            logger.info(f"Searching repositories: page {page}")
            data = self._make_request(url, params)
            
            items = data.get("items", [])
            if not items:
                break
            
            repos.extend(items)
            page += 1
            
            # GitHub search API limits to 1000 results
            if len(repos) >= 1000:
                break
        
        return repos[:max_results]
    
    def get_repository(self, full_name: str) -> Dict[str, Any]:
        """
        Get repository details.
        
        Args:
            full_name: Repository full name (owner/repo)
        
        Returns:
            Repository dictionary
        """
        url = f"{self.base_url}/repos/{full_name}"
        return self._make_request(url)
    
    def get_repository_contents(
        self,
        full_name: str,
        path: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Get repository contents at path.
        
        Args:
            full_name: Repository full name (owner/repo)
            path: Path within repository (empty for root)
        
        Returns:
            List of file/directory dictionaries
        """
        url = f"{self.base_url}/repos/{full_name}/contents/{path}"
        try:
            result = self._make_request(url)
            # Handle single file vs directory
            if isinstance(result, list):
                return result
            else:
                return [result]
        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                return []
            raise
    
    def search_code(
        self,
        full_name: str,
        filename: str
    ) -> bool:
        """
        Search for a file in repository.
        
        Args:
            full_name: Repository full name (owner/repo)
            filename: Filename to search for
        
        Returns:
            True if file exists, False otherwise
        """
        query = f"repo:{full_name} filename:{filename}"
        url = f"{self.base_url}/search/code"
        params = {"q": query, "per_page": 1}
        
        try:
            data = self._make_request(url, params)
            return data.get("total_count", 0) > 0
        except GitHubAPIError:
            return False
