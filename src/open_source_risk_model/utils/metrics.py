"""
Performance metrics tracking for graph generation and API requests.

Tracks graph generation time, API response time, cache hit rate, and error rates.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional


@dataclass
class MetricSnapshot:
    """Snapshot of metrics at a point in time."""
    
    timestamp: str
    graph_generation_count: int
    graph_generation_total_ms: float
    graph_generation_avg_ms: float
    api_response_count: int
    api_response_total_ms: float
    api_response_avg_ms: float
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    errors_by_type: Dict[str, int]
    total_errors: int


class MetricsCollector:
    """
    Thread-safe metrics collector for tracking performance metrics.
    
    Tracks:
    - Graph generation time
    - API response time
    - Cache hit rate
    - Error rate by type
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self._lock = Lock()
        
        # Graph generation metrics
        self._graph_generation_times: List[float] = []
        self._graph_generation_count = 0
        self._graph_generation_total_ms = 0.0
        
        # API response metrics
        self._api_response_times: List[float] = []
        self._api_response_count = 0
        self._api_response_total_ms = 0.0
        
        # Cache metrics
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Error metrics
        self._errors_by_type: Dict[str, int] = defaultdict(int)
        
        # Start time for uptime tracking
        self._start_time = time.time()
    
    def record_graph_generation(self, duration_ms: float) -> None:
        """
        Record graph generation time.
        
        Args:
            duration_ms: Generation time in milliseconds
        """
        with self._lock:
            self._graph_generation_times.append(duration_ms)
            self._graph_generation_count += 1
            self._graph_generation_total_ms += duration_ms
    
    def record_api_response(self, duration_ms: float) -> None:
        """
        Record API response time.
        
        Args:
            duration_ms: Response time in milliseconds
        """
        with self._lock:
            self._api_response_times.append(duration_ms)
            self._api_response_count += 1
            self._api_response_total_ms += duration_ms
    
    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        with self._lock:
            self._cache_hits += 1
    
    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        with self._lock:
            self._cache_misses += 1
    
    def record_error(self, error_type: str) -> None:
        """
        Record an error by type.
        
        Args:
            error_type: Error type/category (e.g., "github_api", "osv_api", "validation")
        """
        with self._lock:
            self._errors_by_type[error_type] += 1
    
    def get_snapshot(self) -> MetricSnapshot:
        """
        Get current metrics snapshot.
        
        Returns:
            MetricSnapshot with current metrics
        """
        with self._lock:
            # Calculate averages
            graph_gen_avg = (
                self._graph_generation_total_ms / self._graph_generation_count
                if self._graph_generation_count > 0
                else 0.0
            )
            
            api_response_avg = (
                self._api_response_total_ms / self._api_response_count
                if self._api_response_count > 0
                else 0.0
            )
            
            # Calculate cache hit rate
            total_cache_ops = self._cache_hits + self._cache_misses
            cache_hit_rate = (
                self._cache_hits / total_cache_ops
                if total_cache_ops > 0
                else 0.0
            )
            
            # Total errors
            total_errors = sum(self._errors_by_type.values())
            
            return MetricSnapshot(
                timestamp=datetime.now(timezone.utc).isoformat(),
                graph_generation_count=self._graph_generation_count,
                graph_generation_total_ms=self._graph_generation_total_ms,
                graph_generation_avg_ms=round(graph_gen_avg, 2),
                api_response_count=self._api_response_count,
                api_response_total_ms=self._api_response_total_ms,
                api_response_avg_ms=round(api_response_avg, 2),
                cache_hits=self._cache_hits,
                cache_misses=self._cache_misses,
                cache_hit_rate=round(cache_hit_rate, 4),
                errors_by_type=dict(self._errors_by_type),
                total_errors=total_errors,
            )
    
    def get_metrics_dict(self) -> Dict:
        """
        Get metrics as dictionary for API responses.
        
        Returns:
            Dictionary with current metrics
        """
        snapshot = self.get_snapshot()
        
        return {
            "timestamp": snapshot.timestamp,
            "graph_generation": {
                "count": snapshot.graph_generation_count,
                "total_ms": round(snapshot.graph_generation_total_ms, 2),
                "avg_ms": snapshot.graph_generation_avg_ms,
            },
            "api_response": {
                "count": snapshot.api_response_count,
                "total_ms": round(snapshot.api_response_total_ms, 2),
                "avg_ms": snapshot.api_response_avg_ms,
            },
            "cache": {
                "hits": snapshot.cache_hits,
                "misses": snapshot.cache_misses,
                "hit_rate": snapshot.cache_hit_rate,
            },
            "errors": {
                "by_type": snapshot.errors_by_type,
                "total": snapshot.total_errors,
            },
            "uptime_seconds": round(time.time() - self._start_time, 2),
        }
    
    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._graph_generation_times.clear()
            self._graph_generation_count = 0
            self._graph_generation_total_ms = 0.0
            
            self._api_response_times.clear()
            self._api_response_count = 0
            self._api_response_total_ms = 0.0
            
            self._cache_hits = 0
            self._cache_misses = 0
            
            self._errors_by_type.clear()
            
            self._start_time = time.time()


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get the global metrics collector instance.
    
    Returns:
        Global MetricsCollector instance
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics() -> None:
    """Reset global metrics (useful for testing)."""
    global _metrics_collector
    if _metrics_collector is not None:
        _metrics_collector.reset()
