# Dependency Graph - Design Improvements

## Critical Improvements Based on Review

This document captures the key design improvements identified before implementation.

## 1. Manifest Discovery (Not Just Root Files)

### Problem
Current design only fetches fixed list of files from root:
- Misses `pyproject.toml`, `setup.cfg`, `poetry.lock`
- Misses manifests in subdirectories (`requirements/dev.txt`)
- Misses monorepo structures

### Solution: Tree Scanning

```python
class ManifestDiscovery:
    """Discovers dependency manifests in repository tree."""
    
    MANIFEST_PATTERNS = [
        # Python
        r'.*requirements.*\.txt$',
        r'.*pyproject\.toml$',
        r'.*setup\.cfg$',
        r'.*poetry\.lock$',
        r'.*Pipfile$',
        
        # JavaScript
        r'.*package\.json$',
        r'.*package-lock\.json$',
        r'.*yarn\.lock$',
        r'.*pnpm-lock\.yaml$',
        
        # Java
        r'.*pom\.xml$',
        r'.*build\.gradle$',
        
        # Go
        r'.*go\.mod$',
    ]
    
    def discover_manifests(
        self,
        repo_full_name: str,
        max_depth: int = 3,
        max_files: int = 20
    ) -> List[str]:
        """
        Discover manifest files using GitHub Tree API.
        
        Strategy:
        1. Fetch repository tree (recursive)
        2. Filter by manifest patterns
        3. Limit to max_files (rate limit protection)
        4. Return file paths
        """
        import requests
        
        token = os.environ.get('GITHUB_TOKEN')
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        
        # Get default branch
        repo_url = f"https://api.github.com/repos/{repo_full_name}"
        repo_data = requests.get(repo_url, headers=headers).json()
        default_branch = repo_data.get('default_branch', 'main')
        
        # Get tree (recursive)
        tree_url = f"https://api.github.com/repos/{repo_full_name}/git/trees/{default_branch}?recursive=1"
        response = requests.get(tree_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return []
        
        tree_data = response.json()
        tree = tree_data.get('tree', [])
        
        # Filter manifest files
        manifests = []
        for item in tree:
            if item['type'] != 'blob':
                continue
            
            path = item['path']
            
            # Check depth
            depth = path.count('/')
            if depth > max_depth:
                continue
            
            # Check pattern match
            for pattern in self.MANIFEST_PATTERNS:
                if re.match(pattern, path):
                    manifests.append(path)
                    break
            
            # Limit total files
            if len(manifests) >= max_files:
                break
        
        return manifests
```

**Benefits:**
- Finds manifests in subdirectories
- Supports monorepos
- Respects rate limits with max_files cap
- Single API call (tree is recursive)



## 2. Add pyproject.toml Parser (Modern Python Standard)

### Problem
Current design only parses `requirements.txt`, missing modern Python projects using:
- PEP 621 (`[project]` dependencies)
- Poetry (`[tool.poetry.dependencies]`)
- PDM, Hatch, etc.

### Solution: PyProjectTomlParser

```python
class PyProjectTomlParser(DependencyParser):
    """Parser for pyproject.toml (PEP 621 + Poetry)."""
    
    def can_parse(self, file_path: str) -> bool:
        return file_path.endswith('pyproject.toml')
    
    def parse(self, content: str) -> List[Dependency]:
        """
        Parse pyproject.toml.
        
        Supports:
        - PEP 621: [project] dependencies
        - Poetry: [tool.poetry.dependencies]
        """
        try:
            import tomli  # or tomllib in Python 3.11+
            data = tomli.loads(content)
        except Exception:
            return []
        
        dependencies = []
        
        # PEP 621 format
        project = data.get('project', {})
        
        # Production dependencies
        for dep_spec in project.get('dependencies', []):
            dep = self._parse_pep621_spec(dep_spec)
            if dep:
                dependencies.append(dep)
        
        # Optional dependencies (dev, test, etc.)
        for group, deps in project.get('optional-dependencies', {}).items():
            for dep_spec in deps:
                dep = self._parse_pep621_spec(dep_spec)
                if dep:
                    dep.is_dev = (group in ['dev', 'test', 'docs'])
                    dep.is_optional = True
                    dependencies.append(dep)
        
        # Poetry format
        poetry = data.get('tool', {}).get('poetry', {})
        
        # Poetry dependencies
        for name, spec in poetry.get('dependencies', {}).items():
            if name == 'python':  # Skip Python version
                continue
            
            dep = self._parse_poetry_spec(name, spec)
            if dep:
                dependencies.append(dep)
        
        # Poetry dev dependencies
        for group_name, group_deps in poetry.get('group', {}).items():
            for name, spec in group_deps.get('dependencies', {}).items():
                dep = self._parse_poetry_spec(name, spec)
                if dep:
                    dep.is_dev = True
                    dependencies.append(dep)
        
        return dependencies
    
    def _parse_pep621_spec(self, spec: str) -> Optional[Dependency]:
        """
        Parse PEP 621 dependency spec.
        
        Examples:
        - "requests"
        - "requests>=2.0.0"
        - "requests[security]>=2.0.0"
        - "requests>=2.0.0; python_version>='3.7'"
        """
        # Remove environment markers
        if ';' in spec:
            spec = spec.split(';')[0].strip()
        
        # Use packaging library for proper parsing
        try:
            from packaging.requirements import Requirement
            req = Requirement(spec)
            
            return Dependency(
                package_name=req.name,
                version_constraint=str(req.specifier) if req.specifier else "",
                is_dev=False,
                is_optional=False,
                extras=list(req.extras) if req.extras else None
            )
        except Exception:
            # Fallback to simple parsing
            match = re.match(r'^([a-zA-Z0-9_-]+)(\[[\w,]+\])?(.*)?$', spec)
            if match:
                return Dependency(
                    package_name=match.group(1),
                    version_constraint=match.group(3).strip() if match.group(3) else "",
                    is_dev=False,
                    is_optional=False
                )
        
        return None
    
    def _parse_poetry_spec(self, name: str, spec: Any) -> Optional[Dependency]:
        """
        Parse Poetry dependency spec.
        
        Examples:
        - "^2.0.0" (string)
        - {version = "^2.0.0", optional = true} (dict)
        """
        if isinstance(spec, str):
            return Dependency(
                package_name=name,
                version_constraint=spec,
                is_dev=False,
                is_optional=False
            )
        elif isinstance(spec, dict):
            return Dependency(
                package_name=name,
                version_constraint=spec.get('version', ''),
                is_dev=False,
                is_optional=spec.get('optional', False)
            )
        
        return None
```

**Benefits:**
- Supports modern Python projects
- Handles PEP 621 and Poetry formats
- Uses `packaging` library for robust parsing
- Extracts optional dependencies and groups



## 3. Improved Database Schema

### Problem
Current schema conflates fields and loses structure:
- `version_constraint` and `declared_version` are duplicates
- No support for extras, markers, dependency groups
- No `manifest_path` (only filename)
- Can't handle multiple manifests per repo

### Solution: Enhanced Schema

```sql
CREATE TABLE repo_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    package_name TEXT NOT NULL,
    registry_type TEXT NOT NULL,
    
    -- Structured dependency data
    specifier TEXT,              -- Raw version specifier (e.g., ">=2.0,<3.0")
    extras TEXT,                 -- JSON array of extras (e.g., ["security", "socks"])
    markers TEXT,                -- Environment markers (e.g., "python_version >= '3.7'")
    
    -- Dependency metadata
    dependency_group TEXT,       -- prod, dev, test, docs, optional
    is_direct BOOLEAN NOT NULL DEFAULT 1,
    is_optional BOOLEAN NOT NULL DEFAULT 0,
    
    -- Provenance
    manifest_path TEXT NOT NULL, -- Full path (e.g., "requirements/dev.txt")
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    
    FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE,
    
    -- Unique constraint includes manifest_path to support multiple manifests
    UNIQUE(repo_full_name, package_name, manifest_path)
);

CREATE INDEX idx_repo_dependencies_repo ON repo_dependencies(repo_full_name);
CREATE INDEX idx_repo_dependencies_package ON repo_dependencies(package_name, registry_type);
CREATE INDEX idx_repo_dependencies_direct ON repo_dependencies(is_direct);
CREATE INDEX idx_repo_dependencies_group ON repo_dependencies(dependency_group);
```

**Key Changes:**
- `specifier` instead of `version_constraint` (clearer naming)
- `extras` as JSON array (supports `requests[security,socks]`)
- `markers` for environment markers
- `dependency_group` instead of just `is_dev` (more flexible)
- `manifest_path` instead of `manifest_file` (full path)
- Unique constraint includes `manifest_path` (multi-manifest support)

**Updated Dependency Dataclass:**

```python
@dataclass
class Dependency:
    """Represents a parsed dependency."""
    package_name: str
    specifier: str = ""           # Version specifier
    extras: List[str] = None      # Extras like [security]
    markers: str = ""             # Environment markers
    dependency_group: str = "prod"  # prod, dev, test, docs, optional
    is_optional: bool = False
    manifest_path: str = ""       # Full path to manifest
```



## 4. Add RESOLVES_TO Edge Type

### Problem
Current design has conceptual `Package → Repo` resolution but no explicit edge type.
This makes traversal and UI rendering ambiguous.

### Solution: Explicit RESOLVES_TO Edge

```python
class EdgeType(str, Enum):
    HAS_RELEASE = "has_release"
    MAINTAINED_BY = "maintained_by"
    HAS_CVE = "has_cve"
    PUBLISHED_AS = "published_as"
    HAS_RISK_FACTOR = "has_risk_factor"
    DEPENDS_ON = "depends_on"
    RESOLVES_TO = "resolves_to"  # NEW: Package → Repository

class ResolvesToEdge(Edge):
    """Edge from Package node to Repository node."""
    relationship_type: EdgeType = EdgeType.RESOLVES_TO
    source: str  # Package node ID
    target: str  # Repository node ID
    metadata: Dict[str, Any] = {
        "resolution_method": str,   # pypi_metadata, npm_repository, github_search
        "resolution_confidence": float,  # 0.0-1.0
    }
    provenance: Dict[str, Any] = {
        "source": "package_resolver",
        "confidence": float,
        "fetched_at": str,
    }
```

**Graph Structure:**

```
[Repo: flask] ──depends_on──> [Package: requests] ──resolves_to──> [Repo: psf/requests]
                                                                           │
                                                                    has_cve
                                                                           ▼
                                                                    [CVE-2024-1234]
```

**Benefits:**
- Clear semantics for traversal
- Enables query: "What repos depend on repo X?" via path traversal
- Confidence tracking at edge level
- UI can render resolution quality

**Query Example:**

```python
# Find all repos that depend on psf/requests
def find_dependents(target_repo: str) -> List[str]:
    """
    Find repos that depend on target_repo.
    
    Path: RepoA -> PackageP -> (RESOLVES_TO) -> RepoX
    """
    # 1. Find all packages that resolve to target_repo
    packages = graph.find_edges(
        target=f"repo:{target_repo}",
        edge_type=EdgeType.RESOLVES_TO
    )
    
    # 2. Find all repos that depend on those packages
    dependents = []
    for pkg_edge in packages:
        pkg_id = pkg_edge.source
        dep_edges = graph.find_edges(
            target=pkg_id,
            edge_type=EdgeType.DEPENDS_ON
        )
        dependents.extend([e.source for e in dep_edges])
    
    return dependents
```



## 5. Rate Limit Protection

### Problem
Current design will quickly hit GitHub API rate limits:
- Fetching manifests (5000 requests/hour)
- Fetching PyPI/npm metadata
- Validating repos exist
- GitHub search fallback

### Solution: Budget Knobs + Caching

```python
@dataclass
class DependencyIngestionConfig:
    """Configuration for dependency ingestion with rate limit protection."""
    
    # Discovery limits
    max_manifests_per_repo: int = 10
    max_manifest_depth: int = 3
    
    # Resolution limits
    max_packages_per_repo: int = 100
    max_registry_calls_per_run: int = 50
    
    # Caching
    manifest_cache_ttl_hours: int = 24
    package_mapping_cache_ttl_hours: int = 168  # 1 week
    
    # Timeouts
    github_api_timeout_seconds: int = 10
    registry_api_timeout_seconds: int = 5
    
    # Retry policy
    max_retries: int = 3
    retry_backoff_seconds: int = 2

class RateLimitTracker:
    """Tracks API usage to prevent rate limit exhaustion."""
    
    def __init__(self):
        self.github_calls = 0
        self.registry_calls = 0
        self.start_time = time.time()
    
    def check_github_budget(self, config: DependencyIngestionConfig) -> bool:
        """Check if we have GitHub API budget remaining."""
        # Check actual rate limit from GitHub
        remaining = self._get_github_rate_limit_remaining()
        
        # Reserve 1000 calls for other operations
        return remaining > 1000
    
    def check_registry_budget(self, config: DependencyIngestionConfig) -> bool:
        """Check if we have registry API budget remaining."""
        return self.registry_calls < config.max_registry_calls_per_run
    
    def record_github_call(self):
        """Record a GitHub API call."""
        self.github_calls += 1
    
    def record_registry_call(self):
        """Record a registry API call."""
        self.registry_calls += 1
    
    def _get_github_rate_limit_remaining(self) -> int:
        """Get remaining GitHub API calls."""
        import requests
        
        token = os.environ.get('GITHUB_TOKEN')
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        
        response = requests.get(
            'https://api.github.com/rate_limit',
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['rate']['remaining']
        
        return 0

class ManifestCache:
    """Caches manifest content to avoid re-fetching."""
    
    def __init__(self, cache_dir: str = "data/manifest_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get(
        self,
        repo_full_name: str,
        manifest_path: str,
        ttl_hours: int = 24
    ) -> Optional[str]:
        """Get cached manifest content."""
        cache_key = f"{repo_full_name}/{manifest_path}".replace('/', '_')
        cache_file = self.cache_dir / f"{cache_key}.txt"
        
        if not cache_file.exists():
            return None
        
        # Check TTL
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours > ttl_hours:
            return None
        
        return cache_file.read_text()
    
    def set(
        self,
        repo_full_name: str,
        manifest_path: str,
        content: str
    ):
        """Cache manifest content."""
        cache_key = f"{repo_full_name}/{manifest_path}".replace('/', '_')
        cache_file = self.cache_dir / f"{cache_key}.txt"
        cache_file.write_text(content)
```

**Integration:**

```python
class GraphBuilder:
    """Enhanced with rate limit protection."""
    
    def __init__(self):
        self.rate_limiter = RateLimitTracker()
        self.manifest_cache = ManifestCache()
        self.config = DependencyIngestionConfig()
    
    def _fetch_manifests(self, repo_full_name: str) -> Dict[str, str]:
        """Fetch manifests with rate limit protection."""
        
        # Check budget
        if not self.rate_limiter.check_github_budget(self.config):
            logger.warning(f"GitHub API budget exhausted, skipping manifests for {repo_full_name}")
            return {}
        
        # Discover manifests
        manifest_paths = self.manifest_discovery.discover_manifests(
            repo_full_name,
            max_depth=self.config.max_manifest_depth,
            max_files=self.config.max_manifests_per_repo
        )
        
        manifests = {}
        
        for path in manifest_paths:
            # Check cache first
            cached = self.manifest_cache.get(
                repo_full_name,
                path,
                ttl_hours=self.config.manifest_cache_ttl_hours
            )
            
            if cached:
                manifests[path] = cached
                continue
            
            # Fetch from GitHub
            try:
                content = self._fetch_file_from_github(repo_full_name, path)
                if content:
                    manifests[path] = content
                    self.manifest_cache.set(repo_full_name, path, content)
                    self.rate_limiter.record_github_call()
            except Exception as e:
                logger.warning(f"Failed to fetch {path} from {repo_full_name}: {e}")
        
        return manifests
```



## 6. Defer Transitive Dependencies to v2

### Problem
Current design includes transitive dependency traversal, but it won't work without:
- Resolving package→repo for most nodes
- Ingesting those resolved repos' dependencies
- Or using lockfiles/registry metadata (different problem)

### Solution: Ship Direct Dependencies First

**Phase 1 (MVP):**
- ✅ Parse direct dependencies from manifests
- ✅ Store in database
- ✅ Query direct dependencies
- ✅ Query reverse dependencies (dependents)
- ❌ NO transitive queries yet

**Phase 2 (Later):**
- Add transitive traversal once multi-repo ingestion is stable
- Requires: Most packages resolved to repos, those repos ingested
- Alternative: Parse lockfiles for full dependency tree

**API Changes:**

```python
# Phase 1: Direct only
GET /api/repos/{repo}/dependencies
# Returns only direct dependencies

GET /api/repos/{repo}/dependents
# Returns repos that directly depend on this

# Phase 2: Add transitive (later)
GET /api/repos/{repo}/dependencies?transitive=true&max_depth=3
# Requires multi-repo ingestion
```

**Benefits:**
- Ship faster with working direct dependencies
- Avoid complexity of transitive traversal
- Focus on getting resolution accuracy high first
- Add transitive when infrastructure is ready



## 7. Implementation Phases (Revised)

### Phase A: Storage + API First (Fast Win)

**Goal:** Get dependency data flowing without changing graph rendering

**Tasks:**
1. Add database tables (repo_dependencies, package_mappings)
2. Run migration on existing database
3. Implement DependencyRepository
4. Add API endpoints:
   - `GET /api/repos/{repo}/dependencies`
   - `GET /api/packages/{package}/dependents`
5. Test with manually inserted data

**Deliverable:** Working API endpoints with test data

**Time:** 2-3 days

---

### Phase B: Manifest Discovery + Parsing (The Real Unlock)

**Goal:** Parse dependencies from real repositories

**Tasks:**
1. Implement ManifestDiscovery (tree scanning)
2. Implement RequirementsTxtParser
3. Implement PyProjectTomlParser
4. Add manifest caching
5. Add rate limit protection
6. Integrate with GraphBuilder (opt-in flag)
7. Test against known repos (flask, requests, fastapi)

**Deliverable:** Dependencies parsed and stored for Python repos

**Time:** 3-4 days

---

### Phase C: Package Resolution (Connect the Network)

**Goal:** Resolve packages to source repositories

**Tasks:**
1. Implement PackageResolver
2. Add PyPI resolution (project_urls, home_page)
3. Add npm resolution (repository field)
4. Add RESOLVES_TO edge type
5. Update graph schema
6. Add resolution caching
7. Test resolution accuracy on sample packages

**Deliverable:** Package nodes linked to repo nodes via RESOLVES_TO edges

**Time:** 3-4 days

---

### Phase D: Testing + Documentation

**Goal:** Production-ready feature

**Tasks:**
1. Unit tests for parsers
2. Unit tests for resolver
3. Integration tests for end-to-end flow
4. Property tests for correctness
5. API documentation
6. User guide
7. Performance optimization

**Deliverable:** Tested, documented, production-ready

**Time:** 2-3 days

---

**Total Estimated Time:** 10-14 days



## 8. Code-Level Fixes

### Fix 1: Flexible Filename Matching

**Problem:**
```python
def can_parse(self, file_path: str) -> bool:
    return file_path.endswith('requirements.txt')  # Too restrictive
```

**Solution:**
```python
def can_parse(self, file_path: str) -> bool:
    # Match any requirements file in any directory
    return bool(re.search(r'requirements.*\.txt$', file_path))
```

---

### Fix 2: Use `packaging` Library for Python

**Problem:**
```python
# Regex parsing is fragile and incomplete
match = re.match(r'^([a-zA-Z0-9_-]+)(\[[\w,]+\])?(.*)?$', line)
```

**Solution:**
```python
from packaging.requirements import Requirement

def _parse_requirement(self, line: str) -> Optional[Dependency]:
    """Parse using packaging library."""
    try:
        req = Requirement(line)
        return Dependency(
            package_name=req.name,
            specifier=str(req.specifier),
            extras=list(req.extras),
            markers=str(req.marker) if req.marker else ""
        )
    except Exception as e:
        logger.warning(f"Failed to parse requirement: {line}: {e}")
        return None
```

---

### Fix 3: Store Per-Dependency Manifest Path

**Problem:**
```python
# Loses provenance for multi-manifest repos
self.dependency_repo.save_dependencies(
    repo_full_name,
    all_dependencies,
    list(manifests.keys())[0]  # BUG: Only first manifest
)
```

**Solution:**
```python
# Store manifest_path in Dependency object
for manifest_path, content in manifests.items():
    dependencies = self.parser_registry.parse_file(manifest_path, content)
    
    # Set manifest_path on each dependency
    for dep in dependencies:
        dep.manifest_path = manifest_path
    
    # Save with full provenance
    self.dependency_repo.save_dependencies(
        repo_full_name,
        dependencies  # Each has its own manifest_path
    )
```

---

### Fix 4: Infer Registry from Manifest Path

**Problem:**
```python
# Fragile inference
def _infer_registry_type(self, manifest_file: str) -> str:
    if 'requirements' in manifest_file:
        return 'pypi'
```

**Solution:**
```python
def _infer_registry_type(self, manifest_path: str) -> str:
    """Infer registry from manifest path."""
    path_lower = manifest_path.lower()
    
    # Python
    if any(x in path_lower for x in ['requirements', 'pyproject.toml', 'setup.cfg', 'pipfile']):
        return 'pypi'
    
    # JavaScript
    if 'package.json' in path_lower or 'package-lock.json' in path_lower:
        return 'npm'
    
    # Java
    if 'pom.xml' in path_lower or 'build.gradle' in path_lower:
        return 'maven'
    
    # Go
    if 'go.mod' in path_lower:
        return 'go'
    
    return 'unknown'
```

## Summary of Improvements

| Issue | Impact | Fix |
|-------|--------|-----|
| Root-only manifest fetching | High | Tree scanning with pattern matching |
| Missing pyproject.toml | High | Add PyProjectTomlParser |
| Schema loses structure | Medium | Enhanced schema with extras, markers, groups |
| No RESOLVES_TO edge | Medium | Add explicit edge type |
| Rate limit exposure | High | Budget knobs + caching |
| Transitive won't work yet | Low | Defer to v2, ship direct first |
| Fragile parsing | Medium | Use `packaging` library |
| Lost provenance | Medium | Store manifest_path per dependency |

## Next Steps

1. ✅ Review improvements
2. Update design.md with these changes
3. Create implementation tasks
4. Start with Phase A (Storage + API)

Ready to proceed?
