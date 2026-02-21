# Graph Visualization Screenshots

This directory contains screenshots and images for the supply chain graph visualization feature.

## Required Images

### graph-example.png
A screenshot showing the supply chain graph for a well-known repository (e.g., numpy/numpy) with:
- Repository node at the center
- Multiple release nodes
- Maintainer nodes
- CVE nodes (if applicable)
- Registry nodes
- Risk factor nodes
- Clear node labels and colors

**Recommended size:** 1200x800 pixels
**Format:** PNG with transparency

### How to Generate Screenshots

1. Start the API server:
   ```bash
   uvicorn api.app:app --reload
   ```

2. Open the graph visualization in your browser:
   ```
   http://localhost:8000/graph?repo=numpy/numpy
   ```

3. Use the built-in export feature or take a screenshot showing:
   - The full graph layout
   - Node type legend
   - Interactive controls
   - Details panel (optional)

4. Save the screenshot as `graph-example.png` in this directory

## Additional Screenshots (Optional)

- `graph-filters.png` - Screenshot showing filter controls in action
- `graph-node-details.png` - Screenshot showing node details panel
- `graph-confidence.png` - Screenshot highlighting confidence indicators
- `graph-cve-example.png` - Screenshot focusing on CVE nodes and relationships

## Notes

- Screenshots should be clear and readable
- Use a repository with interesting graph structure (multiple releases, CVEs, etc.)
- Ensure all node types are visible if possible
- Consider using light mode for better visibility in documentation
