"""
GraphQL-based batch ingestion CLI.

Usage:
    python -m open_source_risk_model.cli.ingest_graphql \\
        --input repos.txt \\
        --batch-size 10 \\
        --max-repos 100

Features:
- GraphQL batching with adaptive sizing
- 50-80% API call reduction vs REST-only
- Progress reporting with API call metrics
- Conservative defaults (batch size 10-30)
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from open_source_risk_model.ingestion.config import IngestionConfig
from open_source_risk_model.ingestion.ingestion_pipeline import IngestionPipeline
from open_source_risk_model.persistence.db import init_database

logger = logging.getLogger(__name__)


def load_repos_from_file(file_path: str) -> List[str]:
    """
    Load repository list from file.
    
    Args:
        file_path: Path to file
    
    Returns:
        List of repository names
    """
    repos = []
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                repos.append(line)
    
    return repos


def main():
    """Main entry point for GraphQL batch ingestion CLI."""
    # Load environment variables
    from pathlib import Path
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip('"').strip("'")
                    os.environ[key] = value
    
    parser = argparse.ArgumentParser(
        description='GraphQL-based batch ingestion of repository data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest with default batch size (10)
  python -m open_source_risk_model.cli.ingest_graphql --input repos.txt
  
  # Ingest with custom batch size
  python -m open_source_risk_model.cli.ingest_graphql --input repos.txt --batch-size 15
  
  # Ingest limited number of repos
  python -m open_source_risk_model.cli.ingest_graphql --input repos.txt --max-repos 50
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Input file with repository list (one per line)'
    )
    
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Initial batch size for GraphQL queries (default: 10, max: 30)'
    )
    
    parser.add_argument(
        '--max-repos',
        type=int,
        help='Maximum number of repos to ingest'
    )
    
    parser.add_argument(
        '--mode',
        choices=['provisional', 'full'],
        default='provisional',
        help='Ingestion mode: provisional (snapshot+contributors) or full (+ issues)'
    )
    
    parser.add_argument(
        '--output-manifest',
        default='data/graphql_ingestion_manifest.json',
        help='Output path for ingestion manifest'
    )
    
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Validate batch size
    if args.batch_size < 1 or args.batch_size > 30:
        print("Error: batch-size must be between 1 and 30")
        sys.exit(1)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Check for GitHub token
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    
    # Load repos
    print(f"Loading repos from {args.input}...")
    repos = load_repos_from_file(args.input)
    
    if args.max_repos:
        repos = repos[:args.max_repos]
    
    print(f"Loaded {len(repos)} repos")
    
    # Initialize database
    print(f"Initializing database at {args.db_path}...")
    init_database(args.db_path)
    
    # Create configuration
    config = IngestionConfig()
    config.config['graphql']['initial_batch_size'] = args.batch_size
    config.config['graphql']['max_batch_size'] = min(args.batch_size * 2, 30)
    
    # Initialize pipeline
    pipeline = IngestionPipeline(
        github_token=github_token,
        config=config
    )
    
    # Start ingestion
    print(f"\nStarting GraphQL batch ingestion...")
    print(f"Mode: {args.mode}")
    print(f"Initial batch size: {args.batch_size}")
    print("=" * 80)
    
    start_time = time.time()
    
    # Ingest repositories
    result = pipeline.ingest_repositories(
        repo_identifiers=repos,
        mode=args.mode
    )
    
    elapsed = time.time() - start_time
    
    # Print summary
    print("\n")
    print("=" * 80)
    print("GRAPHQL INGESTION SUMMARY")
    print("=" * 80)
    print(f"Total repos:          {len(repos)}")
    print(f"Successful:           {result.successful_count}")
    print(f"Failed:               {result.failed_count}")
    print(f"Total API calls:      {result.total_api_calls}")
    print(f"API calls per repo:   {result.total_api_calls / len(repos):.1f}")
    print(f"Duration:             {elapsed:.1f}s")
    print(f"Rate:                 {len(repos)/elapsed:.2f} repos/sec")
    print("=" * 80)
    
    # Write manifest
    manifest = {
        'version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'ingestion_type': 'graphql_batch',
        'mode': args.mode,
        'batch_size': args.batch_size,
        'repos': repos,
        'summary': {
            'total_repos': len(repos),
            'successful': result.successful_count,
            'failed': result.failed_count,
            'total_api_calls': result.total_api_calls,
            'api_calls_per_repo': result.total_api_calls / len(repos) if repos else 0,
            'duration_seconds': elapsed
        }
    }
    
    output_file = Path(args.output_manifest)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\n✅ Ingestion complete!")
    print(f"   Manifest: {args.output_manifest}")
    
    # Exit with appropriate code
    if result.failed_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
