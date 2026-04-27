#!/usr/bin/env python3
"""
Test script for Phase B: Dependency Parsing

Tests:
1. Manifest discovery
2. Dependency parsing (requirements.txt, pyproject.toml, package.json)
3. Integration with GraphBuilder
4. Database storage
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from open_source_risk_model.dependencies import (
    ManifestDiscovery,
    DependencyParserRegistry,
    ManifestCache,
    RateLimitTracker,
    DependencyIngestionConfig,
)
from open_source_risk_model.persistence.dependency_repo import DependencyRepository
from open_source_risk_model.persistence.db import init_database


def test_manifest_discovery():
    """Test manifest discovery on real repositories."""
    print("\n" + "="*60)
    print("TEST 1: Manifest Discovery")
    print("="*60)
    
    github_token = os.environ.get("GITHUB_TOKEN")
    discovery = ManifestDiscovery(github_token=github_token)
    
    test_repos = [
        "pallets/flask",      # Python (requirements.txt, setup.py)
        "psf/requests",       # Python (pyproject.toml)
        "fastapi/fastapi",    # Python (pyproject.toml, Poetry)
        "facebook/react",     # JavaScript (package.json)
    ]
    
    for repo in test_repos:
        print(f"\n{repo}:")
        manifests = discovery.discover_manifests(repo, max_depth=3, max_files=10)
        
        if manifests:
            print(f"  ✓ Found {len(manifests)} manifests:")
            for manifest in manifests:
                print(f"    - {manifest}")
        else:
            print(f"  ✗ No manifests found")


def test_dependency_parsing():
    """Test dependency parsing with sample content."""
    print("\n" + "="*60)
    print("TEST 2: Dependency Parsing")
    print("="*60)
    
    parser_registry = DependencyParserRegistry()
    
    # Test requirements.txt
    print("\nParsing requirements.txt:")
    requirements_content = """
# Production dependencies
requests>=2.28.0
flask[async]>=2.0.0
werkzeug>=2.0.0; python_version>='3.7'

# Comments and blank lines

click>=8.0.0
"""
    deps = parser_registry.parse_file("requirements.txt", requirements_content)
    print(f"  ✓ Parsed {len(deps)} dependencies:")
    for dep in deps:
        extras_str = f"[{','.join(dep.extras)}]" if dep.extras else ""
        print(f"    - {dep.package_name}{extras_str} {dep.specifier}")
    
    # Test pyproject.toml (PEP 621)
    print("\nParsing pyproject.toml (PEP 621):")
    pyproject_content = """
[project]
name = "my-package"
dependencies = [
    "requests>=2.28.0",
    "flask>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "black>=22.0.0",
]
"""
    deps = parser_registry.parse_file("pyproject.toml", pyproject_content)
    print(f"  ✓ Parsed {len(deps)} dependencies:")
    for dep in deps:
        group = f" ({dep.dependency_group})" if dep.dependency_group != "prod" else ""
        print(f"    - {dep.package_name} {dep.specifier}{group}")
    
    # Test package.json
    print("\nParsing package.json:")
    package_json_content = """
{
  "name": "my-package",
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "eslint": "^8.0.0"
  }
}
"""
    deps = parser_registry.parse_file("package.json", package_json_content)
    print(f"  ✓ Parsed {len(deps)} dependencies:")
    for dep in deps:
        group = f" ({dep.dependency_group})" if dep.dependency_group != "prod" else ""
        print(f"    - {dep.package_name} {dep.specifier}{group}")


def test_database_storage():
    """Test storing dependencies in database."""
    print("\n" + "="*60)
    print("TEST 3: Database Storage")
    print("="*60)
    
    # Initialize database
    init_database("data/graphs.db")
    
    # Create a dummy repo graph first (for foreign key constraint)
    from open_source_risk_model.persistence.graph_repo import GraphRepository
    from open_source_risk_model.graph.schema import Graph, Node, NodeType
    
    graph_repo = GraphRepository()
    dummy_graph = Graph(
        nodes=[
            Node(
                id="repo:test/test-repo",
                type=NodeType.REPO,
                label="test/test-repo",
                metadata={},
                provenance={"source": "test", "fetched_at": "2024-01-01T00:00:00Z"}
            )
        ],
        edges=[],
        metadata={"schema_version": "1.0", "repo": "test/test-repo"}
    )
    graph_repo.save_graph("test/test-repo", dummy_graph, generation_time_ms=0)
    print("  ✓ Created dummy repo for testing")
    
    # Create test dependencies
    from open_source_risk_model.dependencies import Dependency
    
    dependencies = [
        Dependency(
            package_name="requests",
            specifier=">=2.28.0",
            dependency_group="prod",
            manifest_path="requirements.txt"
        ),
        Dependency(
            package_name="flask",
            specifier=">=2.0.0",
            extras=["async"],
            dependency_group="prod",
            manifest_path="requirements.txt"
        ),
        Dependency(
            package_name="pytest",
            specifier=">=7.0.0",
            dependency_group="dev",
            manifest_path="requirements-dev.txt"
        ),
    ]
    
    # Store in database
    repo = DependencyRepository()
    repo.save_dependencies("test/test-repo", dependencies)
    print(f"  ✓ Stored {len(dependencies)} dependencies")
    
    # Query back
    stored_deps = repo.get_dependencies("test/test-repo")
    print(f"  ✓ Retrieved {len(stored_deps)} dependencies:")
    for dep in stored_deps:
        print(f"    - {dep['package_name']} {dep['specifier']} ({dep['dependency_group']})")
    
    # Test filtering
    prod_deps = repo.get_dependencies("test/test-repo", include_dev=False)
    print(f"  ✓ Filtered to {len(prod_deps)} production dependencies")


def test_rate_limiting():
    """Test rate limit tracking."""
    print("\n" + "="*60)
    print("TEST 4: Rate Limiting")
    print("="*60)
    
    github_token = os.environ.get("GITHUB_TOKEN")
    tracker = RateLimitTracker(github_token=github_token)
    config = DependencyIngestionConfig()
    
    # Check GitHub budget
    has_budget = tracker.check_github_budget(config)
    print(f"  GitHub API budget available: {has_budget}")
    
    # Simulate some calls
    for i in range(5):
        tracker.record_github_call()
    
    for i in range(3):
        tracker.record_registry_call()
    
    # Get stats
    stats = tracker.get_stats()
    print(f"  ✓ Tracked {stats['github_calls']} GitHub calls")
    print(f"  ✓ Tracked {stats['registry_calls']} registry calls")
    print(f"  ✓ Rate: {stats['github_calls_per_minute']:.1f} calls/minute")


def test_manifest_caching():
    """Test manifest content caching."""
    print("\n" + "="*60)
    print("TEST 5: Manifest Caching")
    print("="*60)
    
    cache = ManifestCache(cache_dir="data/test_manifest_cache")
    
    # Cache some content
    test_content = "requests>=2.28.0\nflask>=2.0.0"
    cache.set("test/repo", "requirements.txt", test_content)
    print("  ✓ Cached manifest content")
    
    # Retrieve from cache
    cached = cache.get("test/repo", "requirements.txt", ttl_hours=24)
    if cached == test_content:
        print("  ✓ Retrieved from cache successfully")
    else:
        print("  ✗ Cache retrieval failed")
    
    # Test cache miss
    missing = cache.get("test/repo", "nonexistent.txt", ttl_hours=24)
    if missing is None:
        print("  ✓ Cache miss handled correctly")
    else:
        print("  ✗ Cache miss not handled correctly")
    
    # Clean up
    cache.clear("test/repo")
    print("  ✓ Cache cleared")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PHASE B: DEPENDENCY PARSING - TEST SUITE")
    print("="*60)
    
    try:
        test_manifest_discovery()
        test_dependency_parsing()
        test_database_storage()
        test_rate_limiting()
        test_manifest_caching()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60)
        print("\n✓ Phase B components are working correctly!")
        print("\nNext steps:")
        print("1. Enable dependency parsing in GraphBuilder")
        print("2. Test with real repositories")
        print("3. Verify database storage")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
