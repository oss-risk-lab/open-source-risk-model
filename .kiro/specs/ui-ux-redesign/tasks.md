# Implementation Plan: UI/UX Redesign

## Overview

Transform the Deep Signal frontend from a functional technical tool into a polished, insight-driven product experience. Implementation follows a strict dependency order: shared design system first, then navigation module, then pages (Homepage → Insights → Graph → Dependency Tree). All work is frontend-only — static HTML/CSS/JS, no framework. The `/api/stats` endpoint already exists in `api/app.py` (added in the pre-deployment-finalization spec) — no new backend endpoints are created.

## Development Rules

- Do NOT modify multiple pages simultaneously. Complete and verify each page before moving to the next.
- Implementation order is strict: design system → navigation → homepage → insights → graph → dependency tree
- The actual API field names are `base_maintenance_risk` and `base_maintenance_label` (from `RepoInsight.to_dict()` in `src/open_source_risk_model/insights/models.py`). Use these exact names in all frontend code — do not use `maintenance_risk_score` or `maintenance_risk`.

## Tasks

- [x] 1. Create the shared design system stylesheet
  - [x] 1.1 Create `ui/design-system.css` with all CSS custom properties
    - Extract the `:root` block from the design document into `ui/design-system.css`
    - Include all background layers, borders, text colors, accent, status colors, spacing scale, radii, shadows, typography, and backward-compat aliases (`--mono`, `--sans`, `--green`, `--yellow`, `--red`, `--orange`, `--indigo`, `--muted`, `--muted2`)
    - Include the global `* { box-sizing: border-box; }` and `body` reset
    - _Requirements: 5.1, 5.2, 5.4, 5.5_

  - [x] 1.2 Add reusable component classes to `ui/design-system.css`
    - Implement `.ds-card` (generic card container with bg-elevated, border, radius-lg, shadow-sm, padding, hover transition)
    - Implement `.ds-section` (page section wrapper with max-width, margin auto, padding)
    - Implement `.ds-kpi` with `.ds-kpi-value` (mono font, 20px bold) and `.ds-kpi-label` (11px tertiary uppercase)
    - Implement `.ds-risk-tag` with `--high`, `--medium`, `--low` modifiers using status color variables
    - Implement `.ds-btn-primary` (accent bg, white text, radius-md, hover opacity)
    - Implement `.ds-btn-subtle` (transparent bg, border, tertiary text, hover surface bg)
    - Implement `.ds-nav`, `.ds-nav-brand`, `.ds-nav-links`, `.ds-nav-link`, `.ds-nav-link.active`
    - _Requirements: 5.3, 16.1, 16.2, 16.3_

  - [x] 1.3 Add loading state and spinner classes to `ui/design-system.css`
    - Implement `.ds-loading` with CSS shimmer keyframe animation (bg-surface to bg-overlay gradient)
    - Implement `.ds-spinner` with CSS-only rotate animation (20px circle, border animation)
    - Define `@keyframes ds-shimmer` and `@keyframes ds-spin`
    - _Requirements: 17.1, 17.2_

  - [x] 1.4 Write unit tests for design system CSS structure
    - Verify `design-system.css` defines all required CSS custom properties
    - Verify all required component classes (`.ds-card`, `.ds-section`, `.ds-kpi`, `.ds-risk-tag`, `.ds-btn-primary`, `.ds-btn-subtle`, `.ds-nav`) are defined
    - Verify transition durations are between 100ms and 200ms for interactive elements
    - _Requirements: 5.2, 5.3, 16.1_

- [x] 2. Checkpoint — Design system complete
  - Ensure `ui/design-system.css` exists with all custom properties and component classes. Ask the user if questions arise.

- [x] 3. Create the shared navigation module
  - [x] 3.1 Create `ui/nav.js` with navigation functions
    - Extract `parseRepoParam`, `getRepoFromUrl`, `buildPageUrl`, `getCurrentPageId`, `renderNav` from the duplicated inline scripts
    - Extract `getCrossLinks` and `renderCrossLinks` helper functions
    - Ensure `renderNav` creates a `<nav>` with class `ds-nav`, brand span "Deep Signal", and links for Home, Insights, Graph, Dependency Tree
    - Ensure the active page link gets `.active` class and `aria-current="page"` attribute
    - Ensure all links propagate the `repo` query parameter when present
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 19.1, 19.2_

  - [x] 3.2 Integrate `nav.js` into `ui/index.html`
    - Add `<link rel="stylesheet" href="design-system.css">` as the first stylesheet
    - Add `<script src="/ui/nav.js"></script>` after `config.js`
    - Remove the inline navigation JS code (parseRepoParam, getRepoFromUrl, buildPageUrl, getCurrentPageId, renderNav)
    - Remove the duplicated `:root` CSS custom properties that are now in `design-system.css`
    - Remove duplicated component class definitions (`.ds-nav`, `.ds-nav-brand`, etc.) that are now in the shared stylesheet
    - Call `renderNav(getCurrentPageId(), getRepoFromUrl())` after nav.js loads
    - _Requirements: 5.1, 6.1, 20.1, 20.3_

  - [x] 3.3 Integrate `nav.js` into `ui/insights.html`
    - Add `<link rel="stylesheet" href="design-system.css">` as the first stylesheet
    - Add `<script src="/ui/nav.js"></script>` after `config.js`
    - Remove the inline navigation JS code and duplicated CSS custom properties/nav classes
    - Call `renderNav(getCurrentPageId(), getRepoFromUrl())` after nav.js loads
    - _Requirements: 5.1, 6.1, 20.1, 20.3_

  - [x] 3.4 Integrate `nav.js` into `ui/graph.html`
    - Add `<link rel="stylesheet" href="design-system.css">` as the first stylesheet
    - Add `<script src="/ui/nav.js"></script>` after `config.js`
    - Remove the inline navigation JS code and duplicated CSS custom properties/nav classes
    - Call `renderNav(getCurrentPageId(), getRepoFromUrl())` after nav.js loads
    - _Requirements: 5.1, 6.1, 20.1, 20.3_

  - [x] 3.5 Integrate `nav.js` into `ui/dependency-tree.html`
    - Add `<link rel="stylesheet" href="design-system.css">` as the first stylesheet
    - Add `<script src="/ui/nav.js"></script>` after `config.js`
    - Remove the inline navigation JS code and duplicated CSS custom properties/nav classes
    - Call `renderNav(getCurrentPageId(), getRepoFromUrl())` after nav.js loads
    - _Requirements: 5.1, 6.1, 20.1, 20.3_

  - [x] 3.6 Write unit tests for navigation module
    - Verify `renderNav` produces correct HTML structure (nav > brand + links container)
    - Verify active page gets `.active` class and `aria-current="page"`
    - Verify repo parameter is propagated to all nav link hrefs
    - Verify `parseRepoParam` rejects invalid formats (no slash, empty, multiple slashes)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 4. Checkpoint — Navigation module integrated across all pages
  - Ensure all four pages import `design-system.css` and `nav.js`, navigation renders identically, and no duplicated nav JS remains. Ask the user if questions arise.

- [x] 5. Redesign the Homepage
  - [x] 5.1 Restructure `ui/index.html` Hero section
    - Update the hero to use an `h1` element with text "Open Source Risk Intelligence"
    - Add subtitle communicating the product value proposition
    - Change CTA button label to "Scan a Repository"
    - Add guidance text "Analyze any public GitHub repository in seconds." below the CTA input
    - Set input placeholder to "numpy/numpy" (not a submitted value)
    - Ensure empty/whitespace input retains focus without navigation
    - Apply `.ds-card`, `.ds-btn-primary` classes from the design system
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 18.1, 18.2_

  - [x] 5.2 Add Capabilities section to `ui/index.html`
    - Add a section below the Hero with 4-6 outcome-focused cards
    - Include cards for: vulnerable dependencies detection, maintainer risk assessment, dependency chain analysis, release health monitoring, and risk scoring
    - Apply `.ds-card` class with hover transition (border highlight and subtle elevation change)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 5.3 Add How It Works section to `ui/index.html`
    - Add a 3-step horizontal layout below the Capabilities section
    - Label steps as "Analyze", "Evaluate", and "Surface" with brief descriptions
    - Add directional indicators (arrows or connectors) between steps
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 5.4 Add Credibility section with dynamic stats to `ui/index.html`
    - Add KPI blocks for: "Repositories Analyzed", "Dependencies Mapped", "Packages Evaluated"
    - Fetch from existing `/api/stats` endpoint on page load (already exists in `api/app.py`); map `total_repos` and `fully_analyzed_repos` to KPIs
    - On API failure, display fallback values ("100+", "500+", "1000+")
    - Render KPI values using `.ds-kpi` class with monospace font
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.5 Write unit tests for Homepage sections
    - Verify h1 text content is "Open Source Risk Intelligence"
    - Verify CTA button label is "Scan a Repository"
    - Verify capability card count is between 4 and 6
    - Verify How It Works has exactly 3 steps labeled "Analyze", "Evaluate", "Surface"
    - Verify stats API fallback renders "100+" on failure
    - _Requirements: 1.1, 1.3, 2.1, 3.2, 4.3_

- [x] 6. Checkpoint — Homepage redesign complete
  - Ensure Homepage has Hero, Capabilities, How It Works, Credibility, and Explore sections all rendering correctly. Ask the user if questions arise.

- [x] 7. Restructure the Insights page detail view
  - [x] 7.1 Add Risk Summary Block to `ui/insights.html` detail view
    - When a single repo is selected, display a Risk Summary Block at the top of the detail view
    - Show Maintenance Risk score (`base_maintenance_risk` + `base_maintenance_label`) and Graph Signal Risk score (`graph_signal_score` + `graph_signal_label`) as two side-by-side `.ds-kpi` blocks
    - Display a color-coded `.ds-risk-tag` for each score
    - Include a one-sentence human-readable insight from `reasons[0]`
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 7.2 Add Top Risk Drivers section to `ui/insights.html`
    - Display 3-5 bullet points from the `reasons` array below the Risk Summary Block
    - Order bullets by signal severity (high first, then medium, then mild)
    - Cap at `min(reasons.length, 5)` bullets, minimum `min(reasons.length, 3)`
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 7.3 Add Grouped Insight Sections to `ui/insights.html`
    - Implement signal-to-category mapping: `cve_*`/`dependency_*`/`vulnerable_*` → "Dependency Risk", `maintainer_*`/`contributor_*`/`bus_factor_*` → "Maintainer Risk", `release_*`/`stale_*`/`version_*` → "Release Health"
    - Render each category as a collapsible panel with section header, category name, and severity indicator (highest severity in group)
    - For Dependency Risk section, also render `top_risky_dependencies` cards
    - When a category has zero signals, display "No issues detected" with low-severity indicator
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 7.4 Add loading states to Insights page
    - Show `.ds-loading` skeleton in the detail content area while fetching insight data
    - Replace skeleton with rendered content on completion
    - _Requirements: 17.1, 17.2, 17.3_

  - [x] 7.5 Add cross-page navigation links to Insights detail view
    - Display "Open in Graph" and "Open in Dependency Tree" buttons in the detail header actions area
    - Use `.ds-btn-subtle` styling, carry the `repo` query parameter
    - _Requirements: 19.1, 19.2_

  - [x] 7.6 Write unit tests for Insights detail view
    - Verify Risk Summary Block renders two KPI blocks with correct labels
    - Verify signal categorization maps `cve_risk` to "Dependency Risk"
    - Verify empty category shows "No issues detected"
    - Verify reasons bullet count is within bounds
    - _Requirements: 7.1, 8.2, 9.3_

- [x] 8. Checkpoint — Insights page restructure complete
  - Ensure Insights detail view shows Risk Summary Block, Top Risk Drivers, and Grouped Insight Sections. Ask the user if questions arise.

- [x] 8a. Checkpoint — Insights logic verified against real data
  - Load `numpy/numpy` (or another repo with data) and verify:
    - Risk Summary Block displays `base_maintenance_risk` + `base_maintenance_label` and `graph_signal_score` + `graph_signal_label` correctly
    - Top Risk Drivers shows actual `reasons` from the API response
    - Signal grouping correctly categorizes `direct_signals` into Dependency Risk, Maintainer Risk, and Release Health sections
    - Empty categories show "No issues detected"
  - This is the highest-risk area — do not proceed to Graph/Tree until this checkpoint passes.

- [x] 9. Fix Graph page layout and add legend
  - [x] 9.1 Fix panel overflow on `ui/graph.html`
    - Ensure `.details-panel` has `max-height: calc(100vh - 60px)` and `overflow-y: auto`
    - Add `word-break: break-word` and `overflow-wrap: break-word` to detail panel text items
    - Verify responsive breakpoint at 1200px reflows panel below graph at full width with 400px max-height
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 9.2 Add Node Legend to `ui/graph.html`
    - Add a legend component within the `.filters-panel` area
    - Map each node type (Repository, Release, Maintainer, CVE, Registry, Risk Factor) to its color swatch and label
    - Legend is always visible when graph is loaded, no toggle required
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 9.3 Update node label positioning in `ui/graph-viz.js`
    - Set default `font.vadjust: 20` in vis.js node options to push labels below shapes
    - Set `font.size: 11` and `font.color` to `rgba(255, 255, 255, 0.55)` (secondary text)
    - Preserve `vadjust: -24` for risk_factor nodes specifically
    - _Requirements: 12.1, 12.2_

  - [x] 9.4 Add selected node summary card structure to `ui/graph.html`
    - Ensure selected node panel shows node type, label, and key metadata
    - Use `.ds-risk-tag` for risk-relevant metadata (risk score, CVE severity, maintainer count)
    - Show placeholder text "Select a node to inspect its role, relationships, and risk context." when no node selected
    - _Requirements: 13.1, 13.2, 13.3_

  - [x] 9.5 Add loading state to Graph page
    - Show `.ds-spinner` in the graph container while fetching graph data
    - _Requirements: 17.1, 17.2_

  - [x] 9.6 Write unit tests for Graph page fixes
    - Verify panel overflow CSS properties are set correctly
    - Verify node legend contains all 6 node types
    - Verify vis.js font configuration has vadjust: 20 default
    - _Requirements: 10.1, 11.2, 12.1_

- [ ] 10. Enhance Dependency Tree page
  - [x] 10.1 Apply design system classes to `ui/dependency-tree.html` Summary Bar
    - Apply `.ds-kpi` classes to the summary grid stat cards (total deps, max depth, high-risk count)
    - Ensure Summary Bar updates dynamically when filters are applied
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 10.2 Enhance sidebar tree summary in `ui/dependency-tree.html` and `ui/dependency-tree.js`
    - Add ecosystem breakdown and risk level distribution to the sidebar summary content
    - Ensure sidebar recalculates on filter changes (already wired via `refetch()`)
    - Position sidebar summary below the Selected Node panel
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 10.3 Add loading state to Dependency Tree page
    - Ensure `.ds-spinner` class is used for the loading spinner
    - _Requirements: 17.1, 17.2_

  - [x] 10.4 Write unit tests for Dependency Tree enhancements
    - Verify Summary Bar renders KPI blocks with correct metrics
    - Verify sidebar summary includes ecosystem breakdown
    - _Requirements: 14.1, 15.1_

- [ ] 11. Final visual consistency pass
  - [x] 11.1 Verify all four pages import `design-system.css` as primary stylesheet
    - Confirm no page redefines CSS custom properties that exist in `design-system.css`
    - Confirm page-specific styles are in `<style>` blocks after the shared import, scoped to page-specific class names
    - _Requirements: 20.1, 20.2, 20.4_

  - [x] 11.2 Add guidance text for pages without repository parameter
    - On Insights, Graph, and Dependency Tree pages loaded without `?repo=`, display guidance text explaining how to load a repository
    - _Requirements: 18.3_

  - [x] 11.3 Verify auto-load from repository query parameter
    - Ensure all pages with a valid `?repo=` parameter auto-load data without additional user interaction
    - _Requirements: 19.3_

- [x] 12. Final checkpoint — All pages complete
  - Ensure all tests pass, all four pages render consistently with the shared design system, navigation works across pages, and no layout overflow issues. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Implementation order is strict: design system → navigation → homepage → insights → graph → dependency tree
- Do NOT modify multiple pages simultaneously — complete and verify each page before moving to the next
- No property-based tests — correctness properties are structural/visual checks validated via unit tests
- All pages remain static HTML/JS — no framework, no build step
- The frontend consumes only existing API endpoints — `/api/stats` already exists, no backend changes needed
- The actual API field names are `base_maintenance_risk` and `base_maintenance_label` — use these exact names everywhere
