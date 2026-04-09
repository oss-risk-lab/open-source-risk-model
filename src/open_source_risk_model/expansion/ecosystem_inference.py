"""Ecosystem inference from repository manifest files."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from .github_client import GitHubClient

logger = logging.getLogger(__name__)


class EcosystemInference:
    """Infer package ecosystem from repository manifest files."""
    
    # Manifest file patterns for each ecosystem
    MANIFEST_PATTERNS = {
        'npm': ['package.json'],
        'pypi': ['requirements.txt', 'setup.py', 'pyproject.toml'],
        'go': ['go.mod'],
        'maven': ['pom.xml', 'build.gradle', 'build.gradle.kts'],
        'rubygems': ['Gemfile']
    }
    
    # Common subpaths to check if root doesn't have manifests
    COMMON_SUBPATHS = ['/frontend', '/backend', '/packages', '/apps', '/src']
    
    # Maximum API calls for deep scan
    MAX_DEEP_SCAN_CALLS = 10
    
    def __init__(self, github_client: GitHubClient, cache_path: str = "data/ecosystem_cache.json"):
        """
        Initialize ecosystem inference.
        
        Args:
            github_client: GitHub API client
            cache_path: Path to cache file
        """
        self.github_client = github_client
        self.cache_path = Path(cache_path)
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Tuple[str, List[str]]]:
        """Load ecosystem cache from file."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r') as f:
                    data = json.load(f)
                    # Convert lists back to tuples
                    return {k: (v[0], v[1]) for k, v in data.items()}
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                return {}
        return {}
    
    def _save_cache(self):
        """Save ecosystem cache to file."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, 'w') as f:
                # Convert tuples to lists for JSON serialization
                data = {k: [v[0], v[1]] for k, v in self.cache.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def infer_ecosystem(self, repo_full_name: str) -> Tuple[Optional[str], List[str]]:
        """
        Infer primary ecosystem and all manifest types for a repository.
        
        Uses bounded 3-phase approach with caching:
        1. Check root-level manifests only (fast, 1 API call)
        2. If none found, check common subpaths allowlist (max 5 paths)
        3. Only if still none found, do deeper scan (hard cap: 10 API calls)
        
        Args:
            repo_full_name: Repository full name (owner/repo)
        
        Returns:
            Tuple of (primary_ecosystem, all_manifest_types)
        """
        # Check cache first
        if repo_full_name in self.cache:
            logger.debug(f"Cache hit for {repo_full_name}")
            return self.cache[repo_full_name]
        
        detected_ecosystems = []
        
        # Phase 1: Check root-level manifests (1 API call)
        logger.debug(f"Phase 1: Checking root manifests for {repo_full_name}")
        root_files = self._get_root_files(repo_full_name)
        detected_ecosystems = self._detect_ecosystems_in_files(root_files)
        
        # Phase 2: If none found, check common subpaths (max 5 API calls)
        if not detected_ecosystems:
            logger.debug(f"Phase 2: Checking common subpaths for {repo_full_name}")
            for subpath in self.COMMON_SUBPATHS:
                subpath_files = self._get_subpath_files(repo_full_name, subpath)
                detected_ecosystems = self._detect_ecosystems_in_files(subpath_files)
                if detected_ecosystems:
                    break
        
        # Phase 3: Only if still none found, do deeper scan (hard cap: 10 API calls)
        if not detected_ecosystems:
            logger.debug(f"Phase 3: Deep scanning for {repo_full_name}")
            detected_ecosystems = self._deep_scan(repo_full_name)
        
        # Determine primary ecosystem
        primary = self._determine_primary_ecosystem(detected_ecosystems)
        
        # Cache result
        result = (primary, detected_ecosystems)
        self.cache[repo_full_name] = result
        self._save_cache()
        
        return result
    
    def _get_root_files(self, repo_full_name: str) -> List[str]:
        """Get list of files in repository root."""
        try:
            contents = self.github_client.get_repository_contents(repo_full_name, "")
            return [item['name'] for item in contents if item['type'] == 'file']
        except Exception as e:
            logger.warning(f"Failed to get root files for {repo_full_name}: {e}")
            return []
    
    def _get_subpath_files(self, repo_full_name: str, subpath: str) -> List[str]:
        """Get list of files in repository subpath."""
        try:
            # Remove leading slash
            subpath = subpath.lstrip('/')
            contents = self.github_client.get_repository_contents(repo_full_name, subpath)
            return [item['name'] for item in contents if item['type'] == 'file']
        except Exception as e:
            logger.debug(f"Subpath {subpath} not found in {repo_full_name}: {e}")
            return []
    
    def _detect_ecosystems_in_files(self, files: List[str]) -> List[str]:
        """Detect ecosystems from list of filenames."""
        detected = []
        for ecosystem, patterns in self.MANIFEST_PATTERNS.items():
            for pattern in patterns:
                if pattern in files:
                    detected.append(ecosystem)
                    break
        return detected
    
    def _deep_scan(self, repo_full_name: str) -> List[str]:
        """
        Deep scan for manifest files (hard cap: 10 API calls).
        
        Uses code search API to find manifest files.
        """
        detected = []
        api_call_count = 0
        
        for ecosystem, patterns in self.MANIFEST_PATTERNS.items():
            if api_call_count >= self.MAX_DEEP_SCAN_CALLS:
                logger.warning(f"Reached API call limit for deep scan of {repo_full_name}")
                break
            
            for pattern in patterns:
                if api_call_count >= self.MAX_DEEP_SCAN_CALLS:
                    break
                
                try:
                    found = self.github_client.search_code(repo_full_name, pattern)
                    api_call_count += 1
                    
                    if found:
                        detected.append(ecosystem)
                        break
                except Exception as e:
                    logger.debug(f"Deep scan failed for {pattern} in {repo_full_name}: {e}")
                    api_call_count += 1
        
        return detected
    
    def _determine_primary_ecosystem(self, detected_ecosystems: List[str]) -> Optional[str]:
        """
        Determine primary ecosystem from detected ecosystems.
        
        Priority: production manifests > development manifests
        Order: npm, pypi, go, maven, rubygems
        """
        if not detected_ecosystems:
            return None
        
        # Priority order for production manifests
        production_priority = ['npm', 'pypi', 'go', 'maven', 'rubygems']
        
        for ecosystem in production_priority:
            if ecosystem in detected_ecosystems:
                return ecosystem
        
        # Fallback to first detected
        return detected_ecosystems[0]
