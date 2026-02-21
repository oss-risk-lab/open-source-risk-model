# Supply Chain Risk Graph - Requirements

## Overview

Transform the flat risk scoring model into a graph-based supply chain risk intelligence engine. This enables visualization and analysis of relationships between repositories, releases, vulnerabilities, maintainers, and deployment contexts.

## Problem Statement

**Current State:**
- Repo → metrics → composite score (flat aggregation)
- No visibility into relationships between entities
- Limited context about supply chain dependencies

**Desired State:**
- Repo → ecosystem graph → multi-source evidence → contextualized risk
- Visual representation of risk propagation
- Enterprise-grade supply chain thinking

## User Stories

### US-1: Graph Data Model
**As a** developer  
**I want** a graph representation of repository risk  
**So that** I can understand relationships between entities in the supply chain

**Acceptance Criteria:**
- Graph contains nodes for: Repo, Release, Maintainer, CVE, Registry, RiskFactor
- Graph contains edges representing relationships between nodes
- Each node has: id, type, label, metadata
- Each edge has: source, target, relationship_type
- Graph structure is validated (no orphaned edges, unique IDs)

### US-2: Graph API Endpoint
**As a** API consumer  
**I want** to retrieve graph data for a repository  
**So that** I can visualize supply chain relationships

**Acceptance Criteria:**
- New endpoint: `GET /api/graph?repo={owner/name}`
- Response includes: repo metadata, schema_version, graph.nodes, graph.edges
- Response time < 2 seconds for cached data
- Empty graph returns valid structure (empty arrays, not null)
- Errors return appropriate HTTP status codes

### US-3: CVE Integration
**As a** security analyst  
**I want** to see known vulnerabilities linked to releases  
**So that** I can assess security risk

**Acceptance Criteria:**
- CVE nodes created for known vulnerabilities
- CVE data sourced from public databases (OSV, GitHub Advisory)
- CVE nodes include: severity, description, affected versions
- Edges connect CVE → Release
- Missing CVE data doesn't break graph generation

### US-4: Package Registry Integration
**As a** developer  
**I want** to see package registry information  
**So that** I can understand distribution channels

**Acceptance Criteria:**
- Registry nodes for PyPI, npm, Maven (when applicable)
- Registry detection based on repo metadata (setup.py, package.json, pom.xml)
- Edges connect Repo → Registry
- Registry node includes: package name, latest version, download stats

### US-5: Maintainer Nodes
**As a** risk analyst  
**I want** to see maintainer relationships  
**So that** I can assess bus factor and governance

**Acceptance Criteria:**
- Maintainer nodes for top contributors
- Edges connect Maintainer → Repo
- Maintainer metadata includes: contribution %, commit count, last activity
- Top 5 maintainers included (configurable)

### US-6: Graph Visualization
**As a** user  
**I want** to see an interactive graph visualization  
**So that** I can explore supply chain relationships

**Acceptance Criteria:**
- Interactive node-edge visualization in UI
- Nodes are clickable and show details
- Graph layout is readable (force-directed or hierarchical)
- Color coding by node type
- Zoom and pan controls
- Works on desktop browsers (Chrome, Firefox, Safari)

### US-7: Risk Factor Nodes
**As a** analyst  
**I want** to see risk factors as graph nodes  
**So that** I can understand what drives the risk score

**Acceptance Criteria:**
- RiskFactor nodes for high-impact metrics
- Edges connect RiskFactor → Repo
- RiskFactor metadata includes: metric name, value, risk score, weight
- Only factors with contribution > 0.05 included

## Non-Functional Requirements

### Performance
- Graph generation: < 500ms for cached data
- API response: < 2s total (including network)
- Graph rendering: < 1s for graphs with < 100 nodes

### Scalability
- Support graphs up to 200 nodes
- Handle repos with 100+ releases
- Graceful degradation for large repos (sample/limit nodes)

### Reliability
- Graph generation never crashes the API
- Missing data results in partial graph (not failure)
- Invalid data logged but doesn't break response

### Maintainability
- Graph schema versioned (start at 1.0)
- Node/edge types extensible
- Clear separation: graph builder, data sources, API layer

## Out of Scope (Future Versions)

- Full dependency tree resolution
- Cross-repository graph linking
- Real-time deployment monitoring
- External scanning API integrations (Snyk, Dependabot)
- Graph persistence/database
- Historical graph snapshots
- Graph query language

## Technical Constraints

- Must work with existing Python 3.8+ codebase
- Must not break existing `/api/score` endpoint
- Must use existing GitHub token authentication
- Frontend must work without additional build tools
- No new database dependencies (use in-memory + JSON cache)

## Success Metrics

- Graph endpoint returns valid data for 95% of public repos
- Graph visualization loads in < 2s
- Zero crashes in graph generation for 1000 test repos
- User can identify CVEs within 10 seconds of loading graph

## Dependencies

- Existing: GitHub API, repo scoring logic, FastAPI
- New: CVE database API (OSV.dev or GitHub Advisory)
- New: Package registry APIs (PyPI, npm - optional)
- New: Graph visualization library (D3.js, vis.js, or cytoscape.js)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CVE API rate limits | High | Cache CVE data, implement backoff |
| Large graphs crash browser | Medium | Limit nodes, implement pagination |
| Complex graph logic delays project | High | Start with minimal viable graph |
| External APIs unreliable | Medium | Graceful fallbacks, partial graphs |

## Open Questions

1. Which CVE database to use? (OSV.dev recommended - free, comprehensive)
2. How many releases to include? (Suggest: latest 10)
3. Should we cache graphs separately from scores? (Suggest: yes, with TTL)
4. Which graph visualization library? (Suggest: vis.js - simple, no build step)
5. How to handle repos with no releases? (Show repo + maintainers only)

## Next Steps

1. Review and approve requirements
2. Create design document with:
   - Graph schema definition
   - API contract
   - Data source integration plan
   - Visualization approach
3. Break into implementation tasks
4. Implement incrementally with testing
