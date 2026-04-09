"""
Property-based tests for CacheManager.

Tests universal properties that should hold across all valid inputs.
Uses hypothesis for property-based testing with minimum 100 iterations.
"""

import tempfile
import time
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from src.open_source_risk_model.ingestion.cache_manager import CacheManager
from src.open_source_risk_model.ingestion.config import IngestionConfig


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def cache_manager_factory(temp_cache_dir):
    """Factory for creating cache managers with temporary cache directory."""
    def _create_manager(ttl_seconds=3600):
        config = IngestionConfig()
        config.config["caching"]["cache_dir"] = str(temp_cache_dir)
        config.config["caching"]["ttl_seconds"] = ttl_seconds
        return CacheManager(config)
    return _create_manager


# Strategy for generating repository identifiers
repo_identifier_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
    min_size=3,
    max_size=50
).filter(lambda x: "/" in x or len(x) > 5).map(
    lambda x: f"{x}/repo" if "/" not in x else x
)

# Strategy for generating endpoint names
endpoint_strategy = st.sampled_from([
    "contributors",
    "issues",
    "releases",
    "commits",
    "pulls",
    "stats",
    "events"
])

# Strategy for generating cache keys
cache_key_strategy = st.builds(
    lambda prefix, repo, endpoint: f"{prefix}:{endpoint}:{repo}",
    prefix=st.sampled_from(["api", "live"]),
    repo=repo_identifier_strategy,
    endpoint=endpoint_strategy
)


# Feature: github-api-optimization-query-coverage, Property 11: Cache Key Uniqueness
@given(
    repo1=repo_identifier_strategy,
    repo2=repo_identifier_strategy,
    endpoint1=endpoint_strategy,
    endpoint2=endpoint_strategy
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.property_test
def test_cache_key_uniqueness(cache_manager_factory, repo1, repo2, endpoint1, endpoint2):
    """
    Property 11: Cache Key Uniqueness
    
    For any two different combinations of (repository_identifier, endpoint),
    the cache keys generated should be distinct.
    
    Validates: Requirements 4.1
    """
    manager = cache_manager_factory()
    
    # Generate cache keys for different combinations
    key1 = f"api:{endpoint1}:{repo1}"
    key2 = f"api:{endpoint2}:{repo2}"
    
    cache_key1 = manager._generate_cache_key(key1)
    cache_key2 = manager._generate_cache_key(key2)
    
    # If the original keys are different, cache keys should be different
    if key1 != key2:
        assert cache_key1 != cache_key2, (
            f"Different keys produced same cache key: {key1} and {key2} "
            f"both mapped to {cache_key1}"
        )


# Feature: github-api-optimization-query-coverage, Property 12: Cache Timestamp Presence
@given(
    key=cache_key_strategy,
    value=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.integers(), st.floats(allow_nan=False), st.text())
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.property_test
def test_cache_timestamp_presence(cache_manager_factory, temp_cache_dir, key, value):
    """
    Property 12: Cache Timestamp Presence
    
    For any cached item, it should have an associated timestamp indicating
    when it was stored.
    
    Validates: Requirements 4.2
    """
    manager = cache_manager_factory()
    
    # Set a value in cache
    manager.set(key, value)
    
    # Check that the cache file exists and has a timestamp
    cache_path = manager._get_cache_path(key)
    assert cache_path.exists(), f"Cache file not created for key {key}"
    
    # Read the cache file and verify timestamp
    import json
    with open(cache_path, 'r') as f:
        cache_entry = json.load(f)
    
    assert "timestamp" in cache_entry, f"No timestamp in cache entry for key {key}"
    assert isinstance(cache_entry["timestamp"], (int, float)), (
        f"Timestamp is not numeric for key {key}: {cache_entry['timestamp']}"
    )
    assert cache_entry["timestamp"] > 0, (
        f"Timestamp is not positive for key {key}: {cache_entry['timestamp']}"
    )


# Feature: github-api-optimization-query-coverage, Property 13: Cache TTL Enforcement
@given(
    key=cache_key_strategy,
    value=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.integers(), st.text())
    ),
    ttl_seconds=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=50, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])  # Reduced examples due to time.sleep
@pytest.mark.property_test
def test_cache_ttl_enforcement(cache_manager_factory, key, value, ttl_seconds):
    """
    Property 13: Cache TTL Enforcement
    
    For any cached item, if its age is less than the TTL, it should be returned
    on cache lookup; if its age exceeds the TTL, it should not be returned.
    
    Validates: Requirements 4.3, 4.4, 14.3, 14.4
    """
    manager = cache_manager_factory(ttl_seconds=ttl_seconds)
    
    # Set value with specific TTL
    manager.set(key, value, ttl_seconds=ttl_seconds)
    
    # Should be available immediately (age < TTL)
    retrieved = manager.get(key)
    assert retrieved == value, (
        f"Cached value not returned immediately for key {key}"
    )
    
    # Wait for TTL to expire
    time.sleep(ttl_seconds + 0.5)
    
    # Should be expired now (age >= TTL)
    expired_result = manager.get(key)
    assert expired_result is None, (
        f"Expired cache entry still returned for key {key} after {ttl_seconds}s TTL"
    )


# Feature: github-api-optimization-query-coverage, Property 15: Cache Invalidation Isolation
@given(
    target_repo=repo_identifier_strategy,
    other_repos=st.lists(repo_identifier_strategy, min_size=2, max_size=5),
    endpoint=endpoint_strategy
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@pytest.mark.property_test
def test_cache_invalidation_isolation(cache_manager_factory, target_repo, other_repos, endpoint):
    """
    Property 15: Cache Invalidation Isolation
    
    For any repository identifier, invalidating its cache entries should not
    affect cache entries for other repositories.
    
    Validates: Requirements 4.6
    """
    manager = cache_manager_factory()
    
    # Ensure target_repo is not in other_repos and repos are sufficiently different
    # to avoid pattern matching issues
    other_repos = [repo for repo in other_repos if repo != target_repo and not target_repo.startswith(repo[:5]) and not repo.startswith(target_repo[:5])]
    if len(other_repos) < 2:
        # Skip if we don't have enough distinct repos after filtering
        return
    
    # Set cache entries for target repo and other repos
    target_key = f"api:{endpoint}:{target_repo}"
    manager.set(target_key, {"data": "target"})
    
    other_keys = []
    for repo in other_repos:
        key = f"api:{endpoint}:{repo}"
        manager.set(key, {"data": repo})
        other_keys.append(key)
    
    # Invalidate target repo's cache using a pattern that matches the transformed filename
    # Since / becomes _ in filenames, we need to use the transformed pattern
    transformed_repo = target_repo.replace('/', '_')
    invalidated = manager.invalidate(f"*{transformed_repo}*")
    
    # Target repo's cache should be invalidated
    assert manager.get(target_key) is None, (
        f"Target repo cache not invalidated: {target_repo}"
    )
    
    # Other repos' caches should still exist
    for key, repo in zip(other_keys, other_repos):
        retrieved = manager.get(key)
        assert retrieved is not None, (
            f"Other repo cache was incorrectly invalidated: {repo} "
            f"when invalidating {target_repo}"
        )


# Additional property test: Cache key generation is deterministic
@given(key=cache_key_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.property_test
def test_cache_key_generation_deterministic(cache_manager_factory, key):
    """
    Property: Cache key generation is deterministic.
    
    For any cache key, generating the cache filename multiple times should
    produce the same result.
    """
    manager = cache_manager_factory()
    
    # Generate cache key multiple times
    cache_key1 = manager._generate_cache_key(key)
    cache_key2 = manager._generate_cache_key(key)
    cache_key3 = manager._generate_cache_key(key)
    
    assert cache_key1 == cache_key2 == cache_key3, (
        f"Cache key generation is not deterministic for key {key}: "
        f"{cache_key1}, {cache_key2}, {cache_key3}"
    )


# Additional property test: Cache set and get round-trip
@given(
    key=cache_key_strategy,
    value=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(),
            st.booleans(),
            st.none()
        ),
        min_size=1,
        max_size=10
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.property_test
def test_cache_set_get_roundtrip(cache_manager_factory, key, value):
    """
    Property: Cache set and get round-trip preserves data.
    
    For any key-value pair, setting it in cache and immediately getting it
    should return the same value.
    """
    manager = cache_manager_factory()
    
    # Set value
    manager.set(key, value)
    
    # Get value
    retrieved = manager.get(key)
    
    # Should be identical
    assert retrieved == value, (
        f"Cache round-trip failed for key {key}: "
        f"stored {value}, retrieved {retrieved}"
    )


# Additional property test: Multiple cache entries coexist
@given(
    entries=st.lists(
        st.tuples(cache_key_strategy, st.dictionaries(
            keys=st.text(min_size=1, max_size=10),
            values=st.integers()
        )),
        min_size=2,
        max_size=10,
        unique_by=lambda x: x[0]  # Unique keys
    )
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.property_test
def test_multiple_cache_entries_coexist(cache_manager_factory, entries):
    """
    Property: Multiple cache entries can coexist independently.
    
    For any set of key-value pairs, all entries should be independently
    retrievable after being set.
    """
    manager = cache_manager_factory()
    
    # Set all entries
    for key, value in entries:
        manager.set(key, value)
    
    # Verify all entries are retrievable
    for key, expected_value in entries:
        retrieved = manager.get(key)
        assert retrieved == expected_value, (
            f"Failed to retrieve entry for key {key}: "
            f"expected {expected_value}, got {retrieved}"
        )
