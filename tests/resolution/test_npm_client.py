"""Tests for NpmClient registry client."""
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from open_source_risk_model.resolution.npm_client import NpmClient
from open_source_risk_model.resolution.models import NormalizedPackageMetadata


@pytest.fixture
def client():
    return NpmClient()


def _mock_response(status_code=200, json_data=None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


SAMPLE_NPM_RESPONSE = {
    "dist-tags": {"latest": "4.18.2"},
    "versions": {
        "4.18.2": {
            "dependencies": {
                "accepts": "~1.3.8",
                "body-parser": "1.20.1",
                "cookie": "0.5.0",
            },
            "devDependencies": {
                "mocha": "10.0.0",
                "supertest": "6.2.4",
            },
            "peerDependencies": {
                "some-peer": "^1.0.0",
            },
            "optionalDependencies": {
                "some-optional": "^2.0.0",
            },
        }
    },
}


class TestEcosystem:
    def test_ecosystem_returns_npm(self, client):
        assert client.ecosystem == "npm"


class TestGetPackageMetadata:
    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_successful_fetch(self, mock_get, client):
        mock_get.return_value = _mock_response(200, SAMPLE_NPM_RESPONSE)

        result = client.get_package_metadata("express")

        assert isinstance(result, NormalizedPackageMetadata)
        assert result.name == "express"
        assert result.version == "4.18.2"
        assert result.ecosystem == "npm"
        assert len(result.dependencies) == 3
        assert result.dependencies[0].name == "accepts"
        assert result.dependencies[0].specifier == "~1.3.8"
        assert result.source_url == "https://registry.npmjs.org/express"

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_only_production_dependencies_included(self, mock_get, client):
        """devDependencies, peerDependencies, optionalDependencies excluded (Req 3.4)."""
        mock_get.return_value = _mock_response(200, SAMPLE_NPM_RESPONSE)

        result = client.get_package_metadata("express")

        dep_names = [d.name for d in result.dependencies]
        assert "accepts" in dep_names
        assert "body-parser" in dep_names
        assert "cookie" in dep_names
        # Excluded dependency types
        assert "mocha" not in dep_names
        assert "supertest" not in dep_names
        assert "some-peer" not in dep_names
        assert "some-optional" not in dep_names

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_scoped_package_url_encoded(self, mock_get, client):
        """Scoped packages like @scope/name are URL-encoded (Req 3.5)."""
        mock_get.return_value = _mock_response(200, {
            "dist-tags": {"latest": "1.0.0"},
            "versions": {"1.0.0": {"dependencies": {}}},
        })

        client.get_package_metadata("@angular/core")

        called_url = mock_get.call_args[0][0]
        assert called_url == "https://registry.npmjs.org/%40angular%2Fcore"

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_http_404_returns_none(self, mock_get, client):
        mock_get.return_value = _mock_response(404)

        result = client.get_package_metadata("nonexistent-package")
        assert result is None

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_http_500_returns_none_and_logs_warning(self, mock_get, client, caplog):
        mock_get.return_value = _mock_response(500)

        with caplog.at_level(logging.WARNING):
            result = client.get_package_metadata("some-package")

        assert result is None
        assert "npm returned 500" in caplog.text

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_network_timeout_returns_none(self, mock_get, client):
        mock_get.side_effect = requests.Timeout("Connection timed out")

        result = client.get_package_metadata("some-package")
        assert result is None

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_missing_dist_tags_latest_returns_none(self, mock_get, client):
        mock_get.return_value = _mock_response(200, {
            "dist-tags": {},
            "versions": {},
        })

        result = client.get_package_metadata("some-package")
        assert result is None

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_dependencies_sorted_by_name(self, mock_get, client):
        mock_get.return_value = _mock_response(200, {
            "dist-tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "dependencies": {
                        "zlib": "^1.0.0",
                        "alpha": "^2.0.0",
                        "middle": "^3.0.0",
                    }
                }
            },
        })

        result = client.get_package_metadata("test-pkg")

        dep_names = [d.name for d in result.dependencies]
        assert dep_names == ["alpha", "middle", "zlib"]

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_specifier_accepted_but_does_not_affect_version(self, mock_get, client):
        """MVP: specifier is accepted but version is always dist-tags.latest."""
        mock_get.return_value = _mock_response(200, SAMPLE_NPM_RESPONSE)

        result_no_spec = client.get_package_metadata("express")
        result_with_spec = client.get_package_metadata("express", specifier="^4.0.0")

        assert result_no_spec.version == result_with_spec.version == "4.18.2"

    @patch("open_source_risk_model.resolution.npm_client.requests.get")
    def test_fetched_at_is_valid_iso8601(self, mock_get, client):
        mock_get.return_value = _mock_response(200, SAMPLE_NPM_RESPONSE)

        result = client.get_package_metadata("express")

        parsed = datetime.fromisoformat(result.fetched_at)
        assert parsed is not None
