#!/usr/bin/env python3
"""
Select repositories for dataset expansion.

This script uses the repository selector to generate a prioritized list
of repositories for expanding the dataset from 51 to 200 repos.

Usage:
    python scripts/select_expansion_repos.py --count 149 --output repos_20260220.json
"""

import sys
import json
import argparse
import logging
import os
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.expansion.repo_selector import RepositorySelector
from src.open_source_risk_model.expansion.models import SelectionCriteria

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Select repositories for dataset expansion')
    parser.add_argument(
        '--count',
        type=int,
        default=149,
        help='Number of repositories to select (default: 149)'
    )
    parser.add_argument(
        '--output',
        help='Output JSON file path (default: repos_YYYYMMDD_HHMMSS.json)'
    )
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    parser.add_argument(
        '--min-stars',
        type=int,
        default=1000,
        help='Minimum GitHub stars (default: 1000)'
    )
    parser.add_argument(
        '--github-token',
        help='GitHub personal access token (or set GITHUB_TOKEN env var)'
    )
    
    args = parser.parse_args()
    
    # Get GitHub token
    github_token = args.github_token or os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("❌ Error: GitHub token required")
        print("   Set GITHUB_TOKEN environment variable or use --github-token")
        sys.exit(1)
    
    # Generate output filename if not provided
    if not args.output:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output = f"repos_{timestamp}.json"
    
    print(f"\n{'='*70}")
    print(f"REPOSITORY SELECTION FOR DATASET EXPANSION")
    print(f"{'='*70}")
    print(f"Target count: {args.count}")
    print(f"Database: {args.db_path}")
    print(f"Min stars: {args.min_stars}")
    print(f"Output: {args.output}")
    print(f"{'='*70}\n")
    
    # Create selection criteria
    criteria = SelectionCriteria(
        min_stars=args.min_stars,
        max_days_since_commit=365,  # 1 year (renamed from min_commit_age_days)
        required_ecosystems=['npm', 'pypi', 'go', 'maven', 'rubygems'],
        ecosystem_targets={
            'npm': (0.25, 0.40),
            'pypi': (0.25, 0.40),
            'go': (0.10, 1.0),
            'maven': (0.10, 1.0),
            'rubygems': (0.05, 1.0)
        },
        exclude_forks=True,
        exclude_duplicate_graphs=True
    )
    
    # Initialize selector
    selector = RepositorySelector(github_token, args.db_path)
    
    # Select repositories
    print("🔍 Selecting repositories...")
    start_time = datetime.now()
    
    try:
        selected = selector.select_repositories(args.count, criteria)
    except Exception as e:
        logger.error(f"Selection failed: {e}", exc_info=True)
        print(f"\n❌ Selection failed: {e}")
        sys.exit(1)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    # Print summary
    print(f"\n✅ Selected {len(selected)} repositories in {duration:.1f}s")
    
    # Calculate ecosystem distribution
    ecosystem_counts = {}
    for repo in selected:
        eco = repo.primary_ecosystem
        ecosystem_counts[eco] = ecosystem_counts.get(eco, 0) + 1
    
    print(f"\n📊 Ecosystem Distribution:")
    for ecosystem in ['npm', 'pypi', 'go', 'maven', 'rubygems']:
        count = ecosystem_counts.get(ecosystem, 0)
        pct = count / len(selected) * 100 if selected else 0
        print(f"   {ecosystem:10s}: {count:3d} ({pct:5.1f}%)")
    
    # Print priority score stats
    scores = [r.priority_score for r in selected]
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0
    
    print(f"\n📈 Priority Scores:")
    print(f"   Average: {avg_score:.3f}")
    print(f"   Min: {min_score:.3f}")
    print(f"   Max: {max_score:.3f}")
    
    # Prepare output data
    output_data = {
        'generated_at': datetime.now().isoformat(),
        'selection_criteria': {
            'min_stars': criteria.min_stars,
            'max_days_since_commit': criteria.max_days_since_commit,
            'required_ecosystems': criteria.required_ecosystems,
            'ecosystem_targets': {k: list(v) for k, v in criteria.ecosystem_targets.items()},
            'exclude_forks': criteria.exclude_forks
        },
        'count': len(selected),
        'ecosystem_distribution': ecosystem_counts,
        'repositories': [
            {
                'full_name': repo.full_name,
                'stars': repo.stars,
                'last_commit_date': repo.last_commit_date.isoformat(),
                'primary_ecosystem': repo.primary_ecosystem,
                'manifest_types': repo.manifest_types,
                'has_prod_deps': repo.has_prod_deps,
                'is_fork': repo.is_fork,
                'fork_parent': repo.fork_parent,
                'priority_score': repo.priority_score,
                'metadata': repo.metadata
            }
            for repo in selected
        ]
    }
    
    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n💾 Saved to: {output_path}")
    
    # Print top 10 repos
    print(f"\n🏆 Top 10 Repositories by Priority:")
    for i, repo in enumerate(selected[:10], 1):
        print(f"   {i:2d}. {repo.full_name:40s} ({repo.primary_ecosystem:8s}) ⭐ {repo.stars:6d} 📊 {repo.priority_score:.3f}")
    
    print(f"\n✅ Done!\n")


if __name__ == '__main__':
    main()
