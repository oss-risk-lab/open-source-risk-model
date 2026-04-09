# Tasks: UI Navigation Unification

## Task 1: Implement Navigation Helper Functions

- [x] 1.1 Create `ui/nav-helpers.js` with the pure helper functions (`getRepoFromUrl`, `parseRepoParam`, `buildPageUrl`, `getCurrentPageId`) that will be duplicated inline in each page. This file serves as the single source of truth for development and testing, though the functions are inlined in production.
  - **Note: `nav-helpers.js` exists for development/test synchronization only and is NOT referenced by the HTML pages at runtime. The HTML pages inline these functions directly.**
  - Implement `parseRepoParam(searchString)` as the core parsing logic: takes a query string (e.g. `"?repo=numpy%2Fnumpy"`), extracts and validates the `repo` param with strict owner/name validation (exactly one slash), returns the decoded repo string or `null`.
  - Implement `getRepoFromUrl()` as a thin wrapper that calls `parseRepoParam(window.location.search)`.
  - Implement `buildPageUrl(page, repo)` that appends `?repo=encodeURIComponent(repo)` when repo is non-null/non-empty, otherwise returns bare page string.
  - Implement `getCurrentPageId()` that checks pathname for "insights", "graph", "dependency-tree" substrings, falling back to "index" for paths ending in `/` or with no recognized filename.
  - Export all functions for use in tests (CommonJS `module.exports` or ES module).
- [x] 1.2 Create `ui/nav-render.js` with `renderNav(currentPageId, repo)` and `getCrossLinks(currentPageId, repo)` functions.
  - **Note: `nav-render.js` exists for development/test synchronization only and is NOT referenced by the HTML pages at runtime. The HTML pages inline these functions directly.**
  - `renderNav` must be idempotent: check for existing `nav.ds-nav` and remove it before inserting a new one.
  - `renderNav` creates a `<nav class="ds-nav" aria-label="Main navigation">` with brand span and 4 links (Home, Insights, Graph, Dependency Tree), applying `active` class and `aria-current="page"` to the link matching `currentPageId`.
  - All nav link hrefs use `buildPageUrl()` to include `?repo=` when repo is non-null.
  - `getCrossLinks(currentPageId, repo)` returns an array of `{label, href, targetPageId}` data objects for the three cross-page links, filtering out any link whose `targetPageId` matches `currentPageId`. The actual DOM rendering of cross-links happens in each page's inline script, not in this helper.
  - Export both functions for testing.

## Task 2: Add Navigation Bar to Each Page

- [x] 2.1 Add nav bar CSS (`.ds-nav`, `.ds-nav-brand`, `.ds-nav-links`, `.ds-nav-link`) to the `<style>` block of `ui/index.html`, using only existing CSS custom properties from the Deep Signal theme.
- [x] 2.2 Add nav bar CSS to the `<style>` block of `ui/graph.html`.
- [x] 2.3 Add nav bar CSS to the `<style>` block of `ui/insights.html`.
- [x] 2.4 Add nav bar CSS to the `<style>` block of `ui/dependency-tree.html`.
- [x] 2.5 Add inline helper functions (`getRepoFromUrl`, `parseRepoParam`, `buildPageUrl`, `getCurrentPageId`, `renderNav`) and initialization call to `ui/index.html` `<script>` block. Call `renderNav(getCurrentPageId(), getRepoFromUrl())` which inserts the nav as the first child of `.wrap`.
- [x] 2.6 Add inline helper functions and initialization call to `ui/graph.html` `<script>` block. Call `renderNav(getCurrentPageId(), getRepoFromUrl())` which inserts the nav as the first child of `.wrap`.
- [x] 2.7 Add inline helper functions and initialization call to `ui/insights.html` `<script>` block. Call `renderNav(getCurrentPageId(), getRepoFromUrl())` which inserts the nav as the first child of `.wrap`.
- [x] 2.8 Add inline helper functions and initialization call to `ui/dependency-tree.html` `<script>` block. Call `renderNav(getCurrentPageId(), getRepoFromUrl())` which inserts the nav as the first child of `.wrap`.

## Task 3: Implement Graph.html Auto-Load from URL

- [x] 3.1 Replace the existing prefill IIFE in `ui/graph.html` inline script with the new IIFE that reuses `getRepoFromUrl()` (instead of re-parsing URL params separately) to both prefill `repoInput` and call `loadGraph(false)` when a valid repo is present. The IIFE should be: `var repo = getRepoFromUrl(); if (repo) { document.getElementById("repoInput").value = repo; loadGraph(false); }`. This ensures the strict owner/name validation from `getRepoFromUrl` is reused consistently. The IIFE runs at the bottom of the inline script, after `graph-viz.js` is loaded, ensuring both `loadGraph` and `repoInput` are available.
- [x] 3.2 Verify that when `?repo=` is absent, no auto-load occurs and the page shows the empty input state.

## Task 4: Add Cross-Page Links to Each Page

- [x] 4.1 Add cross-page links to `ui/index.html`: render below the `.grid` div after `score()` completes. Show all three links ("Open in Insights", "Open in Graph", "Open in Dependency Tree") since index is the home page. Hide when no repo context. After `score()` completes, cross-links use the repo that was actually scored (from `repoInput.value`), even if the page loaded without `?repo=`. The repo source on index.html is: URL `?repo=` on initial load OR `repoInput.value` after scoring.
- [x] 4.2 Add cross-page links to `ui/graph.html`: render inside the existing `.panel` controls section, below the repo input controls. Show "Open in Insights" + "Open in Dependency Tree" (exclude "Open in Graph"). Show after `loadGraph()` completes, hide when no repo loaded.
- [x] 4.3 Add cross-page links to `ui/dependency-tree.html`: render inside the `#summarySection` panel, below the `#repoHeader` div. Show "Open in Insights" + "Open in Graph" (exclude "Open in Dependency Tree"). Show after `loadTree()` completes, hide when no repo loaded.
- [x] 4.4 Update `renderDetailView()` in `ui/insights.html` to add cross-page links inside the `.detail-links` div, alongside the existing "Back to list" and "Open in graph view" links. Show "Open in Graph" + "Open in Dependency Tree" (exclude "Open in Insights"). Replace the existing hardcoded "Open in graph view" link with the standardized "Open in Graph" label using `buildPageUrl`.

## Task 5: Write Property-Based Tests

- [x] 5.1 Set up test infrastructure: create `test/ui/test_nav_properties.js` using fast-check. Configure minimum 100 iterations per property test.
  - [x] 🧪 5.1.1 Property 1 — Nav bar link labels: *For any* `currentPageId` and repo value, `renderNav` produces exactly 4 links with labels "Home", "Insights", "Graph", "Dependency Tree" in order. Tag: `Feature: ui-navigation-unification, Property 1: Nav bar contains all four page links with correct labels`
  - [x] 🧪 5.1.2 Property 2 — Active page indicator: *For any* valid page ID and repo value, `renderNav` produces exactly one link with `active` class and `aria-current="page"`, matching the given page ID. Tag: `Feature: ui-navigation-unification, Property 2: Active page indicator and aria-current correctness`
  - [x] 🧪 5.1.3 Property 3 — buildPageUrl repo inclusion: *For any* page string and repo value, `buildPageUrl` includes `?repo=` iff repo is non-null/non-empty. Tag: `Feature: ui-navigation-unification, Property 3: buildPageUrl includes repo parameter if and only if repo is non-null`
  - [x] 🧪 5.1.4 Property 4 — Encoding round-trip: *For any* valid `owner/name` string (no extra slashes), encoding via `buildPageUrl` then extracting via `parseRepoParam` (with the constructed query string) returns the original string. **Note:** Since `getRepoFromUrl` reads from `window.location.search`, the property test must use the underlying `parseRepoParam(searchString)` function directly rather than relying on actual `window.location`. Tag: `Feature: ui-navigation-unification, Property 4: Repo context encoding round-trip`
  - [x] 🧪 5.1.5 Property 5 — Invalid repo yields null: *For any* string that is empty, whitespace-only, has no slash, has multiple slashes, or has empty parts around the slash, `getRepoFromUrl` returns null. Tag: `Feature: ui-navigation-unification, Property 5: Invalid repo values yield null`
  - [x] 🧪 5.1.6 Property 6 — Cross-page link labels: *For any* target page ID, the generated label matches the defined mapping ("Open in Insights", "Open in Graph", "Open in Dependency Tree"). Tag: `Feature: ui-navigation-unification, Property 6: Cross-page link labels match target page mapping`
  - [x] 🧪 5.1.7 Property 7 — Cross-links hidden without repo: *For any* page and null repo, rendered cross-page links with `?repo=` URLs are empty. Tag: `Feature: ui-navigation-unification, Property 7: Repo-specific cross-links hidden when no repo context`
  - [x] 🧪 5.1.8 Property 8 — Cross-links exclude current page: *For any* page ID in {"insights","graph","dependency-tree"} and non-null repo, no rendered cross-link targets the current page. On "index", all three links are rendered. Tag: `Feature: ui-navigation-unification, Property 8: Cross-links exclude current page`

## Task 6: Write Unit Tests

- [x] 6.1 Create `test/ui/test_nav_unit.js` with two test sections:
  - **Pure helper unit tests:**
    - `getRepoFromUrl` / `parseRepoParam` specific examples: `numpy/numpy` → valid, `pallets/flask` → valid, `a/b/c` → null (multiple slashes), empty → null, whitespace → null, `/` → null, `a/` → null, `/b` → null.
    - `buildPageUrl` examples: `("graph.html", "numpy/numpy")` → `"graph.html?repo=numpy%2Fnumpy"`, `("graph.html", null)` → `"graph.html"`.
    - `getCurrentPageId` examples: paths with "insights.html" → "insights", "graph.html" → "graph", "dependency-tree.html" → "dependency-tree", "/" → "index", "/ui/" → "index".
    - `getCrossLinks` exclusion: on graph page, no "Open in Graph" link; on dependency-tree page, no "Open in Dependency Tree" link; on insights page, no "Open in Insights" link; on index page, all three links present.
    - `renderNav` idempotency: calling twice produces exactly one `<nav>` element.
  - **DOM integration tests:**
    - Cross-link placement verification per page (index: after `.grid`, graph: inside `.panel`, dependency-tree: inside `#summarySection`, insights: inside `.detail-links`).
    - Nav insertion as first child of `.wrap` on each page.

## Task 7: Integration Verification

- [x] 7.1 Manually verify all four pages load without JavaScript errors, nav bar appears at top, active page is highlighted, and existing functionality is preserved.
- [x] 7.2 Verify cross-page navigation preserves repo context: navigate from insights detail → graph → dependency-tree and confirm `?repo=` param carries through with encoded values.
- [x] 7.3 Verify graceful degradation: load each page without `?repo=` param and confirm default state, no cross-page links shown, nav links have no `?repo=` param.
