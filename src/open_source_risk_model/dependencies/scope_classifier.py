"""
Dependency scope classifier.

Pure-function module that maps manifest metadata to (dependency_scope, scope_confidence)
tuples. Stateless, deterministic, and never raises exceptions — always falls through
to the (unknown, low) default.
"""

from enum import Enum
from typing import List, Tuple


class DependencyScope(str, Enum):
    RUNTIME = "runtime"
    DEV = "dev"
    TEST = "test"
    BUILD = "build"
    OPTIONAL = "optional"
    PEER = "peer"
    UNKNOWN = "unknown"


class ScopeConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def classify(
    ecosystem: str,
    manifest_type: str,
    dependency_group: str,
    source_file: str,
    is_optional: bool = False,
) -> Tuple[DependencyScope, ScopeConfidence]:
    """Classify a dependency's scope from manifest metadata.

    Pure function. No side effects. Deterministic.

    Args:
        ecosystem: "npm", "pypi", "cargo", etc.
        manifest_type: "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml"
        dependency_group: The group/section the dep was parsed from
            (e.g. "prod", "dev", "test", "peer").
        source_file: Full manifest file path (e.g. "requirements-dev.txt").
        is_optional: Whether the dependency was marked optional in the manifest.

    Returns:
        (DependencyScope, ScopeConfidence) tuple.

    Note:
        dependency_group is normalized to "unknown" if None before classification.
    """
    # Defensive normalization — parsers may pass None
    dependency_group = dependency_group or "unknown"
    group = dependency_group.lower()
    eco = ecosystem.lower()
    manifest = manifest_type.lower()

    if eco == "npm":
        return _classify_npm(group)

    if eco == "pypi":
        if manifest == "pyproject.toml":
            return _classify_pyproject(group, is_optional)
        if manifest == "requirements.txt":
            return _classify_requirements(source_file)

    if eco == "cargo":
        return _classify_cargo(group)

    # Fallback for any unrecognized ecosystem / manifest
    return DependencyScope.UNKNOWN, ScopeConfidence.LOW


# ---------------------------------------------------------------------------
# Ecosystem-specific classifiers (private helpers)
# ---------------------------------------------------------------------------

def _classify_npm(group: str) -> Tuple[DependencyScope, ScopeConfidence]:
    """Classify an npm/package.json dependency by its group."""
    if group == "prod":
        return DependencyScope.RUNTIME, ScopeConfidence.HIGH
    if group == "dev":
        return DependencyScope.DEV, ScopeConfidence.HIGH
    if group == "optional":
        return DependencyScope.OPTIONAL, ScopeConfidence.HIGH
    if group == "peer":
        return DependencyScope.PEER, ScopeConfidence.MEDIUM
    return DependencyScope.UNKNOWN, ScopeConfidence.LOW


def _classify_pyproject(
    group: str,
    is_optional: bool,
) -> Tuple[DependencyScope, ScopeConfidence]:
    """Classify a pyproject.toml dependency (PEP 621 + Poetry).

    The same rules cover both PEP 621 and Poetry because the parsers already
    normalize group names before calling classify():
      - PEP 621 main deps → group="prod"
      - Poetry main deps  → group="prod"
      - Named groups keep their name (dev, test, docs, lint, …)
      - Poetry optional / extras → is_optional=True
    """
    # Main / production dependencies
    if group == "prod":
        return DependencyScope.RUNTIME, ScopeConfidence.HIGH

    # Optional dependencies (PEP 621 optional-dependencies or Poetry optional/extras)
    # that are NOT in a recognized dev/test/docs group
    _dev_test_docs = {"dev", "test", "docs"}
    if is_optional and group not in _dev_test_docs:
        return DependencyScope.OPTIONAL, ScopeConfidence.HIGH

    # Dev-like groups
    if group in {"dev", "lint", "typecheck", "tooling"}:
        return DependencyScope.DEV, ScopeConfidence.HIGH

    # Test group
    if group == "test":
        return DependencyScope.TEST, ScopeConfidence.HIGH

    # Docs group — classified as build
    if group == "docs":
        return DependencyScope.BUILD, ScopeConfidence.MEDIUM

    return DependencyScope.UNKNOWN, ScopeConfidence.LOW


def _classify_requirements(source_file: str) -> Tuple[DependencyScope, ScopeConfidence]:
    """Classify a Python requirements.txt dependency by filename pattern.

    Patterns use case-insensitive substring matching on the filename:
      - Plain ``requirements.txt`` → runtime / medium
      - Filename contains "dev" → dev / high
      - Filename contains "test" → test / high
      - Filename contains "docs" → build / medium
      - Anything else → unknown / low
    """
    import os

    filename = os.path.basename(source_file).lower()

    # Exact match for the canonical requirements.txt
    if filename == "requirements.txt":
        return DependencyScope.RUNTIME, ScopeConfidence.MEDIUM

    # Dev pattern: *dev*requirements* or *requirements*dev*
    if "dev" in filename:
        return DependencyScope.DEV, ScopeConfidence.HIGH

    # Test pattern
    if "test" in filename:
        return DependencyScope.TEST, ScopeConfidence.HIGH

    # Docs pattern
    if "docs" in filename:
        return DependencyScope.BUILD, ScopeConfidence.MEDIUM

    # Unrecognized filename
    return DependencyScope.UNKNOWN, ScopeConfidence.LOW


def _classify_cargo(group: str) -> Tuple[DependencyScope, ScopeConfidence]:
    """Classify a Cargo.toml dependency by its group."""
    if group == "prod":
        return DependencyScope.RUNTIME, ScopeConfidence.HIGH
    if group == "dev":
        return DependencyScope.DEV, ScopeConfidence.HIGH
    if group == "build":
        return DependencyScope.BUILD, ScopeConfidence.HIGH
    return DependencyScope.UNKNOWN, ScopeConfidence.LOW


# ---------------------------------------------------------------------------
# Scope priority model for transitive propagation (Phase 2)
# ---------------------------------------------------------------------------

SCOPE_PRIORITY: dict[str, int] = {
    "runtime": 7,
    "optional": 6,
    "peer": 5,
    "build": 4,
    "test": 3,
    "dev": 2,
    "unknown": 1,
}

CONFIDENCE_PRIORITY: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


def resolve_scope(
    scope_a: Tuple[str, str],
    scope_b: Tuple[str, str],
) -> Tuple[str, str]:
    """Return the (scope, confidence) tuple with higher priority.

    Pure function. No side effects. No database access.

    Args:
        scope_a: (dependency_scope, scope_confidence)
        scope_b: (dependency_scope, scope_confidence)

    Returns:
        The tuple with higher SCOPE_PRIORITY. On tie, higher
        CONFIDENCE_PRIORITY wins. Unrecognized scope/confidence
        strings get priority 0 (defense-in-depth).
    """
    pri_a = SCOPE_PRIORITY.get(scope_a[0], 0)
    pri_b = SCOPE_PRIORITY.get(scope_b[0], 0)

    if pri_a > pri_b:
        return scope_a
    if pri_b > pri_a:
        return scope_b

    # Scope priorities tied — break by confidence
    conf_a = CONFIDENCE_PRIORITY.get(scope_a[1], 0)
    conf_b = CONFIDENCE_PRIORITY.get(scope_b[1], 0)

    if conf_a >= conf_b:
        return scope_a
    return scope_b


def aggregate_node_scope(
    edges: List[Tuple[str, str]],
) -> Tuple[str, str]:
    """Aggregate multiple (scope, confidence) tuples into one via resolve_scope.

    Reduces pairwise. Returns ("unknown", "low") for empty input.

    Args:
        edges: List of (dependency_scope, scope_confidence) tuples.

    Returns:
        The aggregated (scope, confidence) with highest priority.
    """
    if not edges:
        return ("unknown", "low")

    result = edges[0]
    for edge in edges[1:]:
        result = resolve_scope(result, edge)
    return result
