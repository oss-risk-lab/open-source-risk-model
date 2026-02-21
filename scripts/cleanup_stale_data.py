#!/usr/bin/env python3
"""
Database Cleanup Utility

This script removes stale data from the database to free up space and improve performance.

Usage:
    python scripts/cleanup_stale_data.py [options]

Examples:
    # Remove repos older than 90 days (dry run)
    python scripts/cleanup_stale_data.py --days 90 --dry-run

    # Actually remove stale repos
    python scripts/cleanup_stale_data.py --days 90

    # Remove completed jobs older than 30 days
    python scripts/cleanup_stale_data.py --cleanup-jobs --job-days 30

    # Remove all interrupted jobs
    python scripts/cleanup_stale_data.py --cleanup-interrupted-jobs

    # Full cleanup
    python scripts/cleanup_stale_data.py --days 90 --cleanup-jobs --job-days 30 --cleanup-interrupted-jobs
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Tuple


def get_database_stats(conn: sqlite3.Connection) -> dict:
    """
    Get current database statistics.
    
    Args:
        conn: Database connection
    
    Returns:
        Dictionary of statistics
    """
    cursor = conn.cursor()
    
    stats = {}
    
    # Repository counts
    cursor.execute("SELECT COUNT(*) FROM repo_graphs")
    stats['total_repos'] = cursor.fetchone()[0]
    
    # Job counts by status
    cursor.execute("SELECT status, COUNT(*) FROM ingestion_jobs GROUP BY status")
    stats['jobs_by_status'] = dict(cursor.fetchall())
    
    # Index counts
    cursor.execute("SELECT COUNT(*) FROM repo_maintainers")
    stats['maintainer_entries'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_cves")
    stats['cve_entries'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_registries")
    stats['registry_entries'] = cursor.fetchone()[0]
    
    # Database size
    cursor.execute("PRAGMA page_count")
    page_count = cursor.fetchone()[0]
    cursor.execute("PRAGMA page_size")
    page_size = cursor.fetchone()[0]
    stats['db_size_mb'] = (page_count * page_size) / (1024 * 1024)
    
    return stats


def find_stale_repos(conn: sqlite3.Connection, days: int) -> List[Tuple[str, str]]:
    """
    Find repositories older than specified days.
    
    Args:
        conn: Database connection
        days: Age threshold in days
    
    Returns:
        List of (repo_full_name, updated_at) tuples
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT repo_full_name, updated_at
        FROM repo_graphs
        WHERE updated_at < ?
        ORDER BY updated_at
    """, (cutoff_date,))
    
    return cursor.fetchall()


def delete_stale_repos(conn: sqlite3.Connection, days: int, dry_run: bool = False) -> int:
    """
    Delete repositories older than specified days.
    
    Args:
        conn: Database connection
        days: Age threshold in days
        dry_run: If True, don't actually delete
    
    Returns:
        Number of repositories deleted
    """
    stale_repos = find_stale_repos(conn, days)
    
    if not stale_repos:
        print(f"No repositories older than {days} days found")
        return 0
    
    print(f"\nFound {len(stale_repos)} stale repositories:")
    print()
    
    for repo_name, updated_at in stale_repos[:10]:  # Show first 10
        print(f"  {repo_name} (last updated: {updated_at})")
    
    if len(stale_repos) > 10:
        print(f"  ... and {len(stale_repos) - 10} more")
    
    print()
    
    if dry_run:
        print("DRY RUN: No repositories will be deleted")
        return 0
    
    # Confirm deletion
    response = input(f"Delete {len(stale_repos)} repositories? (yes/no): ")
    
    if response.lower() not in ['yes', 'y']:
        print("Deletion cancelled")
        return 0
    
    # Delete repositories (cascade will handle indexes)
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM repo_graphs
        WHERE updated_at < ?
    """, (cutoff_date,))
    
    deleted_count = cursor.rowcount
    conn.commit()
    
    print(f"✓ Deleted {deleted_count} repositories")
    
    return deleted_count


def find_old_jobs(conn: sqlite3.Connection, days: int, status: str = None) -> List[Tuple[str, str, str]]:
    """
    Find jobs older than specified days.
    
    Args:
        conn: Database connection
        days: Age threshold in days
        status: Optional status filter
    
    Returns:
        List of (job_id, status, created_at) tuples
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    cursor = conn.cursor()
    
    if status:
        cursor.execute("""
            SELECT job_id, status, created_at
            FROM ingestion_jobs
            WHERE created_at < ? AND status = ?
            ORDER BY created_at
        """, (cutoff_date, status))
    else:
        cursor.execute("""
            SELECT job_id, status, created_at
            FROM ingestion_jobs
            WHERE created_at < ?
            ORDER BY created_at
        """, (cutoff_date,))
    
    return cursor.fetchall()


def delete_old_jobs(conn: sqlite3.Connection, days: int, status: str = None, dry_run: bool = False) -> int:
    """
    Delete jobs older than specified days.
    
    Args:
        conn: Database connection
        days: Age threshold in days
        status: Optional status filter
        dry_run: If True, don't actually delete
    
    Returns:
        Number of jobs deleted
    """
    old_jobs = find_old_jobs(conn, days, status)
    
    if not old_jobs:
        status_msg = f" with status '{status}'" if status else ""
        print(f"No jobs{status_msg} older than {days} days found")
        return 0
    
    status_msg = f" ({status})" if status else ""
    print(f"\nFound {len(old_jobs)} old jobs{status_msg}:")
    print()
    
    for job_id, job_status, created_at in old_jobs[:10]:  # Show first 10
        print(f"  {job_id} - {job_status} (created: {created_at})")
    
    if len(old_jobs) > 10:
        print(f"  ... and {len(old_jobs) - 10} more")
    
    print()
    
    if dry_run:
        print("DRY RUN: No jobs will be deleted")
        return 0
    
    # Confirm deletion
    response = input(f"Delete {len(old_jobs)} jobs? (yes/no): ")
    
    if response.lower() not in ['yes', 'y']:
        print("Deletion cancelled")
        return 0
    
    # Delete jobs
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    cursor = conn.cursor()
    
    if status:
        cursor.execute("""
            DELETE FROM ingestion_jobs
            WHERE created_at < ? AND status = ?
        """, (cutoff_date, status))
    else:
        cursor.execute("""
            DELETE FROM ingestion_jobs
            WHERE created_at < ?
        """, (cutoff_date,))
    
    deleted_count = cursor.rowcount
    conn.commit()
    
    print(f"✓ Deleted {deleted_count} jobs")
    
    return deleted_count


def delete_interrupted_jobs(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """
    Delete all interrupted jobs.
    
    Args:
        conn: Database connection
        dry_run: If True, don't actually delete
    
    Returns:
        Number of jobs deleted
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT job_id, created_at
        FROM ingestion_jobs
        WHERE status = 'interrupted'
        ORDER BY created_at
    """)
    
    interrupted_jobs = cursor.fetchall()
    
    if not interrupted_jobs:
        print("No interrupted jobs found")
        return 0
    
    print(f"\nFound {len(interrupted_jobs)} interrupted jobs:")
    print()
    
    for job_id, created_at in interrupted_jobs[:10]:  # Show first 10
        print(f"  {job_id} (created: {created_at})")
    
    if len(interrupted_jobs) > 10:
        print(f"  ... and {len(interrupted_jobs) - 10} more")
    
    print()
    
    if dry_run:
        print("DRY RUN: No jobs will be deleted")
        return 0
    
    # Confirm deletion
    response = input(f"Delete {len(interrupted_jobs)} interrupted jobs? (yes/no): ")
    
    if response.lower() not in ['yes', 'y']:
        print("Deletion cancelled")
        return 0
    
    # Delete jobs
    cursor.execute("DELETE FROM ingestion_jobs WHERE status = 'interrupted'")
    deleted_count = cursor.rowcount
    conn.commit()
    
    print(f"✓ Deleted {deleted_count} interrupted jobs")
    
    return deleted_count


def vacuum_database(conn: sqlite3.Connection) -> None:
    """
    Vacuum the database to reclaim space.
    
    Args:
        conn: Database connection
    """
    print("\nVacuuming database to reclaim space...")
    
    # Get size before vacuum
    cursor = conn.cursor()
    cursor.execute("PRAGMA page_count")
    page_count_before = cursor.fetchone()[0]
    cursor.execute("PRAGMA page_size")
    page_size = cursor.fetchone()[0]
    size_before_mb = (page_count_before * page_size) / (1024 * 1024)
    
    # Vacuum
    conn.execute("VACUUM")
    
    # Get size after vacuum
    cursor.execute("PRAGMA page_count")
    page_count_after = cursor.fetchone()[0]
    size_after_mb = (page_count_after * page_size) / (1024 * 1024)
    
    space_freed_mb = size_before_mb - size_after_mb
    
    print(f"✓ Vacuum completed")
    print(f"  Size before: {size_before_mb:.2f} MB")
    print(f"  Size after: {size_after_mb:.2f} MB")
    print(f"  Space freed: {space_freed_mb:.2f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="Clean up stale data from the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--db-path",
        default=os.getenv("GRAPH_DB_PATH", "data/graphs.db"),
        help="Path to database (default: data/graphs.db)"
    )
    
    parser.add_argument(
        "--days",
        type=int,
        help="Remove repositories older than this many days"
    )
    
    parser.add_argument(
        "--cleanup-jobs",
        action="store_true",
        help="Remove old completed/failed jobs"
    )
    
    parser.add_argument(
        "--job-days",
        type=int,
        default=30,
        help="Remove jobs older than this many days (default: 30)"
    )
    
    parser.add_argument(
        "--cleanup-interrupted-jobs",
        action="store_true",
        help="Remove all interrupted jobs"
    )
    
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Vacuum database after cleanup to reclaim space"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics"
    )
    
    args = parser.parse_args()
    
    # Validate database exists
    if not os.path.exists(args.db_path):
        print(f"✗ Database not found: {args.db_path}", file=sys.stderr)
        return 1
    
    print("=" * 60)
    print("Database Cleanup Utility")
    print("=" * 60)
    print()
    
    if args.dry_run:
        print("⚠️  DRY RUN MODE: No data will be deleted")
        print()
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    
    try:
        # Show initial statistics
        print("Current Database Statistics:")
        stats_before = get_database_stats(conn)
        print(f"  Total repositories: {stats_before['total_repos']}")
        print(f"  Total jobs: {sum(stats_before['jobs_by_status'].values())}")
        for status, count in stats_before['jobs_by_status'].items():
            print(f"    {status}: {count}")
        print(f"  Maintainer entries: {stats_before['maintainer_entries']}")
        print(f"  CVE entries: {stats_before['cve_entries']}")
        print(f"  Registry entries: {stats_before['registry_entries']}")
        print(f"  Database size: {stats_before['db_size_mb']:.2f} MB")
        print()
        
        if args.stats:
            return 0
        
        # Perform cleanup operations
        total_deleted = 0
        
        # Clean up stale repositories
        if args.days:
            deleted = delete_stale_repos(conn, args.days, args.dry_run)
            total_deleted += deleted
        
        # Clean up old jobs
        if args.cleanup_jobs:
            # Delete completed jobs
            deleted = delete_old_jobs(conn, args.job_days, 'completed', args.dry_run)
            total_deleted += deleted
            
            # Delete failed jobs
            deleted = delete_old_jobs(conn, args.job_days, 'failed', args.dry_run)
            total_deleted += deleted
        
        # Clean up interrupted jobs
        if args.cleanup_interrupted_jobs:
            deleted = delete_interrupted_jobs(conn, args.dry_run)
            total_deleted += deleted
        
        if total_deleted == 0 and not args.vacuum:
            print("No cleanup operations performed")
            print()
            print("Use --help to see available options")
            return 0
        
        # Vacuum database if requested
        if args.vacuum and not args.dry_run:
            vacuum_database(conn)
        
        # Show final statistics
        if not args.dry_run:
            print()
            print("Final Database Statistics:")
            stats_after = get_database_stats(conn)
            print(f"  Total repositories: {stats_after['total_repos']} (Δ {stats_after['total_repos'] - stats_before['total_repos']})")
            print(f"  Total jobs: {sum(stats_after['jobs_by_status'].values())} (Δ {sum(stats_after['jobs_by_status'].values()) - sum(stats_before['jobs_by_status'].values())})")
            print(f"  Database size: {stats_after['db_size_mb']:.2f} MB (Δ {stats_after['db_size_mb'] - stats_before['db_size_mb']:.2f} MB)")
        
        print()
        print("=" * 60)
        print("✓ Cleanup completed")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Cleanup failed: {e}")
        print("=" * 60)
        return 1
    
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
