# Supply Chain Graph - User Guide

## Introduction

The Supply Chain Graph feature transforms flat risk scores into an interactive, visual representation of repository supply chain relationships. Instead of just seeing a single risk number, you can explore the connections between repositories, releases, maintainers, vulnerabilities, and risk factors.

**What you can do:**
- Visualize supply chain relationships as an interactive graph
- Identify security vulnerabilities (CVEs) affecting specific releases
- Understand maintainer contributions and bus factor
- See which package registries distribute the software
- Explore what drives the risk score
- Filter and search through complex supply chain data
- Export graphs for reports and presentations

## Getting Started

### Prerequisites

1. API server running (see [Setup Guide](SETUP.md))
2. Modern web browser (Chrome, Firefox, Safari, or Edge)
3. GitHub token configured in `.env` file

### Quick Start

1. **Start the API server:**
   ```bash
   uvicorn api.app:app --reload
   ```

2. **Open the visualization:**
   - Navigate to `ui/graph.html` in your browser
   - Or run the demo: `python demo_graph_visualization.py`

3. **Load your first graph:**
   - Enter a repository name (e.g., `numpy/numpy`)
   - Click "Load Graph"
   - Explore the interactive visualization!

### Example Repositories

Try these repositories to see different graph patterns:

- **`numpy/numpy`** - Large scientific library with many releases and maintainers
- **`psf/requests`** - Popular HTTP library with good maintenance
- **`pallets/flask`** - Web framework with active community
- **`django/django`** - Full-stack framework with comprehensive ecosystem

## Understanding the Graph

### Node Types

The graph contains six types of nodes, each representing a different entity:

#### 📦 Repository (Blue Box)
The central node representing the analyzed repository.

**Information shown:**
- Repository name and URL
- Overall maintenance risk score
- Risk label (low/medium/high/critical)
- Star count
- Archived status

**Example:** `numpy/numpy` with 28,500 stars and low risk (0.197)

#### 🏷️ Release (Green Diamond)
Tagged releases or versions of the software.

**Information shown:**
- Release tag (e.g., v1.26.0)
- Publication date
- Days since release
- Whether it's the latest release
- Prerelease flag

**Why it matters:** Shows release cadence and helps identify which versions have vulnerabilities.

#### 👤 Maintainer (Purple Circle)
Key contributors to the repository.

**Information shown:**
- GitHub username
- Contribution percentage
- Commit count
- Last activity date

**Why it matters:** Helps assess bus factor and governance. High concentration in one maintainer = higher risk.

#### ⚠️ CVE (Red Triangle)
Known security vulnerabilities.

**Information shown:**
- CVE identifier (e.g., CVE-2024-1234)
- Severity level (LOW/MEDIUM/HIGH/CRITICAL)
- CVSS score (0-10)
- Summary description
- Publication date
- Fixed version (if known)

**Why it matters:** Critical for security assessment. Shows which releases are vulnerable.

#### 📚 Registry (Orange Hexagon)
Package registries where the software is distributed.

**Information shown:**
- Registry type (PyPI, npm, Maven, etc.)
- Package name
- Latest version

**Why it matters:** Shows distribution channels and helps verify package authenticity.

#### ⚡ Risk Factor (Yellow Ellipse)
Significant drivers of the overall risk score.

**Information shown:**
- Metric name (e.g., "Days Since Last Release")
- Raw value
- Risk score contribution
- Weight in the model
- Category (activity/community/quality)

**Why it matters:** Explains what makes the repository risky. Focus on high-contribution factors.

### Edge Types

Edges show relationships between nodes:

- **REPO → RELEASE**: Repository has published this release
- **MAINTAINER → REPO**: Maintainer contributes to repository
- **RELEASE → CVE**: Release is affected by vulnerability
- **REPO → REGISTRY**: Repository is published to registry
- **REPO → RISK_FACTOR**: Repository exhibits this risk factor

**Visual cues:**
- Solid lines: High confidence relationships
- Dashed lines: Lower confidence (< 0.8)
- Red edges: High-risk relationships (CVEs)
- Arrow direction shows relationship flow

## Using the Visualization

### Basic Navigation

**Zoom:**
- Mouse wheel: Zoom in/out
- Pinch gesture (touchpad): Zoom
- Navigation buttons: Use built-in controls

**Pan:**
- Click and drag: Move around the graph
- Arrow keys: Navigate in any direction

**Select:**
- Click a node: Show details in side panel
- Click background: Deselect

**Hover:**
- Hover over node: See tooltip with key information
- Hover over edge: See relationship type

### Control Panel

#### Load Graph
Fetches graph data for the specified repository.

- Uses cached data if available (fast, < 100ms)
- Cache expires after 1 hour
- Good for repeated views of the same repository

#### Force Refresh
Bypasses cache and rebuilds graph from external APIs.

- Fetches fresh data from GitHub, OSV.dev, etc.
- Slower (1-3 seconds) but ensures latest data
- Use when you need up-to-date information

#### Node Type Filters
Show or hide specific node types.

**Use cases:**
- Hide risk factors to focus on supply chain structure
- Show only CVEs to focus on security
- Hide maintainers to simplify the view

**Tip:** Start with all types visible, then filter to focus on specific aspects.

#### Confidence Filter
Set minimum confidence threshold (0.0 - 1.0).

**Confidence levels:**
- **1.0**: Authoritative (GitHub API data)
- **0.95**: Highly reliable (OSV.dev CVE data)
- **0.9**: Reliable (GitHub contributor stats)
- **0.85**: Good (CVE-to-version mapping)
- **0.8**: Heuristic (registry detection)

**Use cases:**
- Set to 0.9 to see only high-confidence data
- Set to 0.0 to see all data including inferred relationships
- Use 0.8 as default for balanced view

#### Search
Find nodes by label or ID.

**Examples:**
- Search "v1.26" to find release nodes
- Search "CVE" to find vulnerabilities
- Search username to find maintainer

**Tip:** Search is case-insensitive and matches partial strings.

#### Show Provenance
Toggle display of data source information.

**When enabled, shows:**
- Data source (github_api, osv, heuristic, etc.)
- Timestamp when data was fetched
- Confidence scores
- Match confidence for CVEs and registries

**Use cases:**
- Auditing data quality
- Understanding where information comes from
- Identifying low-confidence data points
- Compliance and traceability

### Node Details Panel

Click any node to see detailed information in the side panel.

**Information displayed:**
- Node type and label
- All metadata fields
- Provenance information (if enabled)
- Confidence indicators
- Related edges

**Confidence badges:**
- 🟢 Green: High confidence (≥ 0.9)
- 🟡 Yellow: Medium confidence (0.8 - 0.9)
- 🔴 Red: Low confidence (< 0.8)

### Export Options

#### Export as JSON
Downloads complete graph data as JSON file.

**Includes:**
- All nodes with metadata
- All edges with relationships
- Provenance information
- Graph metadata

**Use cases:**
- Further analysis in other tools
- Archiving graph snapshots
- Sharing data with team
- Custom processing

**Filename:** `{repo}_graph.json`

#### Export as PNG
Captures current visualization as PNG image.

**Use cases:**
- Reports and presentations
- Documentation
- Sharing visual insights
- Archiving visual state

**Filename:** `{repo}_graph.png`

**Tip:** Adjust zoom and filters before exporting to capture the desired view.

## Understanding Provenance and Confidence

### What is Provenance?

Provenance tells you where each piece of data came from and how reliable it is. Every node and edge includes:

- **Source**: Where the data originated
- **Timestamp**: When it was fetched
- **Confidence**: How reliable it is (0.0 - 1.0)

### Data Sources

**github_api** (Confidence: 1.0)
- Repository metadata
- Release information
- Contributor data
- Most reliable source

**osv** (Confidence: 0.95)
- CVE vulnerability data
- From OSV.dev database
- Highly reliable but may have false positives

**score_model** (Confidence: 1.0)
- Risk factor calculations
- Based on GitHub data
- Deterministic computation

**heuristic** (Confidence: 0.8)
- Registry detection from files
- Package name extraction
- Inferred relationships

### Why Confidence Matters

**High confidence (≥ 0.9):**
- Data from authoritative sources
- Can be trusted for decisions
- Suitable for compliance reporting

**Medium confidence (0.8 - 0.9):**
- Reliable but some uncertainty
- Good for analysis
- Verify for critical decisions

**Low confidence (< 0.8):**
- Heuristic or inferred data
- Use with caution
- Verify independently for important decisions

**Example:** A CVE node with 0.92 match confidence means the system is 92% confident that the CVE affects the linked release version.

## Configuration Options

### API Parameters

Customize graph generation with query parameters:

```bash
# Maximum number of releases (default: 10)
?max_releases=5

# Maximum number of maintainers (default: 5)
?max_maintainers=3

# Include/exclude CVE nodes (default: true)
?include_cves=false

# Force refresh (default: false)
?refresh=true
```

**Example:**
```bash
curl "http://localhost:8000/api/graph?repo=numpy/numpy&max_releases=5&include_cves=false"
```

### Performance Tuning

**For faster loading:**
- Reduce `max_releases` to 5
- Reduce `max_maintainers` to 3
- Set `include_cves=false` (CVE fetching is slowest)
- Use cached data (don't force refresh)

**For comprehensive analysis:**
- Increase `max_releases` to 20
- Increase `max_maintainers` to 10
- Keep `include_cves=true`
- Force refresh for latest data

## Common Use Cases

### Security Assessment

**Goal:** Identify vulnerabilities in a repository.

**Steps:**
1. Load graph with `include_cves=true`
2. Filter to show only CVE nodes
3. Click each CVE to see severity and affected releases
4. Check if latest release has CVEs
5. Export findings as JSON for reporting

**What to look for:**
- High/Critical severity CVEs
- CVEs in latest release
- Unfixed vulnerabilities
- Multiple CVEs in same release

### Maintainer Analysis

**Goal:** Assess bus factor and governance.

**Steps:**
1. Load graph with default settings
2. Filter to show only maintainer nodes
3. Check contribution percentages
4. Look for concentration in one maintainer
5. Check last activity dates

**What to look for:**
- Single maintainer with > 50% contributions (high risk)
- Inactive maintainers (no recent activity)
- Diverse maintainer base (lower risk)
- Aggregate maintainer node (many small contributors)

### Release Cadence Analysis

**Goal:** Understand release patterns and activity.

**Steps:**
1. Load graph with `max_releases=20`
2. Filter to show only release nodes
3. Check publication dates
4. Look at days_ago values
5. Identify release frequency

**What to look for:**
- Regular release pattern (good)
- Long gaps between releases (potential risk)
- Recent releases (active maintenance)
- Prerelease tags (development activity)

### Supply Chain Mapping

**Goal:** Understand distribution channels.

**Steps:**
1. Load graph with default settings
2. Look for registry nodes
3. Check package names match repository
4. Verify latest versions align
5. Check confidence scores

**What to look for:**
- Multiple registries (wider distribution)
- Package name mismatches (potential confusion)
- Low confidence registry detection (verify manually)
- Missing registries (limited distribution)

### Risk Factor Investigation

**Goal:** Understand what drives the risk score.

**Steps:**
1. Load graph with default settings
2. Filter to show only risk factor nodes
3. Sort by contribution value
4. Click high-contribution factors
5. Check raw values and categories

**What to look for:**
- High-contribution factors (> 0.1)
- Activity-related risks (stale releases, inactive repo)
- Community risks (few contributors, low engagement)
- Quality risks (many open issues, no tests)

## Troubleshooting

### Graph doesn't load

**Symptoms:** Empty state or error message

**Solutions:**
1. Check API server is running:
   ```bash
   curl http://127.0.0.1:8000/api/health
   ```
2. Open browser console (F12) and check for errors
3. Verify repository name is correct format: `owner/repo`
4. Try a known-good repository like `numpy/numpy`
5. Check GitHub token is configured in `.env`

### Empty graph

**Symptoms:** Graph loads but has no nodes

**Possible causes:**
- Repository has no releases
- Repository is private or doesn't exist
- External APIs failed (check warnings in metadata)

**Solutions:**
1. Try a different repository
2. Check API response in browser console
3. Look for warnings in metadata section
4. Verify repository is public

### Slow loading

**Symptoms:** Graph takes > 5 seconds to load

**Solutions:**
1. Use cached data (don't force refresh)
2. Reduce `max_releases` to 5
3. Reduce `max_maintainers` to 3
4. Set `include_cves=false` to skip CVE fetching
5. Check network connection

### Visualization looks messy

**Symptoms:** Nodes overlap, edges cross badly

**Solutions:**
1. Refresh the page to reset layout
2. Use filters to reduce node count
3. Zoom out to see full structure
4. Try different browser (layout may vary)

### Low confidence data

**Symptoms:** Many nodes with red confidence badges

**Possible causes:**
- Heuristic registry detection
- CVE version matching uncertainty
- Inferred relationships

**Solutions:**
1. Verify important data manually
2. Check provenance information
3. Use confidence filter to hide low-confidence nodes
4. Cross-reference with official sources

## Best Practices

### For Security Analysis

1. Always force refresh for security assessments
2. Focus on high/critical severity CVEs
3. Check CVE publication dates (recent = more urgent)
4. Verify CVE-to-release mappings manually for critical decisions
5. Export findings for audit trail

### For Risk Assessment

1. Start with overall graph view
2. Identify high-contribution risk factors
3. Investigate each major risk driver
4. Check maintainer diversity
5. Assess release cadence
6. Document findings with screenshots

### For Compliance

1. Enable provenance display
2. Use high confidence threshold (≥ 0.9)
3. Export graph as JSON for records
4. Document data sources
5. Note any warnings or partial data
6. Verify critical information independently

### For Presentations

1. Filter to relevant node types
2. Adjust zoom for readability
3. Export as PNG at desired view
4. Use confidence filter to show only reliable data
5. Prepare explanations for each node type

## Advanced Tips

### Keyboard Shortcuts

- **Arrow keys**: Navigate graph
- **+/-**: Zoom in/out (some browsers)
- **Escape**: Deselect node
- **F12**: Open browser console for debugging

### URL Parameters

You can bookmark specific graph views:

```
ui/graph.html?repo=numpy/numpy&refresh=false&include_cves=true
```

### Browser Console

For debugging, open console (F12) and check:
- Network tab: API requests and responses
- Console tab: JavaScript errors
- Application tab: Cache status

### Performance Monitoring

Check metadata in API response:
- `generation_time_ms`: How long graph took to build
- `cache_hit`: Whether cache was used
- `data_sources`: Which APIs were called
- `warnings`: Any errors during generation

## FAQ

**Q: How often is data refreshed?**
A: Cached data expires after 1 hour. Use force refresh for latest data.

**Q: Can I analyze private repositories?**
A: Yes, if your GitHub token has access to the repository.

**Q: Why are some CVEs missing?**
A: CVE data depends on OSV.dev coverage. Not all vulnerabilities may be cataloged.

**Q: What does low confidence mean?**
A: Data is inferred or heuristic-based. Verify independently for critical decisions.

**Q: Can I export to other formats?**
A: Currently JSON and PNG. Use JSON export for custom processing.

**Q: How do I report issues?**
A: Check browser console for errors, review API logs, and document the issue.

**Q: Can I compare two repositories?**
A: Not currently. Load each separately and compare manually.

**Q: Why is my graph different from yesterday?**
A: Data changes over time (new releases, CVEs, etc.). Use force refresh for latest.

## Related Documentation

- **[API Documentation](API.md)** - Complete API reference
- **[Setup Guide](SETUP.md)** - Installation instructions
- **[Graph Visualization](GRAPH_VISUALIZATION.md)** - Technical details
- **[Design Document](../.kiro/specs/supply-chain-graph/design.md)** - Architecture

## Support

For help:
1. Check this user guide
2. Review [troubleshooting section](#troubleshooting)
3. Check browser console for errors
4. Review API logs for backend issues
5. Consult technical documentation

---

**Happy exploring! ��**
