#!/usr/bin/env python3
"""
Validate data quality in the database.

Checks:
- How many repos have graphs
- How many repos have dependencies
- Resolution rates per repo
- CVE coverage
- Data completeness

Usage:
    python scripts/validate_data_quality.py [--db-path data/graphs.db]
"""

import sys
import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.persistence.db import get_connection


def get_repo_stats(db_path: str) -> Dict[str, Any]:
    """Get repository statistics."""
    conn = get_connection(db_path)
    
    # Repos with graphs
    cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
    repos_with_graphs = cursor.fetchone()[0]
    
    # Repos with dependencies
    cursor = conn.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_dependencies")
    repos_with_deps = cursor.fetchone()[0]
    
    # Total dependencies
    cursor = conn.execute("SELECT COUNT(*) FROM repo_dependencies")
    total_deps = cursor.fetchone()[0]
    
    # Resolved dependencies
    cursor = conn.execute("""
        SELECT COUNT(*) FROM repo_dependencies 
        WHERE resolved_repo IS NOT NULL AND resolved_repo != ''
    """)
    resolved_deps = cursor.fetchone()[0]
    
    # CVEs
    cursor = conn.execute("SELECT COUNT(*) FROM repo_cves")
    total_cves = cursor.fetchone()[0]
    
    # Repos with CVEs
    cursor = conn.execute("SELECT COUNT(DISTINCT repo_full_name) FROM repo_cves")
    repos_with_cves = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'repos_with_graphs': repos_with_graphs,
        'repos_with_deps': repos_with_deps,
        'total_deps': total_deps,
        'resolved_deps': resolved_deps,
        'resolution_rate': (resolved_deps / total_deps * 100) if total_deps > 0 else 0,
        'total_cves': total_cves,
        'repos_with_cves': repos_with_cves,
    }


def get_per_repo_stats(db_path: str) -> List[Dict[str, Any]]:
    """Get per-repo statistics."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT 
            rg.repo_full_name,
            rg.node_count,
            rg.edge_count,
            COUNT(DISTINCT rd.id) as dep_count,
            SUM(CASE WHEN rd.resolved_repo IS NOT NULL AND rd.resolved_repo != '' 
                THEN 1 ELSE 0 END) as resolved_count,
            COUNT(DISTINCT rc.cve_id) as cve_count
        FROM repo_graphs rg
        LEFT JOIN repo_dependencies rd ON rg.repo_full_name = rd.repo_full_name
        LEFT JOIN repo_cves rc ON rg.repo_full_name = rc.repo_full_name
        GROUP BY rg.repo_full_name
        ORDER BY dep_count DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        dep_count = row['dep_count'] or 0
        resolved_count = row['resolved_count'] or 0
        resolution_rate = (resolved_count / dep_count * 100) if dep_count > 0 else 0
        
        result.append({
            'repo': row['repo_full_name'],
            'nodes': row['node_count'],
            'edges': row['edge_count'],
            'deps': dep_count,
            'resolved': resolved_count,
            'resolution_rate': resolution_rate,
            'cves': row['cve_count'] or 0,
        })
    
    return result


def get_top_packages(db_path: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get most depended-on packages."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT 
            package_name,
            registry_type,
            COUNT(DISTINCT repo_full_name) as dependent_count,
            resolved_repo
        FROM repo_dependencies
        GROUP BY package_name, registry_type
        ORDER BY dependent_count DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def print_stats(stats: Dict[str, Any]) -> None:
    """Print overall statistics."""
    print(f"\n{'='*70}")
    print(f"OVERALL STATISTICS")
    print(f"{'='*70}")
    print(f"Repos with graphs:      {stats['repos_with_graphs']}")
    print(f"Repos with dependencies: {stats['repos_with_deps']}")
    print(f"Total dependencies:     {stats['total_deps']}")
    print(f"Resolved dependencies:  {stats['resolved_deps']} ({stats['resolution_rate']:.1f}%)")
    print(f"Total CVEs:             {stats['total_cves']}")
    print(f"Repos with CVEs:        {stats['repos_with_cves']}")
    print(f"{'='*70}\n")


def print_per_repo_stats(repo_stats: List[Dict[str, Any]]) -> None:
    """Print per-repo statistics."""
    print(f"\n{'='*70}")
    print(f"PER-REPO STATISTICS")
    print(f"{'='*70}")
    print(f"{'Repository':<35} {'Deps':<6} {'Resolved':<10} {'CVEs':<6} {'Nodes':<6}")
    print(f"{'-'*70}")
    
    for stat in repo_stats:
        resolution = f"{stat['resolved']}/{stat['deps']}" if stat['deps'] > 0 else "N/A"
        resolution_pct = f"({stat['resolution_rate']:.0f}%)" if stat['deps'] > 0 else ""
        
        print(
            f"{stat['repo']:<35} "
            f"{stat['deps']:<6} "
            f"{resolution:<5} {resolution_pct:<4} "
            f"{stat['cves']:<6} "
            f"{stat['nodes']:<6}"
        )
    
    print(f"{'='*70}\n")


def print_top_packages(packages: List[Dict[str, Any]]) -> None:
    """Print most depended-on packages."""
    print(f"\n{'='*70}")
    print(f"TOP PACKAGES (Most Depended-On)")
    print(f"{'='*70}")
    print(f"{'Package':<30} {'Registry':<10} {'Dependents':<12} {'Resolved To':<30}")
    print(f"{'-'*70}")
    
    for pkg in packages:
        resolved = pkg['resolved_repo'] or "Not resolved"
        print(
            f"{pkg['package_name']:<30} "
            f"{pkg['registry_type']:<10} "
            f"{pkg['dependent_count']:<12} "
            f"{resolved:<30}"
        )
    
    print(f"{'='*70}\n")


def check_data_quality(db_path: str) -> Dict[str, Any]:
    """Check data quality and return issues."""
    conn = get_connection(db_path)
    issues = []
    
    # Check for repos with graphs but no dependencies
    cursor = conn.execute("""
        SELECT rg.repo_full_name
        FROM repo_graphs rg
        LEFT JOIN repo_dependencies rd ON rg.repo_full_name = rd.repo_full_name
        WHERE rd.repo_full_name IS NULL
    """)
    repos_without_deps = [row[0] for row in cursor.fetchall()]
    
    if repos_without_deps:
        issues.append({
            'type': 'missing_dependencies',
            'count': len(repos_without_deps),
            'repos': repos_without_deps
        })
    
    # Check for dependencies with low resolution rates
    cursor = conn.execute("""
        SELECT 
            repo_full_name,
            COUNT(*) as total,
            SUM(CASE WHEN resolved_repo IS NOT NULL AND resolved_repo != '' 
                THEN 1 ELSE 0 END) as resolved
        FROM repo_dependencies
        GROUP BY repo_full_name
        HAVING (resolved * 1.0 / total) < 0.5
    """)
    low_resolution_repos = []
    for row in cursor.fetchall():
        low_resolution_repos.append({
            'repo': row[0],
            'total': row[1],
            'resolved': row[2],
            'rate': row[2] / row[1] * 100
        })
    
    if low_resolution_repos:
        issues.append({
            'type': 'low_resolution_rate',
            'count': len(low_resolution_repos),
            'repos': low_resolution_repos
        })
    
    conn.close()
    
    return {
        'issues': issues,
        'has_issues': len(issues) > 0
    }


def print_quality_issues(quality: Dict[str, Any]) -> None:
    """Print data quality issues."""
    if not quality['has_issues']:
        print(f"\n✅ No data quality issues found!\n")
        return
    
    print(f"\n{'='*70}")
    print(f"DATA QUALITY ISSUES")
    print(f"{'='*70}\n")
    
    for issue in quality['issues']:
        if issue['type'] == 'missing_dependencies':
            print(f"⚠️  Repos with graphs but no dependencies ({issue['count']}):")
            for repo in issue['repos']:
                print(f"   - {repo}")
            print()
        
        elif issue['type'] == 'low_resolution_rate':
            print(f"⚠️  Repos with low resolution rates (<50%) ({issue['count']}):")
            for repo_info in issue['repos']:
                print(
                    f"   - {repo_info['repo']}: "
                    f"{repo_info['resolved']}/{repo_info['total']} "
                    f"({repo_info['rate']:.0f}%)"
                )
            print()
    
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description='Validate data quality')
    parser.add_argument(
        '--db-path',
        default='data/graphs.db',
        help='Path to database (default: data/graphs.db)'
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"DATA QUALITY VALIDATION")
    print(f"{'='*70}")
    print(f"Database: {args.db_path}")
    print(f"{'='*70}")
    
    # Get statistics
    stats = get_repo_stats(args.db_path)
    repo_stats = get_per_repo_stats(args.db_path)
    top_packages = get_top_packages(args.db_path)
    quality = check_data_quality(args.db_path)
    
    # Print results
    print_stats(stats)
    print_per_repo_stats(repo_stats)
    print_top_packages(top_packages)
    print_quality_issues(quality)
    
    # Overall assessment
    print(f"\n{'='*70}")
    print(f"ASSESSMENT")
    print(f"{'='*70}")
    
    if stats['repos_with_graphs'] >= 15:
        print("✅ Good repo coverage (15+ repos)")
    elif stats['repos_with_graphs'] >= 10:
        print("⚠️  Moderate repo coverage (10-14 repos)")
    else:
        print("❌ Low repo coverage (<10 repos)")
    
    if stats['resolution_rate'] >= 80:
        print("✅ Good resolution rate (80%+)")
    elif stats['resolution_rate'] >= 60:
        print("⚠️  Moderate resolution rate (60-79%)")
    else:
        print("❌ Low resolution rate (<60%)")
    
    if not quality['has_issues']:
        print("✅ No data quality issues")
    else:
        print(f"⚠️  {len(quality['issues'])} data quality issue(s) found")
    
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
