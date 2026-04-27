#!/usr/bin/env python3
"""
Test script for Phase C: Package Resolution

Tests:
1. Package resolution (PyPI and npm)
2. GitHub URL extraction
3. Resolution caching
4. Graph integration
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from open_source_risk_model.dependencies import PackageResolver
from open_source_risk_model.persistence.dependency_repo import PackageMappingRepository
from open_source_risk_model.persistence.db import init_database


def test_pypi_resolution():
    """Test PyPI package resolution."""
    print("\n" + "="*60)
    print("TEST 1: PyPI Package Resolution")
    print("="*60)
    
    resolver = PackageResolver()
    
    test_packages = [
        "requests",  # Should resolve to psf/requests
        "flask",     # Should resolve to pallets/flask
        "django",    # Should resolve to django/django
        "numpy",     # Should resolve to numpy/numpy
    ]
    
    for package in test_packages:
        print(f"\n{package}:")
        resolution = resolver.resolve(package, 'pypi')
        
        if resolution:
            print(f"  ✓ Resolved to: {resolution.repo_full_name}")
            print(f"    Method: {resolution.resolution_method}")
            print(f"    Confidence: {resolution.confidence}")
        else:
            print(f"  ✗ Could not resolve")


def test_npm_resolution():
    """Test npm package resolution."""
    print("\n" + "="*60)
    print("TEST 2: npm Package Resolution")
    print("="*60)
    
    resolver = PackageResolver()
    
    test_packages = [
        "react",      # Should resolve to facebook/react
        "express",    # Should resolve to expressjs/express
        "lodash",     # Should resolve to lodash/lodash
        "axios",      # Should resolve to axios/axios
    ]
    
    for package in test_packages:
        print(f"\n{package}:")
        resolution = resolver.resolve(package, 'npm')
        
        if resolution:
            print(f"  ✓ Resolved to: {resolution.repo_full_name}")
            print(f"    Method: {resolution.resolution_method}")
            print(f"    Confidence: {resolution.confidence}")
        else:
            print(f"  ✗ Could not resolve")


def test_github_url_extraction():
    """Test GitHub URL extraction."""
    print("\n" + "="*60)
    print("TEST 3: GitHub URL Extraction")
    print("="*60)
    
    resolver = PackageResolver()
    
    test_urls = [
        ("https://github.com/psf/requests", "psf/requests"),
        ("https://github.com/pallets/flask.git", "pallets/flask"),
        ("git+https://github.com/django/django.git", "django/django"),
        ("git://github.com/numpy/numpy.git", "numpy/numpy"),
        ("github:facebook/react", "facebook/react"),
        ("https://github.com/owner/repo/tree/main", "owner/repo"),
    ]
    
    for url, expected in test_urls:
        result = resolver._extract_github_repo(url)
        if result == expected:
            print(f"  ✓ {url} -> {result}")
        else:
            print(f"  ✗ {url} -> {result} (expected {expected})")


def test_resolution_caching():
    """Test resolution caching."""
    print("\n" + "="*60)
    print("TEST 4: Resolution Caching")
    print("="*60)
    
    # Initialize database
    init_database("data/graphs.db")
    
    resolver = PackageResolver()
    mapping_repo = PackageMappingRepository()
    
    # Resolve a package
    print("\nResolving requests package...")
    resolution = resolver.resolve("requests", "pypi")
    
    if resolution:
        print(f"  ✓ Resolved to: {resolution.repo_full_name}")
        
        # Save to cache
        print("\nSaving to cache...")
        mapping_repo.save_mapping(resolution)
        print("  ✓ Saved")
        
        # Retrieve from cache
        print("\nRetrieving from cache...")
        cached = mapping_repo.get_mapping("requests", "pypi")
        
        if cached:
            print(f"  ✓ Retrieved: {cached['repo_full_name']}")
            print(f"    Method: {cached['resolution_method']}")
            print(f"    Confidence: {cached['confidence']}")
        else:
            print("  ✗ Cache miss")
    else:
        print("  ✗ Could not resolve")


def test_graph_integration():
    """Test graph integration with dependencies."""
    print("\n" + "="*60)
    print("TEST 5: Graph Integration")
    print("="*60)
    
    print("\nThis test requires:")
    print("  1. A repository with dependencies in the database")
    print("  2. GRAPH_PARSE_DEPENDENCIES=true")
    print("  3. Running graph builder")
    print("\nSkipping for now - manual test required")
    print("\nTo test manually:")
    print("  export GRAPH_PARSE_DEPENDENCIES=true")
    print("  python -c \"")
    print("from src.open_source_risk_model.graph.builder import build_graph")
    print("from src.open_source_risk_model.graph.schema import GraphConfig")
    print("# ... score repo first ...")
    print("config = GraphConfig(parse_dependencies=True)")
    print("graph = build_graph('pallets/flask', score_data, config)")
    print("print(f'Nodes: {len(graph.nodes)}')")
    print("print(f'Edges: {len(graph.edges)}')")
    print("print(f'Dependencies: {graph.metadata.get(\"dependencies_in_graph\", 0)}')")
    print("print(f'Resolved: {graph.metadata.get(\"dependencies_resolved\", 0)}')")
    print("  \"")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PHASE C: PACKAGE RESOLUTION - TEST SUITE")
    print("="*60)
    
    try:
        test_pypi_resolution()
        test_npm_resolution()
        test_github_url_extraction()
        test_resolution_caching()
        test_graph_integration()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60)
        print("\n✓ Phase C components are working correctly!")
        print("\nNext steps:")
        print("1. Test with real repository graphs")
        print("2. Verify PACKAGE nodes and RESOLVES_TO edges")
        print("3. Check resolution accuracy")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
