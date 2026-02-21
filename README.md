# Open Source Risk Model

A modular risk-scoring engine for evaluating open-source software repositories using GitHub metadata, with interactive supply chain graph visualization.

This project ingests repository-level signals (activity, contributors, issues, licensing, etc.), maps them to normalized risk scores using configurable strategies, and aggregates them into a composite risk score suitable for comparison and analysis. The supply chain graph feature transforms flat risk scores into a visual, contextualized graph representation showing relationships between repositories, releases, vulnerabilities, maintainers, and risk factors.

## Why This Matters

**The Problem:** Modern software depends on hundreds of open-source packages. A single unmaintained dependency with a critical vulnerability can compromise your entire application. Traditional tools give you a binary "vulnerable/not vulnerable" answer, but don't help you understand the broader supply chain risk.

**The Solution:** This project provides:
- **Contextual Risk Assessment**: Not just "is it vulnerable?" but "how risky is this dependency overall?"
- **Supply Chain Visibility**: See the full picture - releases, maintainers, vulnerabilities, and distribution channels
- **Provenance & Trust**: Every data point includes its source and confidence level
- **Actionable Insights**: Understand which factors drive risk and make informed decisions

**Real-World Impact:**
- Identify unmaintained dependencies before they become security liabilities
- Understand maintainer concentration risk (bus factor)
- Track vulnerability exposure across your dependency tree
- Make data-driven decisions about dependency adoption

## Screenshots

### Interactive Supply Chain Graph
![Supply Chain Graph Visualization](docs/images/graph-visualization.png)
*Interactive graph showing repository relationships, releases, maintainers, CVEs, and risk factors*

### Node Details with Provenance
![Node Details Panel](docs/images/node-details.png)
*Detailed metadata and provenance information for each node, including confidence scores*

### Risk Score Dashboard
![Risk Score API Response](docs/images/risk-score.png)
*Comprehensive risk assessment with feature breakdown and confidence metrics*

> **Note:** Screenshots show example data. Your results will vary based on the repository analyzed.

---

## Project Goals

- Provide a transparent, explainable framework for open-source risk assessment
- Support multiple feature-to-risk mapping strategies
- Enable reproducible scoring via baseline population distributions
- Visualize supply chain relationships through interactive graph representations
- Integrate vulnerability data (CVEs) and package registry information
- Serve as a foundation for experimentation, calibration, and evaluation

---

## High-Level Architecture

```
GitHub API -> Feature Ingestion -> Feature-to-Risk Mapping (Option A/B/C) -> Composite Scoring -> Evaluation & Analysis
                                                                                      |
                                                                                      v
                                                                            Supply Chain Graph
                                                                                      |
                                                    +-----------------------------+---+----------------------------+
                                                    |                             |                                |
                                                    v                             v                                v
                                            CVE Data (OSV.dev)          Package Registries              Interactive Visualization
```


---

## Features

### Risk Scoring
- Transparent, explainable risk assessment framework
- Multiple feature-to-risk mapping strategies (anchor-based, percentile-based)
- Configurable weights for composite scoring
- Reproducible scoring via baseline population distributions

### Supply Chain Graph Visualization
- **Interactive Graph Explorer**: Visual representation of repository supply chain relationships
- **Multi-Source Data Integration**: 
  - GitHub API for releases and contributors
  - OSV.dev for CVE/vulnerability data
  - Automatic package registry detection (PyPI, npm, Maven, etc.)
- **Provenance Tracking**: Every node and edge includes source, timestamp, and confidence metadata
- **Graceful Degradation**: Partial graphs returned when external APIs fail
- **Performance Optimized**: Aggressive caching with configurable TTLs
- **Interactive Features**:
  - Click nodes to see detailed metadata
  - Filter by node type and confidence threshold
  - Search nodes by label
  - Export graphs as JSON or PNG
  - Zoom, pan, and explore relationships

### API Endpoints
- `GET /api/score` - Get risk score for a repository
- `GET /api/graph` - Get supply chain graph data (JSON)
- `GET /graph` - Interactive graph visualization (HTML)
- `GET /health` - Service health check with metrics

---

## Core Concepts

### Feature Ingestion
Repository metadata is collected using the GitHub API, including:
- activity recency
- contributor counts
- issue statistics
- licensing information
- popularity signals

### Feature-to-Risk Mapping
Each raw feature is converted into a normalized risk score in `[0, 1]` using configurable mapping strategies:

- **Option A**: anchor-based monotonic mappings
- **Option B**: population-aware percentile mappings
- **Option C**: alternative / experimental mapping approach

> Option A and Option B are currently used in the default scoring pipeline.  
> Option C is fully implemented and tested but not active by default.

### Composite Scoring
Individual feature risks are combined into a weighted composite score using configuration-driven weights.

### Supply Chain Graph
The graph representation extends the flat scoring model by visualizing relationships between:
- **Repositories** and their **releases**
- **Maintainers** and their contributions
- **CVEs** (vulnerabilities) affecting specific releases
- **Package registries** (PyPI, npm, Maven) where packages are published
- **Risk factors** driving the overall risk score

Each node and edge includes provenance metadata (source, timestamp, confidence) to establish trust and traceability.

---

## Repository Structure

- `src/open_source_risk_model/`  
  Core library code (ingestion, mappings, scoring, utilities)

- `data/baseline/`  
  Baseline population distributions used for calibration and normalization

- `test/`  
  Unit tests and validation scripts for features, mappings, and scoring logic

- `spikes/`  
  Exploratory and evaluation scripts (non-library entry points)

- `docs/`  
  Project documentation, including a detailed file-by-file guide

---

## Documentation

A detailed description of every module, script, and configuration file is available here:

**`docs/File_Guide.docx`**

---

## Design Notes

- Baseline population files are intentionally committed to ensure reproducibility
- Alternative mapping strategies are retained to support future experimentation
- Emphasis is placed on transparency and explainability over black-box modeling

---

## Getting Started

### Prerequisites

- Python 3.9 or higher
- GitHub personal access token ([create one here](https://github.com/settings/tokens))
- Modern web browser (Chrome, Firefox, or Safari) for graph visualization

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/open-source-risk-model.git
cd open-source-risk-model
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package with all dependencies:
```bash
pip install -e ".[dev]"
```

This installs all required dependencies including:
- `fastapi` and `uvicorn` for the API server
- `httpx` for external API calls (OSV.dev for CVE data)
- `pytest` and `hypothesis` for testing
- Graph-related dependencies for data fetching and caching

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your GitHub token
```

Required environment variables:
- `GITHUB_TOKEN`: Your GitHub personal access token (required)
- `LOG_LEVEL`: Logging level (optional, defaults to INFO)

### Quick Start

**Score a repository using the API:**

1. Start the API server:
```bash
uvicorn api.app:app --reload
```

2. Score a repository:
```bash
curl "http://localhost:8000/api/score?repo=numpy/numpy"
```

3. Get the supply chain graph:
```bash
curl "http://localhost:8000/api/graph?repo=numpy/numpy"
```

4. View the interactive graph visualization:
   - Open your browser to **`http://localhost:8000/ui/graph.html`**
   - Enter a repository (e.g., `numpy/numpy`) and click "Load Graph"
   - Explore nodes by clicking, hovering, and using filters
   - Click the "💡 What This Graph Means" panel for guidance
   - See the [Supply Chain User Guide](docs/SUPPLY_CHAIN_USER_GUIDE.md) for detailed features

**Score a repository programmatically:**

```python
from open_source_risk_model.service.score_repo import score_repo

result = score_repo("numpy/numpy")
print(f"Maintenance Risk: {result['maintenance_risk']:.3f}")
print(f"Risk Label: {result['maintenance_label']}")
```

### Running Tests

```bash
pytest
```

---

## Supply Chain Graph Visualization

The supply chain graph feature provides an interactive visualization of repository risk relationships:

![Supply Chain Graph Example](docs/images/graph-example.png)
*Example: numpy/numpy supply chain graph showing releases, maintainers, and CVEs*

### Key Capabilities

**Node Types:**
- 📦 **Repository** (blue) - The analyzed repository
- 🏷️ **Release** (green) - Tagged releases/versions
- 👤 **Maintainer** (purple) - Key contributors
- ⚠️ **CVE** (red) - Known vulnerabilities
- 📚 **Registry** (orange) - Package registries (PyPI, npm, etc.)
- ⚡ **Risk Factor** (yellow) - Significant risk drivers

**Interactive Features:**
- Click nodes to view detailed metadata and provenance
- Hover for quick tooltips
- Filter by node type or confidence threshold
- Search for specific nodes
- Export as JSON or PNG

**Confidence Indicators:**
- Solid borders: High confidence (≥ 0.9)
- Dashed borders: Low confidence (< 0.8)
- Edge opacity reflects confidence level
- Provenance metadata shows data source and timestamp

### Example Usage

```bash
# Get graph data as JSON
curl "http://localhost:8000/api/graph?repo=numpy/numpy"

# With custom parameters
curl "http://localhost:8000/api/graph?repo=numpy/numpy&max_releases=5&include_cves=true"

# View interactive visualization
open "http://localhost:8000/graph?repo=numpy/numpy"
```

See the [Supply Chain User Guide](docs/SUPPLY_CHAIN_USER_GUIDE.md) for detailed documentation.

---

## Documentation

### Core Documentation
- **[API Documentation](docs/API.md)** - REST API endpoints and usage
- **[Data Guide](docs/DATA_GUIDE.md)** - Data directory structure and management
- **[File Guide](docs/File_Guide.docx)** - Detailed module descriptions
- **[Features](docs/features.md)** - Feature definitions and calculations
- **[Design Philosophy](docs/model_design_philosophy.md)** - Scoring approach and principles

### Supply Chain Graph Documentation
- **[Supply Chain User Guide](docs/SUPPLY_CHAIN_USER_GUIDE.md)** - Interactive graph visualization features
- **[Graph Visualization Guide](docs/GRAPH_VISUALIZATION.md)** - Technical details on graph rendering
- **[Logging and Monitoring](docs/LOGGING_AND_MONITORING.md)** - Performance metrics and observability

### Development
- **[Contributing](CONTRIBUTING.md)** - Development setup and guidelines

---

## Status

This project is under active development.  
APIs, configurations, and scoring logic may evolve as calibration and evaluation continue.

---

## License

MIT License
