"""
Manifest content caching to avoid re-fetching.

Caches manifest files with TTL to reduce GitHub API calls.
"""

import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ManifestCache:
    """Caches manifest content to avoid re-fetching."""
    
    def __init__(self, cache_dir: str = "data/manifest_cache"):
        """
        Initialize manifest cache.
        
        Args:
            cache_dir: Directory to store cached manifests
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get(
        self,
        repo_full_name: str,
        manifest_path: str,
        ttl_hours: int = 24
    ) -> Optional[str]:
        """
        Get cached manifest content.
        
        Args:
            repo_full_name: Repository in format "owner/repo"
            manifest_path: Path to manifest file
            ttl_hours: Time-to-live in hours
        
        Returns:
            Cached content or None if not found/expired
        """
        cache_file = self._get_cache_file(repo_full_name, manifest_path)
        
        if not cache_file.exists():
            return None
        
        # Check TTL
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours > ttl_hours:
            logger.debug(f"Cache expired for {repo_full_name}/{manifest_path}")
            return None
        
        try:
            content = cache_file.read_text(encoding='utf-8')
            logger.debug(f"Cache hit for {repo_full_name}/{manifest_path}")
            return content
        except Exception as e:
            logger.error(f"Failed to read cache for {repo_full_name}/{manifest_path}: {e}")
            return None
    
    def set(
        self,
        repo_full_name: str,
        manifest_path: str,
        content: str
    ):
        """
        Cache manifest content.
        
        Args:
            repo_full_name: Repository in format "owner/repo"
            manifest_path: Path to manifest file
            content: File content to cache
        """
        cache_file = self._get_cache_file(repo_full_name, manifest_path)
        
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(content, encoding='utf-8')
            logger.debug(f"Cached {repo_full_name}/{manifest_path}")
        except Exception as e:
            logger.error(f"Failed to cache {repo_full_name}/{manifest_path}: {e}")
    
    def clear(self, repo_full_name: Optional[str] = None):
        """
        Clear cache.
        
        Args:
            repo_full_name: If provided, clear only this repo's cache.
                          If None, clear entire cache.
        """
        if repo_full_name:
            # Clear specific repo
            cache_key = repo_full_name.replace('/', '_')
            repo_cache_dir = self.cache_dir / cache_key
            
            if repo_cache_dir.exists():
                import shutil
                shutil.rmtree(repo_cache_dir)
                logger.info(f"Cleared cache for {repo_full_name}")
        else:
            # Clear entire cache
            if self.cache_dir.exists():
                import shutil
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Cleared entire manifest cache")
    
    def _get_cache_file(self, repo_full_name: str, manifest_path: str) -> Path:
        """Get cache file path for a manifest."""
        # Create safe filename
        cache_key = repo_full_name.replace('/', '_')
        manifest_key = manifest_path.replace('/', '_')
        
        return self.cache_dir / cache_key / f"{manifest_key}.txt"
