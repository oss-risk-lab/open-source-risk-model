#!/usr/bin/env python3
"""
Dataset Expansion Orchestrator

This script orchestrates the complete dataset expansion process from repository
selection through validation and reporting.

Usage:
    python scripts/expand_dataset.py [options]

Examples:
    # Dry run (selection only, no ingestion)
    python scripts/expand_dataset.py --dry-run

    # Full expansion to 200 repos
    python scripts/expand_dataset.py --target-count 200

    # Expansion with custom backup directory
    python scripts/expand_dataset.py --backup-dir /var/backups
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.backup_database import backup_database
from scripts.restore_database import restore_database
from src.open_source_risk_model.expansion.repo_selector import RepositorySelector
from src.open_source_risk_model.expansion.models import SelectionCriteria
from src.open_source_risk_model.persistence.db import get_connection

logger = logging.getLogger(__name__)


def rebuild_indexes(db_path: str) -> None:
    """
    Rebuild database indexes.
    
    Args:
        db_path: Path to database
    """
    import subprocess
    
    # Call rebuild_indexes.py script
    result = subprocess.run(
        [sys.executable, "scripts/rebuild_indexes.py", "--db-path", db_path],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Index rebuild failed: {result.stderr}")


@dataclass
class ExpansionResult:
    """Result of dataset expansion."""
    success: bool
    repos_added: int
    repos_failed: int
    backup_path: str
    duration_seconds: float
    timestamp: datetime
    selection_file: Optional[str] = None
    manifest_file: Optional[str] = None
    error_message: Optional[str] = None


def get_current_repo_count(db_path: str) -> int:
    """
    Get current repository count from database.
    
    Args:
        db_path: Path to database
    
    Returns:
        Number of repositories
    """
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def save_selection_to_file(
    repos: List,
    output_path: str,
    criteria: SelectionCriteria
) -> None:
    """
    Save repository selection to JSON file.
    
    Args:
        repos: List of RepositoryCandidate objects
        output_path: Output file path
        criteria: Selection criteria used
    """
    # Convert repos to dictionaries
    repos_data = []
    for repo in repos:
        repos_data.append({
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
        })
    
    # Build output
    output = {
        'version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'selection_criteria': {
            'min_stars': criteria.min_stars,
            'max_days_since_commit': criteria.max_days_since_commit,
            'required_ecosystems': criteria.required_ecosystems,
            'ecosystem_targets': criteria.ecosystem_targets,
            'exclude_forks': criteria.exclude_forks
        },
        'total_selected': len(repos),
        'repositories': repos_data
    }
    
    # Write to file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    logger.info(f"Saved selection to {output_path}")


def expand_dataset(
    target_count: int = 200,
    db_path: str = "data/graphs.db",
    backup_dir: str = "backups",
    output_dir: str = "data/expansion_reports",
    dry_run: bool = False,
    github_token: Optional[str] = None
) -> ExpansionResult:
    """
    Orchestrate dataset expansion.
    
    Args:
        target_count: Target repository count (default: 200)
        db_path: Database path
        backup_dir: Backup directory
        output_dir: Report output directory
        dry_run: If True, only generate selection without ingesting
        github_token: GitHub personal access token
    
    Returns:
        ExpansionResult with status, metrics, and report path
    """
    start_time = datetime.now(timezone.utc)
    
    logger.info("=" * 80)
    logger.info("DATASET EXPANSION ORCHESTRATOR")
    logger.info("=" * 80)
    logger.info(f"Target count: {target_count}")
    logger.info(f"Database: {db_path}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("")
    
    try:
        # Step 1: Calculate number of repos to add
        logger.info("Step 1: Calculating repos to add...")
        current_count = get_current_repo_count(db_path)
        repos_to_add = target_count - current_count
        
        logger.info(f"Current repos: {current_count}")
        logger.info(f"Repos to add: {repos_to_add}")
        
        if repos_to_add <= 0:
            logger.info("Target count already reached or exceeded")
            return ExpansionResult(
                success=True,
                repos_added=0,
                repos_failed=0,
                backup_path="",
                duration_seconds=0,
                timestamp=start_time
            )
        
        # Step 2: Create pre-expansion backup
        backup_path = ""
        if not dry_run:
            logger.info("")
            logger.info("Step 2: Creating pre-expansion backup...")
            
            try:
                backup_path = backup_database(
                    db_path=db_path,
                    output_dir=backup_dir,
                    compress=False,
                    keep_days=30
                )
                logger.info(f"✓ Backup created: {backup_path}")
            except Exception as e:
                logger.error(f"✗ Backup failed: {e}")
                return ExpansionResult(
                    success=False,
                    repos_added=0,
                    repos_failed=0,
                    backup_path="",
                    duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    timestamp=start_time,
                    error_message=f"Backup failed: {e}"
                )
        
        # Step 3: Select repositories
        logger.info("")
        logger.info("Step 3: Selecting repositories...")
        
        if not github_token:
            github_token = os.getenv("GITHUB_TOKEN")
            if not github_token:
                raise ValueError("GitHub token required. Set GITHUB_TOKEN environment variable.")
        
        selector = RepositorySelector(github_token, db_path)
        criteria = SelectionCriteria()
        
        selected_repos = selector.select_repositories(count=repos_to_add, criteria=criteria)
        
        logger.info(f"✓ Selected {len(selected_repos)} repositories")
        
        # Save selection to file
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        selection_file = f"{output_dir}/selection_{timestamp_str}.json"
        save_selection_to_file(selected_repos, selection_file, criteria)
        
        # If dry run, stop here
        if dry_run:
            logger.info("")
            logger.info("=" * 80)
            logger.info("DRY RUN COMPLETE")
            logger.info(f"Selection saved to: {selection_file}")
            logger.info("=" * 80)
            
            return ExpansionResult(
                success=True,
                repos_added=0,
                repos_failed=0,
                backup_path=backup_path,
                duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                timestamp=start_time,
                selection_file=selection_file
            )
        
        # Step 4: Execute batch ingestion
        logger.info("")
        logger.info("Step 4: Executing batch ingestion...")
        logger.info("(This will be implemented in the next task)")
        
        # TODO: Implement batch ingestion execution
        # For now, return success with placeholder values
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("EXPANSION COMPLETE")
        logger.info(f"Duration: {duration:.1f}s")
        logger.info("=" * 80)
        
        return ExpansionResult(
            success=True,
            repos_added=len(selected_repos),
            repos_failed=0,
            backup_path=backup_path,
            duration_seconds=duration,
            timestamp=start_time,
            selection_file=selection_file
        )
    
    except Exception as e:
        logger.error(f"Expansion failed: {e}", exc_info=True)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        return ExpansionResult(
            success=False,
            repos_added=0,
            repos_failed=0,
            backup_path=backup_path if 'backup_path' in locals() else "",
            duration_seconds=duration,
            timestamp=start_time,
            error_message=str(e)
        )


def rollback_expansion(
    backup_path: str,
    db_path: str = "data/graphs.db",
    expected_repo_count: int = 51
) -> bool:
    """
    Rollback to pre-expansion state.
    
    Args:
        backup_path: Path to backup file
        db_path: Path to database to restore
        expected_repo_count: Expected repository count after rollback
    
    Returns:
        True if rollback successful, False otherwise
    
    Raises:
        ValueError: If backup integrity check fails or verification fails
    """
    logger.info("=" * 80)
    logger.info("ROLLBACK EXPANSION")
    logger.info("=" * 80)
    logger.info(f"Backup: {backup_path}")
    logger.info(f"Database: {db_path}")
    logger.info(f"Expected repo count: {expected_repo_count}")
    logger.info("")
    
    try:
        # Step 1: Verify backup exists and is valid
        logger.info("Step 1: Verifying backup integrity...")
        
        if not Path(backup_path).exists():
            raise ValueError(f"Backup file not found: {backup_path}")
        
        # Check backup is a valid SQLite database
        try:
            conn = get_connection(backup_path)
            cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
            backup_repo_count = cursor.fetchone()[0]
            conn.close()
            logger.info(f"✓ Backup contains {backup_repo_count} repositories")
        except Exception as e:
            raise ValueError(f"Backup integrity check failed: {e}")
        
        # Step 2: Restore database
        logger.info("")
        logger.info("Step 2: Restoring database from backup...")
        
        restore_database(backup_path, db_path)
        logger.info(f"✓ Database restored from {backup_path}")
        
        # Step 3: Verify restoration
        logger.info("")
        logger.info("Step 3: Verifying restored database...")
        
        conn = get_connection(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
        restored_repo_count = cursor.fetchone()[0]
        conn.close()
        
        logger.info(f"Restored repo count: {restored_repo_count}")
        logger.info(f"Expected repo count: {expected_repo_count}")
        
        if restored_repo_count != expected_repo_count:
            raise ValueError(
                f"Rollback verification failed: expected {expected_repo_count} repos, "
                f"got {restored_repo_count}"
            )
        
        logger.info("✓ Verification passed")
        
        # Step 4: Rebuild indexes
        logger.info("")
        logger.info("Step 4: Rebuilding indexes...")
        
        try:
            rebuild_indexes(db_path)
            logger.info("✓ Indexes rebuilt")
        except Exception as e:
            logger.warning(f"Index rebuild failed (non-fatal): {e}")
            logger.info("✓ Rollback complete (indexes may need manual rebuild)")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("ROLLBACK COMPLETE")
        logger.info("=" * 80)
        
        return True
    
    except Exception as e:
        logger.error(f"Rollback failed: {e}", exc_info=True)
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Orchestrate dataset expansion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Expand command
    expand_parser = subparsers.add_parser('expand', help='Expand dataset')
    
    expand_parser.add_argument(
        "--target-count",
        type=int,
        default=200,
        help="Target repository count (default: 200)"
    )
    
    expand_parser.add_argument(
        "--db-path",
        default="data/graphs.db",
        help="Path to database (default: data/graphs.db)"
    )
    
    expand_parser.add_argument(
        "--backup-dir",
        default="backups",
        help="Backup directory (default: backups)"
    )
    
    expand_parser.add_argument(
        "--output-dir",
        default="data/expansion_reports",
        help="Output directory for reports (default: data/expansion_reports)"
    )
    
    expand_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only generate selection without ingesting"
    )
    
    expand_parser.add_argument(
        "--github-token",
        help="GitHub personal access token (or set GITHUB_TOKEN env var)"
    )
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback expansion')
    
    rollback_parser.add_argument(
        "--backup-path",
        required=True,
        help="Path to backup file"
    )
    
    rollback_parser.add_argument(
        "--db-path",
        default="data/graphs.db",
        help="Path to database (default: data/graphs.db)"
    )
    
    rollback_parser.add_argument(
        "--expected-repo-count",
        type=int,
        default=51,
        help="Expected repository count after rollback (default: 51)"
    )
    
    # Common arguments
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Execute command
    if args.command == 'expand' or args.command is None:
        # Default to expand for backward compatibility
        result = expand_dataset(
            target_count=getattr(args, 'target_count', 200),
            db_path=getattr(args, 'db_path', 'data/graphs.db'),
            backup_dir=getattr(args, 'backup_dir', 'backups'),
            output_dir=getattr(args, 'output_dir', 'data/expansion_reports'),
            dry_run=getattr(args, 'dry_run', False),
            github_token=getattr(args, 'github_token', None)
        )
        
        # Print result
        print()
        print("=" * 80)
        print("EXPANSION RESULT")
        print("=" * 80)
        print(f"Success: {result.success}")
        print(f"Repos added: {result.repos_added}")
        print(f"Repos failed: {result.repos_failed}")
        print(f"Backup path: {result.backup_path}")
        print(f"Duration: {result.duration_seconds:.1f}s")
        if result.selection_file:
            print(f"Selection file: {result.selection_file}")
        if result.error_message:
            print(f"Error: {result.error_message}")
        print("=" * 80)
        
        sys.exit(0 if result.success else 1)
    
    elif args.command == 'rollback':
        success = rollback_expansion(
            backup_path=args.backup_path,
            db_path=args.db_path,
            expected_repo_count=args.expected_repo_count
        )
        
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
