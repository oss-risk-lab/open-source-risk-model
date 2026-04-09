# Requirements Document

## Introduction

This feature enhances the open-source risk analysis system with two critical capabilities:

1. **GitHub API Ingestion Optimization**: A hybrid GraphQL/REST API strategy that reduces API calls by 50-80% while supporting ingestion of 100-1,000 repositories efficiently
2. **Query Coverage for Uningested Repositories**: A hybrid query system that enables natural language queries about any GitHub repository, combining pre-ingested database results with on-demand live ingestion

The system currently maintains maintenance risk scores for 145 repositories using REST API ingestion. Users query repositories using natural language, but queries fail when repositories are not pre-ingested. This feature enables scalable ingestion and universal query coverage.

## Glossary

- **API_Client**: The component responsible for making HTTP requests to GitHub's REST and GraphQL APIs
- **GraphQL_Client**: The component that executes GraphQL queries against GitHub's GraphQL API v4
- **REST_Client**: The component that executes REST API calls against GitHub's REST API v3
- **Rate_Limiter**: The component that monitors and enforces GitHub API rate limits (5,000 requests/hour for REST, separate limits for GraphQL)
- **Repo_Snapshot_Fetcher**: The component that retrieves repository metadata using GraphQL
- **Contributors_Fetcher**: The component that retrieves contributor data using REST API
- **Issues_Fetcher**: The component that retrieves issue lifecycle data using REST API
- **Feature_Engineer**: The component that computes derived maintenance risk metrics from raw GitHub data
- **Ingestion_Pipeline**: The orchestrator that coordinates fetching, feature engineering, and persistence
- **Query_Parser**: The component that interprets natural language queries and extracts intent
- **Intent_Classifier**: The component that categorizes query intent (list_dependencies, search_repos, etc.)
- **Entity_Extractor**: The component that identifies repository references in queries
- **Coverage_Checker**: The component that determines whether referenced repositories exist in the database
- **Retrieval_Strategy**: The component that selects between database-only, live-ingestion, or hybrid retrieval
- **DB_Retriever**: The component that fetches data from the local database
- **Live_Repo_Ingestor**: The component that performs on-demand repository ingestion during query execution
- **Result_Summarizer**: The component that generates natural language responses from query results
- **Cache_Manager**: The component that stores and retrieves cached API responses and live ingestion results
- **Maintenance_Risk_Score**: A numeric value (0-1) representing repository maintenance risk, computed from weighted features
- **Repository_Snapshot**: A data structure containing repository metadata (pushedAt, stars, archived status, license, open issues)
- **Contributor_Record**: A data structure containing contributor activity data
- **Issue_Record**: A data structure containing issue lifecycle data (creation, first response, closure, staleness)
- **Provisional_Score**: A maintenance risk score computed using only snapshot features (fast, incomplete)
- **Full_Score**: A maintenance risk score computed using all features including issue lifecycle metrics (slow, complete)
- **Data_Provenance**: Metadata indicating the source, timestamp, and completeness of query results

## Requirements

### Requirement 1: GraphQL Repository Snapshot Fetching

**User Story:** As a system administrator, I want to fetch repository snapshot metadata using GraphQL, so that I can reduce API calls and improve ingestion efficiency.

#### Acceptance Criteria

1. THE GraphQL_Client SHALL execute queries against GitHub GraphQL API v4 endpoint
2. WHEN a repository snapshot is requested, THE Repo_Snapshot_Fetcher SHALL retrieve pushedAt, latestRelease, stargazerCount, isArchived, licenseInfo, and open issues count in a single GraphQL query
3. THE Repo_Snapshot_Fetcher SHALL support configurable GraphQL batching for multiple repositories, with a default target batch size tuned to stay within GitHub query cost and complexity limits
4. WHEN pagination is required, THE Repo_Snapshot_Fetcher SHALL follow GraphQL cursor-based pagination
5. THE Repo_Snapshot_Fetcher SHALL parse GraphQL responses into Repository_Snapshot data structures
6. WHEN a GraphQL query fails, THE GraphQL_Client SHALL return a descriptive error with the failing repository identifier

### Requirement 2: REST API Activity Data Fetching

**User Story:** As a system administrator, I want to fetch contributor and issue activity data using REST API, so that I can compute issue lifecycle and contributor metrics.

#### Acceptance Criteria

1. THE Contributors_Fetcher SHALL retrieve contributor data from /repos/{owner}/{repo}/contributors endpoint
2. THE Contributors_Fetcher SHALL retrieve contributor statistics from /repos/{owner}/{repo}/stats/contributors endpoint
3. THE Issues_Fetcher SHALL retrieve issue data from /repos/{owner}/{repo}/issues endpoint with state=all parameter
4. THE Issues_Fetcher SHALL retrieve issue comments from /repos/{owner}/{repo}/issues/comments endpoint
5. THE Issues_Fetcher SHALL retrieve issue events from /repos/{owner}/{repo}/issues/events endpoint
6. WHEN pagination is required, THE REST_Client SHALL follow Link header pagination
7. THE REST_Client SHALL parse REST responses into Contributor_Record and Issue_Record data structures
8. WHEN a REST API call fails, THE REST_Client SHALL return a descriptive error with the HTTP status code and endpoint

### Requirement 3: Rate Limit Management

**User Story:** As a system administrator, I want to monitor and respect GitHub API rate limits, so that I can avoid service interruptions and API blocking.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL monitor remaining rate limit quota from X-RateLimit-Remaining response headers
2. THE Rate_Limiter SHALL track rate limit reset time from X-RateLimit-Reset response headers
3. WHEN remaining quota falls below 100 requests, THE Rate_Limiter SHALL log a warning
4. WHEN remaining quota reaches 0, THE Rate_Limiter SHALL pause requests until reset time
5. THE Rate_Limiter SHALL maintain separate rate limit tracking for REST API and GraphQL API
6. WHEN a rate limit error (HTTP 403 or 429) is received, THE Rate_Limiter SHALL implement exponential backoff with maximum wait time of 60 seconds

### Requirement 4: API Response Caching

**User Story:** As a system administrator, I want to cache API responses, so that I can avoid redundant API calls and improve ingestion performance.

#### Acceptance Criteria

1. THE Cache_Manager SHALL store API responses with repository identifier and endpoint as cache key
2. THE Cache_Manager SHALL associate each cached response with a timestamp
3. WHEN a cached response exists and is less than 1 hour old, THE API_Client SHALL return the cached response without making an API call
4. WHEN a cached response is older than 1 hour, THE API_Client SHALL fetch fresh data and update the cache
5. THE Cache_Manager SHALL persist cache to disk in data/github_cache/ directory
6. THE Cache_Manager SHALL support cache invalidation by repository identifier

### Requirement 5: Local Feature Engineering

**User Story:** As a data engineer, I want to compute derived maintenance risk metrics locally, so that I can reduce API calls and maintain compatibility with existing scoring logic.

#### Acceptance Criteria

1. THE Feature_Engineer SHALL compute days_since_last_push from Repository_Snapshot pushedAt field
2. THE Feature_Engineer SHALL compute days_since_last_release from Repository_Snapshot latestRelease field
3. THE Feature_Engineer SHALL compute issues_per_contributor from Issue_Record count and Contributor_Record count
4. THE Feature_Engineer SHALL compute fraction_issues_closed_12mo from Issue_Record closure timestamps
5. THE Feature_Engineer SHALL compute fraction_open_issues_stale_180d from Issue_Record last activity timestamps
6. THE Feature_Engineer SHALL compute contributors_last_12mo from Contributor_Record activity timestamps
7. THE Feature_Engineer SHALL compute top_contributor_fraction_12mo from Contributor_Record commit counts
8. THE Feature_Engineer SHALL compute avg_time_to_first_maintainer_response_days from Issue_Record and maintainer identification logic
9. THE Feature_Engineer SHALL compute median_time_to_close_days from Issue_Record creation and closure timestamps
10. THE Feature_Engineer SHALL compute open_issue_age_p90_days as 90th percentile of open Issue_Record ages
11. THE Feature_Engineer SHALL output features compatible with feature_mapping_config.py schema

### Requirement 6: Repository Ingestion Pipeline

**User Story:** As a system administrator, I want to orchestrate repository ingestion, so that I can ingest 100-1,000 repositories efficiently with proper error handling.

#### Acceptance Criteria

1. WHEN ingestion is initiated for a repository list, THE Ingestion_Pipeline SHALL fetch Repository_Snapshot data using Repo_Snapshot_Fetcher
2. WHEN Repository_Snapshot fetching succeeds, THE Ingestion_Pipeline SHALL fetch Contributor_Record data using Contributors_Fetcher
3. WHEN Contributor_Record fetching succeeds, THE Ingestion_Pipeline SHALL fetch Issue_Record data using Issues_Fetcher
4. WHEN all raw data is fetched, THE Ingestion_Pipeline SHALL invoke Feature_Engineer to compute derived metrics
5. WHEN feature engineering succeeds, THE Ingestion_Pipeline SHALL persist results to the database
6. IF any fetching step fails for a repository, THE Ingestion_Pipeline SHALL log the error and continue with remaining repositories
7. THE Ingestion_Pipeline SHALL report progress every 10 repositories processed
8. WHEN ingestion completes, THE Ingestion_Pipeline SHALL return a summary with success count, failure count, and total API calls made

### Requirement 7: Natural Language Query Parsing

**User Story:** As a user, I want to query repositories using natural language, so that I can get maintenance risk analysis without learning query syntax.

#### Acceptance Criteria

1. WHEN a natural language query is received, THE Query_Parser SHALL extract query intent using Intent_Classifier
2. THE Intent_Classifier SHALL classify queries into supported intents, with primary focus on: repo_lookup, repo_comparison, search_ranking, find_dependents, and missing_repo_handling. The system SHALL maintain backward compatibility with existing intents: list_dependencies, get_dependency_tree, check_resolution, list_unresolved, repo_stats, dataset_stats, search_repos, search_packages
3. WHEN repository names are mentioned in the query, THE Entity_Extractor SHALL extract repository identifiers in owner/repo format
4. WHEN ecosystem names are mentioned in the query, THE Entity_Extractor SHALL extract ecosystem identifiers (npm, pypi, maven, cargo)
5. THE Query_Parser SHALL return structured query representation with intent and extracted entities
6. WHEN query parsing fails, THE Query_Parser SHALL return an error message explaining why the query could not be understood

### Requirement 8: Query Coverage Detection

**User Story:** As a user, I want the system to determine whether queried repositories are available, so that I can receive accurate results or understand data limitations.

#### Acceptance Criteria

1. WHEN a query references repositories, THE Coverage_Checker SHALL verify whether each repository exists in the database
2. THE Coverage_Checker SHALL return coverage status for each repository: in_database, missing, or invalid
3. WHEN all referenced repositories are in the database, THE Coverage_Checker SHALL set coverage_mode to database_only
4. WHEN some referenced repositories are missing, THE Coverage_Checker SHALL set coverage_mode to hybrid
5. WHEN all referenced repositories are missing, THE Coverage_Checker SHALL set coverage_mode to live_ingestion_required
6. THE Coverage_Checker SHALL include last_updated timestamp for repositories found in the database

### Requirement 9: Retrieval Strategy Selection

**User Story:** As a system, I want to select the optimal data retrieval strategy, so that I can balance query latency with data freshness and coverage.

#### Acceptance Criteria

1. WHEN coverage_mode is database_only, THE Retrieval_Strategy SHALL select DB_Retriever
2. WHEN coverage_mode is live_ingestion_required, THE Retrieval_Strategy SHALL select Live_Repo_Ingestor
3. WHEN coverage_mode is hybrid, THE Retrieval_Strategy SHALL select both DB_Retriever and Live_Repo_Ingestor
4. WHERE user specifies provisional_score preference, THE Retrieval_Strategy SHALL configure Live_Repo_Ingestor for snapshot-only ingestion
5. WHERE user specifies full_score preference, THE Retrieval_Strategy SHALL configure Live_Repo_Ingestor for complete ingestion
6. THE Retrieval_Strategy SHALL classify expected retrieval cost as low, medium, or high for internal logging and optional UI use

### Requirement 10: Database Retrieval

**User Story:** As a user, I want to retrieve data from pre-ingested repositories, so that I can get fast query responses.

#### Acceptance Criteria

1. WHEN database retrieval is requested, THE DB_Retriever SHALL query the local database for repository data
2. THE DB_Retriever SHALL return Repository_Snapshot, Contributor_Record, Issue_Record, and Maintenance_Risk_Score
3. THE DB_Retriever SHALL include Data_Provenance with source=database and last_updated timestamp
4. THE DB_Retriever SHALL include score_completeness=full in Data_Provenance
5. WHEN a repository is not found in the database, THE DB_Retriever SHALL return not_found status

### Requirement 11: Live Repository Ingestion

**User Story:** As a user, I want to query repositories not in the database, so that I can analyze any GitHub repository on demand.

#### Acceptance Criteria

1. WHEN live ingestion is requested, THE Live_Repo_Ingestor SHALL invoke Ingestion_Pipeline for the specified repository
2. WHERE provisional_score mode is selected, THE Live_Repo_Ingestor SHALL fetch only Repository_Snapshot and Contributor_Record data
3. WHERE full_score mode is selected, THE Live_Repo_Ingestor SHALL fetch Repository_Snapshot, Contributor_Record, and Issue_Record data
4. WHEN live ingestion succeeds, THE Live_Repo_Ingestor SHALL compute Maintenance_Risk_Score using Feature_Engineer
5. THE Live_Repo_Ingestor SHALL include Data_Provenance with source=live_fetch and current timestamp
6. WHERE provisional_score mode is used, THE Live_Repo_Ingestor SHALL include score_completeness=provisional in Data_Provenance
7. WHERE full_score mode is used, THE Live_Repo_Ingestor SHALL include score_completeness=full in Data_Provenance
8. WHEN live ingestion fails, THE Live_Repo_Ingestor SHALL return an error with failure reason
9. THE Live_Repo_Ingestor SHALL support temporary in-query use, cache persistence via Cache_Manager with 1-hour TTL, and optional promotion to the main database based on configuration

### Requirement 12: Hybrid Query Results

**User Story:** As a user, I want to receive combined results from database and live ingestion, so that I can compare pre-ingested and newly analyzed repositories in a single query.

#### Acceptance Criteria

1. WHEN hybrid retrieval is used, THE Result_Summarizer SHALL combine results from DB_Retriever and Live_Repo_Ingestor
2. THE Result_Summarizer SHALL preserve Data_Provenance for each repository in the combined results
3. THE Result_Summarizer SHALL indicate which repositories came from database and which from live ingestion
4. THE Result_Summarizer SHALL indicate score_completeness for each repository
5. WHEN comparing repositories with different score_completeness values, THE Result_Summarizer SHALL include a warning about comparison limitations

### Requirement 13: Natural Language Answer Generation

**User Story:** As a user, I want to receive natural language answers to my queries, so that I can understand maintenance risk analysis without interpreting raw data.

#### Acceptance Criteria

1. WHEN query results are available, THE Result_Summarizer SHALL generate a natural language response
2. THE Result_Summarizer SHALL include Maintenance_Risk_Score values and risk band classifications (low, medium, high, critical)
3. THE Result_Summarizer SHALL include Data_Provenance information (source, last_updated, score_completeness)
4. WHEN multiple repositories are compared, THE Result_Summarizer SHALL rank them by Maintenance_Risk_Score
5. THE Result_Summarizer SHALL explain key contributing factors to risk scores (e.g., days_since_last_push, fraction_open_issues_stale_180d)
6. WHEN provisional scores are included, THE Result_Summarizer SHALL explain that scores are incomplete and may change with full analysis

### Requirement 14: Live Ingestion Result Caching

**User Story:** As a system administrator, I want to cache live ingestion results, so that I can avoid repeated ingestion of the same repository across multiple queries.

#### Acceptance Criteria

1. WHEN live ingestion completes, THE Cache_Manager SHALL store the results with repository identifier as key
2. THE Cache_Manager SHALL associate cached results with a timestamp
3. WHEN a live ingestion request is received for a cached repository less than 1 hour old, THE Live_Repo_Ingestor SHALL return cached results without re-ingesting
4. WHEN cached results are older than 1 hour, THE Live_Repo_Ingestor SHALL re-ingest and update the cache
5. THE Cache_Manager SHALL persist live ingestion cache to disk
6. THE Cache_Manager SHALL support optional promotion of cached live results to the main database based on configuration, enabling future queries to use database retrieval

### Requirement 15: Ingestion Performance Monitoring

**User Story:** As a system administrator, I want to monitor ingestion performance, so that I can verify API call reduction and identify bottlenecks.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL count total API calls made during ingestion
2. THE Ingestion_Pipeline SHALL measure total ingestion time per repository
3. THE Ingestion_Pipeline SHALL log API call count and ingestion time for each repository
4. WHEN ingestion completes, THE Ingestion_Pipeline SHALL report average API calls per repository
5. WHEN ingestion completes, THE Ingestion_Pipeline SHALL report average ingestion time per repository
6. THE Ingestion_Pipeline SHALL report rate limit quota remaining after ingestion

### Requirement 16: Error Handling and Resilience

**User Story:** As a system administrator, I want robust error handling, so that partial failures do not block entire ingestion or query operations.

#### Acceptance Criteria

1. WHEN a GraphQL query fails, THE GraphQL_Client SHALL retry up to 3 times with exponential backoff
2. WHEN a REST API call fails, THE REST_Client SHALL retry up to 3 times with exponential backoff
3. IF a repository fetch fails after retries, THE Ingestion_Pipeline SHALL log the error and continue with remaining repositories
4. WHEN a live ingestion fails during query execution, THE Result_Summarizer SHALL return partial results with an error message for the failed repository
5. WHEN rate limit is exceeded, THE Rate_Limiter SHALL wait until reset time and resume operations
6. THE API_Client SHALL handle network timeouts with 30-second timeout limit per request

### Requirement 17: Backward Compatibility

**User Story:** As a system administrator, I want the new ingestion system to be compatible with existing components, so that I can deploy without breaking existing functionality.

#### Acceptance Criteria

1. THE Feature_Engineer SHALL output features matching the schema in feature_mapping_config.py
2. THE Ingestion_Pipeline SHALL persist data to the existing database schema
3. THE Query_Parser SHALL support all existing query intents from intent_executor.py
4. THE DB_Retriever SHALL return data in the same format as existing query responses
5. THE Maintenance_Risk_Score computation SHALL use weights from composite_config.yaml
6. THE Ingestion_Pipeline SHALL maintain compatibility with existing CLI commands in cli/ingest.py

### Requirement 18: Configuration and Extensibility

**User Story:** As a developer, I want configurable ingestion and query behavior, so that I can tune performance and add new features without code changes.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL read configuration from a config file specifying batch sizes, retry limits, and timeout values
2. THE Cache_Manager SHALL read cache TTL values from configuration
3. THE Rate_Limiter SHALL read rate limit thresholds from configuration
4. THE Retrieval_Strategy SHALL read default score mode (provisional vs full) from configuration
5. WHERE configuration values are not provided, THE system SHALL use documented default values
6. THE configuration file SHALL be in YAML or JSON format

### Requirement 19: GraphQL Query Batching and Pagination

**User Story:** As a system administrator, I want efficient GraphQL batching, so that I can minimize API calls when ingesting multiple repositories.

#### Acceptance Criteria

1. WHEN ingesting multiple repositories, THE Repo_Snapshot_Fetcher SHALL support configurable GraphQL batching with a default target batch size tuned to stay within GitHub query cost and complexity limits
2. WHEN a GraphQL response contains pagination cursors, THE Repo_Snapshot_Fetcher SHALL fetch subsequent pages
3. THE Repo_Snapshot_Fetcher SHALL parse GraphQL errors and identify which repositories in a batch failed
4. WHEN a repository in a batch fails, THE Repo_Snapshot_Fetcher SHALL return partial results for successful repositories
5. THE GraphQL_Client SHALL construct queries using GraphQL aliases to distinguish repositories in batched responses

### Requirement 20: Data Provenance Tracking

**User Story:** As a user, I want to know the source and freshness of query results, so that I can assess data reliability and make informed decisions.

#### Acceptance Criteria

1. THE Result_Summarizer SHALL include Data_Provenance for every repository in query results
2. THE Data_Provenance SHALL include source field with values: database or live_fetch
3. THE Data_Provenance SHALL include last_updated timestamp in ISO 8601 format
4. THE Data_Provenance SHALL include score_completeness field with values: provisional or full
5. WHERE score_completeness is provisional, THE Data_Provenance SHALL list which feature categories are missing (e.g., issue_lifecycle_metrics)
6. THE Result_Summarizer SHALL display Data_Provenance in natural language responses


### Requirement 21: Entity Identifier Normalization

**User Story:** As a system, I want to normalize repository, package, and dependency identifiers into canonical forms, so that I can correctly match entities regardless of how users express them.

#### Acceptance Criteria

1. WHEN repository, package, or ecosystem identifiers are expressed in alternate forms, THE Query_Parser and Entity_Extractor SHALL normalize them to the system's internal canonical identifier where possible
2. THE Entity_Extractor SHALL normalize package names to their canonical repository identifiers (e.g., "numpy" → "numpy/numpy")
3. THE Entity_Extractor SHALL normalize repository references with missing owner to include owner when unambiguous
4. THE Entity_Extractor SHALL normalize import names to package names where mappings are known
5. THE Coverage_Checker SHALL use normalized identifiers when checking database coverage
6. THE system SHALL maintain a normalization mapping table for common package-to-repo conversions

### Requirement 22: Partial Feature Coverage Handling

**User Story:** As a system, I want to handle cases where repository data is incomplete, so that I can avoid returning misleading risk scores.

#### Acceptance Criteria

1. WHEN a repository cannot be fully evaluated because some raw data sources are unavailable, THE system SHALL return a score only if the configured minimum feature coverage threshold is met
2. THE Feature_Engineer SHALL identify which feature categories are missing when data sources fail (e.g., issue_lifecycle_metrics, contributor_metrics)
3. THE system SHALL read minimum_feature_coverage_threshold from configuration (default: 0.6, meaning 60% of weighted features must be available)
4. WHEN feature coverage falls below the threshold, THE Live_Repo_Ingestor SHALL return an error indicating insufficient data
5. WHEN feature coverage meets the threshold but is incomplete, THE Data_Provenance SHALL identify missing feature categories
6. THE Result_Summarizer SHALL explain which feature categories are missing and how this affects score reliability
