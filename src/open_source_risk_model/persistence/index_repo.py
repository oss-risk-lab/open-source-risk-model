"""
IndexRepository implementation for cross-repo indexed lookups.

Provides fast query operations across multiple repositories using
denormalized index tables for maintainers, CVEs, and registries.
"""

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from .db import get_connection
from .errors import DatabaseError

logger = logging.getLogger(__name__)


class IndexRepository:
    """Repository for cross-repo indexed lookups."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize IndexRepository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
    
    def find_repos_by_maintainer(
        self,
        username: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all repositories maintained by a user.
        
        Uses the repo_maintainers index table for fast lookups.
        
        Args:
            username: GitHub username
            limit: Maximum results
        
        Returns:
            List of dicts with repo_full_name, contribution_fraction, commit_count
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT repo_full_name, contribution_fraction, commit_count
                FROM repo_maintainers
                WHERE maintainer_username = ?
                ORDER BY contribution_fraction DESC
                LIMIT ?
            """, (username, limit))
            
            rows = cursor.fetchall()
            
            results = [
                {
                    "repo_full_name": row["repo_full_name"],
                    "contribution_fraction": row["contribution_fraction"],
                    "commit_count": row["commit_count"]
                }
                for row in rows
            ]
            
            logger.info(f"Found {len(results)} repos for maintainer {username}")
            return results
        
        except Exception as e:
            logger.error(f"Failed to find repos by maintainer {username}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to query repos by maintainer: {e}")
        finally:
            conn.close()
    
    def find_repos_by_cve(
        self,
        cve_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all repositories affected by a CVE.
        
        Uses the repo_cves index table for fast lookups.
        
        Args:
            cve_id: CVE identifier (e.g., "CVE-2024-1234")
            limit: Maximum results
        
        Returns:
            List of dicts with repo_full_name, severity, cvss_score, affected_releases
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT repo_full_name, severity, cvss_score, affected_releases
                FROM repo_cves
                WHERE cve_id = ?
                ORDER BY cvss_score DESC NULLS LAST
                LIMIT ?
            """, (cve_id, limit))
            
            rows = cursor.fetchall()
            
            results = [
                {
                    "repo_full_name": row["repo_full_name"],
                    "severity": row["severity"],
                    "cvss_score": row["cvss_score"],
                    "affected_releases": json.loads(row["affected_releases"]) if row["affected_releases"] else []
                }
                for row in rows
            ]
            
            logger.info(f"Found {len(results)} repos affected by {cve_id}")
            return results
        
        except Exception as e:
            logger.error(f"Failed to find repos by CVE {cve_id}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to query repos by CVE: {e}")
        finally:
            conn.close()
    
    def find_repo_by_package(
        self,
        registry_type: str,
        package_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find repository for a package in a registry.
        
        Uses the repo_registries index table for fast lookups.
        
        Args:
            registry_type: Registry type (pypi, npm, maven, etc.)
            package_name: Package name
        
        Returns:
            Dict with repo_full_name, latest_version, or None if not found
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT repo_full_name, latest_version
                FROM repo_registries
                WHERE registry_type = ? AND package_name = ?
                LIMIT 1
            """, (registry_type, package_name))
            
            row = cursor.fetchone()
            
            if not row:
                logger.info(f"No repo found for package {registry_type}:{package_name}")
                return None
            
            result = {
                "repo_full_name": row["repo_full_name"],
                "registry_type": registry_type,
                "package_name": package_name,
                "latest_version": row["latest_version"]
            }
            
            logger.info(f"Found repo {result['repo_full_name']} for package {registry_type}:{package_name}")
            return result
        
        except Exception as e:
            logger.error(f"Failed to find repo by package {registry_type}:{package_name}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to query repo by package: {e}")
        finally:
            conn.close()
    
    def find_repos_sharing_maintainer(
        self,
        repo_full_name: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find repositories sharing maintainers with the given repo.
        
        Uses the repo_maintainers index table to find repos with common maintainers.
        
        Args:
            repo_full_name: Reference repository
            limit: Maximum results
        
        Returns:
            List of dicts with repo_full_name, shared_maintainers (list of usernames)
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            # First, get maintainers of the reference repo
            cursor = conn.execute("""
                SELECT maintainer_username
                FROM repo_maintainers
                WHERE repo_full_name = ?
            """, (repo_full_name,))
            
            maintainers = [row["maintainer_username"] for row in cursor.fetchall()]
            
            if not maintainers:
                logger.info(f"No maintainers found for {repo_full_name}")
                return []
            
            # Find other repos with any of these maintainers
            # Use a parameterized query with placeholders
            placeholders = ','.join('?' * len(maintainers))
            query = f"""
                SELECT repo_full_name, maintainer_username
                FROM repo_maintainers
                WHERE maintainer_username IN ({placeholders})
                  AND repo_full_name != ?
                ORDER BY repo_full_name
            """
            
            cursor = conn.execute(query, maintainers + [repo_full_name])
            rows = cursor.fetchall()
            
            # Group by repo and collect shared maintainers
            repos_dict: Dict[str, List[str]] = {}
            for row in rows:
                repo = row["repo_full_name"]
                maintainer = row["maintainer_username"]
                if repo not in repos_dict:
                    repos_dict[repo] = []
                repos_dict[repo].append(maintainer)
            
            # Convert to list format and apply limit
            results = [
                {
                    "repo_full_name": repo,
                    "shared_maintainers": maintainers_list
                }
                for repo, maintainers_list in sorted(
                    repos_dict.items(),
                    key=lambda x: len(x[1]),
                    reverse=True
                )
            ][:limit]
            
            logger.info(f"Found {len(results)} repos sharing maintainers with {repo_full_name}")
            return results
        
        except Exception as e:
            logger.error(f"Failed to find repos sharing maintainer with {repo_full_name}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to query repos sharing maintainer: {e}")
        finally:
            conn.close()
