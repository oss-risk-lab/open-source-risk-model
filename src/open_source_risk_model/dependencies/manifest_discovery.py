"""
Manifest discovery using GitHub Tree API.

Discovers dependency manifest files in repository trees using pattern matching.
"""

import re
import logging
from typing import List, Optional
import requests

logger = logging.getLogger(__name__)


class ManifestDiscovery:
    """Discovers dependency manifests in repository tree."""
    
    MANIFEST_PATTERNS = [
        # Python
        r'.*requirements.*\.txt$',
        r'.*pyproject\.toml$',
        r'.*setup\.cfg$',
        r'.*poetry\.lock$',
        r'.*Pipfile$',
        
        # JavaScript
        r'.*package\.json$',
        r'.*package-lock\.json$',
        r'.*yarn\.lock$',
        r'.*pnpm-lock\.yaml$',
        
        # Java
        r'.*pom\.xml$',
        r'.*build\.gradle$',
        
        # Go
        r'.*go\.mod$',
    ]
    
    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize manifest discovery.
        
        Args:
            github_token: GitHub API token for authentication
        """
        self.github_token = github_token
    
    def discover_manifests(
        self,
        repo_full_name: str,
        max_depth: int = 3,
        max_files: int = 20
    ) -> List[str]:
        """
        Discover manifest files using GitHub Tree API.
        
        Strategy:
        1. Fetch repository tree (recursive)
        2. Filter by manifest patterns
        3. Limit to max_files (rate limit protection)
        4. Return file paths
        
        Args:
            repo_full_name: Repository in format "owner/repo"
            max_depth: Maximum directory depth to search
            max_files: Maximum number of manifests to return
        
        Returns:
            List of manifest file paths
        """
        try:
            # Get default branch
            default_branch = self._get_default_branch(repo_full_name)
            if not default_branch:
                logger.warning(f"Could not determine default branch for {repo_full_name}")
                return []
            
            # Get tree (recursive)
            tree = self._get_repository_tree(repo_full_name, default_branch)
            if not tree:
                return []
            
            # Filter manifest files
            manifests = []
            for item in tree:
                if item.get('type') != 'blob':
                    continue
                
                path = item.get('path', '')
                
                # Check depth
                depth = path.count('/')
                if depth > max_depth:
                    continue
                
                # Check pattern match
                if self._is_manifest(path):
                    manifests.append(path)
                
                # Limit total files
                if len(manifests) >= max_files:
                    break
            
            logger.info(f"Discovered {len(manifests)} manifests in {repo_full_name}")
            return manifests
        
        except Exception as e:
            logger.error(f"Failed to discover manifests for {repo_full_name}: {e}")
            return []
    
    def _is_manifest(self, path: str) -> bool:
        """Check if path matches any manifest pattern."""
        for pattern in self.MANIFEST_PATTERNS:
            if re.match(pattern, path):
                return True
        return False
    
    def _get_default_branch(self, repo_full_name: str) -> Optional[str]:
        """Get repository default branch."""
        try:
            headers = self._get_headers()
            url = f"https://api.github.com/repos/{repo_full_name}"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('default_branch', 'main')
            
            logger.warning(f"Failed to get default branch for {repo_full_name}: {response.status_code}")
            return None
        
        except Exception as e:
            logger.error(f"Error getting default branch for {repo_full_name}: {e}")
            return None
    
    def _get_repository_tree(
        self,
        repo_full_name: str,
        branch: str
    ) -> List[dict]:
        """Get repository tree using GitHub API."""
        try:
            headers = self._get_headers()
            url = f"https://api.github.com/repos/{repo_full_name}/git/trees/{branch}?recursive=1"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                tree = data.get('tree', [])
                logger.debug(f"Fetched tree with {len(tree)} items for {repo_full_name}")
                return tree
            
            logger.warning(f"Failed to get tree for {repo_full_name}: {response.status_code}")
            return []
        
        except Exception as e:
            logger.error(f"Error getting tree for {repo_full_name}: {e}")
            return []
    
    def _get_headers(self) -> dict:
        """Get headers for GitHub API requests."""
        headers = {}
        if self.github_token:
            headers['Authorization'] = f'Bearer {self.github_token}'
        return headers
