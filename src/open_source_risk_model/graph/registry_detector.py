"""
Registry detector - detects package registries from repository files.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional

# Set up logger
logger = logging.getLogger(__name__)


@dataclass
class RegistryInfo:
    """
    Detected package registry information.
    
    Attributes:
        registry_type: Type of registry (pypi, npm, maven, rubygems, crates)
        package_name: Name of the package in the registry
        detected_from: Filename that indicated the registry
        match_confidence: Confidence in package name extraction (0.0-1.0)
        latest_version: Latest version (optional, for future API integration)
        download_count: Download count (optional, for future API integration)
    """
    registry_type: str
    package_name: str
    detected_from: str
    match_confidence: float
    latest_version: Optional[str] = None
    download_count: Optional[int] = None


class RegistryDetector:
    """
    Detects package registries from repository manifest files.
    
    Supports detection for:
    - PyPI (setup.py, pyproject.toml)
    - npm (package.json)
    - Maven (pom.xml)
    - RubyGems (*.gemspec, Gemfile)
    - crates.io (Cargo.toml)
    """
    
    def __init__(self, github_session):
        """
        Initialize registry detector.
        
        Args:
            github_session: Authenticated requests session for GitHub API
        """
        self.session = github_session
    
    def detect_registries(self, owner: str, repo: str) -> List[RegistryInfo]:
        """
        Detect package registries from repository files.
        
        Args:
            owner: Repository owner
            repo: Repository name
        
        Returns:
            List of detected registry information
        """
        registries = []
        
        try:
            # Fetch repository contents (root directory)
            url = f"https://api.github.com/repos/{owner}/{repo}/contents"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            contents = response.json()
            
            # Build a set of filenames for quick lookup
            filenames = {item["name"]: item for item in contents if item["type"] == "file"}
            
            # Check for Python ecosystem (PyPI)
            if "pyproject.toml" in filenames:
                registry_info = self._detect_pypi_from_pyproject(owner, repo)
                if registry_info:
                    registries.append(registry_info)
            elif "setup.py" in filenames:
                registry_info = self._detect_pypi_from_setup(owner, repo)
                if registry_info:
                    registries.append(registry_info)
            
            # Check for JavaScript ecosystem (npm)
            if "package.json" in filenames:
                registry_info = self._detect_npm(owner, repo)
                if registry_info:
                    registries.append(registry_info)
            
            # Check for Java ecosystem (Maven)
            if "pom.xml" in filenames:
                registry_info = self._detect_maven(owner, repo)
                if registry_info:
                    registries.append(registry_info)
            
            # Check for Ruby ecosystem (RubyGems)
            gemspec_files = [f for f in filenames if f.endswith(".gemspec")]
            if gemspec_files:
                registry_info = self._detect_rubygems_from_gemspec(owner, repo, gemspec_files[0])
                if registry_info:
                    registries.append(registry_info)
            elif "Gemfile" in filenames:
                # Fallback to repo name if only Gemfile exists
                registries.append(RegistryInfo(
                    registry_type="rubygems",
                    package_name=repo,
                    detected_from="Gemfile",
                    match_confidence=0.6,  # Lower confidence for Gemfile-only detection
                ))
            
            # Check for Rust ecosystem (crates.io)
            if "Cargo.toml" in filenames:
                registry_info = self._detect_crates(owner, repo)
                if registry_info:
                    registries.append(registry_info)
            
            logger.info(f"Detected {len(registries)} registries for {owner}/{repo}")
            return registries
            
        except Exception as e:
            logger.warning(f"Failed to detect registries for {owner}/{repo}: {e}")
            return []
    
    def _detect_pypi_from_pyproject(self, owner: str, repo: str) -> Optional[RegistryInfo]:
        """Detect PyPI registry from pyproject.toml."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/pyproject.toml"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
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
                        package_name = name_part.strip('"').strip("'")
                        return RegistryInfo(
                            registry_type="pypi",
                            package_name=package_name,
                            detected_from="pyproject.toml",
                            match_confidence=0.9,  # High confidence from pyproject.toml
                        )
            
            # Fallback: use repo name
            return RegistryInfo(
                registry_type="pypi",
                package_name=repo.lower().replace("-", "_"),
                detected_from="pyproject.toml",
                match_confidence=0.7,  # Lower confidence for fallback
            )
            
        except Exception as e:
            logger.debug(f"Failed to detect PyPI from pyproject.toml: {e}")
            return None
    
    def _detect_pypi_from_setup(self, owner: str, repo: str) -> Optional[RegistryInfo]:
        """Detect PyPI registry from setup.py."""
        try:
            # For setup.py, we'll use a heuristic approach
            # Parsing setup.py with AST is complex, so we use repo name as fallback
            return RegistryInfo(
                registry_type="pypi",
                package_name=repo.lower().replace("-", "_"),
                detected_from="setup.py",
                match_confidence=0.7,  # Lower confidence for heuristic
            )
            
        except Exception as e:
            logger.debug(f"Failed to detect PyPI from setup.py: {e}")
            return None
    
    def _detect_npm(self, owner: str, repo: str) -> Optional[RegistryInfo]:
        """Detect npm registry from package.json."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/package.json"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            package_data = json.loads(content)
            
            package_name = package_data.get("name", repo)
            
            return RegistryInfo(
                registry_type="npm",
                package_name=package_name,
                detected_from="package.json",
                match_confidence=0.95,  # Very high confidence from package.json
            )
            
        except Exception as e:
            logger.debug(f"Failed to detect npm from package.json: {e}")
            return None
    
    def _detect_maven(self, owner: str, repo: str) -> Optional[RegistryInfo]:
        """Detect Maven registry from pom.xml."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/pom.xml"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            
            # Parse XML to extract artifactId
            try:
                root = ET.fromstring(content)
                # Handle XML namespaces
                namespace = {"maven": "http://maven.apache.org/POM/4.0.0"}
                
                # Try with namespace first
                artifact_id = root.find(".//maven:artifactId", namespace)
                if artifact_id is None:
                    # Try without namespace
                    artifact_id = root.find(".//artifactId")
                
                if artifact_id is not None and artifact_id.text:
                    return RegistryInfo(
                        registry_type="maven",
                        package_name=artifact_id.text,
                        detected_from="pom.xml",
                        match_confidence=0.9,  # High confidence from XML parsing
                    )
            except ET.ParseError:
                # Fallback to regex if XML parsing fails
                match = re.search(r"<artifactId>([^<]+)</artifactId>", content)
                if match:
                    return RegistryInfo(
                        registry_type="maven",
                        package_name=match.group(1),
                        detected_from="pom.xml",
                        match_confidence=0.85,  # Slightly lower confidence for regex
                    )
            
            # Fallback: use repo name
            return RegistryInfo(
                registry_type="maven",
                package_name=repo,
                detected_from="pom.xml",
                match_confidence=0.7,  # Lower confidence for fallback
            )
            
        except Exception as e:
            logger.debug(f"Failed to detect Maven from pom.xml: {e}")
            return None
    
    def _detect_rubygems_from_gemspec(self, owner: str, repo: str, gemspec_file: str) -> Optional[RegistryInfo]:
        """Detect RubyGems registry from .gemspec file."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{gemspec_file}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            
            # Look for spec.name = "package_name" pattern
            match = re.search(r'\.name\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return RegistryInfo(
                    registry_type="rubygems",
                    package_name=match.group(1),
                    detected_from=gemspec_file,
                    match_confidence=0.9,  # High confidence from gemspec
                )
            
            # Fallback: use repo name
            return RegistryInfo(
                registry_type="rubygems",
                package_name=repo,
                detected_from=gemspec_file,
                match_confidence=0.7,  # Lower confidence for fallback
            )
            
        except Exception as e:
            logger.debug(f"Failed to detect RubyGems from {gemspec_file}: {e}")
            return None
    
    def _detect_crates(self, owner: str, repo: str) -> Optional[RegistryInfo]:
        """Detect crates.io registry from Cargo.toml."""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/Cargo.toml"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            content = base64.b64decode(response.json()["content"]).decode("utf-8")
            
            # Look for name = "package_name" in [package] section
            in_package_section = False
            for line in content.split("\n"):
                line = line.strip()
                if line == "[package]":
                    in_package_section = True
                elif line.startswith("[") and in_package_section:
                    in_package_section = False
                elif in_package_section and line.startswith("name"):
                    # Extract name value
                    if "=" in line:
                        name_part = line.split("=", 1)[1].strip()
                        # Remove quotes
                        package_name = name_part.strip('"').strip("'")
                        return RegistryInfo(
                            registry_type="crates",
                            package_name=package_name,
                            detected_from="Cargo.toml",
                            match_confidence=0.9,  # High confidence from Cargo.toml
                        )
            
            # Fallback: use repo name
            return RegistryInfo(
                registry_type="crates",
                package_name=repo,
                detected_from="Cargo.toml",
                match_confidence=0.7,  # Lower confidence for fallback
            )
            
        except Exception as e:
            logger.debug(f"Failed to detect crates.io from Cargo.toml: {e}")
            return None
