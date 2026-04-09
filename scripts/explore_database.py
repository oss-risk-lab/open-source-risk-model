#!/usr/bin/env python3
"""
Interactive database explorer for the Open Source Risk Model database.

Usage:
    python scripts/explore_database.py [command]

Commands:
    list-repos              List all repositories
    list-repos-with-deps    List repos with dependency counts
    show-deps REPO          Show dependencies for a specific repo
    stats                   Show database statistics
    top-packages N          Show top N most used packages
    search TERM             Search for repos containing TERM
"""

import sqlite3
import sys
from pathlib import Path


def get_db_connection():
    """Get database connection."""
    db_path = Path("data/graphs.db")
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    return sqlite3.connect(db_path)


def list_repos(conn):
    """List all repositories."""
    cursor = conn.execute("""
        SELECT repo_full_name, node_count, edge_count, 
               datetime(created_at) as created
        FROM repo_graphs
        ORDER BY repo_full_name
    """)
    
    print(f"\n{'Repository':<50} {'Nodes':<8} {'Edges':<8} {'Created':<20}")
    print("=" * 90)
    
    for row in cursor:
        print(f"{row[0]:<50} {row[1]:<8} {row[2]:<8} {row[3]:<20}")
    
    count = conn.execute("SELECT COUNT(*) FROM repo_graphs").fetchone()[0]
    print(f"\nTotal: {count} repositories")


def list_repos_with_deps(conn):
    """List repositories with dependency counts."""
    cursor = conn.execute("""
        SELECT 
            rg.repo_full_name,
            COUNT(DISTINCT rd.package_name) as dep_count,
            SUM(CASE WHEN rd.resolved_repo IS NOT NULL THEN 1 ELSE 0 END) as resolved_count,
            COUNT(DISTINCT rd.manifest_path) as manifest_count
        FROM repo_graphs rg
        LEFT JOIN repo_dependencies rd ON rg.repo_full_name = rd.repo_full_name
        GROUP BY rg.repo_full_name
        ORDER BY dep_count DESC
    """)
    
    print(f"\n{'Repository':<50} {'Deps':<8} {'Resolved':<10} {'Manifests':<10}")
    print("=" * 80)
    
    for row in cursor:
        repo, deps, resolved, manifests = row
        res_pct = f"{resolved}/{deps}" if deps > 0 else "0/0"
        print(f"{repo:<50} {deps:<8} {res_pct:<10} {manifests:<10}")


def show_deps(conn, repo_name):
    """Show dependencies for a specific repository."""
    cursor = conn.execute("""
        SELECT 
            package_name,
            registry_type,
            specifier,
            dependency_group,
            is_direct,
            resolved_repo,
            manifest_path
        FROM repo_dependencies
        WHERE repo_full_name = ?
        ORDER BY is_direct DESC, package_name
    """, (repo_name,))
    
    rows = cursor.fetchall()
    if not rows:
        print(f"\nNo dependencies found for {repo_name}")
        return
    
    print(f"\nDependencies for {repo_name}:")
    print("=" * 100)
    print(f"{'Package':<40} {'Registry':<12} {'Version':<15} {'Type':<8} {'Resolved To':<30}")
    print("-" * 100)
    
    for row in rows:
        pkg, reg, spec, group, direct, resolved, manifest = row
        direct_str = "direct" if direct else "trans"
        spec_str = spec or "any"
        resolved_str = resolved or "unresolved"
        print(f"{pkg:<40} {reg:<12} {spec_str:<15} {direct_str:<8} {resolved_str:<30}")
    
    print(f"\nTotal: {len(rows)} dependencies")


def show_stats(conn):
    """Show database statistics."""
    stats = conn.execute("""
        SELECT 
            COUNT(DISTINCT rg.repo_full_name) as repo_count,
            COUNT(DISTINCT rd.package_name) as unique_packages,
            COUNT(*) as total_deps,
            SUM(CASE WHEN rd.resolved_repo IS NOT NULL THEN 1 ELSE 0 END) as resolved_deps,
            COUNT(DISTINCT rd.manifest_path) as total_manifests,
            COUNT(DISTINCT CASE WHEN rd.package_name IS NOT NULL THEN rd.repo_full_name END) as repos_with_deps
        FROM repo_graphs rg
        LEFT JOIN repo_dependencies rd ON rg.repo_full_name = rd.repo_full_name
    """).fetchone()
    
    repo_count, unique_pkgs, total_deps, resolved, manifests, repos_with_deps = stats
    resolution_rate = (resolved / total_deps * 100) if total_deps > 0 else 0
    
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)
    print(f"Total Repositories:        {repo_count:>8}")
    print(f"Repos with Dependencies:   {repos_with_deps:>8} ({repos_with_deps/repo_count*100:.1f}%)")
    print(f"Total Dependencies:        {total_deps:>8}")
    print(f"Unique Packages:           {unique_pkgs:>8}")
    print(f"Resolved Dependencies:     {resolved:>8} ({resolution_rate:.1f}%)")
    print(f"Total Manifests:           {manifests:>8}")
    print("=" * 60)
    
    # Registry breakdown
    print("\nDependencies by Registry:")
    cursor = conn.execute("""
        SELECT registry_type, COUNT(*) as count
        FROM repo_dependencies
        GROUP BY registry_type
        ORDER BY count DESC
    """)
    for reg, count in cursor:
        print(f"  {reg:<15} {count:>6}")
    
    # Dependency groups
    print("\nDependencies by Type:")
    cursor = conn.execute("""
        SELECT dependency_group, COUNT(*) as count
        FROM repo_dependencies
        GROUP BY dependency_group
        ORDER BY count DESC
    """)
    for group, count in cursor:
        print(f"  {group:<15} {count:>6}")


def top_packages(conn, n=20):
    """Show top N most used packages."""
    cursor = conn.execute("""
        SELECT 
            package_name,
            registry_type,
            COUNT(DISTINCT repo_full_name) as repo_count,
            COUNT(*) as total_uses
        FROM repo_dependencies
        GROUP BY package_name, registry_type
        ORDER BY repo_count DESC, total_uses DESC
        LIMIT ?
    """, (n,))
    
    print(f"\nTop {n} Most Used Packages:")
    print("=" * 80)
    print(f"{'Package':<40} {'Registry':<12} {'Repos':<8} {'Total Uses':<12}")
    print("-" * 80)
    
    for row in cursor:
        pkg, reg, repos, uses = row
        print(f"{pkg:<40} {reg:<12} {repos:<8} {uses:<12}")


def search_repos(conn, term):
    """Search for repositories containing term."""
    cursor = conn.execute("""
        SELECT repo_full_name, node_count, edge_count
        FROM repo_graphs
        WHERE repo_full_name LIKE ?
        ORDER BY repo_full_name
    """, (f"%{term}%",))
    
    rows = cursor.fetchall()
    if not rows:
        print(f"\nNo repositories found matching '{term}'")
        return
    
    print(f"\nRepositories matching '{term}':")
    print("=" * 70)
    for repo, nodes, edges in rows:
        print(f"  {repo}")
    print(f"\nFound {len(rows)} repositories")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    conn = get_db_connection()
    
    try:
        if command == "list-repos":
            list_repos(conn)
        elif command == "list-repos-with-deps":
            list_repos_with_deps(conn)
        elif command == "show-deps":
            if len(sys.argv) < 3:
                print("Error: Please provide a repository name")
                print("Example: python scripts/explore_database.py show-deps django/django")
                sys.exit(1)
            show_deps(conn, sys.argv[2])
        elif command == "stats":
            show_stats(conn)
        elif command == "top-packages":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            top_packages(conn, n)
        elif command == "search":
            if len(sys.argv) < 3:
                print("Error: Please provide a search term")
                sys.exit(1)
            search_repos(conn, sys.argv[2])
        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
