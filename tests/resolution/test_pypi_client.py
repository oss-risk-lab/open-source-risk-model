"""Tests for PyPIClient registry client."""
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from open_source_risk_model.resolution.pypi_client import PyPIClient, _parse_pep508_entry
from open_source_risk_model.resolution.models import NormalizedPackageMetadata


@pytest.fixture
def client():
    return PyPIClient()


def _mock_response(status_code=200, json_data=None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


SAMPLE_PYPI_RESPONSE = {
    "info": {
        "version": "2.31.0",
        "requires_dist": [
            "charset-normalizer (<4,>=2)",
            "idna (<4,>=2.5)",
            "urllib3 (<3,>=1.21.1)",
            "certifi (>=2017.4.17)",
        ],
    }
}


class TestEcosystem:
    def test_ecosystem_returns_pypi(self, client):
        assert client.ecosystem == "pypi"


class TestGetPackageMetadata:
    @patch("open_source_risk_model.resolution.pypi_client.requests.get")
    def test_successful_fetch(self, mock_get, client):
        mock_get.return_value = _mock_response(200, SAMPLE_PYPI_RESPONSE)

        result = client.get_package_metadata("requests")

        assert isinstance(result, NormalizedPackageMetadata)
        assert result.name == "requests"
        assert result.version == "2.31.0"
        assert result.ecosystem == "pypi"
        assert len(result.dependencies) == 4
        assert result.dependencies[0].name == "charset-normalizer"
        assert result.dependencies[0].specifier == "<4,>=2"

    @patch("open_source_risk_model.resolution.pypi_client.requests.get")
    def test_http_404_returns_none(self, mock_get, client):
        mock_get.return_value = _mock_response(404)

        result = client.get_package_metadata("nonexistent-package")
        assert result is None

    @patch("open_source_risk_model.resolution.pypi_client.requests.get")
    def test_http_500_returns_none_and_logs_warning(self, mock_get, client, caplog):
        mock_get.return_value = _mock_response(500)

        with caplog.at_level(logging.WARNING):
            result = client.get_package_metadata("some-package")

        assert result is None
        assert "PyPI returned 500" in caplog.text

    @patch("open_source_risk_model.resolution.pypi_client.requests.get")
    def test_network_timeout_returns_none_and_logs_warning(self, mock_get, client, caplog):
        mock_get.side_effect = requests.Timeout("Connection timed out")

        with caplog.at_level(logging.WARNING):
            result = client.get_package_metadata("some-package")

        assert result is None
        assert "PyPI request failed" in caplog.text

    @patch("open_source_risk_model.resolution.pypi_client.requests.get")
    def test_specifier_accepted_but_does_not_affect_version(self, mock_get, client):
        """MVP: specifier is accepted but version is always latest."""
        mock_get.return_value = _mock_response(200, SAMPLE_PYPI_RESPONSE)

        result_no_spec = client.get_package_metadata("requests")
        result_with_spec = client.get_package_metadata("requests", specifier=">=2.0")

        assert result_no_spec.version == result_with_spec.version == "2.31.0"

    @patch("open_source_risk_model.resolution.pypi_client.requests.get")
    def test_source_url_is_pypi_json_api_url(self, mock_get, client):
        mock_get.return_value = _mock_response(200, SAMPLE_PYPI_RESPONSE)

        result = client.get_package_metadata("requests")
        assert result.source_url == "https://pypi.org/pypi/requests/json"

    @patch("open_source_risk_model.resolution.pypi_client.requests.get")
    def test_fetched_at_is_valid_iso8601(self, mock_get, client):
        mock_get.return_value = _mock_response(200, SAMPLE_PYPI_RESPONSE)

        result = client.get_package_metadata("requests")
        # Should parse without error
        parsed = datetime.fromisoformat(result.fetched_at)
        assert parsed is not None


class TestParseRequiresDist:
    def test_excludes_extra_marker_entries(self, client):
        requires_dist = [
            "idna (<4,>=2.5)",
            'PySocks (!=1.5.7,>=1.5.6) ; extra == "socks"',
            'chardet (<6,>=3.0.2) ; extra == "security"',
        ]
        deps = client._parse_requires_dist(requires_dist)
        names = [d.name for d in deps]
        assert "idna" in names
        assert "PySocks" not in names
        assert "chardet" not in names

    def test_excludes_extra_marker_without_spaces(self, client):
        requires_dist = [
            "idna (<4,>=2.5)",
            'PySocks (!=1.5.7,>=1.5.6) ; extra=="socks"',
        ]
        deps = client._parse_requires_dist(requires_dist)
        names = [d.name for d in deps]
        assert "PySocks" not in names

    def test_includes_environment_marker_entries(self, client):
        requires_dist = [
            "idna (<4,>=2.5)",
            'win32-setctime (>=1.0.0) ; sys_platform == "win32"',
            'colorama (>=0.3.4) ; python_version >= "3.0"',
        ]
        deps = client._parse_requires_dist(requires_dist)
        names = [d.name for d in deps]
        assert "idna" in names
        assert "win32-setctime" in names
        assert "colorama" in names

    def test_empty_list_returns_empty(self, client):
        deps = client._parse_requires_dist([])
        assert deps == []

    def test_extracts_name_and_specifier_correctly(self, client):
        requires_dist = [
            "urllib3 (<3,>=1.21.1)",
            "certifi (>=2017.4.17)",
            "charset-normalizer (<4,>=2)",
        ]
        deps = client._parse_requires_dist(requires_dist)
        assert deps[0].name == "urllib3"
        assert deps[0].specifier == "<3,>=1.21.1"
        assert deps[1].name == "certifi"
        assert deps[1].specifier == ">=2017.4.17"
        assert deps[2].name == "charset-normalizer"
        assert deps[2].specifier == "<4,>=2"


class TestParsePep508Entry:
    def test_simple_name(self):
        name, spec = _parse_pep508_entry("requests")
        assert name == "requests"
        assert spec is None

    def test_name_with_specifier(self):
        name, spec = _parse_pep508_entry("requests>=2.0")
        assert name == "requests"
        assert spec == ">=2.0"

    def test_name_with_parenthesized_specifier(self):
        name, spec = _parse_pep508_entry("urllib3 (<3,>=1.21.1)")
        assert name == "urllib3"
        assert spec == "<3,>=1.21.1"

    def test_entry_with_environment_marker(self):
        name, spec = _parse_pep508_entry('colorama (>=0.3.4) ; python_version >= "3.0"')
        assert name == "colorama"
        assert spec == ">=0.3.4"
