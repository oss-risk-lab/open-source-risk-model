# Implementation Plan: Insight UI Integration

## Overview

Build two frontend components: a new `ui/insights.html` dashboard page (list + detail modes) and an insight summary panel on the existing `ui/graph.html`. Both consume existing API endpoints using vanilla HTML/CSS/JS with inline scripts. Pure helper functions are duplicated in test files for property-based and unit testing with fast-check (test-only dependency, not in runtime bundle).

## Tasks

### Phase A: insights.html

- [x] 1. Create insights.html skeleton with HTML structure, CSS, and pure helper functions
  - [x] 1.1 Create `ui/insights.html` with HTML skeleton and full CSS
    - Create the file with `<!doctype html>`, `<head>` (title, meta, CSS variables matching index.html), and `<body>` structure
    - Include all CSS: `:root` variables, `.wrap`, `.panel`, `.btn`, `.err`, `.pill`, label-indicator, signal-badge, summary-strip, table, pagination, detail-view, loading/empty states, responsive `overflow-x: auto` on table container
    - HTML body: `.wrap` > topbar with heading, filter/sort controls panel, summary strip container, table container (with `<table>`, `<thead>`, `<tbody>`), pagination controls, detail view container (hidden by default), loading indicator, error container, empty state
    - All interactive controls must have `aria-label` attributes; table headers use `<th scope="col">`; pagination range has `aria-live="polite"`
    - Use a `setViewState(state)` helper to manage mutually exclusive visibility of: loading, error, empty, list, detail containers
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 3.1, 3.2, 3.3, 4.1, 4.2, 5.2, 5.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.7, 10.1, 10.2, 10.4, 10.5, 10.6_

  - [x] 1.2 Add inline `<script>` with pure helper functions and `appState`
    - Define `API_BASE`, `LABEL_COLORS`, `SEVERITY_COLORS` constants
    - Define `appState` object per design (mode, repo, filters, sort, pagination, items, detail, loading, error)
    - Implement pure functions: `buildApiUrl(state)`, `signalBadgeText(signals)`, `labelColorClass(label)`, `paginationRangeText(offset, limit, total)`, `paginationButtonState(offset, limit, total)`, `nextOffset(offset, limit, total)`, `prevOffset(offset, limit)`, `encodeRepoParam(repoFullName)`, `decodeRepoParam(encoded)`, `graphViewUrl(repoFullName)`, `insightPanelAriaLabel(repoFullName)`, `summaryCounts(items)`, `formatErrorMessage(status, detail)`
    - `buildApiUrl` must omit null and empty-string filter params; never send `false` for boolean filters
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 3.4, 3.5, 5.2, 5.4, 5.5, 5.6, 5.7, 6.2, 6.7, 8.2, 9.6, 11.1_

- [x] 2. Implement insights.html list mode rendering and API integration
  - [x] 2.1 Implement `fetchInsightsList`, `renderTable`, `renderSummaryStrip`, `renderPagination`, `renderLoading`, `renderError`, `renderEmpty`
    - `fetchInsightsList` calls `GET {API_BASE}/api/insights` with params from `buildApiUrl`
    - `renderTable` builds `<tbody>` rows: repo link (clickable, navigates to detail via event delegation on `<tbody>`), score (mono, 3 decimals), label indicator, reasons list, signal badges
    - `renderSummaryStrip` shows page-scoped counts: "Showing {returned} of {total}", "On this page:" HIGH/MEDIUM/LOW counts from current page items only
    - `renderPagination` updates range text and Previous/Next button disabled states
    - `renderLoading` shows "Loading insights…" in table area; `renderError` shows error in `.err` container with status + detail; `renderEmpty` shows "No repositories match the current filters." (only after successful 200 with zero items, never during loading or after error)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 5.2, 5.3, 5.4, 5.5, 8.1, 8.2, 8.4, 11.1, 11.2, 11.3_

  - [x] 2.2 Implement `onFilterChange`, `onSortChange`, `onPageChange`, and `fetchAndRender` orchestrator
    - `onFilterChange` reads filter controls, resets offset to 0, calls `fetchAndRender`
    - `onSortChange` reads sort controls, resets offset to 0, calls `fetchAndRender`
    - `onPageChange(direction)` adjusts offset by ±limit (clamped), calls `fetchAndRender`
    - `fetchAndRender` clears errors, shows loading via `setViewState("loading")`, calls `fetchInsightsList`, updates `appState.items`/`total`, renders table + summary + pagination, handles errors
    - Wire event listeners to filter dropdowns, checkboxes, sort controls, pagination buttons
    - _Requirements: 3.4, 4.3, 5.6, 5.7, 5.8, 8.4_

- [x] 3. Implement insights.html detail mode and URL routing
  - [x] 3.1 Implement `fetchRepoInsight`, `renderDetailView`, `navigateToDetail`, `navigateToList`
    - `fetchRepoInsight(owner, repo)` calls `GET {API_BASE}/api/insights/{owner}/{repo}`
    - `renderDetailView` shows: repo name, score (3 decimals), label indicator, base maintenance risk, all reasons, direct signals table (signal_name, severity, score_contribution, reason)
    - Include "Back to list" link (calls `navigateToList`) and "Open in graph view" link (`graph.html?repo=owner%2Frepo`)
    - The "Back to list" link is always rendered, even on fetch failure (404 or 5xx)
    - Handle 404 → "Repository not found" with back link; other errors → error with status + detail and back link
    - _Requirements: 6.3, 6.4, 6.5, 6.7_

  - [x] 3.2 Implement URL routing with `history.pushState` and `popstate`
    - On page load: check for `?repo=` param → detail mode; otherwise → list mode
    - `navigateToDetail` pushes `?repo=owner%2Frepo` to history, fetches and renders detail
    - `navigateToList` pushes URL without `repo` param, fetches and renders list
    - On `popstate`: rehydrate mode and relevant state from the current URL query parameters before fetching and rendering
    - Repo link clicks call `navigateToDetail` with `encodeRepoParam`
    - _Requirements: 6.1, 6.2, 6.6_

- [x] 4. Checkpoint — Verify insights.html end-to-end
  - Verify list mode loads and displays data from `GET /api/insights` with default params
  - Verify filter controls (label dropdown, checkboxes, min_score) trigger re-fetch and update table
  - Verify sort controls change ordering
  - Verify pagination Previous/Next buttons work and disable correctly at boundaries
  - Verify clicking a repo name switches to detail mode with correct URL
  - Verify detail mode fetches from `GET /api/insights/{owner}/{repo}` and shows full signals
  - Verify "Back to list" and "Open in graph view" links work
  - Verify browser back/forward navigates between list and detail modes
  - Verify error and empty states display correctly

### Phase B: graph.html insight panel

- [x] 5. Add insight summary panel to graph.html
  - [x] 5.1 Add insight panel HTML and CSS to `ui/graph.html`
    - Add `<div id="insightPanel" class="panel" style="display:none;" aria-label="Insight summary">` between the explanation panel and `.main-container`
    - Add label-indicator and signal-badge CSS classes to graph.html's `<style>` block
    - Panel contains `<div id="insightContent">Loading insight…</div>`
    - _Requirements: 7.2, 7.3, 7.6, 9.6, 10.3_

  - [x] 5.2 Add inline JS function `fetchAndRenderInsight(owner, repo)` to `ui/graph.html`
    - Fetches `GET {API_BASE}/api/insights/{owner}/{repo}` after graph loads
    - On success: populate `#insightContent` with score (3 decimals), label indicator, reasons, signal badges; show panel; set `aria-label` dynamically to `"Insight summary for {repo_full_name}"`
    - On 404: show "No insight data available for this repository."
    - On other error: show "Could not load insight data"
    - Never throws — all errors caught and displayed in panel
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.7_

  - [x] 5.3 Wire insight panel fetch into existing graph load flow in `ui/graph.html`
    - After graph renders successfully, call `fetchAndRenderInsight(owner, repo)` — fire-and-forget, does not block graph rendering
    - If graph load fails, insight panel fetch is never initiated; panel remains hidden
    - Read `?repo=` query parameter on page load to pre-fill the repo input (decode with `decodeURIComponent`); pre-filling only sets the input value, does not auto-trigger graph load (matches existing graph.html behavior where user clicks "Load Graph")
    - _Requirements: 7.1, 7.7_

- [x] 6. Checkpoint — Verify graph.html insight panel
  - Verify insight panel appears after loading a graph for a repo in the database
  - Verify panel shows correct score, label, reasons, and signal badges
  - Verify panel shows "No insight data available" for a repo not in the insights DB
  - Verify graph visualization renders independently — insight fetch failure does not break graph
  - Verify `?repo=` query param pre-fills the repo input field

### Phase C: Tests

- [x] 7. Create test files for pure helper functions
  - [x] 7.1 Create `test/ui/test_insights_logic.js` with tests for pure helper functions
    - Duplicate the pure helper functions from insights.html into the test file (Option A: copy, since UI scripts are inline and cannot be imported)
    - Write unit tests for edge cases: empty items list, zero total, offset at boundary, repo names with special characters, empty-string filter values
    - [x] 7.1.1 Property 1: Label-to-color mapping is total and correct
      - **Property 1: Label-to-color mapping is total and correct**
      - **Validates: Requirements 2.3, 2.4, 2.5**
    - [x] 7.1.2 Property 2: Signal badges appear only for non-info signals with correct text
      - **Property 2: Signal badges appear only for non-info signals with correct text**
      - **Validates: Requirements 2.6**
    - [x] 7.1.3 Property 3: App state maps to correct API query parameters
      - **Property 3: App state maps to correct API query parameters**
      - **Validates: Requirements 3.4, 3.5, 4.3**
    - [x] 7.1.4 Property 4: Pagination range text is correct
      - **Property 4: Pagination range text is correct**
      - **Validates: Requirements 5.2**
    - [x] 7.1.5 Property 5: Pagination button enabled/disabled state
      - **Property 5: Pagination button enabled/disabled state**
      - **Validates: Requirements 5.4, 5.5**
    - [x] 7.1.6 Property 6: Pagination offset arithmetic is bounded
      - **Property 6: Pagination offset arithmetic is bounded**
      - **Validates: Requirements 5.6, 5.7**
    - [x] 7.1.7 Property 7: Filter/sort change resets offset to zero
      - **Property 7: Filter/sort change resets offset to zero**
      - **Validates: Requirements 5.8**
    - [x] 7.1.8 Property 8: Repo name URL encoding round trip
      - **Property 8: Repo name URL encoding round trip**
      - **Validates: Requirements 6.2, 6.3**
    - [x] 7.1.9 Property 9: Detail view graph link points to correct URL
      - **Property 9: Detail view graph link points to correct URL**
      - **Validates: Requirements 6.7**
    - [x] 7.1.10 Unit test: Render output contains all required fields (insight summary)
      - Test as unit test (not property-based) to avoid brittle HTML string matching
      - **Validates: Requirements 2.2, 7.3**
    - [x] 7.1.11 Property 11: Summary strip counts match current page item labels
      - **Property 11: Summary strip counts match current page item labels**
      - **Validates: Requirements 11.1**
    - [x] 7.1.12 Property 12: Error display includes status code and detail
      - **Property 12: Error display includes status code and detail**
      - **Validates: Requirements 8.2**
    - [x] 7.1.13 Property 13: Insight panel aria-label contains repo name
      - **Property 13: Insight panel aria-label contains repo name**
      - **Validates: Requirements 9.6**

  - [x] 7.2 Create `test/ui/test_graph_insight_panel.js` with unit tests
    - Test insight panel render output for success, 404, and error cases
    - Test aria-label dynamic update on success
    - Test that panel remains hidden when graph load fails
    - Test edge cases: empty reasons array, all signals at "info" severity
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7, 9.6_

- [x] 8. Final checkpoint
  - Verify all required tasks (non-`*`) are complete and working
  - If optional property tests were implemented, verify they pass
  - Manual smoke test: load insights dashboard, filter by HIGH, click a repo, verify detail, click "Open in graph view", verify graph page shows insight panel

## Notes

- Tasks marked with `*` are optional property/unit tests that can be deferred for faster MVP delivery. Required tasks (1–6, 8) constitute the complete working feature.
- Pure helper functions are duplicated in test files (Option A from design) since UI scripts are inline and cannot be imported. Keep the canonical copy in `insights.html`; test copies are mirrors.
- fast-check is a test-only dependency, not included in the runtime UI files
- `ui/graph-viz.js` is not modified — the insight panel wiring goes in graph.html's inline script
- The `setViewState()` helper prevents overlapping UI states (loading/error/empty/list/detail)
- Graph page `?repo=` pre-fill only sets the input value; it does not auto-trigger graph load
