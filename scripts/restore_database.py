#!/usr/bin/env python3
"""
Database Restore Utility

This script restores the SQLite database from a backup file.

Usage:
    python scripts/restore_database.py <backup_file> [options]

Examples:
    # Basic restore
    python scripts/restore_database.py backups/graphs_20260220_120000.db

    # Restore from compressed backup
    python scripts/restore_database.py backups/graphs_20260220_120000.db.gz

    # Restore to custom location
    python scripts/restore_database.py backups/graphs_20260220_120000.db --db-path /var/lib/graphs.db

    # Restore without backup of current database
    python scripts/restore_database.py backups/graphs_20260220_120000.db --no-backup
"""

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def verify_backup_integrity(backup_path: str) -> bool:
    """
    Verify the integrity of a backup file.
    
    Args:
        backup_path: Path to backup file
    
    Returns:
        True if backup is valid, False otherwise
    """
    print(f"Verifying backup integrity: {backup_path}")
    
    try:
        conn = sqlite3.connect(backup_path)
        cursor = conn.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        conn.close()
        
        if result != "ok":
            print(f"✗ Integrity check failed: {result}", file=sys.stderr)
            return False
        
        print("✓ Backup integrity verified")
        return True
        
    except Exception as e:
        print(f"✗ Failed to verify backup: {e}", file=sys.stderr)
        return False


def get_backup_info(backup_path: str) -> dict:
    """
    Get information about a backup file.
    
    Args:
        backup_path: Path to backup file
    
    Returns:
        Dictionary with backup information
    """
    info = {}
    
    # File size
    info['size_mb'] = os.path.getsize(backup_path) / (1024 * 1024)
    
    # Modification time
    mtime = os.path.getmtime(backup_path)
    info['created_at'] = datetime.fromtimestamp(mtime).isoformat()
    
    # Database statistics
    try:
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM repo_graphs")
        info['repo_count'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM ingestion_jobs")
        info['job_count'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        info['schema_version'] = cursor.fetchone()[0]
        
        conn.close()
        
    except Exception as e:
        print(f"Warning: Could not read backup statistics: {e}", file=sys.stderr)
    
    return info


def backup_current_database(db_path: str) -> str:
    """
    Create a backup of the current database before restore.
    
    Args:
        db_path: Path to current database
    
    Returns:
        Path to backup file
    """
    if not os.path.exists(db_path):
        print("No existing database to backup")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.before_restore_{timestamp}"
    
    print(f"Backing up current database to: {backup_path}")
    
    try:
        shutil.copy2(db_path, backup_path)
        print("✓ Current database backed up")
        return backup_path
        
    except Exception as e:
        print(f"✗ Failed to backup current database: {e}", file=sys.stderr)
        raise


def decompress_backup(compressed_path: str, output_path: str) -> None:
    """
    Decompress a gzipped backup file.
    
    Args:
        compressed_path: Path to compressed backup
        output_path: Path for decompressed file
    """
    print(f"Decompressing backup...")
    
    try:
        with gzip.open(compressed_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        print("✓ Backup decompressed")
        
    except Exception as e:
        print(f"✗ Decompression failed: {e}", file=sys.stderr)
        if os.path.exists(output_path):
            os.remove(output_path)
        raise


def restore_database(
    backup_path: str,
    db_path: str,
    create_backup: bool = True,
    verify: bool = True
) -> None:
    """
    Restore database from backup.
    
    Args:
        backup_path: Path to backup file
        db_path: Path to target database
        create_backup: Whether to backup current database first
        verify: Whether to verify backup integrity
    """
    # Check if backup file exists
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    
    # Handle compressed backups
    is_compressed = backup_path.endswith('.gz')
    temp_backup = None
    
    if is_compressed:
        temp_backup = backup_path[:-3]  # Remove .gz extension
        decompress_backup(backup_path, temp_backup)
        backup_to_restore = temp_backup
    else:
        backup_to_restore = backup_path
    
    # Verify backup integrity
    if verify:
        if not verify_backup_integrity(backup_to_restore):
            if temp_backup and os.path.exists(temp_backup):
                os.remove(temp_backup)
            raise ValueError("Backup integrity check failed")
    
    # Show backup information
    print("\nBackup Information:")
    info = get_backup_info(backup_to_restore)
    print(f"  Size: {info['size_mb']:.2f} MB")
    print(f"  Created: {info.get('created_at', 'Unknown')}")
    print(f"  Repositories: {info.get('repo_count', 'Unknown')}")
    print(f"  Jobs: {info.get('job_count', 'Unknown')}")
    print(f"  Schema version: {info.get('schema_version', 'Unknown')}")
    print()
    
    # Backup current database
    current_backup = None
    if create_backup and os.path.exists(db_path):
        current_backup = backup_current_database(db_path)
    
    # Perform restore
    print(f"Restoring database to: {db_path}")
    
    try:
        # Ensure target directory exists
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        
        # Copy backup to target location
        shutil.copy2(backup_to_restore, db_path)
        
        print("✓ Database restored successfully")
        
        # Verify restored database
        if verify:
            print("Verifying restored database...")
            if not verify_backup_integrity(db_path):
                raise ValueError("Restored database integrity check failed")
        
    except Exception as e:
        print(f"✗ Restore failed: {e}", file=sys.stderr)
        
        # Attempt to restore from backup of current database
        if current_backup and os.path.exists(current_backup):
            print("Attempting to restore previous database...")
            try:
                shutil.copy2(current_backup, db_path)
                print("✓ Previous database restored")
            except Exception as restore_error:
                print(f"✗ Failed to restore previous database: {restore_error}", file=sys.stderr)
        
        raise
    
    finally:
        # Clean up temporary files
        if temp_backup and os.path.exists(temp_backup):
            os.remove(temp_backup)


def list_available_backups(backup_dir: str) -> list:
    """
    List available backup files in a directory.
    
    Args:
        backup_dir: Directory containing backups
    
    Returns:
        List of backup file paths
    """
    if not os.path.exists(backup_dir):
        return []
    
    backups = []
    
    for filename in sorted(os.listdir(backup_dir), reverse=True):
        if filename.startswith("graphs_") and (filename.endswith(".db") or filename.endswith(".db.gz")):
            filepath = os.path.join(backup_dir, filename)
            backups.append(filepath)
    
    return backups


def main():
    parser = argparse.ArgumentParser(
        description="Restore the Open Source Risk Model database from backup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "backup_file",
        nargs='?',
        help="Path to backup file (.db or .db.gz)"
    )
    
    parser.add_argument(
        "--db-path",
        default=os.getenv("GRAPH_DB_PATH", "data/graphs.db"),
        help="Path to target database (default: data/graphs.db)"
    )
    
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't backup current database before restore"
    )
    
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip integrity verification"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available backups in backups/ directory"
    )
    
    parser.add_argument(
        "--backup-dir",
        default="backups",
        help="Directory to search for backups (default: backups)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Database Restore Utility")
    print("=" * 60)
    print()
    
    # List available backups
    if args.list:
        backups = list_available_backups(args.backup_dir)
        
        if not backups:
            print(f"No backups found in {args.backup_dir}")
            return 0
        
        print(f"Available backups in {args.backup_dir}:")
        print()
        
        for backup_path in backups:
            filename = os.path.basename(backup_path)
            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            mtime = datetime.fromtimestamp(os.path.getmtime(backup_path))
            
            print(f"  {filename}")
            print(f"    Size: {size_mb:.2f} MB")
            print(f"    Date: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
        
        return 0
    
    # Require backup file
    if not args.backup_file:
        parser.error("backup_file is required (or use --list to see available backups)")
    
    # Confirm restore operation
    print(f"Source backup: {args.backup_file}")
    print(f"Target database: {args.db_path}")
    print()
    
    if os.path.exists(args.db_path):
        print("⚠️  WARNING: This will overwrite the existing database!")
        
        if not args.no_backup:
            print("   (Current database will be backed up first)")
        
        print()
        response = input("Continue with restore? (yes/no): ")
        
        if response.lower() not in ['yes', 'y']:
            print("Restore cancelled")
            return 0
        
        print()
    
    # Perform restore
    try:
        restore_database(
            backup_path=args.backup_file,
            db_path=args.db_path,
            create_backup=not args.no_backup,
            verify=not args.no_verify
        )
        
        print()
        print("=" * 60)
        print("✓ Restore completed successfully")
        print()
        print("Next steps:")
        print("  1. Restart the API server")
        print("  2. Verify the application works correctly")
        print("  3. Check logs for any errors")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Restore failed: {e}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
