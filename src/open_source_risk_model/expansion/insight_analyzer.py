"""Signal quality analysis for dataset expansion.

This module provides tools to analyze cross-repository insights and validate
that dataset expansion produces actionable intelligence beyond just data volume.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import sqlite3
from pathlib import Path


@dataclass
class HubPackage:
    """A package used across many repositories."""
    package_name: str
    registry_type: str
    repo_count: int
    usage_percentage: float
    example_repos: List[str]


@dataclass
class FootprintMetric:
    """Transitive dependency footprint for a package."""
    package_name: str
    registry_type: str
    transitive_count: int
    direct_dependents: int


@dataclass
class EcosystemPattern:
    """Ecosystem-specific dependency pattern."""
    ecosystem: str
    pattern_type: str
    description: str
    example_count: int
    examples: List[Dict[str, Any]]


@dataclass
class InsightAnalysis:
    """Cross-repository insight analysis results."""
    hub_packages: List[HubPackage]
    large_footprints: List[FootprintMetric]
    ecosystem_patterns: List[EcosystemPattern]
    new_insights_count: int
    baseline_comparison: Dict[str, Any]


class SignalQualityAnalyzer:
    """Analyze cross-repository insights and signal quality."""
    
    def __init__(self, db_path: str):
        """Initialize with database connection.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def find_hub_packages(
        self,
        min_usage_pct: float = 0.25,
        max_results: int = 50
    ) -> List[HubPackage]:
        """Find packages used by >25% of repositories.
        
        Args:
            min_usage_pct: Minimum usage percentage (default: 0.25 = 25%)
            max_results: Maximum number of results to return
        
        Returns:
            List of HubPackage with usage metrics
        """
        conn = self._get_connection()
        
        try:
            # Get total repo count
            cursor = conn.execute("SELECT COUNT(*) as count FROM repo_graphs")
            total_repos = cursor.fetchone()['count']
            
            if total_repos == 0:
                return []
            
            min_repos = int(total_repos * min_usage_pct)
            
            # Find packages used by many repos
            query = """
                SELECT 
                    package_name,
                    registry_type,
                    COUNT(DISTINCT repo_full_name) as repo_count
                FROM repo_dependencies
                WHERE package_name IS NOT NULL
                  AND registry_type IS NOT NULL
                GROUP BY package_name, registry_type
                HAVING repo_count >= ?
                ORDER BY repo_count DESC
                LIMIT ?
            """
            
            cursor = conn.execute(query, (min_repos, max_results))
            results = cursor.fetchall()
            
            hubs = []
            for row in results:
                package_name = row['package_name']
                registry_type = row['registry_type']
                repo_count = row['repo_count']
                usage_pct = repo_count / total_repos
                
                # Get example repos using this package
                example_query = """
                    SELECT DISTINCT repo_full_name
                    FROM repo_dependencies
                    WHERE package_name = ? AND registry_type = ?
                    LIMIT 5
                """
                example_cursor = conn.execute(
                    example_query,
                    (package_name, registry_type)
                )
                example_repos = [r['repo_full_name'] for r in example_cursor.fetchall()]
                
                hubs.append(HubPackage(
                    package_name=package_name,
                    registry_type=registry_type,
                    repo_count=repo_count,
                    usage_percentage=usage_pct,
                    example_repos=example_repos
                ))
            
            return hubs
        
        finally:
            conn.close()
    
    def calculate_transitive_footprint(
        self,
        max_results: int = 50
    ) -> List[FootprintMetric]:
        """Calculate transitive dependency footprint per package.
        
        Note: This calculates the number of direct dependencies each package has,
        as transitive dependency edges are not yet available in the system.
        
        Args:
            max_results: Maximum number of results to return
        
        Returns:
            List of FootprintMetric with dependency counts
        """
        conn = self._get_connection()
        
        try:
            # Count direct dependencies per package
            # Note: Full transitive calculation requires package→package edges
            query = """
                SELECT 
                    package_name,
                    registry_type,
                    COUNT(DISTINCT repo_full_name) as direct_dependents
                FROM repo_dependencies
                WHERE package_name IS NOT NULL
                  AND registry_type IS NOT NULL
                GROUP BY package_name, registry_type
                ORDER BY direct_dependents DESC
                LIMIT ?
            """
            
            cursor = conn.execute(query, (max_results,))
            results = cursor.fetchall()
            
            footprints = []
            for row in results:
                footprints.append(FootprintMetric(
                    package_name=row['package_name'],
                    registry_type=row['registry_type'],
                    transitive_count=0,  # Not yet available
                    direct_dependents=row['direct_dependents']
                ))
            
            return footprints
        
        finally:
            conn.close()
    
    def detect_ecosystem_patterns(self) -> List[EcosystemPattern]:
        """Detect ecosystem-specific dependency patterns.
        
        Returns:
            List of EcosystemPattern with examples
        """
        conn = self._get_connection()
        patterns = []
        
        try:
            # Pattern 1: npm packages with many dependents (hub pattern)
            npm_hubs = self._detect_npm_hub_pattern(conn)
            if npm_hubs:
                patterns.append(npm_hubs)
            
            # Pattern 2: Python packages with extras/optional dependencies
            python_extras = self._detect_python_extras_pattern(conn)
            if python_extras:
                patterns.append(python_extras)
            
            # Pattern 3: Go module patterns
            go_modules = self._detect_go_module_pattern(conn)
            if go_modules:
                patterns.append(go_modules)
            
            # Pattern 4: Maven multi-module projects
            maven_multi = self._detect_maven_multimodule_pattern(conn)
            if maven_multi:
                patterns.append(maven_multi)
            
            return patterns
        
        finally:
            conn.close()
    
    def _detect_npm_hub_pattern(self, conn: sqlite3.Connection) -> Optional[EcosystemPattern]:
        """Detect npm hub packages (e.g., lodash, react, express)."""
        query = """
            SELECT 
                package_name,
                COUNT(DISTINCT repo_full_name) as usage_count
            FROM repo_dependencies
            WHERE registry_type = 'npm'
            GROUP BY package_name
            HAVING usage_count >= 5
            ORDER BY usage_count DESC
            LIMIT 10
        """
        
        cursor = conn.execute(query)
        results = cursor.fetchall()
        
        if not results:
            return None
        
        examples = [
            {
                'package': row['package_name'],
                'usage_count': row['usage_count']
            }
            for row in results
        ]
        
        return EcosystemPattern(
            ecosystem='npm',
            pattern_type='hub_packages',
            description='Popular npm packages used across many repositories',
            example_count=len(examples),
            examples=examples
        )
    
    def _detect_python_extras_pattern(self, conn: sqlite3.Connection) -> Optional[EcosystemPattern]:
        """Detect Python packages with extras (e.g., requests[security])."""
        query = """
            SELECT 
                package_name,
                specifier,
                repo_full_name
            FROM repo_dependencies
            WHERE registry_type = 'pypi'
              AND (package_name LIKE '%[%]%' OR specifier LIKE '%[%]%')
            LIMIT 10
        """
        
        cursor = conn.execute(query)
        results = cursor.fetchall()
        
        if not results:
            return None
        
        examples = [
            {
                'package': row['package_name'],
                'specifier': row['specifier'],
                'repo': row['repo_full_name']
            }
            for row in results
        ]
        
        return EcosystemPattern(
            ecosystem='pypi',
            pattern_type='extras_dependencies',
            description='Python packages with optional extras',
            example_count=len(examples),
            examples=examples
        )
    
    def _detect_go_module_pattern(self, conn: sqlite3.Connection) -> Optional[EcosystemPattern]:
        """Detect Go module patterns."""
        query = """
            SELECT 
                package_name,
                COUNT(DISTINCT repo_full_name) as usage_count
            FROM repo_dependencies
            WHERE registry_type = 'go'
            GROUP BY package_name
            HAVING usage_count >= 3
            ORDER BY usage_count DESC
            LIMIT 10
        """
        
        cursor = conn.execute(query)
        results = cursor.fetchall()
        
        if not results:
            return None
        
        examples = [
            {
                'module': row['package_name'],
                'usage_count': row['usage_count']
            }
            for row in results
        ]
        
        return EcosystemPattern(
            ecosystem='go',
            pattern_type='common_modules',
            description='Commonly used Go modules',
            example_count=len(examples),
            examples=examples
        )
    
    def _detect_maven_multimodule_pattern(self, conn: sqlite3.Connection) -> Optional[EcosystemPattern]:
        """Detect Maven multi-module project patterns."""
        query = """
            SELECT 
                repo_full_name,
                COUNT(DISTINCT package_name) as dep_count
            FROM repo_dependencies
            WHERE registry_type = 'maven'
            GROUP BY repo_full_name
            HAVING dep_count >= 10
            ORDER BY dep_count DESC
            LIMIT 10
        """
        
        cursor = conn.execute(query)
        results = cursor.fetchall()
        
        if not results:
            return None
        
        examples = [
            {
                'repo': row['repo_full_name'],
                'dependency_count': row['dep_count']
            }
            for row in results
        ]
        
        return EcosystemPattern(
            ecosystem='maven',
            pattern_type='multi_module_projects',
            description='Maven projects with many dependencies (likely multi-module)',
            example_count=len(examples),
            examples=examples
        )
    
    def analyze_insights(
        self,
        baseline_repo_count: int = 51
    ) -> InsightAnalysis:
        """Identify cross-repository insights and compare with baseline.
        
        Args:
            baseline_repo_count: Repository count in baseline dataset
        
        Returns:
            InsightAnalysis with discovered insights and metrics
        """
        # Find hub packages
        hub_packages = self.find_hub_packages()
        
        # Calculate footprints
        large_footprints = self.calculate_transitive_footprint()
        
        # Detect patterns
        ecosystem_patterns = self.detect_ecosystem_patterns()
        
        # Count new insights
        # An insight is "new" if it provides cross-repository visibility
        new_insights_count = len(hub_packages) + len(ecosystem_patterns)
        
        # Baseline comparison
        baseline_comparison = {
            'baseline_repo_count': baseline_repo_count,
            'current_repo_count': self._get_repo_count(),
            'hub_packages_found': len(hub_packages),
            'ecosystem_patterns_found': len(ecosystem_patterns),
            'top_packages_by_usage': len(large_footprints)
        }
        
        return InsightAnalysis(
            hub_packages=hub_packages,
            large_footprints=large_footprints,
            ecosystem_patterns=ecosystem_patterns,
            new_insights_count=new_insights_count,
            baseline_comparison=baseline_comparison
        )
    
    def _get_repo_count(self) -> int:
        """Get current repository count."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) as count FROM repo_graphs")
            return cursor.fetchone()['count']
        finally:
            conn.close()
