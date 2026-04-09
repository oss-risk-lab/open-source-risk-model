# Dependency Graph - Quick Reference

## Quick Start

### Enable Dependency Parsing
```bash
export GRAPH_PARSE_DEPENDENCIES=true
```

### Build Graph with Dependencies
```python
from src.open_source_risk_model.graph.builder import build_graph
from src.open_source_risk_model.graph.schema import GraphConfig

config = GraphConfig(parse_dependencies=True)
graph = build_graph("owner/repo", score_data, config)
```

## API Endpoints

### Get Dependencies
```bash
curl http://localhost:5000/api/repos/pallets/flask/dependencies
curl http://localhost:5000/api/repos/pallets/flask/dependencies?include_dev=true
```

### Get Dependents
```bash
curl http://localhost:5000/api/packages/requests/dependents?registry=pypi
curl http://localhost:5000/api/packages/react/dependents?registry=npm&limit=50
```

## Python API

### Query Dependencies
```python
from src.open_source_risk_model.persistence.dependency_repo import DependencyRepository

repo = DependencyRepository()

# Get dependencies
deps = repo.get_dependencies("pallets/flask")
deps_with_dev = repo.get_dependencies("pallets/flask", include_dev=True)

# Get dependents
dependents = repo.get_dependents("requests", "pypi")
```

### Parse Manifest
```python
from src.open_source_risk_model.dependencies.parsers import DependencyParserRegistry

registry = DependencyParserRegistry()

# Parse requirements.txt
with open("requirements.txt") as f:
    deps = registry.parse_file("requirements.txt", f.read())

# Parse package.json
with open("package.json") as f:
    deps = registry.parse_file("package.json", f.read())
```

### Resolve Package
```python
from src.open_source_risk_model.dependencies.package_resolver import PackageResolver
from src.open_source_risk_model.persistence.dependency_repo import PackageMappingRepository

resolver = PackageResolver(PackageMappingRepository())

# Resolve PyPI package
resolution = resolver.resolve("requests", "pypi")
print(f"Repo: {resolution.repo_full_name}")
print(f"Confidence: {resolution.confidence}")

# Resolve npm package
resolution = resolver.resolve("react", "npm")
```

## Configuration

### Environment Variables
```bash
# Enable/disable
GRAPH_PARSE_DEPENDENCIES=true

# Limits
GRAPH_MAX_DEPENDENCIES=100
GRAPH_INCLUDE_DEV_DEPENDENCIES=false

# Caching
MANIFEST_CACHE_TTL_HOURS=24
PACKAGE_RESOLUTION_CACHE_TTL_HOURS=168

# Rate limits
MANIFEST_DISCOVERY_MAX_API_CALLS=10
MANIFEST_FETCH_MAX_API_CALLS=20
```

### GraphConfig
```python
config = GraphConfig(
    parse_dependencies=True,
    max_dependencies=100,
    include_dev_dependencies=False,
    resolve_packages=True
)
```

## Graph Structure

### Node Types
- `PACKAGE`: Package in a registry (e.g., "requests" in PyPI)

### Edge Types
- `DEPENDS_ON`: Repository → Package
- `RESOLVES_TO`: Package → Repository

### Example
```
[Repo: flask] ─DEPENDS_ON→ [Package: requests] ─RESOLVES_TO→ [Repo: psf/requests]
```

## Supported Formats

### Python
- `requirements.txt` - pip requirements
- `requirements.in` - pip-tools
- `pyproject.toml` - PEP 621, Poetry

### JavaScript
- `package.json` - npm/yarn

## Resolution Confidence

| Method | Confidence | Source |
|--------|-----------|--------|
| pypi_project_urls | 0.95 | PyPI project_urls |
| npm_repository | 0.90 | npm repository field |
| pypi_home_page | 0.75 | PyPI home_page |
| npm_homepage | 0.70 | npm homepage |
| unresolved | 0.00 | Not found |

## Testing

### Run All Tests
```bash
./test/run_dependency_tests.sh
./test/run_dependency_tests.sh --coverage
./test/run_dependency_tests.sh --verbose
```

### Run Specific Tests
```bash
pytest test/test_dependency_parsers.py -v
pytest test/test_package_resolver.py -v
pytest test/test_dependency_integration.py -v
pytest test/test_dependency_properties.py -v
```

### Validate Phase D
```bash
python scripts/validate_phase_d.py
```

## Common Patterns

### Filter by Confidence
```python
deps = repo.get_dependencies("owner/repo")
high_confidence = [d for d in deps if d.get('resolution_confidence', 0) >= 0.80]
```

### Exclude Dev Dependencies
```python
config = GraphConfig(
    parse_dependencies=True,
    include_dev_dependencies=False
)
```

### Check Resolution Status
```python
deps = repo.get_dependencies("owner/repo")
resolved = [d for d in deps if d.get('resolved_repo')]
unresolved = [d for d in deps if not d.get('resolved_repo')]
print(f"Resolution rate: {len(resolved)/len(deps):.1%}")
```

## Troubleshooting

### Dependencies Not Appearing
1. Check `parse_dependencies=True`
2. Verify manifest files exist
3. Check GitHub API token
4. Review rate limits

### Resolution Failing
1. Verify package exists in registry
2. Check package has GitHub URL
3. Review confidence scores
4. Check cache for stale entries

### Performance Issues
1. Enable caching
2. Reduce `max_dependencies`
3. Disable resolution if not needed
4. Use database indexes

## File Locations

### Implementation
- `src/open_source_risk_model/dependencies/parsers.py`
- `src/open_source_risk_model/dependencies/package_resolver.py`
- `src/open_source_risk_model/dependencies/manifest_discovery.py`
- `src/open_source_risk_model/persistence/dependency_repo.py`

### Tests
- `test/test_dependency_parsers.py`
- `test/test_package_resolver.py`
- `test/test_dependency_integration.py`
- `test/test_dependency_properties.py`

### Documentation
- `docs/DEPENDENCY_GRAPH_GUIDE.md` - Full user guide
- `docs/DEPENDENCY_QUICK_REFERENCE.md` - This file
- `.kiro/specs/dependency-graph/` - Spec documents

## Resources

- [Full User Guide](DEPENDENCY_GRAPH_GUIDE.md)
- [Test Documentation](../test/README_DEPENDENCY_TESTS.md)
- [Phase D Summary](../PHASE_D_SUMMARY.md)
- [Design Document](../.kiro/specs/dependency-graph/design.md)

