# Requirements Document

## Introduction

This feature expands the open source risk model dataset from 51 repositories to 200 repositories, representing a 4x increase in scale. The validation phase proved the system is production-ready with 89.22% resolution rate across 3,691 dependencies. This expansion will generate more compelling insights while maintaining system performance and data quality standards.

The expansion targets 15,000-50,000 total dependencies while ensuring query performance remains under 5 seconds and resolution rates stay above 85%. The feature leverages existing proven capabilities: batch ingestion CLI, popular repos script, multi-repo database schema, and cross-repo query API.

**⚠️ SCOPE LIMITATION DISCOVERED (March 9, 2026)**: Production validation revealed that the system currently supports only **2 ecosystems (npm, PyPI)** instead of the originally specified 5 ecosystems. Parsers for Go (`go.mod`), Maven (`pom.xml`, `build.gradle`), and RubyGems (`Gemfile`) are not yet implemented. See `PRODUCTION_VALIDATION_FINDINGS.md` for details.

**SUPPORTED ECOSYSTEMS**: npm, PyPI  
**FUTURE WORK**: Go, Maven, RubyGems (requires parser implementation)

## Glossary

- **Ingestion_Pipeline**: The batch ingestion system that processes repository lists and extracts dependency data
- **Resolution_Rate**: Percentage of dependencies successfully resolved to package registry metadata
- **Resolved_Dependency**: A dependency where the package is matched to a registry, version is parsed, and registry metadata is retrieved
- **Dataset**: The collection of repositories and their dependency graphs stored in the database
- **Repo_Selection_Criteria**: Rules for choosing which repositories to add based on popularity, ecosystem diversity, and value
- **Query_Performance**: Time required to execute cross-repository dependency queries
- **Data_Quality_Validator**: System that verifies ingested data meets quality standards
- **Ingestion_Monitor**: Tool that tracks progress and status of batch ingestion operations
- **Popular_Repos_Script**: Existing script at scripts/populate_popular_repos.py that identifies high-value repositories
- **Dependency_Depth**: The maximum number of transitive dependency levels in a dependency chain
- **Average_Dependency_Depth**: The mean depth across all dependency chains in a repository
- **Ecosystem_Distribution**: The percentage breakdown of repositories by package ecosystem
- **Cross_Repository_Insight**: A pattern or metric visible only when analyzing multiple repositories together
- **Duplicate_Repository**: A repository that is a fork or has an identical dependency graph to an existing repository in the dataset

## Requirements

### Requirement 1: Repository Selection

**User Story:** As a system administrator, I want clear criteria for selecting 149 additional repositories, so that the expanded dataset provides maximum value across diverse ecosystems.

#### Acceptance Criteria

1. THE Repo_Selection_Criteria SHALL prioritize repositories with >1000 GitHub stars
2. THE Repo_Selection_Criteria SHALL include repositories from at least 5 different package ecosystems (npm, PyPI, Maven, RubyGems, Go)  
   **⚠️ BLOCKED**: Only npm and PyPI parsers are currently implemented. Go, Maven, and RubyGems require parser implementation before this criterion can be met. See `PRODUCTION_VALIDATION_FINDINGS.md`.
3. THE Repo_Selection_Criteria SHALL favor repositories with active maintenance (commits within last 6 months)
4. THE Repo_Selection_Criteria SHALL include repositories with diverse dependency patterns (monorepos, microservices, libraries, applications)
5. WHERE a repository has multiple manifest files, THE Repo_Selection_Criteria SHALL prioritize repositories with production dependencies over development-only dependencies
6. THE Repo_Selection_Criteria SHALL exclude repositories that are forks of existing repositories in the Dataset
7. THE Repo_Selection_Criteria SHALL exclude repositories with dependency graphs identical to existing repositories in the Dataset

### Requirement 2: Repository List Generation

**User Story:** As a system administrator, I want an automated way to generate a prioritized list of 149 repositories, so that I can efficiently expand the dataset.

#### Acceptance Criteria

1. THE Popular_Repos_Script SHALL generate a list of 149 repositories matching the Repo_Selection_Criteria
2. THE Popular_Repos_Script SHALL output repositories in priority order (highest value first)
3. THE Popular_Repos_Script SHALL include repository metadata (stars, ecosystem, last commit date)
4. WHEN the Popular_Repos_Script encounters API rate limits, THE Popular_Repos_Script SHALL implement exponential backoff
5. THE Popular_Repos_Script SHALL exclude repositories already present in the Dataset

### Requirement 3: Batch Ingestion Execution

**User Story:** As a system administrator, I want to ingest 149 repositories using the proven batch ingestion pipeline, so that the dataset expands reliably.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL process the repository list using the existing batch ingestion CLI
2. WHEN ingesting 149 repositories, THE Ingestion_Pipeline SHALL complete within 24 hours
3. THE Ingestion_Pipeline SHALL maintain the existing resolution rate of at least 85%
4. IF a repository ingestion fails, THEN THE Ingestion_Pipeline SHALL log the error and continue with remaining repositories
5. THE Ingestion_Pipeline SHALL store all dependency data in the existing multi-repo database schema

### Requirement 4: Ingestion Progress Monitoring

**User Story:** As a system administrator, I want to monitor ingestion progress in real-time, so that I can identify and address issues quickly.

#### Acceptance Criteria

1. THE Ingestion_Monitor SHALL display the count of repositories processed, pending, and failed
2. THE Ingestion_Monitor SHALL display the current resolution rate across all ingested repositories
3. THE Ingestion_Monitor SHALL display estimated time remaining for batch completion
4. WHEN a repository fails ingestion, THE Ingestion_Monitor SHALL display the failure reason
5. THE Ingestion_Monitor SHALL update progress metrics at least every 60 seconds

### Requirement 5: Data Quality Validation

**User Story:** As a system administrator, I want automated validation of ingested data quality, so that the expanded dataset meets production standards.

#### Acceptance Criteria

1. WHEN ingestion completes, THE Data_Quality_Validator SHALL verify the total repository count equals 200
2. THE Data_Quality_Validator SHALL verify the total dependency count is between 15,000 and 50,000
3. THE Data_Quality_Validator SHALL verify the Resolution_Rate is at least 85%
4. THE Data_Quality_Validator SHALL verify at least 5 different package ecosystems are represented
5. THE Data_Quality_Validator SHALL verify npm repositories represent between 25% and 40% of the Dataset
6. THE Data_Quality_Validator SHALL verify PyPI repositories represent between 25% and 40% of the Dataset
7. THE Data_Quality_Validator SHALL verify Go repositories represent at least 10% of the Dataset
8. THE Data_Quality_Validator SHALL verify Maven repositories represent at least 10% of the Dataset
9. THE Data_Quality_Validator SHALL verify RubyGems repositories represent at least 5% of the Dataset
10. IF validation fails, THEN THE Data_Quality_Validator SHALL generate a detailed failure report

### Requirement 5A: Resolution Rate Definition

**User Story:** As a developer, I want a precise definition of resolution rate, so that the metric remains consistent over time and prevents drift.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL count a dependency as a Resolved_Dependency only when the package is matched to a registry
2. THE Ingestion_Pipeline SHALL count a dependency as a Resolved_Dependency only when the version is successfully parsed
3. THE Ingestion_Pipeline SHALL count a dependency as a Resolved_Dependency only when registry metadata is retrieved
4. WHEN calculating Resolution_Rate, THE Ingestion_Pipeline SHALL divide Resolved_Dependency count by total dependency count
5. THE Ingestion_Pipeline SHALL document any dependency that fails any of the three resolution criteria

### Requirement 5B: Dependency Depth Validation

**User Story:** As a security analyst, I want to validate dependency depth metrics, so that I can identify repositories with deep supply chain structures that hide risk.

#### Acceptance Criteria

1. WHEN ingestion completes, THE Data_Quality_Validator SHALL calculate Average_Dependency_Depth for each repository
2. THE Data_Quality_Validator SHALL calculate maximum Dependency_Depth for each repository
3. THE Data_Quality_Validator SHALL verify at least 10 repositories have Dependency_Depth greater than 5 levels
4. THE Data_Quality_Validator SHALL include Average_Dependency_Depth in the validation report
5. THE Data_Quality_Validator SHALL include maximum Dependency_Depth distribution in the validation report

### Requirement 6: Query Performance Validation

**User Story:** As a developer, I want query performance to remain fast after dataset expansion, so that the system stays responsive.

#### Acceptance Criteria

1. WHEN executing cross-repository dependency queries, THE Query_Performance SHALL remain under 5 seconds
2. THE Query_Performance SHALL be measured using the existing query API test suite
3. IF query performance exceeds 5 seconds, THEN THE Data_Quality_Validator SHALL flag performance degradation
4. THE Query_Performance SHALL be validated with at least 10 different query patterns
5. THE Query_Performance SHALL be measured after database indexes are rebuilt

### Requirement 7: Rollback Capability

**User Story:** As a system administrator, I want the ability to rollback to the 51-repository dataset, so that I can recover from expansion failures.

#### Acceptance Criteria

1. WHEN starting dataset expansion, THE Ingestion_Pipeline SHALL create a database backup
2. THE Ingestion_Pipeline SHALL store the backup with a timestamp identifier
3. WHERE expansion fails validation, THE Ingestion_Pipeline SHALL provide a rollback command
4. WHEN executing rollback, THE Ingestion_Pipeline SHALL restore the database to the pre-expansion state
5. THE Ingestion_Pipeline SHALL verify the restored database contains exactly 51 repositories

### Requirement 8: Expansion Documentation

**User Story:** As a developer, I want clear documentation of the expansion process, so that I can understand what changed and reproduce the process.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL generate a summary report listing all 149 newly added repositories
2. THE Ingestion_Pipeline SHALL document the final dependency count and resolution rate
3. THE Ingestion_Pipeline SHALL document any repositories that failed ingestion
4. THE Ingestion_Pipeline SHALL document query performance metrics before and after expansion
5. THE Ingestion_Pipeline SHALL document the Ecosystem_Distribution across all 200 repositories

### Requirement 9: Signal Quality Validation

**User Story:** As a product manager, I want to validate that dataset expansion produces new actionable insights, so that I can ensure the expansion delivers customer value beyond just data volume.

#### Acceptance Criteria

1. WHEN expansion completes, THE Data_Quality_Validator SHALL identify at least 5 Cross_Repository_Insights not visible in the 51-repository dataset
2. THE Data_Quality_Validator SHALL identify dependency hub packages used across more than 25% of repositories
3. THE Data_Quality_Validator SHALL identify the 10 repositories with highest Dependency_Depth
4. THE Data_Quality_Validator SHALL identify packages with the largest transitive dependency footprint
5. THE Data_Quality_Validator SHALL identify new ecosystem-specific dependency patterns
6. THE Data_Quality_Validator SHALL document each Cross_Repository_Insight with supporting metrics
7. IF fewer than 5 Cross_Repository_Insights are found, THEN THE Data_Quality_Validator SHALL flag insufficient signal quality
