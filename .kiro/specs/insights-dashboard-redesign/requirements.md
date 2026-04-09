# Requirements Document

## Introduction

This document defines the requirements for the Insights Dashboard Redesign feature. The redesign transforms `ui/insights.html` from a functional dark-themed dashboard into a premium, structured analytical SaaS dashboard with strong visual hierarchy, clean spacing, subtle depth, and a signature Risk Accent System. All existing JavaScript logic (API fetching, filtering, sorting, pagination, detail view, navigation) is preserved. The deliverable is a single `ui/insights.html` file with upgraded inline styles, structural HTML additions, and two new pure JavaScript functions.

## Glossary

- **Dashboard**: The `ui/insights.html` single-page application that displays risk insights for monitored repositories
- **Design_System**: The set of CSS custom properties defined in `:root` that serve as the single source of truth for all visual tokens (colors, spacing, typography, shadows, radii)
- **Hero_Section**: The primary focal point block at the top of the dashboard displaying total repo count and a dynamic insight sentence
- **KPI_Strip**: A horizontal row of metric cards showing total repos (dominant) and risk-level counts (secondary)
- **Panel**: A styled container with identity header used to wrap content sections (filters, table, detail reasons, detail signals)
- **Panel_Header**: A flex container inside a Panel containing a section title and optional subtitle
- **Risk_Accent_System**: A signature visual element that threads risk color through borders, highlights, and focus states across the interface
- **Dense_Mode**: Table cell padding using `var(--sp-8)` vertical spacing for fast scanning
- **Relaxed_Mode**: Panel and card padding using `var(--sp-16)` or greater for breathing room
- **Spacing_Scale**: The constrained set of spacing values: 4px, 8px, 12px, 16px, 24px, 32px
- **Dominant_Risk_Level**: The highest-priority risk level present in the current items (HIGH > MEDIUM > LOW > none)
- **Insight_Text**: A human-readable sentence generated from the current items summarizing the risk posture
- **generateInsightText**: A pure JavaScript function that produces Insight_Text from an array of insight items
- **getDominantRiskLevel**: A pure JavaScript function that returns the Dominant_Risk_Level from an array of insight items
- **Label_Indicator**: A pill-shaped element displaying a risk level (HIGH, MEDIUM, LOW) with status colors
- **Signal_Badge**: A tinted pill element displaying a signal type (CVE, Maintainer, Stale release) with severity colors
- **Navigation_Bar**: The `<nav class="ds-nav">` element providing cross-page navigation links
- **Text_Risk_Color**: CSS classes (`.text-high`, `.text-medium`, `.text-low`) that apply risk-level colors to inline text spans within the hero insight sentence
- **Hero_Left_Right_Split**: The hero section layout where the left side contains the primary metric value and the right side contains the insight text, creating visual tension and hierarchy

## Requirements

### Requirement 1: Design System Token Foundation

**User Story:** As a developer, I want all visual properties defined as CSS custom properties in `:root`, so that the dashboard has a single source of truth for colors, spacing, typography, shadows, and radii.

#### Acceptance Criteria

1. THE Design_System SHALL define background layer tokens (`--bg`, `--bg-surface`, `--bg-elevated`, `--bg-overlay`) as CSS custom properties in `:root`
2. THE Design_System SHALL define border tokens (`--border`, `--border-subtle`, `--border-emphasis`) as CSS custom properties in `:root`
3. THE Design_System SHALL define text hierarchy tokens (`--text-primary`, `--text-secondary`, `--text-tertiary`) as CSS custom properties in `:root`
4. THE Design_System SHALL define accent tokens (`--accent`, `--accent-muted`) as CSS custom properties in `:root`
5. THE Design_System SHALL define status color tokens for each risk level including background, text, and border variants (`--status-high-bg`, `--status-high-text`, `--status-high-border`, `--status-medium-bg`, `--status-medium-text`, `--status-medium-border`, `--status-low-bg`, `--status-low-text`, `--status-low-border`) as CSS custom properties in `:root`
6. THE Design_System SHALL define spacing scale tokens (`--sp-4`, `--sp-8`, `--sp-12`, `--sp-16`, `--sp-24`, `--sp-32`) corresponding to values 4px, 8px, 12px, 16px, 24px, 32px
7. THE Design_System SHALL define radius tokens (`--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-pill`) as CSS custom properties in `:root`
8. THE Design_System SHALL define shadow tokens (`--shadow-sm`, `--shadow-md`, `--shadow-lg`) as CSS custom properties in `:root`
9. THE Design_System SHALL define typography tokens (`--font-sans`, `--font-mono`) as CSS custom properties in `:root`

### Requirement 2: Spacing Scale Constraint

**User Story:** As a developer, I want all spacing values constrained to a defined scale, so that the dashboard maintains consistent visual rhythm.

#### Acceptance Criteria

1. WHEN any CSS property represents spacing (padding, margin, gap) in the redesigned stylesheet, THE Design_System SHALL use only values from the Spacing_Scale: 4px, 8px, 12px, 16px, 24px, or 32px
2. WHEN a spacing value is needed, THE Design_System SHALL reference the corresponding spacing token (`--sp-4` through `--sp-32`) rather than hardcoded pixel values

### Requirement 3: Color Token Exclusivity

**User Story:** As a developer, I want all color values to reference CSS custom properties, so that theme adjustments can be made from a single location.

#### Acceptance Criteria

1. WHEN a color value is used in the redesigned stylesheet outside the `:root` block, THE Design_System SHALL reference a CSS custom property defined in `:root`
2. THE Dashboard SHALL preserve existing hardcoded color values only within the JavaScript `LABEL_COLORS` and `SEVERITY_COLORS` constants


### Requirement 4: Hero Section

**User Story:** As a user, I want a clear focal point at the top of the dashboard that interprets the data for me, so that I immediately understand the risk posture without scanning the full table.

#### Acceptance Criteria

1. WHEN the Dashboard renders in list mode with items, THE Hero_Section SHALL display the total repository count as a large numeric value with monospace font
2. WHEN the Dashboard renders in list mode with items, THE Hero_Section SHALL display Insight_Text generated by the generateInsightText function
3. WHEN the Dashboard renders in list mode with zero total items, THE Hero_Section SHALL be hidden
4. WHEN the Dashboard renders in detail, loading, error, or empty state, THE Hero_Section SHALL be hidden
5. THE Hero_Section SHALL use `var(--bg-elevated)` background, `var(--border)` border, `var(--radius-lg)` border-radius, and `var(--shadow-sm)` box-shadow
6. THE Hero_Section SHALL use a left/right split layout where the left side (`hero-left`) has a fixed `min-width: 120px` containing the hero value and label, and the right side (`hero-right`) has `flex: 1` containing the insight text
7. WHEN HIGH items exist, THE Hero_Section insight text SHALL wrap the risk count phrase in a `<span class="text-high">` element using `color: var(--status-high-text)` for inline risk color emphasis
8. THE Hero_Section hero value SHALL be visually dominant over all other numeric values on the page (36–44px font-size vs KPI values at 18–22px)

### Requirement 5: Insight Text Generation

**User Story:** As a user, I want the dashboard to generate a human-readable insight sentence from the current data, so that I can quickly understand the dominant risk pattern.

#### Acceptance Criteria

1. WHEN zero items have `graph_signal_label` equal to "HIGH", THE generateInsightText function SHALL return exactly "All repositories are within acceptable risk thresholds. No immediate action required."
2. WHEN N items (N greater than 0) have `graph_signal_label` equal to "HIGH", THE generateInsightText function SHALL return a string containing the count N, the phrase "high-risk", and the most common reason across all HIGH items' reasons arrays in lowercase
3. WHEN exactly 1 item has `graph_signal_label` equal to "HIGH", THE generateInsightText function SHALL use the singular form "repository"
4. WHEN more than 1 item has `graph_signal_label` equal to "HIGH", THE generateInsightText function SHALL use the plural form "repositories"
5. WHEN HIGH items exist but all have empty reasons arrays, THE generateInsightText function SHALL return the count and "high-risk" phrase without a reason suffix
6. THE generateInsightText function SHALL be a pure function with no side effects and no DOM access
7. WHEN no HIGH items exist, THE generateInsightText function SHALL use a confident, intentional tone indicating no immediate action is required

### Requirement 6: Hero Risk Accent Border

**User Story:** As a user, I want the hero insight text to have a colored left border reflecting the dominant risk level, so that I get an immediate visual signal of the overall risk posture.

#### Acceptance Criteria

1. WHEN any items have `graph_signal_label` equal to "HIGH", THE Hero_Section insight element SHALL have class `hero-insight-high` applying `border-left-color: var(--status-high-border)`
2. WHEN no HIGH items exist but MEDIUM items exist, THE Hero_Section insight element SHALL have class `hero-insight-medium` applying `border-left-color: var(--status-medium-border)`
3. WHEN only LOW items exist, THE Hero_Section insight element SHALL have class `hero-insight-low` applying `border-left-color: var(--status-low-border)`

### Requirement 7: Dominant Risk Level Determination

**User Story:** As a developer, I want a pure function that determines the dominant risk level from the current items, so that the Risk_Accent_System can apply the correct accent color.

#### Acceptance Criteria

1. WHEN any items have `graph_signal_label` equal to "HIGH", THE getDominantRiskLevel function SHALL return "high"
2. WHEN no HIGH items exist but MEDIUM items exist, THE getDominantRiskLevel function SHALL return "medium"
3. WHEN only LOW items exist, THE getDominantRiskLevel function SHALL return "low"
4. WHEN the items array is empty, THE getDominantRiskLevel function SHALL return "none"
5. THE getDominantRiskLevel function SHALL be a pure function with no side effects

### Requirement 8: Weighted KPI Strip

**User Story:** As a user, I want the KPI summary to establish system scale before showing risk breakdown, so that I understand "how big is the system" before "what's inside it."

#### Acceptance Criteria

1. WHEN the Dashboard renders in list mode with items, THE KPI_Strip SHALL display exactly 4 cards: one dominant Total Repos card and three secondary status cards (High Risk, Medium Risk, Low Risk)
2. THE KPI_Strip dominant card SHALL have class `kpi-card-dominant` with `flex: 1.5` and a larger font size class `kpi-value-lg`
3. THE KPI_Strip secondary cards SHALL have class `kpi-card-secondary` with `flex: 1`
4. THE KPI_Strip High Risk card SHALL use `var(--status-high-text)` for the value color
5. THE KPI_Strip Medium Risk card SHALL use `var(--status-medium-text)` for the value color
6. THE KPI_Strip Low Risk card SHALL use `var(--status-low-text)` for the value color
7. THE KPI_Strip High Risk card SHALL additionally have class `kpi-card-high` applying a top border accent of `2px solid var(--status-high-border)`
8. THE KPI_Strip cards SHALL use `align-items: flex-start` for left-aligned content to create an analytical rather than widget-like appearance

### Requirement 9: Panel System with Identity Headers

**User Story:** As a user, I want each content section to have a clear identity through a header with title and optional subtitle, so that I can quickly understand what each section contains.

#### Acceptance Criteria

1. WHEN the filter controls section is rendered, THE Dashboard SHALL wrap the controls in a Panel with a Panel_Header containing the title "Filters & Sorting"
2. WHEN the data table section is rendered, THE Dashboard SHALL wrap the table in a Panel with a Panel_Header containing the title "Repositories by Risk" and a subtitle showing the current sort context
3. WHEN the detail view reasons section is rendered, THE Dashboard SHALL wrap the reasons in a Panel with a Panel_Header containing the title "Reasons"
4. WHEN the detail view signals section is rendered, THE Dashboard SHALL wrap the signals table in a Panel with a Panel_Header containing the title "Direct Signals" and a subtitle showing the signal count
5. THE Panel_Header SHALL use a flex layout with `justify-content: space-between` and `align-items: center`
6. THE Panel section title SHALL use 15px font-size, 700 font-weight, and `var(--text-primary)` color
7. THE Panel_Header SHALL have a bottom border divider of `1px solid var(--border-subtle)` with `padding-bottom: var(--sp-12)` and `margin-bottom: var(--sp-16)` to create a section feel

### Requirement 10: Table Redesign with Narrative Framing

**User Story:** As a user, I want the data table wrapped in a narrative context that tells me what I'm looking at and how it's sorted, so that the table feels like an analytical tool rather than raw data.

#### Acceptance Criteria

1. WHEN the table is rendered, THE Dashboard SHALL display a Panel_Header above the table with the title "Repositories by Risk" and a subtitle describing the current sort order
2. THE Dashboard table SHALL maintain the existing column hierarchy: repository name (bold, 700 weight), score (monospace font), label (pill with status color), reasons (secondary text color), signals (badge elements)
3. WHEN a table row represents an item with `graph_signal_label` equal to "HIGH", THE Dashboard SHALL add class `row-high` to the `<tr>` element applying `border-left: 2px solid var(--status-high-border)`
4. WHEN the table is sorted by a column, THE Dashboard SHALL visually highlight the active sort column header with slightly brighter text color and a sort direction indicator (↑ ascending, ↓ descending)

### Requirement 11: Dense Table Rows

**User Story:** As a user, I want table rows to use tighter padding for faster scanning of large datasets, so that I can quickly identify high-risk repositories.

#### Acceptance Criteria

1. THE Dashboard table body cells (`tbody td`) SHALL use Dense_Mode padding of `var(--sp-8) var(--sp-12)` (8px vertical, 12px horizontal)
2. THE Dashboard table header cells (`thead th`) SHALL use Dense_Mode padding of `var(--sp-8) var(--sp-12)`
3. THE Dashboard signals table cells SHALL use Dense_Mode padding of `var(--sp-8) var(--sp-12)`
4. THE Dashboard table header cells SHALL use 11px font-size, `var(--text-tertiary)` color, 700 font-weight, uppercase text-transform, and 0.5px letter-spacing


### Requirement 12: Label Indicators and Signal Badges

**User Story:** As a user, I want risk levels and signals displayed as clearly colored pills, so that I can visually distinguish severity at a glance.

#### Acceptance Criteria

1. THE Dashboard Label_Indicator SHALL use pill styling with `var(--radius-pill)` border-radius, 11px font-size, 700 font-weight, uppercase text-transform, and 0.5px letter-spacing
2. THE Dashboard Label_Indicator for HIGH SHALL use `var(--status-high-bg)` background and `var(--status-high-text)` color
3. THE Dashboard Label_Indicator for MEDIUM SHALL use `var(--status-medium-bg)` background and `var(--status-medium-text)` color
4. THE Dashboard Label_Indicator for LOW SHALL use `var(--status-low-bg)` background and `var(--status-low-text)` color
5. THE Dashboard Signal_Badge SHALL use pill styling with `var(--radius-pill)` border-radius, 11px font-size, and 600 font-weight
6. THE Dashboard Signal_Badge for high severity SHALL use `var(--status-high-bg)` background and `var(--status-high-text)` color
7. THE Dashboard Signal_Badge for medium severity SHALL use `var(--status-medium-bg)` background and `var(--status-medium-text)` color

### Requirement 13: Filter and Sort Controls Upgrade

**User Story:** As a user, I want the filter and sort controls wrapped in a cohesive panel with a clear header, so that the controls feel like a purposeful section of the dashboard.

#### Acceptance Criteria

1. WHEN the filter controls are rendered, THE Dashboard SHALL wrap the controls in a Panel with a Panel_Header containing the title "Filters & Sorting"
2. THE Dashboard filter bar SHALL use flex layout with `flex-wrap: wrap`, `gap: var(--sp-12)`, and `align-items: center`
3. THE Dashboard filter select and number input elements SHALL use `var(--sp-8) var(--sp-12)` padding, `var(--radius-md)` border-radius, `var(--border)` border, `var(--bg-surface)` background, and `var(--text-primary)` color

### Requirement 14: Pagination Polish

**User Story:** As a user, I want minimal, polished pagination controls, so that page navigation feels clean and consistent with the dashboard aesthetic.

#### Acceptance Criteria

1. THE Dashboard pagination SHALL use flex layout with `align-items: center`, `justify-content: center`, and `gap: var(--sp-16)`
2. THE Dashboard pagination range text SHALL use 13px font-size, `var(--text-secondary)` color, and `var(--font-mono)` font-family
3. THE Dashboard pagination buttons SHALL use the existing button styling with design system tokens

### Requirement 15: Detail View Upgrade

**User Story:** As a user, I want the detail view to use structured panels with identity headers for each section, so that the single-repo deep dive feels organized and professional.

#### Acceptance Criteria

1. WHEN the detail view is rendered, THE Dashboard SHALL display a header with the repository name, a "Back to list" link, and cross-page navigation links
2. WHEN the detail view is rendered, THE Dashboard SHALL display meta cards for score (monospace font), label (with Label_Indicator), and base maintenance risk (monospace font)
3. WHEN the detail view is rendered, THE Dashboard score meta card SHALL use class `meta-card-score` with a dominant visual treatment: 32–40px font-size, 800 font-weight, and `var(--font-mono)` font-family on the meta value
4. WHEN the detail view reasons section is rendered, THE Dashboard SHALL wrap the reasons list in a Panel with a Panel_Header containing the title "Reasons"
5. WHEN the detail view signals section is rendered, THE Dashboard SHALL wrap the signals table in a Panel with a Panel_Header containing the title "Direct Signals" and a subtitle showing the count of signals detected
6. THE Dashboard detail view panels SHALL respond to hover with a border-color transition to `var(--border-emphasis)`
7. THE Dashboard detail view score SHALL be the most visually prominent element in the detail view

### Requirement 16: Risk Accent System

**User Story:** As a user, I want a consistent visual thread of risk color through borders and highlights across the interface, so that the dashboard has a distinctive visual identity.

#### Acceptance Criteria

1. WHEN the Hero_Section is rendered, THE Risk_Accent_System SHALL apply a left border color on the insight element matching the Dominant_Risk_Level using status border tokens
2. WHEN the KPI_Strip is rendered, THE Risk_Accent_System SHALL apply a `2px solid var(--status-high-border)` top border on the High Risk card
3. WHEN a table row represents a HIGH risk item, THE Risk_Accent_System SHALL apply a `2px solid var(--status-high-border)` left border via the `row-high` class
4. WHEN a user hovers over any Panel element, THE Risk_Accent_System SHALL transition the border-color to `var(--border-emphasis)` with 0.15s ease timing
5. THE Risk_Accent_System elements SHALL remain subtle and never dominate layout structure — providing signal, not decoration

### Requirement 17: Density Control

**User Story:** As a user, I want intentional density variation between tables and panels, so that tables are scannable while panels have breathing room.

#### Acceptance Criteria

1. THE Dashboard table cells SHALL use Dense_Mode with `var(--sp-8)` vertical padding (8px)
2. THE Dashboard Panel elements SHALL use Relaxed_Mode with `var(--sp-24)` padding (24px)
3. THE Dashboard KPI cards SHALL use Relaxed_Mode with `var(--sp-12) var(--sp-16)` padding
4. THE Dashboard dominant KPI card SHALL use Relaxed_Mode with `var(--sp-16) var(--sp-24)` padding
5. THE Dashboard Hero_Section SHALL use Relaxed_Mode with `var(--sp-24)` padding

### Requirement 18: Interaction Polish

**User Story:** As a user, I want smooth hover transitions on interactive elements, so that the dashboard feels responsive and polished.

#### Acceptance Criteria

1. WHEN a user hovers over a table row, THE Dashboard SHALL apply a smooth background transition with 0.12s ease timing for a sharper feel
2. WHEN a user hovers over a Panel, THE Dashboard SHALL transition border-color with duration between 0.1s and 0.2s using ease timing function
3. WHEN a user hovers over a button, THE Dashboard SHALL apply a smooth background transition
4. THE Dashboard SHALL apply no abrupt visual state changes on any interactive element

### Requirement 19: Functional Preservation

**User Story:** As a developer, I want all existing JavaScript logic preserved exactly, so that the redesign is purely visual with no behavioral regressions.

#### Acceptance Criteria

1. THE Dashboard SHALL preserve the existing `buildApiUrl` function with identical behavior
2. THE Dashboard SHALL preserve the existing `signalBadgeText` function with identical behavior
3. THE Dashboard SHALL preserve the existing `labelColorClass` function with identical behavior
4. THE Dashboard SHALL preserve the existing `paginationRangeText` function with identical behavior
5. THE Dashboard SHALL preserve the existing `paginationButtonState` function with identical behavior
6. THE Dashboard SHALL preserve the existing `nextOffset` and `prevOffset` functions with identical behavior
7. THE Dashboard SHALL preserve the existing `fetchInsightsList` and `fetchRepoInsight` functions with identical behavior
8. THE Dashboard SHALL preserve the existing `navigateToDetail` and `navigateToList` functions with identical behavior
9. THE Dashboard SHALL preserve the existing `onFilterChange`, `onSortChange`, and `onPageChange` event handlers with identical behavior
10. THE Dashboard SHALL preserve the existing `initRoute` URL routing logic with identical behavior
11. THE Dashboard SHALL preserve the existing `summaryCounts` function with identical behavior
12. THE Dashboard SHALL preserve the existing `appState` object structure and all state management logic
13. WHEN the `renderTable` function is updated, THE Dashboard SHALL only add the `row-high` class assignment to HIGH rows, preserving all other rendering logic
14. WHEN the `renderDetailView` function is updated, THE Dashboard SHALL only add Panel wrapping with Panel_Headers around reasons and signals sections, preserving all other rendering logic
15. WHEN the `setViewState` function is updated, THE Dashboard SHALL only add Hero_Section visibility management, preserving all other state transitions
16. WHEN the `fetchAndRender` function is updated, THE Dashboard SHALL only add calls to `renderHero`, preserving all other orchestration logic

### Requirement 20: Navigation Bar Preservation

**User Story:** As a user, I want the navigation bar preserved exactly as-is, so that cross-page navigation continues to work identically.

#### Acceptance Criteria

1. THE Dashboard SHALL render the Navigation_Bar as the first child of the `.wrap` container
2. THE Dashboard Navigation_Bar SHALL retain the `aria-label="Main navigation"` attribute
3. THE Dashboard Navigation_Bar SHALL retain all existing page links (Home, Insights, Graph, Dependency Tree) with identical href construction
4. THE Dashboard Navigation_Bar SHALL retain the active page indicator with `aria-current="page"` attribute

### Requirement 21: Accessibility Preservation

**User Story:** As a user relying on assistive technology, I want all existing accessibility attributes preserved, so that the dashboard remains usable with screen readers and keyboard navigation.

#### Acceptance Criteria

1. THE Dashboard SHALL preserve all existing `aria-label` attributes on form controls and navigation elements
2. THE Dashboard SHALL preserve the `aria-live="polite"` attribute on the pagination range text
3. THE Dashboard SHALL preserve all `scope="col"` attributes on table header cells
4. THE Dashboard SHALL preserve all existing `<label>` element associations with form controls
5. THE Dashboard SHALL preserve the `aria-current="page"` attribute on the active navigation link

### Requirement 22: No External Dependencies

**User Story:** As a developer, I want the redesign to use only inline HTML, CSS, and JavaScript with no external dependencies, so that the page remains self-contained and loads without network dependencies beyond the API.

#### Acceptance Criteria

1. THE Dashboard SHALL achieve all styling using only inline CSS within a `<style>` element
2. THE Dashboard SHALL achieve all behavior using only inline JavaScript within a `<script>` element
3. THE Dashboard SHALL not reference any external CSS frameworks, JavaScript libraries, or CDN resources
4. THE Dashboard SHALL not add any `<link>` elements referencing external stylesheets
5. THE Dashboard SHALL not add any `<script>` elements with `src` attributes referencing external scripts
