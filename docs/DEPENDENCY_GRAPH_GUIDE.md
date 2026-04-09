# Dependency Graph User Guide

## Overview

The Dependency Graph feature adds supply chain analysis capabilities to the Open Source Risk Model by tracking dependencies between repositories. This enables you to:

- Discover what packages a repository depends on
- Find which repositories depend on a specific package
- Trace supply chain relationships across the ecosystem
- Identify potential security risks from transitive dependencies

## Table of Contents

1. [Quick Start](#quick-start)
2. [Features](#features)
3. [Configuration](#configuration)
4. [API Reference](#api-reference)
5. [Graph Structure](#graph-structure)
6. [Supported Ecosystems](#supported-ecosystems)
7. [Resolution Confidence](#resolution-confidence)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Quick Start

### Enable Dependency Parsing

Set the environment variable or configuration flag:

```bash
export GRAPH_PARSE_DEPENDENCIES=true
```

Or in your code:

```python
from src.open_source_risk_model.graph.builder import build_graph
from src.open_source_risk_model.graph.schema import GraphConfig

config = GraphConfig(parse_dependencies=True)
graph = build_graph("owner/repo", score_data, config)
```

### Query Dependencies

```python
from src.open_source_risk_model.persistence.dependency_repo import DependencyRepository

dep_repo = DependencyRepository()

# Get dependencies for a repository
deps = dep_repo.get_dependencies("pallets/flask")

# Get repositories that depend on a package
dependents = dep_repo.get_dependents("requests", "pypi")
```

### API Endpoints

```bash
# Get dependencies for a repository
curl http://localhost:5000/api/repos/pallets/flask/dependencies

# Get repositories that depend on a package
curl http://localhost:5000/api/packages/requests/dependents?registry=pypi
```

## Features

### 1. Manifest Discovery

Automatically discovers dependency manifest files in repositories:

- **Python**: `requirements.txt`, `requirements.in`, `pyproject.toml`
- **JavaScript**: `package.json`
- **Java**: `pom.xml` (planned)
- **Go**: `go.mod` (planned)

Uses GitHub Tree API for efficient scanning, including subdirectories and monorepos.

### 2. Dependency Parsing

Extracts package dependencies with full metadata:

- Package name
- Version constraints/specifiers
- Dependency type (production, development, optional)
- Environment markers (Python)
- Extras (Python)

### 3. Package Resolution

Resolves package names to their source repositories:

- **PyPI**: Uses PyPI API to find GitHub repository URLs
- **npm**: Uses npm registry to find repository field
- Confidence scoring (0.0-1.0) for resolution quality
- Caching to reduce API calls

### 4. Graph Integration

Dependencies are represented as first-class graph elements:

- **PACKAGE nodes**: Represent packages in registries
- **DEPENDS_ON edges**: Connect repositories to packages
- **RESOLVES_TO edges**: Connect packages to source repositories

### 5. Supply Chain Queries

Query the dependency graph:

- Direct dependencies of a repository
- Repositories that depend on a package
- Transitive dependencies (planned)
- Circular dependency detection (planned)

## Configuration

### Environment Variables

```bash
# Enable/disable dependency parsing
GRAPH_PARSE_DEPENDENCIES=true

# Maximum dependencies to parse per repository
GRAPH_MAX_DEPENDENCIES=100

# Include development dependencies
GRAPH_INCLUDE_DEV_DEPENDENCIES=false

# Enable package resolution
GRAPH_RESOLVE_PACKAGES=true

# Manifest cache TTL (hours)
MANIFEST_CACHE_TTL_HOURS=24

# Package resolution cache TTL (hours)
PACKAGE_RESOLUTION_CACHE_TTL_HOURS=168

# API rate limits
MANIFEST_DISCOVERY_MAX_API_CALLS=10
MANIFEST_FETCH_MAX_API_CALLS=20
```

### GraphConfig Options

```python
from src.open_source_risk_model.graph.schema import GraphConfig

config = GraphConfig(
    # Enable dependency parsing
    parse_dependencies=True,
    
    # Maximum dependencies to include
    max_dependencies=100,
    
    # Include development dependencies
    include_dev_dependencies=False,
    
    # Enable package resolution
    resolve_packages=True
)
```

## API Reference

### GET /api/repos/{owner}/{repo}/dependencies

Get dependencies for a repository.

**Parameters:**
- `include_dev` (boolean, optional): Include development dependencies (default: false)

**Response:**
```json
{
  "repo": "pallets/flask",
  "dependencies": [
    {
      "package_name": "werkzeug",
      "registry_type": "pypi",
      "specifier": ">=3.0.0",
      "is_direct": true,
      "is_dev": false,
      "is_optional": false,
      "dependency_group": "prod",
      "manifest_path": "requirements.txt",
      "resolved_repo": "pallets/werkzeug",
      "resolution_confidence": 0.95
    }
  ],
  "total": 1,
  "metadata": {
    "include_dev": false
  }
}
```

### GET /api/packages/{package}/dependents

Get repositories that depend on a package.

**Parameters:**
- `registry` (string, required): Registry type (pypi, npm, maven, etc.)
- `limit` (integer, optional): Maximum results (default: 100)
- `offset` (integer, optional): Pagination offset (default: 0)

**Response:**
```json
{
  "package_name": "requests",
  "registry_type": "pypi",
  "resolved_repo": "psf/requests",
  "resolution_confidence": 0.95,
  "dependents": [
    {
      "repo_full_name": "pallets/flask",
      "specifier": ">=2.31.0",
      "is_direct": true,
      "is_dev": false,
      "confidence": 0.9
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

## Graph Structure

### Node Types

#### PACKAGE Node

Represents a package in a registry (e.g., "requests" in PyPI).

```python
{
  "id": "package:pypi:requests",
  "type": "package",
  "label": "requests",
  "metadata": {
    "package_name": "requests",
    "registry_type": "pypi",
    "version_constraint": ">=2.31.0",
    "resolved_repo": "psf/requests",
    "resolution_confidence": 0.95
  },
  "provenance": {
    "source": "dependency_manifest",
    "manifest_file": "requirements.txt",
    "confidence": 0.9,
    "fetched_at": "2026-02-23T10:00:00Z"
  }
}
```

### Edge Types

#### DEPENDS_ON Edge

Connects a repository to a package it depends on.

```python
{
  "source": "repo:pallets/flask",
  "target": "package:pypi:requests",
  "relationship_type": "depends_on",
  "metadata": {
    "declared_version": ">=2.31.0",
    "is_direct": true,
    "is_dev": false,
    "is_optional": false
  },
  "provenance": {
    "source": "dependency_manifest",
    "manifest_file": "requirements.txt",
    "confidence": 0.9,
    "fetched_at": "2026-02-23T10:00:00Z"
  }
}
```

#### RESOLVES_TO Edge

Connects a package to its source repository.

```python
{
  "source": "package:pypi:requests",
  "target": "repo:psf/requests",
  "relationship_type": "resolves_to",
  "metadata": {
    "resolution_method": "pypi_project_urls",
    "confidence": 0.95
  }
}
```

### Example Graph

```
[Repo: pallets/flask]
     │
     ├─ DEPENDS_ON ─> [Package: pypi:werkzeug]
     │                      │
     │                      └─ RESOLVES_TO ─> [Repo: pallets/werkzeug]
     │                                              │
     │                                              └─ HAS_CVE ─> [CVE-2024-1234]
     │
     └─ DEPENDS_ON ─> [Package: pypi:requests]
                            │
                            └─ RESOLVES_TO ─> [Repo: psf/requests]
```

## Supported Ecosystems

### Python

**Manifest Files:**
- `requirements.txt` - Standard pip requirements
- `requirements.in` - pip-tools input files
- `pyproject.toml` - PEP 621 and Poetry format

**Features:**
- Version specifiers (==, >=, ~=, etc.)
- Extras (e.g., `requests[security]`)
- Environment markers (e.g., `python_version >= "3.7"`)
- Dependency groups (prod, dev, test, docs)

**Resolution:**
- PyPI API for package metadata
- Extracts GitHub URLs from `project_urls` and `home_page`
- Confidence: 0.95 (project_urls), 0.75 (home_page)

### JavaScript/Node.js

**Manifest Files:**
- `package.json` - npm/yarn package manifest

**Features:**
- Semantic versioning (^, ~, etc.)
- Dependency types (dependencies, devDependencies, optionalDependencies)
- Scoped packages (@org/package)

**Resolution:**
- npm registry API
- Extracts GitHub URLs from `repository` field
- Confidence: 0.90 (repository), 0.70 (homepage)

### Future Support

- **Java/Maven**: `pom.xml`
- **Go**: `go.mod`
- **Ruby**: `Gemfile`
- **Rust**: `Cargo.toml`
- **PHP**: `composer.json`

## Resolution Confidence

Package resolution assigns confidence scores (0.0-1.0) based on the method used:

| Method | Confidence | Description |
|--------|-----------|-------------|
| `pypi_project_urls` | 0.95 | Explicit Source/Repository link in PyPI metadata |
| `npm_repository` | 0.90 | Explicit repository field in package.json |
| `pypi_home_page` | 0.75 | Homepage field (might be docs site) |
| `npm_homepage` | 0.70 | Homepage field (might be docs site) |
| `github_search` | 0.50 | GitHub search result (planned) |
| `unresolved` | 0.00 | Could not resolve to repository |

### Using Confidence Scores

Filter by confidence in queries:

```python
# Only high-confidence resolutions
high_confidence_deps = [
    d for d in deps 
    if d.get('resolution_confidence', 0) >= 0.80
]

# Flag low-confidence resolutions for review
low_confidence = [
    d for d in deps 
    if 0 < d.get('resolution_confidence', 0) < 0.70
]
```

## Best Practices

### 1. Enable Caching

Caching reduces API calls and improves performance:

```bash
# Set appropriate TTL values
export MANIFEST_CACHE_TTL_HOURS=24
export PACKAGE_RESOLUTION_CACHE_TTL_HOURS=168
```

### 2. Rate Limit Protection

Monitor API usage to avoid rate limits:

```python
from src.open_source_risk_model.dependencies.rate_limiter import RateLimitTracker

tracker = RateLimitTracker()
stats = tracker.get_stats()

print(f"Manifest discovery calls: {stats['manifest_discovery']}")
print(f"Manifest fetch calls: {stats['manifest_fetch']}")
```

### 3. Incremental Adoption

Start with opt-in dependency parsing:

```python
# Only parse dependencies for specific repos
if repo_full_name in ["critical/repo1", "critical/repo2"]:
    config = GraphConfig(parse_dependencies=True)
else:
    config = GraphConfig(parse_dependencies=False)
```

### 4. Filter Development Dependencies

Exclude dev dependencies for production risk analysis:

```python
config = GraphConfig(
    parse_dependencies=True,
    include_dev_dependencies=False  # Only production deps
)
```

### 5. Monitor Resolution Quality

Track resolution success rates:

```python
deps = dep_repo.get_dependencies("owner/repo")

resolved = [d for d in deps if d.get('resolved_repo')]
unresolved = [d for d in deps if not d.get('resolved_repo')]

resolution_rate = len(resolved) / len(deps) if deps else 0
print(f"Resolution rate: {resolution_rate:.1%}")
```

## Troubleshooting

### Dependencies Not Appearing

**Problem:** Dependencies are not showing up in the graph.

**Solutions:**
1. Verify `parse_dependencies=True` is set
2. Check that manifest files exist in the repository
3. Verify GitHub API token has sufficient permissions
4. Check rate limit budget hasn't been exceeded

```python
# Debug: Check if manifests were discovered
from src.open_source_risk_model.dependencies.manifest_discovery import ManifestDiscovery

discovery = ManifestDiscovery("owner/repo")
manifests = discovery.discover_manifests()
print(f"Found manifests: {manifests}")
```

### Package Resolution Failing

**Problem:** Packages are not resolving to repositories.

**Solutions:**
1. Check package exists in registry (PyPI/npm)
2. Verify package has GitHub URL in metadata
3. Check resolution cache for stale entries
4. Review confidence scores

```python
# Debug: Test resolution directly
from src.open_source_risk_model.dependencies.package_resolver import PackageResolver
from src.open_source_risk_model.persistence.dependency_repo import PackageMappingRepository

resolver = PackageResolver(PackageMappingRepository())
resolution = resolver.resolve("package-name", "pypi")

print(f"Resolved: {resolution.repo_full_name}")
print(f"Confidence: {resolution.confidence}")
print(f"Method: {resolution.resolution_method}")
```

### API Rate Limits

**Problem:** Hitting GitHub API rate limits.

**Solutions:**
1. Increase cache TTL to reduce API calls
2. Use authenticated requests (higher rate limit)
3. Reduce `max_dependencies` limit
4. Batch repository processing

```bash
# Use GitHub token for higher rate limit
export GITHUB_TOKEN=your_token_here

# Increase cache TTL
export MANIFEST_CACHE_TTL_HOURS=48
export PACKAGE_RESOLUTION_CACHE_TTL_HOURS=336  # 2 weeks
```

### Performance Issues

**Problem:** Dependency parsing is slow.

**Solutions:**
1. Enable caching
2. Reduce `max_dependencies` limit
3. Disable package resolution if not needed
4. Use database indexes

```python
# Optimize for speed
config = GraphConfig(
    parse_dependencies=True,
    max_dependencies=50,  # Limit dependencies
    resolve_packages=False  # Skip resolution
)
```

### Malformed Manifests

**Problem:** Parser fails on malformed manifest files.

**Solutions:**
1. Parsers are designed to be fault-tolerant
2. Check logs for specific parsing errors
3. Report issues with example manifests

```python
# Debug: Test parser directly
from src.open_source_risk_model.dependencies.parsers import DependencyParserRegistry

registry = DependencyParserRegistry()
parser = registry.get_parser("requirements.txt")

with open("requirements.txt") as f:
    content = f.read()
    
deps = parser.parse(content)
print(f"Parsed {len(deps)} dependencies")
```

## Support

For issues, questions, or feature requests:

1. Check the [GitHub Issues](https://github.com/your-org/repo/issues)
2. Review the [Design Document](.kiro/specs/dependency-graph/design.md)
3. See [API Documentation](docs/API.md)

## Version History

- **v1.0** (Phase A): Storage + API
- **v1.1** (Phase B): Manifest Discovery + Parsing
- **v1.2** (Phase C): Package Resolution
- **v1.3** (Phase D): Testing + Documentation (current)

