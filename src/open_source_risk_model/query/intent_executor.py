"""
Intent Executor

Executes predefined query intents with hardcoded SQL.
NO SQL GENERATION FROM LLM - only intent classification and parameter extraction.

Each intent method:
1. Validates parameters
2. Executes parameterized SQL query
3. Returns structured results

Supported intents:
- list_dependencies: List direct dependencies of a repo
- find_dependents: Find repos that depend on a package
- get_dependency_tree: Compute dependency tree (BFS)
- check_resolution: Check package-to-repo resolution
- list_unresolved: List unresolved dependencies
- list_manifests: List manifest files
- count_by_manifest_type: Count manifests by type
- repo_stats: Repository statistics
- dataset_stats: Overall dataset statistics
- search_repos: Search repositories by name
- search_packages: Search packages by name
"""

import sqlite3
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import deque

from open_source_risk_model.query.dependency_scope import (
    DependencyScope,
    filter_dependencies_by_scope,
    get_scope_description
)

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of an intent execution."""
    intent: str
    parameters: Dict[str, Any]
    results: List[Dict[str, Any]]
    result_count: int
    execution_time_ms: float
    metadata: Optional[Dict[str, Any]] = None


class IntentExecutor:
    """
    Executes query intents with hardcoded SQL.
    
    This class is the ONLY place where SQL queries are defined.
    The LLM only classifies intent and extracts parameters.
    """
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize intent executor.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        
        # Initialize query coverage components (lazy loading)
        self._entity_normalizer = None
        self._coverage_checker = None
        self._retrieval_strategy = None
        self._db_retriever = None
        self._live_repo_ingestor = None
        self._result_summarizer = None
    
    def execute(
        self,
        intent: str,
        parameters: Dict[str, Any],
        max_results: int = 100
    ) -> QueryResult:
        """
        Execute an intent with parameters.
        
        Args:
            intent: Intent name from allowlist
            parameters: Intent-specific parameters
            max_results: Maximum number of results to return
        
        Returns:
            QueryResult with results and metadata
        
        Raises:
            ValueError: If intent is unknown or parameters are invalid
        """
        import time
        start_time = time.time()
        
        # Dispatch to intent handler
        intent_handlers = {
            "list_dependencies": self._list_dependencies,
            "find_dependents": self._find_dependents,
            "get_dependency_tree": self._get_dependency_tree,
            "check_resolution": self._check_resolution,
            "list_unresolved": self._list_unresolved,
            "list_manifests": self._list_manifests,
            "count_by_manifest_type": self._count_by_manifest_type,
            "repo_stats": self._repo_stats,
            "dataset_stats": self._dataset_stats,
            "search_repos": self._search_repos,
            "search_packages": self._search_packages,
            # New query coverage intents
            "repo_lookup": self._repo_lookup,
            "repo_comparison": self._repo_comparison,
            "missing_repo_handling": self._missing_repo_handling,
        }
        
        if intent not in intent_handlers:
            raise ValueError(f"Unknown intent: {intent}")
        
        handler = intent_handlers[intent]
        results, metadata = handler(parameters, max_results)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        return QueryResult(
            intent=intent,
            parameters=parameters,
            results=results,
            result_count=len(results),
            execution_time_ms=round(execution_time_ms, 2),
            metadata=metadata
        )
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        from open_source_risk_model.persistence.db import get_connection
        return get_connection(self.db_path)
    
    def _list_dependencies(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        List direct dependencies of a repository.
        
        Parameters:
            - repo_full_name (required): Repository in owner/repo format
            - dependency_scope (optional): Filter by scope (prod, build, all). Default: prod
        """
        repo_full_name = parameters.get("repo_full_name")
        if not repo_full_name:
            raise ValueError("repo_full_name is required")
        
        # Get dependency_scope parameter (default to "prod")
        scope_str = parameters.get("dependency_scope", "prod")
        try:
            scope = DependencyScope(scope_str)
        except ValueError:
            raise ValueError(f"Invalid dependency_scope: {scope_str}. Must be one of: prod, build, all")
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        # Filter out non-production paths (examples, tests, docs, etc.)
        excluded_patterns = [
            'examples/%', 'example/%',
            'tests/%', 'test/%',
            'docs/%', 'doc/%',
            'benchmarks/%', 'benchmark/%',
            'samples/%', 'sample/%',
            'demos/%', 'demo/%',
            'tutorials/%', 'tutorial/%'
        ]
        
        exclusion_clause = " AND " + " AND ".join([
            f"manifest_path NOT LIKE '{pattern}'" for pattern in excluded_patterns
        ])
        
        # Fetch ALL dependencies first (we'll filter by scope after)
        cursor = conn.execute(f"""
            SELECT 
                package_name,
                registry_type,
                specifier,
                dependency_group,
                manifest_path,
                resolved_repo,
                resolution_confidence,
                is_optional
            FROM repo_dependencies
            WHERE repo_full_name = ?
              AND is_direct = 1
              {exclusion_clause}
            ORDER BY package_name
        """, (repo_full_name,))
        
        all_results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Apply scope filtering
        filtered_results = filter_dependencies_by_scope(all_results, scope)
        
        # Apply max_results limit
        filtered_results = filtered_results[:max_results]
        
        metadata = {
            "repo_full_name": repo_full_name,
            "dependency_scope": scope.value,
            "dependency_scope_description": get_scope_description(scope),
            "direct_only": True,
            "total_before_scope_filter": len(all_results),
            "total_after_scope_filter": len(filtered_results)
        }
        
        return filtered_results, metadata
    
    def _find_dependents(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Find repositories that depend on a package.
        
        Parameters:
            - package_name (required): Package name
            - registry_type (optional): Registry type (pypi, npm)
        """
        package_name = parameters.get("package_name")
        if not package_name:
            raise ValueError("package_name is required")
        
        registry_type = parameters.get("registry_type")
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        if registry_type:
            cursor = conn.execute("""
                SELECT DISTINCT
                    repo_full_name,
                    specifier,
                    dependency_group,
                    manifest_path,
                    is_direct
                FROM repo_dependencies
                WHERE package_name = ?
                  AND registry_type = ?
                ORDER BY repo_full_name
                LIMIT ?
            """, (package_name, registry_type, max_results))
        else:
            cursor = conn.execute("""
                SELECT DISTINCT
                    repo_full_name,
                    registry_type,
                    specifier,
                    dependency_group,
                    manifest_path,
                    is_direct
                FROM repo_dependencies
                WHERE package_name = ?
                ORDER BY repo_full_name
                LIMIT ?
            """, (package_name, max_results))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        metadata = {
            "package_name": package_name,
            "registry_type": registry_type,
            "dependent_count": len(results)
        }
        
        return results, metadata
    
    def _get_dependency_tree(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Compute dependency tree using BFS traversal.
        
        Parameters:
            - repo_full_name (required): Root repository
            - max_depth (optional): Maximum depth (default: 3)
        """
        repo_full_name = parameters.get("repo_full_name")
        if not repo_full_name:
            raise ValueError("repo_full_name is required")
        
        max_depth = parameters.get("max_depth", 3)
        if max_depth > 5:
            max_depth = 5  # Safety limit
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        # BFS traversal
        tree = []
        visited = set()
        queue = deque([(repo_full_name, 0, None)])  # (repo, depth, parent)
        
        while queue and len(tree) < max_results:
            current_repo, depth, parent = queue.popleft()
            
            if current_repo in visited or depth > max_depth:
                continue
            
            visited.add(current_repo)
            
            # Get dependencies for current repo
            cursor = conn.execute("""
                SELECT 
                    package_name,
                    registry_type,
                    specifier,
                    resolved_repo,
                    resolution_confidence,
                    manifest_path
                FROM repo_dependencies
                WHERE repo_full_name = ?
                  AND is_direct = 1
                  AND resolved_repo IS NOT NULL
            """, (current_repo,))
            
            dependencies = cursor.fetchall()
            
            for dep in dependencies:
                dep_dict = dict(dep)
                dep_dict['depth'] = depth
                dep_dict['parent'] = parent
                dep_dict['repo_full_name'] = current_repo
                tree.append(dep_dict)
                
                # Add resolved repo to queue for next level
                if dep['resolved_repo'] and depth < max_depth:
                    queue.append((dep['resolved_repo'], depth + 1, current_repo))
        
        conn.close()
        
        metadata = {
            "root_repo": repo_full_name,
            "max_depth": max_depth,
            "nodes_visited": len(visited),
            "edges_found": len(tree)
        }
        
        return tree, metadata
    
    def _check_resolution(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Check if a package resolves to a GitHub repository.
        
        Parameters:
            - package_name (required): Package name
            - registry_type (required): Registry type (pypi, npm)
        """
        package_name = parameters.get("package_name")
        registry_type = parameters.get("registry_type")
        
        if not package_name or not registry_type:
            raise ValueError("package_name and registry_type are required")
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT 
                package_name,
                registry_type,
                repo_full_name,
                resolution_method,
                confidence,
                metadata,
                created_at,
                updated_at
            FROM package_mappings
            WHERE package_name = ?
              AND registry_type = ?
        """, (package_name, registry_type))
        
        result = cursor.fetchone()
        results = [dict(result)] if result else []
        
        conn.close()
        
        metadata = {
            "package_name": package_name,
            "registry_type": registry_type,
            "resolved": bool(results)
        }
        
        return results, metadata
    
    def _list_unresolved(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        List dependencies that couldn't be resolved to GitHub repos.
        
        Parameters:
            - repo_full_name (optional): Filter by repository
        """
        repo_full_name = parameters.get("repo_full_name")
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        if repo_full_name:
            cursor = conn.execute("""
                SELECT 
                    repo_full_name,
                    package_name,
                    registry_type,
                    specifier,
                    manifest_path
                FROM repo_dependencies
                WHERE repo_full_name = ?
                  AND (resolved_repo IS NULL OR resolved_repo = '')
                ORDER BY package_name
                LIMIT ?
            """, (repo_full_name, max_results))
        else:
            cursor = conn.execute("""
                SELECT 
                    repo_full_name,
                    package_name,
                    registry_type,
                    specifier,
                    manifest_path
                FROM repo_dependencies
                WHERE resolved_repo IS NULL OR resolved_repo = ''
                ORDER BY repo_full_name, package_name
                LIMIT ?
            """, (max_results,))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        metadata = {
            "repo_full_name": repo_full_name,
            "unresolved_count": len(results)
        }
        
        return results, metadata
    
    def _list_manifests(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        List manifest files for a repository.
        
        Parameters:
            - repo_full_name (required): Repository in owner/repo format
        """
        repo_full_name = parameters.get("repo_full_name")
        if not repo_full_name:
            raise ValueError("repo_full_name is required")
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT DISTINCT
                manifest_path,
                COUNT(*) as dependency_count
            FROM repo_dependencies
            WHERE repo_full_name = ?
            GROUP BY manifest_path
            ORDER BY manifest_path
            LIMIT ?
        """, (repo_full_name, max_results))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        metadata = {
            "repo_full_name": repo_full_name,
            "manifest_count": len(results)
        }
        
        return results, metadata
    
    def _count_by_manifest_type(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Count manifests by type across all repositories.
        
        Parameters: None
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT 
                CASE
                    WHEN manifest_path LIKE '%requirements%.txt' THEN 'requirements.txt'
                    WHEN manifest_path LIKE '%pyproject.toml' THEN 'pyproject.toml'
                    WHEN manifest_path LIKE '%package.json' THEN 'package.json'
                    WHEN manifest_path LIKE '%package-lock.json' THEN 'package-lock.json'
                    WHEN manifest_path LIKE '%yarn.lock' THEN 'yarn.lock'
                    WHEN manifest_path LIKE '%pom.xml' THEN 'pom.xml'
                    WHEN manifest_path LIKE '%go.mod' THEN 'go.mod'
                    ELSE 'other'
                END as manifest_type,
                COUNT(DISTINCT repo_full_name || '/' || manifest_path) as count
            FROM repo_dependencies
            GROUP BY manifest_type
            ORDER BY count DESC
        """)
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        metadata = {
            "total_types": len(results)
        }
        
        return results, metadata
    
    def _repo_stats(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Get statistics for a repository.
        
        Parameters:
            - repo_full_name (required): Repository in owner/repo format
        """
        repo_full_name = parameters.get("repo_full_name")
        if not repo_full_name:
            raise ValueError("repo_full_name is required")
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        # Filter out non-production paths
        excluded_patterns = [
            'examples/%', 'example/%',
            'tests/%', 'test/%',
            'docs/%', 'doc/%',
            'benchmarks/%', 'benchmark/%',
            'samples/%', 'sample/%',
            'demos/%', 'demo/%',
            'tutorials/%', 'tutorial/%'
        ]
        
        exclusion_clause = " AND " + " AND ".join([
            f"manifest_path NOT LIKE '{pattern}'" for pattern in excluded_patterns
        ])
        
        cursor = conn.execute(f"""
            SELECT 
                COUNT(*) as total_dependencies,
                COUNT(DISTINCT manifest_path) as manifest_count,
                SUM(CASE WHEN is_direct = 1 THEN 1 ELSE 0 END) as direct_dependencies,
                SUM(CASE WHEN resolved_repo IS NOT NULL THEN 1 ELSE 0 END) as resolved_dependencies,
                COUNT(DISTINCT registry_type) as registry_types
            FROM repo_dependencies
            WHERE repo_full_name = ?
              {exclusion_clause}
        """, (repo_full_name,))
        
        result = cursor.fetchone()
        results = [dict(result)] if result else []
        
        conn.close()
        
        metadata = {
            "repo_full_name": repo_full_name
        }
        
        return results, metadata
    
    def _dataset_stats(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Get overall dataset statistics.
        
        Parameters: None
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        # Get repo count
        cursor = conn.execute("SELECT COUNT(*) as repo_count FROM repo_graphs")
        repo_count = cursor.fetchone()['repo_count']
        
        # Filter out non-production paths
        excluded_patterns = [
            'examples/%', 'example/%',
            'tests/%', 'test/%',
            'docs/%', 'doc/%',
            'benchmarks/%', 'benchmark/%',
            'samples/%', 'sample/%',
            'demos/%', 'demo/%',
            'tutorials/%', 'tutorial/%'
        ]
        
        exclusion_clause = " WHERE " + " AND ".join([
            f"manifest_path NOT LIKE '{pattern}'" for pattern in excluded_patterns
        ])
        
        # Get dependency stats
        cursor = conn.execute(f"""
            SELECT 
                COUNT(*) as total_dependencies,
                COUNT(DISTINCT repo_full_name) as repos_with_dependencies,
                COUNT(DISTINCT manifest_path) as total_manifests,
                SUM(CASE WHEN resolved_repo IS NOT NULL THEN 1 ELSE 0 END) as resolved_dependencies,
                COUNT(DISTINCT package_name) as unique_packages
            FROM repo_dependencies
            {exclusion_clause}
        """)
        
        dep_stats = dict(cursor.fetchone())
        
        results = [{
            "repo_count": repo_count,
            **dep_stats,
            "resolution_rate": round(
                dep_stats['resolved_dependencies'] / dep_stats['total_dependencies'] * 100, 1
            ) if dep_stats['total_dependencies'] > 0 else 0
        }]
        
        conn.close()
        
        metadata = {
            "database": self.db_path
        }
        
        return results, metadata
    
    def _search_repos(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Search repositories by name pattern.
        
        Parameters:
            - pattern (required): Search pattern (SQL LIKE syntax)
        """
        pattern = parameters.get("pattern")
        if not pattern:
            raise ValueError("pattern is required")
        
        # Ensure pattern has wildcards
        if '%' not in pattern and '_' not in pattern:
            pattern = f"%{pattern}%"
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT DISTINCT
                repo_full_name,
                node_count,
                edge_count,
                created_at,
                updated_at
            FROM repo_graphs
            WHERE repo_full_name LIKE ?
            ORDER BY repo_full_name
            LIMIT ?
        """, (pattern, max_results))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        metadata = {
            "pattern": pattern,
            "match_count": len(results)
        }
        
        return results, metadata
    
    def _search_packages(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Search packages by name pattern.
        
        Parameters:
            - pattern (required): Search pattern (SQL LIKE syntax)
            - registry_type (optional): Filter by registry type
        """
        pattern = parameters.get("pattern")
        if not pattern:
            raise ValueError("pattern is required")
        
        # Ensure pattern has wildcards
        if '%' not in pattern and '_' not in pattern:
            pattern = f"%{pattern}%"
        
        registry_type = parameters.get("registry_type")
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        
        if registry_type:
            cursor = conn.execute("""
                SELECT DISTINCT
                    package_name,
                    registry_type,
                    COUNT(DISTINCT repo_full_name) as used_by_count
                FROM repo_dependencies
                WHERE package_name LIKE ?
                  AND registry_type = ?
                GROUP BY package_name, registry_type
                ORDER BY used_by_count DESC, package_name
                LIMIT ?
            """, (pattern, registry_type, max_results))
        else:
            cursor = conn.execute("""
                SELECT DISTINCT
                    package_name,
                    registry_type,
                    COUNT(DISTINCT repo_full_name) as used_by_count
                FROM repo_dependencies
                WHERE package_name LIKE ?
                GROUP BY package_name, registry_type
                ORDER BY used_by_count DESC, package_name
                LIMIT ?
            """, (pattern, max_results))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        metadata = {
            "pattern": pattern,
            "registry_type": registry_type,
            "match_count": len(results)
        }
        
        return results, metadata

    # ========================================================================
    # Query Coverage System Integration (Tasks 11-16)
    # ========================================================================
    
    def _get_entity_normalizer(self):
        """Lazy load EntityNormalizer."""
        if self._entity_normalizer is None:
            from open_source_risk_model.ingestion.entity_normalizer import EntityNormalizer
            self._entity_normalizer = EntityNormalizer()
        return self._entity_normalizer
    
    def _get_coverage_checker(self):
        """Lazy load CoverageChecker."""
        if self._coverage_checker is None:
            from open_source_risk_model.query.coverage_checker import CoverageChecker
            self._coverage_checker = CoverageChecker(db_path=self.db_path)
        return self._coverage_checker
    
    def _get_retrieval_strategy(self):
        """Lazy load RetrievalStrategy."""
        if self._retrieval_strategy is None:
            from open_source_risk_model.query.retrieval_strategy import RetrievalStrategy
            self._retrieval_strategy = RetrievalStrategy()
        return self._retrieval_strategy
    
    def _get_db_retriever(self):
        """Lazy load DBRetriever."""
        if self._db_retriever is None:
            from open_source_risk_model.query.db_retriever import DBRetriever
            self._db_retriever = DBRetriever(db_path=self.db_path)
        return self._db_retriever
    
    def _get_live_repo_ingestor(self):
        """Lazy load LiveRepoIngestor."""
        if self._live_repo_ingestor is None:
            import os
            from open_source_risk_model.query.live_repo_ingestor import LiveRepoIngestor
            github_token = os.environ.get("GITHUB_TOKEN", "")
            self._live_repo_ingestor = LiveRepoIngestor(
                github_token=github_token,
                db_path=self.db_path
            )
        return self._live_repo_ingestor
    
    def _get_result_summarizer(self):
        """Lazy load ResultSummarizer."""
        if self._result_summarizer is None:
            from open_source_risk_model.query.result_summarizer import ResultSummarizer
            self._result_summarizer = ResultSummarizer()
        return self._result_summarizer
    
    def _repo_lookup(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Look up maintenance risk score for a single repository.
        
        Parameters:
            - repo_identifier (required): Repository name or package name
            - ingestion_mode (optional): provisional or full (default: provisional)
            - persistence_mode (optional): temporary, cache, or database (default: cache)
        """
        repo_identifier = parameters.get("repo_identifier")
        if not repo_identifier:
            raise ValueError("repo_identifier is required")
        
        ingestion_mode = parameters.get("ingestion_mode", "provisional")
        persistence_mode = parameters.get("persistence_mode", "cache")
        
        # Step 1: Normalize entity
        normalizer = self._get_entity_normalizer()
        norm_result = normalizer.normalize_package(repo_identifier)
        
        if not norm_result.canonical_identifier:
            # Unresolved entity
            return [], {
                "repo_identifier": repo_identifier,
                "status": "unresolved",
                "warning": norm_result.warning,
                "alternatives": norm_result.alternatives
            }
        
        canonical_repo = norm_result.canonical_identifier
        
        # Step 2: Check coverage
        coverage_checker = self._get_coverage_checker()
        coverage_report = coverage_checker.check_coverage([canonical_repo])
        
        # Step 3: Select retrieval strategy
        strategy_selector = self._get_retrieval_strategy()
        retrieval_plan = strategy_selector.select_strategy(
            coverage_report=coverage_report,
            user_preferences={"ingestion_mode": ingestion_mode}
        )
        
        # Step 4: Retrieve data
        results = []
        
        if retrieval_plan.use_database:
            db_retriever = self._get_db_retriever()
            db_results = db_retriever.retrieve_summary(retrieval_plan.repos_from_database)
            results.extend(db_results)
        
        if retrieval_plan.use_live_ingestion:
            live_ingestor = self._get_live_repo_ingestor()
            live_results = live_ingestor.ingest(
                repo_identifiers=retrieval_plan.repos_for_ingestion,
                mode=retrieval_plan.live_ingestion_mode,
                persistence_mode=persistence_mode
            )
            results.extend(live_results)
        
        # Step 5: Summarize results
        summarizer = self._get_result_summarizer()
        query_response = summarizer.summarize(
            results=results,
            intent="repo_lookup",
            evidence_scope=retrieval_plan.evidence_scope
        )
        
        # Convert to dict format for QueryResult
        results_dict = [
            {
                "repo_full_name": r.repo_full_name,
                "maintenance_risk_score": r.maintenance_risk_score,
                "risk_band": r.risk_band,
                "features": r.features,
                "provenance": r.provenance.model_dump()
            }
            for r in query_response.structured_results
        ]
        
        metadata = {
            "repo_identifier": repo_identifier,
            "canonical_repo": canonical_repo,
            "normalization_confidence": norm_result.confidence,
            "coverage_mode": coverage_report.coverage_mode,
            "retrieval_plan": {
                "use_database": retrieval_plan.use_database,
                "use_live_ingestion": retrieval_plan.use_live_ingestion,
                "live_ingestion_mode": retrieval_plan.live_ingestion_mode,
                "cost_classification": retrieval_plan.cost_classification
            },
            "natural_language_response": query_response.natural_language_response,
            "warnings": query_response.warnings,
            "evidence_scope": query_response.evidence_scope.model_dump()
        }
        
        return results_dict, metadata
    
    def _repo_comparison(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Compare maintenance risk scores for multiple repositories.
        
        Parameters:
            - repo_identifiers (required): List of repository names or package names
            - ingestion_mode (optional): provisional or full (default: provisional)
            - persistence_mode (optional): temporary, cache, or database (default: cache)
        """
        repo_identifiers = parameters.get("repo_identifiers")
        if not repo_identifiers or not isinstance(repo_identifiers, list):
            raise ValueError("repo_identifiers is required and must be a list")
        
        ingestion_mode = parameters.get("ingestion_mode", "provisional")
        persistence_mode = parameters.get("persistence_mode", "cache")
        
        # Step 1: Normalize all entities
        normalizer = self._get_entity_normalizer()
        canonical_repos = []
        normalization_results = {}
        
        for identifier in repo_identifiers:
            norm_result = normalizer.normalize_package(identifier)
            normalization_results[identifier] = norm_result
            if norm_result.canonical_identifier:
                canonical_repos.append(norm_result.canonical_identifier)
        
        if not canonical_repos:
            # No repos could be normalized
            return [], {
                "repo_identifiers": repo_identifiers,
                "status": "all_unresolved",
                "normalization_results": {
                    k: {"warning": v.warning, "alternatives": v.alternatives}
                    for k, v in normalization_results.items()
                }
            }
        
        # Step 2: Check coverage
        coverage_checker = self._get_coverage_checker()
        coverage_report = coverage_checker.check_coverage(canonical_repos)
        
        # Step 3: Select retrieval strategy
        strategy_selector = self._get_retrieval_strategy()
        retrieval_plan = strategy_selector.select_strategy(
            coverage_report=coverage_report,
            user_preferences={"ingestion_mode": ingestion_mode}
        )
        
        # Step 4: Retrieve data
        results = []
        
        if retrieval_plan.use_database:
            db_retriever = self._get_db_retriever()
            db_results = db_retriever.retrieve_summary(retrieval_plan.repos_from_database)
            results.extend(db_results)
        
        if retrieval_plan.use_live_ingestion:
            live_ingestor = self._get_live_repo_ingestor()
            live_results = live_ingestor.ingest(
                repo_identifiers=retrieval_plan.repos_for_ingestion,
                mode=retrieval_plan.live_ingestion_mode,
                persistence_mode=persistence_mode
            )
            results.extend(live_results)
        
        # Step 5: Summarize results
        summarizer = self._get_result_summarizer()
        query_response = summarizer.summarize(
            results=results,
            intent="repo_comparison",
            evidence_scope=retrieval_plan.evidence_scope
        )
        
        # Convert to dict format for QueryResult
        results_dict = [
            {
                "repo_full_name": r.repo_full_name,
                "maintenance_risk_score": r.maintenance_risk_score,
                "risk_band": r.risk_band,
                "features": r.features,
                "provenance": r.provenance.model_dump()
            }
            for r in query_response.structured_results
        ]
        
        metadata = {
            "repo_identifiers": repo_identifiers,
            "canonical_repos": canonical_repos,
            "normalization_results": {
                k: {
                    "canonical": v.canonical_identifier,
                    "confidence": v.confidence,
                    "warning": v.warning
                }
                for k, v in normalization_results.items()
            },
            "coverage_mode": coverage_report.coverage_mode,
            "retrieval_plan": {
                "use_database": retrieval_plan.use_database,
                "use_live_ingestion": retrieval_plan.use_live_ingestion,
                "live_ingestion_mode": retrieval_plan.live_ingestion_mode,
                "cost_classification": retrieval_plan.cost_classification
            },
            "natural_language_response": query_response.natural_language_response,
            "warnings": query_response.warnings,
            "evidence_scope": query_response.evidence_scope.model_dump()
        }
        
        return results_dict, metadata
    
    def _missing_repo_handling(
        self,
        parameters: Dict[str, Any],
        max_results: int
    ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Handle query for repository not in database (live ingestion).
        
        This is a convenience intent that forces live ingestion regardless of database status.
        
        Parameters:
            - repo_identifier (required): Repository name or package name
            - ingestion_mode (optional): provisional or full (default: provisional)
            - persistence_mode (optional): temporary, cache, or database (default: cache)
        """
        repo_identifier = parameters.get("repo_identifier")
        if not repo_identifier:
            raise ValueError("repo_identifier is required")
        
        ingestion_mode = parameters.get("ingestion_mode", "provisional")
        persistence_mode = parameters.get("persistence_mode", "cache")
        
        # Step 1: Normalize entity
        normalizer = self._get_entity_normalizer()
        norm_result = normalizer.normalize_package(repo_identifier)
        
        if not norm_result.canonical_identifier:
            # Unresolved entity
            return [], {
                "repo_identifier": repo_identifier,
                "status": "unresolved",
                "warning": norm_result.warning,
                "alternatives": norm_result.alternatives
            }
        
        canonical_repo = norm_result.canonical_identifier
        
        # Step 2: Force live ingestion (skip coverage check)
        live_ingestor = self._get_live_repo_ingestor()
        results = live_ingestor.ingest(
            repo_identifiers=[canonical_repo],
            mode=ingestion_mode,
            persistence_mode=persistence_mode
        )
        
        # Step 3: Summarize results
        from open_source_risk_model.ingestion.models import EvidenceScope
        evidence_scope = EvidenceScope(
            source_level="raw_ingestion",
            includes_live_fetch=True,
            includes_cached_results=False,
            includes_database_results=False
        )
        
        summarizer = self._get_result_summarizer()
        query_response = summarizer.summarize(
            results=results,
            intent="missing_repo_handling",
            evidence_scope=evidence_scope
        )
        
        # Convert to dict format for QueryResult
        results_dict = [
            {
                "repo_full_name": r.repo_full_name,
                "maintenance_risk_score": r.maintenance_risk_score,
                "risk_band": r.risk_band,
                "features": r.features,
                "provenance": r.provenance.model_dump()
            }
            for r in query_response.structured_results
        ]
        
        metadata = {
            "repo_identifier": repo_identifier,
            "canonical_repo": canonical_repo,
            "normalization_confidence": norm_result.confidence,
            "forced_live_ingestion": True,
            "ingestion_mode": ingestion_mode,
            "persistence_mode": persistence_mode,
            "natural_language_response": query_response.natural_language_response,
            "warnings": query_response.warnings,
            "evidence_scope": query_response.evidence_scope.model_dump()
        }
        
        return results_dict, metadata
