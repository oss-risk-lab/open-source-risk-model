# Design: Transitive Dependency Resolution

## Architecture Overview

The resolution system inserts a new layer between dependency ingestion (which parses manifests into `repo_dependencies`) and the tree API (which renders trees). It reads direct dependencies, recursively resolves their transitive dependencies via ecosystem registry APIs, and stores the resulting parent-child graph in a new `resolved_dependencies` table.

```
[Manifest Parsing] → [repo_dependencies (direct only, unchanged)]
                              ↓ (read)
                    [TransitiveResolver]
                        ↓           ↓
              [Registry Clients]  [Resolution Cache]
                  (PyPI, npm)     (session + DB)
                        ↓
              [resolved_dependencies (parent-child graph)]
                              ↓ (read)
                    [TreeService] → [Tree API]
                    (prefers resolved data, falls back to flat)
```

Key architectural constraint: `repo_dependencies` is never modified by the resolution system. It remains the source of truth for manifest-declared direct dependencies. `resolved_dependencies` is a derived augmentation layer (Req 12.4, 13.4).

## Depth Convention

All components use a single consistent depth definition:

- **Depth 0**: The repository root. Exists as a `TreeNode` in the tree API response but is NOT stored as an edge in `resolved_dependencies`.
- **Depth 1**: Direct dependencies. Stored as edges where `parent_package = repo_full_name` and `parent_ecosystem = NULL`.
- **Depth 2**: First-level transitive dependencies. Children of direct deps.
- **Depth N**: (N-1)th transitive level.

This matches the existing `TreeNode.depth` convention in `src/open_source_risk_model/tree/models.py`. The `max_depth` configuration (default 5) means the resolver will not create edges with `depth > 5` (Req 4.3, 4.4).

## MVP Resolution Semantics

The transitive resolver is an approximation engine, not a package manager. This section documents what "resolution" means in the MVP context.

**Version selection heuristic:**
- PyPI: The resolver fetches `https://pypi.org/pypi/{package}/json` and uses the `info.version` field, which is the latest release. It does NOT evaluate the Declared_Specifier to select a version that satisfies the constraint. The Declared_Specifier is stored on the edge for provenance but not used for version solving.
- npm: The resolver fetches `https://registry.npmjs.org/{package}` and uses the version pointed to by `dist-tags.latest`. Same caveat — the Declared_Specifier is stored but not solved.

**What this means in practice:**
- The resolved graph shows "package X depends on package Y" relationships that are structurally correct (Y is a real dependency of X).
- The `resolved_version` on each edge is the latest version of the child package at resolution time, which may not be the version that would actually be installed given the parent's version constraint.
- The `declared_specifier` is preserved so post-MVP can implement proper constraint solving without schema changes.

**Environment markers (PyPI):**
- Dependencies gated on `extra ==` markers are excluded (they represent optional feature sets).
- Dependencies with environment markers (`sys_platform`, `python_version`, `os_name`, etc.) are included conservatively. The resolver does not evaluate markers against any target environment. This is a deliberate over-approximation: the graph may include dependencies that would not be installed on a specific platform, but it will not miss dependencies that would be installed on any platform. This trade-off favors completeness for risk analysis.

**npm dependency scopes:**
- Only `dependencies` are included. `devDependencies`, `peerDependencies`, and `optionalDependencies` are excluded (Req 3.4).

**Interpretation:** Users should treat the resolved graph as "what packages does this project transitively depend on, approximately?" rather than "what exact versions would pip/npm install in my environment?"

## source_registry Semantics

The `source_registry` field on `ResolutionEdge` stores **exclusively the ecosystem identifier string** (e.g., `"pypi"`, `"npm"`), never a full URL. This is a short, stable, filterable identifier. All code paths that set `source_registry` must use the ecosystem name — no URL is ever written to this field.

- For successfully resolved edges: `source_registry = client.ecosystem` (e.g., `"pypi"`)
- For error edges where the ecosystem is known: `source_registry = ecosystem` (e.g., `"pypi"`)
- For unsupported ecosystem edges: `source_registry = None`
- For cycle/depth-limit/budget edges: `source_registry = None`

The full registry URL used for the fetch is stored in `NormalizedPackageMetadata.source_url` within the cache, but is NOT propagated to the edge. If URL-level provenance is needed post-MVP, a dedicated `source_url` column can be added to the edge schema without breaking existing data. The `source_registry` field must never be repurposed for URLs.

## Data Models

### File: `src/open_source_risk_model/resolution/models.py`

All data structures used across the resolution module.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Valid resolution statuses (Req 5.4)
RESOLUTION_STATUSES = frozenset({
    "resolved",
    "error",
    "cycle_detected",
    "max_depth_reached",
    "unsupported_ecosystem",
    "budget_exhausted",
})

@dataclass(frozen=True)
class PackageIdentity:
    """Canonical identity for cycle detection and cache keys.
    Version is NOT part of identity for MVP because the resolver always
    resolves to the latest version and does not perform specifier-aware
    version solving. If post-MVP adds version-aware resolution, this
    must be revisited to include version."""
    ecosystem: str   # "pypi", "npm"
    name: str        # normalized package name


def make_node_key(
    ecosystem: str | None, name: str, version: str | None = None
) -> tuple[str | None, str] | tuple[str | None, str, str | None]:
    """Centralized identity key factory.

    MVP returns (ecosystem, name) — version is ignored because the
    resolver always resolves to latest.

    All call sites (cycle detection, cache keys, tree reconstruction
    grouping, branch_visited guards) MUST use this function instead of
    constructing raw tuples. When post-MVP adds version-aware resolution,
    this single function is the only place that needs to change to
    return (ecosystem, name, version).
    """
    # MVP: version excluded from identity
    return (ecosystem, name)

@dataclass
class DependencyDeclaration:
    """A single dependency as declared by a parent package."""
    name: str
    specifier: Optional[str] = None  # Declared_Specifier, e.g. ">=1.0,<2.0"

@dataclass
class NormalizedPackageMetadata:
    """Structured result of a registry lookup.
    This is what the Resolution_Cache stores (Req 6.1)."""
    name: str
    version: str                          # Resolved_Version
    ecosystem: str
    dependencies: list[DependencyDeclaration]  # declared deps of this package
    source_url: str                       # full registry URL used for fetch
    fetched_at: str                       # ISO 8601 timestamp

@dataclass
class ResolutionEdge:
    """A single parent→child edge in the resolved graph (Req 4.2, 7.2).
    Carries both declared specifier and resolved version (Req 2.3, 3.3).
    Parent identity includes ecosystem + package name (Req 7.3)."""
    repo_full_name: str
    parent_ecosystem: Optional[str]  # NULL for depth-1 edges (parent is repo)
    parent_package: str              # repo_full_name for depth-1 edges
    child_ecosystem: Optional[str]
    child_package: str
    declared_specifier: Optional[str]  # what the parent declared
    resolved_version: Optional[str]    # concrete version from registry
    depth: int                         # Node_Depth: 1=direct, 2=first transitive
    resolution_status: str = "resolved"
    error_reason: Optional[str] = None
    source_registry: Optional[str] = None  # ecosystem name, e.g. "pypi"
    resolved_at: str = ""              # ISO 8601, set by resolver

@dataclass
class ResolutionSummary:
    """Run-level summary returned by the resolver (Req 11.5)."""
    repo_full_name: str
    total_edges: int = 0
    resolved_count: int = 0
    error_count: int = 0
    cycle_count: int = 0
    max_depth_reached_count: int = 0
    unsupported_ecosystem_count: int = 0
    budget_exhausted_count: int = 0
    actual_max_depth: int = 0
    api_calls_made: int = 0
    cache_hits: int = 0
    elapsed_seconds: float = 0.0
    edges_per_depth: dict[int, int] = field(default_factory=dict)  # depth → edge count

    @classmethod
    def from_edges(cls, repo: str, edges: list[ResolutionEdge],
                   api_calls: int, cache_hits: int,
                   elapsed: float) -> ResolutionSummary:
        summary = cls(repo_full_name=repo, total_edges=len(edges),
                      api_calls_made=api_calls, cache_hits=cache_hits,
                      elapsed_seconds=elapsed)
        for e in edges:
            match e.resolution_status:
                case "resolved": summary.resolved_count += 1
                case "error": summary.error_count += 1
                case "cycle_detected": summary.cycle_count += 1
                case "max_depth_reached": summary.max_depth_reached_count += 1
                case "unsupported_ecosystem": summary.unsupported_ecosystem_count += 1
                case "budget_exhausted": summary.budget_exhausted_count += 1
            summary.actual_max_depth = max(summary.actual_max_depth, e.depth)
            summary.edges_per_depth[e.depth] = summary.edges_per_depth.get(e.depth, 0) + 1
        return summary
```

## Component Design

### 1. Registry Client Interface

**File**: `src/open_source_risk_model/resolution/registry_client.py`
**Implements**: Req 1

```python
from abc import ABC, abstractmethod

class RegistryClient(ABC):
    """Abstract interface for ecosystem registry clients."""

    @property
    @abstractmethod
    def ecosystem(self) -> str:
        """Return ecosystem identifier (e.g. 'pypi', 'npm')."""

    @abstractmethod
    def get_package_metadata(
        self, name: str, specifier: str | None = None
    ) -> NormalizedPackageMetadata | None:
        """Fetch package metadata from registry.
        Returns None if package not found or request failed.
        The specifier parameter is accepted for interface completeness
        but NOT used for version selection in MVP — always fetches
        latest. Stored on the edge as declared_specifier for provenance."""
```

Design notes:
- `specifier` is accepted but ignored for version selection in MVP (see "MVP Resolution Semantics" section). It flows through to `ResolutionEdge.declared_specifier`.
- Returns `None` for any failure (404, timeout, network error). The caller (Resolver) decides the `resolution_status`.
- No retry logic in MVP (Req 2.9, 3.9).

### 2. PyPI Registry Client

**File**: `src/open_source_risk_model/resolution/pypi_client.py`
**Implements**: Req 2

```python
import logging
import requests
from datetime import datetime, timezone
from .registry_client import RegistryClient
from .models import NormalizedPackageMetadata, DependencyDeclaration

logger = logging.getLogger(__name__)
PYPI_BASE_URL = "https://pypi.org/pypi"
REQUEST_TIMEOUT_SECONDS = 10

class PyPIClient(RegistryClient):
    @property
    def ecosystem(self) -> str:
        return "pypi"

    def get_package_metadata(self, name, specifier=None):
        url = f"{PYPI_BASE_URL}/{name}/json"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code == 404:          # Req 2.6
                return None
            if resp.status_code != 200:          # Req 2.7
                logger.warning("PyPI returned %d for %s", resp.status_code, name)
                return None
            data = resp.json()
            version = data["info"]["version"]    # Req 2.2: latest version
            deps = self._parse_requires_dist(
                data["info"].get("requires_dist") or []
            )
            return NormalizedPackageMetadata(
                name=name, version=version, ecosystem="pypi",
                dependencies=deps, source_url=url,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
        except (requests.RequestException, ValueError) as exc:  # Req 2.8
            logger.warning("PyPI request failed for %s: %s", name, exc)
            return None
        # No retry (Req 2.9)
```

```python
    def _parse_requires_dist(self, requires_dist: list[str]) -> list[DependencyDeclaration]:
        """Parse PEP 508 dependency specifiers from requires_dist.

        Filtering rules (see "MVP Resolution Semantics" for rationale):
        - EXCLUDE entries containing 'extra ==' markers (Req 2.4).
          These are optional feature-set dependencies (e.g., requests[security]).
        - INCLUDE entries with environment markers like sys_platform,
          python_version, os_name (Req 2.5). This is a deliberate
          over-approximation: the resolver does not evaluate markers
          against any target environment. The graph may include deps
          that would not be installed on a specific platform, but will
          not miss deps installed on any platform.
        """
        deps = []
        for entry in requires_dist:
            if "extra ==" in entry or "extra==" in entry:
                continue
            name, specifier = _parse_pep508_entry(entry)
            deps.append(DependencyDeclaration(name=name, specifier=specifier))
        return deps
```

PEP 508 parsing strategy: Use the `packaging` library's `Requirement` class if available, otherwise a simple regex that splits on `;` (to detect markers) and extracts name + version specifier. The `packaging` library is already a transitive dependency of `pip` and `setuptools`.

### 3. npm Registry Client

**File**: `src/open_source_risk_model/resolution/npm_client.py`
**Implements**: Req 3

```python
import logging
import urllib.parse
import requests
from datetime import datetime, timezone
from .registry_client import RegistryClient
from .models import NormalizedPackageMetadata, DependencyDeclaration

logger = logging.getLogger(__name__)
NPM_BASE_URL = "https://registry.npmjs.org"
REQUEST_TIMEOUT_SECONDS = 10

class NpmClient(RegistryClient):
    @property
    def ecosystem(self) -> str:
        return "npm"

    def get_package_metadata(self, name, specifier=None):
        # Handle scoped packages: @scope/name → URL-encoded (Req 3.5)
        encoded = urllib.parse.quote(name, safe="")
        url = f"{NPM_BASE_URL}/{encoded}"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code == 404:          # Req 3.6
                return None
            if resp.status_code != 200:          # Req 3.7
                logger.warning("npm returned %d for %s", resp.status_code, name)
                return None
            data = resp.json()
            # Resolve via dist-tags.latest (Req 3.1, 3.2)
            latest_tag = data.get("dist-tags", {}).get("latest")
            if not latest_tag:
                return None
            version_data = data.get("versions", {}).get(latest_tag, {})
            # Production dependencies only (Req 3.4)
            raw_deps = version_data.get("dependencies", {})
            deps = [
                DependencyDeclaration(name=dep_name, specifier=dep_spec)
                for dep_name, dep_spec in sorted(raw_deps.items())
            ]
            return NormalizedPackageMetadata(
                name=name, version=latest_tag, ecosystem="npm",
                dependencies=deps, source_url=url,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
        except (requests.RequestException, ValueError, KeyError) as exc:  # Req 3.8
            logger.warning("npm request failed for %s: %s", name, exc)
            return None
        # No retry (Req 3.9)
```

### 4. Registry Factory

**File**: `src/open_source_risk_model/resolution/registry_factory.py`
**Implements**: Req 1.3, 1.4

```python
_CLIENTS = {
    "pypi": PyPIClient,
    "npm": NpmClient,
}

def get_registry_client(ecosystem: str) -> RegistryClient | None:
    """Return client for ecosystem, or None if unsupported (Req 1.4)."""
    cls = _CLIENTS.get(ecosystem)
    return cls() if cls else None
```

Returns `None` for unsupported ecosystems (Ruby, Rust, Go, Java). The Resolver records these as `unsupported_ecosystem` edges (Req 5.2).

### 5. Resolution Cache

**File**: `src/open_source_risk_model/resolution/cache.py`
**Implements**: Req 6, 15.2

Two-tier cache: in-memory session dict + SQLite `package_metadata_cache` table.

**Cache key**: `(ecosystem, package_name)`. Version is NOT part of the cache key. This is sufficient for MVP because the resolver always fetches the latest version and does not perform specifier-aware version solving. If post-MVP adds version-aware resolution (resolving different versions of the same package for different consumers), the cache key must be extended to include version or specifier context.

**Cache contents**: The cache stores `NormalizedPackageMetadata` — the structured, parsed result of a registry lookup, including the package name, resolved version, ecosystem, dependency list, source URL, and fetch timestamp. For negative results (package not found), the cache stores a sentinel value. Raw registry responses are NOT cached.

```python
import json
import sqlite3
from datetime import datetime, timezone, timedelta

DEFAULT_TTL_HOURS = 168        # 7 days for positive results (Req 6.5)
NEGATIVE_TTL_HOURS = 1         # 1 hour for negative results (Req 6.6)

class ResolutionCache:
    """Two-tier cache for registry lookup results.

    HARD INVARIANT: The cache layer must NEVER trigger external API calls.
    It is a pure lookup/store abstraction. All registry calls must originate
    from the resolver after budget checks. There is no get_or_fetch() method.
    Any future contributor who adds a method that makes a registry call inside
    this class is violating the architectural contract.
    """

    def __init__(self, db_path: str, ttl_hours: int = DEFAULT_TTL_HOURS):
        self.db_path = db_path
        self.ttl = timedelta(hours=ttl_hours)
        self.negative_ttl = timedelta(hours=NEGATIVE_TTL_HOURS)
        self._session: dict[tuple[str, str], NormalizedPackageMetadata | None] = {}
        self._ensure_table()

    def lookup(self, ecosystem: str, name: str) -> tuple[
        NormalizedPackageMetadata | None, bool
    ]:
        """Check both cache tiers for a package.
        Returns (metadata_or_none, was_found).
        was_found=True means a cache entry exists (even if metadata is None
        for a negative cache hit). was_found=False means cache miss."""
        key = (ecosystem, name)

        # Tier 1: session cache (Req 6.2)
        if key in self._session:
            return self._session[key], True

        # Tier 2: DB cache (Req 6.3)
        db_result = self._read_db_cache(key)
        if db_result is not _CACHE_MISS:
            self._session[key] = db_result
            return db_result, True

        return None, False

    def store(self, ecosystem: str, name: str,
              metadata: NormalizedPackageMetadata | None) -> None:
        """Write to both session and DB cache (Req 6.4).
        metadata=None stores a negative cache entry with shorter TTL (Req 6.6)."""
        key = (ecosystem, name)
        self._session[key] = metadata
        self._write_db_cache(key, metadata)
```

**Database cache table** (Req 15.2):

```sql
CREATE TABLE IF NOT EXISTS package_metadata_cache (
    ecosystem     TEXT NOT NULL,
    package_name  TEXT NOT NULL,
    metadata_json TEXT NOT NULL,   -- serialized NormalizedPackageMetadata or "null"
    fetched_at    TEXT NOT NULL,   -- ISO 8601
    expires_at    TEXT NOT NULL,   -- ISO 8601
    PRIMARY KEY (ecosystem, package_name)
);
```

- Positive results: `expires_at = fetched_at + 168h`
- Negative results (`metadata_json = "null"`): `expires_at = fetched_at + 1h`
- Expiry check: `WHERE ecosystem=? AND package_name=? AND expires_at > datetime('now')`

### 6. Budget Tracker

**File**: `src/open_source_risk_model/resolution/budget_tracker.py`
**Implements**: Req 9

```python
import time
from dataclasses import dataclass, field

@dataclass
class BudgetConfig:
    global_budget: int = 200           # Req 9.1
    per_ecosystem: dict[str, int] = field(default_factory=dict)  # Req 9.4
    min_delay_ms: int = 100            # Req 9.5

class BudgetTracker:
    def __init__(self, config: BudgetConfig):
        self.config = config
        self._global_used: int = 0
        self._per_ecosystem_used: dict[str, int] = {}
        self._last_call_time: dict[str, float] = {}

    def can_make_call(self, ecosystem: str) -> bool:
        """Check if budget allows another API call for this ecosystem."""
        if ecosystem in self.config.per_ecosystem:
            eco_used = self._per_ecosystem_used.get(ecosystem, 0)
            if eco_used >= self.config.per_ecosystem[ecosystem]:
                return False
        else:
            if self._global_used >= self.config.global_budget:
                return False
        return True

    def record_call(self, ecosystem: str) -> None:
        """Record an API call — successful or failed (Req 9.2)."""
        self._global_used += 1
        self._per_ecosystem_used[ecosystem] = (
            self._per_ecosystem_used.get(ecosystem, 0) + 1
        )

    def wait_if_needed(self, ecosystem: str) -> None:
        """Enforce minimum delay between calls to same ecosystem (Req 9.5)."""
        last = self._last_call_time.get(ecosystem, 0)
        elapsed_ms = (time.monotonic() - last) * 1000
        if elapsed_ms < self.config.min_delay_ms:
            time.sleep((self.config.min_delay_ms - elapsed_ms) / 1000)
        self._last_call_time[ecosystem] = time.monotonic()

    @property
    def api_calls_made(self) -> int:
        return self._global_used
```

Simple counter + delay, not a token-bucket. Token-bucket is overkill for MVP where we need a hard cap per run and a minimum inter-call delay.

### 7. Transitive Resolver (Core Algorithm)

**File**: `src/open_source_risk_model/resolution/resolver.py`
**Implements**: Req 4, 5, 8, 9, 14

This is the central component. It reads direct deps from `repo_dependencies`, recursively resolves via registry clients, and produces a list of `ResolutionEdge` records. The resolver orchestrates the cache, budget tracker, and registry clients.

#### Authoritative Cache/Budget/Fetch Flow

There is exactly one flow for obtaining package metadata. The resolver owns this flow; the cache is a pure lookup/store layer and never makes registry calls.

```
1. cache.lookup(ecosystem, name)
   → found=True?  return cached result (cache hit, no budget cost)
2. budget.can_make_call(ecosystem)?
   → False?  record budget_exhausted edge, return
3. budget.wait_if_needed(ecosystem)       # enforce inter-call delay
4. metadata = client.get_package_metadata(name, specifier)
5. budget.record_call(ecosystem)          # counts even if call failed
6. cache.store(ecosystem, name, metadata) # store result (including None)
7. proceed with metadata (or record error edge if None)
```

Cache hits do not count against the budget (Req 9.1). Failed API calls do count (Req 9.2).

```python
import logging
import time
import sqlite3
from datetime import datetime, timezone

from .models import PackageIdentity, ResolutionEdge, ResolutionSummary
from .cache import ResolutionCache
from .budget_tracker import BudgetTracker, BudgetConfig
from .registry_factory import get_registry_client
from ..persistence.db import get_connection

logger = logging.getLogger(__name__)

class TransitiveResolver:
    def __init__(
        self,
        db_path: str = "data/graphs.db",
        max_depth: int = 5,
        budget_config: BudgetConfig | None = None,
        ecosystem_filter: set[str] | None = None,
    ):
        self.db_path = db_path
        self.max_depth = max_depth
        self.budget = BudgetTracker(budget_config or BudgetConfig())
        self.cache = ResolutionCache(db_path)
        self.ecosystem_filter = ecosystem_filter
        self._cache_hits = 0

    def resolve_repo(
        self, repo_full_name: str
    ) -> tuple[list[ResolutionEdge], ResolutionSummary]:
        """Resolve all transitive deps for a repo (Req 4.1)."""
        start = time.monotonic()
        direct_deps = self._get_direct_deps(repo_full_name)
        edges: list[ResolutionEdge] = []

        for dep in sorted(direct_deps, key=lambda d: d["package_name"]):
            ecosystem = dep.get("ecosystem", "unknown")
            if self.ecosystem_filter and ecosystem not in self.ecosystem_filter:
                continue
            branch_path: set[tuple] = set()  # Req 4.5: branch-local, uses make_node_key() tuples
            self._resolve_recursive(
                repo_full_name=repo_full_name,
                parent_ecosystem=None,
                parent_package=repo_full_name,
                child_name=dep["package_name"],
                child_ecosystem=ecosystem,
                declared_specifier=dep.get("version_spec"),
                depth=1,
                branch_path=branch_path,
                edges=edges,
            )

        elapsed = time.monotonic() - start
        summary = ResolutionSummary.from_edges(
            repo_full_name, edges,
            self.budget.api_calls_made, self._cache_hits, elapsed,
        )
        return edges, summary
```

```python
    def _resolve_recursive(
        self,
        repo_full_name: str,
        parent_ecosystem: str | None,
        parent_package: str,
        child_name: str,
        child_ecosystem: str,
        declared_specifier: str | None,
        depth: int,
        branch_path: set[tuple],
        edges: list[ResolutionEdge],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        child_identity = PackageIdentity(child_ecosystem, child_name)
        # Use make_node_key() for cycle detection — centralizes identity logic
        child_key = make_node_key(child_ecosystem, child_name)

        # --- Check 1: Max depth (Req 4.3) ---
        if depth > self.max_depth:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "max_depth_reached", None, None, now,
            ))
            return

        # --- Check 2: Cycle detection — branch-local (Req 4.5, 4.6) ---
        # Uses make_node_key() so identity is ecosystem-qualified
        if child_key in branch_path:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "cycle_detected", None, None, now,
            ))
            return

        # --- Check 3: Registry client availability (Req 5.2) ---
        client = get_registry_client(child_ecosystem)
        if client is None:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "unsupported_ecosystem", None, None, now,
            ))
            return

        # --- Step 4: Cache lookup (authoritative flow step 1) ---
        metadata, cache_found = self.cache.lookup(child_ecosystem, child_name)
        if cache_found:
            self._cache_hits += 1
            # Cache hit — skip budget, proceed directly
        else:
            # --- Step 5: Budget check (authoritative flow step 2) ---
            if not self.budget.can_make_call(child_ecosystem):
                edges.append(self._make_edge(
                    repo_full_name, parent_ecosystem, parent_package,
                    child_ecosystem, child_name, declared_specifier,
                    None, depth, "budget_exhausted", None,
                    child_ecosystem, now,
                ))
                return

            # --- Step 6: Delay + fetch + record (flow steps 3-6) ---
            self.budget.wait_if_needed(child_ecosystem)
            metadata = client.get_package_metadata(child_name, declared_specifier)
            self.budget.record_call(child_ecosystem)
            self.cache.store(child_ecosystem, child_name, metadata)

        # --- Check 7: Registry returned None (Req 5.1) ---
        if metadata is None:
            edges.append(self._make_edge(
                repo_full_name, parent_ecosystem, parent_package,
                child_ecosystem, child_name, declared_specifier,
                None, depth, "error", "Package not found in registry",
                child_ecosystem, now,
            ))
            return

        # --- Success: record resolved edge (Req 4.2, 8.1-8.3) ---
        edges.append(self._make_edge(
            repo_full_name, parent_ecosystem, parent_package,
            child_ecosystem, child_name, declared_specifier,
            metadata.version, depth, "resolved", None,
            child_ecosystem, now,
        ))

        # --- Recurse into sub-dependencies (Req 4.7) ---
        new_branch_path = branch_path | {child_key}  # uses make_node_key() result
        for sub_dep in sorted(metadata.dependencies, key=lambda d: d.name):
            self._resolve_recursive(
                repo_full_name=repo_full_name,
                parent_ecosystem=child_ecosystem,
                parent_package=child_name,
                child_name=sub_dep.name,
                child_ecosystem=child_ecosystem,  # same ecosystem as parent
                declared_specifier=sub_dep.specifier,
                depth=depth + 1,
                branch_path=new_branch_path,
                edges=edges,
            )
```

```python
    @staticmethod
    def _make_edge(repo, p_eco, p_pkg, c_eco, c_pkg, spec, ver,
                   depth, status, err, src, ts) -> ResolutionEdge:
        return ResolutionEdge(
            repo_full_name=repo, parent_ecosystem=p_eco,
            parent_package=p_pkg, child_ecosystem=c_eco,
            child_package=c_pkg, declared_specifier=spec,
            resolved_version=ver, depth=depth,
            resolution_status=status, error_reason=err,
            source_registry=src, resolved_at=ts,
        )

    def _get_direct_deps(self, repo_full_name: str) -> list[dict]:
        """Read direct deps from repo_dependencies table."""
        conn = get_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM repo_dependencies WHERE repo_full_name = ? "
                "ORDER BY package_name",
                (repo_full_name,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
```

**Critical design decisions in the resolver:**

1. **Branch_Path uses `make_node_key()` tuples, not a session-wide set.** Each recursive call gets `branch_path | {child_key}` — a new frozen snapshot per branch. The same package can appear in multiple branches and is resolved independently in each (Req 4.6, 4.7). Session-level fetch deduplication happens in the cache, not the cycle detector. Identity is ecosystem-qualified via `make_node_key()`.

2. **Cache is a pure lookup/store layer — hard invariant.** The cache MUST NEVER make registry calls. The resolver owns the authoritative flow: lookup → budget check → delay → fetch → record → store. There is no `get_or_fetch` method that could bypass budget checks. This is an architectural contract, not a suggestion.

3. **Sorting for determinism (Req 14).** Direct deps sorted by `package_name`. Sub-dependencies sorted by `name`. This ensures deterministic edge ordering across runs.

4. **`child_ecosystem` for sub-deps inherits from parent.** A PyPI package's dependencies are also PyPI packages. An npm package's dependencies are also npm packages. Cross-ecosystem dependencies don't exist in MVP.

### 8. Resolved Dependency Storage

**File**: `src/open_source_risk_model/resolution/storage.py`
**Implements**: Req 7, 12

#### Schema and Parent/Child Identity

The `resolved_dependencies` table stores edges with ecosystem-qualified parent and child identity. The reconstruction key for finding a parent's children is `(repo_full_name, parent_ecosystem, parent_package)`, not just `(repo_full_name, parent_package)`. This prevents name collisions across ecosystems — if a repo somehow had both a PyPI package and an npm package named "debug", their children would not be mixed.

For depth-1 edges (direct deps), `parent_package = repo_full_name` and `parent_ecosystem = NULL`. This is unambiguous because repo_full_name is in "owner/repo" format, which cannot collide with any package name.

**Why the schema is sufficient for unambiguous tree reconstruction:**

1. Direct children of the repo are found by: `WHERE parent_package = repo_full_name AND parent_ecosystem IS NULL`
2. Children of a transitive package are found by: `WHERE parent_package = pkg_name AND parent_ecosystem = pkg_ecosystem`
3. The surrogate `id` primary key allows duplicate parent-child pairs across branches (Req 12.2).
4. The `depth` column enables depth-ordered retrieval and max-depth queries.
5. Both `declared_specifier` and `resolved_version` are stored per-edge, preserving the distinction between what was requested and what was resolved.

```python
class ResolvedDependencyStorage:
    def __init__(self, db_path: str = "data/graphs.db"):
        self.db_path = db_path
        self.ensure_tables()

    def ensure_tables(self) -> None:
        """Create resolved_dependencies table and indexes (Req 12.1, 12.3)."""
        conn = get_connection(self.db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS resolved_dependencies (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name   TEXT NOT NULL,
                    parent_ecosystem TEXT,
                    parent_package   TEXT NOT NULL,
                    child_ecosystem  TEXT,
                    child_package    TEXT NOT NULL,
                    declared_specifier TEXT,
                    resolved_version TEXT,
                    depth            INTEGER NOT NULL,
                    resolution_status TEXT NOT NULL DEFAULT 'resolved',
                    error_reason     TEXT,
                    source_registry  TEXT,
                    resolved_at      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_resolved_deps_repo
                    ON resolved_dependencies(repo_full_name);
                CREATE INDEX IF NOT EXISTS idx_resolved_deps_parent
                    ON resolved_dependencies(
                        repo_full_name, parent_ecosystem, parent_package
                    );
                CREATE INDEX IF NOT EXISTS idx_resolved_deps_depth
                    ON resolved_dependencies(repo_full_name, depth);
            """)
            conn.commit()
        finally:
            conn.close()
```

Note: The `idx_resolved_deps_parent` index now includes `parent_ecosystem` to support the ecosystem-qualified reconstruction lookup.

```python
    def store_edges(self, repo_full_name: str,
                    edges: list[ResolutionEdge]) -> None:
        """Replace all edges for a repo in a single transaction (Req 7.1, 7.4)."""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "DELETE FROM resolved_dependencies WHERE repo_full_name = ?",
                (repo_full_name,),
            )
            conn.executemany(
                """INSERT INTO resolved_dependencies
                   (repo_full_name, parent_ecosystem, parent_package,
                    child_ecosystem, child_package, declared_specifier,
                    resolved_version, depth, resolution_status,
                    error_reason, source_registry, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (e.repo_full_name, e.parent_ecosystem, e.parent_package,
                     e.child_ecosystem, e.child_package, e.declared_specifier,
                     e.resolved_version, e.depth, e.resolution_status,
                     e.error_reason, e.source_registry, e.resolved_at)
                    for e in edges
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def get_edges(self, repo_full_name: str) -> list[ResolutionEdge]:
        """Retrieve edges ordered deterministically (Req 7.5, 14.2).
        Order matches reconstruction key: depth, parent_ecosystem, parent_package, child_package."""
        conn = get_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM resolved_dependencies
                   WHERE repo_full_name = ?
                   ORDER BY depth, parent_ecosystem, parent_package, child_package""",
                (repo_full_name,),
            ).fetchall()
            return [self._row_to_edge(r) for r in rows]
        finally:
            conn.close()

    def has_resolved_data(self, repo_full_name: str) -> bool:
        """True if at least one 'resolved' edge exists (Req 7.6, 10.1)."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                """SELECT 1 FROM resolved_dependencies
                   WHERE repo_full_name = ? AND resolution_status = 'resolved'
                   LIMIT 1""",
                (repo_full_name,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def get_oldest_resolved_at(self, repo_full_name: str) -> str | None:
        """Oldest resolved_at timestamp for staleness display (Req 15)."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT MIN(resolved_at) FROM resolved_dependencies "
                "WHERE repo_full_name = ?",
                (repo_full_name,),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def delete_resolved(self, repo_full_name: str) -> int:
        """Delete all resolved edges for a repo. Returns count deleted."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM resolved_dependencies WHERE repo_full_name = ?",
                (repo_full_name,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
```

### 9. Tree Service Integration

**File**: Modify `src/open_source_risk_model/tree/service.py`
**Implements**: Req 10, 14.3

The existing `_build_canonical_tree` method is extended with a resolved-data path. The fallback to flat `repo_dependencies` data is preserved (Req 10.3).

```python
def _build_canonical_tree(self, repo_full_name: str) -> Tuple[TreeNode, str]:
    """Build the full canonical tree.
    Prefers resolved transitive data when available (Req 10.1-10.3)."""

    storage = ResolvedDependencyStorage(self.db_path)
    if storage.has_resolved_data(repo_full_name):
        edges = storage.get_edges(repo_full_name)
        root = self._build_tree_from_resolved(repo_full_name, edges)
        all_nodes = list(walk_tree(root))
        RiskMetadataEnricher.enrich_nodes(all_nodes, self.db_path)
        return root, "database"

    # Fall back to existing flat tree logic (Req 10.3)
    # ... existing code unchanged ...
```

#### Tree Reconstruction from Resolved Edges

**Reconstruction key**: Children of a parent are found by matching `(parent_ecosystem, parent_package)`, not just `parent_package`. This prevents cross-ecosystem name collisions from attaching children to the wrong parent.

**Separate node occurrences across branches**: The reconstruction creates a new `TreeNode` instance for every edge. If package "urllib3" appears as a transitive dependency of both "requests" and "botocore", it produces two separate TreeNode instances in the tree — one under each parent. There is no deduplication of nodes across branches. This is intentional: the tree is a tree (not a DAG), and each branch is independent (Req 4.7, 10.2c).

```python
def _build_tree_from_resolved(
    self, repo_full_name: str, edges: list[ResolutionEdge]
) -> TreeNode:
    """Build multi-level tree from resolved edges (Req 10.2)."""
    root = TreeNode(
        id=repo_full_name,
        node_type="repository",
        name=repo_full_name,
        depth=0,
        dependency_type="direct",
    )

    # Group edges by make_node_key(parent_ecosystem, parent_package) for lookup.
    # Uses make_node_key() so identity logic is centralized and can later
    # expand to include version without changing call sites.
    children_by_parent: dict[
        tuple[str | None, str], list[ResolutionEdge]
    ] = {}
    for edge in edges:
        key = make_node_key(edge.parent_ecosystem, edge.parent_package)
        children_by_parent.setdefault(key, []).append(edge)

    # Direct children: parent is repo (ecosystem=None, package=repo_full_name)
    direct_edges = children_by_parent.get(make_node_key(None, repo_full_name), [])
    for edge in sorted(direct_edges, key=lambda e: e.child_package):
        child = self._edge_to_node(
            edge, children_by_parent, branch_visited=set()
        )
        root.children.append(child)

    return root
```

```python
def _edge_to_node(
    self,
    edge: ResolutionEdge,
    children_by_parent: dict[tuple[str | None, str], list[ResolutionEdge]],
    branch_visited: set[tuple[str | None, str]],
) -> TreeNode:
    """Convert a ResolutionEdge to a TreeNode, recursively attaching children.

    branch_visited tracks make_node_key() tuples (ecosystem, package_name)
    along the current reconstruction path to prevent infinite loops. This is
    a safety guard — the stored edges should already have cycle_detected
    statuses, but we defend against data inconsistencies. Uses make_node_key()
    so identity is consistent with the resolver's cycle detection.

    Each call creates a NEW TreeNode instance. No deduplication across
    branches — the same package under different parents produces separate
    nodes (Req 4.7, 10.2c).
    """
    canonical_id = _make_canonical_id(
        edge.child_ecosystem, edge.child_package, edge.resolved_version
    )

    # Map resolution_status to TreeNode fields (Req 10.4)
    node_status, error_reason = self._map_resolution_status(edge)
    dep_type = "direct" if edge.depth == 1 else "transitive"

    node = TreeNode(
        id=canonical_id,
        node_type="package",
        name=edge.child_package,
        version=edge.resolved_version,       # Resolved_Version (Req 10.6)
        depth=edge.depth,
        dependency_type=dep_type,
        ecosystem=edge.child_ecosystem,
        specifier=edge.declared_specifier,    # Declared_Specifier (Req 10.6)
        resolution_status=node_status,
        error_reason=error_reason,
    )

    # Terminal statuses: no children
    if edge.resolution_status in (
        "error", "cycle_detected", "max_depth_reached",
        "budget_exhausted", "unsupported_ecosystem",
    ):
        return node

    # Safety guard against reconstruction loops — uses make_node_key()
    # to ensure identity is consistent with resolver's cycle detection
    visit_key = make_node_key(edge.child_ecosystem, edge.child_package, edge.resolved_version)
    if visit_key in branch_visited:
        return node
    new_visited = branch_visited | {visit_key}

    # Find children using ecosystem-qualified parent key via make_node_key() (Req 10.2b)
    child_key = make_node_key(edge.child_ecosystem, edge.child_package, edge.resolved_version)
    child_edges = children_by_parent.get(child_key, [])
    for child_edge in sorted(child_edges, key=lambda e: e.child_package):
        child_node = self._edge_to_node(
            child_edge, children_by_parent, new_visited
        )
        node.children.append(child_node)

    return node

@staticmethod
def _map_resolution_status(
    edge: ResolutionEdge,
) -> tuple[str, str | None]:
    """Map edge resolution_status to TreeNode fields (Req 10.4).

    unsupported_ecosystem maps to a visible non-success state so the
    frontend can display it honestly, not silently as "resolved"."""
    match edge.resolution_status:
        case "resolved":
            return "resolved", None
        case "error":
            return "error", edge.error_reason
        case "cycle_detected":
            return "cycle_detected", None
        case "max_depth_reached":
            return "max_depth_reached", None
        case "unsupported_ecosystem":
            return "unsupported_ecosystem", "Ecosystem not supported for resolution"
        case "budget_exhausted":
            return "budget_exhausted", "Resolution budget exhausted"
        case _:
            return "resolved", None
```

Note on `unsupported_ecosystem` mapping: The previous design mapped this to `"resolved"`, which would silently hide the fact that the package's transitive dependencies were not explored. The revised design maps it to `"unsupported_ecosystem"` with a visible reason string. The existing `TreeNode.resolution_status` field already supports arbitrary string values, and the `to_dict()` method includes non-"resolved" statuses in the output. The frontend can render these as informational leaf nodes.

Note on `budget_exhausted` mapping: Similarly mapped to its own status rather than generic "error", so the frontend can distinguish between "we couldn't find this package" and "we ran out of API budget."

### 10. CLI Command

**File**: `src/open_source_risk_model/cli/resolve.py`
**Implements**: Req 11, 15.4

```python
"""CLI command for transitive dependency resolution.

Usage:
    python -m open_source_risk_model.cli.resolve --repo owner/name
    python -m open_source_risk_model.cli.resolve --repo owner/name --max-depth 3
    python -m open_source_risk_model.cli.resolve --repo owner/name --ecosystems pypi
    python -m open_source_risk_model.cli.resolve --repo owner/name --force
    python -m open_source_risk_model.cli.resolve --repo owner/name --budget 100
"""
import argparse
import sys
import logging

from ..resolution.resolver import TransitiveResolver
from ..resolution.budget_tracker import BudgetConfig
from ..resolution.storage import ResolvedDependencyStorage

logger = logging.getLogger(__name__)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve transitive dependencies for a repository"
    )
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--ecosystems", help="Comma-separated ecosystem filter")
    parser.add_argument("--budget", type=int, default=200)
    parser.add_argument("--force", action="store_true",
                        help="Re-resolve even if data exists (Req 15.4)")
    parser.add_argument("--db-path", default="data/graphs.db")
    args = parser.parse_args()

    storage = ResolvedDependencyStorage(args.db_path)

    # Check for existing data (Req 15.4)
    if not args.force and storage.has_resolved_data(args.repo):
        oldest = storage.get_oldest_resolved_at(args.repo)
        print(f"Resolved data already exists for {args.repo} (since {oldest}).")
        print("Use --force to re-resolve.")
        return 0

    # Check direct deps exist (Req 11.6)
    resolver = TransitiveResolver(db_path=args.db_path)
    direct_deps = resolver._get_direct_deps(args.repo)
    if not direct_deps:
        print(f"No direct dependencies found for {args.repo}. "
              "Run dependency ingestion first.", file=sys.stderr)
        return 1

    # Resolve
    eco_filter = (
        set(args.ecosystems.split(",")) if args.ecosystems else None
    )
    budget_config = BudgetConfig(global_budget=args.budget)
    resolver = TransitiveResolver(
        db_path=args.db_path, max_depth=args.max_depth,
        budget_config=budget_config, ecosystem_filter=eco_filter,
    )
    edges, summary = resolver.resolve_repo(args.repo)

    # Store (Req 7.1)
    storage.store_edges(args.repo, edges)

    # Print summary (Req 11.5)
    print(f"\nResolution complete for {args.repo}")
    print(f"  Total edges:        {summary.total_edges}")
    print(f"  Resolved:           {summary.resolved_count}")
    print(f"  Errors:             {summary.error_count}")
    print(f"  Cycles:             {summary.cycle_count}")
    print(f"  Max depth reached:  {summary.max_depth_reached_count}")
    print(f"  Budget exhausted:   {summary.budget_exhausted_count}")
    print(f"  Unsupported eco:    {summary.unsupported_ecosystem_count}")
    print(f"  Max depth seen:     {summary.actual_max_depth}")
    print(f"  API calls:          {summary.api_calls_made}")
    print(f"  Cache hits:         {summary.cache_hits}")
    print(f"  Elapsed:            {summary.elapsed_seconds:.1f}s")
    if summary.edges_per_depth:
        print(f"  Edges per depth:    {dict(sorted(summary.edges_per_depth.items()))}")

    # Req 11.7: partial failures are normal, exit 0
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Exit code semantics (Req 11.7, 11.8):
- `0`: Resolution completed (even with errors, cycles, budget exhaustion)
- `1`: No direct deps found, invalid arguments, database errors

### 11. Ingestion Pipeline Integration

**File**: Modify `src/open_source_risk_model/dependencies/ingestion_service.py`
**Implements**: Req 13

Minimal change to the existing `ingest_repo` method:

```python
def ingest_repo(self, repo_full_name, refresh=False,
                resolve_packages=True, resolve_transitive=False):
    # ... existing ingestion logic (unchanged) ...
    result = ...  # existing IngestionResult

    # Optional transitive resolution (Req 13.1-13.4)
    if resolve_transitive and result.success and result.dependencies_found > 0:
        try:
            from ..resolution.resolver import TransitiveResolver
            from ..resolution.storage import ResolvedDependencyStorage
            resolver = TransitiveResolver(db_path=self.db_path)
            edges, summary = resolver.resolve_repo(repo_full_name)
            storage = ResolvedDependencyStorage(self.db_path)
            storage.store_edges(repo_full_name, edges)
            logger.info(
                "Transitive resolution for %s: %d edges, %d errors",
                repo_full_name, summary.total_edges, summary.error_count,
            )
        except Exception as exc:
            # Req 13.3: log and continue, don't abort ingestion
            logger.error("Transitive resolution failed for %s: %s",
                         repo_full_name, exc, exc_info=True)

    return result
```

The `resolve_transitive` flag defaults to `False` (Req 13.1). The `repo_dependencies` table is never touched by resolution (Req 13.4, 12.4).

## Database Schema Summary

Two new tables, zero modifications to existing tables.

### `resolved_dependencies` (Req 12)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Surrogate key (Req 12.2) |
| repo_full_name | TEXT | NOT NULL | FK-like to repo_graphs |
| parent_ecosystem | TEXT | nullable | NULL for depth-1 edges (parent is repo) |
| parent_package | TEXT | NOT NULL | repo_full_name for depth-1 edges |
| child_ecosystem | TEXT | nullable | "pypi", "npm", etc. |
| child_package | TEXT | NOT NULL | package name |
| declared_specifier | TEXT | nullable | Declared_Specifier from parent |
| resolved_version | TEXT | nullable | Resolved_Version from registry |
| depth | INTEGER | NOT NULL | 1=direct, 2+=transitive (see Depth Convention) |
| resolution_status | TEXT | NOT NULL DEFAULT 'resolved' | See Req 5.4 |
| error_reason | TEXT | nullable | Human-readable error |
| source_registry | TEXT | nullable | Ecosystem name (e.g., "pypi") |
| resolved_at | TEXT | NOT NULL | ISO 8601 timestamp |

Indexes:
- `idx_resolved_deps_repo` ON `(repo_full_name)` — bulk retrieval/deletion
- `idx_resolved_deps_parent` ON `(repo_full_name, parent_ecosystem, parent_package)` — ecosystem-qualified tree reconstruction
- `idx_resolved_deps_depth` ON `(repo_full_name, depth)` — depth-ordered queries

No UNIQUE constraint — duplicate parent-child pairs across branches are valid (Req 12.2).

### `package_metadata_cache` (Req 6, 15.2)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| ecosystem | TEXT | NOT NULL | Part of PK |
| package_name | TEXT | NOT NULL | Part of PK |
| metadata_json | TEXT | NOT NULL | Serialized NormalizedPackageMetadata or "null" |
| fetched_at | TEXT | NOT NULL | ISO 8601 |
| expires_at | TEXT | NOT NULL | ISO 8601 |

Primary key: `(ecosystem, package_name)` — version not in key because MVP always resolves latest.

## File Structure

```
src/open_source_risk_model/resolution/
    __init__.py
    models.py               # PackageIdentity, DependencyDeclaration,
                            # NormalizedPackageMetadata, ResolutionEdge,
                            # ResolutionSummary, RESOLUTION_STATUSES
    registry_client.py      # RegistryClient ABC
    pypi_client.py          # PyPIClient
    npm_client.py           # NpmClient
    registry_factory.py     # get_registry_client()
    cache.py                # ResolutionCache (session + DB, pure lookup/store)
    budget_tracker.py       # BudgetConfig, BudgetTracker
    resolver.py             # TransitiveResolver (orchestrates cache+budget+fetch)
    storage.py              # ResolvedDependencyStorage

src/open_source_risk_model/cli/
    resolve.py              # CLI entry point (new file)

src/open_source_risk_model/tree/
    service.py              # Modified: _build_canonical_tree,
                            #   _build_tree_from_resolved, _edge_to_node,
                            #   _map_resolution_status

src/open_source_risk_model/dependencies/
    ingestion_service.py    # Modified: resolve_transitive parameter

test/resolution/
    __init__.py
    test_models.py
    test_pypi_client.py
    test_npm_client.py
    test_registry_factory.py
    test_cache.py
    test_budget_tracker.py
    test_resolver.py
    test_storage.py
    test_resolver_properties.py   # property-based tests

test/tree/
    test_resolved_tree.py         # tree construction from resolved edges
```

## Data Flow

```
1. User: python -m open_source_risk_model.cli.resolve --repo pallets/flask

2. CLI reads repo_dependencies for pallets/flask
   → finds: jinja2 (pypi), werkzeug (pypi), click (pypi), ...

3. Resolver processes each direct dep (depth=1), sorted alphabetically:
   For "jinja2":
     a. cache.lookup("pypi", "jinja2") → miss
     b. budget.can_make_call("pypi") → True
     c. budget.wait_if_needed("pypi")
     d. PyPIClient.get_package_metadata("jinja2") → version=3.1.3,
        deps=[markupsafe>=2.0]
     e. budget.record_call("pypi")
     f. cache.store("pypi", "jinja2", metadata)
     g. Edge: repo=pallets/flask, parent=(None, pallets/flask),
        child=(pypi, jinja2), depth=1, declared_specifier=">=3.1.2",
        resolved_version="3.1.3", source_registry="pypi"
     h. Recurse into markupsafe (depth=2):
        → cache.lookup("pypi", "markupsafe") → miss
        → budget check → fetch → PyPI returns version=2.1.5, deps=[]
        → Edge: parent=(pypi, jinja2), child=(pypi, markupsafe),
           depth=2, declared_specifier=">=2.0", resolved_version="2.1.5"
        → No sub-deps, recursion stops

   For "werkzeug":
     a. cache.lookup("pypi", "werkzeug") → miss
     b. ... fetch ... deps=[markupsafe>=2.0]
     c. Recurse into markupsafe (depth=2):
        → cache.lookup("pypi", "markupsafe") → HIT (from jinja2 branch)
        → No API call, no budget cost
        → Separate edge: parent=(pypi, werkzeug), child=(pypi, markupsafe)
        → markupsafe appears in BOTH branches as separate edges

4. All edges stored in resolved_dependencies via single transaction

5. Tree API: GET /repos/pallets/flask/dependency-tree
   → TreeService.has_resolved_data("pallets/flask") → True
   → Build multi-level tree from resolved_dependencies
   → Root (depth=0)
       ├── jinja2 (depth=1) → markupsafe (depth=2)
       └── werkzeug (depth=1) → markupsafe (depth=2)  ← separate node
```

## Error Handling Matrix

| Scenario | resolution_status | error_reason | Recurse? | Budget cost? |
|---|---|---|---|---|
| Package found in registry | resolved | None | Yes | Yes (if not cached) |
| Package not found (404) | error | "Package not found in registry" | No | Yes |
| Registry non-200 response | error | "Registry returned HTTP {code}" | No | Yes |
| Registry timeout/network error | error | "Registry request failed: {msg}" | No | Yes |
| Cycle detected on branch | cycle_detected | None | No | No |
| Max depth exceeded | max_depth_reached | None | No | No |
| Unsupported ecosystem | unsupported_ecosystem | None | No | No |
| Budget exhausted | budget_exhausted | None | No | No |
| Session cache hit (positive) | resolved | None | Yes | No |
| Session cache hit (negative) | error | "Package not found in registry" | No | No |
| DB cache hit (positive) | resolved | None | Yes | No |
| DB cache hit (negative) | error | "Package not found in registry" | No | No |

## Key Design Decisions

1. **Separate derived storage** (Req 12.4, 13.4): `repo_dependencies` stores manifest-parsed data (source of truth for declared deps). `resolved_dependencies` stores derived transitive data. Resolution never modifies `repo_dependencies`.

2. **Surrogate primary key** (Req 12.2): The same parent-child pair can appear at different depths and in different branches. An autoincrement `id` is simple and correct. No UNIQUE constraint.

3. **Branch-local cycle detection, session-level caching** (Req 4.5, 4.6): Cycle detection uses `branch_path` (a set per recursive call chain). The cache uses `(ecosystem, name)` keys shared across the session. A package in branches A and B is fetched once (cache) but produces separate edges in each branch.

4. **Cache is pure lookup/store; resolver orchestrates** (Req 6, 9): The cache MUST NEVER make registry calls. This is a hard architectural invariant. The resolver owns the authoritative flow: lookup → budget check → delay → fetch → record → store. There is no `get_or_fetch` method. Any future contributor who adds a method that makes a registry call inside the cache class is violating this contract.

5. **Ecosystem-qualified reconstruction key via `make_node_key()`**: Tree reconstruction groups edges by `make_node_key(parent_ecosystem, parent_package)`, not just `parent_package`. This prevents cross-ecosystem name collisions. All identity logic (cycle detection, cache keys, reconstruction grouping, branch_visited guards) uses `make_node_key()` so that identity can later expand to include version without changing call sites.

6. **No retries in MVP** (Req 2.9, 3.9): Simplifies implementation and makes budget accounting predictable. A failed call costs exactly 1 budget unit.

7. **Deterministic ordering** (Req 14): Direct deps sorted by `package_name`, sub-deps sorted by `name`, edges stored ordered by `(depth, parent_ecosystem, parent_package, child_package)` — ordering matches reconstruction key, tree children sorted alphabetically by package name.

8. **source_registry stores exclusively ecosystem name, never URL**: `source_registry` contains only ecosystem identifiers (`"pypi"`, `"npm"`). No code path may write a URL to this field. Full URL is stored in `NormalizedPackageMetadata.source_url` within the cache only. If URL-level provenance is needed post-MVP, a dedicated `source_url` column is added to the edge schema.

9. **unsupported_ecosystem is a visible terminal state**: Mapped to its own status in the tree, not silently hidden as "resolved". The frontend can display it honestly. These edges do not trigger recursion, appear as terminal leaf nodes in the tree, and are counted in `ResolutionSummary.unsupported_ecosystem_count`.

10. **Separate node occurrences across branches**: Tree reconstruction creates a new TreeNode for every edge. No deduplication. The tree is a tree, not a DAG.

11. **Conservative environment-marker handling** (Req 2.5): Environment-marker deps are included (over-approximation). Extra-gated deps are excluded. This favors completeness for risk analysis.

12. **Identity isolation for post-MVP extensibility**: For MVP, parent/child identity in cycle detection, cache keys, and tree reconstruction is `(ecosystem, package_name)` via `make_node_key()`. This is only valid because version resolution is fixed to "latest". The `make_node_key()` function isolates identity logic so it can later expand to `(ecosystem, package_name, version)` without breaking storage, reconstruction, or cycle detection. `PackageIdentity` remains available for typed contexts but `make_node_key()` is the canonical identity factory.

## Requirements Traceability

| Requirement | Component(s) | Key Method(s) |
|---|---|---|
| Req 1 | registry_client.py, registry_factory.py | RegistryClient ABC, get_registry_client() |
| Req 2 | pypi_client.py | PyPIClient.get_package_metadata(), _parse_requires_dist() |
| Req 3 | npm_client.py | NpmClient.get_package_metadata() |
| Req 4 | resolver.py | resolve_repo(), _resolve_recursive() |
| Req 5 | resolver.py | _resolve_recursive() status handling |
| Req 6 | cache.py | ResolutionCache.lookup(), .store() |
| Req 7 | storage.py | ResolvedDependencyStorage.store_edges(), .get_edges() |
| Req 8 | resolver.py, models.py | ResolutionEdge.source_registry, .resolved_at, .depth |
| Req 9 | budget_tracker.py, resolver.py | BudgetTracker, authoritative flow in _resolve_recursive() |
| Req 10 | tree/service.py | _build_tree_from_resolved(), _edge_to_node(), _map_resolution_status() |
| Req 11 | cli/resolve.py | main() |
| Req 12 | storage.py | ensure_tables() DDL, idx_resolved_deps_parent includes ecosystem |
| Req 13 | dependencies/ingestion_service.py | ingest_repo() resolve_transitive param |
| Req 14 | resolver.py, storage.py, tree/service.py | sorted() calls, ORDER BY clauses |
| Req 15 | models.py, cache.py, storage.py, cli/resolve.py | resolved_at, fetched_at, expires_at, --force |
