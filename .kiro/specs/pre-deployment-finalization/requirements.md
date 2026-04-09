# Requirements Document

## Introduction

Pre-Deployment Finalization prepares Deep Signal for production deployment and demo use. The scope covers retrying rate-limited repository ingestion, curating a demo-ready repository set, wiring homepage data from that curated list, surfacing dataset coverage statistics in the UI and API, performing end-to-end QA validation, and completing deployment configuration. This feature explicitly excludes expanding parser support (Go, Java, Ruby) and focuses on maximizing quality and usability of the existing dataset.

## Glossary

- **Deep_Signal**: The open-source risk intelligence application comprising a FastAPI backend, SQLite database, and static HTML/JS frontend.
- **Demo_Repo_Config**: A YAML configuration file at `src/open_source_risk_model/config/demo_repos.yaml` containing a curated list of repositories for demo and homepage use.
- **Demo_Repository**: A repository entry in Demo_Repo_Config that has dependency tree data, meaningful graph structure, and non-trivial insight signals.
- **Ingestion_Pipeline**: The sequence of dependency parsing, transitive resolution, graph enrichment, and insight computation that produces a fully analyzed repository.
- **Homepage**: The `ui/index.html` page serving as the entry point to Deep Signal.
- **Insights_Page**: The `ui/insights.html` page displaying risk scores, signals, and trends.
- **Stats_Endpoint**: An optional API endpoint at `/api/stats` returning dataset coverage metadata.
- **Rate_Limited_Repo**: A repository whose dependency parsing previously failed due to GitHub API 403 rate-limit responses (specifically pyyaml/pyyaml and ytdl-org/youtube-dl).
- **Dependency_Tree**: The hierarchical structure of direct and transitive dependencies for a repository, stored in the `resolved_dependencies` table.
- **Coverage_Ratio**: The fraction of total analyzed repositories that have full dependency tree data.

## Requirements

### Requirement 1: Retry Rate-Limited Repository Ingestion

**User Story:** As a data operator, I want to re-run dependency parsing for previously rate-limited Python repositories, so that the dataset has complete coverage for all supported ecosystems.

#### Acceptance Criteria

1. WHEN the retry script is executed for a Rate_Limited_Repo, THE Ingestion_Pipeline SHALL parse direct dependencies from the repository manifest files.
2. WHEN direct dependencies are parsed for a Rate_Limited_Repo, THE Ingestion_Pipeline SHALL resolve transitive dependencies to a depth of at least 3.
3. WHEN transitive resolution completes for a Rate_Limited_Repo, THE Ingestion_Pipeline SHALL enrich the repository graph with the resolved dependency data.
4. WHEN the full Ingestion_Pipeline completes for a Rate_Limited_Repo, THE Deep_Signal dependency tree page SHALL render the dependency tree with edges and nodes for that repository.
5. WHEN the full Ingestion_Pipeline completes for a Rate_Limited_Repo, THE Deep_Signal insights page SHALL compute insight scores for that repository without falling back to default values.
6. IF dependency parsing fails for a Rate_Limited_Repo due to a repeated rate-limit error, THEN THE Ingestion_Pipeline SHALL log the failure with the HTTP status code and repository name and exit with a non-zero status code.

### Requirement 2: Demo-Ready Repository Configuration

**User Story:** As a product demonstrator, I want a curated list of high-quality repositories available in a static configuration file, so that demos consistently showcase repositories with rich data.

#### Acceptance Criteria

1. THE Demo_Repo_Config SHALL contain between 15 and 25 repository entries.
2. THE Demo_Repo_Config SHALL store each entry as an `owner/repo` string with an optional list of tags.
3. THE Demo_Repo_Config SHALL support the following tag values: `high-risk`, `deep-tree`, `well-maintained`, `popular`, and `vulnerable`.
4. WHEN the Demo_Repo_Config is loaded, THE Deep_Signal configuration loader SHALL validate that each listed repository exists in the `repo_graphs` database table.
5. WHEN the Demo_Repo_Config is loaded, THE Deep_Signal configuration loader SHALL validate that each listed repository has at least one entry in the `repo_dependencies` database table.
6. WHEN the Demo_Repo_Config is loaded, THE Deep_Signal configuration loader SHALL validate that each listed repository has a computed insight with a non-null score.
7. IF a repository in Demo_Repo_Config fails validation, THEN THE Deep_Signal configuration loader SHALL log a warning identifying the repository and the missing data category.

### Requirement 3: Homepage Data Wiring

**User Story:** As a first-time user, I want the homepage to display real, curated repositories instead of hardcoded placeholders, so that I can immediately explore meaningful data.

#### Acceptance Criteria

1. WHEN the Homepage loads, THE Homepage SHALL read repository entries from Demo_Repo_Config to populate the "Explore Repositories" section.
2. WHEN the Homepage renders a repository chip, THE Homepage SHALL display the repository name, owner, and a risk-level indicator dot derived from the repository insight data.
3. WHEN a user clicks a repository chip on the Homepage, THE Homepage SHALL navigate to the Insights_Page with the selected repository pre-loaded via the `?repo=` query parameter.
4. THE Homepage SHALL display a trust signal line reading "Analyzing {N}+ open-source repositories across dependency graphs, contributors, and vulnerability data" where {N} is the total number of analyzed repositories retrieved from the Stats_Endpoint or Demo_Repo_Config metadata.
5. WHEN the Homepage loads and the Stats_Endpoint is unreachable, THE Homepage SHALL fall back to displaying the repository count from Demo_Repo_Config metadata or a static default value.
6. WHEN a user enters a repository name in the Homepage search bar and activates the scan action, THE Homepage SHALL navigate to the Insights_Page with a smooth transition preserving the repository context in the URL.

### Requirement 4: Dataset Coverage Statistics

**User Story:** As a stakeholder, I want to see how many repositories Deep Signal has analyzed and what percentage have full dependency coverage, so that I can assess the platform's data completeness.

#### Acceptance Criteria

1. THE Stats_Endpoint SHALL return a JSON response containing `total_repos`, `fully_analyzed_repos`, and `coverage_ratio` fields.
2. WHEN the Stats_Endpoint is called, THE Stats_Endpoint SHALL compute `total_repos` as the count of distinct repositories in the `repo_graphs` database table.
3. WHEN the Stats_Endpoint is called, THE Stats_Endpoint SHALL compute `fully_analyzed_repos` as the count of distinct repositories present in both the `repo_graphs` and `repo_dependencies` database tables.
4. WHEN the Stats_Endpoint is called, THE Stats_Endpoint SHALL compute `coverage_ratio` as `fully_analyzed_repos` divided by `total_repos`, rounded to two decimal places.
5. IF `total_repos` is zero, THEN THE Stats_Endpoint SHALL return `coverage_ratio` as 0.00.
6. THE Homepage SHALL display the `total_repos` value in a visible UI element within the hero section or footer area.
7. THE Insights_Page SHALL display the `total_repos` and `coverage_ratio` values in a header or summary area.

### Requirement 5: Pre-Deployment QA Validation

**User Story:** As a developer, I want an automated QA validation script that tests demo repositories end-to-end across all API endpoints, so that I can confirm the application is ready for deployment.

#### Acceptance Criteria

1. WHEN the QA validation script is executed, THE QA_Script SHALL test at least 5 Demo_Repository entries from Demo_Repo_Config.
2. WHEN testing a Demo_Repository, THE QA_Script SHALL verify that the `/api/insights/{owner}/{repo}` endpoint returns a 200 status with a non-null `score` field.
3. WHEN testing a Demo_Repository, THE QA_Script SHALL verify that the `/api/graph?repo={owner}/{repo}` endpoint returns a 200 status with at least one node and one edge.
4. WHEN testing a Demo_Repository, THE QA_Script SHALL verify that the `/repos/{owner}/{repo}/dependency-tree` endpoint returns a 200 status with a non-empty `tree` object.
5. WHEN testing a Demo_Repository, THE QA_Script SHALL verify that the `/api/score?repo={owner}/{repo}` endpoint returns a 200 status.
6. IF any endpoint returns an error status or empty data for a Demo_Repository, THEN THE QA_Script SHALL report the failure with the repository name, endpoint path, HTTP status code, and response body summary.
7. WHEN all tests complete, THE QA_Script SHALL print a summary reporting the count of passed tests, failed tests, and total tests.

### Requirement 6: Deployment Configuration

**User Story:** As a deployment engineer, I want documented and validated deployment configuration, so that the backend and frontend can be deployed to a public URL with correct environment settings.

#### Acceptance Criteria

1. THE Deep_Signal deployment configuration SHALL specify the required environment variables: `GITHUB_TOKEN`, `OPENAI_API_KEY`, `GRAPH_DB_PATH`, and `GRAPH_DB_ENABLED`.
2. WHEN the FastAPI backend starts, THE Deep_Signal backend SHALL validate that `GITHUB_TOKEN` is set and log a warning if it is missing.
3. WHEN the FastAPI backend starts, THE Deep_Signal backend SHALL configure CORS to allow requests from the configured frontend origin.
4. THE Deep_Signal deployment documentation SHALL include steps to deploy the FastAPI backend and serve the static frontend files.
5. WHEN the public URL is loaded in a browser, THE Deep_Signal frontend SHALL load the Homepage and render navigation links to Insights, Graph, and Dependency Tree pages.
6. WHEN the frontend makes an API request, THE Deep_Signal backend SHALL respond with appropriate CORS headers allowing the request from the frontend origin.
7. IF the `GITHUB_TOKEN` environment variable is not set, THEN THE Deep_Signal backend SHALL continue to operate in a degraded mode with rate-limited GitHub API access and log a startup warning.
