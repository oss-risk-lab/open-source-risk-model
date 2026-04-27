# 🧠 Intelligence Layer - Implementation Plan

**Phase**: Infrastructure → Intelligence
**Goal**: Enable AI-native queries over structured supply chain data
**Timeline**: 4-6 weeks

---

## 🎯 Objectives

### Primary Goals
1. **Populate 20-50 repos** (Python + JavaScript ecosystems)
2. **Implement `/api/query`** with strict intent allowlist
3. **Replace checkbox UI** with AI chat interface
4. **Build tree visualization** from DB relationships

### Constraints (Do NOT)
- ❌ Add depth columns to schema
- ❌ Precompute transitive edges
- ❌ Expand schema prematurely
- ❌ Implement scoring research
- ❌ Generate raw SQL from LLM

---

## 📋 Phase Breakdown

### Task 1: Data Population (Week 1)
**Goal**: 20-50 repos with dependencies and CVEs

#### 1.1 Expand Repository List
**Current**: 20 repos in `populate_popular_repos.py`
**Target**: 50 repos (25 Python, 25 JavaScript)

**Python Repos** (25):
- Web frameworks: Flask, Django, FastAPI, Tornado, Pyramid
- Data science: NumPy, Pandas, Scikit-learn, Matplotlib, SciPy
- Testing: Pytest, Unittest, Nose, Tox, Coverage
- CLI tools: Click, Argparse, Rich, Typer
- Async: AsyncIO, Trio, AnyIO
- HTTP: Requests, HTTPX, Urllib3, AIOHTTP
- Utilities: Six, Python-dateutil, PyYAML, Jinja2

**JavaScript Repos** (25):
- Frameworks: React, Vue, Angular, Svelte, Next.js
- Backend: Express, Koa, Fastify, NestJS, Hapi
- Build tools: Webpack, Vite, Rollup, Parcel, ESBuild
- Testing: Jest, Mocha, Chai, Cypress, Playwright
- Utilities: Lodash, Axios, Moment, Day.js, Ramda

#### 1.2 Run Batch Ingestion
```bash
# Update populate_popular_repos.py with 50 repos
python scripts/populate_popular_repos.py --refresh

# Expected: 4-6 hours runtime
# Expected: 40-45 successful ingestions (90% success rate)
```

#### 1.3 Validate Data Quality
```bash
python scripts/validate_data_quality.py

# Expected output:
# - 40-50 repos with graphs
# - 40-50 repos with dependencies
# - 1000-2000 total dependencies
# - 85-90% resolution rate
# - 100-200 CVEs tracked
```

**Deliverable**: Database with 40-50 populated repos

---

### Task 2: Intent-Based Query API (Week 2-3)
**Goal**: Safe, structured query endpoint with no SQL generation

#### 2.1 Design Intent Schema

**Intent Structure**:
```python
@dataclass
class QueryIntent:
    """Structured query intent (no SQL)."""
    action: str  # From allowlist
    params: Dict[str, Any]  # Validated parameters
    context: Optional[str] = None  # User context
```

**Allowed Actions** (Strict Allowlist):
```python
ALLOWED_ACTIONS = {
    # Single repo queries
    "get_dependencies",      # Get deps for a repo
    "get_cves",             # Get CVEs for a repo
    "get_maintainers",      # Get maintainers for a repo
    "get_graph",            # Get graph for a repo
    
    # Cross-repo queries
    "get_dependents",       # Get repos that depend on package
    "search_repos",         # Search repos by name
    "search_cves",          # Search CVEs by severity/ID
    
    # Tree queries
    "get_dependency_tree",  # Get dep tree (computed on-the-fly)
    "get_transitive_deps",  # Get transitive deps (depth-limited)
}
```

**Parameter Validation**:
```python
PARAM_SCHEMAS = {
    "get_dependencies": {
        "repo_full_name": {"type": "string", "pattern": r"^[\w-]+/[\w-]+$"},
        "include_dev": {"type": "boolean", "default": True},
        "include_optional": {"type": "boolean", "default": True},
    },
    "get_dependents": {
        "package_name": {"type": "string", "max_length": 100},
        "registry_type": {"type": "string", "enum": ["pypi", "npm", "maven"]},
        "limit": {"type": "integer", "min": 1, "max": 100, "default": 20},
    },
    # ... etc
}
```

#### 2.2 Implement Intent Parser

**File**: `src/open_source_risk_model/intelligence/intent_parser.py`

```python
class IntentParser:
    """Parse natural language to structured intents."""
    
    def parse(self, query: str, context: Optional[str] = None) -> QueryIntent:
        """
        Parse natural language query to intent.
        
        Uses LLM to extract action + params, then validates against allowlist.
        """
        # Step 1: LLM extracts structured intent
        raw_intent = self._llm_extract(query, context)
        
        # Step 2: Validate action is in allowlist
        if raw_intent["action"] not in ALLOWED_ACTIONS:
            raise InvalidIntentError(f"Action not allowed: {raw_intent['action']}")
        
        # Step 3: Validate parameters against schema
        validated_params = self._validate_params(
            raw_intent["action"], 
            raw_intent["params"]
        )
        
        # Step 4: Return validated intent
        return QueryIntent(
            action=raw_intent["action"],
            params=validated_params,
            context=context
        )
```

#### 2.3 Implement Intent Executor

**File**: `src/open_source_risk_model/intelligence/intent_executor.py`

```python
class IntentExecutor:
    """Execute validated intents against database."""
    
    def execute(self, intent: QueryIntent) -> QueryResult:
        """
        Execute intent using parameterized queries.
        
        NO SQL GENERATION - only predefined queries with parameters.
        """
        # Dispatch to handler based on action
        handler = self._get_handler(intent.action)
        
        # Execute with validated params
        result = handler(intent.params)
        
        # Return structured result
        return QueryResult(
            action=intent.action,
            data=result,
            metadata=self._get_metadata(intent)
        )
    
    def _get_handler(self, action: str) -> Callable:
        """Get handler for action (from allowlist)."""
        return {
            "get_dependencies": self._handle_get_dependencies,
            "get_dependents": self._handle_get_dependents,
            "get_cves": self._handle_get_cves,
            # ... etc
        }[action]
    
    def _handle_get_dependencies(self, params: Dict) -> List[Dict]:
        """Handler for get_dependencies action."""
        # Use existing DependencyRepository
        return self.dep_repo.get_dependencies(
            repo_full_name=params["repo_full_name"],
            include_dev=params.get("include_dev", True),
            include_optional=params.get("include_optional", True)
        )
```

#### 2.4 Add `/api/query` Endpoint

**File**: `api/app.py`

```python
@app.post("/api/query")
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """
    AI-native query endpoint.
    
    Accepts natural language, returns structured results.
    NO SQL GENERATION - uses intent allowlist.
    """
    try:
        # Parse natural language to intent
        intent = intent_parser.parse(
            query=request.query,
            context=request.context
        )
        
        # Execute intent
        result = intent_executor.execute(intent)
        
        # Return structured response
        return QueryResponse(
            success=True,
            intent=intent,
            result=result,
            metadata={
                "query": request.query,
                "action": intent.action,
                "execution_time_ms": result.execution_time_ms
            }
        )
    
    except InvalidIntentError as e:
        return QueryResponse(
            success=False,
            error=str(e),
            error_type="invalid_intent"
        )
    
    except Exception as e:
        logger.error(f"Query execution failed: {e}", exc_info=True)
        return QueryResponse(
            success=False,
            error="Query execution failed",
            error_type="execution_error"
        )
```

**Deliverable**: `/api/query` endpoint with intent allowlist

---

### Task 3: AI Chat Interface (Week 3-4)
**Goal**: Replace checkbox UI with chat-based exploration

#### 3.1 Design Chat UI

**File**: `ui/chat.html`

**Layout**:
```
┌─────────────────────────────────────────┐
│  Open Source Risk Model - Chat         │
├─────────────────────────────────────────┤
│                                         │
│  [Repo Context: pallets/flask ▼]       │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Chat History                      │ │
│  │                                   │ │
│  │ You: Show me Flask's dependencies │ │
│  │                                   │ │
│  │ AI: Found 39 dependencies for    │ │
│  │     pallets/flask:                │ │
│  │     [Table with deps]             │ │
│  │                                   │ │
│  │ You: Which repos depend on it?   │ │
│  │                                   │ │
│  │ AI: 12 repos depend on Flask:    │ │
│  │     [List of repos]               │ │
│  │                                   │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Ask a question...                 │ │
│  └───────────────────────────────────┘ │
│                                    [Send]│
└─────────────────────────────────────────┘
```

**Features**:
- Repo context selector (dropdown)
- Chat history with user/AI messages
- Result rendering (table, list, tree, graph)
- Example queries (quick start)
- Loading states
- Error handling

#### 3.2 Implement Chat Logic

**File**: `ui/chat.js`

```javascript
class ChatInterface {
    constructor() {
        this.context = null;  // Current repo context
        this.history = [];    // Chat history
    }
    
    async sendQuery(query) {
        // Add user message to history
        this.addMessage('user', query);
        
        // Show loading
        this.showLoading();
        
        try {
            // Call /api/query
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    query: query,
                    context: this.context
                })
            });
            
            const result = await response.json();
            
            // Render result based on action
            this.renderResult(result);
            
        } catch (error) {
            this.showError(error);
        } finally {
            this.hideLoading();
        }
    }
    
    renderResult(result) {
        // Render based on action type
        switch (result.intent.action) {
            case 'get_dependencies':
                this.renderTable(result.data);
                break;
            case 'get_dependency_tree':
                this.renderTree(result.data);
                break;
            case 'get_graph':
                this.renderGraph(result.data);
                break;
            default:
                this.renderList(result.data);
        }
    }
}
```

#### 3.3 Add Result Renderers

**Table Renderer** (for dependencies, CVEs):
```javascript
renderTable(data) {
    const table = document.createElement('table');
    // ... render table with columns
    this.addMessage('ai', table);
}
```

**Tree Renderer** (for dependency trees):
```javascript
renderTree(data) {
    const tree = this.buildTreeComponent(data);
    this.addMessage('ai', tree);
}
```

**Graph Renderer** (for supply chain graphs):
```javascript
renderGraph(data) {
    // Reuse existing graph-viz.js
    const graph = new GraphVisualization(data);
    this.addMessage('ai', graph.render());
}
```

**Deliverable**: Chat UI replacing checkbox interface

---

### Task 4: Tree Visualization (Week 4-5)
**Goal**: Interactive dependency tree from DB relationships

#### 4.1 Implement Tree Query

**File**: `src/open_source_risk_model/intelligence/tree_builder.py`

```python
class DependencyTreeBuilder:
    """Build dependency trees from DB relationships."""
    
    def build_tree(
        self, 
        repo_full_name: str, 
        max_depth: int = 3,
        include_transitive: bool = True
    ) -> DependencyTree:
        """
        Build dependency tree by recursively querying DB.
        
        NO PRECOMPUTED EDGES - queries on-the-fly.
        """
        # Get direct dependencies
        root = self._get_dependencies(repo_full_name)
        
        if include_transitive and max_depth > 1:
            # Recursively get dependencies of dependencies
            self._expand_tree(root, max_depth - 1, visited=set())
        
        return DependencyTree(root=root)
    
    def _expand_tree(self, node: TreeNode, depth: int, visited: Set[str]):
        """Recursively expand tree (depth-limited)."""
        if depth == 0 or node.repo in visited:
            return
        
        visited.add(node.repo)
        
        # Get dependencies for this node
        deps = self._get_dependencies(node.repo)
        
        # Add as children
        node.children = deps
        
        # Recurse
        for child in deps:
            self._expand_tree(child, depth - 1, visited)
```

#### 4.2 Add Tree Endpoint

**File**: `api/app.py`

```python
@app.get("/api/repos/{repo}/tree")
async def get_dependency_tree(
    repo: str,
    max_depth: int = 3,
    include_transitive: bool = True
) -> DependencyTreeResponse:
    """
    Get dependency tree for a repository.
    
    Computed on-the-fly from DB relationships.
    """
    tree_builder = DependencyTreeBuilder(db_path)
    
    tree = tree_builder.build_tree(
        repo_full_name=repo,
        max_depth=max_depth,
        include_transitive=include_transitive
    )
    
    return DependencyTreeResponse(
        repo=repo,
        tree=tree.to_dict(),
        metadata={
            "max_depth": max_depth,
            "node_count": tree.node_count,
            "computed_at": datetime.now().isoformat()
        }
    )
```

#### 4.3 Build Tree UI Component

**File**: `ui/tree-viz.js`

```javascript
class TreeVisualization {
    constructor(treeData) {
        this.data = treeData;
    }
    
    render(container) {
        // Use D3.js tree layout
        const tree = d3.tree()
            .size([height, width]);
        
        const root = d3.hierarchy(this.data);
        const nodes = tree(root);
        
        // Render nodes
        this.renderNodes(nodes);
        
        // Render edges
        this.renderEdges(nodes);
        
        // Add interactivity
        this.addInteractivity();
    }
    
    addInteractivity() {
        // Click to expand/collapse
        // Hover to show details
        // Right-click for context menu
    }
}
```

**Deliverable**: Interactive tree visualization

---

### Task 5: Testing & Documentation (Week 5-6)
**Goal**: Ensure quality and usability

#### 5.1 Add Tests

**Intent Parser Tests**:
```python
def test_parse_valid_intent():
    parser = IntentParser()
    intent = parser.parse("Show me Flask's dependencies")
    assert intent.action == "get_dependencies"
    assert intent.params["repo_full_name"] == "pallets/flask"

def test_parse_invalid_action():
    parser = IntentParser()
    with pytest.raises(InvalidIntentError):
        parser.parse("DROP TABLE repo_dependencies")
```

**Intent Executor Tests**:
```python
def test_execute_get_dependencies():
    executor = IntentExecutor(db_path)
    intent = QueryIntent(
        action="get_dependencies",
        params={"repo_full_name": "pallets/flask"}
    )
    result = executor.execute(intent)
    assert len(result.data) > 0
```

**Tree Builder Tests**:
```python
def test_build_tree_depth_limit():
    builder = DependencyTreeBuilder(db_path)
    tree = builder.build_tree("pallets/flask", max_depth=2)
    assert tree.max_depth <= 2
```

#### 5.2 Update Documentation

**Files to Update**:
- `docs/API.md` - Add `/api/query` documentation
- `docs/INTELLIGENCE_LAYER.md` - New guide for AI queries
- `README.md` - Update with chat UI instructions
- `ui/README.md` - Document chat interface

**Deliverable**: Comprehensive tests and docs

---

## 📊 Success Criteria

### Data Population
- ✅ 40-50 repos ingested
- ✅ 1000-2000 dependencies stored
- ✅ 85-90% resolution rate
- ✅ 100-200 CVEs tracked

### Intent API
- ✅ `/api/query` endpoint working
- ✅ 8-10 allowed actions implemented
- ✅ Parameter validation working
- ✅ No SQL generation (only parameterized queries)
- ✅ <100ms query execution

### Chat UI
- ✅ Natural language input
- ✅ Context-aware queries
- ✅ Multi-format result rendering
- ✅ Error handling
- ✅ Example queries

### Tree Visualization
- ✅ Interactive tree component
- ✅ Depth-limited traversal
- ✅ Circular dependency detection
- ✅ Expand/collapse nodes
- ✅ Computed from DB (no precomputed edges)

### Quality
- ✅ 20+ new tests
- ✅ All tests passing
- ✅ Documentation updated
- ✅ No schema changes

---

## 🚫 Anti-Patterns to Avoid

### Do NOT
1. **Generate SQL from LLM output**
   - ❌ Bad: `llm.generate_sql(query)`
   - ✅ Good: `intent_parser.parse(query)` → validate → execute

2. **Add depth columns to schema**
   - ❌ Bad: `ALTER TABLE repo_dependencies ADD COLUMN depth INTEGER`
   - ✅ Good: Compute depth on-the-fly during tree traversal

3. **Precompute transitive edges**
   - ❌ Bad: Store all transitive dependencies
   - ✅ Good: Compute on-the-fly with depth limit

4. **Expand schema prematurely**
   - ❌ Bad: Add risk_score, path, parent_id columns
   - ✅ Good: Use existing schema, compute what's needed

5. **Implement scoring research**
   - ❌ Bad: Build statistical risk models now
   - ✅ Good: Defer until query layer is stable

---

## 📅 Timeline

### Week 1: Data Population
- Day 1-2: Expand repo list to 50
- Day 3-5: Run batch ingestion
- Day 6-7: Validate data quality

### Week 2: Intent API Foundation
- Day 1-2: Design intent schema
- Day 3-4: Implement intent parser
- Day 5-7: Implement intent executor

### Week 3: Intent API Completion
- Day 1-3: Add `/api/query` endpoint
- Day 4-5: Add all allowed actions
- Day 6-7: Testing and refinement

### Week 4: Chat UI
- Day 1-2: Design and build chat interface
- Day 3-4: Implement result renderers
- Day 5-7: Integration and polish

### Week 5: Tree Visualization
- Day 1-3: Implement tree builder
- Day 4-5: Build tree UI component
- Day 6-7: Integration and testing

### Week 6: Testing & Documentation
- Day 1-3: Write comprehensive tests
- Day 4-5: Update documentation
- Day 6-7: Final polish and validation

---

## 🎯 Deliverables

### End of Week 2
- ✅ 40-50 repos populated
- ✅ Intent parser working
- ✅ Intent executor working

### End of Week 4
- ✅ `/api/query` endpoint live
- ✅ Chat UI functional
- ✅ Basic queries working

### End of Week 6
- ✅ Tree visualization working
- ✅ All tests passing
- ✅ Documentation complete
- ✅ Ready for user testing

---

## 🚀 Getting Started

### Step 1: Update Repo List
```bash
# Edit scripts/populate_popular_repos.py
# Add 30 more repos (25 Python, 25 JS total)
```

### Step 2: Run Data Population
```bash
python scripts/populate_popular_repos.py --refresh
python scripts/validate_data_quality.py
```

### Step 3: Create Intelligence Module
```bash
mkdir -p src/open_source_risk_model/intelligence
touch src/open_source_risk_model/intelligence/__init__.py
touch src/open_source_risk_model/intelligence/intent_parser.py
touch src/open_source_risk_model/intelligence/intent_executor.py
touch src/open_source_risk_model/intelligence/tree_builder.py
```

### Step 4: Start Building
Follow the task breakdown above, week by week.

---

**This plan aligns with North Star principles: database-first, no SQL generation, compute on-the-fly, defer scoring research.**

**Ready to start with Week 1: Data Population?**
