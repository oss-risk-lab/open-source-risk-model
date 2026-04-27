"""
Tests to prevent schema drift between init_database() and actual usage.

These tests ensure that a fresh database created by init_database() supports
all operations without requiring manual ALTER TABLE commands.
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from src.open_source_risk_model.persistence.db import init_database, get_connection
from src.open_source_risk_model.persistence.dependency_repo import DependencyRepository


class TestSchemaCoherence:
    """Tests to ensure schema coherence and prevent drift."""
    
    def test_fresh_db_supports_resolution_updates(self):
        """
        T1: Fresh DB supports resolution updates.
        
        Ensures that a brand new database created by init_database()
        has all the columns needed for dependency resolution.
        """
        # Create temporary database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            
            # Initialize fresh database
            init_database(db_path)
            
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
            
            # Update resolution - this should NOT fail
            repo.update_resolution(
                repo_full_name='test/repo',
                package_name='requests',
                registry_type='pypi',
                resolved_repo='psf/requests',
                confidence=0.95,
                method='pypi_project_urls'
            )
            
            # Verify the update worked
            deps = repo.get_dependencies('test/repo')
            assert len(deps) == 1
            assert deps[0]['resolved_repo'] == 'psf/requests'
            assert deps[0]['resolution_confidence'] == 0.95
            assert deps[0]['resolution_method'] == 'pypi_project_urls'
    
    def test_multi_manifest_preservation(self):
        """
        T2: Multi-manifest preservation.
        
        Ensures that saving dependencies for one manifest doesn't delete
        dependencies from other manifests.
        """
        # Create temporary database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            
            # Initialize fresh database
            init_database(db_path)
            
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
            
            # Verify both manifests' dependencies still exist
            all_deps = repo.get_dependencies('test/repo')
            assert len(all_deps) == 2
            
            package_names = {dep['package_name'] for dep in all_deps}
            assert 'flask' in package_names
            assert 'pytest' in package_names
            
            manifest_paths = {dep['manifest_path'] for dep in all_deps}
            assert 'requirements.txt' in manifest_paths
            assert 'requirements-dev.txt' in manifest_paths
    
    def test_schema_has_resolution_columns(self):
        """
        Verify that repo_dependencies table has all required resolution columns.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            
            # Initialize fresh database
            init_database(db_path)
            
            # Check schema
            conn = get_connection(db_path)
            cursor = conn.execute("PRAGMA table_info(repo_dependencies)")
            columns = {row[1] for row in cursor.fetchall()}
            conn.close()
            
            # Verify resolution columns exist
            assert 'resolved_repo' in columns, "resolved_repo column missing"
            assert 'resolution_confidence' in columns, "resolution_confidence column missing"
            assert 'resolution_method' in columns, "resolution_method column missing"
    
    def test_schema_has_resolution_index(self):
        """
        Verify that index on resolved_repo exists.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            
            # Initialize fresh database
            init_database(db_path)
            
            # Check indexes
            conn = get_connection(db_path)
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND tbl_name='repo_dependencies'
            """)
            indexes = {row[0] for row in cursor.fetchall()}
            conn.close()
            
            # Verify resolution index exists
            assert 'idx_repo_dependencies_resolved' in indexes, "Resolution index missing"
    
    def test_schema_migration_adds_missing_columns(self):
        """
        Test that schema migration adds missing columns to existing databases.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            
            # Create database with old schema (without resolution columns)
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE repo_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name TEXT NOT NULL,
                    package_name TEXT NOT NULL,
                    registry_type TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
            
            # Run init_database (should trigger migration)
            init_database(db_path)
            
            # Verify columns were added
            conn = get_connection(db_path)
            cursor = conn.execute("PRAGMA table_info(repo_dependencies)")
            columns = {row[1] for row in cursor.fetchall()}
            conn.close()
            
            assert 'resolved_repo' in columns
            assert 'resolution_confidence' in columns
            assert 'resolution_method' in columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
