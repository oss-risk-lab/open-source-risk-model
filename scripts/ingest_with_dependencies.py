#!/usr/bin/env python3
"""
Script to ingest repositories with full dependency parsing.

This script properly ingests repositories by:
1. Fetching repository data from GitHub
2. Parsing dependency manifests
3. Resolving packages to repositories
4. Storing everything in the database

Usage:
    python scripts/ingest_with_dependencies.py numpy/numpy
    python scripts/ingest_with_dependencies.py --file repos.txt
    python scripts/ingest_with_dependencies.py --batch numpy/numpy scipy/scipy pandas-dev/pandas
"""

import os
import sys
import argparse
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from open_source_risk_model.graph.builder import build_graph
from open_source_risk_model.graph.schema import GraphConfig
from open_source_risk_model.persistence.graph_repo import GraphRepository
from open_source_risk_model.persistence.dependency_repo import DependencyRepository
from open_source_risk_model.dependencies.manifest_discovery import ManifestDiscovery
from open_source_risk_model.dependencies.parsers import DependencyParserRegistry
from open_source_risk_model.dependencies.package_resolver import PackageResolver
from open_source_risk_model.persistence.dependency_repo import PackageMappingRepository
from open_source_risk_model.service.score_repo import score_repo


def ingest_repository(repo_full_name: str, db_path: str = "data/graphs.db"):
    """
    Ingest a repository with full dependency parsing.
    
    Args:
        repo_full_name: Repository in owner/repo format
        db_path: Path to database
    
    Returns:
        dict: Results with dependency count and status
    """
    print(f"\n{'='*60}")
    print(f"Ingesting: {repo_full_name}")
    print(f"{'='*60}")
    
    try:
        # Step 1: Score the repository
        print("📊 Step 1: Scoring repository...")
        score_data = score_repo(repo_full_name)
        print(f"   ✓ Score: {score_data.get('maintenance_risk', 'N/A')}")
        
        # Step 2: Build graph with dependency parsing enabled
        print("🔍 Step 2: Discovering manifests...")
        config = GraphConfig(parse_dependencies=True)
        
        discovery = ManifestDiscovery(repo_full_name)
        manifests = discovery.discover_manifests()
        print(f"   ✓ Found {len(manifests)} manifest file(s): {', '.join(manifests)}")
        
        # Step 3: Parse dependencies
        print("📦 Step 3: Parsing dependencies...")
        parser_registry = DependencyParserRegistry()
        dep_repo = DependencyRepository(db_path)
        
        all_dependencies = []
        for manifest_path in manifests:
            try:
                content = discovery._fetch_file_content(manifest_path)
                if content:
                    deps = parser_registry.parse_file(manifest_path, content)
                    print(f"   ✓ {manifest_path}: {len(deps)} dependencies")
                    
                    # Save to database
                    dep_repo.save_dependencies(repo_full_name, deps, manifest_path)
                    all_dependencies.extend(deps)
            except Exception as e:
                print(f"   ⚠ Failed to parse {manifest_path}: {e}")
        
        # Step 4: Resolve packages
        print("🔗 Step 4: Resolving packages to repositories...")
        resolver = PackageResolver(PackageMappingRepository(db_path))
        resolved_count = 0
        
        for dep in all_dependencies:
            try:
                # Infer registry type from manifest
                if 'requirements' in dep.manifest_path or 'pyproject.toml' in dep.manifest_path:
                    registry_type = 'pypi'
                elif 'package.json' in dep.manifest_path:
                    registry_type = 'npm'
                else:
                    continue
                
                resolution = resolver.resolve(dep.package_name, registry_type)
                if resolution.repo_full_name:
                    resolved_count += 1
                    print(f"   ✓ {dep.package_name} → {resolution.repo_full_name} ({resolution.confidence:.0%})")
                else:
                    print(f"   ⚠ {dep.package_name} → unresolved")
            except Exception as e:
                print(f"   ⚠ Failed to resolve {dep.package_name}: {e}")
        
        # Step 5: Build and store graph
        print("📊 Step 5: Building graph...")
        graph = build_graph(repo_full_name, score_data, config)
        
        graph_repo = GraphRepository(db_path)
        graph_repo.save_graph(repo_full_name, graph)
        print(f"   ✓ Graph saved: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        
        # Summary
        print(f"\n{'='*60}")
        print(f"✅ SUCCESS: {repo_full_name}")
        print(f"{'='*60}")
        print(f"Dependencies parsed: {len(all_dependencies)}")
        print(f"Packages resolved: {resolved_count}/{len(all_dependencies)} ({resolved_count/len(all_dependencies)*100:.0%})" if all_dependencies else "No dependencies")
        print(f"Graph nodes: {len(graph.nodes)}")
        print(f"Graph edges: {len(graph.edges)}")
        
        return {
            'success': True,
            'repo': repo_full_name,
            'dependencies': len(all_dependencies),
            'resolved': resolved_count,
            'nodes': len(graph.nodes),
            'edges': len(graph.edges)
        }
        
    except Exception as e:
        print(f"\n❌ ERROR: {repo_full_name}")
        print(f"   {str(e)}")
        return {
            'success': False,
            'repo': repo_full_name,
            'error': str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description='Ingest repositories with full dependency parsing'
    )
    parser.add_argument(
        'repos',
        nargs='*',
        help='Repository names (owner/repo format)'
    )
    parser.add_argument(
        '--file',
        '-f',
        help='File containing repository names (one per line)'
    )
    parser.add_argument(
        '--batch',
        '-b',
        nargs='+',
        help='Batch of repositories to ingest'
    )
    parser.add_argument(
        '--db',
        default='data/graphs.db',
        help='Database path (default: data/graphs.db)'
    )
    parser.add_argument(
        '--delay',
        type=int,
        default=2,
        help='Delay between repositories in seconds (default: 2)'
    )
    
    args = parser.parse_args()
    
    # Collect repositories
    repos = []
    
    if args.repos:
        repos.extend(args.repos)
    
    if args.batch:
        repos.extend(args.batch)
    
    if args.file:
        with open(args.file) as f:
            repos.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
    
    if not repos:
        parser.print_help()
        print("\nExample usage:")
        print("  python scripts/ingest_with_dependencies.py numpy/numpy")
        print("  python scripts/ingest_with_dependencies.py --batch numpy/numpy scipy/scipy")
        print("  python scripts/ingest_with_dependencies.py --file repos.txt")
        sys.exit(1)
    
    # Check for GitHub token
    if not os.getenv('GITHUB_TOKEN'):
        print("⚠️  Warning: GITHUB_TOKEN not set. You may hit rate limits.")
        print("   Set it with: export GITHUB_TOKEN=your_token_here")
        print()
    
    # Process repositories
    print(f"\n🚀 Starting ingestion of {len(repos)} repositories")
    print(f"Database: {args.db}")
    print(f"Delay: {args.delay}s between repos")
    print()
    
    results = []
    for i, repo in enumerate(repos, 1):
        print(f"\n[{i}/{len(repos)}] Processing {repo}...")
        result = ingest_repository(repo, args.db)
        results.append(result)
        
        # Delay between repos to be nice to GitHub API
        if i < len(repos):
            time.sleep(args.delay)
    
    # Final summary
    print(f"\n\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"Total repositories: {len(repos)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        total_deps = sum(r['dependencies'] for r in successful)
        total_resolved = sum(r['resolved'] for r in successful)
        print(f"\nTotal dependencies parsed: {total_deps}")
        print(f"Total packages resolved: {total_resolved}")
        
        if total_deps > 0:
            print(f"Overall resolution rate: {total_resolved/total_deps*100:.1%}")
    
    if failed:
        print("\n❌ Failed repositories:")
        for r in failed:
            print(f"   - {r['repo']}: {r['error']}")
    
    print(f"\n{'='*60}")
    print("✅ Ingestion complete!")
    print(f"{'='*60}")
    
    # Show next steps
    print("\nNext steps:")
    print("  1. Query dependencies:")
    print(f"     curl 'http://localhost:8000/api/repos/{successful[0]['repo']}/dependencies'" if successful else "")
    print("  2. Open Dependency Explorer:")
    print("     open ui/dependency-explorer.html")
    print("  3. View in database:")
    print(f"     sqlite3 {args.db} 'SELECT * FROM repo_dependencies;'")


if __name__ == '__main__':
    main()
