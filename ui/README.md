# Supply Chain Graph Visualization

Interactive visualization of repository supply chain relationships using vis.js.

## Files

- `graph.html` - Main visualization page with controls and graph container
- `graph-viz.js` - JavaScript implementation for graph rendering and interaction
- `index.html` - Original risk scoring UI

## Features

### Graph Visualization
- **Interactive Network Graph**: Powered by vis.js with hierarchical layout
- **Node Types**: Repository, Release, Maintainer, CVE, Registry, Risk Factor
- **Color-Coded Nodes**: Each node type has a distinct color and shape
- **Confidence Indicators**: Low-confidence nodes/edges shown with dashed borders

### Interactive Features
- **Node Click**: Click any node to see detailed information in the side panel
- **Node Hover**: Hover over nodes to see quick tooltips
- **Zoom & Pan**: Mouse wheel to zoom, drag to pan
- **Navigation**: Built-in navigation buttons for easy exploration

### Filtering & Search
- **Node Type Filters**: Toggle visibility of different node types
- **Confidence Filter**: Slider to filter by minimum confidence level
- **Search**: Find nodes by label or ID
- **Real-time Updates**: Filters apply instantly to the graph

### Provenance Display
- **Toggle Provenance**: Show/hide data source and confidence information
- **Confidence Badges**: Visual indicators for high/medium/low confidence
- **Source Tracking**: See where each data point came from
- **Timestamps**: View when data was fetched

### Export Options
- **Export JSON**: Download complete graph data
- **Export PNG**: Save visualization as image

## Usage

### Starting the API Server

```bash
# From project root
cd api
uvicorn app:app --reload
```

The API will be available at `http://127.0.0.1:8000`

### Opening the Visualization

1. Open `ui/graph.html` in a web browser
2. Enter a repository name (e.g., `numpy/numpy`)
3. Click "Load Graph" to fetch and visualize the supply chain

### Controls

- **Load Graph**: Fetch graph from cache or build new one
- **Force Refresh**: Bypass cache and rebuild graph from external APIs
- **Node Type Filters**: Check/uncheck to show/hide node types
- **Confidence Slider**: Adjust minimum confidence threshold
- **Search**: Type to filter nodes by label
- **Show Provenance**: Toggle to display data source information

## Node Types

| Type | Color | Shape | Description |
|------|-------|-------|-------------|
| Repository | Blue | Box | The analyzed repository |
| Release | Green | Diamond | Tagged releases/versions |
| Maintainer | Purple | Circle | Key contributors |
| CVE | Red | Triangle | Security vulnerabilities |
| Registry | Orange | Hexagon | Package registries (PyPI, npm, etc.) |
| Risk Factor | Yellow | Ellipse | Significant risk drivers |

## Edge Types

- **has_release**: Repository → Release
- **maintained_by**: Maintainer → Repository
- **has_cve**: Release → CVE
- **published_as**: Repository → Registry
- **has_risk_factor**: Repository → Risk Factor

## Confidence Levels

- **High (≥0.9)**: Solid border, full opacity, green badge
- **Medium (0.8-0.9)**: Solid border, 90% opacity, yellow badge
- **Low (<0.8)**: Dashed border, 80% opacity, red badge

## API Parameters

The visualization uses the `/api/graph` endpoint with these parameters:

- `repo`: Repository in `owner/repo` format (required)
- `refresh`: Force refresh from external APIs (default: false)
- `include_cves`: Include CVE vulnerability nodes (default: true)
- `max_releases`: Maximum number of release nodes (default: 10)
- `max_maintainers`: Maximum number of maintainer nodes (default: 5)

## Browser Compatibility

- Chrome/Edge: Full support
- Firefox: Full support
- Safari: Full support
- Mobile: Limited support (desktop recommended)

## Performance

- **Small graphs (<20 nodes)**: Instant rendering
- **Medium graphs (20-50 nodes)**: <1 second
- **Large graphs (50-100 nodes)**: 1-2 seconds
- **Very large graphs (>100 nodes)**: May be slow, consider reducing max_releases/max_maintainers

## Troubleshooting

### Graph doesn't load
- Check that API server is running at `http://127.0.0.1:8000`
- Check browser console for errors
- Verify repository name is correct

### Empty graph
- Repository may not have enough data (no releases, etc.)
- Try with a well-known repo like `numpy/numpy` or `psf/requests`

### Slow loading
- Reduce `max_releases` and `max_maintainers` parameters
- Disable CVE fetching with `include_cves=false`
- Use cached data (don't click "Force Refresh")

## Development

### Testing

```bash
# Run visualization integration tests
python -m pytest test/test_graph_visualization.py -v
```

### Modifying Styles

Edit the `<style>` section in `graph.html` to customize colors, fonts, and layout.

### Modifying Graph Behavior

Edit `graph-viz.js` to customize:
- Node/edge styling in `NODE_TYPES` configuration
- Layout algorithm in `renderGraph()` options
- Filter logic in `applyFilters()`
- Detail panel content in `showNodeDetails()`

## Future Enhancements

- Multiple layout algorithms (force-directed, circular, etc.)
- Graph comparison (compare two repositories)
- Time-based filtering (show graph at specific point in time)
- Subgraph extraction (focus on specific node and neighbors)
- Advanced export formats (SVG, GraphML)
- Collaborative features (share graph views)
