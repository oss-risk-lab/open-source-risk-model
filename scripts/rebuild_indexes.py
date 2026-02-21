#!/usr/bin/env python3
"""
Database Index Rebuild Utility

This script rebuilds database indexes to improve query performance and fix
inconsistencies between graph data and index tables.

Usage:
    python scripts/rebuild_indexes.py [options]

Examples:
    # Rebuild all indexes
    python scripts/rebuild_indexes.py

    # Rebuild indexes for specific repository
    python scripts/rebuild_indexes.py --repo numpy/numpy

    # Verify indexes without rebuilding
    python scripts/rebuild_indexes.py --verify-only

    # Rebuild with optimization
    python scripts/rebuild_indexes.py --optimize
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from typing import Dict, List, Any


def verify_indexes(conn: sqlite3.Connection, repo_full_name: str = None) -> Dict[str, Any]:
    """
    Verify index consistency with graph data.
    
    Args:
        conn: Database connection
        repo_full_name: Optional specific repository to verify
    
    Returns:
        Dictionary with verification results
    """
    cursor = conn.cursor()
    
    results = {
        'total_repos': 0,
        'verified_repos': 0,
        'inconsistencies': []
    }
    
    # Get repositories to verify
    if repo_full_name:
        cursor.execute("SELECT repo_full_name, graph_json FROM repo_graphs WHERE repo_full_name = ?", (repo_full_name,))
    else:
        cursor.execute("SELECT repo_full_name, graph_json FROM repo_graphs")
    
    repos = cursor.fetchall()
    results['total_repos'] = len(repos)
    
    print(f"Verifying indexes for {len(repos)} repositories...")
    print()
    
    for repo_name, graph_json in repos:
        graph = json.loads(graph_json)
        nodes = graph.get('nodes', [])
        
        # Count expected index entries from graph
        expected_maintainers = sum(1 for n in nodes if n.get('type') == 'maintainer')
        expected_cves = sum(1 for n in nodes if n.get('type') == 'cve')
        expected_registries = sum(1 for n in nodes if n.get('type') == 'registry')
        
        # Count actual index entries
        cursor.execute("SELECT COUNT(*) FROM repo_maintainers WHERE repo_full_name = ?", (repo_name,))
        actual_maintainers = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM repo_cves WHERE repo_full_name = ?", (repo_name,))
        actual_cves = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM repo_registries WHERE repo_full_name = ?", (repo_name,))
        actual_registries = cursor.fetchone()[0]
        
        # Check for inconsistencies
        inconsistent = False
        
        if expected_maintainers != actual_maintainers:
            results['inconsistencies'].append({
                'repo': repo_name,
                'type': 'maintainers',
                'expected': expected_maintainers,
                'actual': actual_maintainers
            })
            inconsistent = True
        
        if expected_cves != actual_cves:
            results['inconsistencies'].append({
                'repo': repo_name,
                'type': 'cves',
                'expected': expected_cves,
                'actual': actual_cves
            })
            inconsistent = True
        
        if expected_registries != actual_registries:
            results['inconsistencies'].append({
                'repo': repo_name,
                'type': 'registries',
                'expected': expected_registries,
                'actual': actual_registries
            })
            inconsistent = True
        
        if not inconsistent:
            results['verified_repos'] += 1
    
    return results


def rebuild_indexes_for_repo(conn: sqlite3.Connection, repo_full_name: str, graph_json: str) -> None:
    """
    Rebuild indexes for a single repository.
    
    Args:
        conn: Database connection
        repo_full_name: Repository identifier
        graph_json: Graph JSON string
    """
    cursor = conn.cursor()
    
    # Parse graph
    graph = json.loads(graph_json)
    nodes = graph.get('nodes', [])
    edges = graph.get('edges', [])
    
    # Build node lookup dict for O(1) access
    node_by_id = {node['id']: node for node in nodes}
    
    # Delete existing indexes
    cursor.execute("DELETE FROM repo_maintainers WHERE repo_full_name = ?", (repo_full_name,))
    cursor.execute("DELETE FROM repo_cves WHERE repo_full_name = ?", (repo_full_name,))
    cursor.execute("DELETE FROM repo_registries WHERE repo_full_name = ?", (repo_full_name,))
    
    # Rebuild maintainer indexes
    for node in nodes:
        if node.get('type') == 'maintainer':
            metadata = node.get('metadata', {})
            username = metadata.get('username')
            
            if username:
                cursor.execute("""
                    INSERT INTO repo_maintainers
                    (repo_full_name, maintainer_username, contribution_fraction, commit_count)
                    VALUES (?, ?, ?, ?)
                """, (
                    repo_full_name,
                    username,
                    metadata.get('contribution_fraction', 0.0),
                    metadata.get('commit_count', 0)
                ))
    
    # Rebuild CVE indexes
    for node in nodes:
        if node.get('type') == 'cve':
            metadata = node.get('metadata', {})
            cve_id = metadata.get('cve_id')
            
            if cve_id:
                # Find affected releases
                affected_releases = []
                for edge in edges:
                    if edge.get('target') == node['id'] and edge.get('relationship_type') == 'has_cve':
                        release_node = node_by_id.get(edge.get('source'))
                        if release_node:
                            affected_releases.append(release_node.get('metadata', {}).get('tag_name', ''))
                
                cursor.execute("""
                    INSERT INTO repo_cves
                    (repo_full_name, cve_id, severity, cvss_score, affected_releases)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    repo_full_name,
                    cve_id,
                    metadata.get('severity', 'UNKNOWN'),
                    metadata.get('cvss_score'),
                    json.dumps(affected_releases)
                ))
    
    # Rebuild registry indexes
    for node in nodes:
        if node.get('type') == 'registry':
            metadata = node.get('metadata', {})
            registry_type = metadata.get('registry_type')
            package_name = metadata.get('package_name')
            
            if registry_type and package_name:
                cursor.execute("""
                    INSERT INTO repo_registries
                    (repo_full_name, registry_type, package_name, latest_version)
                    VALUES (?, ?, ?, ?)
                """, (
                    repo_full_name,
                    registry_type,
                    package_name,
                    metadata.get('latest_version')
                ))


def rebuild_all_indexes(conn: sqlite3.Connection, repo_full_name: str = None) -> int:
    """
    Rebuild indexes for all or specific repository.
    
    Args:
        conn: Database connection
        repo_full_name: Optional specific repository
    
    Returns:
        Number of repositories processed
    """
    cursor = conn.cursor()
    
    # Get repositories to rebuild
    if repo_full_name:
        cursor.execute("SELECT repo_full_name, graph_json FROM repo_graphs WHERE repo_full_name = ?", (repo_full_name,))
    else:
        cursor.execute("SELECT repo_full_name, graph_json FROM repo_graphs")
    
    repos = cursor.fetchall()
    
    if not repos:
        print("No repositories found")
        return 0
    
    print(f"Rebuilding indexes for {len(repos)} repositories...")
    print()
    
    processed = 0
    
    for repo_name, graph_json in repos:
        try:
            rebuild_indexes_for_repo(conn, repo_name, graph_json)
            processed += 1
            
            if processed % 10 == 0:
                print(f"  Processed {processed}/{len(repos)} repositories...")
        
        except Exception as e:
            print(f"  ✗ Failed to rebuild indexes for {repo_name}: {e}", file=sys.stderr)
    
    conn.commit()
    
    print()
    print(f"✓ Rebuilt indexes for {processed} repositories")
    
    return processed


def optimize_database(conn: sqlite3.Connection) -> None:
    """
    Optimize database for better query performance.
    
    Args:
        conn: Database connection
    """
    print("\nOptimizing database...")
    
    cursor = conn.cursor()
    
    # Rebuild SQLite indexes
    print("  Rebuilding SQLite indexes...")
    cursor.execute("REINDEX")
    
    # Analyze tables for query planner
    print("  Analyzing tables...")
    cursor.execute("ANALYZE")
    
    # Checkpoint WAL file
    print("  Checkpointing WAL...")
    cursor.execute("PRAGMA wal_checkpoint(FULL)")
    
    print("✓ Database optimized")


def get_index_statistics(conn: sqlite3.Connection) -> Dict[str, int]:
    """
    Get statistics about index tables.
    
    Args:
        conn: Database connection
    
    Returns:
        Dictionary of statistics
    """
    cursor = conn.cursor()
    
    stats = {}
    
    cursor.execute("SELECT COUNT(*) FROM repo_maintainers")
    stats['maintainer_entries'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_cves")
    stats['cve_entries'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repo_registries")
    stats['registry_entries'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_maintainers")
    stats['repos_with_maintainers'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_cves")
    stats['repos_with_cves'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_registries")
    stats['repos_with_registries'] = cursor.fetchone()[0]
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild database indexes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--db-path",
        default=os.getenv("GRAPH_DB_PATH", "data/graphs.db"),
        help="Path to database (default: data/graphs.db)"
    )
    
    parser.add_argument(
        "--repo",
        help="Rebuild indexes for specific repository (owner/repo)"
    )
    
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify indexes without rebuilding"
    )
    
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Optimize database after rebuilding"
    )
    
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show index statistics"
    )
    
    args = parser.parse_args()
    
    # Validate database exists
    if not os.path.exists(args.db_path):
        print(f"✗ Database not found: {args.db_path}", file=sys.stderr)
        return 1
    
    print("=" * 60)
    print("Database Index Rebuild Utility")
    print("=" * 60)
    print()
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    
    try:
        # Show initial statistics
        print("Current Index Statistics:")
        stats_before = get_index_statistics(conn)
        print(f"  Maintainer entries: {stats_before['maintainer_entries']}")
        print(f"  CVE entries: {stats_before['cve_entries']}")
        print(f"  Registry entries: {stats_before['registry_entries']}")
        print(f"  Repos with maintainers: {stats_before['repos_with_maintainers']}")
        print(f"  Repos with CVEs: {stats_before['repos_with_cves']}")
        print(f"  Repos with registries: {stats_before['repos_with_registries']}")
        print()
        
        if args.stats:
            return 0
        
        # Verify indexes
        print("Verifying index consistency...")
        verification = verify_indexes(conn, args.repo)
        
        print(f"Verified {verification['verified_repos']}/{verification['total_repos']} repositories")
        
        if verification['inconsistencies']:
            print(f"\nFound {len(verification['inconsistencies'])} inconsistencies:")
            print()
            
            for issue in verification['inconsistencies'][:10]:  # Show first 10
                print(f"  {issue['repo']} - {issue['type']}: expected {issue['expected']}, found {issue['actual']}")
            
            if len(verification['inconsistencies']) > 10:
                print(f"  ... and {len(verification['inconsistencies']) - 10} more")
            
            print()
        else:
            print("✓ All indexes are consistent")
            print()
        
        if args.verify_only:
            return 0
        
        # Rebuild indexes if inconsistencies found or forced
        if verification['inconsistencies'] or args.repo:
            if not args.repo:
                response = input("Rebuild all indexes? (yes/no): ")
                if response.lower() not in ['yes', 'y']:
                    print("Rebuild cancelled")
                    return 0
                print()
            
            rebuild_all_indexes(conn, args.repo)
            
            # Verify after rebuild
            print("\nVerifying rebuilt indexes...")
            verification_after = verify_indexes(conn, args.repo)
            
            if verification_after['inconsistencies']:
                print(f"⚠️  Warning: {len(verification_after['inconsistencies'])} inconsistencies remain")
            else:
                print("✓ All indexes verified successfully")
        
        # Optimize database if requested
        if args.optimize:
            optimize_database(conn)
        
        # Show final statistics
        print()
        print("Final Index Statistics:")
        stats_after = get_index_statistics(conn)
        print(f"  Maintainer entries: {stats_after['maintainer_entries']} (Δ {stats_after['maintainer_entries'] - stats_before['maintainer_entries']})")
        print(f"  CVE entries: {stats_after['cve_entries']} (Δ {stats_after['cve_entries'] - stats_before['cve_entries']})")
        print(f"  Registry entries: {stats_after['registry_entries']} (Δ {stats_after['registry_entries'] - stats_before['registry_entries']})")
        
        print()
        print("=" * 60)
        print("✓ Index rebuild completed")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Index rebuild failed: {e}")
        print("=" * 60)
        return 1
    
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
