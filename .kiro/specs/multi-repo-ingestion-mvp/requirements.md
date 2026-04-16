# Requirements Document

## Introduction

Multi-Repo Ingestion MVP transforms Deep Signal from a single-repository analysis tool into a system that can analyze a software system defined by repositories and dependencies, and surface prioritized risk across the system. Users define an "Analysis Scope" containing multiple repos or dependency names, trigger a single ingestion, and receive a unified risk overview that highlights what to fix first — not just which repos are risky, but which dependencies, maintainers, and vulnerabilities pose the greatest system-wide risk. This is an MVP: no authentication, no database persistence for scopes, and no framework — static HTML/CSS/JS frontend only.

## Glossary

- **Analysis_Scope**: A named, in-memory collection of repository identifiers and/or dependency package names that are analyzed together as one unit representing a software system.
- **Scope_Store**: An in-memory dictionary on the backend that holds active Analysis_Scope objects keyed by scope ID. No database persistence is required.
- **Ingestion_Endpoint**: The POST /api/ingest-scope backend endpoint that accepts a scope definition and triggers analysis for each item.
- **Overview_Page**: The ui/overview.html page that displays the unified system risk summary for an Analysis_Scope.
- **Homepage**: The ui/index.html page where users enter repositories for analysis.
- **Nav_Module**: The shared navigation module (ui/nav.js) that renders the top navigation bar across all pages.
- **Score_Pipeline**: The existing score_repo function that fetches GitHub data and computes maintenance risk scores for a single repository.
- **Graph_Pipeline**: The existing build_graph function that constructs a supply chain graph for a single repository.
- **Insight_Pipeline**: The existing compute_repo_insight function that computes risk insights from a stored graph.
- **Merged_Graph**: A combined graph produced by unioning the nodes and edges from individual repository graphs within a single Analysis_Scope, with nodes tracking which source repos they came from.
- **System_Risk_Summary**: An aggregated object containing both repo-level and dependency-level risk metrics, priority risks, and per-repo breakdowns for an Analysis_Scope.
- **Priority_Risk**: A ranked risk item (dependency, repo, maintainer, or CVE) surfaced as a prioritized action item across the entire scope.
- **Scope_ID**: A unique string identifier generated server-side for each Analysis_Scope.

## Requirements

### Requirement 1: Analysis Scope Data Model

**User Story:** As a developer, I want to define a set of repositories and dependencies as a single analysis scope, so that I can evaluate risk across my entire software system at once.

#### Acceptance Criteria

1. THE Scope_Store SHALL represent each Analysis_Scope as an object containing a Scope_ID, a human-readable name, a list of repository identifiers (in owner/repo format), a list of dependency package names, and a status field.
2. WHEN a new Analysis_Scope is created, THE Scope_Store SHALL generate a unique Scope_ID and store the scope in memory.
3. THE Scope_Store SHALL support at least 20 concurrent Analysis_Scope objects without degradation.
4. WHEN the backend process restarts, THE Scope_Store SHALL start with an empty state (no persistence required).
5. THE Analysis_Scope status field SHALL support the following values: "processing", "complete", "partial" (some repos failed), and "failed" (all repos failed).

### Requirement 2: Multi-Repo Ingestion Endpoint

**User Story:** As a developer, I want to submit multiple repositories and dependency names in a single API call, so that I can trigger system-wide analysis without making individual requests.

#### Acceptance Criteria

1. WHEN a POST request is sent to /api/ingest-scope with a JSON body containing a scope name, a list of repository identifiers, and an optional list of dependency package names, THE Ingestion_Endpoint SHALL create a new Analysis_Scope and return the Scope_ID with HTTP status 202.
2. WHEN the Ingestion_Endpoint receives a request with an empty repos list and an empty dependencies list, THE Ingestion_Endpoint SHALL return HTTP 422 with a descriptive error message.
3. WHEN the Ingestion_Endpoint receives a request with more than 10 repository identifiers, THE Ingestion_Endpoint SHALL return HTTP 422 indicating the maximum allowed count (constrained for MVP performance).
4. WHEN the Ingestion_Endpoint processes each repository in the scope, THE Ingestion_Endpoint SHALL call the existing Score_Pipeline for scoring and the Graph_Pipeline for graph construction.
5. IF the Score_Pipeline or Graph_Pipeline fails for one repository, THEN THE Ingestion_Endpoint SHALL record the error for that repository and continue processing the remaining repositories.
6. WHEN all repositories in the scope have been processed, THE Ingestion_Endpoint SHALL merge individual graphs into a single Merged_Graph by unioning nodes and edges, deduplicating nodes by node ID, and tracking which source repos each node came from.
7. THE Merged_Graph SHALL preserve relationship types on edges and support cross-repo relationships where the same dependency node is referenced by multiple repository graphs.
8. WHEN all repositories in the scope have been processed, THE Ingestion_Endpoint SHALL compute a System_Risk_Summary containing repo-level metrics (total repo count, count of high/medium/low-risk repos, average maintenance risk score, per-repo results) AND dependency-level metrics (total unique dependencies, dependencies used by multiple repos, high-risk dependencies based on dependency risk scores, vulnerable dependencies with CVEs, dependency concentration flags).
9. WHEN dependencies are provided in the input, THE Ingestion_Endpoint SHALL resolve each dependency into a package node in the Merged_Graph and attempt best-effort mapping to a GitHub repository. Dependency-to-repository mapping is best-effort for MVP and may be incomplete.
10. THE Ingestion_Endpoint SHALL update the Analysis_Scope status to "processing" when ingestion begins, "complete" when all repos succeed, "partial" when some repos fail, and "failed" when all repos fail.
11. THE Ingestion_Endpoint SHALL compute a list of Priority_Risk items (top 3–5) ranked across the entire scope, where each item includes a name, type (dependency/repo/maintainer/CVE), reason, and severity level.

### Requirement 3: Scope Retrieval Endpoint

**User Story:** As a frontend developer, I want to retrieve the results of a completed analysis scope, so that I can render the unified system risk overview.

#### Acceptance Criteria

1. WHEN a GET request is sent to /api/scope/{scope_id}, THE Ingestion_Endpoint SHALL return the Analysis_Scope object including its status, System_Risk_Summary, Priority_Risk list, and Merged_Graph.
2. IF the requested Scope_ID does not exist in the Scope_Store, THEN THE Ingestion_Endpoint SHALL return HTTP 404 with a descriptive error message.
3. WHILE the Analysis_Scope status is "processing", THE Ingestion_Endpoint SHALL return the partial results available so far along with the current status.

### Requirement 4: Homepage Multi-Repo Input

**User Story:** As a user, I want to toggle between analyzing a single repo and analyzing multiple repos on the homepage, so that I can choose the appropriate mode for my needs.

#### Acceptance Criteria

1. THE Homepage SHALL display a toggle control allowing the user to switch between "Single Repo" mode and "Multi-Repo" mode.
2. WHILE the Homepage is in "Single Repo" mode, THE Homepage SHALL display the existing single repository input field and "Scan a Repository" button with unchanged behavior.
3. WHILE the Homepage is in "Multi-Repo" mode, THE Homepage SHALL display a textarea input for entering multiple repository identifiers (one per line) and a scope name input field.
4. WHILE the Homepage is in "Multi-Repo" mode, THE Homepage SHALL display an "Analyze System" button that submits the list to the Ingestion_Endpoint.
5. WHEN the user clicks "Analyze System", THE Homepage SHALL send a POST request to /api/ingest-scope and redirect to the Overview_Page with the returned Scope_ID as a query parameter.
6. IF the Ingestion_Endpoint returns an error, THEN THE Homepage SHALL display the error message inline without navigating away.

### Requirement 5: Unified System Risk Overview Page

**User Story:** As a user, I want to see a single dashboard summarizing system-wide risk across all repositories in my analysis scope, so that I can quickly identify what to fix first.

#### Acceptance Criteria

1. THE Overview_Page SHALL read the scope_id query parameter from the URL and fetch scope data from GET /api/scope/{scope_id}.
2. WHEN scope data is loaded, THE Overview_Page SHALL display KPI cards showing: total repositories analyzed, total unique dependencies, high-risk dependencies count, vulnerable dependencies count, and aggregate system risk score with label.
3. WHEN scope data is loaded, THE Overview_Page SHALL display a "Priority Risks" section showing the top 3–5 Priority_Risk items across the entire scope, each displaying name, type (dependency/repo/maintainer/CVE), reason, and severity.
4. WHEN scope data is loaded, THE Overview_Page SHALL display a "Top Risk Drivers" section listing the top 5 repositories sorted by descending risk score, each showing repo name, risk label, and risk score.
5. WHEN scope data is loaded, THE Overview_Page SHALL display a "Risky Dependencies" section listing high-risk dependencies sorted by risk score, each showing package name, risk score, which repos depend on it, and CVE count if applicable.
6. WHILE the Analysis_Scope status is "processing", THE Overview_Page SHALL display a loading indicator and poll GET /api/scope/{scope_id} every 3 seconds until the status changes to "complete" or "partial", with a maximum polling timeout of 60 seconds.
7. IF the scope_id parameter is missing or the scope is not found, THEN THE Overview_Page SHALL display an error message with a link back to the Homepage.
8. THE Overview_Page SHALL use the existing design system (ui/design-system.css) for all visual styling.
9. WHEN the user clicks a repository name in the Top Risk Drivers list, THE Overview_Page SHALL navigate to the Insights page for that repository.

### Requirement 6: Navigation Update

**User Story:** As a user, I want to access the Overview page from any page in the application, so that I can quickly navigate to the system risk summary.

#### Acceptance Criteria

1. THE Nav_Module SHALL include an "Overview" entry in the NAV_PAGES array linking to overview.html.
2. WHEN a scope_id query parameter is present in the URL, THE Nav_Module SHALL propagate the scope_id parameter to the Overview link.
3. THE Nav_Module SHALL render the "Overview" link between "Home" and "Insights" in the navigation bar.

### Requirement 7: Scope-Aware Graph and Tree Pages

**User Story:** As a user, I want to view merged graph and dependency tree data for my entire analysis scope, so that I can explore cross-repo relationships.

#### Acceptance Criteria

1. WHEN the graph.html page receives a scope_id query parameter, THE Graph_Pipeline SHALL fetch the Merged_Graph from GET /api/scope/{scope_id} and render it instead of a single-repo graph.
2. WHEN the dependency-tree.html page receives a scope_id query parameter, THE dependency-tree page SHALL display a combined tree view sourced from the scope data.
3. WHILE a scope_id parameter is present, THE graph.html and dependency-tree.html pages SHALL hide the single-repo input controls and display the scope name as the page title.

### Requirement 8: Backend Tests

**User Story:** As a developer, I want automated tests for the multi-repo ingestion endpoint, so that I can verify correctness of scope creation, per-repo processing, graph merging, and system risk aggregation.

#### Acceptance Criteria

1. THE test suite SHALL include a test verifying that POST /api/ingest-scope with valid repos returns HTTP 202 and a Scope_ID.
2. THE test suite SHALL include a test verifying that POST /api/ingest-scope with an empty repos list and empty dependencies list returns HTTP 422.
3. THE test suite SHALL include a test verifying that POST /api/ingest-scope with more than 10 repos returns HTTP 422.
4. THE test suite SHALL include a test verifying that GET /api/scope/{scope_id} returns the complete System_Risk_Summary including dependency-level metrics after processing.
5. THE test suite SHALL include a test verifying that GET /api/scope/{nonexistent_id} returns HTTP 404.
6. THE test suite SHALL include a test verifying that graph merging deduplicates nodes with the same node ID across repos and tracks source repos on merged nodes.
7. THE test suite SHALL include a test verifying that partial failures (one repo fails, others succeed) produce a valid System_Risk_Summary with error details for the failed repo and status "partial".
8. THE test suite SHALL include a test verifying that Priority_Risk items are computed and ranked by severity across the scope.

### Requirement 9: Frontend Overview Page Tests

**User Story:** As a developer, I want automated tests for the overview page logic, so that I can verify KPI computation, priority risk rendering, polling behavior, and error handling.

#### Acceptance Criteria

1. THE test suite SHALL include a test verifying that KPI values are correctly computed from scope data (repo count, unique dependencies, high-risk dependencies, vulnerable dependencies, aggregate score).
2. THE test suite SHALL include a test verifying that the Priority Risks section renders items with name, type, reason, and severity.
3. THE test suite SHALL include a test verifying that the Top Risk Drivers list is sorted by descending risk score and limited to 5 entries.
4. THE test suite SHALL include a test verifying that the overview page displays an error message when scope_id is missing.
5. THE test suite SHALL include a test verifying that the overview page polls while status is "processing" and stops polling when status is "complete" or after 60 seconds.

## Non-Goals

- No authentication or user accounts
- No database persistence for scopes (in-memory only)
- No GitHub OAuth or org-level integrations
- No full dependency parser system — dependency-to-repo mapping is best-effort
- No framework migration — remains static HTML/CSS/JS
- No real-time WebSocket updates — polling only

## Data Contracts

### POST /api/ingest-scope — Request

```json
{
  "name": "My Project Stack",
  "repos": ["numpy/numpy", "pandas-dev/pandas", "psf/requests"],
  "dependencies": ["flask", "sqlalchemy"]
}
```

### POST /api/ingest-scope — Response (202)

```json
{
  "scope_id": "scope_abc123",
  "status": "processing"
}
```

### GET /api/scope/{scope_id} — Response

```json
{
  "scope_id": "scope_abc123",
  "name": "My Project Stack",
  "status": "complete",
  "system_risk_summary": {
    "total_repos": 3,
    "total_unique_dependencies": 47,
    "dependencies_used_by_multiple_repos": 8,
    "high_risk_dependencies": 5,
    "vulnerable_dependencies": 3,
    "high_risk_repos": 1,
    "medium_risk_repos": 1,
    "low_risk_repos": 1,
    "aggregate_risk_score": 0.42,
    "aggregate_label": "MEDIUM",
    "per_repo_results": [
      {
        "repo": "numpy/numpy",
        "risk_score": 0.35,
        "risk_label": "LOW",
        "error": null
      }
    ]
  },
  "priority_risks": [
    {
      "name": "requests",
      "type": "dependency",
      "reason": "Used by 3 repos, has 2 known CVEs",
      "severity": "high"
    }
  ],
  "top_risky_dependencies": [
    {
      "package_name": "requests",
      "risk_score": 0.7,
      "risk_label": "HIGH",
      "used_by_repos": ["numpy/numpy", "psf/requests"],
      "cve_count": 2
    }
  ],
  "graph": {
    "nodes": [],
    "edges": []
  }
}
```
