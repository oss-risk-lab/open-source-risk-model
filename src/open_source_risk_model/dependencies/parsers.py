"""
Dependency parsers for various manifest formats.

Supports:
- requirements.txt (Python)
- pyproject.toml (Python - PEP 621 + Poetry)
- package.json (JavaScript)
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from open_source_risk_model.dependencies.scope_classifier import classify

logger = logging.getLogger(__name__)


@dataclass
class Dependency:
    """Represents a parsed dependency."""
    package_name: str
    specifier: str = ""
    extras: List[str] = field(default_factory=list)
    markers: str = ""
    dependency_group: str = "prod"
    is_optional: bool = False
    manifest_path: str = ""
    dependency_scope: str = "unknown"
    scope_confidence: str = "low"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'package_name': self.package_name,
            'specifier': self.specifier,
            'extras': self.extras,
            'markers': self.markers,
            'dependency_group': self.dependency_group,
            'is_optional': self.is_optional,
            'manifest_path': self.manifest_path,
            'dependency_scope': self.dependency_scope,
            'scope_confidence': self.scope_confidence,
        }


class DependencyParser(ABC):
    """Base class for dependency parsers."""
    
    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """Check if this parser can handle the file."""
        pass
    
    @abstractmethod
    def parse(self, content: str, source_file: str = "") -> List[Dependency]:
        """Parse dependencies from file content.
        
        Args:
            content: Raw file content to parse.
            source_file: Path to the manifest file, used for filename-based
                classification (e.g. requirements-dev.txt).
        """
        pass


class RequirementsTxtParser(DependencyParser):
    """Parser for requirements.txt files."""
    
    def can_parse(self, file_path: str) -> bool:
        """Match any requirements file in any directory."""
        return bool(re.search(r'requirements.*\.txt$', file_path))
    
    def parse(self, content: str, source_file: str = "") -> List[Dependency]:
        """
        Parse requirements.txt content.
        
        Supports:
        - Simple: requests
        - Versioned: requests>=2.0.0
        - Extras: requests[security]>=2.0.0
        - Markers: requests>=2.0.0; python_version>='3.7'
        - Comments and blank lines
        
        Args:
            content: Raw requirements.txt content.
            source_file: Path to the requirements file, used for
                filename-based scope classification.
        """
        dependencies = []
        
        for line in content.splitlines():
            line = line.strip()
            
            # Skip comments and blank lines
            if not line or line.startswith('#'):
                continue
            
            # Skip editable installs and URLs
            if line.startswith('-e') or line.startswith('http'):
                continue
            
            # Parse requirement
            dep = self._parse_requirement(line)
            if dep:
                scope, confidence = classify(
                    ecosystem="pypi",
                    manifest_type="requirements.txt",
                    dependency_group=dep.dependency_group,
                    source_file=source_file,
                )
                dep.dependency_scope = scope.value
                dep.scope_confidence = confidence.value
                dependencies.append(dep)
        
        return dependencies
    
    def _parse_requirement(self, line: str) -> Optional[Dependency]:
        """Parse a single requirement line using packaging library."""
        try:
            from packaging.requirements import Requirement
            
            req = Requirement(line)
            
            return Dependency(
                package_name=req.name,
                specifier=str(req.specifier) if req.specifier else "",
                extras=list(req.extras) if req.extras else [],
                markers=str(req.marker) if req.marker else "",
                dependency_group="prod",
                is_optional=False
            )
        
        except Exception as e:
            # Fallback to simple regex parsing
            logger.debug(f"Failed to parse requirement with packaging library: {line}: {e}")
            return self._parse_requirement_fallback(line)
    
    def _parse_requirement_fallback(self, line: str) -> Optional[Dependency]:
        """Fallback parser using regex."""
        # Remove environment markers
        if ';' in line:
            line = line.split(';')[0].strip()
        
        # Match: package[extras]>=version
        match = re.match(r'^([a-zA-Z0-9_-]+)(\[[\w,]+\])?(.*)?$', line)
        if match:
            package_name = match.group(1)
            extras_str = match.group(2)
            specifier = match.group(3).strip() if match.group(3) else ""
            
            # Parse extras
            extras = []
            if extras_str:
                extras_str = extras_str.strip('[]')
                extras = [e.strip() for e in extras_str.split(',')]
            
            return Dependency(
                package_name=package_name,
                specifier=specifier,
                extras=extras,
                dependency_group="prod",
                is_optional=False
            )
        
        return None


class PyProjectTomlParser(DependencyParser):
    """Parser for pyproject.toml (PEP 621 + Poetry)."""
    
    def can_parse(self, file_path: str) -> bool:
        """Check if file is pyproject.toml."""
        return file_path.endswith('pyproject.toml')
    
    def parse(self, content: str, source_file: str = "") -> List[Dependency]:
        """
        Parse pyproject.toml content.
        
        Supports:
        - PEP 621: [project] dependencies
        - Poetry: [tool.poetry.dependencies]
        """
        try:
            # Try tomllib (Python 3.11+) first, fall back to tomli
            try:
                import tomllib
                data = tomllib.loads(content)
            except ImportError:
                import tomli
                data = tomli.loads(content)
        except Exception as e:
            logger.error(f"Failed to parse TOML: {e}")
            return []
        
        dependencies = []
        
        # Parse PEP 621 format
        dependencies.extend(self._parse_pep621(data))
        
        # Parse Poetry format
        dependencies.extend(self._parse_poetry(data))
        
        return dependencies
    
    def _parse_pep621(self, data: dict) -> List[Dependency]:
        """Parse PEP 621 [project] dependencies."""
        dependencies = []
        project = data.get('project', {})
        
        # Production dependencies
        for dep_spec in project.get('dependencies', []):
            dep = self._parse_pep621_spec(dep_spec)
            if dep:
                scope, confidence = classify(
                    ecosystem="pypi",
                    manifest_type="pyproject.toml",
                    dependency_group="prod",
                    source_file="",
                    is_optional=False,
                )
                dep.dependency_scope = scope.value
                dep.scope_confidence = confidence.value
                dependencies.append(dep)
        
        # Optional dependencies (dev, test, etc.)
        for group, deps in project.get('optional-dependencies', {}).items():
            for dep_spec in deps:
                dep = self._parse_pep621_spec(dep_spec)
                if dep:
                    dep.dependency_group = group
                    dep.is_optional = True
                    scope, confidence = classify(
                        ecosystem="pypi",
                        manifest_type="pyproject.toml",
                        dependency_group=group,
                        source_file="",
                        is_optional=True,
                    )
                    dep.dependency_scope = scope.value
                    dep.scope_confidence = confidence.value
                    dependencies.append(dep)
        
        return dependencies
    
    def _parse_pep621_spec(self, spec: str) -> Optional[Dependency]:
        """Parse PEP 621 dependency spec."""
        try:
            from packaging.requirements import Requirement
            
            req = Requirement(spec)
            
            return Dependency(
                package_name=req.name,
                specifier=str(req.specifier) if req.specifier else "",
                extras=list(req.extras) if req.extras else [],
                markers=str(req.marker) if req.marker else "",
                dependency_group="prod",
                is_optional=False
            )
        
        except Exception as e:
            logger.debug(f"Failed to parse PEP 621 spec: {spec}: {e}")
            return None
    
    def _parse_poetry(self, data: dict) -> List[Dependency]:
        """Parse Poetry [tool.poetry.dependencies]."""
        dependencies = []
        poetry = data.get('tool', {}).get('poetry', {})
        
        # Poetry dependencies (main/prod)
        for name, spec in poetry.get('dependencies', {}).items():
            if name == 'python':  # Skip Python version
                continue
            
            dep = self._parse_poetry_spec(name, spec)
            if dep:
                is_opt = dep.is_optional
                scope, confidence = classify(
                    ecosystem="pypi",
                    manifest_type="pyproject.toml",
                    dependency_group="prod",
                    source_file="",
                    is_optional=is_opt,
                )
                dep.dependency_scope = scope.value
                dep.scope_confidence = confidence.value
                dependencies.append(dep)
        
        # Poetry dev dependencies (legacy format)
        for name, spec in poetry.get('dev-dependencies', {}).items():
            dep = self._parse_poetry_spec(name, spec)
            if dep:
                dep.dependency_group = 'dev'
                scope, confidence = classify(
                    ecosystem="pypi",
                    manifest_type="pyproject.toml",
                    dependency_group="dev",
                    source_file="",
                    is_optional=False,
                )
                dep.dependency_scope = scope.value
                dep.scope_confidence = confidence.value
                dependencies.append(dep)
        
        # Poetry group dependencies (modern format)
        for group_name, group_data in poetry.get('group', {}).items():
            for name, spec in group_data.get('dependencies', {}).items():
                dep = self._parse_poetry_spec(name, spec)
                if dep:
                    dep.dependency_group = group_name
                    scope, confidence = classify(
                        ecosystem="pypi",
                        manifest_type="pyproject.toml",
                        dependency_group=group_name,
                        source_file="",
                        is_optional=False,
                    )
                    dep.dependency_scope = scope.value
                    dep.scope_confidence = confidence.value
                    dependencies.append(dep)
        
        return dependencies
    
    def _parse_poetry_spec(self, name: str, spec: Any) -> Optional[Dependency]:
        """Parse Poetry dependency spec."""
        if isinstance(spec, str):
            return Dependency(
                package_name=name,
                specifier=spec,
                dependency_group="prod",
                is_optional=False
            )
        elif isinstance(spec, dict):
            return Dependency(
                package_name=name,
                specifier=spec.get('version', ''),
                dependency_group="prod",
                is_optional=spec.get('optional', False)
            )
        
        return None


class PackageJsonParser(DependencyParser):
    """Parser for package.json files."""
    
    def can_parse(self, file_path: str) -> bool:
        """Check if file is package.json."""
        return file_path.endswith('package.json')
    
    def parse(self, content: str, source_file: str = "") -> List[Dependency]:
        """
        Parse package.json content.
        
        Supports:
        - dependencies
        - devDependencies
        - peerDependencies
        - optionalDependencies
        """
        try:
            import json
            data = json.loads(content)
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
            return []
        
        dependencies = []
        
        # Production dependencies
        for name, version in data.get('dependencies', {}).items():
            dep = Dependency(
                package_name=name,
                specifier=version,
                dependency_group="prod",
                is_optional=False,
            )
            scope, confidence = classify(
                ecosystem="npm",
                manifest_type="package.json",
                dependency_group="prod",
                source_file="",
            )
            dep.dependency_scope = scope.value
            dep.scope_confidence = confidence.value
            dependencies.append(dep)
        
        # Dev dependencies
        for name, version in data.get('devDependencies', {}).items():
            dep = Dependency(
                package_name=name,
                specifier=version,
                dependency_group="dev",
                is_optional=False,
            )
            scope, confidence = classify(
                ecosystem="npm",
                manifest_type="package.json",
                dependency_group="dev",
                source_file="",
            )
            dep.dependency_scope = scope.value
            dep.scope_confidence = confidence.value
            dependencies.append(dep)
        
        # Peer dependencies
        for name, version in data.get('peerDependencies', {}).items():
            dep = Dependency(
                package_name=name,
                specifier=version,
                dependency_group="peer",
                is_optional=False,
            )
            scope, confidence = classify(
                ecosystem="npm",
                manifest_type="package.json",
                dependency_group="peer",
                source_file="",
            )
            dep.dependency_scope = scope.value
            dep.scope_confidence = confidence.value
            dependencies.append(dep)
        
        # Optional dependencies
        for name, version in data.get('optionalDependencies', {}).items():
            dep = Dependency(
                package_name=name,
                specifier=version,
                dependency_group="optional",
                is_optional=True,
            )
            scope, confidence = classify(
                ecosystem="npm",
                manifest_type="package.json",
                dependency_group="optional",
                source_file="",
            )
            dep.dependency_scope = scope.value
            dep.scope_confidence = confidence.value
            dependencies.append(dep)
        
        return dependencies


class DependencyParserRegistry:
    """Registry of dependency parsers."""
    
    def __init__(self):
        """Initialize with default parsers."""
        self.parsers: List[DependencyParser] = [
            RequirementsTxtParser(),
            PyProjectTomlParser(),
            PackageJsonParser(),
        ]
    
    def register(self, parser: DependencyParser):
        """Register a custom parser."""
        self.parsers.append(parser)
    
    def parse_file(self, file_path: str, content: str) -> List[Dependency]:
        """
        Parse file using appropriate parser.
        
        Args:
            file_path: Path to manifest file
            content: File content
        
        Returns:
            List of parsed dependencies
        """
        for parser in self.parsers:
            if parser.can_parse(file_path):
                try:
                    dependencies = parser.parse(content, source_file=file_path)
                    logger.info(f"Parsed {len(dependencies)} dependencies from {file_path}")
                    
                    # Set manifest_path on each dependency
                    for dep in dependencies:
                        dep.manifest_path = file_path
                    
                    return dependencies
                except Exception as e:
                    logger.error(f"Parser failed for {file_path}: {e}")
                    return []
        
        logger.warning(f"No parser found for {file_path}")
        return []
    
    def infer_registry_type(self, manifest_path: str) -> str:
        """Infer registry type from manifest path."""
        path_lower = manifest_path.lower()
        
        # Python
        if any(x in path_lower for x in ['requirements', 'pyproject.toml', 'setup.cfg', 'pipfile']):
            return 'pypi'
        
        # JavaScript
        if 'package.json' in path_lower or 'package-lock.json' in path_lower:
            return 'npm'
        
        # Java
        if 'pom.xml' in path_lower or 'build.gradle' in path_lower:
            return 'maven'
        
        # Go
        if 'go.mod' in path_lower:
            return 'go'
        
        return 'unknown'
