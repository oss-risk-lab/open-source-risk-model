"""
Dependency scope filtering for query API.

Defines scope semantics and filtering logic for production vs build vs all dependencies.
"""

from enum import Enum
from typing import List, Dict, Any


class DependencyScope(str, Enum):
    """
    Dependency scope for filtering.
    
    - prod: Production/runtime dependencies only
    - build: Production + dev/test/build tooling (CI/build pipeline)
    - all: Everything including optional extras
    """
    PROD = "prod"
    BUILD = "build"
    ALL = "all"


# Dependency groups that are considered production/runtime
PROD_GROUPS = {
    "prod",
    "runtime",
    "standard",
    "",  # Empty string means main/default dependencies
}

# Dependency groups that are build/dev/test related
BUILD_GROUPS = {
    "dev",
    "test",
    "lint",
    "docs",
    "doc",
    "ci",
    "build",
    "tooling",
    "github-actions",
    "typing",
}

# Dependency groups that are optional extras/features
OPTIONAL_GROUPS = {
    "async",
    "dotenv",
    "speedups",
    "cli",
    "brotli",
    "jupyter",
    "argon2",
    "bcrypt",
    "colorama",
    "completion",
    "http2",
    "i18n",
    "socks",
    "uvloop",
    "watchdog",
    "zstd",
    "d",  # Some packages use single-letter extras
}


def filter_dependencies_by_scope(
    dependencies: List[Dict[str, Any]],
    scope: DependencyScope
) -> List[Dict[str, Any]]:
    """
    Filter dependencies based on scope.
    
    Scope semantics:
    - prod: Only production/runtime dependencies (non-optional, prod groups)
    - build: Production + dev/test/build dependencies (excludes optional extras)
    - all: Everything (prod + build + optional extras)
    
    Args:
        dependencies: List of dependency records
        scope: Dependency scope to filter by
    
    Returns:
        Filtered list of dependencies
    """
    if scope == DependencyScope.ALL:
        # Return everything
        return dependencies
    
    filtered = []
    
    for dep in dependencies:
        dependency_group = dep.get("dependency_group", "")
        is_optional = dep.get("is_optional", 0)
        
        # Normalize group (handle None, empty string)
        if dependency_group is None:
            dependency_group = ""
        
        # Check if this is an optional extra
        is_optional_extra = (
            is_optional == 1 or 
            dependency_group.lower() in OPTIONAL_GROUPS
        )
        
        if scope == DependencyScope.PROD:
            # Production only: exclude optional extras and build/dev groups
            if is_optional_extra:
                continue
            if dependency_group.lower() in BUILD_GROUPS:
                continue
            # Include if it's a prod group or peer dependency
            if dependency_group.lower() in PROD_GROUPS or dependency_group.lower() == "peer":
                filtered.append(dep)
        
        elif scope == DependencyScope.BUILD:
            # Build: include prod + build groups, exclude optional extras
            if is_optional_extra:
                continue
            # Include prod, build, and peer groups
            if (dependency_group.lower() in PROD_GROUPS or 
                dependency_group.lower() in BUILD_GROUPS or
                dependency_group.lower() == "peer"):
                filtered.append(dep)
    
    return filtered


def get_scope_description(scope: DependencyScope) -> str:
    """
    Get human-readable description of scope.
    
    Args:
        scope: Dependency scope
    
    Returns:
        Description string
    """
    descriptions = {
        DependencyScope.PROD: "Production/runtime dependencies only",
        DependencyScope.BUILD: "Production + dev/test/build dependencies",
        DependencyScope.ALL: "All dependencies including optional extras"
    }
    return descriptions.get(scope, "Unknown scope")
