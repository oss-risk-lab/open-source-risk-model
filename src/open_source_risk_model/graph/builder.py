"""
Graph builder - constructs supply chain graph from repository data.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schema import Node, Edge, Graph, NodeType, EdgeType, GraphConfig
from .github_client import GitHubClient
from .cve_fetcher import CVEFetcher
from .registry_detector import RegistryDetector
from ..utils.logging_utils import StructuredLogger, log_event, LogEvent

# Set up structured logger
logger = StructuredLogger(__name__)


class GraphBuilder:
    """
    Builds a supply chain risk graph from repository scoring data.
    
    Takes the output from score_repo() and constructs a graph
    representation with nodes and edges.
    """
    
    def __init__(self, full_name: str, score_data: Dict[str, Any], config: Optional[GraphConfig] = None):
        """
        Initialize graph builder.
        
        Args:
            full_name: Repository full name (owner/repo)
            score_data: Output from score_repo() containing features and risks
            config: Graph configuration (uses defaults if not provided)
        """
        self.full_name = full_name
        self.score_data = score_data
        self.config = config or GraphConfig()
        # Single source of truth for where the database lives. Honors
        # GRAPH_DB_PATH so dependency data lands in the same file the API
        # reads (critical once the DB is on a mounted disk).
        self.db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")
        self.graph = Graph(metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repo": full_name,
            "warnings": [],  # Track partial failures
        })
        
        # Initialize GitHub client for fetching additional data
        self.github_client = GitHubClient(cache_ttl_hours=self.config.cache_ttl_hours)
        
        # Initialize CVE fetcher for vulnerability data
        self.cve_fetcher = CVEFetcher(
            cache_ttl_hours=self.config.cache_ttl_hours,
            timeout_seconds=self.config.cve_timeout_seconds
        )
        
        # Initialize registry detector for package registry detection
        self.registry_detector = RegistryDetector(github_session=self.github_client.session)
        
        # Initialize dependency parsing components (opt-in via config)
        if self.config.parse_dependencies:
            from ..dependencies import (
                ManifestDiscovery,
                DependencyParserRegistry,
                ManifestCache,
                RateLimitTracker,
                DependencyIngestionConfig,
            )
            from ..persistence.dependency_repo import DependencyRepository
            
            github_token = os.environ.get("GITHUB_TOKEN")
            self.manifest_discovery = ManifestDiscovery(github_token=github_token)
            self.parser_registry = DependencyParserRegistry()
            self.manifest_cache = ManifestCache()
            self.rate_limiter = RateLimitTracker(github_token=github_token)
            self.dependency_config = DependencyIngestionConfig()
            # Must honor GRAPH_DB_PATH: these repositories default to the
            # hardcoded relative "data/graphs.db". When the DB lives on a
            # mounted disk (GRAPH_DB_PATH=/var/data/graphs.db), defaulting
            # writes dependencies to a different file than the one the API
            # reads, so dependency coverage silently reads as 0.
            self.dependency_repo = DependencyRepository(db_path=self.db_path)
        else:
            self.manifest_discovery = None
            self.parser_registry = None
            self.manifest_cache = None
            self.rate_limiter = None
            self.dependency_config = None
            self.dependency_repo = None
    
    def build(self) -> Graph:
        """
        Build the complete graph.
        
        Returns:
            Constructed and validated graph
        """
        logger.info("Starting graph build", repo=self.full_name)
        
        # Build core nodes (always present - should not fail)
        try:
            self._add_repo_node()
        except Exception as e:
            # Repo node is critical - log and re-raise
            logger.error(f"Failed to add repo node for {self.full_name}: {e}", exc_info=True)
            raise
        
        # Build enrichment nodes (may fail gracefully)
        self._safe_add_nodes("risk_factor_nodes", self._add_risk_factor_nodes)
        self._safe_add_nodes("maintainer_nodes", self._add_maintainer_nodes)
        self._safe_add_nodes("release_nodes", self._add_release_nodes)
        self._safe_add_nodes("registry_nodes", self._add_registry_nodes)
        
        # Add CVE nodes if enabled
        if self.config.include_cves:
            self._safe_add_nodes("cve_nodes", self._add_cve_nodes)
        
        # Parse and store dependencies if enabled
        if self.config.parse_dependencies:
            self._safe_add_nodes("dependency_parsing", self._parse_and_store_dependencies)
            # Add dependency nodes and resolution edges to graph (Phase C)
            self._safe_add_nodes("dependency_graph_nodes", self._add_dependency_nodes_and_edges)
        
        # Validate before returning
        errors = self.graph.validate()
        if errors:
            # Log errors but return graph anyway (graceful degradation)
            logger.warning(f"Graph validation errors for {self.full_name}: {errors}")
            log_event(
                logger,
                LogEvent.VALIDATION_FAILED,
                level="warning",
                repo=self.full_name,
                errors=errors,
            )
            self.graph.metadata["validation_errors"] = errors
        else:
            log_event(logger, LogEvent.VALIDATION_PASSED, repo=self.full_name)
        
        logger.info(
            "Graph build completed",
            repo=self.full_name,
            node_count=len(self.graph.nodes),
            edge_count=len(self.graph.edges),
        )
        
        return self.graph
    
    def _safe_add_nodes(self, node_type: str, add_func) -> None:
        """
        Safely execute a node addition function with error handling.
        
        Args:
            node_type: Type of nodes being added (for logging)
            add_func: Function to call to add nodes
        """
        try:
            add_func()
        except Exception as e:
            # Log error with context
            error_msg = f"Failed to add {node_type}: {str(e)}"
            logger.warning(f"{error_msg} for {self.full_name}", exc_info=True)
            
            # Add warning to graph metadata
            warning = {
                "source": node_type,
                "error": str(e),
                "impact": f"{node_type} not included in graph"
            }
            self.graph.metadata["warnings"].append(warning)
    
    def _add_repo_node(self) -> None:
        """Add the central repository node."""
        repo_info = self.score_data.get("repo", {})
        overall = self.score_data.get("overall", {})
        
        # Calculate data confidence based on coverage
        coverage = overall.get("coverage", 0.0)
        data_confidence = min(1.0, 0.7 + (coverage * 0.3))  # Scale from 0.7-1.0 based on coverage
        
        node = Node(
            id=f"repo:{self.full_name}",
            type=NodeType.REPO,
            label=self.full_name,
            metadata={
                "url": repo_info.get("url"),
                "maintenance_risk": overall.get("maintenance_risk"),
                "maintenance_label": overall.get("maintenance_label"),
                "coverage": overall.get("coverage"),
                "confidence": overall.get("confidence"),
            },
            provenance={
                "source": "github_api",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": data_confidence,
            }
        )
        self.graph.add_node(node)
    
    def _add_maintainer_nodes(self) -> None:
        """Add maintainer nodes from GitHub Contributors API."""
        # Parse owner and repo from full_name
        parts = self.full_name.split("/")
        if len(parts) != 2:
            logger.warning(f"Invalid repository name format: {self.full_name}")
            return
        
        owner, repo = parts
        
        try:
            # Fetch contributors from GitHub API
            contributors = self.github_client.fetch_contributors(
                owner=owner,
                repo=repo,
                max_count=self.config.max_maintainers
            )
            
            if not contributors:
                logger.info(f"No contributors found for {self.full_name}")
                return
            
            # Calculate total contributions for fraction calculation
            total_contributions = sum(c.get("contributions", 0) for c in contributors)
            
            if total_contributions == 0:
                logger.warning(f"Total contributions is 0 for {self.full_name}")
                return
            
            # Create nodes for each contributor
            for contributor in contributors:
                username = contributor.get("login")
                contributions = contributor.get("contributions", 0)
                
                if not username:
                    logger.warning(f"Skipping contributor with missing username: {contributor}")
                    continue
                
                # Calculate contribution fraction
                contribution_fraction = contributions / total_contributions if total_contributions > 0 else 0.0
                
                # Create maintainer node
                node = Node(
                    id=f"maintainer:{self.full_name}:{username}",
                    type=NodeType.MAINTAINER,
                    label=username,
                    metadata={
                        "username": username,
                        "contribution_fraction": contribution_fraction,
                        "commit_count": contributions,
                        "type": "individual",
                    },
                    provenance={
                        "source": "github_api",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "data_confidence": 0.9,
                    }
                )
                self.graph.add_node(node)
                
                # Create edge: Maintainer -> Repo
                edge = Edge(
                    source=node.id,
                    target=f"repo:{self.full_name}",
                    relationship_type=EdgeType.MAINTAINED_BY,
                    metadata={
                        "contribution_fraction": contribution_fraction,
                        "commit_count": contributions,
                    },
                    provenance={
                        "source": "github_api",
                        "established_at": datetime.now(timezone.utc).isoformat(),
                        "confidence": 0.9,
                    }
                )
                self.graph.add_edge(edge)
            
            logger.info(f"Added {len(contributors)} maintainer nodes for {self.full_name}")
            
        except Exception as e:
            # Log error and let _safe_add_nodes handle it
            logger.warning(f"Failed to fetch contributors for {self.full_name}: {e}")
            raise
    
    def _add_risk_factor_nodes(self) -> None:
        """Add nodes for significant risk factors."""
        top_drivers = self.score_data.get("top_drivers", [])
        
        # Get repo confidence for provenance
        overall = self.score_data.get("overall", {})
        coverage = overall.get("coverage", 0.0)
        data_confidence = min(1.0, 0.7 + (coverage * 0.3))
        
        # Only include top N risk factors with contribution > 0.01 (1%)
        # Lowered threshold to show more factors in the graph visualization
        max_factors = self.config.max_risk_factors
        for driver in top_drivers[:max_factors]:
            contribution = driver.get("contribution")
            if contribution is None or contribution < 0.01:
                continue
            
            key = driver["key"]
            
            # Find the feature details
            feature_detail = None
            for f in self.score_data.get("features", []):
                if f["key"] == key:
                    feature_detail = f
                    break
            
            if not feature_detail:
                continue
            
            node = Node(
                id=f"risk:{self.full_name}:{key}",
                type=NodeType.RISK_FACTOR,
                label=feature_detail.get("label", key.replace("_", " ").title()),
                metadata={
                    "key": key,
                    "raw_value": feature_detail.get("raw_value"),
                    "risk_score": feature_detail.get("risk_score"),
                    "contribution": contribution,
                    "weight": feature_detail.get("weight"),
                    "category": feature_detail.get("category"),
                },
                provenance={
                    "source": "score_model",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "data_confidence": data_confidence,
                }
            )
            self.graph.add_node(node)
            
            # Add edge: Repo -> RiskFactor
            edge = Edge(
                source=f"repo:{self.full_name}",
                target=node.id,
                relationship_type=EdgeType.HAS_RISK_FACTOR,
                metadata={"contribution": contribution},
                provenance={
                    "source": "score_model",
                    "established_at": datetime.now(timezone.utc).isoformat(),
                    "confidence": data_confidence,
                }
            )
            self.graph.add_edge(edge)
    
    def _add_release_nodes(self) -> None:
        """Add release nodes from GitHub Releases API."""
        # Parse owner and repo from full_name
        parts = self.full_name.split("/")
        if len(parts) != 2:
            logger.warning(f"Invalid repository name format: {self.full_name}")
            return
        
        owner, repo = parts
        
        try:
            # Fetch releases from GitHub API
            releases = self.github_client.fetch_releases(
                owner=owner,
                repo=repo,
                max_count=self.config.max_releases
            )
            
            if releases:
                # Create nodes for each release
                for idx, release in enumerate(releases):
                    tag_name = release.get("tag_name", "")
                    published_at = release.get("published_at")
                    is_prerelease = release.get("prerelease", False)
                    is_latest = (idx == 0)
                    
                    if not tag_name or not published_at:
                        logger.warning(f"Skipping release with missing data: {release}")
                        continue
                    
                    # Calculate days since release
                    try:
                        published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                        days_ago = (datetime.now(timezone.utc) - published_dt).days
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Invalid published_at timestamp for release {tag_name}: {e}")
                        days_ago = None
                    
                    # Create release node
                    node = Node(
                        id=f"release:{self.full_name}:{tag_name}",
                        type=NodeType.RELEASE,
                        label=tag_name,
                        metadata={
                            "tag_name": tag_name,
                            "name": release.get("name", tag_name),
                            "published_at": published_at,
                            "days_ago": days_ago,
                            "is_latest": is_latest,
                            "is_prerelease": is_prerelease,
                        },
                        provenance={
                            "source": "github_api",
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "data_confidence": 1.0,
                        }
                    )
                    self.graph.add_node(node)
                    
                    # Create edge: Repo -> Release
                    edge = Edge(
                        source=f"repo:{self.full_name}",
                        target=node.id,
                        relationship_type=EdgeType.HAS_RELEASE,
                        metadata={
                            "days_ago": days_ago,
                            "is_latest": is_latest,
                        },
                        provenance={
                            "source": "github_api",
                            "established_at": datetime.now(timezone.utc).isoformat(),
                            "confidence": 1.0,
                        }
                    )
                    self.graph.add_edge(edge)
                
                logger.info(f"Added {len(releases)} release nodes for {self.full_name}")
                return  # Successfully added releases from GitHub
            
            # No releases from GitHub - check score_data as fallback
            logger.info(f"No releases found from GitHub API for {self.full_name}, checking score_data")
            
        except Exception as e:
            # GitHub API failed - try fallback to score_data
            logger.warning(f"GitHub API failed for releases: {e}, checking score_data")
        
        # Fallback: Check if we have release information in score_data
        features = self.score_data.get("features", [])
        days_since_release = None
        for feature in features:
            if feature["key"] == "days_since_last_release":
                days_since_release = feature.get("raw_value")
                break
        
        if days_since_release is not None:
            # Create a simplified release node from score_data
            node = Node(
                id=f"release:{self.full_name}:latest",
                type=NodeType.RELEASE,
                label="Latest Release",
                metadata={
                    "days_since_release": days_since_release,
                    "type": "latest",
                },
                provenance={
                    "source": "score_data",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "data_confidence": 0.8,  # Lower confidence since it's from score_data
                }
            )
            self.graph.add_node(node)
            
            # Add edge: Repo -> Release
            edge = Edge(
                source=f"repo:{self.full_name}",
                target=node.id,
                relationship_type=EdgeType.HAS_RELEASE,
                metadata={"days_ago": days_since_release},
                provenance={
                    "source": "score_data",
                    "established_at": datetime.now(timezone.utc).isoformat(),
                    "confidence": 0.8,
                }
            )
            self.graph.add_edge(edge)
            logger.info(f"Added fallback release node from score_data for {self.full_name}")
        else:
            # No release data available from either source
            logger.info(f"No release data available for {self.full_name}")
    
    def _detect_ecosystem(self) -> Optional[tuple[str, str]]:
        """
        Detect package ecosystem from repository files.
        
        Returns:
            Tuple of (ecosystem, package_name) if detected, None otherwise
            Ecosystem values: "PyPI", "npm", "Maven", "RubyGems", "crates.io"
        """
        # Parse owner and repo from full_name
        parts = self.full_name.split("/")
        if len(parts) != 2:
            logger.warning(f"Invalid repository name format: {self.full_name}")
            return None
        
        owner, repo = parts
        
        try:
            # Fetch repository contents (root directory)
            url = f"https://api.github.com/repos/{owner}/{repo}/contents"
            response = self.github_client.session.get(url, timeout=10)
            response.raise_for_status()
            
            contents = response.json()
            
            # Build a set of filenames for quick lookup
            filenames = {item["name"] for item in contents if item["type"] == "file"}
            
            # Check for Python ecosystem (PyPI)
            if "setup.py" in filenames or "pyproject.toml" in filenames:
                # Try to extract package name from setup.py or pyproject.toml
                package_name = self._extract_python_package_name(owner, repo, filenames)
                if package_name:
                    return ("PyPI", package_name)
            
            # Check for JavaScript ecosystem (npm)
            if "package.json" in filenames:
                package_name = self._extract_npm_package_name(owner, repo)
                if package_name:
                    return ("npm", package_name)
            
            # Check for Java ecosystem (Maven)
            if "pom.xml" in filenames:
                package_name = self._extract_maven_package_name(owner, repo)
                if package_name:
                    return ("Maven", package_name)
            
            # Check for Ruby ecosystem (RubyGems)
            if any(f.endswith(".gemspec") for f in filenames) or "Gemfile" in filenames:
                # Use repo name as fallback for Ruby
                return ("RubyGems", repo)
            
            # Check for Rust ecosystem (crates.io)
            if "Cargo.toml" in filenames:
                # Use repo name as fallback for Rust
                return ("crates.io", repo)
            
            logger.info(f"No package ecosystem detected for {self.full_name}")
            return None
            
        except Exception as e:
            logger.warning(f"Failed to detect ecosystem for {self.full_name}: {e}")
            return None
    
    def _extract_python_package_name(self, owner: str, repo: str, filenames: set) -> Optional[str]:
        """Extract Python package name from setup.py or pyproject.toml."""
        try:
            # Try pyproject.toml first (modern approach)
            if "pyproject.toml" in filenames:
                url = f"https://api.github.com/repos/{owner}/{repo}/contents/pyproject.toml"
                response = self.github_client.session.get(url, timeout=10)
                response.raise_for_status()
                
                import base64
                content = base64.b64decode(response.json()["content"]).decode("utf-8")
                
                # Simple parsing - look for name = "package_name" in [project] section
                in_project_section = False
                for line in content.split("\n"):
                    line = line.strip()
                    if line == "[project]":
                        in_project_section = True
                    elif line.startswith("[") and in_project_section:
                        in_project_section = False
                    elif in_project_section and line.startswith("name"):
                        # Extract name value
                        if "=" in line:
                            name_part = line.split("=", 1)[1].strip()
                            # Remove quotes
                            name_part = name_part.strip('"').strip("'")
                            return name_part
            
            # Fallback: use repo name
            return repo.lower().replace("-", "_")
            
        except Exception as e:
            logger.debug(f"Failed to extract Python package name: {e}")
            return repo.lower().replace("-", "_")
    
    def _extract_npm_package_name(self, owner: str, repo: str) -> Optional[str]:
        """Extract npm package name from package.json."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/package.json"
            response = self.github_client.session.get(url, timeout=10)
            response.raise_for_status()
            
            import base64
            import json
            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            package_data = json.loads(content)
            
            return package_data.get("name", repo)
            
        except Exception as e:
            logger.debug(f"Failed to extract npm package name: {e}")
            return repo
    
    def _extract_maven_package_name(self, owner: str, repo: str) -> Optional[str]:
        """Extract Maven artifact ID from pom.xml."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/pom.xml"
            response = self.github_client.session.get(url, timeout=10)
            response.raise_for_status()
            
            import base64
            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            
            # Simple XML parsing - look for <artifactId>
            import re
            match = re.search(r"<artifactId>([^<]+)</artifactId>", content)
            if match:
                return match.group(1)
            
            return repo
            
        except Exception as e:
            logger.debug(f"Failed to extract Maven package name: {e}")
            return repo
    
    def _add_cve_nodes(self) -> None:
        """
        Add CVE nodes from OSV.dev API.
        
        Detects package ecosystem, fetches CVEs, creates CVE nodes,
        and adds HAS_CVE edges from releases to CVEs.
        """
        # Detect package ecosystem
        ecosystem_info = self._detect_ecosystem()
        if not ecosystem_info:
            logger.info(f"No package ecosystem detected for {self.full_name}, skipping CVE nodes")
            return
        
        ecosystem, package_name = ecosystem_info
        logger.info(f"Detected ecosystem {ecosystem} with package name {package_name} for {self.full_name}")
        
        try:
            # Fetch CVEs from OSV.dev
            cves = self.cve_fetcher.fetch_cves(
                package_name=package_name,
                ecosystem=ecosystem,
                force_refresh=False
            )
            
            if not cves:
                logger.info(f"No CVEs found for {ecosystem}/{package_name}")
                return
            
            logger.info(f"Found {len(cves)} CVEs for {ecosystem}/{package_name}")
            
            # Get release nodes to map CVEs to releases
            release_nodes = [n for n in self.graph.nodes if n.type == NodeType.RELEASE]
            
            if not release_nodes:
                logger.info(f"No release nodes found, creating CVE nodes without release mapping")
                # Create CVE nodes without release mapping
                for cve in cves:
                    self._create_cve_node(cve)
                return
            
            # Extract release versions for mapping
            release_versions = [n.metadata.get("tag_name", "") for n in release_nodes]
            
            # Map CVEs to releases
            release_cve_map = self.cve_fetcher.map_cves_to_releases(cves, release_versions)
            
            # Create CVE nodes and edges
            created_cve_ids = set()
            
            for release_version, release_cves in release_cve_map.items():
                if not release_cves:
                    continue
                
                # Find the release node
                release_node = next(
                    (n for n in release_nodes if n.metadata.get("tag_name") == release_version),
                    None
                )
                
                if not release_node:
                    continue
                
                for cve in release_cves:
                    # Create CVE node if not already created
                    if cve.id not in created_cve_ids:
                        self._create_cve_node(cve)
                        created_cve_ids.add(cve.id)
                    
                    # Create edge: Release -> CVE
                    edge = Edge(
                        source=release_node.id,
                        target=f"cve:{cve.id}",
                        relationship_type=EdgeType.HAS_CVE,
                        metadata={
                            "severity": cve.severity,
                            "fixed_in": cve.fixed_in,
                        },
                        provenance={
                            "source": cve.source,
                            "established_at": datetime.now(timezone.utc).isoformat(),
                            "match_confidence": 0.85,  # CVE-to-version mapping has some uncertainty
                            "confidence": 0.85,
                        }
                    )
                    self.graph.add_edge(edge)
            
            logger.info(f"Added {len(created_cve_ids)} CVE nodes for {self.full_name}")
            
        except Exception as e:
            # Log error and let _safe_add_nodes handle it
            logger.warning(f"Failed to add CVE nodes for {self.full_name}: {e}")
            raise
    
    def _create_cve_node(self, cve) -> None:
        """
        Create a CVE node from a CVERecord.
        
        Args:
            cve: CVERecord object
        """
        node = Node(
            id=f"cve:{cve.id}",
            type=NodeType.CVE,
            label=cve.cve_id or cve.ghsa_id or cve.id,  # Prefer CVE ID for label
            metadata={
                "id": cve.id,
                "cve_id": cve.cve_id,
                "ghsa_id": cve.ghsa_id,
                "aliases": cve.aliases,
                "severity": cve.severity,
                "cvss_score": cve.cvss_score,
                "summary": cve.summary,
                "published": cve.published,
                "fixed_in": cve.fixed_in,
                "source": cve.source,
            },
            provenance={
                "source": cve.source,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data_confidence": 0.95,  # OSV.dev is highly reliable
            }
        )
        self.graph.add_node(node)


    def _add_registry_nodes(self) -> None:
        """
        Add registry nodes from package manifest detection.
        
        Detects package registries using RegistryDetector,
        creates REGISTRY nodes with metadata, and adds PUBLISHED_AS edges.
        """
        # Parse owner and repo from full_name
        parts = self.full_name.split("/")
        if len(parts) != 2:
            logger.warning(f"Invalid repository name format: {self.full_name}")
            return
        
        owner, repo = parts
        
        try:
            # Detect registries using RegistryDetector
            registries = self.registry_detector.detect_registries(owner=owner, repo=repo)
            
            if not registries:
                logger.info(f"No package registries detected for {self.full_name}")
                return
            
            logger.info(f"Detected {len(registries)} registries for {self.full_name}")
            
            # Create nodes for each detected registry
            for registry_info in registries:
                # Create registry node
                node = Node(
                    id=f"registry:{registry_info.registry_type}:{registry_info.package_name}",
                    type=NodeType.REGISTRY,
                    label=f"{registry_info.registry_type}: {registry_info.package_name}",
                    metadata={
                        "registry_type": registry_info.registry_type,
                        "package_name": registry_info.package_name,
                        "detected_from": registry_info.detected_from,
                        "latest_version": registry_info.latest_version,
                        "download_count": registry_info.download_count,
                    },
                    provenance={
                        "source": "heuristic",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "match_confidence": registry_info.match_confidence,
                        "data_confidence": 0.8,  # Heuristic detection has some uncertainty
                    }
                )
                self.graph.add_node(node)
                
                # Create edge: Repo -> Registry
                edge = Edge(
                    source=f"repo:{self.full_name}",
                    target=node.id,
                    relationship_type=EdgeType.PUBLISHED_AS,
                    metadata={
                        "package_name": registry_info.package_name,
                        "latest_version": registry_info.latest_version,
                    },
                    provenance={
                        "source": "heuristic",
                        "established_at": datetime.now(timezone.utc).isoformat(),
                        "match_confidence": registry_info.match_confidence,
                        "confidence": 0.8,
                    }
                )
                self.graph.add_edge(edge)
            
            logger.info(f"Added {len(registries)} registry nodes for {self.full_name}")
            
        except Exception as e:
            # Log error and let _safe_add_nodes handle it
            logger.warning(f"Failed to add registry nodes for {self.full_name}: {e}")
            raise

    def _parse_and_store_dependencies(self) -> None:
        """
        Parse dependencies from manifests and store in database.

        This method:
        1. Discovers manifest files in the repository
        2. Fetches manifest content (with caching)
        3. Parses dependencies using appropriate parsers
        4. Stores dependencies in database

        Note: This does NOT add dependency nodes to the graph yet.
        That will be Phase C (Package Resolution).
        """
        if not self.manifest_discovery or not self.parser_registry:
            logger.warning("Dependency parsing not initialized")
            return

        # Check rate limit budget
        if not self.rate_limiter.check_github_budget(self.dependency_config):
            logger.warning(f"GitHub API budget exhausted, skipping dependency parsing for {self.full_name}")
            return

        try:
            # Discover manifests
            manifest_paths = self.manifest_discovery.discover_manifests(
                repo_full_name=self.full_name,
                max_depth=self.dependency_config.max_manifest_depth,
                max_files=self.dependency_config.max_manifests_per_repo
            )

            if not manifest_paths:
                logger.info(f"No manifests found for {self.full_name}")
                return

            logger.info(f"Found {len(manifest_paths)} manifests for {self.full_name}")

            # Fetch and parse each manifest
            all_dependencies = []

            for manifest_path in manifest_paths:
                # Check cache first
                cached_content = self.manifest_cache.get(
                    repo_full_name=self.full_name,
                    manifest_path=manifest_path,
                    ttl_hours=self.dependency_config.manifest_cache_ttl_hours
                )

                if cached_content:
                    content = cached_content
                    logger.debug(f"Using cached manifest: {manifest_path}")
                else:
                    # Fetch from GitHub
                    content = self._fetch_manifest_content(manifest_path)
                    if not content:
                        logger.warning(f"Failed to fetch manifest: {manifest_path}")
                        continue

                    # Cache for future use
                    self.manifest_cache.set(
                        repo_full_name=self.full_name,
                        manifest_path=manifest_path,
                        content=content
                    )

                    # Record API call
                    self.rate_limiter.record_github_call()

                # Parse dependencies
                dependencies = self.parser_registry.parse_file(manifest_path, content)

                if dependencies:
                    # Infer registry type
                    registry_type = self.parser_registry.infer_registry_type(manifest_path)

                    # Set registry type on each dependency
                    for dep in dependencies:
                        dep.manifest_path = manifest_path

                    all_dependencies.extend(dependencies)
                    logger.info(f"Parsed {len(dependencies)} dependencies from {manifest_path}")

            if not all_dependencies:
                logger.info(f"No dependencies parsed for {self.full_name}")
                return

            # Store dependencies in database
            self.dependency_repo.save_dependencies(
                repo_full_name=self.full_name,
                dependencies=all_dependencies
            )

            logger.info(f"Stored {len(all_dependencies)} dependencies for {self.full_name}")

            # Add metadata to graph
            self.graph.metadata["dependencies_parsed"] = len(all_dependencies)
            self.graph.metadata["manifests_found"] = len(manifest_paths)

        except Exception as e:
            logger.error(f"Failed to parse dependencies for {self.full_name}: {e}")
            raise

    def _fetch_manifest_content(self, manifest_path: str) -> Optional[str]:
        """
        Fetch manifest file content from GitHub.

        Args:
            manifest_path: Path to manifest file in repository

        Returns:
            File content or None if fetch fails
        """
        try:
            parts = self.full_name.split("/")
            if len(parts) != 2:
                return None

            owner, repo = parts

            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{manifest_path}"
            response = self.github_client.session.get(url, timeout=10)

            if response.status_code != 200:
                logger.warning(f"Failed to fetch {manifest_path}: {response.status_code}")
                return None

            import base64
            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            return content

        except Exception as e:
            logger.error(f"Error fetching {manifest_path}: {e}")
            return None

    def _add_dependency_nodes_and_edges(self) -> None:
        """
        Add dependency nodes and resolution edges to the graph (Phase C).

        This method:
        1. Retrieves dependencies from database
        2. Creates PACKAGE nodes for each dependency
        3. Creates DEPENDS_ON edges from repo to packages
        4. Resolves packages to repositories
        5. Creates RESOLVES_TO edges from packages to repos
        6. Caches resolutions for future use
        """
        if not self.dependency_repo:
            logger.warning("Dependency repository not initialized")
            return

        try:
            # Get dependencies from database
            from ..persistence.dependency_repo import DependencyRepository
            dep_repo = DependencyRepository(db_path=self.db_path)

            dependencies = dep_repo.get_dependencies(
                repo_full_name=self.full_name,
                include_dev=True,  # Include all for now
                include_optional=True
            )

            if not dependencies:
                logger.info(f"No dependencies found in database for {self.full_name}")
                return

            logger.info(f"Adding {len(dependencies)} dependency nodes to graph")

            # Initialize package resolver
            from ..dependencies import PackageResolver
            from ..persistence.dependency_repo import PackageMappingRepository

            resolver = PackageResolver(timeout_seconds=self.config.cve_timeout_seconds)
            mapping_repo = PackageMappingRepository(db_path=self.db_path)

            resolved_count = 0

            for dep in dependencies:
                package_name = dep['package_name']
                registry_type = dep['registry_type']

                # Create package node ID
                package_id = f"package:{registry_type}:{package_name}"

                # Create PACKAGE node
                package_node = Node(
                    id=package_id,
                    type=NodeType.PACKAGE,
                    label=f"{package_name} ({registry_type})",
                    metadata={
                        "package_name": package_name,
                        "registry_type": registry_type,
                        "specifier": dep.get('specifier', ''),
                        "dependency_group": dep.get('dependency_group', 'prod'),
                        "is_optional": dep.get('is_optional', False),
                    },
                    provenance={
                        "source": "dependency_parser",
                        "fetched_at": dep.get('created_at'),
                        "data_confidence": dep.get('confidence', 0.9),
                    }
                )
                self.graph.add_node(package_node)

                # Create DEPENDS_ON edge from repo to package
                depends_edge = Edge(
                    source=f"repo:{self.full_name}",
                    target=package_id,
                    relationship_type=EdgeType.DEPENDS_ON,
                    metadata={
                        "specifier": dep.get('specifier', ''),
                        "dependency_group": dep.get('dependency_group', 'prod'),
                        "manifest_path": dep.get('manifest_path', ''),
                    },
                    provenance={
                        "source": "dependency_parser",
                        "established_at": dep.get('created_at'),
                        "confidence": dep.get('confidence', 0.9),
                    }
                )
                self.graph.add_edge(depends_edge)

                # Try to resolve package to repository
                # Check cache first
                cached_mapping = mapping_repo.get_mapping(package_name, registry_type)

                if cached_mapping:
                    resolution = cached_mapping
                    logger.debug(f"Using cached resolution for {package_name}")
                else:
                    # Resolve package
                    resolution = resolver.resolve(package_name, registry_type)

                    if resolution:
                        # Cache the resolution
                        mapping_repo.save_mapping(resolution)
                        self.rate_limiter.record_registry_call()

                # Normalize: get_mapping() returns a dict, resolver.resolve()
                # returns a PackageResolution dataclass. Treat both as dicts.
                if resolution is not None and not isinstance(resolution, dict):
                    resolution = resolution.to_dict()

                # If resolved, record the resolution ON THE PACKAGE NODE.
                #
                # We deliberately do NOT emit a RESOLVES_TO edge to
                # "repo:<resolved_repo>": the schema requires exactly one REPO
                # node per graph (see Graph.validate), so a second repo node is
                # invalid and an edge without one is a dangling reference. Either
                # way the graph fails validation and save_graph rejects it,
                # which previously broke the whole scan. Keeping the resolution
                # as node metadata preserves the information and keeps the
                # graph valid.
                if resolution and resolution.get('repo_full_name'):
                    resolved_repo = resolution['repo_full_name']

                    package_node.metadata["resolved_repo"] = resolved_repo
                    package_node.metadata["resolution_method"] = resolution.get(
                        'resolution_method', 'unknown'
                    )
                    package_node.metadata["resolution_confidence"] = resolution.get(
                        'confidence', 0.0
                    )
                    resolved_count += 1

                    logger.debug(f"Resolved {package_name} -> {resolved_repo}")

            # Add metadata to graph
            self.graph.metadata["dependencies_in_graph"] = len(dependencies)
            self.graph.metadata["dependencies_resolved"] = resolved_count

            logger.info(f"Added {len(dependencies)} dependency nodes, resolved {resolved_count} to repos")

        except Exception as e:
            logger.error(f"Failed to add dependency nodes for {self.full_name}: {e}")
            raise




def build_graph(full_name: str, score_data: Dict[str, Any], config: Optional[GraphConfig] = None) -> Graph:
    """
    Convenience function to build a graph from score data.
    
    Args:
        full_name: Repository full name (owner/repo)
        score_data: Output from score_repo()
        config: Graph configuration (uses defaults if not provided)
    
    Returns:
        Constructed graph
    """
    builder = GraphBuilder(full_name, score_data, config)
    return builder.build()
