"""
Live on-demand ingestion CLI.

Usage:
    python -m open_source_risk_model.cli.ingest_live \\
        --repos numpy pandas flask \\
        --mode provisional \\
        --persistence cache

Features:
- On-demand ingestion for any GitHub repository
- Provisional mode (fast, ~5 API calls, ~2-3 seconds)
- Full mode (comprehensive, ~15 API calls, ~8-10 seconds)
- Flexible persistence (temporary, cache, database)
- Cache checking (1-hour TTL)
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

from open_source_risk_model.query.live_repo_ingestor import LiveRepoIngestor

logger = logging.getLogger(__name__)


def main():
    """Main entry point for live ingestion CLI."""
    # Load environment variables
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
        description='Live on-demand ingestion of repository data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest single repo with provisional mode (fast)
  python -m open_source_risk_model.cli.ingest_live --repos numpy/numpy
  
  # Ingest multiple repos with full mode
  python -m open_source_risk_model.cli.ingest_live --repos flask django fastapi --mode full
  
  # Ingest with database persistence
  python -m open_source_risk_model.cli.ingest_live --repos numpy --persistence database
  
  # Ingest from file
  python -m open_source_risk_model.cli.ingest_live --input repos.txt --mode provisional
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--repos',
        nargs='+',
        help='Repository identifiers (owner/repo or package names)'
    )
    input_group.add_argument(
        '--input',
        help='Input file with repository list (one per line)'
    )
    
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    
    parser.add_argument(
        '--mode',
        choices=['provisional', 'full'],
        default='provisional',
        help='Ingestion mode: provisional (fast) or full (comprehensive)'
    )
    
    parser.add_argument(
        '--persistence',
        choices=['temporary', 'cache', 'database'],
        default='cache',
        help='Persistence mode: temporary (in-query only), cache (1-hour TTL), or database'
    )
    
    parser.add_argument(
        '--output',
        help='Output JSON file with results'
    )
    
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
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
    if args.repos:
        repos = args.repos
    else:
        with open(args.input, 'r') as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"Ingesting {len(repos)} repositories...")
    print(f"Mode: {args.mode}")
    print(f"Persistence: {args.persistence}")
    print("=" * 80)
    
    # Initialize ingestor
    ingestor = LiveRepoIngestor(
        github_token=github_token,
        db_path=args.db_path
    )
    
    # Ingest repositories
    start_time = time.time()
    
    results = ingestor.ingest(
        repo_identifiers=repos,
        mode=args.mode,
        persistence_mode=args.persistence
    )
    
    elapsed = time.time() - start_time
    
    # Print results
    print("\n")
    print("=" * 80)
    print("LIVE INGESTION RESULTS")
    print("=" * 80)
    
    for result in results:
        print(f"\n{result.repo_full_name}:")
        print(f"  Risk Score:       {result.maintenance_risk_score:.3f}")
        print(f"  Risk Band:        {result.risk_band}")
        print(f"  Completeness:     {result.provenance.score_completeness}")
        print(f"  Source:           {result.provenance.source}")
        print(f"  API Calls:        {result.provenance.api_calls_made or 'N/A'}")
        print(f"  Ingestion Time:   {result.provenance.ingestion_time_seconds or 0:.1f}s")
        
        if result.provenance.missing_feature_categories:
            print(f"  Missing Features: {', '.join(result.provenance.missing_feature_categories)}")
    
    print("\n")
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total repos:      {len(repos)}")
    print(f"Successful:       {len(results)}")
    print(f"Failed:           {len(repos) - len(results)}")
    print(f"Duration:         {elapsed:.1f}s")
    print(f"Avg per repo:     {elapsed/len(repos):.1f}s")
    print("=" * 80)
    
    # Write output file if requested
    if args.output:
        output_data = {
            'version': '1.0',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'ingestion_type': 'live_on_demand',
            'mode': args.mode,
            'persistence': args.persistence,
            'results': [
                {
                    'repo_full_name': r.repo_full_name,
                    'maintenance_risk_score': r.maintenance_risk_score,
                    'risk_band': r.risk_band,
                    'features': r.features,
                    'provenance': {
                        'source': r.provenance.source,
                        'last_updated': r.provenance.last_updated.isoformat(),
                        'score_completeness': r.provenance.score_completeness,
                        'missing_feature_categories': r.provenance.missing_feature_categories,
                        'api_calls_made': r.provenance.api_calls_made,
                        'ingestion_time_seconds': r.provenance.ingestion_time_seconds
                    }
                }
                for r in results
            ],
            'summary': {
                'total_repos': len(repos),
                'successful': len(results),
                'failed': len(repos) - len(results),
                'duration_seconds': elapsed
            }
        }
        
        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\n✅ Results written to {args.output}")
    
    # Exit with appropriate code
    if len(results) < len(repos):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
