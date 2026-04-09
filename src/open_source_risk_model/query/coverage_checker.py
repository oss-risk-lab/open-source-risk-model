"""
Coverage checker for determining repository availability in database.

This module checks which repositories exist in the database and determines
the appropriate retrieval strategy (database-only, live ingestion, or hybrid).
"""

import logging
import re
import sqlite3
from datetime import datetime
from typing import List

from .models import CoverageReport, RepoStatus

logger = logging.getLogger(__name__)


class CoverageChecker:
    """
    Checks repository coverage in the database.
    
    Determines which repositories are available in the database and which
    require live ingestion. Sets coverage mode based on the mix of available
    and missing repositories.
    """
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize coverage checker.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
    
    def check_coverage(self, repo_identifiers: List[str]) -> CoverageReport:
        """
        Check which repositories are in database.
        
        Args:
            repo_identifiers: List of repository identifiers in owner/repo format
            
        Returns:
            CoverageReport with coverage status for each repository
            
        Example:
            >>> checker = CoverageChecker()
            >>> report = checker.check_coverage(["numpy/numpy", "invalid", "missing/repo"])
            >>> report.coverage_mode
            'hybrid'
            >>> len(report.in_database)
            1
            >>> len(report.missing)
            1
            >>> len(report.invalid)
            1
        """
        in_database = []
        missing = []
        invalid = []
        
        # Validate and categorize each repository identifier
        for repo_id in repo_identifiers:
            if not self._is_valid_repo_identifier(repo_id):
                invalid.append(repo_id)
                continue
            
            # Check if repository exists in database
            repo_status = self._query_database(repo_id)
            if repo_status:
                in_database.append(repo_status)
            else:
                missing.append(repo_id)
        
        # Determine coverage mode
        coverage_mode = self._determine_coverage_mode(in_database, missing)
        
        return CoverageReport(
            coverage_mode=coverage_mode,
            in_database=in_database,
            missing=missing,
            invalid=invalid
        )
    
    def _is_valid_repo_identifier(self, repo_id: str) -> bool:
        """
        Validate repository identifier format.
        
        Args:
            repo_id: Repository identifier to validate
            
        Returns:
            True if valid owner/repo format, False otherwise
        """
        # Must be in owner/repo format
        pattern = r'^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$'
        return bool(re.match(pattern, repo_id))
    
    def _query_database(self, repo_id: str) -> RepoStatus | None:
        """
        Query database for repository information.
        
        Args:
            repo_id: Repository identifier in owner/repo format
            
        Returns:
            RepoStatus if found, None otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Query repo_graphs table for repository data
            cursor.execute("""
                SELECT 
                    repo_full_name,
                    updated_at,
                    data_sources
                FROM repo_graphs
                WHERE repo_full_name = ?
            """, (repo_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                # Parse updated_at timestamp
                try:
                    last_updated = datetime.fromisoformat(row['updated_at'])
                except (ValueError, TypeError):
                    # Fallback to current time if parsing fails
                    last_updated = datetime.now()
                
                # Determine score completeness based on data sources
                # For now, assume all database entries are "full"
                # This can be enhanced later to check actual data completeness
                score_completeness = "full"
                
                return RepoStatus(
                    repo_full_name=row['repo_full_name'],
                    last_updated=last_updated,
                    score_completeness=score_completeness
                )
            
            return None
            
        except sqlite3.Error as e:
            logger.error(f"Database error checking coverage for {repo_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error checking coverage for {repo_id}: {e}")
            return None
    
    def _determine_coverage_mode(
        self,
        in_database: List[RepoStatus],
        missing: List[str]
    ) -> str:
        """
        Determine coverage mode based on repository availability.
        
        Args:
            in_database: List of repositories found in database
            missing: List of repositories not found in database
            
        Returns:
            Coverage mode: "database_only", "live_ingestion_required", or "hybrid"
        """
        has_database = len(in_database) > 0
        has_missing = len(missing) > 0
        
        if has_database and not has_missing:
            return "database_only"
        elif has_missing and not has_database:
            return "live_ingestion_required"
        elif has_database and has_missing:
            return "hybrid"
        else:
            # No valid repositories at all (all invalid)
            return "live_ingestion_required"
