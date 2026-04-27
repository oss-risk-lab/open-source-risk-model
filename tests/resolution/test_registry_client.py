"""Tests for RegistryClient ABC enforcement (Req 1.1, 1.2)."""

import pytest

from open_source_risk_model.resolution.registry_client import RegistryClient
from open_source_risk_model.resolution.models import (
    DependencyDeclaration,
    NormalizedPackageMetadata,
)


class TestRegistryClientABC:
    """Verify ABC enforcement on RegistryClient."""

    def test_cannot_instantiate_directly(self):
        """RegistryClient is abstract — direct instantiation must raise TypeError."""
        with pytest.raises(TypeError):
            RegistryClient()

    def test_concrete_subclass_with_both_methods_is_instantiable(self):
        """A subclass implementing both abstract members can be instantiated."""

        class FakeClient(RegistryClient):
            @property
            def ecosystem(self) -> str:
                return "fake"

            def get_package_metadata(self, name, specifier=None):
                return NormalizedPackageMetadata(
                    name=name,
                    version="1.0.0",
                    ecosystem="fake",
                    dependencies=[],
                    source_url="https://fake.registry/",
                    fetched_at="2024-01-01T00:00:00+00:00",
                )

        client = FakeClient()
        assert client.ecosystem == "fake"
        meta = client.get_package_metadata("some-pkg")
        assert meta is not None
        assert meta.name == "some-pkg"

    def test_subclass_missing_ecosystem_raises(self):
        """A subclass that only implements get_package_metadata cannot be instantiated."""

        class PartialClient(RegistryClient):
            def get_package_metadata(self, name, specifier=None):
                return None

        with pytest.raises(TypeError):
            PartialClient()

    def test_subclass_missing_get_package_metadata_raises(self):
        """A subclass that only implements ecosystem cannot be instantiated."""

        class PartialClient(RegistryClient):
            @property
            def ecosystem(self) -> str:
                return "partial"

        with pytest.raises(TypeError):
            PartialClient()
