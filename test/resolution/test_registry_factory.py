"""Tests for registry_factory — Req 1.3, 1.4."""

from src.open_source_risk_model.resolution.registry_factory import get_registry_client
from src.open_source_risk_model.resolution.pypi_client import PyPIClient
from src.open_source_risk_model.resolution.npm_client import NpmClient


class TestGetRegistryClient:
    def test_pypi_returns_pypi_client(self):
        client = get_registry_client("pypi")
        assert isinstance(client, PyPIClient)

    def test_npm_returns_npm_client(self):
        client = get_registry_client("npm")
        assert isinstance(client, NpmClient)

    def test_rubygems_returns_none(self):
        assert get_registry_client("rubygems") is None

    def test_unknown_returns_none(self):
        assert get_registry_client("unknown") is None

    def test_pypi_client_ecosystem_property(self):
        client = get_registry_client("pypi")
        assert client.ecosystem == "pypi"

    def test_npm_client_ecosystem_property(self):
        client = get_registry_client("npm")
        assert client.ecosystem == "npm"
