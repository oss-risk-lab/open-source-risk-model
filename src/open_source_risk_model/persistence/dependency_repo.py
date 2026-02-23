"""
DependencyRepository implementation for dependency CRUD operations.

Provides database operations for storing and querying repository dependencies,
including direct dependencies, dependents, and package-to-repo mappings.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .db import get_connection
from .errors import DatabaseError

logger = logging.getLogger(__name__)


class DependencyRepository:
    """Repository for dependency CRUD operations."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize DependencyRepository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
    
    def save_dependencies(
        self,
        repo_full_name: str,
        dependencies: List[Dict[str, Any]]
    ) -> None:
        """
        Save dependencies for a repository.
        
        Replaces existing dependencies for the same repo+manifest combinations.
        
        Args:
            repo_full_name: Repository identifier (owner/repo)
            dependencies: List of dependency dicts with fields:
                - package_name: str
                - registry_type: str
                - specifier: str (optional)
                - extras: List[str] (optional)
                - markers: str (optional)
                - dependency_group: str (default: 'prod')
                - is_optional: bool (default: False)
                - manifest_path: str
                - confidence: float
        
        Raises:
            DatabaseError: If save fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.execute("BEGIN TRANSACTION")
            
            # Convert Dependency objects to dicts if needed
            dep_dicts = []
            for dep in dependencies:
                if hasattr(dep, 'to_dict'):
                    # It's a Dependency dataclass
                    dep_dict = dep.to_dict()
                elif isinstance(dep, dict):
                    # It's already a dict
                    dep_dict = dep
                else:
                    # Try to convert using __dict__
                    dep_dict = dep.__dict__ if hasattr(dep, '__dict__') else dep
                dep_dicts.append(dep_dict)
            
            # Get unique manifest paths
            manifest_paths = set(dep['manifest_path'] for dep in dep_dicts)
            
            # Delete existing dependencies for these manifests
            for manifest_path in manifest_paths:
                conn.execute("""
                    DELETE FROM repo_dependencies
                    WHERE repo_full_name = ? AND manifest_path = ?
                """, (repo_full_name, manifest_path))
            
            # Insert new dependencies
            now = datetime.now(timezone.utc).isoformat()
            
            # Infer registry type from manifest path
            from ..dependencies.parsers import DependencyParserRegistry
            parser_registry = DependencyParserRegistry()
            
            for dep in dep_dicts:
                # Infer registry type if not provided
                registry_type = dep.get('registry_type')
                if not registry_type:
                    registry_type = parser_registry.infer_registry_type(dep['manifest_path'])
                
                conn.execute("""
                    INSERT INTO repo_dependencies
                    (repo_full_name, package_name, registry_type, specifier,
                     extras, markers, dependency_group, is_direct, is_optional,
                     manifest_path, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    repo_full_name,
                    dep['package_name'],
                    registry_type,
                    dep.get('specifier', ''),
                    json.dumps(dep.get('extras', [])),
                    dep.get('markers', ''),
                    dep.get('dependency_group', 'prod'),
                    True,  # is_direct (always true for parsed dependencies)
                    dep.get('is_optional', False),
                    dep['manifest_path'],
                    dep.get('confidence', 0.9),
                    now
                ))
            
            conn.execute("COMMIT")
            logger.info(f"Saved {len(dependencies)} dependencies for {repo_full_name}")
        
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Failed to save dependencies for {repo_full_name}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to save dependencies: {e}")
        finally:
            conn.close()
    
    def get_dependencies(
        self,
        repo_full_name: str,
        include_dev: bool = True,
        include_optional: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get dependencies for a repository.
        
        Args:
            repo_full_name: Repository identifier
            include_dev: Include development dependencies
            include_optional: Include optional dependencies
        
        Returns:
            List of dependency dicts
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            query = """
                SELECT * FROM repo_dependencies
                WHERE repo_full_name = ?
            """
            params = [repo_full_name]
            
            if not include_dev:
                query += " AND dependency_group != 'dev'"
            
            if not include_optional:
                query += " AND is_optional = 0"
            
            query += " ORDER BY package_name"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            # Parse JSON fields
            result = []
            for row in rows:
                dep = dict(row)
                dep['extras'] = json.loads(dep['extras']) if dep['extras'] else []
                result.append(dep)
            
            return result
        
        finally:
            conn.close()
    
    def get_dependents(
        self,
        package_name: str,
        registry_type: str,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get repositories that depend on a package.
        
        Args:
            package_name: Package name
            registry_type: Registry type (pypi, npm, etc.)
            limit: Maximum results
            offset: Pagination offset
        
        Returns:
            Dict with 'dependents' list and 'total' count
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            # Get total count
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT repo_full_name) as total
                FROM repo_dependencies
                WHERE package_name = ? AND registry_type = ?
            """, (package_name, registry_type))
            
            total = cursor.fetchone()['total']
            
            # Get dependents with pagination
            cursor = conn.execute("""
                SELECT DISTINCT repo_full_name, package_name, specifier,
                       is_direct, dependency_group, confidence
                FROM repo_dependencies
                WHERE package_name = ? AND registry_type = ?
                ORDER BY repo_full_name
                LIMIT ? OFFSET ?
            """, (package_name, registry_type, limit, offset))
            
            rows = cursor.fetchall()
            dependents = [dict(row) for row in rows]
            
            return {
                'dependents': dependents,
                'total': total,
                'limit': limit,
                'offset': offset
            }
        
        finally:
            conn.close()
    
    def delete_dependencies(self, repo_full_name: str) -> None:
        """
        Delete all dependencies for a repository.
        
        Args:
            repo_full_name: Repository identifier
        
        Raises:
            DatabaseError: If delete fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.execute("""
                DELETE FROM repo_dependencies WHERE repo_full_name = ?
            """, (repo_full_name,))
            
            conn.commit()
            logger.info(f"Deleted dependencies for {repo_full_name}")
        
        except Exception as e:
            logger.error(f"Failed to delete dependencies for {repo_full_name}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to delete dependencies: {e}")
        finally:
            conn.close()


class PackageMappingRepository:
    """Repository for package-to-repo mappings."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize PackageMappingRepository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
    
    def get_mapping(
        self,
        package_name: str,
        registry_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached package-to-repo mapping.
        
        Args:
            package_name: Package name
            registry_type: Registry type
        
        Returns:
            Mapping dict or None if not found
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute("""
                SELECT * FROM package_mappings
                WHERE package_name = ? AND registry_type = ?
            """, (package_name, registry_type))
            
            row = cursor.fetchone()
            
            if row:
                mapping = dict(row)
                mapping['metadata'] = json.loads(mapping['metadata']) if mapping['metadata'] else {}
                return mapping
            
            return None
        
        finally:
            conn.close()
    
    def save_mapping(
        self,
        package_name_or_resolution,
        registry_type: Optional[str] = None,
        repo_full_name: Optional[str] = None,
        resolution_method: Optional[str] = None,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Save package-to-repo mapping.
        
        Can be called with either:
        1. A PackageResolution object
        2. Individual parameters
        
        Args:
            package_name_or_resolution: Package name or PackageResolution object
            registry_type: Registry type (if not using PackageResolution)
            repo_full_name: Resolved repository (None if unresolved)
            resolution_method: How package was resolved
            confidence: Resolution confidence (0.0-1.0)
            metadata: Additional resolution metadata
        
        Raises:
            DatabaseError: If save fails
        """
        # Handle PackageResolution object
        if hasattr(package_name_or_resolution, 'to_dict'):
            resolution_dict = package_name_or_resolution.to_dict()
            package_name = resolution_dict['package_name']
            registry_type = resolution_dict['registry_type']
            repo_full_name = resolution_dict['repo_full_name']
            resolution_method = resolution_dict['resolution_method']
            confidence = resolution_dict['confidence']
            metadata = resolution_dict['metadata']
        elif isinstance(package_name_or_resolution, dict):
            # Handle dict
            package_name = package_name_or_resolution['package_name']
            registry_type = package_name_or_resolution['registry_type']
            repo_full_name = package_name_or_resolution.get('repo_full_name')
            resolution_method = package_name_or_resolution['resolution_method']
            confidence = package_name_or_resolution['confidence']
            metadata = package_name_or_resolution.get('metadata', {})
        else:
            # Handle individual parameters
            package_name = package_name_or_resolution
        
        conn = get_connection(self.db_path)
        
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            conn.execute("""
                INSERT OR REPLACE INTO package_mappings
                (package_name, registry_type, repo_full_name, resolution_method,
                 confidence, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 
                    COALESCE((SELECT created_at FROM package_mappings 
                              WHERE package_name = ? AND registry_type = ?), ?),
                    ?)
            """, (
                package_name,
                registry_type,
                repo_full_name,
                resolution_method,
                confidence,
                json.dumps(metadata),
                package_name,
                registry_type,
                now,
                now
            ))
            
            conn.commit()
            logger.debug(f"Saved mapping: {package_name} ({registry_type}) -> {repo_full_name}")
        
        except Exception as e:
            logger.error(f"Failed to save package mapping: {e}", exc_info=True)
            raise DatabaseError(f"Failed to save package mapping: {e}")
        finally:
            conn.close()
