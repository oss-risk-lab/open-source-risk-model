"""
Package resolver - resolves package names to source repositories.

Supports PyPI and npm package resolution with confidence scoring.
"""

import re
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import requests

logger = logging.getLogger(__name__)


@dataclass
class PackageResolution:
    """Result of package resolution."""
    package_name: str
    registry_type: str
    repo_full_name: Optional[str]
    resolution_method: str
    confidence: float
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'package_name': self.package_name,
            'registry_type': self.registry_type,
            'repo_full_name': self.repo_full_name,
            'resolution_method': self.resolution_method,
            'confidence': self.confidence,
            'metadata': self.metadata,
        }


class PackageResolver:
    """Resolves package names to source repositories."""
    
    def __init__(self, timeout_seconds: int = 5):
        """
        Initialize package resolver.
        
        Args:
            timeout_seconds: Timeout for API requests
        """
        self.timeout = timeout_seconds
    
    def resolve(
        self,
        package_name: str,
        registry_type: str
    ) -> Optional[PackageResolution]:
        """
        Resolve package to source repository.
        
        Args:
            package_name: Package name (e.g., "requests", "react")
            registry_type: Registry type (pypi, npm, etc.)
        
        Returns:
            PackageResolution if successful, None otherwise
        """
        if registry_type == 'pypi':
            return self._resolve_pypi(package_name)
        elif registry_type == 'npm':
            return self._resolve_npm(package_name)
        else:
            logger.warning(f"Unsupported registry type: {registry_type}")
            return None
    
    def _resolve_pypi(self, package_name: str) -> Optional[PackageResolution]:
        """
        Resolve PyPI package to GitHub repository.
        
        Strategy:
        1. Fetch package metadata from PyPI API
        2. Check project_urls for Source/Repository/GitHub
        3. Check home_page for GitHub URL
        4. Extract owner/repo from URL
        5. Assign confidence based on source
        
        Args:
            package_name: PyPI package name
        
        Returns:
            PackageResolution if successful, None otherwise
        """
        try:
            # Fetch package metadata
            url = f"https://pypi.org/pypi/{package_name}/json"
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code != 200:
                logger.debug(f"PyPI package not found: {package_name}")
                return None
            
            data = response.json()
            info = data.get('info', {})
            
            # Try project_urls first (most reliable)
            project_urls = info.get('project_urls', {})
            
            # Priority order for project_urls
            url_keys = ['Source', 'Repository', 'Source Code', 'GitHub', 'Code']
            
            for key in url_keys:
                if key in project_urls:
                    github_url = project_urls[key]
                    repo = self._extract_github_repo(github_url)
                    if repo:
                        return PackageResolution(
                            package_name=package_name,
                            registry_type='pypi',
                            repo_full_name=repo,
                            resolution_method='pypi_project_urls',
                            confidence=0.95,  # High confidence
                            metadata={
                                'url_key': key,
                                'url': github_url,
                                'package_version': info.get('version'),
                            }
                        )
            
            # Try home_page as fallback
            home_page = info.get('home_page', '')
            if home_page:
                repo = self._extract_github_repo(home_page)
                if repo:
                    return PackageResolution(
                        package_name=package_name,
                        registry_type='pypi',
                        repo_full_name=repo,
                        resolution_method='pypi_home_page',
                        confidence=0.75,  # Lower confidence (might be docs site)
                        metadata={
                            'url': home_page,
                            'package_version': info.get('version'),
                        }
                    )
            
            # No GitHub URL found
            logger.debug(f"No GitHub URL found for PyPI package: {package_name}")
            return None
        
        except Exception as e:
            logger.error(f"Error resolving PyPI package {package_name}: {e}")
            return None
    
    def _resolve_npm(self, package_name: str) -> Optional[PackageResolution]:
        """
        Resolve npm package to GitHub repository.
        
        Strategy:
        1. Fetch package metadata from npm registry
        2. Check repository field
        3. Extract owner/repo from URL
        4. Assign confidence based on source
        
        Args:
            package_name: npm package name
        
        Returns:
            PackageResolution if successful, None otherwise
        """
        try:
            # Fetch package metadata
            url = f"https://registry.npmjs.org/{package_name}"
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code != 200:
                logger.debug(f"npm package not found: {package_name}")
                return None
            
            data = response.json()
            
            # Get latest version metadata
            latest_version = data.get('dist-tags', {}).get('latest')
            if not latest_version:
                logger.debug(f"No latest version for npm package: {package_name}")
                return None
            
            version_data = data.get('versions', {}).get(latest_version, {})
            
            # Check repository field
            repository = version_data.get('repository', {})
            
            if isinstance(repository, dict):
                repo_url = repository.get('url', '')
            elif isinstance(repository, str):
                repo_url = repository
            else:
                repo_url = ''
            
            if repo_url:
                repo = self._extract_github_repo(repo_url)
                if repo:
                    return PackageResolution(
                        package_name=package_name,
                        registry_type='npm',
                        repo_full_name=repo,
                        resolution_method='npm_repository',
                        confidence=0.90,  # High confidence
                        metadata={
                            'url': repo_url,
                            'package_version': latest_version,
                        }
                    )
            
            # Try homepage as fallback
            homepage = version_data.get('homepage', '')
            if homepage:
                repo = self._extract_github_repo(homepage)
                if repo:
                    return PackageResolution(
                        package_name=package_name,
                        registry_type='npm',
                        repo_full_name=repo,
                        resolution_method='npm_homepage',
                        confidence=0.70,  # Lower confidence
                        metadata={
                            'url': homepage,
                            'package_version': latest_version,
                        }
                    )
            
            # No GitHub URL found
            logger.debug(f"No GitHub URL found for npm package: {package_name}")
            return None
        
        except Exception as e:
            logger.error(f"Error resolving npm package {package_name}: {e}")
            return None
    
    def _extract_github_repo(self, url: str) -> Optional[str]:
        """
        Extract owner/repo from GitHub URL.
        
        Handles various URL formats:
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - git+https://github.com/owner/repo.git
        - git://github.com/owner/repo.git
        - github:owner/repo
        
        Args:
            url: URL to parse
        
        Returns:
            "owner/repo" if valid GitHub URL, None otherwise
        """
        if not url:
            return None
        
        # Remove git+ prefix
        url = url.replace('git+', '')
        
        # Remove .git suffix
        url = url.replace('.git', '')
        
        # Handle github:owner/repo format
        if url.startswith('github:'):
            repo = url.replace('github:', '')
            if self._is_valid_repo_format(repo):
                return repo
        
        # Extract from URL
        # Match: github.com/owner/repo
        match = re.search(r'github\.com[:/]([^/]+)/([^/\s#?]+)', url)
        if match:
            owner = match.group(1)
            repo = match.group(2)
            repo_full_name = f"{owner}/{repo}"
            
            if self._is_valid_repo_format(repo_full_name):
                return repo_full_name
        
        return None
    
    def _is_valid_repo_format(self, repo: str) -> bool:
        """
        Validate repo format.
        
        Args:
            repo: Repository in format "owner/repo"
        
        Returns:
            True if valid format, False otherwise
        """
        if not repo or '/' not in repo:
            return False
        
        parts = repo.split('/')
        if len(parts) != 2:
            return False
        
        owner, repo_name = parts
        
        # Basic validation
        if not owner or not repo_name:
            return False
        
        # Check for invalid characters
        if any(c in owner for c in ['@', ':', ' ', '\n', '\t']):
            return False
        
        if any(c in repo_name for c in ['@', ':', ' ', '\n', '\t']):
            return False
        
        return True
