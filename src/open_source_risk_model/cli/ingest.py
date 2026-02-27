"""
Batch ingestion CLI for dependency data.

Usage:
    python -m open_source_risk_model.cli.ingest \\
        --input repos.txt \\
        --max-repos 500 \\
        --concurrency 3 \\
        --resume \\
        --sleep-on-ratelimit

Features:
- Progress bar with ETA
- Resume capability (skip already-ingested repos)
- Rate limit detection and backoff
- Concurrent workers (with rate limit coordination)
- Dataset manifest generation
- Per-repo status reporting
"""

import argparse
import json
import logging
import os
import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from open_source_risk_model.dependencies.ingestion_service import (
    DependencyIngestionService,
    IngestionResult
)
from open_source_risk_model.persistence.db import init_database, get_connection

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is detected."""
    pass


class IngestionRunTracker:
    """Tracks ingestion runs in database."""
    
    def __init__(self, db_path: str, run_id: str):
        """
        Initialize tracker.
        
        Args:
            db_path: Path to database
            run_id: Unique run identifier
        """
        self.db_path = db_path
        self.run_id = run_id
    
    def is_already_ingested(self, repo_full_name: str) -> bool:
        """
        Check if repo was already successfully ingested in this run.
        
        Args:
            repo_full_name: Repository name
        
        Returns:
            True if already ingested successfully
        """
        conn = get_connection(self.db_path)
        cursor = conn.execute("""
            SELECT COUNT(*) FROM repo_ingestion_runs 
            WHERE repo_full_name = ? AND run_id = ? AND status = 'success'
        """, (repo_full_name, self.run_id))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0
    
    def record_start(self, repo_full_name: str) -> None:
        """
        Record ingestion start.
        
        Args:
            repo_full_name: Repository name
        """
        conn = get_connection(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO repo_ingestion_runs 
            (repo_full_name, run_id, status, started_at)
            VALUES (?, ?, ?, ?)
        """, (
            repo_full_name,
            self.run_id,
            'in_progress',
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        conn.close()
    
    def record_success(self, result: IngestionResult) -> None:
        """
        Record successful ingestion.
        
        Args:
            result: Ingestion result
        """
        conn = get_connection(self.db_path)
        conn.execute("""
            UPDATE repo_ingestion_runs 
            SET status = ?,
                completed_at = ?,
                dependencies_found = ?,
                dependencies_resolved = ?,
                manifests_discovered = ?,
                duration_seconds = ?
            WHERE repo_full_name = ? AND run_id = ?
        """, (
            'success',
            result.completed_at.isoformat(),
            result.dependencies_found,
            result.dependencies_resolved,
            result.manifests_discovered,
            result.duration_seconds,
            result.repo_full_name,
            self.run_id
        ))
        conn.commit()
        conn.close()
    
    def record_failure(self, repo_full_name: str, error_message: str) -> None:
        """
        Record failed ingestion.
        
        Args:
            repo_full_name: Repository name
            error_message: Error message
        """
        conn = get_connection(self.db_path)
        conn.execute("""
            UPDATE repo_ingestion_runs 
            SET status = ?,
                completed_at = ?,
                error_message = ?
            WHERE repo_full_name = ? AND run_id = ?
        """, (
            'failed',
            datetime.now(timezone.utc).isoformat(),
            error_message,
            repo_full_name,
            self.run_id
        ))
        conn.commit()
        conn.close()


class ProgressReporter:
    """Reports ingestion progress."""
    
    def __init__(self, total: int):
        """
        Initialize reporter.
        
        Args:
            total: Total number of repos
        """
        self.total = total
        self.processed = 0
        self.successful = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
    
    def update(self, status: str) -> None:
        """
        Update progress.
        
        Args:
            status: Status (success, failed, skipped)
        """
        self.processed += 1
        
        if status == 'success':
            self.successful += 1
        elif status == 'failed':
            self.failed += 1
        elif status == 'skipped':
            self.skipped += 1
    
    def print_progress(self, repo_name: str, status: str, details: str = "") -> None:
        """
        Print progress line.
        
        Args:
            repo_name: Repository name
            status: Status (success, failed, skipped)
            details: Additional details
        """
        elapsed = time.time() - self.start_time
        rate = self.processed / elapsed if elapsed > 0 else 0
        remaining = self.total - self.processed
        eta_seconds = remaining / rate if rate > 0 else 0
        
        # Status emoji
        emoji = {
            'success': '✅',
            'failed': '❌',
            'skipped': '⏭️'
        }.get(status, '❓')
        
        # Progress bar
        progress_pct = (self.processed / self.total) * 100
        bar_width = 30
        filled = int(bar_width * self.processed / self.total)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        # Format ETA
        eta_str = self._format_duration(eta_seconds)
        
        # Print line
        print(f"\r[{bar}] {progress_pct:5.1f}% | "
              f"{self.processed}/{self.total} | "
              f"{emoji} {repo_name:40s} | "
              f"ETA: {eta_str:8s} | "
              f"{details:30s}", end='', flush=True)
    
    def print_summary(self) -> None:
        """Print final summary."""
        elapsed = time.time() - self.start_time
        
        print("\n")
        print("=" * 80)
        print("INGESTION SUMMARY")
        print("=" * 80)
        print(f"Total repos:      {self.total}")
        print(f"Successful:       {self.successful} ({self.successful/self.total*100:.1f}%)")
        print(f"Failed:           {self.failed} ({self.failed/self.total*100:.1f}%)")
        print(f"Skipped:          {self.skipped} ({self.skipped/self.total*100:.1f}%)")
        print(f"Duration:         {self._format_duration(elapsed)}")
        print(f"Rate:             {self.processed/elapsed:.2f} repos/sec")
        print("=" * 80)
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.0f}m"
        else:
            return f"{seconds/3600:.1f}h"


class DatasetManifestWriter:
    """Writes dataset manifest to JSON file."""
    
    def __init__(self, output_path: str):
        """
        Initialize writer.
        
        Args:
            output_path: Path to output manifest file
        """
        self.output_path = output_path
    
    def write(
        self,
        run_id: str,
        results: List[IngestionResult],
        skipped_repos: List[str]
    ) -> None:
        """
        Write manifest to file.
        
        Args:
            run_id: Run identifier
            results: List of ingestion results
            skipped_repos: List of skipped repo names
        """
        # Calculate summary
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        total_deps = sum(r.dependencies_found for r in successful)
        total_resolved = sum(r.dependencies_resolved for r in successful)
        resolution_rate = total_resolved / total_deps if total_deps > 0 else 0.0
        
        # Build manifest
        manifest = {
            'version': '1.0',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'run_id': run_id,
            'repos': [
                {
                    'repo_full_name': r.repo_full_name,
                    'status': 'success' if r.success else 'failed',
                    'dependencies_found': r.dependencies_found,
                    'dependencies_resolved': r.dependencies_resolved,
                    'manifests_discovered': r.manifests_discovered,
                    'resolution_rate': r.resolution_rate,
                    'duration_seconds': r.duration_seconds,
                    'ingested_at': r.completed_at.isoformat(),
                    'errors': r.errors if r.errors else []
                }
                for r in results
            ],
            'skipped': [
                {
                    'repo_full_name': repo,
                    'reason': 'already_ingested'
                }
                for repo in skipped_repos
            ],
            'summary': {
                'total_repos': len(results) + len(skipped_repos),
                'successful_repos': len(successful),
                'failed_repos': len(failed),
                'skipped_repos': len(skipped_repos),
                'total_dependencies': total_deps,
                'total_resolved': total_resolved,
                'resolution_rate': resolution_rate
            }
        }
        
        # Write to file
        output_file = Path(self.output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Wrote dataset manifest to {self.output_path}")


def load_repos_from_file(file_path: str) -> List[str]:
    """
    Load repository list from file.
    
    Skips comments and empty lines.
    
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


def detect_rate_limit(error: Exception) -> bool:
    """
    Detect if error is due to rate limiting.
    
    Args:
        error: Exception to check
    
    Returns:
        True if rate limit detected
    """
    error_str = str(error).lower()
    
    # Check for common rate limit indicators
    rate_limit_keywords = [
        'rate limit',
        '403',
        '429',
        'too many requests',
        'secondary rate limit'
    ]
    
    return any(keyword in error_str for keyword in rate_limit_keywords)


def calculate_backoff_delay(attempt: int, base_delay: int = 60) -> float:
    """
    Calculate exponential backoff delay with jitter.
    
    Args:
        attempt: Attempt number (0-indexed)
        base_delay: Base delay in seconds
    
    Returns:
        Delay in seconds
    """
    # Exponential backoff: base * 2^attempt
    delay = base_delay * (2 ** attempt)
    
    # Add jitter (0-10% of delay)
    jitter = random.uniform(0, delay * 0.1)
    
    return delay + jitter


def ingest_single_repo(
    repo_full_name: str,
    service: DependencyIngestionService,
    tracker: IngestionRunTracker,
    resume: bool,
    sleep_on_ratelimit: bool
) -> tuple[str, Optional[IngestionResult], Optional[str]]:
    """
    Ingest a single repository.
    
    Args:
        repo_full_name: Repository name
        service: Ingestion service
        tracker: Run tracker
        resume: Whether to skip already-ingested repos
        sleep_on_ratelimit: Whether to sleep on rate limit
    
    Returns:
        Tuple of (status, result, error_message)
        Status is one of: success, failed, skipped
    """
    # Check if already ingested
    if resume and tracker.is_already_ingested(repo_full_name):
        return ('skipped', None, None)
    
    # Record start
    tracker.record_start(repo_full_name)
    
    # Attempt ingestion with retry on rate limit
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            result = service.ingest_repo(
                repo_full_name,
                refresh=True,
                resolve_packages=True
            )
            
            if result.success:
                tracker.record_success(result)
                return ('success', result, None)
            else:
                error_msg = '; '.join(result.errors) if result.errors else 'Unknown error'
                tracker.record_failure(repo_full_name, error_msg)
                return ('failed', result, error_msg)
        
        except Exception as e:
            # Check if rate limit
            if detect_rate_limit(e):
                if sleep_on_ratelimit and attempt < max_attempts - 1:
                    delay = calculate_backoff_delay(attempt)
                    logger.warning(
                        f"Rate limit detected for {repo_full_name}, "
                        f"sleeping {delay:.0f}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    error_msg = f"Rate limit exceeded: {str(e)}"
                    tracker.record_failure(repo_full_name, error_msg)
                    return ('failed', None, error_msg)
            else:
                error_msg = f"Ingestion error: {str(e)}"
                tracker.record_failure(repo_full_name, error_msg)
                return ('failed', None, error_msg)
    
    # Max attempts reached
    error_msg = "Max retry attempts reached"
    tracker.record_failure(repo_full_name, error_msg)
    return ('failed', None, error_msg)


def main():
    """Main entry point for batch ingestion CLI."""
    parser = argparse.ArgumentParser(
        description='Batch ingestion of repository dependencies',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest from file with resume
  python -m open_source_risk_model.cli.ingest --input repos.txt --resume
  
  # Ingest with concurrency and rate limit handling
  python -m open_source_risk_model.cli.ingest --input repos.txt --concurrency 3 --sleep-on-ratelimit
  
  # Ingest limited number of repos
  python -m open_source_risk_model.cli.ingest --input repos.txt --max-repos 100
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
        '--max-repos',
        type=int,
        help='Maximum number of repos to ingest'
    )
    
    parser.add_argument(
        '--concurrency',
        type=int,
        default=1,
        help='Number of concurrent workers (default: 1)'
    )
    
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Skip already-ingested repos'
    )
    
    parser.add_argument(
        '--sleep-on-ratelimit',
        action='store_true',
        help='Sleep and retry on rate limit (instead of failing)'
    )
    
    parser.add_argument(
        '--manifest-output',
        default='data/manifest.json',
        help='Output path for dataset manifest (default: data/manifest.json)'
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
    
    # Load repos
    print(f"Loading repos from {args.input}...")
    repos = load_repos_from_file(args.input)
    
    if args.max_repos:
        repos = repos[:args.max_repos]
    
    print(f"Loaded {len(repos)} repos")
    
    # Initialize database
    print(f"Initializing database at {args.db_path}...")
    init_database(args.db_path)
    
    # Create run ID
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    print(f"Run ID: {run_id}")
    
    # Initialize components
    service = DependencyIngestionService(db_path=args.db_path)
    tracker = IngestionRunTracker(db_path=args.db_path, run_id=run_id)
    reporter = ProgressReporter(total=len(repos))
    manifest_writer = DatasetManifestWriter(output_path=args.manifest_output)
    
    # Start ingestion
    print(f"\nStarting ingestion with {args.concurrency} worker(s)...")
    print("=" * 80)
    
    results = []
    skipped_repos = []
    
    if args.concurrency == 1:
        # Sequential ingestion
        for repo in repos:
            status, result, error = ingest_single_repo(
                repo, service, tracker, args.resume, args.sleep_on_ratelimit
            )
            
            if status == 'skipped':
                skipped_repos.append(repo)
                reporter.update('skipped')
                reporter.print_progress(repo, 'skipped', 'Already ingested')
            elif status == 'success':
                results.append(result)
                reporter.update('success')
                details = f"{result.dependencies_found} deps, {result.resolution_rate:.0%} resolved"
                reporter.print_progress(repo, 'success', details)
            else:
                reporter.update('failed')
                reporter.print_progress(repo, 'failed', error or 'Unknown error')
    
    else:
        # Concurrent ingestion
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {
                executor.submit(
                    ingest_single_repo,
                    repo, service, tracker, args.resume, args.sleep_on_ratelimit
                ): repo
                for repo in repos
            }
            
            for future in as_completed(futures):
                repo = futures[future]
                
                try:
                    status, result, error = future.result()
                    
                    if status == 'skipped':
                        skipped_repos.append(repo)
                        reporter.update('skipped')
                        reporter.print_progress(repo, 'skipped', 'Already ingested')
                    elif status == 'success':
                        results.append(result)
                        reporter.update('success')
                        details = f"{result.dependencies_found} deps, {result.resolution_rate:.0%} resolved"
                        reporter.print_progress(repo, 'success', details)
                    else:
                        reporter.update('failed')
                        reporter.print_progress(repo, 'failed', error or 'Unknown error')
                
                except Exception as e:
                    reporter.update('failed')
                    reporter.print_progress(repo, 'failed', str(e))
    
    # Print summary
    reporter.print_summary()
    
    # Write manifest
    print(f"\nWriting dataset manifest to {args.manifest_output}...")
    manifest_writer.write(run_id, results, skipped_repos)
    
    print(f"\n✅ Ingestion complete!")
    print(f"   Run ID: {run_id}")
    print(f"   Manifest: {args.manifest_output}")
    
    # Exit with appropriate code
    if reporter.failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
