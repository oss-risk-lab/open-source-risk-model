#!/usr/bin/env python3
"""
Unit tests for package resolver.

Tests package-to-repository resolution for PyPI and npm packages.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.open_source_risk_model.dependencies.package_resolver import (
    PackageResolver,
    PackageResolution
)


class TestPackageResolver:
    """Test PackageResolver class."""
    
    def setup_method(self):
        self.mock_cache_repo = Mock()
        self.resolver = PackageResolver(self.mock_cache_repo)
    
    def test_extract_github_repo_https(self):
        """Test extracting repo from HTTPS URL."""
        url = "https://github.com/psf/requests"
        repo = self.resolver._extract_github_repo(url)
        
        assert repo == "psf/requests"
    
    def test_extract_github_repo_git_suffix(self):
        """Test extracting repo from URL with .git suffix."""
        url = "https://github.com/psf/requests.git"
        repo = self.resolver._extract_github_repo(url)
        
        assert repo == "psf/requests"
    
    def test_extract_github_repo_git_protocol(self):
        """Test extracting repo from git:// URL."""
        url = "git://github.com/psf/requests.git"
        repo = self.resolver._extract_github_repo(url)
        
        assert repo == "psf/requests"
    
    def test_extract_github_repo_git_plus_https(self):
        """Test extracting repo from git+https URL."""
        url = "git+https://github.com/psf/requests.git"
        repo = self.resolver._extract_github_repo(url)
        
        assert repo == "psf/requests"
    
    def test_extract_github_repo_ssh(self):
        """Test extracting repo from SSH URL."""
        url = "git@github.com:psf/requests.git"
        repo = self.resolver._extract_github_repo(url)
        
        assert repo == "psf/requests"
    
    def test_extract_github_repo_invalid_url(self):
        """Test extracting repo from invalid URL."""
        url = "https://example.com/not-github"
        repo = self.resolver._extract_github_repo(url)
        
        assert repo is None
    
    def test_extract_github_repo_empty_url(self):
        """Test extracting repo from empty URL."""
        repo = self.resolver._extract_github_repo("")
        
        assert repo is None
    
    def test_is_valid_repo_format_valid(self):
        """Test valid repo format."""
        assert self.resolver._is_valid_repo_format("psf/requests")
        assert self.resolver._is_valid_repo_format("facebook/react")
        assert self.resolver._is_valid_repo_format("user-name/repo-name")
    
    def test_is_valid_repo_format_invalid(self):
        """Test invalid repo formats."""
        assert not self.resolver._is_valid_repo_format("invalid")
        assert not self.resolver._is_valid_repo_format("too/many/slashes")
        assert not self.resolver._is_valid_repo_format("")
        assert not self.resolver._is_valid_repo_format(None)
    
    @patch('requests.get')
    def test_resolve_pypi_project_urls(self, mock_get):
        """Test PyPI resolution using project_urls."""
        # Mock PyPI API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "info": {
                "project_urls": {
                    "Source": "https://github.com/psf/requests"
                }
            }
        }
        mock_get.return_value = mock_response
        
        # Mock cache miss
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("requests", "pypi")
        
        assert resolution.package_name == "requests"
        assert resolution.registry_type == "pypi"
        assert resolution.repo_full_name == "psf/requests"
        assert resolution.confidence == 0.95
        assert resolution.resolution_method == "pypi_project_urls"
    
    @patch('requests.get')
    def test_resolve_pypi_home_page_fallback(self, mock_get):
        """Test PyPI resolution falling back to home_page."""
        # Mock PyPI API response without project_urls
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "info": {
                "home_page": "https://github.com/psf/requests"
            }
        }
        mock_get.return_value = mock_response
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("requests", "pypi")
        
        assert resolution.repo_full_name == "psf/requests"
        assert resolution.confidence == 0.75
        assert resolution.resolution_method == "pypi_home_page"
    
    @patch('requests.get')
    def test_resolve_pypi_not_found(self, mock_get):
        """Test PyPI resolution when package not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("nonexistent-package", "pypi")
        
        assert resolution.repo_full_name is None
        assert resolution.confidence == 0.0
        assert resolution.resolution_method == "unresolved"
    
    @patch('requests.get')
    def test_resolve_npm_repository_field(self, mock_get):
        """Test npm resolution using repository field."""
        # Mock npm registry response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "repository": {
                "type": "git",
                "url": "https://github.com/facebook/react.git"
            }
        }
        mock_get.return_value = mock_response
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("react", "npm")
        
        assert resolution.package_name == "react"
        assert resolution.registry_type == "npm"
        assert resolution.repo_full_name == "facebook/react"
        assert resolution.confidence == 0.90
        assert resolution.resolution_method == "npm_repository_field"
    
    @patch('requests.get')
    def test_resolve_npm_repository_string(self, mock_get):
        """Test npm resolution with repository as string."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "repository": "https://github.com/lodash/lodash.git"
        }
        mock_get.return_value = mock_response
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("lodash", "npm")
        
        assert resolution.repo_full_name == "lodash/lodash"
        assert resolution.confidence == 0.90
    
    @patch('requests.get')
    def test_resolve_npm_homepage_fallback(self, mock_get):
        """Test npm resolution falling back to homepage."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "homepage": "https://github.com/expressjs/express"
        }
        mock_get.return_value = mock_response
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("express", "npm")
        
        assert resolution.repo_full_name == "expressjs/express"
        assert resolution.confidence == 0.70
        assert resolution.resolution_method == "npm_homepage"
    
    def test_resolve_from_cache(self):
        """Test resolution from cache."""
        # Mock cache hit
        self.mock_cache_repo.get_mapping.return_value = {
            "package_name": "requests",
            "registry_type": "pypi",
            "repo_full_name": "psf/requests",
            "confidence": 0.95,
            "resolution_method": "pypi_project_urls",
            "metadata": {}
        }
        
        resolution = self.resolver.resolve("requests", "pypi")
        
        assert resolution.repo_full_name == "psf/requests"
        assert resolution.confidence == 0.95
        
        # Verify cache was checked
        self.mock_cache_repo.get_mapping.assert_called_once_with("requests", "pypi")
    
    @patch('requests.get')
    def test_resolve_saves_to_cache(self, mock_get):
        """Test that resolution is saved to cache."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "info": {
                "project_urls": {
                    "Source": "https://github.com/psf/requests"
                }
            }
        }
        mock_get.return_value = mock_response
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        self.resolver.resolve("requests", "pypi")
        
        # Verify cache was updated
        self.mock_cache_repo.save_mapping.assert_called_once()
        
        # Check the saved resolution
        saved_resolution = self.mock_cache_repo.save_mapping.call_args[0][0]
        assert saved_resolution.package_name == "requests"
        assert saved_resolution.repo_full_name == "psf/requests"
    
    @patch('requests.get')
    def test_resolve_handles_timeout(self, mock_get):
        """Test that resolution handles timeouts gracefully."""
        import requests
        mock_get.side_effect = requests.Timeout()
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("requests", "pypi")
        
        assert resolution.repo_full_name is None
        assert resolution.confidence == 0.0
        assert resolution.resolution_method == "unresolved"
    
    @patch('requests.get')
    def test_resolve_handles_connection_error(self, mock_get):
        """Test that resolution handles connection errors gracefully."""
        import requests
        mock_get.side_effect = requests.ConnectionError()
        
        self.mock_cache_repo.get_mapping.return_value = None
        
        resolution = self.resolver.resolve("requests", "pypi")
        
        assert resolution.repo_full_name is None
        assert resolution.confidence == 0.0
    
    def test_unresolved_package(self):
        """Test unresolved package result."""
        resolution = self.resolver._unresolved("unknown-package", "pypi")
        
        assert resolution.package_name == "unknown-package"
        assert resolution.registry_type == "pypi"
        assert resolution.repo_full_name is None
        assert resolution.confidence == 0.0
        assert resolution.resolution_method == "unresolved"
        assert resolution.metadata == {}


class TestPackageResolution:
    """Test PackageResolution dataclass."""
    
    def test_create_resolution(self):
        """Test creating a PackageResolution."""
        resolution = PackageResolution(
            package_name="requests",
            registry_type="pypi",
            repo_full_name="psf/requests",
            confidence=0.95,
            resolution_method="pypi_project_urls",
            metadata={"url": "https://github.com/psf/requests"}
        )
        
        assert resolution.package_name == "requests"
        assert resolution.registry_type == "pypi"
        assert resolution.repo_full_name == "psf/requests"
        assert resolution.confidence == 0.95
        assert resolution.resolution_method == "pypi_project_urls"
        assert "url" in resolution.metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
