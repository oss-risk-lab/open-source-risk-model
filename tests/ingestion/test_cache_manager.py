"""
Unit tests for CacheManager.

Tests cache operations, TTL enforcement, invalidation, and disk persistence.
"""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from src.open_source_risk_model.ingestion.cache_manager import CacheManager
from src.open_source_risk_model.ingestion.config import IngestionConfig


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def cache_manager(temp_cache_dir):
    """Create a CacheManager with temporary cache directory."""
    # Create a mock config
    config = IngestionConfig()
    config.config["caching"]["cache_dir"] = str(temp_cache_dir)
    config.config["caching"]["ttl_seconds"] = 2  # Short TTL for testing
    
    return CacheManager(config)


def test_cache_set_and_get(cache_manager):
    """Test basic cache set and get operations."""
    key = "test:key:1"
    value = {"data": "test_value", "count": 42}
    
    # Set value
    cache_manager.set(key, value)
    
    # Get value
    retrieved = cache_manager.get(key)
    
    assert retrieved == value


def test_cache_get_nonexistent(cache_manager):
    """Test getting a non-existent cache key returns None."""
    result = cache_manager.get("nonexistent:key")
    assert result is None


def test_cache_ttl_enforcement(cache_manager):
    """Test that expired cache entries are not returned."""
    key = "test:ttl:key"
    value = {"data": "expires_soon"}
    
    # Set value with short TTL
    cache_manager.set(key, value)
    
    # Should be available immediately
    assert cache_manager.get(key) == value
    
    # Wait for expiration (TTL is 2 seconds in fixture)
    time.sleep(2.5)
    
    # Should be expired now
    assert cache_manager.get(key) is None


def test_cache_custom_ttl(cache_manager):
    """Test setting custom TTL for specific cache entries."""
    key = "test:custom:ttl"
    value = {"data": "custom_ttl"}
    
    # Set with very short custom TTL (1 second)
    cache_manager.set(key, value, ttl_seconds=1)
    
    # Should be available immediately
    assert cache_manager.get(key) == value
    
    # Wait for custom TTL to expire
    time.sleep(1.5)
    
    # Should be expired
    assert cache_manager.get(key) is None


def test_cache_key_generation():
    """Test cache key generation creates safe filenames."""
    config = IngestionConfig()
    manager = CacheManager(config)
    
    # Test various key formats
    test_cases = [
        ("api:contributors:owner/repo", "api_contributors_owner_repo.json"),
        ("live:numpy/numpy:full", "live_numpy_numpy_full.json"),
        ("test:key:with:colons", "test_key_with_colons.json"),
    ]
    
    for key, expected_filename in test_cases:
        filename = manager._generate_cache_key(key)
        # Check that special characters are replaced
        assert "/" not in filename
        assert filename.endswith(".json")


def test_cache_invalidate_single(cache_manager):
    """Test invalidating a single cache entry."""
    # Set multiple cache entries
    cache_manager.set("repo:owner1/repo1", {"data": "1"})
    cache_manager.set("repo:owner2/repo2", {"data": "2"})
    cache_manager.set("api:owner1/repo1", {"data": "3"})
    
    # Invalidate entries matching pattern
    count = cache_manager.invalidate("repo:owner1/repo1")
    
    # Should have invalidated 1 entry
    assert count == 1
    
    # Check that correct entry was invalidated
    assert cache_manager.get("repo:owner1/repo1") is None
    assert cache_manager.get("repo:owner2/repo2") is not None
    assert cache_manager.get("api:owner1/repo1") is not None


def test_cache_invalidate_pattern(cache_manager):
    """Test invalidating multiple cache entries with wildcard pattern."""
    # Set multiple cache entries
    cache_manager.set("repo:owner1/repo1", {"data": "1"})
    cache_manager.set("repo:owner1/repo2", {"data": "2"})
    cache_manager.set("repo:owner2/repo1", {"data": "3"})
    cache_manager.set("api:owner1/repo1", {"data": "4"})
    
    # Invalidate all entries for owner1
    count = cache_manager.invalidate("*owner1*")
    
    # Should have invalidated 3 entries (2 repo + 1 api)
    assert count == 3
    
    # Check that correct entries were invalidated
    assert cache_manager.get("repo:owner1/repo1") is None
    assert cache_manager.get("repo:owner1/repo2") is None
    assert cache_manager.get("api:owner1/repo1") is None
    assert cache_manager.get("repo:owner2/repo1") is not None


def test_cache_invalidate_isolation(cache_manager):
    """Test that invalidating one repo doesn't affect others."""
    # Set cache entries for different repos
    cache_manager.set("live:numpy/numpy:full", {"data": "numpy"})
    cache_manager.set("live:pandas/pandas:full", {"data": "pandas"})
    cache_manager.set("live:flask/flask:full", {"data": "flask"})
    
    # Invalidate only numpy
    count = cache_manager.invalidate("*numpy*")
    
    assert count == 1
    assert cache_manager.get("live:numpy/numpy:full") is None
    assert cache_manager.get("live:pandas/pandas:full") is not None
    assert cache_manager.get("live:flask/flask:full") is not None


def test_cache_disk_persistence(cache_manager, temp_cache_dir):
    """Test that cache entries are persisted to disk."""
    key = "test:persistence"
    value = {"data": "persisted"}
    
    cache_manager.set(key, value)
    
    # Check that file exists on disk
    cache_files = list(temp_cache_dir.glob("*.json"))
    assert len(cache_files) == 1
    
    # Verify file contents
    with open(cache_files[0], 'r') as f:
        cache_entry = json.load(f)
    
    assert "timestamp" in cache_entry
    assert "ttl_seconds" in cache_entry
    assert "value" in cache_entry
    assert cache_entry["value"] == value


def test_cache_disabled_persistence():
    """Test cache manager with disk persistence disabled."""
    config = IngestionConfig()
    config.config["caching"]["enable_disk_persistence"] = False
    
    manager = CacheManager(config)
    
    # Set and get should work but not persist
    manager.set("test:key", {"data": "value"})
    result = manager.get("test:key")
    
    # Should return None since persistence is disabled
    assert result is None


def test_cache_corrupted_file(cache_manager, temp_cache_dir):
    """Test handling of corrupted cache files."""
    key = "test:corrupted"
    
    # Create a corrupted cache file
    cache_path = cache_manager._get_cache_path(key)
    with open(cache_path, 'w') as f:
        f.write("invalid json {{{")
    
    # Should return None and remove corrupted file
    result = cache_manager.get(key)
    assert result is None
    assert not cache_path.exists()


def test_cache_stats(cache_manager):
    """Test cache statistics reporting."""
    # Add some cache entries
    cache_manager.set("key1", {"data": "1"})
    cache_manager.set("key2", {"data": "2"})
    cache_manager.set("key3", {"data": "3"})
    
    stats = cache_manager.get_cache_stats()
    
    assert stats["total_entries"] == 3
    assert stats["valid_entries"] == 3
    assert stats["expired_entries"] == 0
    assert stats["total_size_bytes"] > 0


def test_cache_cleanup_expired(cache_manager):
    """Test cleanup of expired cache entries."""
    # Add entries with short TTL
    cache_manager.set("key1", {"data": "1"}, ttl_seconds=1)
    cache_manager.set("key2", {"data": "2"}, ttl_seconds=1)
    cache_manager.set("key3", {"data": "3"}, ttl_seconds=10)  # Won't expire
    
    # Wait for expiration
    time.sleep(1.5)
    
    # Cleanup expired entries
    removed = cache_manager.cleanup_expired()
    
    assert removed == 2
    
    # Check that only non-expired entry remains
    assert cache_manager.get("key1") is None
    assert cache_manager.get("key2") is None
    assert cache_manager.get("key3") is not None


def test_promote_to_database_not_implemented(cache_manager):
    """Test that promote_to_database returns False (not yet implemented)."""
    # Set a live ingestion result
    cache_manager.set("live:test/repo:full", {"data": "result"})
    
    # Try to promote
    result = cache_manager.promote_to_database("test/repo")
    
    # Should return False since not implemented
    assert result is False


def test_promote_to_database_no_cache(cache_manager):
    """Test promote_to_database with no cached result."""
    result = cache_manager.promote_to_database("nonexistent/repo")
    assert result is False


def test_cache_with_complex_data(cache_manager):
    """Test caching complex nested data structures."""
    key = "test:complex"
    value = {
        "repo": "owner/repo",
        "features": {
            "days_since_push": 10,
            "stars": 1000,
            "contributors": [
                {"login": "user1", "contributions": 100},
                {"login": "user2", "contributions": 50}
            ]
        },
        "metadata": {
            "fetched_at": "2024-01-01T00:00:00",
            "source": "live_fetch"
        }
    }
    
    cache_manager.set(key, value)
    retrieved = cache_manager.get(key)
    
    assert retrieved == value
    assert retrieved["features"]["contributors"][0]["login"] == "user1"


def test_cache_timestamp_presence(cache_manager, temp_cache_dir):
    """Test that all cached items have timestamps."""
    keys = ["key1", "key2", "key3"]
    
    for key in keys:
        cache_manager.set(key, {"data": key})
    
    # Check all cache files have timestamps
    for cache_file in temp_cache_dir.glob("*.json"):
        with open(cache_file, 'r') as f:
            cache_entry = json.load(f)
        
        assert "timestamp" in cache_entry
        assert isinstance(cache_entry["timestamp"], (int, float))
        assert cache_entry["timestamp"] > 0


def test_cache_key_uniqueness():
    """Test that different key combinations produce unique cache keys."""
    config = IngestionConfig()
    manager = CacheManager(config)
    
    keys = [
        "api:contributors:owner/repo",
        "api:issues:owner/repo",
        "live:owner/repo:full",
        "live:owner/repo:provisional",
        "live:owner/other:full",
    ]
    
    cache_keys = [manager._generate_cache_key(key) for key in keys]
    
    # All cache keys should be unique
    assert len(cache_keys) == len(set(cache_keys))
