"""Exception classes for the dependency tree module."""


class RepositoryNotFoundError(Exception):
    """Repository cannot be located in database or via live ingestion. → 404"""


class TreeConstructionTimeoutError(Exception):
    """Tree construction exceeded the 10-second timeout. → 503"""


class AllDependenciesFailedError(Exception):
    """Every dependency failed to resolve; cannot build even a partial tree. → 503"""


class DependencyResolutionError(Exception):
    """A single dependency failed to resolve.

    Internal only — converted to error node, never propagated to API.
    """
