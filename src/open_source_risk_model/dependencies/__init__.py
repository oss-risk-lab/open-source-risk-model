"""
Dependency graph components for parsing and resolving dependencies.

This package provides:
- Manifest discovery (tree scanning)
- Dependency parsers (requirements.txt, pyproject.toml, package.json)
- Package resolution (package → repository mapping)
- Rate limiting and caching
"""

from .manifest_discovery import ManifestDiscovery
from .parsers import (
    Dependency,
    DependencyParser,
    RequirementsTxtParser,
    PyProjectTomlParser,
    PackageJsonParser,
    DependencyParserRegistry,
)
from .manifest_cache import ManifestCache
from .rate_limiter import RateLimitTracker, DependencyIngestionConfig

__all__ = [
    "ManifestDiscovery",
    "Dependency",
    "DependencyParser",
    "RequirementsTxtParser",
    "PyProjectTomlParser",
    "PackageJsonParser",
    "DependencyParserRegistry",
    "ManifestCache",
    "RateLimitTracker",
    "DependencyIngestionConfig",
]
