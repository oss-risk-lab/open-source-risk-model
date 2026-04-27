"""
Tests for IntentClassifier

Tests cover:
- Classification accuracy for each intent
- Parameter extraction
- Confidence thresholding
- Unknown intent handling
- JSON schema validation
"""

import pytest
import os
from pathlib import Path
from open_source_risk_model.query.intent_classifier import (
    IntentClassifier,
    ClassificationResult,
    IntentType
)
from open_source_risk_model.llm import LLMClient, PromptManager
from open_source_risk_model.llm.providers import MockProvider


# Skip tests if no API key (CI/CD environments) - for integration tests only
skip_if_no_api_key = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)


@pytest.fixture
def prompt_manager():
    """Create PromptManager instance."""
    prompts_dir = Path("src/open_source_risk_model/llm/prompts")
    return PromptManager(prompts_dir)


@pytest.fixture
def mock_provider():
    """Create MockProvider with default responses."""
    return MockProvider({
        "intent_classification": '{"intent": "unknown", "parameters": {}, "confidence": 0.5, "reasoning": "Default response"}'
    })


@pytest.fixture
def classifier(prompt_manager, mock_provider):
    """Create classifier instance with mock provider."""
    client = LLMClient(mock_provider, prompt_manager)
    return IntentClassifier(client)


class TestClassificationAccuracy:
    """Test classification accuracy for each intent."""
    
    def test_list_dependencies_classification(self, prompt_manager):
        """Test classifying list_dependencies queries."""
        # Setup mock provider with list_dependencies response
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "list_dependencies", "parameters": {"repo_full_name": "django/django"}, "confidence": 0.95, "reasoning": "Clear request for dependencies"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("What are the dependencies of django/django?")
        assert result.intent == "list_dependencies"
        assert result.confidence >= 0.7
        assert "repo_full_name" in result.parameters
    
    def test_find_dependents_classification(self, prompt_manager):
        """Test classifying find_dependents queries."""
        # Setup mock provider with find_dependents response
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "find_dependents", "parameters": {"package_name": "flask"}, "confidence": 0.92, "reasoning": "Looking for dependents"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("Which repos depend on flask?")
        assert result.intent == "find_dependents"
        assert result.confidence >= 0.7
        assert "package_name" in result.parameters
    
    def test_dataset_stats_classification(self, prompt_manager):
        """Test classifying dataset_stats queries."""
        # Setup mock provider with dataset_stats response
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "dataset_stats", "parameters": {}, "confidence": 0.95, "reasoning": "Request for dataset statistics"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("How many repos do we have?")
        assert result.intent == "dataset_stats"
        assert result.confidence >= 0.7


class TestParameterExtraction:
    """Test parameter extraction from natural language."""
    
    def test_extract_repo_name(self, prompt_manager):
        """Test extracting repository name."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "list_dependencies", "parameters": {"repo_full_name": "django/django"}, "confidence": 0.95, "reasoning": "Clear request for dependencies"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("What are the dependencies of django/django?")
        assert result.parameters["repo_full_name"] == "django/django"
    
    def test_extract_package_name_and_registry(self, prompt_manager):
        """Test extracting package name and registry type."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "find_dependents", "parameters": {"package_name": "flask", "registry_type": "pypi"}, "confidence": 0.92, "reasoning": "Looking for dependents of Python package"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("Which repos depend on flask?")
        assert result.parameters["package_name"] == "flask"
        assert result.parameters["registry_type"] == "pypi"
    
    def test_extract_max_depth(self, prompt_manager):
        """Test extracting max_depth parameter."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "get_dependency_tree", "parameters": {"repo_full_name": "pallets/flask", "max_depth": 2}, "confidence": 0.90, "reasoning": "Request for dependency tree with depth limit"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("Show dependency tree for flask with depth 2")
        assert result.parameters["max_depth"] == 2


class TestConfidenceThresholding:
    """Test confidence threshold enforcement."""
    
    def test_low_confidence_returns_unknown(self, prompt_manager):
        """Test that low confidence returns unknown intent."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "list_dependencies", "parameters": {"repo_full_name": "something"}, "confidence": 0.5, "reasoning": "Ambiguous query"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("Show me stuff")
        assert result.intent == "unknown"
        assert result.confidence == 0.5
        assert "threshold" in result.reasoning.lower()
    
    def test_high_confidence_accepted(self, prompt_manager):
        """Test that high confidence is accepted."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "dataset_stats", "parameters": {}, "confidence": 0.95, "reasoning": "Clear request for stats"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("How many repos?")
        assert result.intent == "dataset_stats"
        assert result.confidence == 0.95


class TestInvalidIntentHandling:
    """Test handling of invalid intents from LLM."""
    
    def test_invalid_intent_returns_unknown(self, prompt_manager):
        """Test that invalid intent from LLM returns unknown."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "delete_all_data", "parameters": {}, "confidence": 0.95, "reasoning": "Malicious intent"}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        result = classifier.classify("Delete everything")
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert "not in allowlist" in result.reasoning


class TestJSONSchemaValidation:
    """Test JSON schema validation."""
    
    def test_missing_intent_field(self, prompt_manager):
        """Test that missing intent field raises error."""
        mock_provider = MockProvider({
            "intent_classification": '{"parameters": {}, "confidence": 0.95}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        with pytest.raises(ValueError, match="Missing 'intent' field"):
            classifier.classify("Test query")
    
    def test_missing_parameters_field(self, prompt_manager):
        """Test that missing parameters field raises error."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "dataset_stats", "confidence": 0.95}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        with pytest.raises(ValueError, match="Missing 'parameters' field"):
            classifier.classify("Test query")
    
    def test_missing_confidence_field(self, prompt_manager):
        """Test that missing confidence field raises error."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "dataset_stats", "parameters": {}}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        with pytest.raises(ValueError, match="Missing 'confidence' field"):
            classifier.classify("Test query")
    
    def test_invalid_confidence_range(self, prompt_manager):
        """Test that confidence outside 0-1 range raises error."""
        mock_provider = MockProvider({
            "intent_classification": '{"intent": "dataset_stats", "parameters": {}, "confidence": 1.5}'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            classifier.classify("Test query")
    
    def test_invalid_json_response(self, prompt_manager):
        """Test that invalid JSON raises error."""
        mock_provider = MockProvider({
            "intent_classification": 'Not valid JSON'
        })
        
        client = LLMClient(mock_provider, prompt_manager)
        classifier = IntentClassifier(client)
        
        with pytest.raises(ValueError, match="Invalid JSON response"):
            classifier.classify("Test query")


class TestErrorHandling:
    """Test error handling."""
    
    def test_llm_client_required(self):
        """Test that LLMClient is required."""
        # This test verifies that IntentClassifier requires an LLMClient
        # The constructor will fail if called without proper arguments
        with pytest.raises(TypeError):
            IntentClassifier()  # Missing required llm_client argument


class TestIntentAllowlist:
    """Test that all intents are in allowlist."""
    
    def test_all_intents_in_enum(self):
        """Test that all expected intents are in IntentType enum."""
        expected_intents = [
            "list_dependencies",
            "find_dependents",
            "get_dependency_tree",
            "check_resolution",
            "list_unresolved",
            "list_manifests",
            "count_by_manifest_type",
            "repo_stats",
            "dataset_stats",
            "search_repos",
            "search_packages",
            "unknown"
        ]
        
        enum_values = [e.value for e in IntentType]
        
        for intent in expected_intents:
            assert intent in enum_values


class TestClassificationResult:
    """Test ClassificationResult dataclass."""
    
    def test_classification_result_structure(self):
        """Test that ClassificationResult has correct structure."""
        result = ClassificationResult(
            intent="dataset_stats",
            parameters={},
            confidence=0.95,
            reasoning="Test"
        )
        
        assert result.intent == "dataset_stats"
        assert result.parameters == {}
        assert result.confidence == 0.95
        assert result.reasoning == "Test"
    
    def test_classification_result_optional_reasoning(self):
        """Test that reasoning is optional."""
        result = ClassificationResult(
            intent="dataset_stats",
            parameters={},
            confidence=0.95
        )
        
        assert result.reasoning is None
