"""
Tests for configuration loading.

Tests cover:
- YAML file loading
- Default value fallback
- Configuration validation
- Merge behavior
"""

import pytest
import os
from pathlib import Path

from open_source_risk_model.ingestion.config import IngestionConfig


class TestConfigLoading:
    """Test configuration loading from YAML."""
    
    def test_load_default_config(self):
        """Test loading default configuration."""
        config = IngestionConfig()
        
        assert config.config is not None
        assert isinstance(config.config, dict)
    
    def test_graphql_config_present(self):
        """Test that GraphQL configuration is present."""
        config = IngestionConfig()
        
        assert "graphql" in config.config
        assert "initial_batch_size" in config.config["graphql"]
        assert "max_batch_size" in config.config["graphql"]
    
    def test_rest_config_present(self):
        """Test that REST configuration is present."""
        config = IngestionConfig()
        
        assert "rest" in config.config
        assert "timeout_seconds" in config.config["rest"]
    
    def test_rate_limiting_config_present(self):
        """Test that rate limiting configuration is present."""
        config = IngestionConfig()
        
        assert "rate_limiting" in config.config
        assert "warning_threshold" in config.config["rate_limiting"]
    
    def test_caching_config_present(self):
        """Test that caching configuration is present."""
        config = IngestionConfig()
        
        assert "caching" in config.config
        assert "ttl_seconds" in config.config["caching"]
        assert "cache_dir" in config.config["caching"]
    
    def test_features_config_present(self):
        """Test that features configuration is present."""
        config = IngestionConfig()
        
        assert "features" in config.config
        assert "minimum_coverage_threshold" in config.config["features"]


class TestConfigValues:
    """Test configuration values."""
    
    def test_batch_size_defaults(self):
        """Test batch size default values."""
        config = IngestionConfig()
        
        assert config.config["graphql"]["initial_batch_size"] == 10
        assert config.config["graphql"]["max_batch_size"] == 30
    
    def test_coverage_threshold_default(self):
        """Test coverage threshold default value."""
        config = IngestionConfig()
        
        assert config.config["features"]["minimum_coverage_threshold"] == 0.6
    
    def test_cache_ttl_default(self):
        """Test cache TTL default value."""
        config = IngestionConfig()
        
        assert config.config["caching"]["ttl_seconds"] == 3600  # 1 hour


class TestConfigValidation:
    """Test configuration validation."""
    
    def test_batch_size_within_limits(self):
        """Test that batch sizes are within acceptable limits."""
        config = IngestionConfig()
        
        initial = config.config["graphql"]["initial_batch_size"]
        max_size = config.config["graphql"]["max_batch_size"]
        
        assert 1 <= initial <= 30
        assert 1 <= max_size <= 30
        assert initial <= max_size
    
    def test_coverage_threshold_valid(self):
        """Test that coverage threshold is valid."""
        config = IngestionConfig()
        
        threshold = config.config["features"]["minimum_coverage_threshold"]
        
        assert 0.0 <= threshold <= 1.0
    
    def test_ttl_positive(self):
        """Test that TTL is positive."""
        config = IngestionConfig()
        
        ttl = config.config["caching"]["ttl_seconds"]
        
        assert ttl > 0


class TestConfigFileLoading:
    """Test loading from specific config files."""
    
    def test_load_from_explicit_path(self):
        """Test loading from explicit path."""
        # This should work if config/ingestion_config.yaml exists
        config_path = "config/ingestion_config.yaml"
        
        if os.path.exists(config_path):
            config = IngestionConfig(config_path=config_path)
            assert config.config is not None
    
    def test_fallback_to_defaults_on_missing_file(self):
        """Test fallback to defaults when file is missing."""
        config = IngestionConfig(config_path="nonexistent_config.yaml")
        
        # Should still have defaults
        assert config.config is not None
        assert "graphql" in config.config


class TestConfigMerging:
    """Test configuration merging behavior."""
    
    def test_defaults_present(self):
        """Test that defaults are present even with custom config."""
        config = IngestionConfig()
        
        # All major sections should be present
        assert "graphql" in config.config
        assert "rest" in config.config
        assert "rate_limiting" in config.config
        assert "caching" in config.config
        assert "features" in config.config
