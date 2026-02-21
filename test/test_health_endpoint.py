"""
Tests for the enhanced health check endpoint.
"""

import sys
sys.path.insert(0, 'api')

import pytest
from app import _check_cache_status, _check_github_api_status, _check_osv_api_status


def test_check_cache_status():
    """Test cache status check."""
    status = _check_cache_status()
    
    assert "status" in status
    assert "message" in status
    assert status["status"] in ["ok", "warning", "error"]


def test_check_github_api_status():
    """Test GitHub API status check."""
    status = _check_github_api_status()
    
    assert "status" in status
    assert "message" in status
    assert status["status"] in ["ok", "warning", "error"]


def test_check_osv_api_status():
    """Test OSV API status check."""
    status = _check_osv_api_status()
    
    assert "status" in status
    assert "message" in status
    assert status["status"] in ["ok", "warning", "error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
