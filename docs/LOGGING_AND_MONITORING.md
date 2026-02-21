# Logging and Monitoring

This document describes the logging and monitoring features implemented for the supply chain risk graph API.

## Overview

The system includes comprehensive logging and performance metrics tracking to help monitor and debug graph generation operations.

## Features

### 1. Structured Logging

All log entries include:
- **Request ID**: Unique identifier for each API request (UUID format)
- **Context**: Additional key-value pairs providing context (repo, timing, etc.)
- **Event types**: Standardized event types for common operations

#### Event Types

- `graph_generation_started`: Graph generation begins
- `graph_generation_completed`: Graph generation succeeds
- `graph_generation_failed`: Graph generation fails
- `external_api_call_started`: External API call begins (GitHub, OSV.dev)
- `external_api_call_completed`: External API call succeeds
- `external_api_call_failed`: External API call fails
- `cache_hit`: Cache lookup succeeds
- `cache_miss`: Cache lookup fails
- `cache_write`: Cache write succeeds
- `cache_write_failed`: Cache write fails
- `validation_failed`: Graph validation fails
- `validation_passed`: Graph validation succeeds

#### Usage Example

```python
from open_source_risk_model.utils.logging_utils import (
    StructuredLogger,
    generate_request_id,
    set_request_id,
    log_event,
    LogEvent,
)

# Create logger
logger = StructuredLogger(__name__)

# Set request ID for context
request_id = generate_request_id()
set_request_id(request_id)

# Log with context
logger.info("Processing request", repo="owner/repo", refresh=True)

# Log structured event
log_event(logger, LogEvent.CACHE_HIT, cache_key="owner/repo")
```

### 2. Performance Metrics

The system tracks:
- **Graph generation time**: Time to build graph (milliseconds)
- **API response time**: Total API response time (milliseconds)
- **Cache hit rate**: Percentage of cache hits vs total cache operations
- **Error rate by type**: Count of errors by category

#### Metrics Categories

- `graph_generation`: Graph build timing
  - `count`: Total number of graphs generated
  - `total_ms`: Total time spent generating graphs
  - `avg_ms`: Average generation time
  
- `api_response`: API response timing
  - `count`: Total number of API requests
  - `total_ms`: Total response time
  - `avg_ms`: Average response time
  
- `cache`: Cache performance
  - `hits`: Number of cache hits
  - `misses`: Number of cache misses
  - `hit_rate`: Cache hit rate (0.0-1.0)
  
- `errors`: Error tracking
  - `by_type`: Error counts by type (dict)
  - `total`: Total error count

#### Usage Example

```python
from open_source_risk_model.utils.metrics import get_metrics_collector

# Get global metrics collector
metrics = get_metrics_collector()

# Record metrics
metrics.record_graph_generation(250.5)  # milliseconds
metrics.record_api_response(300.0)
metrics.record_cache_hit()
metrics.record_error("github_api")

# Get current metrics
metrics_dict = metrics.get_metrics_dict()
print(f"Cache hit rate: {metrics_dict['cache']['hit_rate']}")
print(f"Avg response time: {metrics_dict['api_response']['avg_ms']}ms")
```

### 3. Enhanced Health Check Endpoint

The `/api/health` endpoint provides comprehensive health status:

#### Response Format

```json
{
  "status": "ok",
  "timestamp": "2026-02-18T10:30:00Z",
  "services": {
    "github_api": {
      "status": "ok",
      "message": "Connected (rate limit: 4500/5000)",
      "rate_limit_remaining": 4500,
      "rate_limit_total": 5000
    },
    "osv_api": {
      "status": "ok",
      "message": "Connected"
    },
    "cache": {
      "status": "ok",
      "message": "Cache is operational"
    }
  },
  "metrics": {
    "cache_hit_rate": 0.75,
    "avg_response_time_ms": 245.5,
    "total_requests": 100,
    "total_errors": 2
  },
  "uptime_seconds": 3600.5
}
```

#### Service Status Values

- `ok`: Service is operational
- `warning`: Service has issues but is functional (e.g., no GitHub token)
- `error`: Service is not operational

#### Overall Status

- `ok`: All services are operational
- `degraded`: One or more services have issues

## Integration

### API Endpoint

The `/api/graph` endpoint automatically:
1. Generates a unique request ID for each request
2. Logs all operations with request ID context
3. Records performance metrics
4. Includes request ID in response metadata

Example response metadata:
```json
{
  "metadata": {
    "node_count": 15,
    "edge_count": 18,
    "cache_hit": false,
    "generation_time_ms": 245,
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

### External API Calls

All external API calls (GitHub, OSV.dev) are logged with:
- API name and endpoint
- Request parameters
- Response time (milliseconds)
- Success/failure status
- Error details (if failed)

### Cache Operations

All cache operations are logged with:
- Cache key
- Hit/miss status
- Read/write operation
- Error details (if failed)

## Monitoring Best Practices

1. **Track Request IDs**: Use request IDs to trace operations across logs
2. **Monitor Cache Hit Rate**: Low cache hit rate may indicate cache issues
3. **Watch API Response Times**: Spikes may indicate external API issues
4. **Check Error Rates**: High error rates by type indicate specific issues
5. **Review Health Endpoint**: Regularly check service health status

## Configuration

### Logging Level

Set logging level via environment variable:
```bash
export LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### Metrics Reset

For testing, metrics can be reset:
```python
from open_source_risk_model.utils.metrics import reset_metrics
reset_metrics()
```

## Troubleshooting

### High Error Rate

Check error breakdown by type:
```bash
curl http://localhost:8000/api/health | jq '.metrics'
```

### Slow Response Times

Check average response time and graph generation time:
```bash
curl http://localhost:8000/api/health | jq '.metrics.avg_response_time_ms'
```

### External API Issues

Check service status:
```bash
curl http://localhost:8000/api/health | jq '.services'
```

### Cache Issues

Check cache hit rate and cache service status:
```bash
curl http://localhost:8000/api/health | jq '.metrics.cache_hit_rate'
curl http://localhost:8000/api/health | jq '.services.cache'
```

## Future Enhancements

Potential improvements:
- Export metrics to monitoring systems (Prometheus, Datadog)
- Add alerting based on thresholds
- Track per-repository metrics
- Add request tracing across services
- Implement log aggregation
