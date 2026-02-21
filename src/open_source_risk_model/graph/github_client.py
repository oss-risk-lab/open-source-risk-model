"""
GitHub API client for graph data fetching.

Provides methods to fetch releases, contributors, and other GitHub data
with caching support.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ..utils.logging_utils import StructuredLogger, log_event, LogEvent

# Set up structured logger
logger = StructuredLogger(__name__)

GITHUB_API_URL = "https://api.github.com"


class GitHubClient:
    """
    GitHub API client with caching support.
    
    Handles authentication, rate limiting, and caching of GitHub API responses.
    """
    
    def __init__(self, cache_dir: Optional[str | Path] = None, cache_ttl_hours: int = 1):
        """
        Initialize GitHub client.
        
        Args:
            cache_dir: Directory for caching API responses (default: data/github_cache)
            cache_ttl_hours: Cache time-to-live in hours
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/github_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create authenticated requests session."""
        token = os.environ.get("GITHUB_TOKEN")
        session = requests.Session()
        session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if token:
            session.headers["Authorization"] = f"Bearer {token}"
        return session
    
    def _cache_path(self, cache_key: str) -> Path:
        """Get cache file path for a given key."""
        safe_key = cache_key.replace("/", "__").replace(":", "_")
        return self.cache_dir / f"{safe_key}.json"
    
    def _get_cached(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached data if it exists and is fresh.
        
        Args:
            cache_key: Cache key identifier
        
        Returns:
            Cached data if fresh, None otherwise
        """
        cache_path = self._cache_path(cache_key)
        
        if not cache_path.exists():
            return None
        
        try:
            cached = json.loads(cache_path.read_text())
            cached_at = datetime.fromisoformat(cached["cached_at"])
            
            # Check if cache is still fresh
            if datetime.now(timezone.utc) - cached_at <= self.cache_ttl:
                logger.debug(f"Cache hit for {cache_key}")
                return cached["data"]
            else:
                logger.debug(f"Cache expired for {cache_key}")
                return None
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Invalid cache file for {cache_key}: {e}")
            return None
    
    def _set_cached(self, cache_key: str, data: Any) -> None:
        """
        Store data in cache.
        
        Args:
            cache_key: Cache key identifier
            data: Data to cache
        """
        cache_path = self._cache_path(cache_key)
        
        payload = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "cache_key": cache_key,
            "data": data,
        }
        
        try:
            cache_path.write_text(json.dumps(payload, indent=2))
            logger.debug(f"Cached data for {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache data for {cache_key}: {e}")
    
    def fetch_releases(
        self, 
        owner: str, 
        repo: str, 
        max_count: int = 10,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch releases from GitHub API with caching.
        
        Args:
            owner: Repository owner
            repo: Repository name
            max_count: Maximum number of releases to fetch
            force_refresh: Force refresh from API, bypassing cache
        
        Returns:
            List of release dictionaries with keys:
            - tag_name: Release tag (e.g., "v1.2.3")
            - name: Release name
            - published_at: ISO timestamp
            - prerelease: Boolean flag
            - draft: Boolean flag
        
        Raises:
            requests.RequestException: On API errors
        """
        cache_key = f"releases:{owner}/{repo}"
        
        # Check cache first unless force refresh
        if not force_refresh:
            cached = self._get_cached(cache_key)
            if cached is not None:
                log_event(logger, LogEvent.CACHE_HIT, cache_key=cache_key)
                return cached[:max_count]
            else:
                log_event(logger, LogEvent.CACHE_MISS, cache_key=cache_key)
        
        # Fetch from API
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases"
        params = {"per_page": max_count}
        
        try:
            logger.info(f"Fetching releases for {owner}/{repo} from GitHub API")
            
            # Log API call start
            start_time = time.time()
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_STARTED,
                api="github",
                endpoint="releases",
                repo=f"{owner}/{repo}",
            )
            
            response = self.session.get(url, params=params, timeout=20)
            response.raise_for_status()
            
            # Log API call completion with timing
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_COMPLETED,
                api="github",
                endpoint="releases",
                repo=f"{owner}/{repo}",
                elapsed_ms=elapsed_ms,
            )
            
            releases = response.json()
            
            # Filter out drafts
            releases = [r for r in releases if not r.get("draft", False)]
            
            # Cache the results
            self._set_cached(cache_key, releases)
            
            return releases[:max_count]
            
        except requests.exceptions.HTTPError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_FAILED,
                level="warning",
                api="github",
                endpoint="releases",
                repo=f"{owner}/{repo}",
                error=str(e),
                status_code=e.response.status_code if e.response else None,
                elapsed_ms=elapsed_ms,
            )
            
            if e.response.status_code == 404:
                # Repository has no releases
                logger.info(f"No releases found for {owner}/{repo}")
                self._set_cached(cache_key, [])
                return []
            else:
                logger.error(f"HTTP error fetching releases for {owner}/{repo}: {e}")
                raise
        except requests.exceptions.RequestException as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_FAILED,
                level="error",
                api="github",
                endpoint="releases",
                repo=f"{owner}/{repo}",
                error=str(e),
                elapsed_ms=elapsed_ms,
            )
            logger.error(f"Error fetching releases for {owner}/{repo}: {e}")
            raise
    
    def fetch_contributors(
        self, 
        owner: str, 
        repo: str, 
        max_count: int = 5,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch contributors from GitHub API with caching.
        
        Args:
            owner: Repository owner
            repo: Repository name
            max_count: Maximum number of contributors to fetch
            force_refresh: Force refresh from API, bypassing cache
        
        Returns:
            List of contributor dictionaries with keys:
            - login: GitHub username
            - contributions: Number of contributions
            - avatar_url: Avatar URL
            - type: User type (usually "User")
        
        Raises:
            requests.RequestException: On API errors
        """
        cache_key = f"contributors:{owner}/{repo}"
        
        # Check cache first unless force refresh
        if not force_refresh:
            cached = self._get_cached(cache_key)
            if cached is not None:
                log_event(logger, LogEvent.CACHE_HIT, cache_key=cache_key)
                return cached[:max_count]
            else:
                log_event(logger, LogEvent.CACHE_MISS, cache_key=cache_key)
        
        # Fetch from API
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contributors"
        params = {"per_page": max_count}
        
        try:
            logger.info(f"Fetching contributors for {owner}/{repo} from GitHub API")
            
            # Log API call start
            start_time = time.time()
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_STARTED,
                api="github",
                endpoint="contributors",
                repo=f"{owner}/{repo}",
            )
            
            response = self.session.get(url, params=params, timeout=20)
            response.raise_for_status()
            
            # Log API call completion with timing
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_COMPLETED,
                api="github",
                endpoint="contributors",
                repo=f"{owner}/{repo}",
                elapsed_ms=elapsed_ms,
            )
            
            contributors = response.json()
            
            # Cache the results (TTL is 24 hours for contributors as per design)
            self._set_cached(cache_key, contributors)
            
            return contributors[:max_count]
            
        except requests.exceptions.HTTPError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_FAILED,
                level="warning",
                api="github",
                endpoint="contributors",
                repo=f"{owner}/{repo}",
                error=str(e),
                status_code=e.response.status_code if e.response else None,
                elapsed_ms=elapsed_ms,
            )
            
            if e.response.status_code == 404:
                # Repository not found or no contributors
                logger.info(f"No contributors found for {owner}/{repo}")
                self._set_cached(cache_key, [])
                return []
            else:
                logger.error(f"HTTP error fetching contributors for {owner}/{repo}: {e}")
                raise
        except requests.exceptions.RequestException as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_event(
                logger,
                LogEvent.EXTERNAL_API_CALL_FAILED,
                level="error",
                api="github",
                endpoint="contributors",
                repo=f"{owner}/{repo}",
                error=str(e),
                elapsed_ms=elapsed_ms,
            )
            logger.error(f"Error fetching contributors for {owner}/{repo}: {e}")
            raise

