# Requirements Document

## Introduction

Deep Signal has four working HTML pages (index.html, graph.html, dependency-tree.html, insights.html) that each function independently but lack a shared navigation structure and consistent cross-page linking. This feature adds a unified top navigation bar, preserves repository context across page transitions via query parameters, and adds contextual cross-page links so the pages feel like a single cohesive product. The implementation stays minimal: inline HTML/CSS/JS, no frameworks, no build tools, reusing existing CSS variables and dark theme.

## Glossary

- **Navigation_Bar**: A shared horizontal header element rendered at the top of every Deep Signal page, containing links to all four pages and highlighting the active page.
- **Page**: One of the four Deep Signal HTML files: index.html (Home), insights.html (Insights Dashboard), graph.html (Supply Chain Graph), dependency-tree.html (Dependency Tree).
- **Repo_Context**: The currently selected repository, represented as an owner/name string (e.g. "pallets/flask") and propagated between pages via the `?repo=` URL query parameter.
- **Active_Page_Indicator**: A visual style applied to the Navigation_Bar link that corresponds to the currently loaded Page.
- **Cross_Page_Link**: A hyperlink or button on one Page that navigates to another Page, preserving Repo_Context when available.
- **URL_Encoding**: The use of encodeURIComponent and decodeURIComponent to safely encode and decode the Repo_Context value in URL query parameters.
- **Deep_Signal_Theme**: The existing dark theme defined by CSS custom properties (--bg, --panel, --card, --border, --text, --muted, --muted2, --shadow, --radius, --mono, --sans) shared across all Pages.

## Requirements

### Requirement 1: Shared Navigation Bar Rendering

**User Story:** As a user, I want a consistent navigation header on every page, so that I can always see where I am and navigate to any other page.

#### Acceptance Criteria

1. THE Navigation_Bar SHALL appear at the top of every Page (index.html, insights.html, graph.html, dependency-tree.html).
2. THE Navigation_Bar SHALL contain links to all four Pages labeled: Home, Insights, Graph, Dependency Tree.
3. THE Navigation_Bar SHALL use only CSS custom properties from the Deep_Signal_Theme for all styling.
4. THE Navigation_Bar SHALL be implemented as inline HTML and CSS within each Page, with no external CSS files or framework dependencies.
5. WHEN a Page is loaded, THE Navigation_Bar SHALL apply the Active_Page_Indicator to the link corresponding to the current Page.
6. THE Navigation_Bar SHALL render consistently across all four Pages with identical markup structure and styling.
7. WHEN insights.html is loaded in list mode (no `?repo=` parameter), THE Navigation_Bar SHALL apply the Active_Page_Indicator to the Insights link.
8. WHEN insights.html is loaded in detail mode (with `?repo=` parameter), THE Navigation_Bar SHALL apply the Active_Page_Indicator to the Insights link.
9. WHEN graph.html is loaded with or without a `?repo=` parameter, THE Navigation_Bar SHALL apply the Active_Page_Indicator to the Graph link.
10. WHEN dependency-tree.html is loaded with or without a `?repo=` parameter, THE Navigation_Bar SHALL apply the Active_Page_Indicator to the Dependency Tree link.

### Requirement 2: Repo Context Preservation in Navigation

**User Story:** As a user, I want the navigation links to carry my current repo selection to the next page, so that I do not lose context when switching views.

#### Acceptance Criteria

1. WHEN Repo_Context is known on the current Page, THE Navigation_Bar links SHALL include the `?repo=` query parameter with the URL-encoded Repo_Context value.
2. WHEN Repo_Context is not known on the current Page, THE Navigation_Bar links SHALL omit the `?repo=` query parameter.
3. THE Navigation_Bar SHALL use encodeURIComponent to encode the Repo_Context value in all generated URLs.
4. WHEN a Page receives a `?repo=` query parameter, THE Page SHALL use decodeURIComponent to decode the Repo_Context value.
5. WHEN insights.html is in detail mode with a `?repo=` parameter, THE Navigation_Bar links to graph.html and dependency-tree.html SHALL include the same `?repo=` parameter value to preserve Repo_Context.

### Requirement 3: Graph Page Repo Auto-Load

**User Story:** As a user, I want graph.html to automatically load the repo from the URL so that I can arrive from another page and see results immediately.

#### Acceptance Criteria

1. WHEN graph.html loads with a `?repo=` query parameter, THE graph.html Page SHALL prefill the repository input field with the decoded Repo_Context value.
2. WHEN graph.html loads with a `?repo=` query parameter, THE graph.html Page SHALL automatically trigger the graph load for that repository exactly once on initial page load.
3. WHEN graph.html loads with a `?repo=` query parameter, THE graph.html Page SHALL ensure no duplicate graph loads are triggered by other event handlers.
4. WHEN graph.html loads without a `?repo=` query parameter, THE graph.html Page SHALL display the empty input state without triggering any automatic load.

### Requirement 4: Dependency Tree Page Repo Auto-Load

**User Story:** As a user, I want dependency-tree.html to automatically load the repo from the URL so that I can arrive from another page and see results immediately.

#### Acceptance Criteria

1. WHEN dependency-tree.html loads with a `?repo=` query parameter, THE dependency-tree.html Page SHALL prefill the repository input field with the decoded Repo_Context value.
2. WHEN dependency-tree.html loads with a `?repo=` query parameter, THE dependency-tree.html Page SHALL automatically trigger the tree load for that repository exactly once on initial page load.
3. WHEN dependency-tree.html loads with a `?repo=` query parameter, THE dependency-tree.html Page SHALL ensure no duplicate tree loads are triggered by other event handlers.
4. WHEN dependency-tree.html loads without a `?repo=` query parameter, THE dependency-tree.html Page SHALL display the empty input state without triggering any automatic load.

### Requirement 5: Insights Page Repo Context Compatibility

**User Story:** As a user, I want the insights page to continue working with its existing `?repo=` parameter for detail mode, so that navigation from other pages lands correctly.

#### Acceptance Criteria

1. WHEN insights.html loads with a `?repo=` query parameter, THE insights.html Page SHALL enter detail mode for the specified repository (existing behavior preserved).
2. WHEN insights.html loads without a `?repo=` query parameter, THE insights.html Page SHALL display the dashboard list view (existing behavior preserved).
3. WHEN the user navigates from detail mode back to list mode, THE insights.html Page SHALL remove the `?repo=` parameter from the URL.

### Requirement 6: Cross-Page Contextual Links from Insights Detail

**User Story:** As a user viewing a repo's insights, I want quick links to the graph and dependency tree for that same repo, so that I can explore different views without re-entering the repo name.

#### Acceptance Criteria

1. WHILE insights.html is in detail mode for a repository, THE insights.html Page SHALL display Cross_Page_Links to graph.html and dependency-tree.html for that repository.
2. THE Cross_Page_Links on insights.html SHALL include the `?repo=` query parameter with the URL-encoded Repo_Context value.

### Requirement 7: Cross-Page Contextual Links from Graph

**User Story:** As a user viewing a repo's supply chain graph, I want quick links to the insights detail and dependency tree for that same repo.

#### Acceptance Criteria

1. WHILE graph.html has a loaded repository, THE graph.html Page SHALL display Cross_Page_Links to insights.html and dependency-tree.html for that repository.
2. THE Cross_Page_Links on graph.html SHALL include the `?repo=` query parameter with the URL-encoded Repo_Context value.

### Requirement 8: Cross-Page Contextual Links from Dependency Tree

**User Story:** As a user viewing a repo's dependency tree, I want quick links to the insights detail and graph for that same repo.

#### Acceptance Criteria

1. WHILE dependency-tree.html has a loaded repository, THE dependency-tree.html Page SHALL display Cross_Page_Links to insights.html and graph.html for that repository.
2. THE Cross_Page_Links on dependency-tree.html SHALL include the `?repo=` query parameter with the URL-encoded Repo_Context value.

### Requirement 9: Home Page Entry Points

**User Story:** As a user on the home page, I want clear entry points to the Insights Dashboard and repo-based exploration pages, so that I can start my workflow from a central location.

#### Acceptance Criteria

1. THE index.html Page SHALL display a visible entry point link to insights.html (Insights Dashboard).
2. WHEN Repo_Context is known on index.html (after scoring a repo), THE index.html Page SHALL display Cross_Page_Links to graph.html, dependency-tree.html, and insights.html detail for that repository.
3. THE Cross_Page_Links on index.html SHALL include the `?repo=` query parameter with the URL-encoded Repo_Context value when Repo_Context is known.

### Requirement 10: Graceful Degradation Without Repo Context

**User Story:** As a user, I want all pages to work normally even when no repo query parameter is present, so that direct navigation and bookmarks still function.

#### Acceptance Criteria

1. WHEN any Page loads without a `?repo=` query parameter, THE Page SHALL render fully and remain functional.
2. WHEN Repo_Context is not known, THE Cross_Page_Links that do not imply a specific repository in their label SHALL link to the target Page without a `?repo=` parameter.
3. WHEN Repo_Context is not known, THE Cross_Page_Links whose label implies a specific repository (e.g. "Open numpy/numpy in Graph") SHALL be hidden.
4. IF a `?repo=` query parameter contains an invalid or empty value, THEN THE Page SHALL treat Repo_Context as unknown and display the default state.

### Requirement 11: No External Dependencies

**User Story:** As a developer, I want the navigation implementation to use only vanilla HTML, CSS, and JS, so that no new build tools or frameworks are introduced.

#### Acceptance Criteria

1. THE Navigation_Bar implementation SHALL use only inline HTML, CSS, and JavaScript within each Page file.
2. THE Navigation_Bar implementation SHALL introduce zero external JavaScript libraries, CSS frameworks, or build tool dependencies.
3. THE Navigation_Bar implementation SHALL reuse existing CSS custom properties from the Deep_Signal_Theme.

### Requirement 12: Existing Functionality Preservation

**User Story:** As a user, I want all existing page functionality to continue working after the navigation is added, so that nothing breaks.

#### Acceptance Criteria

1. WHEN the Navigation_Bar is added to graph.html, THE graph.html Page SHALL preserve all existing graph visualization, insight panel, and interaction behavior.
2. WHEN the Navigation_Bar is added to dependency-tree.html, THE dependency-tree.html Page SHALL preserve all existing tree rendering, filtering, and detail panel behavior.
3. WHEN the Navigation_Bar is added to insights.html, THE insights.html Page SHALL preserve all existing dashboard list mode, detail mode, and popstate routing behavior.
4. WHEN the Navigation_Bar is added to index.html, THE index.html Page SHALL preserve all existing repo scoring and results display behavior.

### Requirement 13: Repo Context Encoding and Decoding Consistency

**User Story:** As a developer, I want all pages to use the same encoding and decoding functions for the repo query parameter, so that repo context is never corrupted during cross-page navigation.

#### Acceptance Criteria

1. THE Page SHALL use encodeURIComponent to encode all `?repo=` values when constructing URLs.
2. THE Page SHALL use decodeURIComponent to decode all `?repo=` values when reading from the URL.
3. IF a decoded `?repo=` value is an empty string or a malformed value (not matching owner/name format), THEN THE Page SHALL treat Repo_Context as unknown.

### Requirement 14: Navigation Accessibility

**User Story:** As a user relying on assistive technology, I want the navigation bar to use semantic markup and ARIA attributes, so that I can understand the page structure and my current location.

#### Acceptance Criteria

1. THE Navigation_Bar SHALL be rendered inside a semantic `<nav>` HTML element.
2. WHEN a Page is loaded, THE Navigation_Bar SHALL apply `aria-current="page"` to the link corresponding to the current Page.

### Requirement 15: Consistent Cross-Page Link Labels

**User Story:** As a user, I want cross-page links to use consistent labels across all pages, so that the navigation language is predictable and clear.

#### Acceptance Criteria

1. THE Cross_Page_Links targeting insights.html SHALL use the label "Open in Insights".
2. THE Cross_Page_Links targeting graph.html SHALL use the label "Open in Graph".
3. THE Cross_Page_Links targeting dependency-tree.html SHALL use the label "Open in Dependency Tree".
4. THE Cross_Page_Link labels SHALL be consistent across all Pages that display Cross_Page_Links.
