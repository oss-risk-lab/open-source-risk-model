"""
Tests for logging and metrics functionality.
"""

import pytest
from src.open_source_risk_model.utils.logging_utils import (
    StructuredLogger,
    generate_request_id,
    set_request_id,
    get_request_id,
    clear_request_id,
    log_event,
    LogEvent,
)
from src.open_source_risk_model.utils.metrics import (
    get_metrics_collector,
    reset_metrics,
)


def test_structured_logger_basic():
    """Test basic structured logging functionality."""
    logger = StructuredLogger("test")
    
    # Should not raise any exceptions
    logger.info("Test message")
    logger.debug("Debug message")
    logger.warning("Warning message")
    logger.error("Error message")


def test_structured_logger_with_context():
    """Test structured logging with context."""
    logger = StructuredLogger("test")
    
    # Set request ID
    request_id = generate_request_id()
    set_request_id(request_id)
    
    # Verify request ID is set
    assert get_request_id() == request_id
    
    # Log with context
    logger.info("Test message", repo="test/repo", count=5)
    
    # Clear request ID
    clear_request_id()
    assert get_request_id() is None


def test_log_event():
    """Test event logging."""
    logger = StructuredLogger("test")
    
    # Should not raise any exceptions
    log_event(logger, LogEvent.CACHE_HIT, cache_key="test_key")
    log_event(logger, LogEvent.CACHE_MISS, cache_key="test_key")
    log_event(logger, LogEvent.GRAPH_GENERATION_STARTED, repo="test/repo")
    log_event(logger, LogEvent.GRAPH_GENERATION_COMPLETED, repo="test/repo")


def test_metrics_collector_graph_generation():
    """Test metrics collector for graph generation."""
    reset_metrics()
    metrics = get_metrics_collector()
    
    # Record some graph generation times
    metrics.record_graph_generation(100.0)
    metrics.record_graph_generation(200.0)
    metrics.record_graph_generation(300.0)
    
    # Get snapshot
    snapshot = metrics.get_snapshot()
    
    assert snapshot.graph_generation_count == 3
    assert snapshot.graph_generation_avg_ms == 200.0
    assert snapshot.graph_generation_total_ms == 600.0


def test_metrics_collector_api_response():
    """Test metrics collector for API response times."""
    reset_metrics()
    metrics = get_metrics_collector()
    
    # Record some API response times
    metrics.record_api_response(150.0)
    metrics.record_api_response(250.0)
    
    # Get snapshot
    snapshot = metrics.get_snapshot()
    
    assert snapshot.api_response_count == 2
    assert snapshot.api_response_avg_ms == 200.0
    assert snapshot.api_response_total_ms == 400.0


def test_metrics_collector_cache():
    """Test metrics collector for cache operations."""
    reset_metrics()
    metrics = get_metrics_collector()
    
    # Record cache operations
    metrics.record_cache_hit()
    metrics.record_cache_hit()
    metrics.record_cache_miss()
    
    # Get snapshot
    snapshot = metrics.get_snapshot()
    
    assert snapshot.cache_hits == 2
    assert snapshot.cache_misses == 1
    assert snapshot.cache_hit_rate == pytest.approx(0.6667, rel=0.01)


def test_metrics_collector_errors():
    """Test metrics collector for error tracking."""
    reset_metrics()
    metrics = get_metrics_collector()
    
    # Record errors
    metrics.record_error("github_api")
    metrics.record_error("osv_api")
    metrics.record_error("github_api")
    
    # Get snapshot
    snapshot = metrics.get_snapshot()
    
    assert snapshot.total_errors == 3
    assert snapshot.errors_by_type["github_api"] == 2
    assert snapshot.errors_by_type["osv_api"] == 1


def test_metrics_collector_dict():
    """Test metrics collector dictionary output."""
    reset_metrics()
    metrics = get_metrics_collector()
    
    # Record some metrics
    metrics.record_graph_generation(100.0)
    metrics.record_api_response(200.0)
    metrics.record_cache_hit()
    metrics.record_error("test_error")
    
    # Get metrics dict
    metrics_dict = metrics.get_metrics_dict()
    
    # Verify structure
    assert "timestamp" in metrics_dict
    assert "graph_generation" in metrics_dict
    assert "api_response" in metrics_dict
    assert "cache" in metrics_dict
    assert "errors" in metrics_dict
    assert "uptime_seconds" in metrics_dict
    
    # Verify values
    assert metrics_dict["graph_generation"]["count"] == 1
    assert metrics_dict["api_response"]["count"] == 1
    assert metrics_dict["cache"]["hits"] == 1
    assert metrics_dict["errors"]["total"] == 1


def test_metrics_reset():
    """Test metrics reset functionality."""
    reset_metrics()
    metrics = get_metrics_collector()
    
    # Record some metrics
    metrics.record_graph_generation(100.0)
    metrics.record_cache_hit()
    metrics.record_error("test")
    
    # Verify metrics are recorded
    snapshot = metrics.get_snapshot()
    assert snapshot.graph_generation_count == 1
    assert snapshot.cache_hits == 1
    assert snapshot.total_errors == 1
    
    # Reset metrics
    metrics.reset()
    
    # Verify metrics are cleared
    snapshot = metrics.get_snapshot()
    assert snapshot.graph_generation_count == 0
    assert snapshot.cache_hits == 0
    assert snapshot.total_errors == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
