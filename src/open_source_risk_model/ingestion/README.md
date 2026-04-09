# GitHub API Ingestion Module

This module provides optimized repository data ingestion using a hybrid GraphQL/REST API strategy.

## Overview

The ingestion system reduces GitHub API calls by 50-80% through:
- **GraphQL** for repository snapshots (batch fetching with adaptive sizing)
- **REST API** for activity data (contributors, issues with pagination)
- **Adaptive batching** that adjusts based on query costs
- **Caching** with configurable TTL (default 1 hour)
- **Rate limiting** with separate tracking for REST and GraphQL

## Architecture

### Core Components

- **GraphQLClient**: Executes GraphQL queries with retry logic and adaptive batching
- **RESTClient**: Executes REST API calls with Link header pagination and retry logic
- **RateLimiter**: Monitors and enforces GitHub API rate limits
- **CacheManager**: Manages disk-based caching with TTL enforcement
- **RepoSnapshotFetcher**: Fetches repository metadata using GraphQL
- **ContributorsFetcher**: Fetches contributor data using REST API
- **IssuesFetcher**: Fetches issue lifecycle data using REST API
- **FeatureEngineer**: Computes derived maintenance risk metrics
- **IngestionPipeline**: Orchestrates the complete ingestion flow

### Data Models

All external data structures use Pydantic BaseModel for validation:

- **RepositorySnapshot**: GraphQL API response for repo metadata
- **ContributorRecord**: REST API response for contributor data
- **IssueRecord**: REST API response for issue data
- **MaintenanceRiskScore**: Computed risk score with metadata
- **DataProvenance**: Metadata about data source and freshness
- **EvidenceScope**: Tracks evidence used in queries
- **IngestionResult**: Result of single repository ingestion
- **IngestionSummary**: Summary of batch ingestion operation

## Configuration

Configuration is loaded from `config/ingestion_config.yaml`:

```yaml
graphql:
  initial_batch_size: 10  # Conservative starting point
  max_batch_size: 30      # Conservative maximum
  
rate_limiting:
  warning_threshold: 100  # Warn at 100 requests remaining
  
caching:
  ttl_seconds: 3600       # 1 hour cache TTL
  cache_dir: "data/github_cache"
  
features:
  minimum_coverage_threshold: 0.6  # 60% weighted features required
```

## Usage

### Basic Ingestion

```python
from open_source_risk_model.ingestion import IngestionPipeline, IngestionConfig

# Load configuration
config = IngestionConfig()

# Create pipeline
pipeline = IngestionPipeline(token="github_token", config=config)

# Ingest repositories
summary = pipeline.ingest_repositories(
    repo_identifiers=["numpy/numpy", "pandas-dev/pandas"],
    mode="full"  # or "provisional"
)

print(f"Ingested {summary.successful} repos with {summary.total_api_calls} API calls")
```

### Live Query Ingestion

```python
from open_source_risk_model.ingestion import LiveRepoIngestor

# Create ingestor
ingestor = LiveRepoIngestor(token="github_token", config=config)

# Ingest on-demand
results = ingestor.ingest(
    repo_identifiers=["flask/flask"],
    mode="provisional",  # Fast mode: snapshot + contributors only
    persistence_mode="cache"  # Cache with 1-hour TTL
)
```

## Implementation Status

### Completed
- ✅ Task 1: Directory structure, Pydantic data models, configuration schema
- ✅ Task 2.1: GraphQL client with query execution and error handling
- ✅ Task 2.2: Property tests for GraphQL client
- ✅ Task 2.3: REST client with pagination support

### In Progress
- Task 2.4: Property tests for REST client

### Upcoming Tasks
- Task 3: Rate limiting and caching implementation
- Task 5: Repository snapshot fetcher with adaptive batching
- Task 6: Activity data fetchers (contributors, issues)
- Task 7: Feature engineering with weighted coverage
- Task 9: Ingestion pipeline orchestration

## Design Principles

1. **Conservative Batching**: Start small (10-15 repos), grow cautiously
2. **Fail Gracefully**: Individual failures don't block batch operations
3. **Weighted Coverage**: Feature coverage based on weights, not raw count
4. **Pydantic Validation**: All external data validated at boundaries
5. **Configurable Behavior**: Tunable via YAML without code changes

## References

- Design Document: `.kiro/specs/github-api-optimization-query-coverage/design.md`
- Requirements: `.kiro/specs/github-api-optimization-query-coverage/requirements.md`
- Tasks: `.kiro/specs/github-api-optimization-query-coverage/tasks.md`
