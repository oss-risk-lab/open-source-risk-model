# Design Document: Dataset Expansion to 200 Repositories

## Overview

This feature expands the open source risk model dataset from 51 to 200 repositories, representing a 4x scale increase. The expansion leverages proven infrastructure (batch ingestion CLI, repository selection scripts, multi-repo database) while introducing comprehensive validation, monitoring, and rollback capabilities to ensure data quality and system performance.

### Goals

- Expand dataset to 200 repositories across 5+ package ecosystems
- Target 15,000-50,000 total dependencies with >85% resolution rate
- Maintain query performance under 5 seconds (p95)
- Ensure ecosystem distribution targets (npm 25-40%, PyPI 25-40%, Go ≥10%, Maven ≥10%, RubyGems ≥5%)
- Generate 5+ new cross-repository insights not visible in 51-repo dataset
- Provide rollback capability for failed expansions
- Detect and report duplicate dependency graphs post-ingestion

### Non-Goals

- Real-time ingestion (batch processing is sufficient)
- Distributed ingestion across multiple machines
- Custom package resolvers beyond existing ecosystem support
- Automated insight interpretation (human analysis required)
- Transitive dependency depth calculation (requires Step 3: transitive ingestion feature - deferred to future work)

## Architecture

### High-Level Design

The expansion follows a pipeline architecture with five stages:

1. **Repository Selection**: Query GitHub API, apply selection criteria, generate prioritized list
2. **Pre-Expansion Backup**: Create database backup with timestamp
3. **Batch Ingestion**: Process repository list using existing CLI with monitoring
4. **Validation**: Verify data quality, ecosystem distribution, performance, and signal quality
5. **Reporting**: Generate expansion summary with metrics and insights

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Expansion Orchestrator                        │
│  (scripts/expand_dataset.py - NEW)                              │
└────────┬────────────────────────────────────────────────────────┘
         │
         ├──► Repository Selector (scripts/populate_popular_repos.py - ENHANCED)
         │    ├─► GitHub API Client
         │    ├─► Selection Criteria Engine (NEW)
         │    └─► Deduplication Filter (NEW)
         │
         ├──► Database Backup (scripts/backup_database.py - EXISTING)
         │
         ├──► Batch Ingestion (src/open_source_risk_model/cli/ingest.py - EXISTING)
         │    ├─► Progress Monitor (ENHANCED)
         │    └─► Ingestion Service (EXISTING)
         │
         ├──► Data Quality Validator (scripts/validate_expansion.py - NEW)
         │    ├─► Count Validator
         │    ├─► Ecosystem Validator
         │    ├─► Resolution Validator
         │    ├─► Depth Calculator
         │    └─► Performance Benchmarker
         │
         ├──► Signal Quality Analyzer (scripts/analyze_insights.py - NEW)
         │    ├─► Hub Detector
         │    ├─► Depth Ranker
         │    ├─► Footprint Calculator
         │    └─► Pattern Detector
         │
         └──► Report Generator (scripts/generate_expansion_report.py - NEW)
              └─► Markdown/JSON Output
```


## Components and Interfaces

### 1. Expansion Orchestrator

**Purpose**: Coordinates the entire expansion process from selection through validation.

**Location**: `scripts/expand_dataset.py` (NEW)

**Interface**:
```python
def expand_dataset(
    target_count: int = 200,
    db_path: str = "data/graphs.db",
    backup_dir: str = "backups",
    output_dir: str = "data/expansion_reports",
    dry_run: bool = False
) -> ExpansionResult:
    """
    Orchestrate dataset expansion.
    
    Args:
        target_count: Target repository count (default: 200)
        db_path: Database path
        backup_dir: Backup directory
        output_dir: Report output directory
        dry_run: If True, only generate selection without ingesting
    
    Returns:
        ExpansionResult with status, metrics, and report path
    """
```

**Responsibilities**:
- Calculate number of repos to add (target - current)
- Invoke repository selector
- Create pre-expansion backup
- Execute batch ingestion with monitoring
- Run validation suite
- Generate expansion report
- Handle rollback on validation failure

### 2. Repository Selector (Enhanced)

**Purpose**: Generate prioritized list of repositories matching selection criteria.

**Location**: `scripts/populate_popular_repos.py` (ENHANCED)

**New Module**: `src/open_source_risk_model/expansion/repo_selector.py` (NEW)

**Interface**:
```python
class RepositorySelector:
    def __init__(self, github_token: str, db_path: str):
        """Initialize with GitHub API access and database connection."""
    
    def select_repositories(
        self,
        count: int,
        criteria: SelectionCriteria
    ) -> List[RepositoryCandidate]:
        """
        Select repositories matching criteria.
        
        Args:
            count: Number of repositories to select
            criteria: Selection criteria configuration
        
        Returns:
            List of repository candidates with metadata
        """
    
    def calculate_priority_score(
        self,
        repo: GitHubRepository
    ) -> float:
        """
        Calculate priority score for repository.
        
        Score = (stars_weight * normalized_stars) +
                (recency_weight * normalized_recency) +
                (prod_deps_weight * has_prod_deps) +
                (ecosystem_diversity_bonus)
        
        Returns:
            Priority score (0.0-1.0)
        """
    
    def is_duplicate(
        self,
        candidate: GitHubRepository,
        existing_repos: List[str]
    ) -> bool:
        """
        Check if candidate is fork or has similar name/owner.
        
        Note: Identical dependency graph detection requires ingestion,
        so it's deferred to post-ingestion analysis (see Property 37).
        
        Returns:
            True if duplicate fork or similar name, False otherwise
        """
    
    def infer_ecosystem(
        self,
        repo: GitHubRepository
    ) -> Tuple[str, List[str]]:
        """
        Infer primary ecosystem and all detected manifest types.
        
        Scans repo contents via GitHub Contents API for manifest filenames.
        Assigns primary ecosystem based on production manifest presence.
        
        Manifest→Ecosystem mapping:
        - package.json → npm
        - requirements.txt, setup.py, pyproject.toml → pypi
        - go.mod → go
        - pom.xml, build.gradle → maven
        - Gemfile → rubygems
        
        Returns:
            Tuple of (primary_ecosystem, all_manifest_types)
        """
```

**Selection Algorithm**:
1. Query GitHub API for repos with >1000 stars across target ecosystems
2. Filter out forks and existing repos
3. Infer ecosystem by scanning for manifest files via GitHub Contents API
4. Calculate priority score for each candidate
5. Apply ecosystem distribution constraints using quota-based selection
6. Sort by priority score
7. Select top N repos ensuring ecosystem targets

**Note on Duplicate Graph Detection**: Detecting identical dependency graphs requires full ingestion of each candidate repository. This is computationally expensive and would slow down selection significantly. Instead, we use selection-time heuristics (fork detection, name similarity) and defer comprehensive duplicate graph detection to post-ingestion analysis (see Property 37).


### 3. Data Quality Validator

**Purpose**: Verify expanded dataset meets all quality requirements.

**Location**: `scripts/validate_expansion.py` (NEW)

**Interface**:
```python
class DataQualityValidator:
    def __init__(self, db_path: str):
        """Initialize with database connection."""
    
    def validate_expansion(
        self,
        expected_repo_count: int = 200,
        min_resolution_rate: float = 0.85
    ) -> ValidationResult:
        """
        Run complete validation suite.
        
        Returns:
            ValidationResult with pass/fail status and detailed metrics
        """
    
    def validate_counts(self) -> CountValidation:
        """Validate repository and dependency counts."""
    
    def validate_ecosystem_distribution(self) -> EcosystemValidation:
        """Validate ecosystem percentages meet targets."""
    
    def validate_resolution_rate(self) -> ResolutionValidation:
        """Validate resolution rate meets threshold."""
    
    def validate_query_performance(self) -> PerformanceValidation:
        """Benchmark query performance across patterns."""
```

**Validation Checks**:
- Repository count == 200
- Dependency count in [15,000, 50,000]
- Resolution rate >= 85%
- Ecosystem count >= 5
- npm: 25-40%, PyPI: 25-40%, Go: ≥10%, Maven: ≥10%, RubyGems: ≥5%
- Query performance < 5 seconds for 10 query patterns

**Note on Dependency Depth**: Dependency depth calculation requires transitive dependency edges (package→package relationships). The current system only stores direct dependencies (repo→package edges) with `is_direct = True` always set. Transitive dependency ingestion is deferred to a future feature (Step 3). Therefore, dependency depth validation is removed from this spec.

### 4. Signal Quality Analyzer

**Purpose**: Identify cross-repository insights and validate signal quality.

**Location**: `scripts/analyze_insights.py` (NEW)

**Interface**:
```python
class SignalQualityAnalyzer:
    def __init__(self, db_path: str):
        """Initialize with database connection."""
    
    def analyze_insights(
        self,
        baseline_repo_count: int = 51
    ) -> InsightAnalysis:
        """
        Identify cross-repository insights.
        
        Returns:
            InsightAnalysis with discovered insights and metrics
        """
    
    def find_hub_packages(
        self,
        min_usage_pct: float = 0.25
    ) -> List[HubPackage]:
        """Find packages used by >25% of repositories."""
    
    def calculate_transitive_footprint(self) -> List[FootprintMetric]:
        """Calculate transitive dependency footprint per package."""
    
    def detect_ecosystem_patterns(self) -> List[EcosystemPattern]:
        """Detect ecosystem-specific dependency patterns."""
```

**Insight Types**:
1. Hub packages (used by >25% of repos)
2. Largest transitive footprints
3. Ecosystem-specific patterns (e.g., npm peer dependencies, Python extras)
4. Cross-ecosystem dependencies

**Note**: Depth-based insights removed because transitive dependency depth calculation requires package→package edges not yet available in the system.


### 5. Progress Monitor (Enhanced)

**Purpose**: Display real-time ingestion progress with detailed metrics.

**Location**: `src/open_source_risk_model/cli/ingest.py` (ENHANCED)

**Enhancements**:
- Add resolution rate to progress display
- Add ETA calculation
- Add failure reason display
- Update interval: 60 seconds minimum

**Display Format**:
```
[████████████████░░░░░░░░░░░░░░] 55.0% | 82/149 | ✅ owner/repo | ETA: 2h 15m
Success: 78 | Failed: 4 | Resolution: 87.3% | Deps: 12,450
```

### 6. Report Generator

**Purpose**: Generate comprehensive expansion summary report.

**Location**: `scripts/generate_expansion_report.py` (NEW)

**Interface**:
```python
def generate_expansion_report(
    expansion_result: ExpansionResult,
    validation_result: ValidationResult,
    insight_analysis: InsightAnalysis,
    output_path: str
) -> str:
    """
    Generate expansion report in Markdown format.
    
    Returns:
        Path to generated report
    """
```

**Report Sections**:
1. Executive Summary (repo count, dependency count, resolution rate)
2. Newly Added Repositories (list of 149 repos with metadata)
3. Failed Ingestions (if any)
4. Ecosystem Distribution (table with percentages)
5. Query Performance (before/after comparison with cold/warm cache metrics)
6. Cross-Repository Insights (5+ insights with metrics)
7. Duplicate Graph Detection (post-ingestion analysis)
8. Validation Status (pass/fail with details)

## Data Models

### RepositoryCandidate

```python
@dataclass
class RepositoryCandidate:
    """Repository candidate for selection."""
    full_name: str
    stars: int
    last_commit_date: datetime
    primary_ecosystem: str  # Primary ecosystem for distribution counting
    manifest_types: List[str]  # All detected manifest types
    has_prod_deps: bool
    is_fork: bool
    fork_parent: Optional[str]
    priority_score: float
    metadata: Dict[str, Any]
```

### SelectionCriteria

```python
@dataclass
class SelectionCriteria:
    """Criteria for repository selection."""
    min_stars: int = 1000
    min_commit_age_days: int = 180  # 6 months
    required_ecosystems: List[str] = field(default_factory=lambda: [
        'npm', 'pypi', 'go', 'maven', 'rubygems'
    ])
    ecosystem_targets: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'npm': (0.25, 0.40),
        'pypi': (0.25, 0.40),
        'go': (0.10, 1.0),
        'maven': (0.10, 1.0),
        'rubygems': (0.05, 1.0)
    })
    exclude_forks: bool = True
    exclude_duplicate_graphs: bool = True
```

### ValidationResult

```python
@dataclass
class ValidationResult:
    """Result of data quality validation."""
    passed: bool
    repo_count: int
    dependency_count: int
    resolution_rate: float
    ecosystem_distribution: Dict[str, float]
    performance_metrics: PerformanceMetrics
    failures: List[ValidationFailure]
    timestamp: datetime
```

### InsightAnalysis

```python
@dataclass
class InsightAnalysis:
    """Cross-repository insight analysis."""
    hub_packages: List[HubPackage]
    large_footprints: List[FootprintMetric]
    ecosystem_patterns: List[EcosystemPattern]
    new_insights_count: int
    baseline_comparison: Dict[str, Any]
```

**Note**: Depth-based insights (top_depth_repos) removed because transitive dependency depth calculation requires package→package edges not yet available in the system.

### ExpansionResult

```python
@dataclass
class ExpansionResult:
    """Result of dataset expansion."""
    success: bool
    repos_added: int
    repos_failed: int
    backup_path: str
    validation_result: ValidationResult
    insight_analysis: InsightAnalysis
    report_path: str
    duration_seconds: float
    timestamp: datetime
```


## Algorithms

### Repository Selection Algorithm

**Purpose**: Select N repositories that maximize value while meeting ecosystem distribution constraints.

**Algorithm**: Quota-Based Priority Selection with Explicit Quotas

```python
def select_repositories(count: int, criteria: SelectionCriteria) -> List[RepositoryCandidate]:
    """
    Select repositories using quota-based priority selection.
    
    For 149 new repos (to reach 200 total), explicit quotas:
    - npm: 38-60 repos (25-40% of 200 total)
    - pypi: 38-60 repos (25-40% of 200 total)
    - go: ≥15 repos (≥10% of 200 total)
    - maven: ≥15 repos (≥10% of 200 total)
    - rubygems: ≥8 repos (≥5% of 200 total)
    
    1. Query GitHub API for candidates
    2. Filter by basic criteria (stars, recency, forks)
    3. Infer ecosystem for each candidate
    4. Calculate priority scores
    5. Remove duplicates (forks, similar names)
    6. Apply quota-based ecosystem distribution
    7. Select top N by priority within constraints
    """
    
    # Phase 1: Query and filter
    candidates = query_github_repos(min_stars=criteria.min_stars)
    candidates = filter_by_recency(candidates, criteria.min_commit_age_days)
    candidates = filter_forks(candidates) if criteria.exclude_forks else candidates
    candidates = filter_existing_repos(candidates, db_path)
    
    # Phase 2: Infer ecosystems
    for candidate in candidates:
        primary_eco, manifests = infer_ecosystem(candidate)
        candidate.primary_ecosystem = primary_eco
        candidate.manifest_types = manifests
    
    # Phase 3: Score and deduplicate
    for candidate in candidates:
        candidate.priority_score = calculate_priority_score(candidate)
    
    candidates = remove_duplicate_forks_and_names(candidates, db_path)
    
    # Phase 4: Quota-based selection with explicit minimum quotas
    # Compute minimum quotas per ecosystem (using ceil to ensure integers)
    target_total = 200  # Final dataset size
    ecosystem_quotas = {
        'npm': {'min': 38, 'max': 60, 'current': 0},
        'pypi': {'min': 38, 'max': 60, 'current': 0},
        'go': {'min': 15, 'max': 200, 'current': 0},
        'maven': {'min': 15, 'max': 200, 'current': 0},
        'rubygems': {'min': 8, 'max': 200, 'current': 0}
    }
    
    selected = []
    
    # Sort by priority (descending)
    candidates.sort(key=lambda r: r.priority_score, reverse=True)
    
    # Phase 4a: Fill minimum quotas first
    for ecosystem in criteria.required_ecosystems:
        ecosystem_candidates = [c for c in candidates if c.primary_ecosystem == ecosystem]
        min_quota = ecosystem_quotas[ecosystem]['min']
        
        for candidate in ecosystem_candidates[:min_quota]:
            if candidate not in selected:
                selected.append(candidate)
                ecosystem_quotas[ecosystem]['current'] += 1
    
    # Phase 4b: Fill remaining slots by overall priority respecting max constraints
    for candidate in candidates:
        if len(selected) >= count:
            break
        
        if candidate in selected:
            continue
        
        ecosystem = candidate.primary_ecosystem
        current = ecosystem_quotas.get(ecosystem, {}).get('current', 0)
        max_quota = ecosystem_quotas.get(ecosystem, {}).get('max', count)
        
        if current < max_quota:
            selected.append(candidate)
            ecosystem_quotas[ecosystem]['current'] += 1
    
    return selected
```

**Priority Score Calculation**:

```python
def calculate_priority_score(repo: GitHubRepository) -> float:
    """
    Calculate priority score (0.0-1.0).
    
    Score = 0.4 * stars_score + 
            0.3 * recency_score + 
            0.2 * prod_deps_score +
            0.1 * ecosystem_diversity_bonus
    """
    
    # Normalize stars (log scale)
    stars_score = min(1.0, math.log10(repo.stars) / 5.0)  # 100k stars = 1.0
    
    # Normalize recency (days since last commit)
    days_since_commit = (datetime.now() - repo.last_commit_date).days
    recency_score = max(0.0, 1.0 - (days_since_commit / 365.0))
    
    # Production dependencies bonus
    prod_deps_score = 1.0 if repo.has_prod_deps else 0.5
    
    # Ecosystem diversity bonus (underrepresented ecosystems get boost)
    current_distribution = get_current_ecosystem_distribution()
    target_pct = ECOSYSTEM_TARGETS.get(repo.ecosystem, (0.1, 0.4))[0]
    current_pct = current_distribution.get(repo.ecosystem, 0.0)
    ecosystem_diversity_bonus = max(0.0, target_pct - current_pct)
    
    score = (0.4 * stars_score + 
             0.3 * recency_score + 
             0.2 * prod_deps_score +
             0.1 * ecosystem_diversity_bonus)
    
    return score
```

### Ecosystem Inference Algorithm

**Purpose**: Determine primary ecosystem and all manifest types for a repository.

**Algorithm**: Bounded Manifest File Scanning with Caching

```python
def infer_ecosystem(repo: GitHubRepository) -> Tuple[str, List[str]]:
    """
    Infer primary ecosystem by scanning for manifest files.
    
    Uses GitHub Contents API with bounded search to prevent API rate explosion.
    Caches results to avoid re-hitting API on reruns.
    
    Three-phase approach:
    1. Check root-level manifests only (fast, 1 API call)
    2. If none found, check common subpaths allowlist (max 5 paths)
    3. Only if still none found, do deeper scan (hard cap: 10 API calls)
    """
    
    # Check cache first
    cache = load_ecosystem_cache()
    if repo.full_name in cache:
        return cache[repo.full_name]
    
    # Manifest file patterns
    manifest_patterns = {
        'npm': ['package.json'],
        'pypi': ['requirements.txt', 'setup.py', 'pyproject.toml'],
        'go': ['go.mod'],
        'maven': ['pom.xml', 'build.gradle', 'build.gradle.kts'],
        'rubygems': ['Gemfile']
    }
    
    detected_ecosystems = []
    
    # Phase 1: Check root-level manifests (1 API call)
    root_files = get_repo_root_files(repo)
    for ecosystem, patterns in manifest_patterns.items():
        for pattern in patterns:
            if pattern in root_files:
                detected_ecosystems.append(ecosystem)
                break
    
    # Phase 2: If none found, check common subpaths (max 5 API calls)
    if not detected_ecosystems:
        common_subpaths = ['/frontend', '/backend', '/packages', '/apps', '/src']
        for subpath in common_subpaths:
            try:
                subpath_files = get_repo_files(repo, subpath)
                for ecosystem, patterns in manifest_patterns.items():
                    for pattern in patterns:
                        if pattern in subpath_files:
                            detected_ecosystems.append(ecosystem)
                            break
                if detected_ecosystems:
                    break
            except FileNotFoundError:
                continue
    
    # Phase 3: Only if still none found, do deeper scan (hard cap: 10 API calls)
    if not detected_ecosystems:
        api_call_count = 0
        max_api_calls = 10
        
        for ecosystem, patterns in manifest_patterns.items():
            if api_call_count >= max_api_calls:
                break
            for pattern in patterns:
                if api_call_count >= max_api_calls:
                    break
                if search_file_in_repo(repo, pattern):
                    detected_ecosystems.append(ecosystem)
                    api_call_count += 1
                    break
    
    # Determine primary ecosystem
    # Priority: production manifests > development manifests
    production_priority = ['npm', 'pypi', 'go', 'maven', 'rubygems']
    
    primary = None
    for eco in production_priority:
        if eco in detected_ecosystems:
            primary = eco
            break
    
    if not primary and detected_ecosystems:
        primary = detected_ecosystems[0]
    
    # Cache result
    cache[repo.full_name] = (primary, detected_ecosystems)
    save_ecosystem_cache(cache)
    
    return primary, detected_ecosystems
```

### Duplicate Fork Detection

**Purpose**: Identify repositories that are forks or have similar names.

**Algorithm**: Fork and Name Similarity Heuristics

```python
def is_duplicate(candidate: GitHubRepository, existing_repos: List[str]) -> bool:
    """
    Check if candidate is fork or has similar name to existing repo.
    
    Note: Full dependency graph comparison requires ingestion and is
    deferred to post-ingestion analysis (see Property 37).
    """
    
    # Check if it's a fork
    if candidate.is_fork:
        return True
    
    # Check for name similarity with existing repos
    for existing in existing_repos:
        if is_similar_name(candidate.full_name, existing):
            return True
    
    return False

def is_similar_name(name1: str, name2: str) -> bool:
    """Check if two repo names are similar (same owner or very similar name)."""
    owner1, repo1 = name1.split('/')
    owner2, repo2 = name2.split('/')
    
    # Same owner and similar repo name
    if owner1 == owner2 and levenshtein_distance(repo1, repo2) < 3:
        return True
    
    # Exact repo name match (different owners)
    if repo1 == repo2:
        return True
    
    return False
```


### Hub Package Detection

**Purpose**: Identify packages used across many repositories.

**Algorithm**: Cross-Repository Dependency Analysis

```python
def find_hub_packages(db_path: str, min_usage_pct: float = 0.25) -> List[HubPackage]:
    """
    Find packages used by >25% of repositories.
    
    Query all dependencies, group by package, count unique repos.
    """
    
    conn = get_connection(db_path)
    
    # Get total repo count
    total_repos = conn.execute("SELECT COUNT(*) FROM repo_graphs").fetchone()[0]
    min_repos = int(total_repos * min_usage_pct)
    
    # Find packages used by many repos
    query = """
        SELECT package_name, registry_type, COUNT(DISTINCT repo_full_name) as repo_count
        FROM repo_dependencies
        GROUP BY package_name, registry_type
        HAVING repo_count >= ?
        ORDER BY repo_count DESC
    """
    
    results = conn.execute(query, (min_repos,)).fetchall()
    
    hubs = []
    for package_name, registry_type, repo_count in results:
        usage_pct = repo_count / total_repos
        hubs.append(HubPackage(
            package_name=package_name,
            registry_type=registry_type,
            repo_count=repo_count,
            usage_percentage=usage_pct
        ))
    
    return hubs
```

### Resolution Rate Calculation

**Purpose**: Calculate percentage of dependencies successfully resolved.

**Algorithm**: Three-Criteria Resolution Check

```python
def calculate_resolution_rate(db_path: str) -> float:
    """
    Calculate resolution rate using three-criteria definition.
    
    A dependency is resolved if:
    1. Package is matched to a registry (registry_type IS NOT NULL)
    2. Version is successfully parsed (specifier IS NOT NULL)
    3. Registry metadata is retrieved (resolved_repo IS NOT NULL AND resolution_confidence IS NOT NULL)
    
    Note: The resolved_repo column stores the GitHub repository that provides
    the package (e.g., "facebook/react" for npm package "react"). This proves
    the package was matched to the registry and metadata was retrieved.
    """
    
    conn = get_connection(db_path)
    
    # Total dependencies
    total = conn.execute("SELECT COUNT(*) FROM repo_dependencies").fetchone()[0]
    
    # Resolved dependencies (all three criteria met)
    resolved_query = """
        SELECT COUNT(*) FROM repo_dependencies
        WHERE registry_type IS NOT NULL
          AND registry_type != ''
          AND specifier IS NOT NULL
          AND resolved_repo IS NOT NULL
          AND resolution_confidence IS NOT NULL
    """
    resolved = conn.execute(resolved_query).fetchone()[0]
    
    return resolved / total if total > 0 else 0.0
```

### Query Performance Benchmarking

**Purpose**: Measure end-to-end query performance across different patterns.

**Algorithm**: Multi-Pattern Benchmark Suite

```python
def benchmark_query_performance(db_path: str) -> PerformanceMetrics:
    """
    Benchmark 10 query patterns and measure end-to-end execution time.
    
    Measures complete API time including Python overhead, not just SQL time.
    Includes warm/cold cache runs to account for SQLite page cache effects.
    
    Query patterns:
    1. Get dependencies for single repo
    2. Get dependents for popular package
    3. Find hub packages
    4. Cross-repo dependency search
    5. Ecosystem distribution query
    6. Resolution rate calculation
    7. Top packages by usage
    8. Transitive dependency lookup
    9. Multi-repo aggregate query
    10. Package metadata lookup
    """
    
    patterns = [
        ("single_repo_deps", lambda: get_dependencies("facebook/react", db_path)),
        ("package_dependents", lambda: get_dependents("express", "npm", db_path)),
        ("hub_packages", lambda: find_hub_packages(db_path)),
        ("cross_repo_search", lambda: search_dependencies("lodash", db_path)),
        ("ecosystem_dist", lambda: get_ecosystem_distribution(db_path)),
        ("resolution_rate", lambda: calculate_resolution_rate(db_path)),
        ("top_packages", lambda: get_top_packages(db_path, limit=100)),
        ("transitive_deps", lambda: get_transitive_dependencies("requests", "pypi", db_path)),
        ("aggregate_query", lambda: get_aggregate_stats(db_path)),
        ("package_metadata", lambda: get_package_metadata("lodash", "npm", db_path))
    ]
    
    results = {}
    
    # Run each pattern 3 times, report median + p95
    for pattern_name, query_func in patterns:
        durations = []
        
        # First run: cold cache (fresh connection)
        conn = get_fresh_connection(db_path)
        start = time.time()
        query_func()
        durations.append(time.time() - start)
        conn.close()
        
        # Subsequent runs: warm cache
        for _ in range(2):
            start = time.time()
            query_func()
            durations.append(time.time() - start)
        
        median = sorted(durations)[1]
        p95 = sorted(durations)[2]
        
        results[pattern_name] = {
            'median': median,
            'p95': p95,
            'cold': durations[0]
        }
    
    max_duration = max(r['p95'] for r in results.values())
    avg_duration = sum(r['median'] for r in results.values()) / len(results)
    
    return PerformanceMetrics(
        pattern_results=results,
        max_duration=max_duration,
        avg_duration=avg_duration,
        passed=max_duration < 5.0,
        measurement_note="End-to-end query time including Python overhead"
    )
```


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

**Important Design Decisions**:

1. **Duplicate Graph Detection Split**: Property 1.7 (duplicate graph exclusion) is split into two phases:
   - **Selection-time (Property 6)**: Uses heuristics (fork detection, name similarity) to filter obvious duplicates before ingestion
   - **Post-ingestion (Property 37)**: Computes actual dependency graphs after ingestion and reports duplicates
   - **Rationale**: Computing dependency graphs requires full ingestion, which is too expensive to do during selection

2. **Dependency Depth Validation Removed**: Requirements 5B.1-5B.5 (dependency depth validation) are removed from this spec:
   - **Current system limitation**: Database only stores repo→package (direct dependencies), not package→package (transitive dependencies)
   - **Code evidence**: `src/open_source_risk_model/persistence/dependency_repo.py` shows `is_direct = True` always, no lockfile storage
   - **Deferred to**: Future transitive dependency ingestion feature (Step 3)
   - **Properties removed**: Property 25 (depth threshold), Property 26 (depth metrics in report)

3. **Ecosystem Inference**: Added explicit ecosystem inference algorithm that scans manifest files via GitHub Contents API to handle multi-ecosystem repositories

4. **Query Performance Measurement**: Clarified that benchmarks measure end-to-end API time (including Python overhead) with cold/warm cache runs, not just SQL time

5. **Resolution Definition**: Clarified that `resolved_repo` column stores the GitHub repo providing the package, proving metadata retrieval

### Property Reflection

Before defining properties, I reviewed the prework analysis to eliminate redundancy:

**Redundancies Identified**:
1. Properties 5.5-5.9 (ecosystem percentage checks) can be combined into a single comprehensive ecosystem distribution property
2. Properties 5A.1-5A.3 (resolution criteria) can be combined into a single resolution definition property
3. Properties 5B.1-5B.2 (depth calculations) are removed - depth validation requires transitive edges not yet available
4. Properties 5B.3-5B.5 (depth validation and reporting) are removed - deferred to transitive dependency ingestion feature
5. Properties 8.1-8.5 (report content) can be combined into a single comprehensive report property
6. Properties 4.1-4.3 (monitor display fields) can be combined into a single monitor output property
7. Property 1.7 (duplicate graph exclusion) split into two phases: selection-time heuristics (Property 6) and post-ingestion detection (Property 37)

**Consolidated Properties**: After reflection and removal of unimplementable depth validation, 67 acceptance criteria reduce to 35 unique testable properties.

### Property 1: Star Threshold Filtering

For any repository candidate, if it is selected by the selection algorithm, then it must have more than 1000 GitHub stars.

**Validates: Requirements 1.1**

### Property 2: Ecosystem Diversity

For any repository selection of N repos, the selected set must include at least 5 different package ecosystems.

**Validates: Requirements 1.2**

### Property 3: Recency Prioritization

For any two repository candidates with equal star counts, the candidate with more recent commits (within last 6 months) must have a higher priority score.

**Validates: Requirements 1.3**

### Property 4: Production Dependency Prioritization

For any two repository candidates with equal stars and recency, the candidate with production dependencies must have a higher priority score than one with only development dependencies.

**Validates: Requirements 1.5**

### Property 5: Fork Exclusion

For any repository candidate that is a fork of an existing repository in the dataset, the candidate must be excluded from selection.

**Validates: Requirements 1.6**

### Property 6: Duplicate Fork Exclusion

For any repository candidate that is a fork of an existing repository in the dataset, the candidate must be excluded from selection.

**Validates: Requirements 1.6**

**Note**: This property covers selection-time duplicate detection (forks and name similarity). Comprehensive duplicate graph detection requires full ingestion and is covered by Property 37 (post-ingestion analysis).

### Property 7: Priority Ordering

For any list of selected repositories, the list must be sorted in descending order by priority score.

**Validates: Requirements 2.2**

### Property 8: Repository Metadata Completeness

For any repository in the selection output, the record must contain stars, ecosystem, and last_commit_date fields.

**Validates: Requirements 2.3**

### Property 9: Exponential Backoff on Rate Limits

For any sequence of rate limit errors, the delay between retry attempts must increase exponentially (delay_n = base_delay * 2^n).

**Validates: Requirements 2.4**

### Property 10: Existing Repository Exclusion

For any repository already present in the dataset, it must not appear in the selection output.

**Validates: Requirements 2.5**

### Property 11: Resolution Rate Threshold

For any completed ingestion, the resolution rate must be at least 85%.

**Validates: Requirements 3.3**

### Property 12: Error Logging and Continuation

For any repository ingestion failure, the pipeline must log the error and continue processing remaining repositories.

**Validates: Requirements 3.4**

### Property 13: Monitor Display Completeness

For any progress monitor output, it must display counts of processed, pending, and failed repositories, plus current resolution rate.

**Validates: Requirements 4.1, 4.2**

### Property 14: ETA Display

For any progress monitor output after the first repository, it must display an estimated time remaining value.

**Validates: Requirements 4.3**

### Property 15: Failure Reason Display

For any repository ingestion failure, the monitor must display the failure reason in its output.

**Validates: Requirements 4.4**

### Property 16: Monitor Update Frequency

For any ingestion lasting longer than 60 seconds, the monitor must update progress metrics at least once every 60 seconds.

**Validates: Requirements 4.5**

### Property 17: Dependency Count Range

For any completed expansion, the total dependency count must be between 15,000 and 50,000.

**Validates: Requirements 5.2**

### Property 18: Resolution Rate Validation

For any completed expansion, the resolution rate must be at least 85%.

**Validates: Requirements 5.3**

### Property 19: Ecosystem Count Threshold

For any completed expansion, the dataset must contain at least 5 different package ecosystems.

**Validates: Requirements 5.4**

### Property 20: Ecosystem Distribution Constraints

For any completed expansion, the ecosystem distribution must satisfy: npm ∈ [25%, 40%], PyPI ∈ [25%, 40%], Go ≥ 10%, Maven ≥ 10%, RubyGems ≥ 5%.

**Validates: Requirements 5.5, 5.6, 5.7, 5.8, 5.9**

### Property 21: Validation Failure Reporting

For any validation failure, the validator must generate a detailed failure report containing the failed check and actual values.

**Validates: Requirements 5.10**

### Property 22: Resolution Definition Consistency

For any dependency, it is counted as resolved if and only if: (1) package is matched to a registry, AND (2) version is successfully parsed, AND (3) registry metadata is retrieved.

**Validates: Requirements 5A.1, 5A.2, 5A.3**

### Property 23: Resolution Rate Calculation

For any dataset, the resolution rate must equal (count of resolved dependencies) / (total dependency count).

**Validates: Requirements 5A.4**

### Property 24: Resolution Failure Documentation

For any dependency that fails any of the three resolution criteria, the failure must be documented with the specific criterion that failed.

**Validates: Requirements 5A.5**

### Property 25: Query Performance Threshold

For any cross-repository dependency query, the execution time must be under 5 seconds.

**Validates: Requirements 6.1**

### Property 26: Performance Degradation Detection

For any query with execution time exceeding 5 seconds, the validator must flag performance degradation.

**Validates: Requirements 6.3**

### Property 27: Backup Creation

For any expansion start, a database backup must be created before ingestion begins.

**Validates: Requirements 7.1**

### Property 28: Backup Timestamp Naming

For any created backup, the filename must contain a timestamp identifier.

**Validates: Requirements 7.2**

### Property 29: Rollback Round-Trip

For any database state S, after backup, modification, and rollback, the restored state must equal S.

**Validates: Requirements 7.4**

### Property 30: Expansion Report Completeness

For any completed expansion, the report must contain: list of newly added repositories, final dependency count, resolution rate, failed repositories (if any), query performance metrics (before/after), and ecosystem distribution.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

### Property 33: Minimum Insights Threshold

For any completed expansion, at least 5 cross-repository insights not visible in the 51-repository dataset must be identified.

**Validates: Requirements 9.1**

### Property 34: Hub Package Detection

For any package used by more than 25% of repositories, it must be identified as a hub package.

**Validates: Requirements 9.2**

### Property 35: Insight Documentation

For any identified cross-repository insight, it must be documented with supporting metrics (usage count, percentage, or ranking).

**Validates: Requirements 9.6**

### Property 36: Insufficient Signal Detection

For any expansion where fewer than 5 cross-repository insights are found, the validator must flag insufficient signal quality.

**Validates: Requirements 9.7**

### Property 37: Post-Ingestion Duplicate Graph Detection

For any two repositories in the expanded dataset, if they have identical dependency graphs (same set of direct dependencies), this must be detected and reported in the expansion analysis.

**Validates: Requirements 1.7**

**Note**: This property is evaluated post-ingestion because computing dependency graphs requires full ingestion. Selection-time duplicate detection (Property 6) uses heuristics (fork detection, name similarity) to filter obvious duplicates before ingestion.


## Error Handling

### Error Categories

1. **GitHub API Errors**
   - Rate limiting (403, 429)
   - Authentication failures (401)
   - Repository not found (404)
   - Network timeouts

2. **Ingestion Errors**
   - Manifest parsing failures
   - Package resolution failures
   - Database write failures
   - Dependency graph cycles

3. **Validation Errors**
   - Count mismatches
   - Resolution rate below threshold
   - Ecosystem distribution violations
   - Performance degradation

4. **System Errors**
   - Disk space exhaustion
   - Database corruption
   - Backup failures
   - Out of memory

### Error Handling Strategies

**GitHub API Rate Limiting**:
- Detect rate limit errors (403, 429, "rate limit" in message)
- Implement exponential backoff: delay = base_delay * 2^attempt
- Add jitter (0-10% of delay) to avoid thundering herd
- Maximum 3 retry attempts per request
- Log rate limit events for monitoring

**Ingestion Failures**:
- Log error with repository name and failure reason
- Continue processing remaining repositories
- Track failed repos in database (repo_ingestion_runs table)
- Include failed repos in expansion report
- Do not fail entire expansion for individual repo failures

**Validation Failures**:
- Generate detailed failure report with actual vs expected values
- Offer rollback option to user
- Do not automatically rollback (user decision)
- Log validation failures for analysis
- Exit with non-zero status code

**Database Errors**:
- Wrap all database operations in try-catch
- Rollback transactions on error
- Log full stack trace for debugging
- Attempt backup restoration on corruption
- Fail fast on unrecoverable errors

### Rollback Procedure

```python
def rollback_expansion(backup_path: str, db_path: str) -> bool:
    """
    Rollback to pre-expansion state.
    
    1. Verify backup integrity
    2. Stop any running processes
    3. Restore database from backup
    4. Verify restored database
    5. Rebuild indexes
    6. Confirm rollback success
    """
    
    # Verify backup exists and is valid
    if not verify_backup_integrity(backup_path):
        raise ValueError(f"Backup integrity check failed: {backup_path}")
    
    # Restore database
    restore_database(backup_path, db_path)
    
    # Verify restoration
    conn = get_connection(db_path)
    repo_count = conn.execute("SELECT COUNT(*) FROM repo_graphs").fetchone()[0]
    
    if repo_count != 51:
        raise ValueError(f"Rollback verification failed: expected 51 repos, got {repo_count}")
    
    # Rebuild indexes
    rebuild_indexes(db_path)
    
    return True
```

### Logging Strategy

**Log Levels**:
- DEBUG: Detailed execution flow, API responses
- INFO: Progress updates, successful operations
- WARNING: Recoverable errors, rate limits, retries
- ERROR: Failed operations, validation failures
- CRITICAL: System failures, data corruption

**Log Locations**:
- Console: INFO and above (for user visibility)
- File: DEBUG and above (for debugging)
- Database: ERROR and above (for analysis)

**Log Format**:
```
2026-02-20 14:30:45 - expansion - INFO - Starting expansion to 200 repos
2026-02-20 14:30:46 - selector - INFO - Selected 149 candidates (avg score: 0.78)
2026-02-20 14:35:12 - ingestion - WARNING - Rate limit hit, backing off 60s
2026-02-20 15:42:33 - ingestion - ERROR - Failed to ingest owner/repo: manifest not found
2026-02-20 18:15:20 - validator - INFO - Validation passed: 200 repos, 87.3% resolution
```


## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests for comprehensive coverage:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property tests**: Verify universal properties across all inputs

Together, these approaches provide comprehensive coverage where unit tests catch concrete bugs and property tests verify general correctness.

### Unit Testing

**Focus Areas**:
- Specific examples of repository selection
- Edge cases (empty datasets, single ecosystem, exact threshold values)
- Error conditions (API failures, database errors, validation failures)
- Integration points (GitHub API, database, file system)
- Rollback scenarios

**Example Unit Tests**:
```python
def test_select_repositories_with_exact_count():
    """Test selection produces exactly requested count."""
    selector = RepositorySelector(github_token, db_path)
    result = selector.select_repositories(count=10, criteria=default_criteria)
    assert len(result) == 10

def test_validation_fails_on_low_resolution_rate():
    """Test validator detects resolution rate below threshold."""
    validator = DataQualityValidator(db_path)
    # Setup database with 80% resolution rate
    result = validator.validate_expansion()
    assert not result.passed
    assert "resolution rate" in result.failures[0].message

def test_rollback_restores_original_state():
    """Test rollback returns to pre-expansion state."""
    original_count = get_repo_count(db_path)
    backup_path = backup_database(db_path)
    # Modify database
    add_repos(db_path, 10)
    # Rollback
    rollback_expansion(backup_path, db_path)
    assert get_repo_count(db_path) == original_count
```

### Property-Based Testing

**Property Testing Library**: Use `hypothesis` for Python

**Configuration**: Minimum 100 iterations per property test

**Test Tagging**: Each property test must reference its design document property:
```python
# Feature: dataset-expansion-200-repos, Property 1: Star Threshold Filtering
@given(candidates=st.lists(repository_candidate()))
def test_star_threshold_filtering(candidates):
    """For any repository candidate, if selected, it must have >1000 stars."""
    ...
```

**Property Test Examples**:

```python
from hypothesis import given, strategies as st

# Feature: dataset-expansion-200-repos, Property 1: Star Threshold Filtering
@given(candidates=st.lists(repository_candidate(), min_size=1))
@settings(max_examples=100)
def test_star_threshold_filtering(candidates):
    """For any repository candidate, if selected, it must have >1000 stars."""
    selector = RepositorySelector(github_token, db_path)
    selected = selector.select_repositories(count=10, criteria=default_criteria)
    
    for repo in selected:
        assert repo.stars > 1000

# Feature: dataset-expansion-200-repos, Property 7: Priority Ordering
@given(candidates=st.lists(repository_candidate(), min_size=2))
@settings(max_examples=100)
def test_priority_ordering(candidates):
    """For any list of selected repositories, it must be sorted by priority score."""
    selector = RepositorySelector(github_token, db_path)
    selected = selector.select_repositories(count=len(candidates), criteria=default_criteria)
    
    scores = [repo.priority_score for repo in selected]
    assert scores == sorted(scores, reverse=True)

# Feature: dataset-expansion-200-repos, Property 9: Exponential Backoff on Rate Limits
@given(attempt=st.integers(min_value=0, max_value=5))
@settings(max_examples=100)
def test_exponential_backoff(attempt):
    """For any sequence of rate limit errors, delay must increase exponentially."""
    base_delay = 60
    delay = calculate_backoff_delay(attempt, base_delay)
    expected_min = base_delay * (2 ** attempt)
    expected_max = expected_min * 1.1  # 10% jitter
    
    assert expected_min <= delay <= expected_max

# Feature: dataset-expansion-200-repos, Property 20: Ecosystem Distribution Constraints
@given(repos=st.lists(repository_candidate(), min_size=200, max_size=200))
@settings(max_examples=100)
def test_ecosystem_distribution_constraints(repos):
    """For any completed expansion, ecosystem distribution must meet targets."""
    validator = DataQualityValidator(db_path)
    # Setup database with repos
    result = validator.validate_ecosystem_distribution()
    
    dist = result.distribution
    assert 0.25 <= dist.get('npm', 0) <= 0.40
    assert 0.25 <= dist.get('pypi', 0) <= 0.40
    assert dist.get('go', 0) >= 0.10
    assert dist.get('maven', 0) >= 0.10
    assert dist.get('rubygems', 0) >= 0.05

# Feature: dataset-expansion-200-repos, Property 22: Resolution Definition Consistency
@given(dependency=dependency_record())
@settings(max_examples=100)
def test_resolution_definition_consistency(dependency):
    """A dependency is resolved iff all three criteria are met."""
    has_registry = dependency.registry_type is not None and dependency.registry_type != ''
    has_version = dependency.specifier is not None
    has_metadata = dependency.resolved_repo is not None
    
    is_resolved = is_dependency_resolved(dependency)
    
    assert is_resolved == (has_registry and has_version and has_metadata)

# Feature: dataset-expansion-200-repos, Property 31: Rollback Round-Trip
@given(modifications=st.lists(st.text(), min_size=1, max_size=10))
@settings(max_examples=100)
def test_rollback_round_trip(modifications):
    """For any database state, backup -> modify -> rollback must restore original."""
    original_state = get_database_state(db_path)
    backup_path = backup_database(db_path)
    
    # Apply modifications
    for mod in modifications:
        apply_modification(db_path, mod)
    
    # Rollback
    rollback_expansion(backup_path, db_path)
    restored_state = get_database_state(db_path)
    
    assert original_state == restored_state
```

### Test Data Generators

**Hypothesis Strategies**:
```python
@st.composite
def repository_candidate(draw):
    """Generate random repository candidate."""
    return RepositoryCandidate(
        full_name=draw(st.text(min_size=5, max_size=50)),
        stars=draw(st.integers(min_value=0, max_value=100000)),
        last_commit_date=draw(st.datetimes()),
        ecosystem=draw(st.sampled_from(['npm', 'pypi', 'go', 'maven', 'rubygems'])),
        has_prod_deps=draw(st.booleans()),
        is_fork=draw(st.booleans()),
        fork_parent=draw(st.one_of(st.none(), st.text())),
        priority_score=draw(st.floats(min_value=0.0, max_value=1.0)),
        metadata={}
    )

@st.composite
def dependency_record(draw):
    """Generate random dependency record."""
    return {
        'package_name': draw(st.text(min_size=1, max_size=50)),
        'registry_type': draw(st.one_of(st.none(), st.sampled_from(['npm', 'pypi', 'go']))),
        'specifier': draw(st.one_of(st.none(), st.text())),
        'resolved_repo': draw(st.one_of(st.none(), st.text()))
    }
```

### Integration Testing

**End-to-End Test**:
```python
def test_full_expansion_workflow():
    """Test complete expansion from selection through validation."""
    # Start with 51-repo database
    setup_baseline_database(db_path, repo_count=51)
    
    # Run expansion
    result = expand_dataset(
        target_count=200,
        db_path=db_path,
        dry_run=False
    )
    
    # Verify results
    assert result.success
    assert result.repos_added == 149
    assert result.validation_result.passed
    assert result.validation_result.repo_count == 200
    assert result.validation_result.resolution_rate >= 0.85
    assert len(result.insight_analysis.hub_packages) >= 5
```

### Performance Testing

**Query Performance Benchmarks**:
- Run benchmark suite before and after expansion
- Verify all queries complete under 5 seconds
- Compare performance metrics
- Flag any degradation >20%

**Load Testing**:
- Test with 500+ repository candidates
- Verify selection algorithm scales
- Test concurrent ingestion (if implemented)
- Monitor memory usage during expansion

### Test Coverage Goals

- Unit test coverage: >80% of new code
- Property test coverage: All 36 correctness properties
- Integration test coverage: All major workflows
- Error path coverage: All error handling branches


## Implementation Approach

### Phase 1: Repository Selection (Week 1)

**Deliverables**:
- `src/open_source_risk_model/expansion/repo_selector.py` - Selection algorithm
- `src/open_source_risk_model/expansion/github_client.py` - GitHub API wrapper
- Enhanced `scripts/populate_popular_repos.py` - CLI for selection
- Unit tests and property tests for selection logic

**Tasks**:
1. Implement SelectionCriteria data model
2. Implement GitHub API client with rate limiting
3. Implement priority score calculation
4. Implement duplicate detection (fork and graph)
5. Implement ecosystem-constrained selection
6. Add CLI for generating repository list
7. Write tests (unit + property)

**Validation**:
- Generate list of 149 repos
- Verify all meet criteria (>1000 stars, recent commits)
- Verify ecosystem distribution targets
- Verify no forks or duplicates

### Phase 2: Ingestion and Monitoring (Week 2)

**Deliverables**:
- Enhanced progress monitor in `src/open_source_risk_model/cli/ingest.py`
- Database backup integration
- Ingestion orchestration script
- Tests for monitoring and error handling
- **Preflight validation on 10-repo subset**

**Tasks**:
1. Enhance progress monitor with resolution rate and ETA
2. Add failure reason display
3. Integrate backup creation before ingestion
4. Add error logging and continuation logic
5. **Add preflight validation: test ingestion on 10 repos before full 149-repo run**
6. Write tests for monitoring and error paths

**Validation**:
- Run ingestion on 20 test repos
- Verify progress display updates
- Verify error handling (inject failures)
- Verify backup creation
- **Preflight validation passes on 10-repo subset before proceeding**

### Phase 3: Validation Framework (Week 3)

**Deliverables**:
- `scripts/validate_expansion.py` - Validation suite
- `src/open_source_risk_model/expansion/validators.py` - Validation logic
- Tests for all validation checks

**Tasks**:
1. Implement count validators (repo, dependency)
2. Implement ecosystem distribution validator
3. Implement resolution rate validator
4. Implement query performance benchmarker (with cold/warm cache runs)
5. Add validation report generation
6. Write tests for all validators

**Validation**:
- Run validators on test database
- Verify all checks execute correctly
- Test with failing conditions
- Verify report generation

**Note**: Dependency depth validation removed because it requires transitive dependency edges not yet available in the system.

### Phase 4: Signal Quality Analysis (Week 4)

**Deliverables**:
- `scripts/analyze_insights.py` - Insight analysis
- `src/open_source_risk_model/expansion/insight_analyzer.py` - Analysis logic
- `src/open_source_risk_model/expansion/duplicate_detector.py` - Post-ingestion duplicate graph detection
- Tests for insight detection

**Tasks**:
1. Implement hub package detector
2. Implement transitive footprint calculator
3. Implement pattern detector (ecosystem-specific)
4. Implement post-ingestion duplicate graph detector
5. Add baseline comparison logic
6. Write tests for insight detection

**Validation**:
- Run analysis on 51-repo baseline
- Run analysis on 200-repo dataset
- Verify 5+ new insights discovered
- Verify metrics are accurate
- Verify duplicate graph detection works

**Note**: Depth-based insights removed because transitive dependency depth calculation requires package→package edges not yet available in the system.

### Phase 5: Reporting and Rollback (Week 5)

**Deliverables**:
- `scripts/generate_expansion_report.py` - Report generator
- Rollback procedure documentation
- End-to-end integration tests

**Tasks**:
1. Implement report generator (Markdown + JSON)
2. Add rollback command to orchestrator
3. Test rollback procedure
4. Write end-to-end integration test
5. Document expansion procedure
6. Create runbook for operations

**Validation**:
- Generate report from test expansion
- Verify all sections present
- Test rollback on test database
- Run full end-to-end test

### Phase 6: Production Expansion (Week 6)

**Deliverables**:
- Expanded 200-repo dataset
- Expansion report
- Updated documentation

**Tasks**:
1. Create production database backup
2. Run repository selection (149 repos)
3. Review and approve repository list
4. Execute batch ingestion (24 hours)
5. Run validation suite
6. Run signal quality analysis
7. Generate expansion report
8. Update documentation and demos

**Validation**:
- All validation checks pass
- Resolution rate >= 85%
- Query performance < 5 seconds
- 5+ new insights discovered
- Ecosystem distribution meets targets

### Rollback Plan

If validation fails during production expansion:

1. **Stop ingestion** (if still running)
2. **Review validation failures** - Determine if fixable
3. **Decision point**:
   - If fixable: Fix issues and re-run validation
   - If not fixable: Execute rollback
4. **Execute rollback**:
   ```bash
   python scripts/restore_database.py backups/graphs_TIMESTAMP.db
   ```
5. **Verify rollback**:
   ```bash
   python scripts/validate_expansion.py --expected-count 51
   ```
6. **Analyze failures** - Determine root cause
7. **Plan remediation** - Fix issues before retry

### Dependencies

**External**:
- GitHub API access (token required)
- Sufficient API rate limit (5000 requests/hour)
- Disk space for backup (~500MB)
- 24 hours for ingestion

**Internal**:
- Existing batch ingestion CLI
- Existing database schema
- Existing package resolvers
- Existing query API

### Risks and Mitigations

**Risk**: GitHub API rate limiting during selection
**Mitigation**: Implement exponential backoff, use authenticated requests (5000/hour limit)

**Risk**: Ingestion failures due to repository changes
**Mitigation**: Error logging and continuation, track failed repos, allow retry

**Risk**: Validation failures after 24-hour ingestion
**Mitigation**: Pre-validate on subset, rollback capability, clear failure reporting

**Risk**: Query performance degradation
**Mitigation**: Rebuild indexes after ingestion, benchmark before/after, optimize slow queries

**Risk**: Insufficient new insights
**Mitigation**: Careful repository selection for diversity, analyze baseline first

**Risk**: Ecosystem distribution violations
**Mitigation**: Constrained selection algorithm, validation before full ingestion

### Success Metrics

- 200 repositories ingested successfully
- Resolution rate >= 85%
- Query performance < 5 seconds (all patterns, p95)
- Ecosystem distribution meets all targets
- 5+ new cross-repository insights
- Zero data loss or corruption
- Successful rollback capability demonstrated
- Post-ingestion duplicate graph analysis completed

