# Implementation Plan: Insights Dashboard Redesign

## Overview

Redesign `ui/insights.html` from a flat dark-themed dashboard into a premium analytical SaaS dashboard. All changes are inline CSS/HTML/JS within the single file. The existing navigation bar helpers and all JavaScript logic are preserved. Implementation proceeds layer-by-layer: design system tokens → structural HTML → component CSS → JS function updates → polish.

## Tasks

- [x] 1. Design System CSS Tokens and Base Styles
  - [x] 1.1 Replace the existing `:root` CSS custom properties with the new design system tokens
    - Replace `--bg`, `--panel`, `--card`, `--border`, `--text`, `--muted`, `--muted2`, `--shadow`, `--radius`, `--mono`, `--sans` with the full token set
    - Add background layers: `--bg`, `--bg-surface`, `--bg-elevated`, `--bg-overlay`
    - Add border tokens: `--border`, `--border-subtle`, `--border-emphasis`
    - Add text hierarchy: `--text-primary`, `--text-secondary`, `--text-tertiary`
    - Add accent: `--accent`, `--accent-muted`
    - Add status colors with border variants: `--status-high-bg/text/border`, `--status-medium-bg/text/border`, `--status-low-bg/text/border`
    - Add spacing scale: `--sp-4` through `--sp-32`
    - Add radius tokens: `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-pill`
    - Add shadow tokens: `--shadow-sm`, `--shadow-md`, `--shadow-lg`
    - Add typography tokens: `--font-sans`, `--font-mono`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_
  - [x] 1.2 Update `body` styles to use flat `var(--bg)` background (remove radial gradients), reference `var(--font-sans)` and `var(--text-primary)`
    - _Requirements: 1.1, 3.1_
  - [x] 1.3 Update `.panel` base styles to use `var(--bg-elevated)`, `var(--border)`, `var(--radius-lg)`, `var(--shadow-sm)`, `var(--sp-24)` padding, and add `transition: border-color 0.15s ease` with hover rule for `var(--border-emphasis)`
    - _Requirements: 9.5, 16.4, 17.2, 18.2_
  - [x] 1.4 Add `.panel-header` styles with flex layout, `padding-bottom: var(--sp-12)`, `border-bottom: 1px solid var(--border-subtle)`, `margin-bottom: var(--sp-16)`
    - _Requirements: 9.5, 9.6, 9.7_
  - [x] 1.5 Add `.section-title` at 15px/700/`var(--text-primary)` and `.panel-subtitle` at 12px/`var(--text-tertiary)`
    - _Requirements: 9.6_
  - [x] 1.6 Update `.btn` styles to use design system tokens for padding, radius, border, background, and transitions
    - _Requirements: 3.1, 18.3_
  - [x] 1.7 Update `.err` styles to use design system tokens
    - _Requirements: 3.1_
  - [x] 1.8 Add `.text-high`, `.text-medium`, `.text-low` CSS classes for inline risk color text emphasis
    - Risk accent elements SHALL remain subtle and never dominate layout structure — signal, not decoration
    - _Requirements: 4.7, 16.5_

- [x] 2. Checkpoint — Verify design system tokens compile correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Hero Section
  - [x] 3.1 Add hero HTML structure with left/right split layout
    - Add `<div id="heroSection" class="hero" style="display:none;">` before the filter panel
    - Left side: `<div class="hero-left">` with `#heroValue` and `.hero-label`
    - Right side: `<div class="hero-right">` with `#heroInsight` div
    - _Requirements: 4.1, 4.2, 4.5, 4.6_
  - [x] 3.2 Add hero CSS: `.hero` flex container, `.hero-left` with `min-width: 120px`, `.hero-right` with `flex: 1`, `.hero-value` at 36–44px/800/mono (must be visually dominant over ALL other numeric values on the page — larger than KPI values at 18–22px), `.hero-label` at 11px/tertiary/uppercase, `.hero-insight` at 15px/secondary with left border
    - _Requirements: 4.5, 4.6, 4.8, 17.5_
  - [x] 3.3 Add hero risk accent CSS classes: `.hero-insight-high`, `.hero-insight-medium`, `.hero-insight-low` with corresponding `border-left-color` using status border tokens
    - _Requirements: 6.1, 6.2, 6.3, 16.1_
  - [x] 3.4 Add `generateInsightText(items)` JavaScript function
    - Filter HIGH items, find most common reason, build insight sentence
    - Return "All repositories are within acceptable risk thresholds. No immediate action required." when no HIGH items (confident, intentional tone)
    - Singular/plural handling for "repository"/"repositories"
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  - [x] 3.5 Add `getDominantRiskLevel(items)` JavaScript function
    - Return "high" > "medium" > "low" > "none" priority ordering
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 3.6 Add `renderHero(items, total)` JavaScript function
    - Set hero value to total, generate insight text with inline risk color span (`text-high`/`text-medium`/`text-low`), set risk accent border class, show hero
    - _Requirements: 4.1, 4.2, 4.7, 6.1, 6.2, 6.3_
  - [x] 3.7 Write property test for generateInsightText
    - **Property 4: generateInsightText correctness**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
  - [x] 3.8 Write property test for getDominantRiskLevel
    - **Property 6: getDominantRiskLevel priority ordering**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
  - [x] 3.9 Write property test for generateInsightText and getDominantRiskLevel purity
    - **Property 5: generateInsightText and getDominantRiskLevel purity**
    - **Validates: Requirements 5.6, 7.5**

- [x] 4. KPI Strip
  - [x] 4.1 Replace existing `.summary-strip` / `.summary-stat` CSS with `.kpi-strip`, `.kpi-card`, `.kpi-card-dominant`, `.kpi-card-secondary`, `.kpi-card-high`, `.kpi-value`, `.kpi-value-lg`, `.kpi-label`
    - KPI cards use `align-items: flex-start` for left-aligned analytical feel
    - Dominant card: `flex: 1.5`, secondary: `flex: 1`
    - HIGH card: `border-top: 2px solid var(--status-high-border)`
    - _Requirements: 8.1, 8.2, 8.3, 8.7, 8.8, 17.3, 17.4_
  - [x] 4.2 Update `renderSummaryStrip(items, total)` to produce weighted KPI cards with dominant total card, secondary status cards, and `kpi-card-high` class on HIGH card
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  - [x] 4.3 Write property test for KPI strip weighted layout
    - **Property 9: KPI strip weighted layout**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.7**

- [x] 5. Checkpoint — Verify hero and KPI render correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Panel System, Filter Controls, and Table Redesign
  - [x] 6.1 Wrap filter controls in a panel with `.panel-header` containing "Filters & Sorting" title
    - Update HTML structure: add panel-header div above `.filter-controls` (renamed to `.filter-bar`)
    - Update filter bar CSS: `flex-wrap: wrap`, `gap: var(--sp-12)`, `align-items: center`
    - Update select/input styles to use design system tokens
    - _Requirements: 9.1, 13.1, 13.2, 13.3_
  - [x] 6.2 Wrap table in a panel with `.panel-header` containing "Repositories by Risk" title and sort subtitle
    - Add panel wrapper around `#tableContainer` with narrative header
    - _Requirements: 9.2, 10.1_
  - [x] 6.3 Update table CSS for dense rows: `tbody td` and `thead th` padding to `var(--sp-8) var(--sp-12)`, thead styling (11px, tertiary, uppercase, 0.5px letter-spacing)
    - Add `tbody tr { transition: background 0.12s ease; }` for faster hover
    - Add active sort column header highlight: slightly brighter color + sort direction indicator (↑/↓) appended to the active column header text
    - _Requirements: 10.4, 11.1, 11.2, 11.4, 18.1_
  - [x] 6.4 Add `.row-high` CSS class: `border-left: 2px solid var(--status-high-border)`
    - _Requirements: 10.3, 16.3_
  - [x] 6.5 Update `renderTable(items)` to add `class="row-high"` on HIGH rows
    - Only add the class assignment, preserve all other rendering logic
    - _Requirements: 10.3, 19.13_
  - [x] 6.6 Update table column hierarchy CSS: repo name bold (700), score mono, reasons muted, signals badges
    - _Requirements: 10.2_
  - [x] 6.7 Write property test for risk accent on HIGH table rows
    - **Property 11: Risk accent on HIGH table rows**
    - **Validates: Requirements 10.3, 16.3, 19.13**

- [x] 7. Label Indicators and Signal Badges
  - [x] 7.1 Update `.label-indicator` CSS to use design system tokens: `var(--radius-pill)`, 11px, 700 weight, `var(--sp-4) var(--sp-12)` padding
    - Update `.label-high`, `.label-medium`, `.label-low` to use `var(--status-*-bg)` and `var(--status-*-text)`
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  - [x] 7.2 Update `.signal-badge` CSS to use design system tokens: `var(--radius-pill)`, 11px, 600 weight, `var(--sp-4) var(--sp-8)` padding
    - Update `.signal-high`, `.signal-medium`, `.signal-mild` to use status tokens
    - _Requirements: 12.5, 12.6, 12.7_

- [x] 8. Pagination Polish
  - [x] 8.1 Update `.pagination` CSS to use design system tokens: `gap: var(--sp-16)`, `var(--sp-16) 0` padding
    - Update `.range-text` to use 13px, `var(--text-secondary)`, `var(--font-mono)`
    - _Requirements: 14.1, 14.2, 14.3_

- [x] 9. Detail View Redesign
  - [x] 9.1 Update detail view CSS: `.detail-header`, `.detail-meta`, `.meta-card`, `.meta-card-score` styles using design system tokens
    - Score meta card: `meta-card-score .meta-value` at 32–40px/800/mono for dominant visual treatment — SHALL be the most visually prominent element in the detail view
    - _Requirements: 15.1, 15.2, 15.3, 15.6_
  - [x] 9.2 Update `renderDetailView(detail)` to wrap reasons in a panel with `.panel-header` ("Reasons" title) and signals in a panel with `.panel-header` ("Direct Signals" title + signal count subtitle)
    - Add `meta-card-score` class to the score meta card
    - Add cross-page links using `getCrossLinks()`
    - Preserve all other rendering logic
    - _Requirements: 15.3, 15.4, 15.5, 19.14_
  - [x] 9.3 Write property test for detail view rendering completeness
    - **Property 16: Detail view rendering completeness**
    - **Validates: Requirements 15.1, 15.2, 15.3, 15.4**

- [x] 10. Checkpoint — Verify panels, table, and detail view render correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. JavaScript State Management Updates
  - [x] 11.1 Update `setViewState(state)` to manage `#heroSection` visibility
    - "list" state: show hero, KPI strip, table, pagination
    - All other states: hide hero
    - _Requirements: 4.3, 4.4, 19.15_
  - [x] 11.2 Update `fetchAndRender()` to call `renderHero(appState.items, appState.total)` after `setViewState("list")`
    - _Requirements: 19.16_
  - [x] 11.3 Write property test for view state mutual exclusivity
    - **Property 14: View state mutual exclusivity**
    - **Validates: Requirements 4.3, 4.4, 19.15**

- [x] 12. Responsive Layout and Loading/Empty States
  - [x] 12.1 Update responsive `@media (max-width: 700px)` rules for new components: `.kpi-strip` stacks vertically, `.hero` stacks vertically, `.detail-header` stacks
    - _Requirements: 8.1_
  - [x] 12.2 Update `.loading-state` and `.empty-state` CSS to use design system tokens
    - _Requirements: 3.1_

- [x] 13. Navigation Bar and Accessibility Preservation
  - [x] 13.1 Update `.ds-nav` and related CSS to use design system tokens while preserving structure and all `aria-*` attributes
    - Preserve `aria-label="Main navigation"`, `aria-current="page"`, all form control labels
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 21.1, 21.2, 21.3, 21.4, 21.5_
  - [x] 13.2 Write property test for preserved pure function equivalence
    - **Property 13: Preserved pure function equivalence**
    - **Validates: Requirements 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.11**

- [x] 14. Final Checkpoint — Full integration verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify no external dependencies added (no `<link>` or external `<script src>` elements)
  - Verify all spacing values use the defined scale tokens
  - Verify all colors reference CSS custom properties
  - _Requirements: 2.1, 2.2, 3.1, 3.2, 22.1, 22.2, 22.3, 22.4, 22.5_

- [x] 15. Visual Tuning Pass
  - [x] 15.1 Verify font size hierarchy creates clear visual weight ordering: hero value (36–44px) > detail score (32–40px) > KPI dominant value (28px) > KPI secondary values (20px) > section titles (15px) > body text (13px) > labels (11px). Adjust any values that feel equal-weight.
  - [x] 15.2 Validate eye flow: Hero → KPI → Table. Ensure no section competes with the hero for attention. Reduce anything that feels repetitive or boxy.
  - [x] 15.3 Verify risk accent subtlety: borders and text color accents should provide signal without dominating layout. If any colored border feels heavy, reduce opacity in the status border tokens.
  - [x] 15.4 Check density contrast: table rows should feel noticeably tighter than panel padding. If the difference isn't perceptible, increase panel padding or decrease table cell padding.
  - [x] 15.5 Verify KPI strip "On this page" clarity: ensure users understand counts reflect the current page, not global totals. Add "Showing X of Y" context to the dominant KPI card label if needed.
  - [x] 15.6 Verify empty confidence state: when no HIGH items exist, the hero insight text should read "All repositories are within acceptable risk thresholds. No immediate action required." — confident and intentional tone.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- This is a single-file redesign — all changes go into `ui/insights.html` with inline CSS/HTML/JS
- The existing navigation bar helpers are already inlined and must be preserved exactly
- Property tests use fast-check (JavaScript) and validate pure helper functions
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
