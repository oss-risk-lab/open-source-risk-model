"""
Graph caching module for supply chain risk graphs.

Provides caching functionality to store and retrieve complete graphs,
reducing the need to rebuild graphs from external APIs on every request.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from .schema import Graph, Node, Edge, NodeType, EdgeType

# Set up logger
logger = logging.getLogger(__name__)


class GraphCache:
    """
    Manages caching of supply chain risk graphs.
    
    Caches complete graphs to disk with TTL-based expiration.
    Cache files are stored in data/graphs/{owner}__{repo}.json
    """
    
    def __init__(self, cache_dir: str = "data/graphs", ttl_hours: int = 1):
        """
        Initialize graph cache.
        
        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Time-to-live for cached graphs in hours (default: 1)
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_hours = ttl_hours
        
        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized GraphCache with dir={cache_dir}, ttl={ttl_hours}h")
    
    def get(self, repo: str, max_releases: int = 10, max_maintainers: int = 5, include_cves: bool = True, max_risk_factors: int = 5) -> Optional[Graph]:
        """
        Retrieve a cached graph if it exists and is not expired.
        
        Args:
            repo: Repository full name (owner/repo)
            max_releases: Maximum number of releases (for cache key)
            max_maintainers: Maximum number of maintainers (for cache key)
            include_cves: Whether CVEs are included (for cache key)
            max_risk_factors: Maximum number of risk factors (for cache key)
        
        Returns:
            Cached Graph object if found and valid, None otherwise
        """
        cache_file = self._get_cache_file(repo, max_releases, max_maintainers, include_cves, max_risk_factors)
        
        if not cache_file.exists():
            logger.debug(f"Cache miss: {repo} (file not found)")
            return None
        
        try:
            # Read cache file
            with open(cache_file, "r") as f:
                cache_data = json.load(f)
            
            # Check if cache is expired
            if self._is_expired(cache_data):
                logger.info(f"Cache expired: {repo}")
                return None
            
            # Deserialize graph from cache data
            graph = self._deserialize_graph(cache_data)
            
            logger.info(f"Cache hit: {repo}")
            return graph
            
        except Exception as e:
            logger.warning(f"Failed to read cache for {repo}: {e}")
            return None
    
    def set(self, repo: str, graph: Graph, max_releases: int = 10, max_maintainers: int = 5, include_cves: bool = True, max_risk_factors: int = 5) -> bool:
        """
        Store a graph in the cache.
        
        Args:
            repo: Repository full name (owner/repo)
            graph: Graph object to cache
            max_releases: Maximum number of releases (for cache key)
            max_maintainers: Maximum number of maintainers (for cache key)
            include_cves: Whether CVEs are included (for cache key)
            max_risk_factors: Maximum number of risk factors (for cache key)
        
        Returns:
            True if successfully cached, False otherwise
        """
        cache_file = self._get_cache_file(repo, max_releases, max_maintainers, include_cves, max_risk_factors)
        
        try:
            # Serialize graph with cache metadata
            cache_data = self._serialize_graph(graph, repo)
            
            # Write to cache file
            with open(cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)
            
            logger.info(f"Cached graph for {repo} at {cache_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache graph for {repo}: {e}")
            return False
    
    def invalidate(self, repo: str) -> bool:
        """
        Invalidate (delete) a cached graph.
        
        Args:
            repo: Repository full name (owner/repo)
        
        Returns:
            True if cache was deleted, False if it didn't exist or deletion failed
        """
        cache_file = self._get_cache_file(repo)
        
        if not cache_file.exists():
            logger.debug(f"Cache file not found for {repo}")
            return False
        
        try:
            cache_file.unlink()
            logger.info(f"Invalidated cache for {repo}")
            return True
        except Exception as e:
            logger.error(f"Failed to invalidate cache for {repo}: {e}")
            return False
    
    def _get_cache_file(self, repo: str, max_releases: int = 10, max_maintainers: int = 5, include_cves: bool = True, max_risk_factors: int = 5) -> Path:
        """
        Get the cache file path for a repository with specific parameters.
        
        Args:
            repo: Repository full name (owner/repo)
            max_releases: Maximum number of releases
            max_maintainers: Maximum number of maintainers
            include_cves: Whether CVEs are included
            max_risk_factors: Maximum number of risk factors
        
        Returns:
            Path to cache file
        """
        # Replace slash with double underscore for filename
        # Include parameters in cache key for granularity
        cves_suffix = "cves" if include_cves else "nocves"
        filename = f"{repo.replace('/', '__')}__r{max_releases}_m{max_maintainers}_rf{max_risk_factors}_{cves_suffix}.json"
        return self.cache_dir / filename
    
    def _is_expired(self, cache_data: Dict[str, Any]) -> bool:
        """
        Check if cached data is expired.
        
        Args:
            cache_data: Cache data dictionary
        
        Returns:
            True if expired, False otherwise
        """
        try:
            expires_at_str = cache_data.get("cache_metadata", {}).get("expires_at")
            if not expires_at_str:
                logger.warning("Cache data missing expires_at, treating as expired")
                return True
            
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            
            return now >= expires_at
            
        except Exception as e:
            logger.warning(f"Failed to parse expiration time: {e}, treating as expired")
            return True
    
    def _serialize_graph(self, graph: Graph, repo: str) -> Dict[str, Any]:
        """
        Serialize a graph to a cache-friendly dictionary.
        
        Args:
            graph: Graph object to serialize
            repo: Repository full name (for metadata)
        
        Returns:
            Dictionary with graph data and cache metadata
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.ttl_hours)
        
        return {
            "cache_metadata": {
                "repo": repo,
                "cached_at": now.isoformat(),
                "ttl_hours": self.ttl_hours,
                "expires_at": expires_at.isoformat(),
            },
            "graph": graph.to_dict(),
        }
    
    def _deserialize_graph(self, cache_data: Dict[str, Any]) -> Graph:
        """
        Deserialize a graph from cached data.
        
        Args:
            cache_data: Cache data dictionary
        
        Returns:
            Graph object
        """
        graph_data = cache_data.get("graph", {})
        
        # Reconstruct nodes
        nodes = []
        for node_dict in graph_data.get("nodes", []):
            node = Node(
                id=node_dict["id"],
                type=NodeType(node_dict["type"]),
                label=node_dict["label"],
                metadata=node_dict.get("metadata", {}),
                provenance=node_dict.get("provenance", {}),
            )
            nodes.append(node)
        
        # Reconstruct edges
        edges = []
        for edge_dict in graph_data.get("edges", []):
            edge = Edge(
                source=edge_dict["source"],
                target=edge_dict["target"],
                relationship_type=EdgeType(edge_dict["relationship_type"]),
                metadata=edge_dict.get("metadata", {}),
                provenance=edge_dict.get("provenance", {}),
            )
            edges.append(edge)
        
        # Reconstruct graph
        graph = Graph(
            nodes=nodes,
            edges=edges,
            metadata=graph_data.get("metadata", {}),
        )
        
        return graph
