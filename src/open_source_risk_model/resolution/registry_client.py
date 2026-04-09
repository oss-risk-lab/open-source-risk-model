from abc import ABC, abstractmethod

from .models import NormalizedPackageMetadata


class RegistryClient(ABC):
    """Abstract interface for ecosystem registry clients."""

    @property
    @abstractmethod
    def ecosystem(self) -> str:
        """Return ecosystem identifier (e.g. 'pypi', 'npm')."""

    @abstractmethod
    def get_package_metadata(
        self, name: str, specifier: str | None = None
    ) -> NormalizedPackageMetadata | None:
        """Fetch package metadata from registry.
        Returns None if package not found or request failed.
        The specifier parameter is accepted for interface completeness
        but NOT used for version selection in MVP — always fetches
        latest. Stored on the edge as declared_specifier for provenance."""
