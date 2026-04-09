"""Tests for LLM provider factory functions."""

import os
import pytest

from open_source_risk_model.llm import create_provider, create_provider_from_env
from open_source_risk_model.llm.providers import OpenAIProvider
from open_source_risk_model.llm.exceptions import ConfigurationError


class TestCreateProvider:
    """Tests for create_provider() factory function."""
    
    def test_create_provider_openai(self):
        """Test creating OpenAI provider with valid config."""
        config = {
            "provider_type": "openai",
            "api_key": "test-api-key",
            "timeout": 60
        }
        
        provider = create_provider(config)
        
        assert provider is not None
        assert isinstance(provider, OpenAIProvider)
        assert provider.name == "openai"
        assert provider.api_key == "test-api-key"
        assert provider.timeout == 60
        assert len(provider.supported_models) > 0
    
    def test_create_provider_openai_with_optional_params(self):
        """Test creating OpenAI provider with all optional parameters."""
        config = {
            "provider_type": "openai",
            "api_key": "test-api-key",
            "base_url": "https://custom.api.com",
            "organization": "org-123",
            "timeout": 120
        }
        
        provider = create_provider(config)
        
        assert provider is not None
        assert isinstance(provider, OpenAIProvider)
        assert provider.base_url == "https://custom.api.com"
        assert provider.organization == "org-123"
        assert provider.timeout == 120
    
    def test_create_provider_openai_default_timeout(self):
        """Test that default timeout is applied when not specified."""
        config = {
            "provider_type": "openai",
            "api_key": "test-api-key"
        }
        
        provider = create_provider(config)
        
        assert provider.timeout == 30  # Default timeout
    
    def test_create_provider_missing_provider_type(self):
        """Test error when provider_type is missing."""
        config = {
            "api_key": "test-api-key"
        }
        
        with pytest.raises(ConfigurationError) as exc_info:
            create_provider(config)
        
        assert "provider_type" in str(exc_info.value)
    
    def test_create_provider_unknown_type(self):
        """Test error when provider_type is unknown."""
        config = {
            "provider_type": "unknown_provider",
            "api_key": "test-api-key"
        }
        
        with pytest.raises(ConfigurationError) as exc_info:
            create_provider(config)
        
        assert "Unknown provider type" in str(exc_info.value)
        assert "unknown_provider" in str(exc_info.value)
    
    def test_create_provider_openai_missing_api_key(self):
        """Test error when OpenAI API key is missing."""
        config = {
            "provider_type": "openai"
        }
        
        with pytest.raises(ConfigurationError) as exc_info:
            create_provider(config)
        
        assert "api_key" in str(exc_info.value).lower()
    
    def test_create_provider_openai_empty_api_key(self):
        """Test error when OpenAI API key is empty string."""
        config = {
            "provider_type": "openai",
            "api_key": ""
        }
        
        with pytest.raises(ConfigurationError) as exc_info:
            create_provider(config)
        
        assert "api_key" in str(exc_info.value).lower()


class TestCreateProviderFromEnv:
    """Tests for create_provider_from_env() factory function."""
    
    def test_create_provider_from_env_openai(self, monkeypatch):
        """Test creating OpenAI provider from environment variables."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        
        provider = create_provider_from_env()
        
        assert provider is not None
        assert isinstance(provider, OpenAIProvider)
        assert provider.name == "openai"
        assert provider.api_key == "test-env-key"
    
    def test_create_provider_from_env_default_provider(self, monkeypatch):
        """Test that 'openai' is the default provider when LLM_PROVIDER not set."""
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        
        provider = create_provider_from_env()
        
        assert provider is not None
        assert provider.name == "openai"
    
    def test_create_provider_from_env_with_base_url(self, monkeypatch):
        """Test creating provider with custom base URL from environment."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api.com")
        
        provider = create_provider_from_env()
        
        assert provider.base_url == "https://custom.api.com"
    
    def test_create_provider_from_env_with_organization(self, monkeypatch):
        """Test creating provider with organization from environment."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        monkeypatch.setenv("OPENAI_ORGANIZATION", "org-456")
        
        provider = create_provider_from_env()
        
        assert provider.organization == "org-456"
    
    def test_create_provider_from_env_all_options(self, monkeypatch):
        """Test creating provider with all environment variables set."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api.com")
        monkeypatch.setenv("OPENAI_ORGANIZATION", "org-789")
        
        provider = create_provider_from_env()
        
        assert provider.api_key == "test-env-key"
        assert provider.base_url == "https://custom.api.com"
        assert provider.organization == "org-789"
    
    def test_create_provider_from_env_missing_api_key(self, monkeypatch):
        """Test error when OPENAI_API_KEY environment variable is missing."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        with pytest.raises(ConfigurationError) as exc_info:
            create_provider_from_env()
        
        assert "OPENAI_API_KEY" in str(exc_info.value)
        assert "required" in str(exc_info.value).lower()
    
    def test_create_provider_from_env_unknown_provider(self, monkeypatch):
        """Test error when LLM_PROVIDER is set to unknown type."""
        monkeypatch.setenv("LLM_PROVIDER", "unknown_provider")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        
        with pytest.raises(ConfigurationError) as exc_info:
            create_provider_from_env()
        
        assert "Unknown provider type" in str(exc_info.value)
        assert "unknown_provider" in str(exc_info.value)
    
    def test_create_provider_from_env_no_base_url(self, monkeypatch):
        """Test that base_url is None when not set in environment."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        
        provider = create_provider_from_env()
        
        assert provider.base_url is None
    
    def test_create_provider_from_env_no_organization(self, monkeypatch):
        """Test that organization is None when not set in environment."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-env-key")
        monkeypatch.delenv("OPENAI_ORGANIZATION", raising=False)
        
        provider = create_provider_from_env()
        
        assert provider.organization is None


class TestFactoryIntegration:
    """Integration tests for factory functions."""
    
    def test_factory_creates_functional_provider(self):
        """Test that factory-created provider is functional."""
        config = {
            "provider_type": "openai",
            "api_key": "test-api-key"
        }
        
        provider = create_provider(config)
        
        # Verify provider has all required methods
        assert hasattr(provider, "complete")
        assert hasattr(provider, "stream")
        assert hasattr(provider, "validate_config")
        assert hasattr(provider, "name")
        assert hasattr(provider, "supported_models")
        
        # Verify provider properties work
        assert provider.name == "openai"
        assert isinstance(provider.supported_models, list)
        assert len(provider.supported_models) > 0
    
    def test_both_factories_create_equivalent_providers(self, monkeypatch):
        """Test that both factory methods create equivalent providers."""
        # Create provider from config dict
        config = {
            "provider_type": "openai",
            "api_key": "test-key-123",
            "base_url": "https://api.example.com",
            "organization": "org-abc"
        }
        provider1 = create_provider(config)
        
        # Create provider from environment
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com")
        monkeypatch.setenv("OPENAI_ORGANIZATION", "org-abc")
        provider2 = create_provider_from_env()
        
        # Verify both providers have same configuration
        assert provider1.name == provider2.name
        assert provider1.api_key == provider2.api_key
        assert provider1.base_url == provider2.base_url
        assert provider1.organization == provider2.organization
        assert provider1.supported_models == provider2.supported_models
