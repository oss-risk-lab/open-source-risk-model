# Requirements Document

## Introduction

Deep Signal is an open source risk intelligence platform with a FastAPI backend and static HTML/JS frontend. The product currently has four pages (Homepage, Insights, Graph, Dependency Tree) that function correctly but present as a technical tool rather than a polished SaaS product. This redesign transforms the UI/UX into an insight-driven, visually consistent product experience that communicates risk clearly and guides users through the analysis workflow. The frontend remains static HTML/JS with no framework rewrite.

## Glossary

- **Deep_Signal**: The overall open source risk intelligence application comprising a FastAPI backend and static HTML/JS frontend
- **Homepage**: The landing page (`ui/index.html`) serving as the product entry point with repo scanning and navigation
- **Insights_Page**: The insights dashboard (`ui/insights.html`) displaying risk scores, signals, and repository analysis
- **Graph_Page**: The supply chain graph visualization page (`ui/graph.html`) using vis.js for network rendering
- **Dependency_Tree_Page**: The dependency tree explorer (`ui/dependency-tree.html`) showing transitive dependency structure
- **Design_System**: The shared set of CSS custom properties, reusable component classes, and layout patterns used across all pages
- **Hero_Section**: The prominent top section of the Homepage containing the product title, subtitle, and primary call-to-action
- **Risk_Summary_Block**: A top-level panel on the Insights_Page showing combined Maintenance Risk and Graph Signal Risk scores
- **Node_Legend**: A visual key on the Graph_Page mapping node colors and shapes to their entity types
- **Summary_Bar**: A horizontal strip of KPI metrics displayed at the top of a page section
- **CTA**: Call-to-action element prompting user interaction (button, input, link)
- **KPI_Block**: A reusable stat display component showing a numeric value with a label
- **Risk_Tag**: A color-coded label component indicating risk level (HIGH, MEDIUM, LOW)
- **Loading_Skeleton**: A lightweight placeholder animation shown while data is being fetched
- **Stats_API**: The `/api/stats` endpoint returning aggregate platform metrics (total repos, dependencies mapped, packages evaluated)
- **Default_Repo**: The pre-configured repository (`numpy/numpy`) loaded automatically on first visit

## Requirements

### Requirement 1: Homepage Hero Section

**User Story:** As a first-time visitor, I want to immediately understand what Deep Signal does and how to use it, so that I can start analyzing a repository within 10 seconds.

#### Acceptance Criteria

1. THE Homepage SHALL display a Hero_Section containing the title "Open Source Risk Intelligence" as an `h1` element
2. THE Homepage SHALL display a subtitle in the Hero_Section that communicates the product value proposition in one sentence
3. THE Homepage SHALL display a primary CTA labeled "Scan a Repository" with an adjacent text input accepting a GitHub repository identifier (e.g. `owner/repo`)
4. WHEN a user submits a repository identifier via the CTA input, THE Homepage SHALL navigate to the Insights_Page with the repository pre-loaded as a URL query parameter
5. WHEN the CTA input is empty and the user activates the submit action, THE Homepage SHALL retain focus on the input without navigation
6. THE Homepage SHALL display a guidance text below the CTA input reading "Analyze any public GitHub repository in seconds."

### Requirement 2: Homepage Capabilities Section

**User Story:** As a prospective user, I want to see what risks Deep Signal can identify, so that I understand the product's value before scanning a repository.

#### Acceptance Criteria

1. THE Homepage SHALL display a Capabilities Section below the Hero_Section containing 4 to 6 outcome-focused cards
2. THE Homepage SHALL include capability cards for: vulnerable dependencies detection, maintainer risk assessment, dependency chain analysis, release health monitoring, and risk scoring
3. WHEN a user hovers over a capability card, THE Homepage SHALL apply a visual emphasis transition (border highlight and subtle elevation change) within 150 milliseconds

### Requirement 3: Homepage How It Works Section

**User Story:** As a new user, I want to understand the analysis workflow, so that I trust the product methodology before using it.

#### Acceptance Criteria

1. THE Homepage SHALL display a "How It Works" section below the Capabilities Section using a 3-step horizontal layout
2. THE Homepage SHALL label the three steps as "Analyze", "Evaluate", and "Surface" with a brief description for each step
3. THE Homepage SHALL visually connect the three steps with directional indicators (arrows or connectors) to convey sequential flow

### Requirement 4: Homepage Credibility Section with Dynamic Stats

**User Story:** As a prospective user, I want to see platform-wide statistics, so that I gain confidence in the product's scale and data coverage.

#### Acceptance Criteria

1. THE Homepage SHALL display a Credibility Section containing KPI_Block components for: repositories analyzed, dependencies mapped, and packages evaluated
2. WHEN the Homepage loads, THE Homepage SHALL fetch aggregate statistics from the Stats_API endpoint
3. IF the Stats_API request fails, THEN THE Homepage SHALL display fallback static values (e.g. "100+") for each KPI_Block
4. THE Homepage SHALL render KPI_Block values using the monospace font family defined in the Design_System

### Requirement 5: Global Design System — Shared Stylesheet

**User Story:** As a developer maintaining the frontend, I want a single shared CSS file defining all reusable components, so that styling is consistent across pages and changes propagate globally.

#### Acceptance Criteria

1. THE Design_System SHALL be defined in a single shared CSS file (`ui/design-system.css`) imported by all four pages
2. THE Design_System SHALL define CSS custom properties for: background layers, border styles, text colors, accent colors, status colors (high/medium/low), spacing scale, border radii, shadows, and font families
3. THE Design_System SHALL define reusable component classes for: Card (`.ds-card`), Section wrapper (`.ds-section`), KPI_Block (`.ds-kpi`), Risk_Tag (`.ds-risk-tag`), Button primary (`.ds-btn-primary`), Button subtle (`.ds-btn-subtle`), and Navigation bar (`.ds-nav`)
4. THE Design_System SHALL use a minimal color palette where risk severity is communicated through color intensity (red for high, amber for medium, green for low)
5. THE Design_System SHALL remove heavy decorative shapes and use consistent spacing based on the defined spacing scale (4px increments)

### Requirement 6: Global Design System — Navigation Component

**User Story:** As a user navigating between pages, I want a consistent navigation bar on every page, so that I always know where I am and can switch pages without confusion.

#### Acceptance Criteria

1. THE Design_System SHALL define a navigation bar component rendered identically on all four pages
2. THE Navigation bar SHALL display the brand name "Deep Signal" on the left and page links (Home, Insights, Graph, Dependency Tree) on the right
3. THE Navigation bar SHALL visually indicate the current active page using a distinct background and text color on the active link
4. WHEN a repository is loaded in the current session, THE Navigation bar SHALL propagate the repository query parameter to all page links

### Requirement 7: Insights Page — Repo Risk Summary Block

**User Story:** As an analyst viewing a repository's insights, I want to see a top-level risk summary immediately, so that I understand the overall risk posture before reading details.

#### Acceptance Criteria

1. WHEN a single repository is selected on the Insights_Page, THE Insights_Page SHALL display a Risk_Summary_Block at the top of the detail view
2. THE Risk_Summary_Block SHALL show the Maintenance Risk score and the Graph Signal Risk score as two prominent KPI_Block components side by side
3. THE Risk_Summary_Block SHALL display a color-coded Risk_Tag for each score reflecting the risk label (HIGH, MEDIUM, LOW)
4. THE Risk_Summary_Block SHALL include a one-sentence human-readable insight summarizing the dominant risk factor

### Requirement 8: Insights Page — Top Risk Drivers Section

**User Story:** As an analyst, I want to see the top risk drivers at a glance, so that I can prioritize which risks to investigate first.

#### Acceptance Criteria

1. WHEN a single repository is selected on the Insights_Page, THE Insights_Page SHALL display a "Top Risk Drivers" section below the Risk_Summary_Block
2. THE "Top Risk Drivers" section SHALL list 3 to 5 bullet points extracted from the insight engine's `reasons` array
3. THE "Top Risk Drivers" section SHALL order bullet points by signal severity (high signals first, then medium, then mild)

### Requirement 9: Insights Page — Grouped Insight Sections

**User Story:** As an analyst, I want insights organized by risk category, so that I can focus on one risk domain at a time.

#### Acceptance Criteria

1. WHEN a single repository is selected on the Insights_Page, THE Insights_Page SHALL display insight details grouped into three sections: "Dependency Risk", "Maintainer Risk", and "Release Health"
2. THE Insights_Page SHALL display each grouped section as a collapsible panel with a section header showing the category name and a severity indicator
3. WHEN a grouped section contains no relevant signals, THE Insights_Page SHALL display the section header with a "No issues detected" message and a low-severity indicator

### Requirement 10: Graph Page — Panel Overflow Fix

**User Story:** As a user viewing the graph, I want the right-side detail panel to display correctly without content overflow, so that I can read all node information.

#### Acceptance Criteria

1. THE Graph_Page SHALL constrain the right-side details panel to a maximum height of `calc(100vh - 60px)` with vertical scroll overflow
2. THE Graph_Page SHALL prevent horizontal overflow of text content within detail panel items by applying `word-break: break-word` and `overflow-wrap: break-word`
3. WHILE the browser viewport width is below 1200 pixels, THE Graph_Page SHALL reflow the details panel below the graph container at full width with a maximum height of 400 pixels

### Requirement 11: Graph Page — Node Legend

**User Story:** As a user viewing the graph, I want a visible legend mapping node colors to entity types, so that I can interpret the visualization without prior knowledge.

#### Acceptance Criteria

1. THE Graph_Page SHALL display a Node_Legend component within the filters panel area
2. THE Node_Legend SHALL map each node type (Repository, Release, Maintainer, CVE, Registry, Risk Factor) to its corresponding color swatch and label
3. THE Node_Legend SHALL remain visible while the graph is loaded, without requiring user interaction to reveal it

### Requirement 12: Graph Page — Node Labels Outside Shapes

**User Story:** As a user viewing the graph, I want node labels positioned outside the node shapes, so that labels are readable without overlapping the node icons.

#### Acceptance Criteria

1. WHEN the graph is rendered, THE Graph_Page SHALL position node labels below the node shapes using the vis.js `font.vadjust` configuration
2. THE Graph_Page SHALL render node labels in the Design_System sans-serif font at 11 pixels with secondary text color

### Requirement 13: Graph Page — Selected Node Summary Card

**User Story:** As a user who clicks a graph node, I want a structured summary card showing key metadata, so that I can understand the node's role and risk context.

#### Acceptance Criteria

1. WHEN a user selects a node in the graph, THE Graph_Page SHALL display a summary card in the Selected Node panel with: node type, node label, and key metadata fields
2. THE summary card SHALL display risk-relevant metadata (risk score, CVE severity, maintainer count) using color-coded Risk_Tag components
3. WHEN no node is selected, THE Graph_Page SHALL display placeholder text in the Selected Node panel reading "Select a node to inspect its role, relationships, and risk context."

### Requirement 14: Dependency Tree Page — Top Summary Bar

**User Story:** As a user viewing the dependency tree, I want a top-level summary of key metrics, so that I understand the dependency landscape before exploring the tree.

#### Acceptance Criteria

1. WHEN a dependency tree is loaded, THE Dependency_Tree_Page SHALL display a Summary_Bar containing: total dependency count, maximum tree depth, and high-risk dependency count
2. THE Summary_Bar SHALL render each metric as a KPI_Block component using the Design_System styling
3. THE Summary_Bar SHALL update dynamically when filters are applied to reflect the filtered subset metrics

### Requirement 15: Dependency Tree Page — Sidebar Tree Summary

**User Story:** As a user exploring the dependency tree, I want the sidebar summary to stay synchronized with the main tree data, so that summary metrics reflect the current view.

#### Acceptance Criteria

1. WHEN a dependency tree is loaded, THE Dependency_Tree_Page SHALL display a sidebar summary panel showing: ecosystem breakdown, risk level distribution, and resolution status counts
2. WHEN the user applies filters (depth, risk level, direct-only), THE sidebar summary panel SHALL recalculate and display metrics for the filtered subset only
3. THE sidebar summary panel SHALL display below the Selected Node panel in the detail column

### Requirement 16: Micro-Interactions — Hover States and Transitions

**User Story:** As a user interacting with the UI, I want smooth visual feedback on interactive elements, so that the interface feels responsive and polished.

#### Acceptance Criteria

1. THE Design_System SHALL define hover state transitions for all interactive elements (buttons, cards, links, table rows) with a duration between 100 and 200 milliseconds
2. THE Design_System SHALL define hover states that modify border color, background color, or opacity without layout shifts
3. THE Design_System SHALL implement all transitions using CSS `transition` properties without JavaScript animation libraries

### Requirement 17: Micro-Interactions — Loading States

**User Story:** As a user waiting for data to load, I want visual loading indicators, so that I know the application is working and not frozen.

#### Acceptance Criteria

1. WHEN data is being fetched on any page, THE page SHALL display a Loading_Skeleton or spinner animation in the content area where data will appear
2. THE Loading_Skeleton SHALL use CSS-only animation (keyframes) without external animation libraries
3. WHEN data loading completes, THE page SHALL replace the Loading_Skeleton with the rendered content within one animation frame

### Requirement 18: User Flow — Auto-Load Default Repository

**User Story:** As a first-time visitor, I want to see a pre-loaded example analysis, so that I understand the product's output without needing to enter a repository.

#### Acceptance Criteria

1. WHEN a user visits the Homepage for the first time without a repository query parameter, THE Homepage SHALL pre-populate the CTA input with the Default_Repo value "numpy/numpy"
2. THE Homepage SHALL display the Default_Repo as placeholder text in the input, not as a submitted value, allowing the user to clear and enter a different repository
3. WHEN the user navigates to the Insights_Page, Graph_Page, or Dependency_Tree_Page without a repository query parameter, THE respective page SHALL display guidance text explaining how to load a repository

### Requirement 19: User Flow — Seamless Cross-Page Navigation

**User Story:** As a user analyzing a repository, I want to navigate between Insights, Graph, and Dependency Tree views without re-entering the repository name, so that my analysis context is preserved.

#### Acceptance Criteria

1. WHEN a repository is loaded on any page, THE page SHALL include cross-page navigation links (e.g. "Open in Graph", "Open in Dependency Tree") that carry the repository query parameter
2. THE cross-page navigation links SHALL appear in the page header actions area, styled as subtle buttons using the Design_System
3. WHEN the user navigates via a cross-page link, THE target page SHALL auto-load the repository data from the carried query parameter

### Requirement 20: Visual Consistency Across Pages

**User Story:** As a user navigating the product, I want all pages to share the same visual language, so that the product feels cohesive and professional.

#### Acceptance Criteria

1. THE Homepage, Insights_Page, Graph_Page, and Dependency_Tree_Page SHALL import the shared Design_System stylesheet as the primary style source
2. THE four pages SHALL use identical CSS custom property values for background colors, text colors, border styles, spacing, and typography
3. THE four pages SHALL use the same navigation bar component with identical markup structure and styling
4. IF a page requires page-specific styles, THEN THE page SHALL define those styles in a `<style>` block after the shared stylesheet import, scoped to page-specific class names

## Non-Goals

- No frontend framework migration (React, Vue, Svelte, etc.) — remains static HTML/JS
- No backend refactor of scoring, insight computation, or graph building logic
- No authentication, user accounts, or session management
- No database schema changes — all queries use existing tables
- No redesign of API endpoints beyond consuming existing `/api/stats`, `/api/insights`, `/api/graph`, `/api/demo-repos`, and `/repos/.../dependency-tree`
- No new backend endpoints — the frontend consumes only what already exists
- No third-party CSS frameworks (Bootstrap, Tailwind) — custom design system only
- No heavy JavaScript animation libraries (GSAP, Framer Motion, etc.)

## Success Metrics

- A new user can understand the product purpose within 10 seconds of landing on the Homepage
- Each page has a clear top-level summary visible without scrolling (above the fold)
- Visual consistency across all four pages — shared design system fully applied with zero page-specific color or typography overrides
- Zero layout overflow issues at browser zoom levels between 67% and 150%
- All pages load and render within 1 second after API response is received (no JS-heavy rendering bottlenecks)
- The shared `design-system.css` file is the single source of truth for all component styles — no duplicate CSS custom property definitions across pages

## Data Contracts

The frontend consumes the following API response shapes. These are locked — the redesign must work with these exact structures.

### Stats API — `GET /api/stats`

```json
{
  "total_repos": 145,
  "fully_analyzed_repos": 122,
  "coverage_ratio": 0.84
}
```

Fields used by the UI:
- `total_repos` → Credibility section "Repositories Analyzed" KPI
- `fully_analyzed_repos` → Credibility section "Dependencies Mapped" KPI
- `coverage_ratio` → not displayed directly, available for future use

### Insight API — `GET /api/insights/{owner}/{repo}`

```json
{
  "repo_full_name": "numpy/numpy",
  "base_maintenance_risk": 0.35,
  "base_maintenance_label": "LOW",
  "graph_signal_score": 0.42,
  "graph_signal_label": "MEDIUM",
  "reasons": [
    "3 known CVEs in dependency chain",
    "Single maintainer controls 2 critical packages",
    "Last release was 180+ days ago"
  ],
  "direct_signals": [
    {
      "signal_name": "cve_risk",
      "severity": "high",
      "score_contribution": 0.25,
      "reason": "3 known CVEs found in transitive dependencies"
    }
  ],
  "top_risky_dependencies": [
    {
      "package_name": "requests",
      "registry_type": "pypi",
      "risk_score": 0.7,
      "risk_label": "HIGH",
      "reasons": ["Known CVE-2023-XXXX"],
      "cve_count": 1
    }
  ]
}
```

Fields used by the UI:
- `base_maintenance_risk` + `base_maintenance_label` → Risk Summary Block "Maintenance Risk"
- `graph_signal_score` + `graph_signal_label` → Risk Summary Block "Graph Signal Risk"
- `reasons` → "Top Risk Drivers" bullet list
- `direct_signals` → Grouped insight sections (Dependency Risk, Maintainer Risk, Release Health) — grouped by `signal_name`
- `top_risky_dependencies` → Dependency Risk section detail cards

### Demo Repos API — `GET /api/demo-repos`

```json
{
  "repos": [
    {
      "repo": "numpy/numpy",
      "name": "numpy",
      "owner": "numpy",
      "tags": ["well-maintained", "popular", "deep-tree"],
      "risk_label": "LOW"
    }
  ]
}
```

### Graph API — `GET /api/graph?repo={owner/repo}`

Response shape is an existing graph JSON with `nodes` and `edges` arrays. No changes needed — the graph page already consumes this correctly.

### Dependency Tree API — `GET /repos/{owner}/{repo}/dependency-tree`

Response shape is an existing tree JSON with `tree`, `summary`, and `provenance` objects. No changes needed — the dependency tree page already consumes this correctly.
