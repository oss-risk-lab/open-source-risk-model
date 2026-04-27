#!/usr/bin/env python3
"""
Simple test script to verify schema coherence without pytest dependency.
"""

import sqlite3
import tempfile
import os
import sys

# Add src to path
sys.path.insert(0, '.')

from src.open_source_risk_model.persistence.db import init_database, get_connection
from src.open_source_risk_model.persistence.dependency_repo import DependencyRepository


def test_fresh_db_supports_resolution_updates():
    """T1: Fresh DB supports resolution updates."""
    print("=" * 60)
    print("TEST 1: Fresh DB Supports Resolution Updates")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Initialize fresh database
        init_database(db_path)
        print("✓ Fresh database initialized")
        
        # Create repository entry (required for foreign key)
        conn = get_connection(db_path)
        conn.execute("""
            INSERT INTO repo_graphs 
            (repo_full_name, graph_json, schema_version, node_count, edge_count, 
             created_at, updated_at, data_sources)
            VALUES (?, '{}', '1.0', 0, 0, datetime('now'), datetime('now'), '[]')
        """, ('test/repo',))
        conn.commit()
        conn.close()
        print("✓ Repo graph entry created")
        
        # Create repository
        repo = DependencyRepository(db_path)
        
        # Insert a test dependency
        test_dep = {
            'package_name': 'requests',
            'registry_type': 'pypi',
            'specifier': '>=2.28.0',
            'extras': [],
            'markers': '',
            'dependency_group': 'prod',
            'is_optional': False,
            'manifest_path': 'requirements.txt',
            'confidence': 0.9
        }
        
        repo.save_dependencies('test/repo', [test_dep])
        print("✓ Test dependency saved")
        
        # Update resolution - this should NOT fail
        repo.update_resolution(
            repo_full_name='test/repo',
            package_name='requests',
            registry_type='pypi',
            resolved_repo='psf/requests',
            confidence=0.95,
            method='pypi_project_urls'
        )
        print("✓ Resolution updated successfully")
        
        # Verify the update worked
        deps = repo.get_dependencies('test/repo')
        assert len(deps) == 1, f"Expected 1 dependency, got {len(deps)}"
        assert deps[0]['resolved_repo'] == 'psf/requests', f"Expected psf/requests, got {deps[0]['resolved_repo']}"
        assert deps[0]['resolution_confidence'] == 0.95, f"Expected 0.95, got {deps[0]['resolution_confidence']}"
        assert deps[0]['resolution_method'] == 'pypi_project_urls', f"Expected pypi_project_urls, got {deps[0]['resolution_method']}"
        print("✓ Resolution data verified")
        
        print("\n✅ TEST 1 PASSED\n")
        return True


def test_multi_manifest_preservation():
    """T2: Multi-manifest preservation."""
    print("=" * 60)
    print("TEST 2: Multi-Manifest Preservation")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Initialize fresh database
        init_database(db_path)
        print("✓ Fresh database initialized")
        
        # Create repository entry (required for foreign key)
        conn = get_connection(db_path)
        conn.execute("""
            INSERT INTO repo_graphs 
            (repo_full_name, graph_json, schema_version, node_count, edge_count, 
             created_at, updated_at, data_sources)
            VALUES (?, '{}', '1.0', 0, 0, datetime('now'), datetime('now'), '[]')
        """, ('test/repo',))
        conn.commit()
        conn.close()
        print("✓ Repo graph entry created")
        
        # Create repository
        repo = DependencyRepository(db_path)
        
        # Save dependencies for manifest A
        deps_a = [{
            'package_name': 'flask',
            'registry_type': 'pypi',
            'specifier': '>=2.0.0',
            'extras': [],
            'markers': '',
            'dependency_group': 'prod',
            'is_optional': False,
            'manifest_path': 'requirements.txt',
            'confidence': 0.9
        }]
        
        repo.save_dependencies('test/repo', deps_a)
        print("✓ Manifest A dependencies saved")
        
        # Save dependencies for manifest B
        deps_b = [{
            'package_name': 'pytest',
            'registry_type': 'pypi',
            'specifier': '>=7.0.0',
            'extras': [],
            'markers': '',
            'dependency_group': 'dev',
            'is_optional': False,
            'manifest_path': 'requirements-dev.txt',
            'confidence': 0.9
        }]
        
        repo.save_dependencies('test/repo', deps_b)
        print("✓ Manifest B dependencies saved")
        
        # Verify both manifests' dependencies still exist
        all_deps = repo.get_dependencies('test/repo')
        assert len(all_deps) == 2, f"Expected 2 dependencies, got {len(all_deps)}"
        
        package_names = {dep['package_name'] for dep in all_deps}
        assert 'flask' in package_names, "flask dependency missing"
        assert 'pytest' in package_names, "pytest dependency missing"
        
        manifest_paths = {dep['manifest_path'] for dep in all_deps}
        assert 'requirements.txt' in manifest_paths, "requirements.txt manifest missing"
        assert 'requirements-dev.txt' in manifest_paths, "requirements-dev.txt manifest missing"
        print("✓ Both manifests preserved")
        
        print("\n✅ TEST 2 PASSED\n")
        return True


def test_schema_has_resolution_columns():
    """Verify that repo_dependencies table has all required resolution columns."""
    print("=" * 60)
    print("TEST 3: Schema Has Resolution Columns")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Initialize fresh database
        init_database(db_path)
        print("✓ Fresh database initialized")
        
        # Check schema
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA table_info(repo_dependencies)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        
        # Verify resolution columns exist
        assert 'resolved_repo' in columns, "resolved_repo column missing"
        assert 'resolution_confidence' in columns, "resolution_confidence column missing"
        assert 'resolution_method' in columns, "resolution_method column missing"
        print("✓ All resolution columns present")
        
        print("\n✅ TEST 3 PASSED\n")
        return True


def test_schema_migration_adds_missing_columns():
    """Test that schema migration adds missing columns to existing databases."""
    print("=" * 60)
    print("TEST 4: Schema Migration Adds Missing Columns")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Create database with old schema (without resolution columns)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            
            CREATE TABLE repo_graphs (
                repo_full_name TEXT PRIMARY KEY,
                graph_json TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                node_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data_sources TEXT NOT NULL
            );
            
            CREATE TABLE repo_dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_full_name TEXT NOT NULL,
                package_name TEXT NOT NULL,
                registry_type TEXT NOT NULL,
                specifier TEXT,
                extras TEXT,
                markers TEXT,
                dependency_group TEXT DEFAULT 'prod',
                is_direct BOOLEAN NOT NULL DEFAULT 1,
                is_optional BOOLEAN NOT NULL DEFAULT 0,
                manifest_path TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
            );
        """)
        conn.commit()
        conn.close()
        print("✓ Old schema database created (without resolution columns)")
        
        # Run init_database (should trigger migration)
        init_database(db_path)
        print("✓ Migration triggered")
        
        # Verify columns were added
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA table_info(repo_dependencies)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        
        assert 'resolved_repo' in columns, "resolved_repo column not added by migration"
        assert 'resolution_confidence' in columns, "resolution_confidence column not added by migration"
        assert 'resolution_method' in columns, "resolution_method column not added by migration"
        print("✓ All columns added by migration")
        
        print("\n✅ TEST 4 PASSED\n")
        return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SCHEMA COHERENCE TEST SUITE")
    print("Prevents 'works on my machine' drift")
    print("=" * 60 + "\n")
    
    results = []
    
    try:
        results.append(("Fresh DB Resolution Updates", test_fresh_db_supports_resolution_updates()))
    except Exception as e:
        print(f"❌ TEST 1 FAILED: {e}\n")
        results.append(("Fresh DB Resolution Updates", False))
    
    try:
        results.append(("Multi-Manifest Preservation", test_multi_manifest_preservation()))
    except Exception as e:
        print(f"❌ TEST 2 FAILED: {e}\n")
        results.append(("Multi-Manifest Preservation", False))
    
    try:
        results.append(("Schema Has Resolution Columns", test_schema_has_resolution_columns()))
    except Exception as e:
        print(f"❌ TEST 3 FAILED: {e}\n")
        results.append(("Schema Has Resolution Columns", False))
    
    try:
        results.append(("Schema Migration", test_schema_migration_adds_missing_columns()))
    except Exception as e:
        print(f"❌ TEST 4 FAILED: {e}\n")
        results.append(("Schema Migration", False))
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<45} {status}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Schema is coherent and portable.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    exit(main())
