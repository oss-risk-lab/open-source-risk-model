"""
Unit tests for CVE fetcher.

Tests CVE fetching from OSV.dev API with mocking, timeout handling,
cache behavior, and version range parsing.
"""

import json
import pytest
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import requests

from src.open_source_risk_model.graph.cve_fetcher import CVEFetcher, CVERecord


# Test Fixtures

@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / "cve_cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def cve_fetcher(temp_cache_dir):
    """Create a CVEFetcher instance with temporary cache."""
    return CVEFetcher(cache_dir=temp_cache_dir, cache_ttl_hours=24, timeout_seconds=5)


@pytest.fixture
def mock_osv_response():
    """Mock OSV.dev API response with sample vulnerabilities."""
    return {
        "vulns": [
            {
                "id": "CVE-2024-1234",
                "summary": "Buffer overflow vulnerability in numpy.array",
                "severity": [
                    {
                        "type": "CVSS_V3",
                        "score": "7.5 HIGH"
                    }
                ],
                "published": "2024-01-15T10:00:00Z",
                "affected": [
                    {
                        "package": {"name": "numpy", "ecosystem": "PyPI"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [
                                    {"introduced": "0"},
                                    {"fixed": "1.22.0"}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "GHSA-xxxx-yyyy-zzzz",
                "summary": "Denial of service vulnerability",
                "severity": [
                    {
                        "type": "CVSS_V3",
                        "score": "5.3 MEDIUM"
                    }
                ],
                "published": "2023-11-20T14:30:00Z",
                "affected": [
                    {
                        "package": {"name": "numpy", "ecosystem": "PyPI"},
                        "ranges": [
                            {
                                "type": "SEMVER",
                                "events": [
                                    {"introduced": "1.20.0"},
                                    {"fixed": "1.21.5"}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_empty_osv_response():
    """Mock OSV.dev API response with no vulnerabilities."""
    return {"vulns": []}


# Unit Tests - Basic Functionality

def test_cve_fetcher_initialization(temp_cache_dir):
    """Test CVEFetcher initialization with custom parameters."""
    fetcher = CVEFetcher(
        cache_dir=temp_cache_dir,
        cache_ttl_hours=12,
        timeout_seconds=10
    )
    
    assert fetcher.cache_dir == temp_cache_dir
    assert fetcher.cache_ttl == timedelta(hours=12)
    assert fetcher.timeout == 10
    assert fetcher.session is not None


def test_cve_fetcher_default_initialization():
    """Test CVEFetcher initialization with default parameters."""
    fetcher = CVEFetcher()
    
    assert fetcher.cache_dir == Path("data/cve")
    assert fetcher.cache_ttl == timedelta(hours=24)
    assert fetcher.timeout == 5


def test_fetch_cves_with_mock_response(cve_fetcher, mock_osv_response):
    """Test fetching CVEs with a mocked OSV.dev response."""
    # Mock the requests.post call
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_osv_response
        mock_post.return_value = mock_response
        
        # Fetch CVEs
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Verify API was called correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.osv.dev/v1/query"
        assert call_args[1]["json"]["package"]["name"] == "numpy"
        assert call_args[1]["json"]["package"]["ecosystem"] == "PyPI"
        assert call_args[1]["timeout"] == 5
        
        # Verify CVE records were parsed correctly
        assert len(cves) == 2
        
        # Check first CVE
        assert cves[0].id == "CVE-2024-1234"
        assert cves[0].severity == "HIGH"
        assert cves[0].cvss_score == 7.5
        assert "Buffer overflow" in cves[0].summary
        assert cves[0].published == "2024-01-15T10:00:00Z"
        assert cves[0].fixed_in == "1.22.0"
        assert cves[0].source == "cve"
        
        # Check second CVE
        assert cves[1].id == "GHSA-xxxx-yyyy-zzzz"
        assert cves[1].severity == "MEDIUM"
        assert cves[1].cvss_score == 5.3
        assert "Denial of service" in cves[1].summary
        assert cves[1].source == "github_advisory"


def test_fetch_cves_with_no_vulnerabilities(cve_fetcher, mock_empty_osv_response):
    """Test fetching CVEs when no vulnerabilities exist."""
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_empty_osv_response
        mock_post.return_value = mock_response
        
        cves = cve_fetcher.fetch_cves("safe-package", "PyPI")
        
        assert len(cves) == 0
        mock_post.assert_called_once()


# Unit Tests - Timeout Handling

def test_fetch_cves_timeout_with_retry(cve_fetcher, mock_osv_response):
    """Test timeout handling with exponential backoff retry."""
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        # First two calls timeout, third succeeds
        mock_post.side_effect = [
            requests.Timeout("Connection timeout"),
            requests.Timeout("Connection timeout"),
            Mock(status_code=200, json=lambda: mock_osv_response)
        ]
        
        # Should succeed after retries
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have retried 3 times
        assert mock_post.call_count == 3
        assert len(cves) == 2


def test_fetch_cves_timeout_exhausted(cve_fetcher):
    """Test timeout handling when all retries are exhausted."""
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        # All calls timeout
        mock_post.side_effect = requests.Timeout("Connection timeout")
        
        # Should raise Timeout after max retries
        with pytest.raises(requests.Timeout):
            cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have tried 3 times (max_retries)
        assert mock_post.call_count == 3


def test_fetch_cves_timeout_duration(cve_fetcher):
    """Test that timeout parameter is passed to requests."""
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vulns": []}
        mock_post.return_value = mock_response
        
        cve_fetcher.fetch_cves("test-package", "PyPI")
        
        # Verify timeout was passed
        call_args = mock_post.call_args
        assert call_args[1]["timeout"] == 5


# Unit Tests - Rate Limiting and Exponential Backoff

def test_fetch_cves_rate_limiting_with_retry(cve_fetcher, mock_osv_response):
    """Test rate limiting (429) handling with exponential backoff."""
    with patch.object(cve_fetcher.session, 'post') as mock_post, \
         patch('time.sleep') as mock_sleep:
        
        # First call returns 429, second succeeds
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_response.raise_for_status.side_effect = requests.HTTPError("429 Too Many Requests")
        
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = mock_osv_response
        
        mock_post.side_effect = [rate_limit_response, success_response]
        
        # Should succeed after retry
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have retried
        assert mock_post.call_count == 2
        assert len(cves) == 2
        
        # Should have slept with exponential backoff (1 second for first retry)
        mock_sleep.assert_called_once_with(1.0)


def test_fetch_cves_rate_limiting_exhausted(cve_fetcher):
    """Test rate limiting when all retries are exhausted."""
    with patch.object(cve_fetcher.session, 'post') as mock_post, \
         patch('time.sleep') as mock_sleep:
        
        # All calls return 429
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_response.raise_for_status.side_effect = requests.HTTPError("429 Too Many Requests")
        mock_post.return_value = rate_limit_response
        
        # Should raise HTTPError after max retries
        with pytest.raises(requests.HTTPError):
            cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have tried 3 times
        assert mock_post.call_count == 3
        
        # Should have slept with exponential backoff: 1s, 2s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)  # First retry
        mock_sleep.assert_any_call(2.0)  # Second retry


def test_fetch_cves_exponential_backoff_timing(cve_fetcher, mock_osv_response):
    """Test exponential backoff timing progression."""
    with patch.object(cve_fetcher.session, 'post') as mock_post, \
         patch('time.sleep') as mock_sleep:
        
        # First two calls fail, third succeeds
        mock_post.side_effect = [
            requests.RequestException("Network error"),
            requests.RequestException("Network error"),
            Mock(status_code=200, json=lambda: mock_osv_response)
        ]
        
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have slept twice with exponential backoff
        assert mock_sleep.call_count == 2
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls[0] == 1.0  # First retry: 1 * 2^0
        assert calls[1] == 2.0  # Second retry: 1 * 2^1


# Unit Tests - Cache Behavior

def test_cve_caching_stores_data(cve_fetcher, mock_osv_response):
    """Test that CVE data is cached after fetching."""
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_osv_response
        mock_post.return_value = mock_response
        
        # Fetch CVEs
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Check cache file was created
        cache_path = cve_fetcher._cache_path("PyPI", "numpy")
        assert cache_path.exists()
        
        # Verify cache contents
        cached_data = json.loads(cache_path.read_text())
        assert "fetched_at" in cached_data
        assert "expires_at" in cached_data
        assert cached_data["ecosystem"] == "PyPI"
        assert cached_data["package"] == "numpy"
        assert len(cached_data["cves"]) == 2


def test_cve_caching_retrieves_fresh_data(cve_fetcher, mock_osv_response):
    """Test that fresh cached data is retrieved without API call."""
    # First, populate the cache
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_osv_response
        mock_post.return_value = mock_response
        
        cves1 = cve_fetcher.fetch_cves("numpy", "PyPI")
        assert mock_post.call_count == 1
    
    # Second fetch should use cache
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        cves2 = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should not have called API
        mock_post.assert_not_called()
        
        # Should return same data
        assert len(cves2) == len(cves1)
        assert cves2[0].id == cves1[0].id


def test_cve_caching_expired_data(cve_fetcher, mock_osv_response):
    """Test that expired cached data triggers a new API call."""
    # Create expired cache manually
    cache_path = cve_fetcher._cache_path("PyPI", "numpy")
    expired_time = datetime.now(timezone.utc) - timedelta(hours=25)  # Older than 24h TTL
    
    expired_cache = {
        "fetched_at": expired_time.isoformat(),
        "expires_at": (expired_time + timedelta(hours=24)).isoformat(),
        "ecosystem": "PyPI",
        "package": "numpy",
        "cves": []
    }
    cache_path.write_text(json.dumps(expired_cache))
    
    # Fetch should ignore expired cache and call API
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_osv_response
        mock_post.return_value = mock_response
        
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have called API
        mock_post.assert_called_once()
        assert len(cves) == 2


def test_cve_caching_force_refresh(cve_fetcher, mock_osv_response):
    """Test force_refresh parameter bypasses cache."""
    # First, populate the cache
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_osv_response
        mock_post.return_value = mock_response
        
        cves1 = cve_fetcher.fetch_cves("numpy", "PyPI")
        assert mock_post.call_count == 1
    
    # Force refresh should bypass cache
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_osv_response
        mock_post.return_value = mock_response
        
        cves2 = cve_fetcher.fetch_cves("numpy", "PyPI", force_refresh=True)
        
        # Should have called API despite cache
        mock_post.assert_called_once()


def test_cve_caching_invalid_cache_file(cve_fetcher, mock_osv_response):
    """Test handling of corrupted cache files."""
    # Create invalid cache file
    cache_path = cve_fetcher._cache_path("PyPI", "numpy")
    cache_path.write_text("invalid json content {{{")
    
    # Should ignore invalid cache and fetch from API
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_osv_response
        mock_post.return_value = mock_response
        
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have called API
        mock_post.assert_called_once()
        assert len(cves) == 2


# Unit Tests - Version Range Parsing

def test_map_cves_to_releases_basic(cve_fetcher):
    """Test basic CVE-to-release mapping."""
    cves = [
        CVERecord(
            id="CVE-2024-1234",
            severity="HIGH",
            cvss_score=7.5,
            summary="Test vulnerability",
            published="2024-01-15T10:00:00Z",
            fixed_in="1.22.0",
            affected_ranges=[
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "0"},
                        {"fixed": "1.22.0"}
                    ]
                }
            ],
            source="osv"
        )
    ]
    
    releases = ["v1.20.0", "v1.21.0", "v1.22.0", "v1.23.0"]
    
    mapping = cve_fetcher.map_cves_to_releases(cves, releases)
    
    # v1.20.0 and v1.21.0 should be affected
    assert len(mapping["v1.20.0"]) == 1
    assert len(mapping["v1.21.0"]) == 1
    
    # v1.22.0 and v1.23.0 should not be affected (fixed in 1.22.0)
    assert len(mapping["v1.22.0"]) == 0
    assert len(mapping["v1.23.0"]) == 0


def test_map_cves_to_releases_multiple_cves(cve_fetcher):
    """Test mapping multiple CVEs to releases."""
    cves = [
        CVERecord(
            id="CVE-2024-1234",
            severity="HIGH",
            cvss_score=7.5,
            summary="First vulnerability",
            published="2024-01-15T10:00:00Z",
            fixed_in="1.22.0",
            affected_ranges=[
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "0"},
                        {"fixed": "1.22.0"}
                    ]
                }
            ],
            source="osv"
        ),
        CVERecord(
            id="CVE-2024-5678",
            severity="MEDIUM",
            cvss_score=5.3,
            summary="Second vulnerability",
            published="2024-02-20T10:00:00Z",
            fixed_in="1.23.0",
            affected_ranges=[
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "1.21.0"},
                        {"fixed": "1.23.0"}
                    ]
                }
            ],
            source="osv"
        )
    ]
    
    releases = ["v1.20.0", "v1.21.0", "v1.22.0", "v1.23.0"]
    
    mapping = cve_fetcher.map_cves_to_releases(cves, releases)
    
    # v1.20.0: affected by first CVE only
    assert len(mapping["v1.20.0"]) == 1
    assert mapping["v1.20.0"][0].id == "CVE-2024-1234"
    
    # v1.21.0: affected by both CVEs
    assert len(mapping["v1.21.0"]) == 2
    
    # v1.22.0: affected by second CVE only
    assert len(mapping["v1.22.0"]) == 1
    assert mapping["v1.22.0"][0].id == "CVE-2024-5678"
    
    # v1.23.0: not affected by any
    assert len(mapping["v1.23.0"]) == 0


def test_map_cves_to_releases_no_fixed_version(cve_fetcher):
    """Test mapping CVEs with no fixed version (all versions affected)."""
    cves = [
        CVERecord(
            id="CVE-2024-9999",
            severity="CRITICAL",
            cvss_score=9.8,
            summary="Unfixed vulnerability",
            published="2024-03-01T10:00:00Z",
            fixed_in=None,
            affected_ranges=[
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "0"}
                    ]
                }
            ],
            source="osv"
        )
    ]
    
    releases = ["v1.20.0", "v1.21.0", "v1.22.0"]
    
    mapping = cve_fetcher.map_cves_to_releases(cves, releases)
    
    # All releases should be affected
    assert len(mapping["v1.20.0"]) == 1
    assert len(mapping["v1.21.0"]) == 1
    assert len(mapping["v1.22.0"]) == 1


def test_map_cves_to_releases_empty_inputs(cve_fetcher):
    """Test mapping with empty inputs."""
    # Empty CVEs
    mapping1 = cve_fetcher.map_cves_to_releases([], ["v1.0.0", "v2.0.0"])
    assert len(mapping1["v1.0.0"]) == 0
    assert len(mapping1["v2.0.0"]) == 0
    
    # Empty releases
    cves = [
        CVERecord(
            id="CVE-2024-1234",
            severity="HIGH",
            cvss_score=7.5,
            summary="Test",
            published="2024-01-15T10:00:00Z",
            fixed_in="1.22.0",
            affected_ranges=[],
            source="osv"
        )
    ]
    mapping2 = cve_fetcher.map_cves_to_releases(cves, [])
    assert len(mapping2) == 0


def test_version_comparison_simple(cve_fetcher):
    """Test simple version comparison logic."""
    # Test basic comparisons
    assert cve_fetcher._simple_version_compare("1.20.0", "1.22.0") < 0
    assert cve_fetcher._simple_version_compare("1.22.0", "1.20.0") > 0
    assert cve_fetcher._simple_version_compare("1.22.0", "1.22.0") == 0
    
    # Test with different lengths
    assert cve_fetcher._simple_version_compare("1.20", "1.20.0") == 0
    assert cve_fetcher._simple_version_compare("1.20.1", "1.20") > 0


def test_parse_vulnerability_with_minimal_data(cve_fetcher):
    """Test parsing vulnerability with minimal required data."""
    vuln = {
        "id": "CVE-2024-0001",
        "summary": "Minimal vulnerability",
        "published": "2024-01-01T00:00:00Z"
    }
    
    cve_record = cve_fetcher._parse_vulnerability(vuln)
    
    assert cve_record is not None
    assert cve_record.id == "CVE-2024-0001"
    assert cve_record.summary == "Minimal vulnerability"
    assert cve_record.severity == "UNKNOWN"
    assert cve_record.cvss_score is None
    assert cve_record.fixed_in is None


def test_parse_vulnerability_with_missing_id(cve_fetcher):
    """Test parsing vulnerability with missing ID returns None."""
    vuln = {
        "summary": "Vulnerability without ID",
        "published": "2024-01-01T00:00:00Z"
    }
    
    cve_record = cve_fetcher._parse_vulnerability(vuln)
    
    assert cve_record is None


def test_parse_vulnerability_determines_source(cve_fetcher):
    """Test that source is determined correctly from vulnerability ID."""
    # CVE source
    vuln_cve = {"id": "CVE-2024-1234", "summary": "Test", "published": "2024-01-01T00:00:00Z"}
    cve_record = cve_fetcher._parse_vulnerability(vuln_cve)
    assert cve_record.source == "cve"
    
    # GitHub Advisory source
    vuln_ghsa = {"id": "GHSA-xxxx-yyyy-zzzz", "summary": "Test", "published": "2024-01-01T00:00:00Z"}
    ghsa_record = cve_fetcher._parse_vulnerability(vuln_ghsa)
    assert ghsa_record.source == "github_advisory"
    
    # OSV source (default)
    vuln_osv = {"id": "OSV-2024-1234", "summary": "Test", "published": "2024-01-01T00:00:00Z"}
    osv_record = cve_fetcher._parse_vulnerability(vuln_osv)
    assert osv_record.source == "osv"


def test_parse_vulnerability_truncates_long_summary(cve_fetcher):
    """Test that very long summaries are truncated."""
    long_summary = "A" * 1000  # 1000 character summary
    vuln = {
        "id": "CVE-2024-1234",
        "summary": long_summary,
        "published": "2024-01-01T00:00:00Z"
    }
    
    cve_record = cve_fetcher._parse_vulnerability(vuln)
    
    assert len(cve_record.summary) == 500  # Truncated to 500 chars


def test_cache_path_sanitization(cve_fetcher):
    """Test that cache paths are sanitized properly."""
    # Test with special characters
    cache_path = cve_fetcher._cache_path("PyPI", "my/package")
    assert "/" not in cache_path.name
    assert cache_path.name == "PyPI__my_package.json"


def test_fetch_cves_network_error_with_retry(cve_fetcher, mock_osv_response):
    """Test network error handling with retry."""
    with patch.object(cve_fetcher.session, 'post') as mock_post, \
         patch('time.sleep') as mock_sleep:
        
        # First call fails, second succeeds
        mock_post.side_effect = [
            requests.RequestException("Network error"),
            Mock(status_code=200, json=lambda: mock_osv_response)
        ]
        
        cves = cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have retried
        assert mock_post.call_count == 2
        assert len(cves) == 2
        
        # Should have slept once
        mock_sleep.assert_called_once_with(1.0)


def test_fetch_cves_http_error(cve_fetcher):
    """Test handling of HTTP errors (non-429)."""
    with patch.object(cve_fetcher.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Internal Server Error")
        mock_post.return_value = mock_response
        
        # Should raise HTTPError after retries
        with pytest.raises(requests.HTTPError):
            cve_fetcher.fetch_cves("numpy", "PyPI")
        
        # Should have retried
        assert mock_post.call_count == 3
