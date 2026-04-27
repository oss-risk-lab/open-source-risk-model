"""
Tests for GraphConfig configuration system.
"""

import os
import pytest
from src.open_source_risk_model.graph.schema import GraphConfig
from src.open_source_risk_model.graph.builder import GraphBuilder


def test_graph_config_defaults():
    """Test that GraphConfig has correct default values."""
    config = GraphConfig()
    
    assert config.include_cves is True
    assert config.max_releases == 10
    assert config.max_maintainers == 5
    assert config.max_risk_factors == 5
    assert config.cve_timeout_seconds == 5
    assert config.cache_ttl_hours == 24


def test_graph_config_custom_values():
    """Test that GraphConfig accepts custom values."""
    config = GraphConfig(
        include_cves=False,
        max_releases=20,
        max_maintainers=10,
        max_risk_factors=8,
        cve_timeout_seconds=10,
        cache_ttl_hours=48
    )
    
    assert config.include_cves is False
    assert config.max_releases == 20
    assert config.max_maintainers == 10
    assert config.max_risk_factors == 8
    assert config.cve_timeout_seconds == 10
    assert config.cache_ttl_hours == 48


def test_graph_config_from_env_defaults(monkeypatch):
    """Test that from_env() uses defaults when env vars not set."""
    # Clear any existing env vars
    for key in ["GRAPH_INCLUDE_CVES", "GRAPH_MAX_RELEASES", "GRAPH_MAX_MAINTAINERS",
                "GRAPH_MAX_RISK_FACTORS", "GRAPH_CVE_TIMEOUT_SECONDS", "GRAPH_CACHE_TTL_HOURS"]:
        monkeypatch.delenv(key, raising=False)
    
    config = GraphConfig.from_env()
    
    assert config.include_cves is True
    assert config.max_releases == 10
    assert config.max_maintainers == 5
    assert config.max_risk_factors == 5
    assert config.cve_timeout_seconds == 5
    assert config.cache_ttl_hours == 24


def test_graph_config_from_env_custom_values(monkeypatch):
    """Test that from_env() reads values from environment variables."""
    monkeypatch.setenv("GRAPH_INCLUDE_CVES", "false")
    monkeypatch.setenv("GRAPH_MAX_RELEASES", "15")
    monkeypatch.setenv("GRAPH_MAX_MAINTAINERS", "8")
    monkeypatch.setenv("GRAPH_MAX_RISK_FACTORS", "7")
    monkeypatch.setenv("GRAPH_CVE_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("GRAPH_CACHE_TTL_HOURS", "48")
    
    config = GraphConfig.from_env()
    
    assert config.include_cves is False
    assert config.max_releases == 15
    assert config.max_maintainers == 8
    assert config.max_risk_factors == 7
    assert config.cve_timeout_seconds == 10
    assert config.cache_ttl_hours == 48


def test_graph_config_from_env_boolean_variations(monkeypatch):
    """Test that from_env() handles various boolean string formats."""
    # Test "true"
    monkeypatch.setenv("GRAPH_INCLUDE_CVES", "true")
    assert GraphConfig.from_env().include_cves is True
    
    # Test "1"
    monkeypatch.setenv("GRAPH_INCLUDE_CVES", "1")
    assert GraphConfig.from_env().include_cves is True
    
    # Test "yes"
    monkeypatch.setenv("GRAPH_INCLUDE_CVES", "yes")
    assert GraphConfig.from_env().include_cves is True
    
    # Test "false"
    monkeypatch.setenv("GRAPH_INCLUDE_CVES", "false")
    assert GraphConfig.from_env().include_cves is False
    
    # Test "0"
    monkeypatch.setenv("GRAPH_INCLUDE_CVES", "0")
    assert GraphConfig.from_env().include_cves is False


def test_graph_config_from_env_invalid_integers(monkeypatch):
    """Test that from_env() uses defaults for invalid integer values."""
    monkeypatch.setenv("GRAPH_MAX_RELEASES", "not_a_number")
    monkeypatch.setenv("GRAPH_MAX_MAINTAINERS", "invalid")
    
    config = GraphConfig.from_env()
    
    # Should fall back to defaults
    assert config.max_releases == 10
    assert config.max_maintainers == 5


def test_graph_builder_uses_config():
    """Test that GraphBuilder respects config settings."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high"
        },
        "features": [
            {"key": "days_since_last_release", "raw_value": 30, "risk_score": 0.2, "weight": 0.1, "category": "activity"},
            {"key": "contributors_last_12mo", "raw_value": 10, "risk_score": 0.1, "weight": 0.1, "category": "community"},
        ],
        "top_drivers": [
            {"key": "days_since_last_release", "contribution": 0.15},
            {"key": "contributors_last_12mo", "contribution": 0.10},
            {"key": "issue_response_time", "contribution": 0.08},
            {"key": "commit_frequency", "contribution": 0.07},
            {"key": "test_coverage", "contribution": 0.06},
            {"key": "documentation_quality", "contribution": 0.05},
        ]
    }
    
    # Test with custom config limiting risk factors to 3
    config = GraphConfig(max_risk_factors=3)
    builder = GraphBuilder("test/repo", score_data, config)
    graph = builder.build()
    
    # Count risk factor nodes
    risk_factor_nodes = [n for n in graph.nodes if n.type.value == "risk_factor"]
    
    # Should have at most 3 risk factor nodes (those with contribution > 0.05)
    assert len(risk_factor_nodes) <= 3


def test_graph_builder_default_config():
    """Test that GraphBuilder uses default config when none provided."""
    score_data = {
        "repo": {"url": "https://github.com/test/repo"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high"
        },
        "features": [],
        "top_drivers": []
    }
    
    builder = GraphBuilder("test/repo", score_data)
    
    # Should have default config
    assert builder.config.include_cves is True
    assert builder.config.max_releases == 10
    assert builder.config.max_maintainers == 5
    assert builder.config.max_risk_factors == 5
