# Dependency Graph - Design Document

## Overview

This design adds dependency edges between repositories, transforming isolated repository graphs into a connected supply chain network. The system will parse dependency manifests (requirements.txt, package.json, etc.), resolve package names to source repositories, and create graph edges representing "depends_on" relationships.

**Core Philosophy:** Start simple with Python ecosystem, build extensible architecture for future ecosystems. Focus on direct dependencies first, enable transitive queries through graph traversal.

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│  /api/repos/{repo}/dependencies (new)                       │
│  /api/repos/{repo}/dependents (new)                         │
│  /api/packages/{package}/dependents (new)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│  Graph Builder   │ │ Dependency   │ │  Query API   │
│  (enhanced)      │ │   Parser     │ │  (new)       │
│                  │ │   (new)      │ │              │
└──────────────────┘ └──────────────┘ └──────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Dependency Layer (NEW)                    │
│  • DependencyParser (manifest parsing)                      │
│  • PackageResolver (package → repo mapping)                 │
│  • DependencyRepository (CRUD for dependencies)             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      SQLite Database                         │
│  • repo_graphs (existing)                                    │
│  • repo_dependencies (NEW - dependency edges)                │
│  • package_mappings (NEW - package → repo resolution)       │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Ecosystem Extensibility:** Plugin architecture for parsers (Python first, others later)
2. **Lazy Resolution:** Parse dependencies during ingestion, resolve packages on-demand
3. **Confidence Tracking:** Every resolution has a confidence score
4. **Graceful Degradation:** Missing manifests or unresolvable packages don't break ingestion
5. **Graph Integration:** Dependencies are first-class graph nodes and edges



## Graph Schema Updates

### New Node Type: PACKAGE

Represents a package in a registry (e.g., "requests" in PyPI).

```python
class NodeType(str, Enum):
    REPOSITORY = "repository"
    RELEASE = "release"
    MAINTAINER = "maintainer"
    CVE = "cve"
    REGISTRY = "registry"
    RISK_FACTOR = "risk_factor"
    PACKAGE = "package"  # NEW

class PackageNode(Node):
    type: NodeType = NodeType.PACKAGE
    metadata: Dict[str, Any] = {
        "package_name": str,        # e.g., "requests"
        "registry_type": str,       # e.g., "pypi", "npm", "maven"
        "version_constraint": str,  # e.g., ">=2.0.0,<3.0.0"
        "resolved_version": str,    # e.g., "2.31.0" (optional)
        "resolved_repo": str,       # e.g., "psf/requests" (optional)
        "resolution_confidence": float,  # 0.0-1.0
    }
    provenance: Dict[str, Any] = {
        "source": "dependency_manifest",
        "manifest_file": str,       # e.g., "requirements.txt"
        "confidence": float,
        "fetched_at": str,
    }
```

### New Edge Type: DEPENDS_ON

Represents a dependency relationship.

```python
class EdgeType(str, Enum):
    HAS_RELEASE = "has_release"
    MAINTAINED_BY = "maintained_by"
    HAS_CVE = "has_cve"
    PUBLISHED_AS = "published_as"
    HAS_RISK_FACTOR = "has_risk_factor"
    DEPENDS_ON = "depends_on"  # NEW

class DependsOnEdge(Edge):
    relationship_type: EdgeType = EdgeType.DEPENDS_ON
    source: str  # Repository node ID
    target: str  # Package node ID
    metadata: Dict[str, Any] = {
        "declared_version": str,    # Version from manifest
        "is_direct": bool,          # True for direct, False for transitive
        "is_dev": bool,             # Development dependency
        "is_optional": bool,        # Optional dependency
    }
    provenance: Dict[str, Any] = {
        "source": "dependency_manifest",
        "manifest_file": str,
        "confidence": float,
        "fetched_at": str,
    }
```

### Example Graph Structure

```
[Repo: flask] ──depends_on──> [Package: requests] ──resolved_to──> [Repo: psf/requests]
                                                                           │
                                                                    has_cve
                                                                           ▼
                                                                    [CVE-2024-1234]
```



## Database Schema Updates

### Table: repo_dependencies

Stores dependency edges for efficient querying.

```sql
CREATE TABLE repo_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    package_name TEXT NOT NULL,
    registry_type TEXT NOT NULL,
    version_constraint TEXT,
    declared_version TEXT,
    is_direct BOOLEAN NOT NULL DEFAULT 1,
    is_dev BOOLEAN NOT NULL DEFAULT 0,
    is_optional BOOLEAN NOT NULL DEFAULT 0,
    manifest_file TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
);

CREATE INDEX idx_repo_dependencies_repo ON repo_dependencies(repo_full_name);
CREATE INDEX idx_repo_dependencies_package ON repo_dependencies(package_name, registry_type);
CREATE INDEX idx_repo_dependencies_direct ON repo_dependencies(is_direct);
```

**Design Rationale:**
- Denormalized from graph JSON for fast dependency queries
- Composite index on (package_name, registry_type) enables "find all repos that depend on X"
- `is_direct` index enables filtering direct vs transitive dependencies
- Cascade delete ensures cleanup when repo is removed

### Table: package_mappings

Caches package-to-repository resolutions.

```sql
CREATE TABLE package_mappings (
    package_name TEXT NOT NULL,
    registry_type TEXT NOT NULL,
    repo_full_name TEXT,
    resolution_method TEXT NOT NULL,
    confidence REAL NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (package_name, registry_type)
);

CREATE INDEX idx_package_mappings_repo ON package_mappings(repo_full_name);
CREATE INDEX idx_package_mappings_confidence ON package_mappings(confidence);
```

**Design Rationale:**
- Caches expensive package resolution lookups
- `resolution_method` tracks how package was resolved (pypi_metadata, github_search, etc.)
- `metadata` stores additional resolution details as JSON
- Composite primary key ensures one mapping per package per registry
- Can be refreshed periodically to update stale mappings



## Component Design

### 1. Dependency Parser

Extracts dependencies from manifest files.

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class Dependency:
    """Represents a parsed dependency."""
    package_name: str
    version_constraint: str
    is_dev: bool = False
    is_optional: bool = False
    extras: List[str] = None

class DependencyParser(ABC):
    """Abstract base class for dependency parsers."""
    
    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """Check if this parser can handle the file."""
        pass
    
    @abstractmethod
    def parse(self, content: str) -> List[Dependency]:
        """Parse dependencies from file content."""
        pass

class RequirementsTxtParser(DependencyParser):
    """Parser for Python requirements.txt files."""
    
    def can_parse(self, file_path: str) -> bool:
        return file_path.endswith(('requirements.txt', 'requirements.in'))
    
    def parse(self, content: str) -> List[Dependency]:
        """
        Parse requirements.txt format.
        
        Supports:
        - Simple: requests
        - Versioned: requests==2.31.0
        - Constraints: requests>=2.0.0,<3.0.0
        - Comments: # This is a comment
        - Extras: requests[security]
        - Environment markers: requests; python_version >= "3.7"
        """
        dependencies = []
        
        for line in content.splitlines():
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Skip -r/-e/-c flags (recursive requirements)
            if line.startswith(('-r', '-e', '-c', '--')):
                continue
            
            # Remove environment markers
            if ';' in line:
                line = line.split(';')[0].strip()
            
            # Extract package name and version
            # Handle: package, package==1.0, package>=1.0,<2.0, package[extra]
            match = re.match(r'^([a-zA-Z0-9_-]+)(\[[\w,]+\])?(.*)?$', line)
            if match:
                package_name = match.group(1)
                extras = match.group(2)
                version_constraint = match.group(3).strip() if match.group(3) else ""
                
                dependencies.append(Dependency(
                    package_name=package_name,
                    version_constraint=version_constraint,
                    is_dev=False,
                    is_optional=False,
                    extras=self._parse_extras(extras) if extras else None
                ))
        
        return dependencies
    
    def _parse_extras(self, extras_str: str) -> List[str]:
        """Parse extras from [extra1,extra2] format."""
        return [e.strip() for e in extras_str.strip('[]').split(',')]

class PackageJsonParser(DependencyParser):
    """Parser for Node.js package.json files."""
    
    def can_parse(self, file_path: str) -> bool:
        return file_path.endswith('package.json')
    
    def parse(self, content: str) -> List[Dependency]:
        """
        Parse package.json format.
        
        Extracts from:
        - dependencies: Production dependencies
        - devDependencies: Development dependencies
        - optionalDependencies: Optional dependencies
        """
        import json
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []
        
        dependencies = []
        
        # Production dependencies
        for name, version in data.get('dependencies', {}).items():
            dependencies.append(Dependency(
                package_name=name,
                version_constraint=version,
                is_dev=False,
                is_optional=False
            ))
        
        # Dev dependencies
        for name, version in data.get('devDependencies', {}).items():
            dependencies.append(Dependency(
                package_name=name,
                version_constraint=version,
                is_dev=True,
                is_optional=False
            ))
        
        # Optional dependencies
        for name, version in data.get('optionalDependencies', {}).items():
            dependencies.append(Dependency(
                package_name=name,
                version_constraint=version,
                is_dev=False,
                is_optional=True
            ))
        
        return dependencies

class DependencyParserRegistry:
    """Registry of dependency parsers."""
    
    def __init__(self):
        self.parsers: List[DependencyParser] = [
            RequirementsTxtParser(),
            PackageJsonParser(),
            # Add more parsers here
        ]
    
    def get_parser(self, file_path: str) -> DependencyParser:
        """Get appropriate parser for file."""
        for parser in self.parsers:
            if parser.can_parse(file_path):
                return parser
        return None
    
    def parse_file(self, file_path: str, content: str) -> List[Dependency]:
        """Parse dependencies from file."""
        parser = self.get_parser(file_path)
        if parser:
            return parser.parse(content)
        return []
```



### 2. Package Resolver

Resolves package names to source repositories.

```python
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class PackageResolution:
    """Result of package-to-repo resolution."""
    package_name: str
    registry_type: str
    repo_full_name: Optional[str]
    confidence: float
    resolution_method: str
    metadata: Dict[str, Any]

class PackageResolver:
    """Resolves package names to source repositories."""
    
    def __init__(self, cache_repo: 'PackageMappingRepository'):
        self.cache_repo = cache_repo
    
    def resolve(
        self,
        package_name: str,
        registry_type: str
    ) -> PackageResolution:
        """
        Resolve package to source repository.
        
        Resolution strategy:
        1. Check cache (package_mappings table)
        2. Try registry-specific resolution
        3. Fall back to GitHub search
        4. Return unresolved if all fail
        """
        # Check cache first
        cached = self.cache_repo.get_mapping(package_name, registry_type)
        if cached:
            return PackageResolution(
                package_name=package_name,
                registry_type=registry_type,
                repo_full_name=cached['repo_full_name'],
                confidence=cached['confidence'],
                resolution_method=cached['resolution_method'],
                metadata=cached['metadata']
            )
        
        # Try registry-specific resolution
        if registry_type == 'pypi':
            resolution = self._resolve_pypi(package_name)
        elif registry_type == 'npm':
            resolution = self._resolve_npm(package_name)
        else:
            resolution = self._resolve_github_search(package_name, registry_type)
        
        # Cache result
        self.cache_repo.save_mapping(resolution)
        
        return resolution
    
    def _resolve_pypi(self, package_name: str) -> PackageResolution:
        """
        Resolve PyPI package to GitHub repo.
        
        Strategy:
        1. Fetch package metadata from PyPI API
        2. Extract project_urls (Homepage, Source, Repository)
        3. Parse GitHub URL if present
        4. Validate repo exists
        """
        import requests
        
        try:
            # Fetch PyPI metadata
            response = requests.get(
                f"https://pypi.org/pypi/{package_name}/json",
                timeout=5
            )
            
            if response.status_code != 200:
                return self._unresolved(package_name, 'pypi')
            
            data = response.json()
            info = data.get('info', {})
            
            # Try project_urls first
            project_urls = info.get('project_urls', {})
            for key in ['Source', 'Repository', 'Homepage', 'Code']:
                url = project_urls.get(key, '')
                repo = self._extract_github_repo(url)
                if repo:
                    return PackageResolution(
                        package_name=package_name,
                        registry_type='pypi',
                        repo_full_name=repo,
                        confidence=0.9,
                        resolution_method='pypi_project_urls',
                        metadata={'url': url, 'key': key}
                    )
            
            # Try home_page field
            home_page = info.get('home_page', '')
            repo = self._extract_github_repo(home_page)
            if repo:
                return PackageResolution(
                    package_name=package_name,
                    registry_type='pypi',
                    repo_full_name=repo,
                    confidence=0.8,
                    resolution_method='pypi_home_page',
                    metadata={'url': home_page}
                )
            
            # Fall back to GitHub search
            return self._resolve_github_search(package_name, 'pypi')
        
        except Exception as e:
            logger.warning(f"Failed to resolve PyPI package {package_name}: {e}")
            return self._unresolved(package_name, 'pypi')
    
    def _resolve_npm(self, package_name: str) -> PackageResolution:
        """
        Resolve npm package to GitHub repo.
        
        Strategy:
        1. Fetch package metadata from npm registry
        2. Extract repository field
        3. Parse GitHub URL
        4. Validate repo exists
        """
        import requests
        
        try:
            response = requests.get(
                f"https://registry.npmjs.org/{package_name}",
                timeout=5
            )
            
            if response.status_code != 200:
                return self._unresolved(package_name, 'npm')
            
            data = response.json()
            
            # Extract repository field
            repository = data.get('repository', {})
            if isinstance(repository, dict):
                url = repository.get('url', '')
            elif isinstance(repository, str):
                url = repository
            else:
                url = ''
            
            repo = self._extract_github_repo(url)
            if repo:
                return PackageResolution(
                    package_name=package_name,
                    registry_type='npm',
                    repo_full_name=repo,
                    confidence=0.9,
                    resolution_method='npm_repository_field',
                    metadata={'url': url}
                )
            
            # Fall back to GitHub search
            return self._resolve_github_search(package_name, 'npm')
        
        except Exception as e:
            logger.warning(f"Failed to resolve npm package {package_name}: {e}")
            return self._unresolved(package_name, 'npm')
    
    def _resolve_github_search(
        self,
        package_name: str,
        registry_type: str
    ) -> PackageResolution:
        """
        Resolve package via GitHub search.
        
        Strategy:
        1. Search GitHub for package name
        2. Filter by language/ecosystem
        3. Return top result if confidence high enough
        """
        # TODO: Implement GitHub search
        # For now, return unresolved
        return self._unresolved(package_name, registry_type)
    
    def _extract_github_repo(self, url: str) -> Optional[str]:
        """
        Extract owner/repo from GitHub URL.
        
        Handles:
        - https://github.com/owner/repo
        - git+https://github.com/owner/repo.git
        - git://github.com/owner/repo.git
        """
        if not url:
            return None
        
        import re
        
        # Remove git+ prefix
        url = url.replace('git+', '')
        
        # Match GitHub URL pattern
        match = re.search(r'github\.com[:/]([^/]+)/([^/\.]+)', url)
        if match:
            owner = match.group(1)
            repo = match.group(2)
            return f"{owner}/{repo}"
        
        return None
    
    def _unresolved(
        self,
        package_name: str,
        registry_type: str
    ) -> PackageResolution:
        """Return unresolved package."""
        return PackageResolution(
            package_name=package_name,
            registry_type=registry_type,
            repo_full_name=None,
            confidence=0.0,
            resolution_method='unresolved',
            metadata={}
        )
```



### 3. Dependency Repository

Database operations for dependencies.

```python
class DependencyRepository:
    """Repository for dependency CRUD operations."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        self.db_path = db_path
    
    def save_dependencies(
        self,
        repo_full_name: str,
        dependencies: List[Dependency],
        manifest_file: str
    ) -> None:
        """
        Save dependencies for a repository.
        
        Args:
            repo_full_name: Repository identifier
            dependencies: List of parsed dependencies
            manifest_file: Source manifest file path
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.execute("BEGIN TRANSACTION")
            
            # Delete existing dependencies for this repo
            conn.execute(
                "DELETE FROM repo_dependencies WHERE repo_full_name = ?",
                (repo_full_name,)
            )
            
            # Insert new dependencies
            for dep in dependencies:
                conn.execute("""
                    INSERT INTO repo_dependencies
                    (repo_full_name, package_name, registry_type, version_constraint,
                     declared_version, is_direct, is_dev, is_optional, manifest_file,
                     confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    repo_full_name,
                    dep.package_name,
                    self._infer_registry_type(manifest_file),
                    dep.version_constraint,
                    dep.version_constraint,
                    True,  # is_direct
                    dep.is_dev,
                    dep.is_optional,
                    manifest_file,
                    0.9,  # confidence
                    datetime.now(timezone.utc).isoformat()
                ))
            
            conn.execute("COMMIT")
        
        except Exception as e:
            conn.execute("ROLLBACK")
            raise DatabaseError(f"Failed to save dependencies: {e}")
        finally:
            conn.close()
    
    def get_dependencies(
        self,
        repo_full_name: str,
        include_dev: bool = True
    ) -> List[Dict[str, Any]]:
        """Get dependencies for a repository."""
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            query = """
                SELECT * FROM repo_dependencies
                WHERE repo_full_name = ?
            """
            params = [repo_full_name]
            
            if not include_dev:
                query += " AND is_dev = 0"
            
            query += " ORDER BY package_name"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
        
        finally:
            conn.close()
    
    def get_dependents(
        self,
        package_name: str,
        registry_type: str
    ) -> List[Dict[str, Any]]:
        """Get repositories that depend on a package."""
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute("""
                SELECT DISTINCT repo_full_name, package_name, version_constraint,
                       is_direct, is_dev, confidence
                FROM repo_dependencies
                WHERE package_name = ? AND registry_type = ?
                ORDER BY repo_full_name
            """, (package_name, registry_type))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        
        finally:
            conn.close()
    
    def _infer_registry_type(self, manifest_file: str) -> str:
        """Infer registry type from manifest file name."""
        if 'requirements' in manifest_file:
            return 'pypi'
        elif 'package.json' in manifest_file:
            return 'npm'
        elif 'pom.xml' in manifest_file:
            return 'maven'
        elif 'go.mod' in manifest_file:
            return 'go'
        else:
            return 'unknown'

class PackageMappingRepository:
    """Repository for package-to-repo mappings."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        self.db_path = db_path
    
    def get_mapping(
        self,
        package_name: str,
        registry_type: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached package-to-repo mapping."""
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute("""
                SELECT * FROM package_mappings
                WHERE package_name = ? AND registry_type = ?
            """, (package_name, registry_type))
            
            row = cursor.fetchone()
            return dict(row) if row else None
        
        finally:
            conn.close()
    
    def save_mapping(self, resolution: PackageResolution) -> None:
        """Save package-to-repo mapping."""
        conn = get_connection(self.db_path)
        
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            conn.execute("""
                INSERT OR REPLACE INTO package_mappings
                (package_name, registry_type, repo_full_name, resolution_method,
                 confidence, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 
                    COALESCE((SELECT created_at FROM package_mappings 
                              WHERE package_name = ? AND registry_type = ?), ?),
                    ?)
            """, (
                resolution.package_name,
                resolution.registry_type,
                resolution.repo_full_name,
                resolution.resolution_method,
                resolution.confidence,
                json.dumps(resolution.metadata),
                resolution.package_name,
                resolution.registry_type,
                now,
                now
            ))
            
            conn.commit()
        
        except Exception as e:
            raise DatabaseError(f"Failed to save package mapping: {e}")
        finally:
            conn.close()
```



## Integration with Graph Builder

Update GraphBuilder to include dependencies.

```python
class GraphBuilder:
    """Enhanced to include dependency parsing and resolution."""
    
    def __init__(self):
        self.parser_registry = DependencyParserRegistry()
        self.package_resolver = PackageResolver(PackageMappingRepository())
        self.dependency_repo = DependencyRepository()
    
    def build_graph(
        self,
        repo_full_name: str,
        score_data: Dict[str, Any],
        config: GraphConfig
    ) -> Graph:
        """Build graph including dependencies."""
        
        # Existing graph building logic...
        graph = self._build_base_graph(repo_full_name, score_data, config)
        
        # Add dependencies if enabled
        if config.include_dependencies:
            self._add_dependencies(graph, repo_full_name)
        
        return graph
    
    def _add_dependencies(self, graph: Graph, repo_full_name: str) -> None:
        """
        Add dependency nodes and edges to graph.
        
        Steps:
        1. Fetch dependency manifest from GitHub
        2. Parse dependencies
        3. Resolve packages to repos
        4. Create package nodes
        5. Create dependency edges
        6. Save to database
        """
        # Fetch manifest files from GitHub
        manifests = self._fetch_manifests(repo_full_name)
        
        all_dependencies = []
        
        for manifest_file, content in manifests.items():
            # Parse dependencies
            dependencies = self.parser_registry.parse_file(manifest_file, content)
            
            for dep in dependencies:
                # Resolve package to repo
                registry_type = self._infer_registry_type(manifest_file)
                resolution = self.package_resolver.resolve(
                    dep.package_name,
                    registry_type
                )
                
                # Create package node
                package_node = Node(
                    id=f"package:{registry_type}:{dep.package_name}",
                    type=NodeType.PACKAGE,
                    label=dep.package_name,
                    metadata={
                        "package_name": dep.package_name,
                        "registry_type": registry_type,
                        "version_constraint": dep.version_constraint,
                        "resolved_repo": resolution.repo_full_name,
                        "resolution_confidence": resolution.confidence,
                    },
                    provenance={
                        "source": "dependency_manifest",
                        "manifest_file": manifest_file,
                        "confidence": 0.9,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                
                graph.nodes.append(package_node)
                
                # Create dependency edge
                repo_node_id = f"repo:{repo_full_name}"
                dependency_edge = Edge(
                    source=repo_node_id,
                    target=package_node.id,
                    relationship_type=EdgeType.DEPENDS_ON,
                    metadata={
                        "declared_version": dep.version_constraint,
                        "is_direct": True,
                        "is_dev": dep.is_dev,
                        "is_optional": dep.is_optional,
                    },
                    provenance={
                        "source": "dependency_manifest",
                        "manifest_file": manifest_file,
                        "confidence": 0.9,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                
                graph.edges.append(dependency_edge)
                
                all_dependencies.append(dep)
        
        # Save dependencies to database
        if all_dependencies:
            self.dependency_repo.save_dependencies(
                repo_full_name,
                all_dependencies,
                list(manifests.keys())[0]  # Primary manifest
            )
    
    def _fetch_manifests(self, repo_full_name: str) -> Dict[str, str]:
        """
        Fetch dependency manifest files from GitHub.
        
        Returns:
            Dict mapping file path to content
        """
        manifests = {}
        
        # List of manifest files to try
        manifest_files = [
            'requirements.txt',
            'requirements.in',
            'package.json',
            'pom.xml',
            'go.mod',
        ]
        
        for file_path in manifest_files:
            try:
                content = self._fetch_file_from_github(repo_full_name, file_path)
                if content:
                    manifests[file_path] = content
            except Exception as e:
                logger.debug(f"Could not fetch {file_path} from {repo_full_name}: {e}")
        
        return manifests
    
    def _fetch_file_from_github(
        self,
        repo_full_name: str,
        file_path: str
    ) -> Optional[str]:
        """Fetch file content from GitHub."""
        import requests
        import base64
        
        token = os.environ.get('GITHUB_TOKEN')
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        
        url = f"https://api.github.com/repos/{repo_full_name}/contents/{file_path}"
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data['content']).decode('utf-8')
            return content
        
        return None
```



## API Endpoints

### GET /api/repos/{repo}/dependencies

Get direct dependencies for a repository.

**Request:**
```
GET /api/repos/flask/flask/dependencies?include_dev=true
```

**Response:**
```json
{
  "repo": "pallets/flask",
  "dependencies": [
    {
      "package_name": "werkzeug",
      "registry_type": "pypi",
      "version_constraint": ">=3.0.0",
      "is_direct": true,
      "is_dev": false,
      "is_optional": false,
      "resolved_repo": "pallets/werkzeug",
      "resolution_confidence": 0.9,
      "manifest_file": "requirements.txt"
    },
    {
      "package_name": "jinja2",
      "registry_type": "pypi",
      "version_constraint": ">=3.1.2",
      "is_direct": true,
      "is_dev": false,
      "is_optional": false,
      "resolved_repo": "pallets/jinja",
      "resolution_confidence": 0.9,
      "manifest_file": "requirements.txt"
    }
  ],
  "total": 2,
  "metadata": {
    "include_dev": true,
    "transitive": false
  }
}
```

### GET /api/repos/{repo}/dependencies?transitive=true

Get transitive dependencies (dependencies of dependencies).

**Request:**
```
GET /api/repos/flask/flask/dependencies?transitive=true&max_depth=2
```

**Response:**
```json
{
  "repo": "pallets/flask",
  "dependencies": [
    {
      "package_name": "werkzeug",
      "registry_type": "pypi",
      "version_constraint": ">=3.0.0",
      "is_direct": true,
      "depth": 1,
      "path": ["pallets/flask", "werkzeug"],
      "resolved_repo": "pallets/werkzeug"
    },
    {
      "package_name": "markupsafe",
      "registry_type": "pypi",
      "version_constraint": ">=2.0",
      "is_direct": false,
      "depth": 2,
      "path": ["pallets/flask", "jinja2", "markupsafe"],
      "resolved_repo": "pallets/markupsafe"
    }
  ],
  "total": 15,
  "metadata": {
    "transitive": true,
    "max_depth": 2,
    "circular_dependencies": []
  }
}
```

### GET /api/repos/{repo}/dependents

Get repositories that depend on this repository.

**Request:**
```
GET /api/repos/psf/requests/dependents?limit=10
```

**Response:**
```json
{
  "repo": "psf/requests",
  "dependents": [
    {
      "repo_full_name": "pallets/flask",
      "package_name": "requests",
      "version_constraint": ">=2.0.0",
      "is_direct": true,
      "confidence": 0.9
    },
    {
      "repo_full_name": "django/django",
      "package_name": "requests",
      "version_constraint": ">=2.25.0",
      "is_direct": true,
      "confidence": 0.9
    }
  ],
  "total": 2,
  "limit": 10,
  "offset": 0
}
```

### GET /api/packages/{package}/dependents

Get repositories that depend on a package.

**Request:**
```
GET /api/packages/requests/dependents?registry=pypi&limit=10
```

**Response:**
```json
{
  "package_name": "requests",
  "registry_type": "pypi",
  "resolved_repo": "psf/requests",
  "resolution_confidence": 0.9,
  "dependents": [
    {
      "repo_full_name": "pallets/flask",
      "version_constraint": ">=2.0.0",
      "is_direct": true,
      "is_dev": false
    },
    {
      "repo_full_name": "django/django",
      "version_constraint": ">=2.25.0",
      "is_direct": true,
      "is_dev": false
    }
  ],
  "total": 2,
  "limit": 10,
  "offset": 0
}
```



## Transitive Dependency Algorithm

```python
class DependencyTraverser:
    """Traverses dependency graph to find transitive dependencies."""
    
    def __init__(self, dependency_repo: DependencyRepository):
        self.dependency_repo = dependency_repo
    
    def get_transitive_dependencies(
        self,
        repo_full_name: str,
        max_depth: int = 3,
        include_dev: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get transitive dependencies using breadth-first search.
        
        Args:
            repo_full_name: Starting repository
            max_depth: Maximum traversal depth
            include_dev: Include development dependencies
        
        Returns:
            List of dependencies with depth and path information
        """
        visited = set()
        result = []
        queue = [(repo_full_name, 0, [repo_full_name])]
        
        while queue:
            current_repo, depth, path = queue.pop(0)
            
            # Stop if max depth reached
            if depth >= max_depth:
                continue
            
            # Get direct dependencies
            dependencies = self.dependency_repo.get_dependencies(
                current_repo,
                include_dev=include_dev
            )
            
            for dep in dependencies:
                package_key = f"{dep['registry_type']}:{dep['package_name']}"
                
                # Skip if already visited (circular dependency)
                if package_key in visited:
                    # Record circular dependency
                    result.append({
                        **dep,
                        'depth': depth + 1,
                        'path': path + [dep['package_name']],
                        'is_circular': True
                    })
                    continue
                
                visited.add(package_key)
                
                # Add to result
                result.append({
                    **dep,
                    'depth': depth + 1,
                    'path': path + [dep['package_name']],
                    'is_circular': False
                })
                
                # If package resolves to a repo, traverse it
                # (This requires package resolution)
                # For now, we only traverse direct dependencies
        
        return result
```

## Configuration

Add dependency configuration to GraphConfig.

```python
@dataclass
class GraphConfig:
    """Configuration for graph generation."""
    
    # Existing fields...
    include_cves: bool = True
    max_releases: int = 10
    max_maintainers: int = 5
    max_risk_factors: int = 5
    
    # New dependency fields
    include_dependencies: bool = True
    max_dependencies: int = 100
    include_dev_dependencies: bool = False
    resolve_packages: bool = True
    max_dependency_depth: int = 1  # For transitive queries
```

## Environment Variables

```bash
# Dependency feature flags
GRAPH_INCLUDE_DEPENDENCIES=true
GRAPH_MAX_DEPENDENCIES=100
GRAPH_INCLUDE_DEV_DEPENDENCIES=false
GRAPH_RESOLVE_PACKAGES=true

# Package resolution
PACKAGE_RESOLUTION_CACHE_TTL_HOURS=168  # 1 week
PACKAGE_RESOLUTION_TIMEOUT_SECONDS=5
```



## Testing Strategy

### Unit Tests

1. **Dependency Parsers**
   - Test requirements.txt parsing (various formats)
   - Test package.json parsing
   - Test malformed manifests
   - Test edge cases (comments, environment markers, etc.)

2. **Package Resolver**
   - Test PyPI resolution
   - Test npm resolution
   - Test GitHub URL extraction
   - Test caching behavior
   - Test unresolvable packages

3. **Dependency Repository**
   - Test save/get dependencies
   - Test get dependents
   - Test transaction rollback

### Integration Tests

1. **End-to-End Dependency Ingestion**
   - Ingest repo with dependencies
   - Verify dependencies in database
   - Verify package nodes in graph
   - Verify dependency edges in graph

2. **Dependency Query API**
   - Test GET /api/repos/{repo}/dependencies
   - Test GET /api/repos/{repo}/dependents
   - Test GET /api/packages/{package}/dependents
   - Test transitive queries

3. **Package Resolution**
   - Test resolution for real packages
   - Test cache hit/miss behavior
   - Test resolution confidence scores

### Property Tests

1. **Dependency Parsing Idempotency**
   - Parsing same manifest twice produces same result

2. **Transitive Dependency Completeness**
   - All reachable dependencies found within max_depth

3. **Circular Dependency Detection**
   - Circular dependencies detected and flagged

4. **Resolution Cache Consistency**
   - Cached resolutions match fresh resolutions

## Performance Considerations

### Optimization Strategies

1. **Batch Package Resolution**
   - Resolve multiple packages in parallel
   - Use connection pooling for registry APIs

2. **Aggressive Caching**
   - Cache package resolutions for 1 week
   - Cache manifest files (GitHub API rate limits)

3. **Lazy Resolution**
   - Parse dependencies during ingestion
   - Resolve packages on-demand (first query)

4. **Database Indexes**
   - Index on (package_name, registry_type)
   - Index on repo_full_name
   - Index on is_direct for filtering

### Expected Performance

- **Dependency Parsing**: < 1 second per manifest
- **Package Resolution**: < 500ms per package (cached)
- **Dependency Query**: < 100ms for direct dependencies
- **Transitive Query (depth 3)**: < 2 seconds

## Migration Strategy

### Phase 1: Add Schema (Non-Breaking)
1. Add repo_dependencies table
2. Add package_mappings table
3. Run migration on existing database

### Phase 2: Add Parsing (Opt-In)
1. Implement dependency parsers
2. Add include_dependencies flag (default: false)
3. Test with select repositories

### Phase 3: Add Resolution (Opt-In)
1. Implement package resolver
2. Add resolve_packages flag (default: false)
3. Test resolution accuracy

### Phase 4: Enable by Default
1. Set include_dependencies=true by default
2. Monitor performance and accuracy
3. Iterate on resolution strategies

### Phase 5: Add API Endpoints
1. Implement dependency query endpoints
2. Add to API documentation
3. Update UI to show dependencies

## Success Metrics

- **Parsing Success Rate**: > 90% of repositories with manifests
- **Resolution Accuracy**: > 70% of packages resolved correctly
- **Query Performance**: < 100ms for direct dependencies
- **Transitive Performance**: < 2 seconds for depth 3
- **Zero Breaking Changes**: Existing functionality unaffected

## Future Enhancements (Out of Scope)

- Support for more ecosystems (Ruby, Rust, etc.)
- Dependency version conflict detection
- Automated dependency updates
- License compatibility analysis
- Security advisory matching
- Dependency graph optimization recommendations
- Private package registry support
- Dependency tree visualization in UI

## Summary

This design adds dependency edges to the graph, enabling true supply chain analysis. The implementation is:

- **Extensible**: Plugin architecture for parsers
- **Performant**: Caching and lazy resolution
- **Reliable**: Graceful error handling
- **Testable**: Comprehensive test coverage
- **Non-Breaking**: Backward compatible

The dependency graph unlocks powerful queries like "What repos depend on requests?" and "If this package has a CVE, which repos are affected?" - setting the foundation for Step 3 (transitive risk scoring).
