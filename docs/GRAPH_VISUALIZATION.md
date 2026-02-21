# Supply Chain Graph Visualization

## Overview

The Supply Chain Graph Visualization provides an interactive, visual representation of repository supply chain relationships. It transforms flat risk scores into a contextualized graph showing connections between repositories, releases, maintainers, vulnerabilities, and risk factors.

## Features Implemented

### 1. Interactive Graph Visualization (Task 16.1, 16.2)

**HTML Page** (`ui/graph.html`):
- Modern, responsive design matching existing UI style
- Graph container with vis.js integration
- Control panel with filters and search
- Details panel for node information
- Export buttons for JSON and PNG

**JavaScript Implementation** (`ui/graph-viz.js`):
- Fetches graph data from `/api/graph` endpoint
- Converts graph data to vis.js format
- Applies node styling by type (colors, shapes, icons)
- Applies edge styling (colors, widths, dashed for low confidence)
- Implements hierarchical layout algorithm
- Handles empty states and errors gracefully

**Node Types**:
| Type | Color | Shape | Icon | Description |
|------|-------|-------|------|-------------|
| Repository | Blue (#2563eb) | Box | 📦 | The analyzed repository |
| Release | Green (#16a34a) | Diamond | 🏷️ | Tagged releases/versions |
| Maintainer | Purple (#9333ea) | Circle | 👤 | Key contributors |
| CVE | Red (#dc2626) | Triangle | ⚠️ | Security vulnerabilities |
| Registry | Orange (#ea580c) | Hexagon | 📚 | Package registries |
| Risk Factor | Yellow (#ca8a04) | Ellipse | ⚡ | Significant risk drivers |

### 2. Interactive Features (Task 16.3)

**Node Interaction**:
- **Click**: Shows detailed information in side panel
- **Hover**: Displays tooltip with key metadata
- **Selection**: Highlights selected node

**Navigation**:
- **Zoom**: Mouse wheel to zoom in/out
- **Pan**: Drag to move around the graph
- **Navigation Buttons**: Built-in controls for easy navigation
- **Keyboard**: Arrow keys for navigation

**Filtering**:
- **Node Type Filters**: Checkboxes to show/hide each node type
- **Confidence Filter**: Slider to set minimum confidence threshold (0.0-1.0)
- **Search**: Text input to find nodes by label or ID
- **Real-time Updates**: Filters apply instantly without reloading

### 3. Provenance Display (Task 16.4)

**Provenance Metadata**:
- **Source**: Shows where data came from (github_api, osv, heuristic, etc.)
- **Timestamp**: When data was fetched
- **Confidence**: Numeric confidence score (0.0-1.0)
- **Match Confidence**: For CVE and Registry nodes

**Visual Indicators**:
- **High Confidence (≥0.9)**: Solid border, full opacity, green badge
- **Medium Confidence (0.8-0.9)**: Solid border, 90% opacity, yellow badge
- **Low Confidence (<0.8)**: Dashed border, 80% opacity, red badge

**Toggle Control**:
- Checkbox to show/hide provenance information
- Keeps UI clean when provenance not needed
- Preserves selection when toggling

### 4. Export Functionality

**JSON Export**:
- Downloads complete graph data as JSON file
- Includes all nodes, edges, metadata, and provenance
- Filename: `{repo}_graph.json`

**PNG Export**:
- Captures current visualization as PNG image
- Uses canvas rendering from vis.js
- Filename: `{repo}_graph.png`

### 5. Integration Tests (Task 16.5)

**Test Coverage** (`test/test_graph_visualization.py`):
- ✅ Visualization files exist and are properly structured
- ✅ HTML includes vis.js and required elements
- ✅ JavaScript has required functions and configuration
- ✅ API returns data compatible with visualization
- ✅ Node types match visualization configuration
- ✅ Provenance fields present in all nodes
- ✅ Empty graph structure handled correctly
- ✅ Small and medium graphs load successfully
- ✅ Various node types included in graphs
- ✅ Metadata present for visualization

**Test Results**: 14/14 tests passing

## Usage

### Quick Start

1. **Start the API server**:
   ```bash
   cd api
   uvicorn app:app --reload
   ```

2. **Open the visualization**:
   - Open `ui/graph.html` in your browser
   - Or run: `python demo_graph_visualization.py`

3. **Load a graph**:
   - Enter a repository (e.g., `numpy/numpy`)
   - Click "Load Graph"

### Example Repositories

Good repositories to try:
- `numpy/numpy` - Large scientific computing library
- `psf/requests` - Popular HTTP library
- `pallets/flask` - Web framework
- `django/django` - Full-stack web framework

### Controls

**Load Graph**: Fetch graph from cache or build new one
- Uses cached data if available (1 hour TTL)
- Fast response for repeated requests

**Force Refresh**: Bypass cache and rebuild from external APIs
- Fetches fresh data from GitHub, OSV.dev, etc.
- Slower but ensures latest data

**Node Type Filters**: Show/hide specific node types
- Useful for focusing on specific aspects
- Example: Hide risk factors to see just supply chain

**Confidence Slider**: Filter by minimum confidence
- Set to 0.8 to see only high-confidence data
- Set to 0.0 to see all data

**Search**: Find specific nodes
- Search by label or ID
- Case-insensitive
- Real-time filtering

**Show Provenance**: Toggle data source information
- Shows where each data point came from
- Displays confidence levels
- Useful for auditing and trust

## API Integration

The visualization uses the `/api/graph` endpoint:

**Endpoint**: `GET /api/graph`

**Parameters**:
- `repo` (required): Repository in `owner/repo` format
- `refresh` (optional): Force refresh from external APIs (default: false)
- `include_cves` (optional): Include CVE nodes (default: true)
- `max_releases` (optional): Maximum release nodes (default: 10)
- `max_maintainers` (optional): Maximum maintainer nodes (default: 5)

**Response Format**:
```json
{
  "repo": "numpy/numpy",
  "schema_version": "1.0",
  "generated_at": "2026-02-18T10:30:00Z",
  "graph": {
    "nodes": [...],
    "edges": [...]
  },
  "metadata": {
    "node_count": 15,
    "edge_count": 18,
    "data_sources": ["github_api", "osv"],
    "cache_hit": true,
    "generation_time_ms": 245
  }
}
```

## Architecture

### Data Flow

```
User Input (repo name)
    ↓
JavaScript (graph-viz.js)
    ↓
API Request (/api/graph)
    ↓
Graph Builder (Python)
    ↓
External APIs (GitHub, OSV.dev)
    ↓
Graph Data (JSON)
    ↓
vis.js Rendering
    ↓
Interactive Visualization
```

### Component Structure

```
ui/
├── graph.html          # Main visualization page
├── graph-viz.js        # JavaScript implementation
├── index.html          # Original risk scoring UI
└── README.md           # Usage documentation

test/
└── test_graph_visualization.py  # Integration tests

docs/
└── GRAPH_VISUALIZATION.md       # This file
```

## Performance

**Rendering Performance**:
- Small graphs (<20 nodes): Instant
- Medium graphs (20-50 nodes): <1 second
- Large graphs (50-100 nodes): 1-2 seconds

**API Performance**:
- Cached: <100ms
- Fresh build: 1-3 seconds (depends on external APIs)

**Optimization Tips**:
- Use cached data when possible
- Reduce `max_releases` and `max_maintainers` for faster loading
- Disable CVE fetching if not needed (`include_cves=false`)

## Browser Compatibility

**Fully Supported**:
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

**Limited Support**:
- Mobile browsers (desktop recommended)
- Older browsers (may need polyfills)

## Troubleshooting

### Graph doesn't load
**Symptoms**: Empty state or error message

**Solutions**:
1. Check API server is running: `curl http://127.0.0.1:8000/api/health`
2. Check browser console for errors (F12)
3. Verify repository name is correct
4. Try a known-good repo like `numpy/numpy`

### Empty graph
**Symptoms**: Graph loads but has no nodes

**Causes**:
- Repository has no releases
- Repository has no public data
- External APIs failed

**Solutions**:
1. Try a different repository
2. Check API response in browser console
3. Look for warnings in metadata

### Slow loading
**Symptoms**: Graph takes >5 seconds to load

**Solutions**:
1. Use cached data (don't force refresh)
2. Reduce `max_releases` to 5
3. Reduce `max_maintainers` to 3
4. Disable CVE fetching

### Visualization looks wrong
**Symptoms**: Nodes overlap, edges cross badly

**Solutions**:
1. Refresh the page
2. Try different layout (future feature)
3. Reduce number of nodes with filters

## Future Enhancements

Potential improvements for future versions:

1. **Multiple Layout Algorithms**
   - Force-directed layout
   - Circular layout
   - Tree layout

2. **Advanced Filtering**
   - Filter by edge type
   - Filter by metadata values
   - Save filter presets

3. **Graph Comparison**
   - Compare two repositories side-by-side
   - Highlight differences

4. **Time-based Views**
   - Show graph at specific point in time
   - Animate changes over time

5. **Subgraph Extraction**
   - Focus on specific node and neighbors
   - Export subgraphs

6. **Collaborative Features**
   - Share graph views via URL
   - Annotate nodes/edges
   - Export to presentation formats

7. **Performance Improvements**
   - Virtual rendering for large graphs
   - Progressive loading
   - WebGL rendering

## Related Documentation

- [API Documentation](API.md) - Complete API reference
- [Design Document](../.kiro/specs/supply-chain-graph/design.md) - Detailed design
- [Requirements](../.kiro/specs/supply-chain-graph/requirements.md) - User stories
- [Tasks](../.kiro/specs/supply-chain-graph/tasks.md) - Implementation plan

## Support

For issues or questions:
1. Check this documentation
2. Review test cases in `test/test_graph_visualization.py`
3. Check browser console for errors
4. Review API logs for backend issues
