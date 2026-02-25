# 🧭 PROJECT NORTH STAR — Open Source Risk Model

## 1. Product Vision

This project is evolving into:

**An AI-native supply chain intelligence system** that allows users to ask complex risk questions about open source ecosystems and receive structured, explainable answers derived from a normalized database — not ad hoc API calls.

The system must support:
- Risk graph visualization
- Dependency resolution tracking
- CVE + GHSA correlation
- Cross-repo supply chain queries
- Natural-language AI queries over structured data
- Tree-based and graph-based dependency exploration
- Eventually, statistically grounded risk scoring

**This is not just a graph visualizer. This is not just a CVE fetcher. This is not just a dependency parser.**

**It is becoming a supply chain intelligence engine.**

---

## 2. Core Architectural Principles (Non-Negotiable)

### Database is the source of truth
- No GET endpoints perform network calls
- Ingestion is separate from query
- All queries must execute against stored data

### Ingestion is ETL, not request-time logic
- Dependency resolution, GitHub fetches, CVE queries happen in ingestion
- API reads are fast and deterministic

### LLM never generates raw SQL
- LLM outputs structured intents
- Backend validates intents
- Backend executes parameterized queries

### Single source of ingestion logic
- `DependencyIngestionService` is canonical
- CLI, Batch API, and Worker call the same service

### Schema is authoritative
- `init_database()` must fully define schema
- Migrations must be encoded, not manual
- No duplicate logic across scripts, API, and services

---

## 3. UI Direction

The UI will evolve into:

### Phase A: Chat-based query interface
- User selects repo context
- User asks natural-language question
- Backend converts to safe structured intent
- Results render as:
  - Table
  - Tree
  - Graph
  - Text explanation

### Phase B: Tree-style dependency explorer
- Merge `graph.html` + `dependency-explorer.html` into a unified UI
- Tree derived from database relationships, not static graph JSON

### Phase C: Cross-repo supply chain queries
- Risk propagation visualization

**The UI should move away from checkbox-driven graph configuration. The user should not be "configuring nodes." They should be asking questions.**

---

## 4. Risk Scoring Direction

The current scoring model is provisional.

### Future direction:
- Replace arbitrary weights with statistically grounded modeling
- Evaluate distributions for features (stars, activity decay, release cadence)
- Consider probabilistic or regression-based models
- Keep scoring isolated from ingestion and query layers
- Research code must not live in production modules

---

## 5. Immediate Roadmap Focus

### Near-term focus:
- ✅ Harden ingestion + persistence
- ✅ Build safe query layer (intent-based)
- 🔄 Replace checkbox UI with AI query UI
- 🔄 Implement tree-based dependency rendering
- 🔄 Populate multiple repos for demo credibility

### Do not:
- ❌ Rebuild entire graph engine
- ❌ Implement deep recursive transitive resolution beyond depth=2 for now
- ❌ Introduce heavy ML before query layer is stable

---

## 6. Development Philosophy

When implementing features:

### Favor:
- ✅ Clarity over cleverness
- ✅ Explicit over magical
- ✅ Composable modules
- ✅ Deterministic behavior

### Always:
- Add tests for schema-level invariants
- Keep services thin and composable
- Avoid mixing research code with production code

---

## 7. Engineering Discipline & Git Practices

### Commit Discipline (Non-Negotiable)

**All work must be committed frequently in atomic, coherent commits.**

Each commit should:
- Represent one logical change
- Be self-contained and reversible
- Have a clear, descriptive message

### Conventional Commit Style (Required)

Use conventional commit format:
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `test`: Add or update tests
- `refactor`: Code refactoring
- `docs`: Documentation changes
- `chore`: Maintenance tasks
- `perf`: Performance improvements

**Examples**:
```
feat(query): add intent executor with allowlist validation
fix(schema): add resolution columns migration
test(api): add query endpoint integration tests
refactor(deps): extract tree builder to separate module
docs(north-star): add engineering discipline section
chore(gitignore): exclude database and cache files
```

### What NOT to Commit (Enforced by .gitignore)

**Never commit**:
- ❌ `.venv/` - Virtual environments
- ❌ `data/graphs.db` - Database files
- ❌ `__pycache__/`, `.pytest_cache/` - Cache directories
- ❌ `.env` - Environment files with secrets
- ❌ `*.pyc`, `*.pyo` - Compiled Python files
- ❌ `.DS_Store` - OS-specific files
- ❌ `node_modules/` - Dependencies

**Do commit**:
- ✅ `.env.example` - Template without secrets
- ✅ Source code
- ✅ Tests
- ✅ Documentation
- ✅ Configuration templates
- ✅ Migration scripts

### Testing Requirements (Non-Negotiable)

**Every new feature must include tests.**

- Unit tests for core logic
- Integration tests for API endpoints
- Property-based tests for data validation
- End-to-end tests for critical flows

**The main branch must remain stable and passing tests.**

Before merging:
1. All tests must pass
2. Code must be reviewed
3. Commit history must be clean

### Repository as Product Narrative

**This repository is part of the product narrative.**

Commit history should reflect:
- Architectural clarity
- Evolutionary design decisions
- Problem-solving approach
- Quality standards

**Good commit history**:
```
feat(intelligence): add intent parser with LLM integration
test(intelligence): add intent parser validation tests
feat(intelligence): add intent executor with parameterized queries
test(intelligence): add intent executor integration tests
docs(intelligence): document intent-based query architecture
```

**Bad commit history**:
```
wip
fix stuff
more changes
final version
actually final
```

---

## 8. Future Deployment Direction (AWS)

### Deployment Assumption

**This system will eventually be deployed to AWS.**

All design decisions must assume:

### Stateless API Servers
- No local file storage for persistent data
- Session state in external store (Redis/DynamoDB)
- Horizontal scaling capability
- Load balancer compatible

### Configuration via Environment Variables
- All config from environment (12-factor app)
- No hardcoded paths or credentials
- Support for AWS Parameter Store / Secrets Manager
- Environment-specific configuration

### No Hardcoded Local Paths
- Use environment variables for paths
- Default to standard locations
- Support for S3 or EFS for file storage
- Relative paths where possible

### Clear Separation: API vs. Worker
- API servers handle HTTP requests only
- Background workers handle ingestion
- Communication via queue (SQS)
- Independent scaling

### Database Abstraction
- Current: SQLite (development)
- Future: PostgreSQL (production)
- Use connection strings from environment
- Abstract database operations in repositories
- Support for RDS connection pooling

### AWS-Ready Checklist

When writing new code, ensure:

- [ ] Configuration from environment variables
- [ ] No hardcoded file paths
- [ ] Database connection via connection string
- [ ] Stateless request handling
- [ ] Logging to stdout/stderr (CloudWatch compatible)
- [ ] Health check endpoint for load balancer
- [ ] Graceful shutdown handling
- [ ] Error handling with proper HTTP status codes

### What This Means in Practice

**Good** (AWS-ready):
```python
# Configuration from environment
db_path = os.getenv('DATABASE_URL', 'data/graphs.db')
conn = get_connection(db_path)

# Logging to stdout
logger.info("Processing request", extra={"repo": repo_name})

# Stateless handler
@app.get("/api/repos/{repo}/dependencies")
async def get_dependencies(repo: str):
    # No session state, no local files
    return dep_repo.get_dependencies(repo)
```

**Bad** (blocks AWS deployment):
```python
# Hardcoded path
conn = sqlite3.connect('/Users/colin/data/graphs.db')

# Local file storage
with open('cache/results.json', 'w') as f:
    json.dump(data, f)

# Session state in memory
session_cache = {}  # Lost on restart
```

### Not Deploying Yet, But...

**We are not deploying to AWS yet**, but:
- New code must not block future deployment
- Refactoring for AWS should be minimal
- Architecture should support cloud deployment
- Local development should remain simple

### Future AWS Architecture (Reference)

```
┌─────────────────────────────────────────────┐
│ Route 53 (DNS)                              │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│ CloudFront (CDN) + WAF                      │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│ Application Load Balancer                   │
└─────────┬───────────────────┬───────────────┘
          │                   │
┌─────────▼─────────┐ ┌──────▼──────────────┐
│ ECS/Fargate       │ │ ECS/Fargate         │
│ API Servers       │ │ Background Workers  │
│ (Stateless)       │ │ (Ingestion)         │
└─────────┬─────────┘ └──────┬──────────────┘
          │                   │
          │         ┌─────────▼─────────────┐
          │         │ SQS (Job Queue)       │
          │         └───────────────────────┘
          │
┌─────────▼─────────────────────────────────┐
│ RDS PostgreSQL (Multi-AZ)                 │
└───────────────────────────────────────────┘

┌───────────────────────────────────────────┐
│ S3 (Static assets, cache files)          │
└───────────────────────────────────────────┘

┌───────────────────────────────────────────┐
│ ElastiCache Redis (Session, rate limits) │
└───────────────────────────────────────────┘

┌───────────────────────────────────────────┐
│ CloudWatch (Logs, Metrics, Alarms)       │
└───────────────────────────────────────────┘
```

**Keep this architecture in mind when making design decisions.**

---

## 9. What This System Is Becoming

Long-term, this is moving toward:

- **A risk intelligence layer** for open source ecosystems
- **A structured supply chain database**
- **An AI-queryable graph knowledge system**
- **A foundation for risk propagation modeling**
- **A platform for institutional-grade OSS risk evaluation**

**All design decisions should be evaluated against that trajectory.**

---

## Current Status (As of Latest Session)

### ✅ Completed:
1. **Dependency Resolution Storage** - 92% resolution rate, stores resolved GitHub repos
2. **CVE/GHSA Dual Identifiers** - Tracks both CVE-2025-xxx and GHSA-xxx identifiers
3. **Schema Drift Prevention** - Portable schema with automatic migrations
4. **Multi-Manifest Support** - Handles multiple dependency files per repo
5. **Repository Pattern** - Clean separation between services and persistence
6. **Comprehensive Testing** - 76+ tests including property-based tests

### 🔄 In Progress:
1. **Data Population** - Only 1 repo fully populated (pallets/flask)
2. **UI Modernization** - Still using checkbox-driven configuration
3. **AI Query Layer** - Not yet implemented

### 📋 Next Priorities:
1. Populate 10-20 popular repos for credible demo
2. Design intent-based query API
3. Build chat-based query UI
4. Implement tree-based dependency visualization

---

## Key Metrics

### Current Capabilities:
- **Dependency Resolution**: 92% success rate (Flask example)
- **CVE Coverage**: Full OSV.dev integration with dual identifiers
- **Supported Ecosystems**: Python (PyPI), JavaScript (npm), Java (Maven), Go
- **Database**: SQLite with 8 core tables, full foreign key support
- **API**: FastAPI with 15+ endpoints
- **Tests**: 76+ tests across unit, integration, and property-based

### Performance Targets:
- **Ingestion**: <15 seconds per repo (including resolution)
- **Query**: <100ms for most queries (database-backed)
- **Graph Generation**: <2 seconds (cached)

---

## Decision Framework

When evaluating new features or changes, ask:

1. **Does this align with the supply chain intelligence vision?**
2. **Does this maintain separation between ingestion and query?**
3. **Does this keep the database as source of truth?**
4. **Does this avoid mixing research with production code?**
5. **Does this improve the AI-queryability of the system?**

If the answer to any of these is "no," reconsider the approach.

---

## Anti-Patterns to Avoid

### ❌ Don't:
- Perform network calls in GET endpoints
- Generate raw SQL from LLM outputs
- Duplicate ingestion logic across CLI/API/Worker
- Mix scoring research with production modules
- Create "works on my machine" schema drift
- Build features that don't serve the intelligence engine vision

### ✅ Do:
- Store everything in the database first
- Use structured intents for AI queries
- Keep ingestion logic in `DependencyIngestionService`
- Isolate scoring models from core system
- Encode schema changes in `init_database()`
- Build features that enable complex supply chain questions

---

## Success Criteria

The project will be successful when:

1. **Users can ask natural language questions** about supply chain risks and get accurate, explainable answers
2. **All data is queryable** without making external API calls
3. **Ingestion is reliable** and can populate hundreds of repos overnight
4. **The UI is intuitive** and doesn't require understanding graph theory
5. **Risk scores are defensible** with statistical grounding
6. **The system scales** to institutional use cases

---

## Long-Term Vision (3-5 Years)

This system should become:

- The **de facto intelligence layer** for OSS supply chain risk
- A **queryable knowledge graph** of the open source ecosystem
- A **foundation for risk propagation** modeling across dependency chains
- A **platform for research** into supply chain security
- An **institutional-grade tool** for compliance and security teams

Every line of code should move us closer to that future.

---

*This document serves as the guiding star for all architectural and product decisions. When in doubt, refer back to these principles.*
