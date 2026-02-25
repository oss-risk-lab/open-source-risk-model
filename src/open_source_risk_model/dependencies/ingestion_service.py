"""
Dependency Ingestion Service

Centralized service for ingesting repository dependencies.
Used by CLI scripts, batch API, and graph generation.

This follows the "clean architecture" pattern recommended for ETL jobs.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os

from open_source_risk_model.dependencies.manifest_discovery import ManifestDiscovery
from open_source_risk_model.dependencies.parsers import DependencyParserRegistry, Dependency
from open_source_risk_model.dependencies.package_resolver import PackageResolver
from open_source_risk_model.persistence.dependency_repo import (
    DependencyRepository,
    PackageMappingRepository
)

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of dependency ingestion."""
    success: bool
    repo_full_name: str
    dependencies_found: int
    dependencies_resolved: int
    manifests_discovered: int
    errors: List[str]
    started_at: datetime
    completed_at: datetime
    
    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        return (self.completed_at - self.started_at).total_seconds()
    
    @property
    def resolution_rate(self) -> float:
        """Calculate resolution success rate."""
        if self.dependencies_found == 0:
            return 0.0
        return self.dependencies_resolved / self.dependencies_found


class DependencyIngestionService:
    """
    Service for ingesting repository dependencies.
    
    This is the single source of truth for dependency ingestion,
    used by:
    - CLI scripts (scripts/ingest_with_dependencies.py)
    - Batch ingestion API (POST /api/ingest)
    - Graph generation (when parse_dependencies=True)
    
    Usage:
        service = DependencyIngestionService(db_path="data/graphs.db")
        result = service.ingest_repo("numpy/numpy", refresh=False)
        
        if result.success:
            print(f"Found {result.dependencies_found} dependencies")
            print(f"Resolved {result.dependencies_resolved} packages")
    """
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize the ingestion service.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        
        # Initialize database schema if needed
        from open_source_risk_model.persistence.db import init_database
        init_database(db_path)
        
        self.dep_repo = DependencyRepository(db_path)
        self.mapping_repo = PackageMappingRepository(db_path)
        self.parser_registry = DependencyParserRegistry()
        self.resolver = PackageResolver(timeout_seconds=10)
        
        # Load GitHub token from environment
        self.github_token = os.environ.get("GITHUB_TOKEN")

    def _update_dependency_resolution(
        self,
        repo_full_name: str,
        package_name: str,
        registry_type: str,
        resolved_repo: str,
        confidence: float,
        method: str
    ):
        """
        Update resolution info for a dependency.

        Uses DependencyRepository.update_resolution() instead of direct DB access.

        Args:
            repo_full_name: Repository that has the dependency
            package_name: Package name
            registry_type: Registry type (pypi, npm, etc.)
            resolved_repo: Resolved GitHub repository
            confidence: Resolution confidence (0.0-1.0)
            method: Resolution method used
        """
        self.dep_repo.update_resolution(
            repo_full_name,
            package_name,
            registry_type,
            resolved_repo,
            confidence,
            method
        )

    def _fetch_file_content(self, repo_full_name: str, file_path: str) -> Optional[str]:
        """
        Fetch file content from GitHub.

        Args:
            repo_full_name: Repository in owner/repo format
            file_path: Path to file in repository

        Returns:
            File content or None if fetch fails
        """
        try:
            import requests
            import base64

            url = f"https://api.github.com/repos/{repo_full_name}/contents/{file_path}"
            
            # Add GitHub token if available
            headers = {}
            if self.github_token:
                headers['Authorization'] = f'Bearer {self.github_token}'
            
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                logger.warning(f"Failed to fetch {file_path}: {response.status_code}")
                return None

            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            return content

        except Exception as e:
            logger.error(f"Error fetching {file_path}: {e}")
            return None
    
    def _ensure_repo_graph_exists(self, repo_full_name: str) -> None:
        """
        Ensure a minimal graph entry exists for the repo.
        
        This is required because repo_dependencies has a foreign key to repo_graphs.
        Creates a minimal stub entry if one doesn't exist.
        
        Args:
            repo_full_name: Repository in owner/repo format
        """
        from open_source_risk_model.persistence.graph_repo import GraphRepository
        
        graph_repo = GraphRepository(self.db_path)
        
        # Check if graph exists
        existing = graph_repo.get_graph(repo_full_name)
        if existing:
            return  # Already exists
        
        # Create minimal stub graph with just a repo node
        from open_source_risk_model.graph.schema import Graph, Node, NodeType
        from datetime import datetime, timezone
        
        # Create minimal repo node
        repo_node = Node(
            id=repo_full_name,
            type=NodeType.REPO,
            label=repo_full_name,
            metadata={"name": repo_full_name},
            provenance={
                "source": "stub",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "confidence": 1.0
            }
        )
        
        stub_graph = Graph(
            nodes=[repo_node],
            edges=[],
            metadata={
                "schema_version": "1.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "data_sources": ["stub"],
                "note": "Minimal stub for dependency ingestion"
            }
        )
        
        graph_repo.save_graph(repo_full_name, stub_graph, generation_time_ms=0)
        logger.info(f"Created stub graph entry for {repo_full_name}")
    
    def ingest_repo(
        self,
        repo_full_name: str,
        refresh: bool = False,
        resolve_packages: bool = True
    ) -> IngestionResult:
        """
        Ingest dependencies for a repository.
        
        This is the main entry point for dependency ingestion.
        
        Args:
            repo_full_name: Repository in owner/repo format
            refresh: If False, skip if recently ingested
            resolve_packages: Whether to resolve package names to repos
        
        Returns:
            IngestionResult with status and metrics
        """
        started_at = datetime.now(timezone.utc)
        errors = []
        
        logger.info(f"Starting ingestion for {repo_full_name}")
        
        try:
            # Step 1: Check if we should skip (if not refresh)
            if not refresh:
                existing = self.dep_repo.get_dependencies(repo_full_name)
                if existing:
                    logger.info(f"Skipping {repo_full_name} - already ingested (use refresh=True to force)")
                    return IngestionResult(
                        success=True,
                        repo_full_name=repo_full_name,
                        dependencies_found=len(existing),
                        dependencies_resolved=sum(1 for d in existing if d.get('resolved_repo')),
                        manifests_discovered=0,
                        errors=["Skipped - already ingested"],
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc)
                    )
            
            # Step 2: Discover manifests
            discovery = ManifestDiscovery(github_token=self.github_token)
            manifests = discovery.discover_manifests(repo_full_name)
            
            if not manifests:
                logger.warning(f"No manifests found for {repo_full_name}")
                return IngestionResult(
                    success=True,
                    repo_full_name=repo_full_name,
                    dependencies_found=0,
                    dependencies_resolved=0,
                    manifests_discovered=0,
                    errors=["No manifest files found"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc)
                )
            
            logger.info(f"Found {len(manifests)} manifest(s): {', '.join(manifests)}")
            
            # Step 3: Ensure repo_graph entry exists (required for foreign key)
            self._ensure_repo_graph_exists(repo_full_name)
            
            # Step 4: Parse dependencies from all manifests
            all_dependencies = []
            for manifest_path in manifests:
                try:
                    content = self._fetch_file_content(repo_full_name, manifest_path)
                    if content:
                        deps = self.parser_registry.parse_file(manifest_path, content)
                        logger.info(f"Parsed {len(deps)} dependencies from {manifest_path}")
                        
                        # Add manifest_path to each dependency
                        for dep in deps:
                            dep.manifest_path = manifest_path
                        
                        all_dependencies.extend(deps)
                except Exception as e:
                    error_msg = f"Failed to parse {manifest_path}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            if not all_dependencies:
                logger.warning(f"No dependencies parsed for {repo_full_name}")
                return IngestionResult(
                    success=True,
                    repo_full_name=repo_full_name,
                    dependencies_found=0,
                    dependencies_resolved=0,
                    manifests_discovered=len(manifests),
                    errors=errors or ["No dependencies found in manifests"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc)
                )
            
            # Step 5: Save dependencies to database
            # Group by manifest for proper storage
            by_manifest = {}
            for dep in all_dependencies:
                manifest = getattr(dep, 'manifest_path', 'unknown')
                if manifest not in by_manifest:
                    by_manifest[manifest] = []
                by_manifest[manifest].append(dep)
            
            for manifest_path, deps in by_manifest.items():
                try:
                    self.dep_repo.save_dependencies(repo_full_name, deps)
                    logger.info(f"Saved {len(deps)} dependencies from {manifest_path}")
                except Exception as e:
                    error_msg = f"Failed to save dependencies from {manifest_path}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            # Step 5: Resolve packages (optional)
            resolved_count = 0
            if resolve_packages:
                resolved_count = self._resolve_packages(repo_full_name, all_dependencies, errors)
            
            # Success!
            completed_at = datetime.now(timezone.utc)
            result = IngestionResult(
                success=True,
                repo_full_name=repo_full_name,
                dependencies_found=len(all_dependencies),
                dependencies_resolved=resolved_count,
                manifests_discovered=len(manifests),
                errors=errors,
                started_at=started_at,
                completed_at=completed_at
            )
            
            logger.info(
                f"Completed ingestion for {repo_full_name}: "
                f"{result.dependencies_found} deps, "
                f"{result.dependencies_resolved} resolved "
                f"({result.resolution_rate:.0%}), "
                f"{result.duration_seconds:.1f}s"
            )
            
            return result
            
        except Exception as e:
            error_msg = f"Ingestion failed: {str(e)}"
            logger.error(f"Failed to ingest {repo_full_name}: {e}", exc_info=True)
            errors.append(error_msg)
            
            return IngestionResult(
                success=False,
                repo_full_name=repo_full_name,
                dependencies_found=0,
                dependencies_resolved=0,
                manifests_discovered=0,
                errors=errors,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc)
            )
    
    def _resolve_packages(
        self,
        repo_full_name: str,
        dependencies: List[Dependency],
        errors: List[str]
    ) -> int:
        """
        Resolve package names to repositories.

        Args:
            repo_full_name: Repository that has these dependencies
            dependencies: List of dependencies to resolve
            errors: List to append errors to

        Returns:
            Number of successfully resolved packages
        """
        resolved_count = 0

        for dep in dependencies:
            try:
                # Infer registry type from manifest
                manifest_path = getattr(dep, 'manifest_path', '')
                if 'requirements' in manifest_path or 'pyproject.toml' in manifest_path:
                    registry_type = 'pypi'
                elif 'package.json' in manifest_path:
                    registry_type = 'npm'
                else:
                    continue

                # Resolve package
                resolution = self.resolver.resolve(dep.package_name, registry_type)
                
                # Save resolution to mapping cache (only if successful)
                if resolution:
                    self.mapping_repo.save_mapping(resolution)

                if resolution and resolution.repo_full_name:
                    # Store resolution in database
                    self._update_dependency_resolution(
                        repo_full_name,
                        dep.package_name,
                        registry_type,
                        resolution.repo_full_name,
                        resolution.confidence,
                        resolution.resolution_method
                    )
                    resolved_count += 1
                    logger.debug(
                        f"Resolved {dep.package_name} → {resolution.repo_full_name} "
                        f"({resolution.confidence:.0%})"
                    )
                else:
                    logger.debug(f"Could not resolve {dep.package_name}")

            except Exception as e:
                error_msg = f"Failed to resolve {dep.package_name}: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)

        return resolved_count
    
    def ingest_batch(
        self,
        repo_list: List[str],
        refresh: bool = False,
        resolve_packages: bool = True
    ) -> List[IngestionResult]:
        """
        Ingest multiple repositories.
        
        Args:
            repo_list: List of repository names
            refresh: Whether to refresh existing data
            resolve_packages: Whether to resolve packages
        
        Returns:
            List of IngestionResult for each repository
        """
        results = []
        
        for repo in repo_list:
            result = self.ingest_repo(repo, refresh, resolve_packages)
            results.append(result)
        
        return results
