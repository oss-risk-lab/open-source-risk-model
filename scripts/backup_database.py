#!/usr/bin/env python3
"""
Database Backup Utility

This script creates a backup of the SQLite database with optional compression
and cloud storage upload.

Usage:
    python scripts/backup_database.py [options]

Examples:
    # Basic backup
    python scripts/backup_database.py

    # Backup with compression
    python scripts/backup_database.py --compress

    # Backup to specific directory
    python scripts/backup_database.py --output /var/backups/graphs

    # Backup and upload to S3
    python scripts/backup_database.py --compress --s3-bucket my-backups
"""

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def backup_database(
    db_path: str,
    output_dir: str,
    compress: bool = False,
    keep_days: int = 30
) -> str:
    """
    Create a backup of the SQLite database.
    
    Args:
        db_path: Path to the source database
        output_dir: Directory to store backup
        compress: Whether to compress the backup
        keep_days: Number of days to keep old backups
    
    Returns:
        Path to the backup file
    """
    # Validate source database exists
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"graphs_{timestamp}.db"
    backup_path = os.path.join(output_dir, backup_filename)
    
    print(f"Creating backup: {backup_path}")
    
    # Use SQLite's backup API for consistent backup
    try:
        source_conn = sqlite3.connect(db_path)
        backup_conn = sqlite3.connect(backup_path)
        
        # Perform backup
        with backup_conn:
            source_conn.backup(backup_conn)
        
        source_conn.close()
        backup_conn.close()
        
        print(f"✓ Backup created successfully")
        
    except Exception as e:
        print(f"✗ Backup failed: {e}", file=sys.stderr)
        if os.path.exists(backup_path):
            os.remove(backup_path)
        raise
    
    # Verify backup integrity
    print("Verifying backup integrity...")
    try:
        conn = sqlite3.connect(backup_path)
        cursor = conn.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        conn.close()
        
        if result != "ok":
            raise ValueError(f"Integrity check failed: {result}")
        
        print("✓ Backup integrity verified")
        
    except Exception as e:
        print(f"✗ Integrity check failed: {e}", file=sys.stderr)
        os.remove(backup_path)
        raise
    
    # Compress if requested
    if compress:
        print("Compressing backup...")
        compressed_path = f"{backup_path}.gz"
        
        try:
            with open(backup_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove uncompressed backup
            os.remove(backup_path)
            backup_path = compressed_path
            
            print(f"✓ Backup compressed: {backup_path}")
            
        except Exception as e:
            print(f"✗ Compression failed: {e}", file=sys.stderr)
            if os.path.exists(compressed_path):
                os.remove(compressed_path)
            raise
    
    # Get backup size
    backup_size = os.path.getsize(backup_path)
    size_mb = backup_size / (1024 * 1024)
    print(f"Backup size: {size_mb:.2f} MB")
    
    # Clean up old backups
    cleanup_old_backups(output_dir, keep_days)
    
    return backup_path


def cleanup_old_backups(backup_dir: str, keep_days: int) -> None:
    """
    Remove backups older than keep_days.
    
    Args:
        backup_dir: Directory containing backups
        keep_days: Number of days to keep backups
    """
    if keep_days <= 0:
        return
    
    print(f"Cleaning up backups older than {keep_days} days...")
    
    cutoff_time = datetime.now().timestamp() - (keep_days * 86400)
    removed_count = 0
    
    for filename in os.listdir(backup_dir):
        if not filename.startswith("graphs_"):
            continue
        
        filepath = os.path.join(backup_dir, filename)
        
        if os.path.getmtime(filepath) < cutoff_time:
            try:
                os.remove(filepath)
                removed_count += 1
                print(f"  Removed: {filename}")
            except Exception as e:
                print(f"  Failed to remove {filename}: {e}", file=sys.stderr)
    
    if removed_count > 0:
        print(f"✓ Removed {removed_count} old backup(s)")
    else:
        print("No old backups to remove")


def upload_to_s3(backup_path: str, bucket: str, prefix: str = "") -> None:
    """
    Upload backup to AWS S3.
    
    Args:
        backup_path: Path to backup file
        bucket: S3 bucket name
        prefix: Optional prefix for S3 key
    """
    try:
        import boto3
    except ImportError:
        print("✗ boto3 not installed. Install with: pip install boto3", file=sys.stderr)
        return
    
    print(f"Uploading to S3: s3://{bucket}/{prefix}")
    
    try:
        s3_client = boto3.client('s3')
        
        filename = os.path.basename(backup_path)
        s3_key = f"{prefix}/{filename}" if prefix else filename
        
        s3_client.upload_file(backup_path, bucket, s3_key)
        
        print(f"✓ Uploaded to s3://{bucket}/{s3_key}")
        
    except Exception as e:
        print(f"✗ S3 upload failed: {e}", file=sys.stderr)
        raise


def get_database_stats(db_path: str) -> dict:
    """
    Get statistics about the database.
    
    Args:
        db_path: Path to database
    
    Returns:
        Dictionary of statistics
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    stats = {}
    
    # Get table counts
    cursor.execute("SELECT COUNT(*) FROM repo_graphs")
    stats['repo_count'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ingestion_jobs")
    stats['job_count'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_maintainers")
    stats['maintainer_count'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_cves")
    stats['cve_count'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_registries")
    stats['registry_count'] = cursor.fetchone()[0]
    
    # Get database size
    cursor.execute("PRAGMA page_count")
    page_count = cursor.fetchone()[0]
    cursor.execute("PRAGMA page_size")
    page_size = cursor.fetchone()[0]
    stats['db_size_mb'] = (page_count * page_size) / (1024 * 1024)
    
    conn.close()
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Backup the Open Source Risk Model database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--db-path",
        default=os.getenv("GRAPH_DB_PATH", "data/graphs.db"),
        help="Path to source database (default: data/graphs.db)"
    )
    
    parser.add_argument(
        "--output",
        default="backups",
        help="Output directory for backups (default: backups)"
    )
    
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress backup with gzip"
    )
    
    parser.add_argument(
        "--keep-days",
        type=int,
        default=30,
        help="Number of days to keep old backups (default: 30)"
    )
    
    parser.add_argument(
        "--s3-bucket",
        help="Upload backup to S3 bucket"
    )
    
    parser.add_argument(
        "--s3-prefix",
        default="open-source-risk-model",
        help="S3 key prefix (default: open-source-risk-model)"
    )
    
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics before backup"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Database Backup Utility")
    print("=" * 60)
    print()
    
    # Show database statistics
    if args.stats:
        print("Database Statistics:")
        try:
            stats = get_database_stats(args.db_path)
            print(f"  Repositories: {stats['repo_count']}")
            print(f"  Jobs: {stats['job_count']}")
            print(f"  Maintainers: {stats['maintainer_count']}")
            print(f"  CVEs: {stats['cve_count']}")
            print(f"  Registries: {stats['registry_count']}")
            print(f"  Database size: {stats['db_size_mb']:.2f} MB")
            print()
        except Exception as e:
            print(f"Failed to get statistics: {e}", file=sys.stderr)
            print()
    
    # Create backup
    try:
        backup_path = backup_database(
            db_path=args.db_path,
            output_dir=args.output,
            compress=args.compress,
            keep_days=args.keep_days
        )
        
        # Upload to S3 if requested
        if args.s3_bucket:
            upload_to_s3(backup_path, args.s3_bucket, args.s3_prefix)
        
        print()
        print("=" * 60)
        print("✓ Backup completed successfully")
        print(f"Backup file: {backup_path}")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Backup failed: {e}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
