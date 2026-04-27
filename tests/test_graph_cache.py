"""
Unit tests for graph caching functionality.

Tests cache hit/miss scenarios, refresh parameter, and TTL expiration.

Feature: supply-chain-graph
Task: 14.3 Write unit tests for caching
"""

import json
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from open_source_risk_model.graph.cache import GraphCache
from open_source_risk_model.graph.schema import Graph, Node, Edge, NodeType, EdgeType


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    graph = Graph(
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repo": "test/repo",
        }
    )
    
    # Add a repo node
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={
            "url": "https://github.com/test/repo",
            "maintenance_risk": 0.3,
        },
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 0.9,
        }
    )
    graph.add_node(repo_node)
    
    # Add a release node
    release_node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={
            "tag_name": "v1.0.0",
            "published_at": "2024-01-01T00:00:00Z",
        },
        provenance={
            "source": "github_api",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data_confidence": 1.0,
        }
    )
    graph.add_node(release_node)
    
    # Add an edge
    edge = Edge(
        source="repo:test/repo",
        target="release:test/repo:v1.0.0",
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={"is_latest": True},
        provenance={
            "source": "github_api",
            "established_at": datetime.now(timezone.utc).isoformat(),
            "confidence": 1.0,
        }
    )
    graph.add_edge(edge)
    
    return graph


def test_cache_miss(temp_cache_dir):
    """Test cache miss scenario when graph is not cached."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Try to get a graph that doesn't exist
    result = cache.get("test/repo")
    
    assert result is None


def test_cache_hit(temp_cache_dir, sample_graph):
    """Test cache hit scenario when graph is cached and valid."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store graph in cache
    success = cache.set("test/repo", sample_graph)
    assert success is True
    
    # Retrieve from cache
    cached_graph = cache.get("test/repo")
    
    assert cached_graph is not None
    assert len(cached_graph.nodes) == 2
    assert len(cached_graph.edges) == 1
    assert cached_graph.nodes[0].id == "repo:test/repo"
    assert cached_graph.nodes[1].id == "release:test/repo:v1.0.0"
    assert cached_graph.edges[0].source == "repo:test/repo"
    assert cached_graph.edges[0].target == "release:test/repo:v1.0.0"


def test_cache_file_creation(temp_cache_dir, sample_graph):
    """Test that cache file is created with correct naming."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store graph with default parameters
    cache.set("owner/repo", sample_graph)
    
    # Check that file exists with correct name (includes parameters)
    cache_file = Path(temp_cache_dir) / "owner__repo__r10_m5_cves.json"
    assert cache_file.exists()
    
    # Verify file content structure
    with open(cache_file, "r") as f:
        cache_data = json.load(f)
    
    assert "cache_metadata" in cache_data
    assert "graph" in cache_data
    assert cache_data["cache_metadata"]["repo"] == "owner/repo"
    assert "cached_at" in cache_data["cache_metadata"]
    assert "expires_at" in cache_data["cache_metadata"]
    assert cache_data["cache_metadata"]["ttl_hours"] == 1


def test_cache_ttl_expiration(temp_cache_dir, sample_graph):
    """Test that expired cache is not returned."""
    # Create cache with very short TTL (0 hours = immediate expiration)
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=0)
    
    # Store graph
    cache.set("test/repo", sample_graph)
    
    # Wait a moment to ensure expiration
    time.sleep(0.1)
    
    # Try to retrieve - should be expired
    result = cache.get("test/repo")
    
    assert result is None


def test_cache_ttl_not_expired(temp_cache_dir, sample_graph):
    """Test that non-expired cache is returned."""
    # Create cache with long TTL
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=24)
    
    # Store graph
    cache.set("test/repo", sample_graph)
    
    # Retrieve immediately - should not be expired
    result = cache.get("test/repo")
    
    assert result is not None
    assert len(result.nodes) == 2


def test_cache_invalidation(temp_cache_dir, sample_graph):
    """Test cache invalidation (deletion)."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store graph
    cache.set("test/repo", sample_graph)
    
    # Verify it's cached
    assert cache.get("test/repo") is not None
    
    # Invalidate cache
    success = cache.invalidate("test/repo")
    assert success is True
    
    # Verify it's no longer cached
    assert cache.get("test/repo") is None


def test_cache_invalidation_nonexistent(temp_cache_dir):
    """Test invalidating a cache that doesn't exist."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Try to invalidate non-existent cache
    success = cache.invalidate("nonexistent/repo")
    
    assert success is False


def test_cache_serialization_deserialization(temp_cache_dir, sample_graph):
    """Test that graph is correctly serialized and deserialized."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store graph
    cache.set("test/repo", sample_graph)
    
    # Retrieve and verify all fields are preserved
    cached_graph = cache.get("test/repo")
    
    assert cached_graph is not None
    
    # Verify nodes
    assert len(cached_graph.nodes) == len(sample_graph.nodes)
    for original, cached in zip(sample_graph.nodes, cached_graph.nodes):
        assert cached.id == original.id
        assert cached.type == original.type
        assert cached.label == original.label
        assert cached.metadata == original.metadata
        assert cached.provenance == original.provenance
    
    # Verify edges
    assert len(cached_graph.edges) == len(sample_graph.edges)
    for original, cached in zip(sample_graph.edges, cached_graph.edges):
        assert cached.source == original.source
        assert cached.target == original.target
        assert cached.relationship_type == original.relationship_type
        assert cached.metadata == original.metadata
        assert cached.provenance == original.provenance
    
    # Verify metadata
    assert cached_graph.metadata == sample_graph.metadata


def test_cache_with_multiple_repos(temp_cache_dir, sample_graph):
    """Test caching multiple repositories independently."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store graphs for different repos
    cache.set("repo1/test", sample_graph)
    cache.set("repo2/test", sample_graph)
    
    # Verify both are cached independently
    graph1 = cache.get("repo1/test")
    graph2 = cache.get("repo2/test")
    
    assert graph1 is not None
    assert graph2 is not None
    
    # Invalidate one
    cache.invalidate("repo1/test")
    
    # Verify only one is invalidated
    assert cache.get("repo1/test") is None
    assert cache.get("repo2/test") is not None


def test_cache_corrupted_file(temp_cache_dir, sample_graph):
    """Test handling of corrupted cache file."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store valid graph
    cache.set("test/repo", sample_graph)
    
    # Corrupt the cache file
    cache_file = Path(temp_cache_dir) / "test__repo__r10_m5_cves.json"
    with open(cache_file, "w") as f:
        f.write("invalid json {{{")
    
    # Try to retrieve - should handle gracefully
    result = cache.get("test/repo")
    
    assert result is None


def test_cache_missing_expiration(temp_cache_dir, sample_graph):
    """Test handling of cache file missing expiration metadata."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store valid graph
    cache.set("test/repo", sample_graph)
    
    # Manually modify cache file to remove expires_at
    cache_file = Path(temp_cache_dir) / "test__repo__r10_m5_cves.json"
    with open(cache_file, "r") as f:
        cache_data = json.load(f)
    
    del cache_data["cache_metadata"]["expires_at"]
    
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    
    # Try to retrieve - should treat as expired
    result = cache.get("test/repo")
    
    assert result is None


def test_cache_directory_creation(sample_graph):
    """Test that cache directory is created if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "nested" / "cache" / "dir"
        
        # Directory doesn't exist yet
        assert not cache_dir.exists()
        
        # Create cache - should create directory
        cache = GraphCache(cache_dir=str(cache_dir), ttl_hours=1)
        
        # Directory should now exist
        assert cache_dir.exists()
        
        # Should be able to store graph
        success = cache.set("test/repo", sample_graph)
        assert success is True


def test_cache_respects_parameters(temp_cache_dir, sample_graph):
    """Test that cache uses different files for different parameters."""
    cache = GraphCache(cache_dir=temp_cache_dir, ttl_hours=1)
    
    # Store graph with different parameters
    cache.set("test/repo", sample_graph, max_releases=5, max_maintainers=3, include_cves=True)
    cache.set("test/repo", sample_graph, max_releases=10, max_maintainers=5, include_cves=True)
    cache.set("test/repo", sample_graph, max_releases=5, max_maintainers=3, include_cves=False)
    
    # Verify different cache files exist
    cache_file_1 = Path(temp_cache_dir) / "test__repo__r5_m3_cves.json"
    cache_file_2 = Path(temp_cache_dir) / "test__repo__r10_m5_cves.json"
    cache_file_3 = Path(temp_cache_dir) / "test__repo__r5_m3_nocves.json"
    
    assert cache_file_1.exists()
    assert cache_file_2.exists()
    assert cache_file_3.exists()
    
    # Verify retrieval with matching parameters works
    result_1 = cache.get("test/repo", max_releases=5, max_maintainers=3, include_cves=True)
    result_2 = cache.get("test/repo", max_releases=10, max_maintainers=5, include_cves=True)
    result_3 = cache.get("test/repo", max_releases=5, max_maintainers=3, include_cves=False)
    
    assert result_1 is not None
    assert result_2 is not None
    assert result_3 is not None
