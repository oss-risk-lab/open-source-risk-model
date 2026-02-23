"""
Rate limiting and budget tracking for dependency ingestion.

Protects against GitHub API rate limit exhaustion.
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class DependencyIngestionConfig:
    """Configuration for dependency ingestion with rate limit protection."""
    
    # Discovery limits
    max_manifests_per_repo: int = 10
    max_manifest_depth: int = 3
    
    # Resolution limits
    max_packages_per_repo: int = 100
    max_registry_calls_per_run: int = 50
    
    # Caching
    manifest_cache_ttl_hours: int = 24
    package_mapping_cache_ttl_hours: int = 168  # 1 week
    
    # Timeouts
    github_api_timeout_seconds: int = 10
    registry_api_timeout_seconds: int = 5
    
    # Retry policy
    max_retries: int = 3
    retry_backoff_seconds: int = 2


class RateLimitTracker:
    """Tracks API usage to prevent rate limit exhaustion."""
    
    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize rate limit tracker.
        
        Args:
            github_token: GitHub API token for authentication
        """
        self.github_token = github_token
        self.github_calls = 0
        self.registry_calls = 0
        self.start_time = time.time()
    
    def check_github_budget(self, config: DependencyIngestionConfig) -> bool:
        """
        Check if we have GitHub API budget remaining.
        
        Args:
            config: Ingestion configuration
        
        Returns:
            True if budget available, False otherwise
        """
        remaining = self._get_github_rate_limit_remaining()
        
        # Reserve 1000 calls for other operations
        has_budget = remaining > 1000
        
        if not has_budget:
            logger.warning(f"GitHub API budget low: {remaining} calls remaining")
        
        return has_budget
    
    def check_registry_budget(self, config: DependencyIngestionConfig) -> bool:
        """
        Check if we have registry API budget remaining.
        
        Args:
            config: Ingestion configuration
        
        Returns:
            True if budget available, False otherwise
        """
        has_budget = self.registry_calls < config.max_registry_calls_per_run
        
        if not has_budget:
            logger.warning(
                f"Registry API budget exhausted: "
                f"{self.registry_calls}/{config.max_registry_calls_per_run}"
            )
        
        return has_budget
    
    def record_github_call(self):
        """Record a GitHub API call."""
        self.github_calls += 1
    
    def record_registry_call(self):
        """Record a registry API call."""
        self.registry_calls += 1
    
    def get_stats(self) -> dict:
        """Get usage statistics."""
        elapsed = time.time() - self.start_time
        
        return {
            'github_calls': self.github_calls,
            'registry_calls': self.registry_calls,
            'elapsed_seconds': elapsed,
            'github_calls_per_minute': (self.github_calls / elapsed * 60) if elapsed > 0 else 0,
        }
    
    def _get_github_rate_limit_remaining(self) -> int:
        """Get remaining GitHub API calls."""
        try:
            headers = {}
            if self.github_token:
                headers['Authorization'] = f'Bearer {self.github_token}'
            
            response = requests.get(
                'https://api.github.com/rate_limit',
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                remaining = data['rate']['remaining']
                reset_time = data['rate']['reset']
                
                logger.debug(
                    f"GitHub rate limit: {remaining} remaining, "
                    f"resets at {time.ctime(reset_time)}"
                )
                
                return remaining
            
            logger.warning(f"Failed to get rate limit: {response.status_code}")
            return 0
        
        except Exception as e:
            logger.error(f"Error getting rate limit: {e}")
            return 0
