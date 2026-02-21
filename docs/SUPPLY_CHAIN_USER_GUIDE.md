# Supply Chain Graph - User Guide

## Introduction

The Supply Chain Graph feature transforms flat risk scores into an interactive, visual representation of your repository's supply chain relationships. Instead of just seeing a single risk number, you can explore how repositories, releases, maintainers, vulnerabilities, and risk factors connect together.

**What you'll learn:**
- How to generate and view supply chain graphs
- Understanding different node and edge types
- Using provenance and confidence information
- Interactive visualization features
- Configuration options

---

## Getting Started

### Prerequisites

Before using the supply chain graph feature, ensure you have:

1. **API Server Running:**
   ```bash
   cd api
   uvicorn app:app --reload
   ```

2. **GitHub Token Configured:**
   - Set `GITHUB_TOKEN` in your `.env` file
   - See [Setup Guide](SETUP.md) for details

3. **Modern Web Browser:**
   - Chrome/Edge 90+, Firefox 88+, or Safari 14+

### Quick Start

1. **Open the visualization:**
   - Navigate to `ui/graph.html` in your browser
   - Or run: `python demo_graph_visualization.py`

2. **Enter a repository:**
   - Type a repository name (e.g., `numpy/numpy`)
   - Or paste a GitHub URL

3. **Click "Load Graph":**
   - The graph will load from cache if available
   - First load may take 2-3 seconds

4. **Explore:**
   - Click nodes to see details
   - Use filters to focus on specific aspects
   - Zoom and pan to navigate

---

## Understanding the Graph

### Node Types

The graph contains six types of nodes, each representing a different aspect of the supply chain:

#### 1. Repository (📦 Blue Box)

The central node representing the analyzed repository.

**What it shows:**
- Repository name and URL
- Overall maintenance risk score
- Risk label (low/medium/high/critical)
- Star count and archived status
- Feature coverage and confidence

**Example:**
```
numpy/numpy
Risk: 0.197 (low)
Stars: 28,500
Confidence: high
```

#### 2. Release (🏷️ Green Diamond)

Tagged releases or versions of the repository.

**What it shows:**
- Release tag name (e.g., v1.26.0)
- Publication date
- Days since release
- Whether it's the latest release
- Prerelease flag

**Why it matters:**
- Shows release frequency and recency
- Helps identify which versions have vulnerabilities
- Indicates project activity level

**Example:**
```
v1.26.0
Published: 2024-09-16
150 days ago
Latest: Yes
```

#### 3. Maintainer (👤 Purple Circle)

Key contributors to the repository.

**What it shows:**
- GitHub username
- Contribution percentage
- Commit count
- Last activity date

**Why it matters:**
- Reveals bus factor (concentration risk)
- Shows governance structure
- Indicates active vs. inactive maintainers

**Example:**
```
charris
Contributions: 23%
Commits: 5,234
Type: individual
```

#### 4. CVE (⚠️ Red Triangle)

Known security vulnerabilities affecting the repository.

**What it shows:**
- CVE identifier
- Severity level (LOW/MEDIUM/HIGH/CRITICAL)
- CVSS score (0-10)
- Brief description
- Publication date
- Fixed version (if known)

**Why it matters:**
- Critical for security assessment
- Shows which releases are vulnerable
- Helps prioritize updates

**Example:**
```
CVE-2024-1234
Severity: HIGH (7.5)
Buffer overflow vulnerability
Fixed in: v1.22.0
```

#### 5. Registry (📚 Orange Hexagon)

Package registries where the repository is published.

**What it shows:**
- Registry type (PyPI, npm, Maven, etc.)
- Package name
- Latest version
- Registry URL

**Why it matters:**
- Shows distribution channels
- Helps verify package authenticity
- Indicates ecosystem integration

**Example:**
```
PyPI: numpy
Package: numpy
Latest: 1.26.0
```

#### 6. Risk Factor (⚡ Yellow Ellipse)

Significant risk drivers from the scoring model.

**What it shows:**
- Metric name
- Raw value
- Risk score (0-1)
- Contribution to overall risk
- Category (activity/community/quality)

**Why it matters:**
- Explains what drives the risk score
- Helps identify improvement areas
- Shows relative importance of factors

**Example:**
```
Days Since Last Release
Value: 150 days
Risk: 0.074
Contribution: 7.4%
```

### Edge Types

Edges show relationships between nodes:

| Edge Type | Connection | Meaning |
|-----------|------------|---------|
| **has_release** | Repo → Release | Repository published this release |
| **maintained_by** | Maintainer → Repo | Maintainer contributes to repository |
| **has_cve** | Release → CVE | Release affected by vulnerability |
| **published_as** | Repo → Registry | Repository published to registry |
| **has_risk_factor** | Repo → Risk Factor | Repository exhibits this risk |

**Edge Styling:**
- **Solid lines**: High confidence (≥0.8)
- **Dashed lines**: Low confidence (<0.8)
- **Thicker lines**: More important relationships
- **Red edges**: High-risk connections (CVEs)

---

## Provenance and Confidence

Every piece of data in the graph includes provenance information - where it came from and how reliable it is.

### What is Provenance?

Provenance tells you:
- **Source**: Where the data came from
- **Timestamp**: When it was fetched
- **Confidence**: How reliable it is (0.0-1.0)

### Data Sources

| Source | Description | Typical Confidence |
|--------|-------------|-------------------|
| `github_api` | GitHub REST API | 0.9-1.0 (very reliable) |
| `osv` | OSV.dev vulnerability database | 0.95 (highly reliable) |
| `score_model` | Internal risk scoring | 1.0 (deterministic) |
| `heuristic` | File-based detection | 0.8 (good but uncertain) |

### Confidence Levels

**High Confidence (≥0.9)** 🟢
- Data from authoritative sources
- Solid border, full opacity
- Green confidence badge
- Example: GitHub release data

**Medium Confidence (0.8-0.9)** 🟡
- Reliable but some uncertainty
- Solid border, 90% opacity
- Yellow confidence badge
- Example: Contributor statistics

**Low Confidence (<0.8)** 🔴
- Heuristic or inferred data
- Dashed border, 80% opacity
- Red confidence badge
- Example: Registry detection from files

### Why Provenance Matters

1. **Trust**: Know which data points are certain vs. inferred
2. **Debugging**: Trace where data came from
3. **Auditing**: Establish data lineage for compliance
4. **Filtering**: Focus on high-confidence data only

### Viewing Provenance

1. **Toggle Display:**
   - Check "Show Provenance" in controls
   - Provenance appears in node details panel

2. **Confidence Badges:**
   - Automatically shown on all nodes
   - Color-coded by confidence level

3. **Node Details:**
   - Click any node
   - See full provenance in side panel

---

## Using the Visualization

### Basic Navigation

**Zoom:**
- Mouse wheel: Zoom in/out
- Pinch gesture (trackpad): Zoom
- Navigation buttons: +/- controls

**Pan:**
- Click and drag background
- Arrow keys: Move view
- Two-finger drag (trackpad): Pan

**Select Node:**
- Click any node
- Details appear in side panel
- Node highlights in graph

**Hover:**
- Hover over node for quick info
- Tooltip shows key metadata
- No need to click

### Filtering

#### Node Type Filters

Show or hide specific node types:

- ☑️ **Repository**: Always visible (can't hide)
- ☑️ **Releases**: Toggle release nodes
- ☑️ **Maintainers**: Toggle maintainer nodes
- ☑️ **CVEs**: Toggle vulnerability nodes
- ☑️ **Registries**: Toggle registry nodes
- ☑️ **Risk Factors**: Toggle risk factor nodes

**Use cases:**
- Hide risk factors to focus on supply chain
- Show only CVEs to focus on security
- Hide releases for simpler view

#### Confidence Filter

Set minimum confidence threshold:

- **Slider**: 0.0 (show all) to 1.0 (only certain)
- **Default**: 0.0 (show everything)
- **Recommended**: 0.8 for high-quality data

**Example:**
- Set to 0.9: Only GitHub API data
- Set to 0.8: Exclude heuristic detections
- Set to 0.0: See all data with warnings

#### Search

Find specific nodes:

- **Text input**: Type node label or ID
- **Case-insensitive**: Matches partial text
- **Real-time**: Filters as you type
- **Clear**: Click X to reset

**Examples:**
- Search "v1.2" to find releases
- Search "CVE" to find vulnerabilities
- Search username to find maintainer

### Interactive Features

#### Node Details Panel

Click any node to see:

**Repository:**
- Full URL
- Risk score and label
- Coverage and confidence
- Star count
- Archived status
- Provenance information

**Release:**
- Tag name
- Publication date
- Days since release
- Latest flag
- Prerelease flag
- Provenance

**Maintainer:**
- Username
- Contribution percentage
- Commit count
- Last activity
- Provenance

**CVE:**
- CVE identifier
- Severity and CVSS score
- Description
- Publication date
- Fixed version
- Provenance

**Registry:**
- Registry type
- Package name
- Latest version
- Registry URL
- Provenance

**Risk Factor:**
- Metric name
- Raw value
- Risk score
- Contribution
- Weight
- Category
- Provenance

#### Export Options

**JSON Export:**
- Downloads complete graph data
- Includes all nodes, edges, metadata
- Filename: `{repo}_graph.json`
- Use for: Analysis, archiving, sharing

**PNG Export:**
- Captures current visualization
- High-resolution image
- Filename: `{repo}_graph.png`
- Use for: Reports, presentations, documentation

---

## Configuration Options

### API Parameters

Control graph generation via URL parameters:

```bash
# Basic
/api/graph?repo=numpy/numpy

# Force refresh (bypass cache)
/api/graph?repo=numpy/numpy&refresh=true

# Skip CVEs (faster)
/api/graph?repo=numpy/numpy&include_cves=false

# Limit nodes
/api/graph?repo=numpy/numpy&max_releases=5&max_maintainers=3
```

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `repo` | (required) | Repository name or URL |
| `refresh` | `false` | Force fresh data from APIs |
| `include_cves` | `true` | Include vulnerability nodes |
| `max_releases` | `10` | Maximum release nodes |
| `max_maintainers` | `5` | Maximum maintainer nodes |

### When to Use Each Option

**Use `refresh=true` when:**
- You need the latest data
- Repository just had a new release
- CVE was recently published
- Willing to wait 2-3 seconds

**Use `include_cves=false` when:**
- You don't care about security
- You want faster loading
- CVE API is slow or down
- Focusing on other aspects

**Reduce `max_releases` when:**
- Graph is too cluttered
- Only care about recent releases
- Want faster loading
- Repository has 100+ releases

**Reduce `max_maintainers` when:**
- Graph is too cluttered
- Only care about top contributors
- Want simpler view

---

## Common Use Cases

### 1. Security Assessment

**Goal**: Identify security vulnerabilities

**Steps:**
1. Load graph with `include_cves=true` (default)
2. Filter: Show only CVE nodes
3. Look for red triangles connected to releases
4. Click CVEs to see severity and details
5. Check which releases are affected
6. Verify if latest release is vulnerable

**What to look for:**
- HIGH or CRITICAL severity CVEs
- CVEs affecting latest release
- Multiple CVEs in recent releases
- Unfixed vulnerabilities

### 2. Maintenance Health Check

**Goal**: Assess project maintenance status

**Steps:**
1. Load graph
2. Look at release nodes (green diamonds)
3. Check days since last release
4. Examine maintainer nodes (purple circles)
5. Review risk factor nodes (yellow ellipses)

**What to look for:**
- Recent releases (< 90 days)
- Multiple active maintainers
- Low contribution concentration
- Low risk factor scores

### 3. Supply Chain Verification

**Goal**: Verify distribution channels

**Steps:**
1. Load graph
2. Look for registry nodes (orange hexagons)
3. Verify package names match
4. Check confidence levels
5. Visit registry URLs to confirm

**What to look for:**
- Expected registries present
- Package names correct
- High confidence (≥0.9)
- Latest versions match

### 4. Governance Analysis

**Goal**: Understand project governance

**Steps:**
1. Load graph
2. Focus on maintainer nodes
3. Check contribution percentages
4. Look for concentration risk
5. Verify active contributors

**What to look for:**
- Multiple maintainers (not just 1-2)
- Balanced contributions (no single person >50%)
- Recent activity from maintainers
- Diverse contributor base

### 5. Risk Factor Investigation

**Goal**: Understand what drives risk score

**Steps:**
1. Load graph
2. Show only risk factor nodes
3. Sort by contribution
4. Click high-contribution factors
5. Review raw values

**What to look for:**
- Which factors contribute most
- Whether values are concerning
- Trends over time (if comparing graphs)
- Actionable improvements

---

## Troubleshooting

### Graph Doesn't Load

**Symptoms**: Empty state or error message

**Solutions:**
1. Check API server is running:
   ```bash
   curl http://127.0.0.1:8000/api/health
   ```
2. Open browser console (F12) for errors
3. Verify repository name is correct
4. Try a known-good repo: `numpy/numpy`
5. Check GitHub token is configured

### Empty Graph

**Symptoms**: Graph loads but has no nodes

**Possible causes:**
- Repository has no releases
- Repository is private (no access)
- External APIs failed

**Solutions:**
1. Try a different repository
2. Check API response in browser console
3. Look for warnings in metadata
4. Try with `include_cves=false`

### Slow Loading

**Symptoms**: Graph takes >5 seconds

**Solutions:**
1. Use cached data (don't force refresh)
2. Reduce `max_releases` to 5
3. Reduce `max_maintainers` to 3
4. Disable CVE fetching: `include_cves=false`
5. Check internet connection

### Visualization Looks Wrong

**Symptoms**: Nodes overlap, edges cross badly

**Solutions:**
1. Refresh the page
2. Zoom out to see full graph
3. Use filters to reduce clutter
4. Try different browser

### Low Confidence Data

**Symptoms**: Many red badges, dashed lines

**Meaning**: Data is inferred or uncertain

**What to do:**
1. Use confidence filter (set to 0.8+)
2. Focus on high-confidence nodes
3. Verify uncertain data manually
4. Consider it advisory, not definitive

### Missing CVEs

**Symptoms**: No CVE nodes despite known vulnerabilities

**Possible causes:**
- CVE API timeout
- Package not in OSV.dev database
- Version matching failed

**Solutions:**
1. Check metadata for warnings
2. Try force refresh
3. Verify package ecosystem detected
4. Check OSV.dev manually: https://osv.dev

---

## Best Practices

### 1. Start with Cache

- Use default `refresh=false` for speed
- Only force refresh when needed
- Cache is valid for 1 hour

### 2. Use Filters Strategically

- Start with all nodes visible
- Filter down to focus on specific aspects
- Use confidence filter to remove noise

### 3. Verify Critical Data

- Don't trust low-confidence data blindly
- Cross-check CVEs with official sources
- Verify registry information manually

### 4. Export for Records

- Export JSON for archival
- Export PNG for reports
- Include timestamp in filename

### 5. Compare Over Time

- Export graphs periodically
- Compare node counts
- Track CVE additions/removals
- Monitor risk factor changes

### 6. Understand Limitations

- Graph shows point-in-time snapshot
- Some data is inferred (heuristics)
- External APIs may be incomplete
- Confidence levels indicate uncertainty

---

## Advanced Topics

### Understanding Match Confidence

For CVE and Registry nodes, you'll see two confidence values:

- **data_confidence**: Reliability of the data source
- **match_confidence**: Confidence in matching logic

**Example:**
```json
{
  "provenance": {
    "source": "osv",
    "data_confidence": 0.95,  // OSV.dev is reliable
    "match_confidence": 0.85  // Version matching is uncertain
  }
}
```

**Interpretation:**
- High data_confidence + High match_confidence = Very trustworthy
- High data_confidence + Low match_confidence = Data is good, but matching is uncertain
- Low data_confidence = Treat with caution regardless

### Graph Schema Version

The graph includes a `schema_version` field (currently "1.0").

**Why it matters:**
- Future versions may add new node/edge types
- Schema changes are versioned for compatibility
- Tools can adapt based on version

**Current version**: 1.0
- 6 node types
- 5 edge types
- Provenance metadata required

### Performance Considerations

**Graph Size Limits:**
- Optimal: < 50 nodes
- Good: 50-100 nodes
- Acceptable: 100-200 nodes
- Slow: > 200 nodes

**If graph is too large:**
- Reduce `max_releases`
- Reduce `max_maintainers`
- Use filters to hide node types
- Consider focusing on specific aspects

### API Response Metadata

The API response includes useful metadata:

```json
{
  "metadata": {
    "node_count": 15,
    "edge_count": 18,
    "data_sources": ["github_api", "osv"],
    "cache_hit": true,
    "generation_time_ms": 245,
    "warnings": []
  }
}
```

**Use this to:**
- Check if data was cached
- See which sources were used
- Identify any warnings
- Monitor performance

---

## FAQ

**Q: How often should I refresh the graph?**

A: Cache is valid for 1 hour. Refresh when:
- New release just published
- CVE recently disclosed
- Investigating current state
- Data seems stale

**Q: Why are some nodes dashed?**

A: Dashed borders indicate low confidence (<0.8). The data is inferred or uncertain. Verify manually if critical.

**Q: Can I save my filter settings?**

A: Not currently. Filters reset on page reload. Export the filtered view as PNG if needed.

**Q: Why don't I see any CVE nodes?**

A: Possible reasons:
- No known vulnerabilities (good!)
- CVE API timeout (check warnings)
- Package not in OSV.dev database
- `include_cves=false` parameter

**Q: What does "aggregate" maintainer mean?**

A: An aggregate node represents all other contributors beyond the top N. It shows the collective contribution of minor contributors.

**Q: Can I compare two repositories?**

A: Not in the same view currently. Load each separately and compare side-by-side, or export both as JSON for programmatic comparison.

**Q: Why is the graph layout different each time?**

A: The hierarchical layout is deterministic, but minor variations can occur. The structure and data remain the same.

**Q: How do I report incorrect data?**

A: Check provenance to identify the source, then:
- GitHub data: Verify on GitHub directly
- CVE data: Check OSV.dev or NVD
- Registry data: Verify on registry website
- Report issues with evidence

---

## Related Documentation

- **[API Documentation](API.md)** - Complete API reference
- **[Graph Visualization Guide](GRAPH_VISUALIZATION.md)** - Technical details
- **[Setup Guide](SETUP.md)** - Installation instructions
- **[Design Document](../.kiro/specs/supply-chain-graph/design.md)** - Architecture and design

---

## Support

For issues or questions:

1. Check this user guide
2. Review [troubleshooting section](#troubleshooting)
3. Check browser console for errors
4. Review API logs for backend issues
5. Consult technical documentation

---

## Glossary

- **CVE**: Common Vulnerabilities and Exposures - standardized vulnerability identifiers
- **CVSS**: Common Vulnerability Scoring System - severity scoring (0-10)
- **Provenance**: Origin and history of data
- **Confidence**: Reliability score (0.0-1.0)
- **Node**: Graph element representing an entity
- **Edge**: Graph element representing a relationship
- **Registry**: Package distribution platform (PyPI, npm, etc.)
- **Heuristic**: Rule-based detection logic
- **Bus Factor**: Risk from contributor concentration
- **TTL**: Time To Live - cache expiration time
