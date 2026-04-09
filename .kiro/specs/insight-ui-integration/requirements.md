# Requirements Document

## Introduction

This feature adds two UI components to the Deep Signal risk model system: (1) a new Insights Dashboard page (`ui/insights.html`) that provides a filterable, sortable cross-repo view of computed risk insights, and (2) an Insight Summary panel embedded in the existing Supply Chain Graph page (`ui/graph.html`) that shows per-repo insight data alongside the graph visualization. Both components consume the existing `/api/insights` and `/api/insights/{owner}/{repo}` endpoints, use the established dark theme CSS variables, and require no build tools or external frameworks.

## Glossary

- **Dashboard**: The new `ui/insights.html` page that lists all repositories with their computed insight scores, labels, reasons, and signal badges in a filterable, sortable, paginated table.
- **Insight_Summary_Panel**: A compact UI section added to `ui/graph.html` that displays the graph signal score, label, reasons, and signal badges for the currently loaded repository.
- **Signal_Badge**: A small visual indicator (pill-shaped element) representing the presence and severity of a specific risk signal (CVE risk, maintainer concentration, or release staleness).
- **Label_Indicator**: A color-coded pill element displaying the graph signal label (HIGH, MEDIUM, LOW) with distinct colors per level.
- **API_Base**: The base URL for all API calls: `http://127.0.0.1:8000`.
- **Insight_Item**: A single repository entry returned by the `GET /api/insights` endpoint, containing `repo_full_name`, `graph_signal_score`, `graph_signal_label`, `base_maintenance_risk`, `reasons`, and `signals` summary.
- **Dark_Theme**: The existing CSS variable-based theme used across all Deep Signal UI pages, defined with `--bg`, `--panel`, `--card`, `--border`, `--text`, `--muted`, `--radius`, `--shadow`, and related variables.
- **Filter_Controls**: UI elements (dropdowns, checkboxes, number inputs) that map to the `GET /api/insights` query parameters for filtering the repo list.
- **Sort_Controls**: UI elements that set the `sort_by` and `order` query parameters sent to the `GET /api/insights` endpoint.
- **Pagination_Controls**: UI elements (previous/next buttons, page indicator) that manage `limit` and `offset` parameters for paginated API requests.

## Requirements

### Requirement 1: Insights Dashboard Page Structure

**User Story:** As a risk analyst, I want a dedicated Insights Dashboard page at `ui/insights.html`, so that I can view all repositories and their computed risk insights in one place.

#### Acceptance Criteria

1. THE Dashboard SHALL be a single static HTML file located at `ui/insights.html` that loads without build tools or external frameworks.
2. THE Dashboard SHALL use the same CSS variables as `ui/index.html` for `--bg`, `--panel`, `--card`, `--border`, `--text`, `--muted`, `--muted2`, `--shadow`, `--radius`, `--mono`, and `--sans`.
3. THE Dashboard SHALL include a page title "Deep Signal — Insights Dashboard" in the HTML `<title>` element and a visible heading.
4. THE Dashboard SHALL render the same background gradient and body styling as the existing Deep Signal pages.

### Requirement 2: Cross-Repo Insight Table

**User Story:** As a risk analyst, I want to see a table of all repositories with their insight scores, labels, reasons, and signal indicators, so that I can quickly assess risk across the portfolio.

#### Acceptance Criteria

1. WHEN the Dashboard loads, THE Dashboard SHALL fetch data from `GET {API_Base}/api/insights` with default parameters and display the results in a table layout.
2. THE Dashboard SHALL display each Insight_Item as a row containing: `repo_full_name`, `graph_signal_score` (rounded to 3 decimal places), `graph_signal_label` as a Label_Indicator, a list of `reasons`, and Signal_Badges for CVE risk, maintainer concentration, and release staleness.
3. WHEN `graph_signal_label` is "HIGH", THE Label_Indicator SHALL use a red color scheme (background `rgba(239,68,68,.15)`, text `#ef4444`).
4. WHEN `graph_signal_label` is "MEDIUM", THE Label_Indicator SHALL use a yellow color scheme (background `rgba(234,179,8,.15)`, text `#eab308`).
5. WHEN `graph_signal_label` is "LOW", THE Label_Indicator SHALL use a green color scheme (background `rgba(34,197,94,.15)`, text `#22c55e`).
6. THE Dashboard SHALL display a Signal_Badge for each signal type only when the signal severity is not "info". Badge text SHALL be: "CVE" (or "{count} CVEs" if count > 1) for CVE risk, "Maintainer" for maintainer concentration, and "Stale release" for release staleness. Badge background color SHALL be red (`#ef4444` background at 15% opacity) for "high" severity, yellow (`#eab308` background at 15% opacity) for "medium" severity, and muted orange (`#ea580c` background at 15% opacity) for "mild" severity.
7. WHEN the API returns zero items after a successful response, THE Dashboard SHALL display a message "No repositories match the current filters." THE empty-state message SHALL NOT appear during loading or after a failed request.

### Requirement 3: Filter Controls

**User Story:** As a risk analyst, I want to filter the repository list by label, signal presence, and minimum score, so that I can focus on the repositories that matter most.

#### Acceptance Criteria

1. THE Filter_Controls SHALL include a dropdown for `label` with options: "All", "HIGH", "MEDIUM", "LOW".
2. THE Filter_Controls SHALL include checkboxes for `has_cves`, `has_maintainer_risk`, and `has_stale_release`, each defaulting to unchecked (no filter applied).
3. THE Filter_Controls SHALL include a numeric input for `min_score` accepting values from 0.0 to 1.0 with step 0.05, defaulting to empty (no filter applied).
4. WHEN the user changes any filter value, THE Dashboard SHALL send a new request to `GET {API_Base}/api/insights` with the updated query parameters and re-render the table.
5. WHEN a checkbox filter is unchecked, THE Dashboard SHALL omit that parameter from the API request entirely (not send `false`).

### Requirement 4: Sort Controls

**User Story:** As a risk analyst, I want to sort the repository list by different risk dimensions, so that I can identify the highest-risk repositories by specific criteria.

#### Acceptance Criteria

1. THE Sort_Controls SHALL include a dropdown for `sort_by` with options: "Score" (`score`), "Base Risk" (`base_risk`), "CVE Count" (`cve_count`), "Maintainer Fraction" (`maintainer_fraction`), "Release Staleness" (`release_staleness`).
2. THE Sort_Controls SHALL include a toggle or dropdown for `order` with options: "Descending" (`desc`), "Ascending" (`asc`), defaulting to "Descending".
3. WHEN the user changes the sort field or order, THE Dashboard SHALL send a new request to `GET {API_Base}/api/insights` with the updated `sort_by` and `order` parameters and re-render the table.

### Requirement 5: Pagination

**User Story:** As a risk analyst, I want to page through the repository list, so that I can browse all 145+ repositories without loading them all at once.

#### Acceptance Criteria

1. THE Dashboard SHALL use a default page size of 25 items per page.
2. THE Pagination_Controls SHALL display the current page range (e.g., "1–25 of 145") and total count from the API `total` field.
3. THE Pagination_Controls SHALL include "Previous" and "Next" buttons.
4. WHEN the user is on the first page, THE "Previous" button SHALL be disabled.
5. WHEN `offset + limit >= total`, THE "Next" button SHALL be disabled.
6. WHEN the user clicks "Next", THE Dashboard SHALL increment `offset` by `limit` and re-fetch data from the API.
7. WHEN the user clicks "Previous", THE Dashboard SHALL decrement `offset` by `limit` (minimum 0) and re-fetch data from the API.
8. WHEN any filter or sort parameter changes, THE Dashboard SHALL reset `offset` to 0 before fetching.

### Requirement 6: Repo Navigation from Dashboard

**User Story:** As a risk analyst, I want to click a repository name in the dashboard to see its detailed insight view, so that I can drill down into specific risk signals.

#### Acceptance Criteria

1. THE Dashboard SHALL render each `repo_full_name` as a clickable link.
2. WHEN the user clicks a repo name, THE Dashboard SHALL navigate to `insights.html?repo=owner%2Frepo` where `repo_full_name` is URL-encoded (the slash in `owner/repo` SHALL be encoded as `%2F`). WHEN reading the `repo` query parameter, THE Dashboard SHALL URL-decode it.
3. WHEN the Dashboard loads with a `repo` query parameter, THE Dashboard SHALL fetch `GET {API_Base}/api/insights/{owner}/{repo}` and display a detail view showing: `repo_full_name`, `graph_signal_score`, `graph_signal_label` as a Label_Indicator, `base_maintenance_risk`, all `reasons`, and each `direct_signal` with `signal_name`, `severity`, `score_contribution`, and `reason`.
4. THE detail view SHALL include a "Back to list" link that returns to the table view (removes the `repo` query parameter).
5. THE detail view SHALL use `GET {API_Base}/api/insights/{owner}/{repo}` which returns full `direct_signals` with `signal_name`, `severity`, `score_contribution`, and `reason`. THE list view SHALL use `GET {API_Base}/api/insights` which returns compact `signals` summary.
6. THE Dashboard SHALL operate in two modes: (a) list mode (default, no `repo` query parameter) showing the filterable table, and (b) detail mode (when `repo` query parameter is present) showing the single-repo detail view. Switching between modes SHALL update the URL without a full page reload where possible.
7. THE detail view SHALL include an "Open in graph view" link that navigates to `graph.html?repo={owner}/{repo}` for the current repository.

### Requirement 7: Insight Summary Panel on Graph Page

**User Story:** As a risk analyst, I want to see a compact insight summary when viewing a repository's supply chain graph, so that I can correlate graph structure with computed risk signals.

#### Acceptance Criteria

1. WHEN a graph is successfully loaded for a repository in `graph.html`, THE Insight_Summary_Panel SHALL fetch `GET {API_Base}/api/insights/{owner}/{repo}` for the same repository.
2. THE Insight_Summary_Panel SHALL be positioned above the main graph container, inside a `.panel` element matching the existing page styling.
3. THE Insight_Summary_Panel SHALL display: `graph_signal_score` (rounded to 3 decimal places), `graph_signal_label` as a Label_Indicator, a list of `reasons`, and Signal_Badges for each active signal.
4. WHEN the insight API returns a 404 (repo not found in insights), THE Insight_Summary_Panel SHALL display "No insight data available for this repository."
5. IF the insight API request fails with a non-404 error, THEN THE Insight_Summary_Panel SHALL display "Could not load insight data" and not disrupt the graph visualization.
6. THE Insight_Summary_Panel SHALL be hidden by default and only appear after a graph is loaded.
7. THE graph visualization SHALL render independently of the insight fetch. THE Insight_Summary_Panel fetch SHALL be initiated after the graph API call succeeds but SHALL NOT block graph rendering. IF the insight fetch fails, THEN the graph SHALL remain fully functional.

### Requirement 8: Loading and Error States

**User Story:** As a risk analyst, I want clear feedback when data is loading or when errors occur, so that I understand the current state of the interface.

#### Acceptance Criteria

1. WHILE the Dashboard is fetching data from the API, THE Dashboard SHALL display a loading indicator (text "Loading insights…" or a spinner) in the table area.
2. IF the Dashboard API request fails, THEN THE Dashboard SHALL display an error message with the HTTP status code and error detail in a styled error container matching the existing `.err` class pattern.
3. WHILE the Insight_Summary_Panel is fetching data, THE Insight_Summary_Panel SHALL display "Loading insight…" text.
4. WHEN a new fetch begins (due to filter, sort, or page change), THE Dashboard SHALL clear any previous error message.

### Requirement 9: Accessibility

**User Story:** As a user relying on assistive technology, I want the insight UI components to be accessible, so that I can navigate and understand the risk data.

#### Acceptance Criteria

1. THE Dashboard SHALL use semantic HTML elements: `<table>`, `<thead>`, `<tbody>`, `<th>`, `<td>` for the repo list, or equivalent ARIA `role` attributes if using `<div>`-based layout.
2. THE Dashboard SHALL include `aria-label` attributes on all interactive controls (filter dropdowns, sort controls, pagination buttons).
3. THE Dashboard SHALL ensure all Label_Indicators and Signal_Badges have sufficient color contrast (minimum 4.5:1 ratio against their background) or include text labels alongside color coding.
4. THE Pagination_Controls SHALL include `aria-live="polite"` on the page range indicator so screen readers announce page changes.
5. THE Dashboard SHALL support keyboard navigation: Tab to move between controls, Enter/Space to activate buttons and links.
6. THE Insight_Summary_Panel SHALL include an `aria-label="Insight summary for {repo_full_name}"` attribute on its container.
7. IF the Dashboard uses `<table>` elements, THEN all column headers SHALL use `<th scope="col">`.

### Requirement 10: Theme and Layout Consistency

**User Story:** As a user of Deep Signal, I want the new insight UI to look and feel like the existing pages, so that the experience is cohesive.

#### Acceptance Criteria

1. THE Dashboard SHALL use the `.wrap`, `.panel`, `.btn`, `.err`, and `.pill` CSS class patterns from `ui/index.html`.
2. THE Dashboard SHALL use the same `max-width: 1100px` centered layout as `ui/index.html`.
3. THE Insight_Summary_Panel SHALL use the `.panel` class styling from `ui/graph.html`.
4. THE Dashboard and Insight_Summary_Panel SHALL use `font-family: var(--sans)` for body text and `font-family: var(--mono)` for numeric values.
5. THE Dashboard SHALL include no external CSS or JavaScript dependencies beyond what is already used in the project.
6. ON viewports narrower than the table's natural width, THE Dashboard table container SHALL allow horizontal scrolling (`overflow-x: auto`) rather than breaking the layout.


### Requirement 11: Summary Statistics Strip

**User Story:** As a risk analyst, I want a summary strip at the top of the dashboard showing aggregate counts, so that I get an at-a-glance overview of the dataset.

#### Acceptance Criteria

1. THE Dashboard SHALL display a summary strip above the table showing: total repos in current filter, count of HIGH repos, count of MEDIUM repos, count of LOW repos.
2. THE summary strip SHALL update whenever filters change and new data is fetched.
3. THE HIGH/MEDIUM/LOW counts SHALL use the same color scheme as the Label_Indicators.
