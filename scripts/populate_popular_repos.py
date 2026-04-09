#!/usr/bin/env python3
"""
Populate database with popular open source repositories.

This script ingests 15-20 popular repos with full dependency resolution
to create a credible demo dataset.

Usage:
    python scripts/populate_popular_repos.py [--refresh] [--skip-resolution]
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.dependencies.ingestion_service import (
    DependencyIngestionService,
    IngestionResult
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Popular repos across different ecosystems
POPULAR_REPOS = [
    # Python
    'pallets/flask',
    'psf/requests',
    'django/django',
    'fastapi/fastapi',
    'pytest-dev/pytest',
    'numpy/numpy',
    'pandas-dev/pandas',
    'scikit-learn/scikit-learn',
    'ansible/ansible',
    'scrapy/scrapy',
    
    # JavaScript/TypeScript
    'facebook/react',
    'microsoft/vscode',
    'nodejs/node',
    'expressjs/express',
    'webpack/webpack',
    
    # Go
    'kubernetes/kubernetes',
    'docker/compose',
    'prometheus/prometheus',
    
    # Java
    'spring-projects/spring-boot',
    'elastic/elasticsearch',
]


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


def print_result(result: IngestionResult) -> None:
    """Print ingestion result in a nice format."""
    status = "✅" if result.success else "❌"
    resolution_pct = f"{result.resolution_rate:.0%}" if result.dependencies_found > 0 else "N/A"
    
    print(f"{status} {result.repo_full_name}")
    print(f"   Manifests: {result.manifests_discovered}")
    print(f"   Dependencies: {result.dependencies_found}")
    print(f"   Resolved: {result.dependencies_resolved} ({resolution_pct})")
    print(f"   Duration: {format_duration(result.duration_seconds)}")
    
    if result.errors:
        print(f"   Errors: {len(result.errors)}")
        for error in result.errors[:3]:  # Show first 3 errors
            print(f"     - {error}")


def main():
    parser = argparse.ArgumentParser(description='Populate database with popular repos')
    parser.add_argument(
        '--refresh',
        action='store_true',
        help='Refresh existing repos (default: skip if already ingested)'
    )
    parser.add_argument(
        '--skip-resolution',
        action='store_true',
        help='Skip package resolution (faster, but no GitHub repos)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of repos to ingest'
    )
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    
    args = parser.parse_args()
    
    # Initialize service
    service = DependencyIngestionService(db_path=args.db_path)
    
    # Select repos
    repos = POPULAR_REPOS
    if args.limit:
        repos = repos[:args.limit]
    
    print(f"\n{'='*70}")
    print(f"POPULATING DATABASE WITH {len(repos)} POPULAR REPOS")
    print(f"{'='*70}")
    print(f"Database: {args.db_path}")
    print(f"Refresh: {args.refresh}")
    print(f"Resolve packages: {not args.skip_resolution}")
    print(f"{'='*70}\n")
    
    # Track stats
    start_time = datetime.now()
    results = []
    
    # Ingest each repo
    for i, repo in enumerate(repos, 1):
        print(f"\n[{i}/{len(repos)}] Ingesting {repo}...")
        
        try:
            result = service.ingest_repo(
                repo,
                refresh=args.refresh,
                resolve_packages=not args.skip_resolution
            )
            results.append(result)
            print_result(result)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        except Exception as e:
            logger.error(f"Failed to ingest {repo}: {e}", exc_info=True)
            print(f"❌ {repo}")
            print(f"   Error: {e}")
    
    # Print summary
    total_duration = (datetime.now() - start_time).total_seconds()
    successful = sum(1 for r in results if r.success)
    total_deps = sum(r.dependencies_found for r in results)
    total_resolved = sum(r.dependencies_resolved for r in results)
    avg_resolution = (total_resolved / total_deps * 100) if total_deps > 0 else 0
    
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Total repos: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")
    print(f"Total dependencies: {total_deps}")
    print(f"Total resolved: {total_resolved} ({avg_resolution:.0f}%)")
    print(f"Total duration: {format_duration(total_duration)}")
    print(f"Avg per repo: {format_duration(total_duration / len(results)) if results else 'N/A'}")
    print(f"{'='*70}\n")
    
    # Print failures
    failures = [r for r in results if not r.success]
    if failures:
        print(f"\n⚠️  FAILED REPOS ({len(failures)}):")
        for result in failures:
            print(f"  - {result.repo_full_name}")
            for error in result.errors[:2]:
                print(f"      {error}")
    
    # Print skipped
    skipped = [r for r in results if r.errors and "Skipped" in r.errors[0]]
    if skipped:
        print(f"\n⏭️  SKIPPED REPOS ({len(skipped)}):")
        for result in skipped:
            print(f"  - {result.repo_full_name} (already ingested)")
    
    print("\n✅ Done!\n")


if __name__ == '__main__':
    main()
