"""Integration tests for LLM Provider Abstraction Layer.

These tests use real API calls and are skipped unless API keys are present.
Run with: pytest -m integration
"""

import os
import pytest
from pathlib import Path
from open_source_risk_model.llm import (
    create_provider_from_env,
    LLMClient,
    PromptManager
)
from open_source_risk_model.query.intent_classifier import IntentClassifier


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
def test_intent_classification_with_real_openai():
    """Integration test with real OpenAI API."""
    # Create real provider
    provider = create_provider_from_env()
    
    # Create client
    prompts_dir = Path("src/open_source_risk_model/llm/prompts")
    prompt_manager = PromptManager(prompts_dir)
    client = LLMClient(provider, prompt_manager)
    
    # Create classifier
    classifier = IntentClassifier(client)
    
    # Test classification
    result = classifier.classify("What are the dependencies of django/django?")
    
    # Verify result
    assert result.intent == "list_dependencies"
    assert result.confidence >= 0.7
    assert "repo_full_name" in result.parameters
    assert result.parameters["repo_full_name"] == "django/django"


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
def test_provider_validation():
    """Test that provider validates configuration."""
    provider = create_provider_from_env()
    assert provider.validate_config()
