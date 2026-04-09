"""
Cache manager for GitHub API responses and live ingestion results.

Provides disk-based caching with TTL enforcement, cache invalidation,
and optional database promotion for live ingestion results.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .config import IngestionConfig


class CacheManager:
    """
    Manages caching of API responses and live ingestion results.
    
    Features:
    - Disk persistence to data/github_cache/
    - TTL enforcement (1 hour default)
    - Cache key generation from repository identifier + endpoint
    - Pattern-based cache invalidation
    - Optional database promotion for live ingestion results
    """

    def __init__(self, config: Optional[IngestionConfig] = None):
        """
        Initialize cache manager.
        
        Args:
            config: Configuration object. If None, uses defaults.
        """
        self.config = config or IngestionConfig()
        
        # Get cache configuration
        self.cache_dir = Path(self.config.get("caching", "cache_dir", default="data/github_cache"))
        self.ttl_seconds = self.config.get("caching", "ttl_seconds", default=3600)
        self.enable_disk_persistence = self.config.get("caching", "enable_disk_persistence", default=True)
        
        # Create cache directory if it doesn't exist
        if self.enable_disk_persistence:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _generate_cache_key(self, key: str) -> str:
        """
        Generate a safe filename from cache key.
        
        Args:
            key: Cache key (e.g., "api:contributors:owner/repo" or "live:owner/repo:full")
            
        Returns:
            Safe filename for cache entry
        """
        # Replace special characters with underscores
        safe_key = re.sub(r'[^\w\-:]', '_', key)
        return f"{safe_key}.json"

    def _get_cache_path(self, key: str) -> Path:
        """Get full path to cache file."""
        filename = self._generate_cache_key(key)
        return self.cache_dir / filename

    def _is_expired(self, timestamp: float, ttl_seconds: Optional[int] = None) -> bool:
        """
        Check if a cached item is expired.
        
        Args:
            timestamp: Unix timestamp when item was cached
            ttl_seconds: TTL in seconds. If None, uses default.
            
        Returns:
            True if expired, False otherwise
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        age = time.time() - timestamp
        return age >= ttl

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve cached value if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found or expired
        """
        if not self.enable_disk_persistence:
            return None

        cache_path = self._get_cache_path(key)
        
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r') as f:
                cache_entry = json.load(f)
            
            # Check if expired
            timestamp = cache_entry.get('timestamp')
            if timestamp is None:
                # Invalid cache entry, remove it
                cache_path.unlink()
                return None
            
            # Use the TTL stored with the entry, or default
            ttl = cache_entry.get('ttl_seconds', self.ttl_seconds)
            if self._is_expired(timestamp, ttl):
                # Expired, remove it
                cache_path.unlink()
                return None
            
            return cache_entry.get('value')
            
        except (json.JSONDecodeError, IOError) as e:
            # Cache read failure - log warning and return None
            print(f"Warning: Failed to read cache for key '{key}': {e}")
            # Try to remove corrupted cache file
            try:
                cache_path.unlink()
            except:
                pass
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        Store value with TTL.
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_seconds: TTL in seconds. If None, uses default.
        """
        if not self.enable_disk_persistence:
            return

        cache_path = self._get_cache_path(key)
        
        cache_entry = {
            'timestamp': time.time(),
            'ttl_seconds': ttl_seconds if ttl_seconds is not None else self.ttl_seconds,
            'value': value
        }
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache_entry, f, indent=2, default=str)
        except (IOError, TypeError) as e:
            # Cache write failure - log error but continue
            print(f"Error: Failed to write cache for key '{key}': {e}")

    def invalidate(self, pattern: str) -> int:
        """
        Invalidate cache entries matching pattern.
        
        Args:
            pattern: Pattern to match against cache keys (supports wildcards)
            
        Returns:
            Number of cache entries invalidated
        """
        if not self.enable_disk_persistence:
            return 0

        if not self.cache_dir.exists():
            return 0

        # Convert pattern to regex
        # Replace * with .* for wildcard matching
        regex_pattern = pattern.replace('*', '.*')
        regex = re.compile(regex_pattern)
        
        invalidated_count = 0
        
        try:
            for cache_file in self.cache_dir.glob('*.json'):
                # Extract original key from filename
                filename = cache_file.stem
                # Reverse the safe key transformation (approximately)
                original_key = filename.replace('_', '/')
                
                if regex.search(original_key) or regex.search(filename):
                    try:
                        cache_file.unlink()
                        invalidated_count += 1
                    except IOError as e:
                        print(f"Warning: Failed to delete cache file {cache_file}: {e}")
        except Exception as e:
            print(f"Error during cache invalidation: {e}")
        
        return invalidated_count

    def promote_to_database(self, repo_identifier: str) -> bool:
        """
        Promote cached live ingestion result to database.
        
        This method is a placeholder for optional database promotion.
        The actual implementation depends on the database schema and
        persistence layer integration.
        
        Args:
            repo_identifier: Repository identifier (owner/repo)
            
        Returns:
            True if promotion successful, False otherwise
        """
        # Check if we have a cached live ingestion result
        cache_key = f"live:{repo_identifier}:full"
        cached_result = self.get(cache_key)
        
        if cached_result is None:
            # Try provisional mode
            cache_key = f"live:{repo_identifier}:provisional"
            cached_result = self.get(cache_key)
        
        if cached_result is None:
            return False
        
        # TODO: Implement actual database promotion
        # This would involve:
        # 1. Extracting the ingestion result from cached_result
        # 2. Persisting to the database using the persistence layer
        # 3. Updating metadata to mark as database-sourced
        
        # For now, return False to indicate not implemented
        print(f"Database promotion not yet implemented for {repo_identifier}")
        return False

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.enable_disk_persistence or not self.cache_dir.exists():
            return {
                'total_entries': 0,
                'expired_entries': 0,
                'valid_entries': 0,
                'total_size_bytes': 0
            }
        
        total_entries = 0
        expired_entries = 0
        valid_entries = 0
        total_size_bytes = 0
        
        try:
            for cache_file in self.cache_dir.glob('*.json'):
                total_entries += 1
                total_size_bytes += cache_file.stat().st_size
                
                try:
                    with open(cache_file, 'r') as f:
                        cache_entry = json.load(f)
                    
                    timestamp = cache_entry.get('timestamp')
                    ttl = cache_entry.get('ttl_seconds', self.ttl_seconds)
                    if timestamp and self._is_expired(timestamp, ttl):
                        expired_entries += 1
                    else:
                        valid_entries += 1
                except:
                    expired_entries += 1
        except Exception as e:
            print(f"Error getting cache stats: {e}")
        
        return {
            'total_entries': total_entries,
            'expired_entries': expired_entries,
            'valid_entries': valid_entries,
            'total_size_bytes': total_size_bytes
        }

    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.
        
        Returns:
            Number of entries removed
        """
        if not self.enable_disk_persistence or not self.cache_dir.exists():
            return 0
        
        removed_count = 0
        
        try:
            for cache_file in self.cache_dir.glob('*.json'):
                try:
                    with open(cache_file, 'r') as f:
                        cache_entry = json.load(f)
                    
                    timestamp = cache_entry.get('timestamp')
                    ttl = cache_entry.get('ttl_seconds', self.ttl_seconds)
                    if timestamp and self._is_expired(timestamp, ttl):
                        cache_file.unlink()
                        removed_count += 1
                except:
                    # If we can't read it, it's corrupted - remove it
                    try:
                        cache_file.unlink()
                        removed_count += 1
                    except:
                        pass
        except Exception as e:
            print(f"Error during cache cleanup: {e}")
        
        return removed_count
