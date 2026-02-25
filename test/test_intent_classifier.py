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
from unittest.mock import Mock, patch
from open_source_risk_model.query.intent_classifier import (
    IntentClassifier,
    ClassificationResult,
    IntentType
)


# Skip tests if no API key (CI/CD environments)
skip_if_no_api_key = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)


@pytest.fixture
def classifier():
    """Create classifier instance."""
    return IntentClassifier(model="gpt-4")


@pytest.fixture
def mock_classifier():
    """Create classifier with mocked LLM."""
    classifier = IntentClassifier(model="gpt-4", api_key="test-key")
    return classifier


class TestClassificationAccuracy:
    """Test classification accuracy for each intent."""
    
    @skip_if_no_api_key
    def test_list_dependencies_classification(self, classifier):
        """Test classifying list_dependencies queries."""
        queries = [
            "What are the dependencies of django/django?",
            "List dependencies for flask",
            "Show me what django depends on"
        ]
        
        for query in queries:
            result = classifier.classify(query)
            assert result.intent == "list_dependencies"
            assert result.confidence >= 0.7
            assert "repo_full_name" in result.parameters
    
    @skip_if_no_api_key
    def test_find_dependents_classification(self, classifier):
        """Test classifying find_dependents queries."""
        queries = [
            "Which repos depend on flask?",
            "What uses the requests package?",
            "Find dependents of numpy"
        ]
        
        for query in queries:
            result = classifier.classify(query)
            assert result.intent == "find_dependents"
            assert result.confidence >= 0.7
            assert "package_name" in result.parameters
    
    @skip_if_no_api_key
    def test_dataset_stats_classification(self, classifier):
        """Test classifying dataset_stats queries."""
        queries = [
            "How many repos do we have?",
            "Show dataset statistics",
            "What's in the database?"
        ]
        
        for query in queries:
            result = classifier.classify(query)
            assert result.intent == "dataset_stats"
            assert result.confidence >= 0.7


class TestParameterExtraction:
    """Test parameter extraction from natural language."""
    
    def test_extract_repo_name(self, mock_classifier):
        """Test extracting repository name."""
        mock_response = {
            "intent": "list_dependencies",
            "parameters": {"repo_full_name": "django/django"},
            "confidence": 0.95,
            "reasoning": "Clear request for dependencies"
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            result = mock_classifier.classify("What are the dependencies of django/django?")
            
            assert result.parameters["repo_full_name"] == "django/django"
    
    def test_extract_package_name_and_registry(self, mock_classifier):
        """Test extracting package name and registry type."""
        mock_response = {
            "intent": "find_dependents",
            "parameters": {
                "package_name": "flask",
                "registry_type": "pypi"
            },
            "confidence": 0.92,
            "reasoning": "Looking for dependents of Python package"
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            result = mock_classifier.classify("Which repos depend on flask?")
            
            assert result.parameters["package_name"] == "flask"
            assert result.parameters["registry_type"] == "pypi"
    
    def test_extract_max_depth(self, mock_classifier):
        """Test extracting max_depth parameter."""
        mock_response = {
            "intent": "get_dependency_tree",
            "parameters": {
                "repo_full_name": "pallets/flask",
                "max_depth": 2
            },
            "confidence": 0.90,
            "reasoning": "Request for dependency tree with depth limit"
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            result = mock_classifier.classify("Show dependency tree for flask with depth 2")
            
            assert result.parameters["max_depth"] == 2


class TestConfidenceThresholding:
    """Test confidence threshold enforcement."""
    
    def test_low_confidence_returns_unknown(self, mock_classifier):
        """Test that low confidence returns unknown intent."""
        mock_response = {
            "intent": "list_dependencies",
            "parameters": {"repo_full_name": "something"},
            "confidence": 0.5,  # Below threshold
            "reasoning": "Ambiguous query"
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            result = mock_classifier.classify("Show me stuff")
            
            assert result.intent == "unknown"
            assert result.confidence == 0.5
            assert "threshold" in result.reasoning.lower()
    
    def test_high_confidence_accepted(self, mock_classifier):
        """Test that high confidence is accepted."""
        mock_response = {
            "intent": "dataset_stats",
            "parameters": {},
            "confidence": 0.95,
            "reasoning": "Clear request for stats"
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            result = mock_classifier.classify("How many repos?")
            
            assert result.intent == "dataset_stats"
            assert result.confidence == 0.95


class TestInvalidIntentHandling:
    """Test handling of invalid intents from LLM."""
    
    def test_invalid_intent_returns_unknown(self, mock_classifier):
        """Test that invalid intent from LLM returns unknown."""
        mock_response = {
            "intent": "delete_all_data",  # Not in allowlist
            "parameters": {},
            "confidence": 0.95,
            "reasoning": "Malicious intent"
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            result = mock_classifier.classify("Delete everything")
            
            assert result.intent == "unknown"
            assert result.confidence == 0.0
            assert "not in allowlist" in result.reasoning


class TestJSONSchemaValidation:
    """Test JSON schema validation."""
    
    def test_missing_intent_field(self, mock_classifier):
        """Test that missing intent field raises error."""
        mock_response = {
            "parameters": {},
            "confidence": 0.95
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            with pytest.raises(ValueError, match="Missing 'intent' field"):
                mock_classifier.classify("Test query")
    
    def test_missing_parameters_field(self, mock_classifier):
        """Test that missing parameters field raises error."""
        mock_response = {
            "intent": "dataset_stats",
            "confidence": 0.95
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            with pytest.raises(ValueError, match="Missing 'parameters' field"):
                mock_classifier.classify("Test query")
    
    def test_missing_confidence_field(self, mock_classifier):
        """Test that missing confidence field raises error."""
        mock_response = {
            "intent": "dataset_stats",
            "parameters": {}
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            with pytest.raises(ValueError, match="Missing 'confidence' field"):
                mock_classifier.classify("Test query")
    
    def test_invalid_confidence_range(self, mock_classifier):
        """Test that confidence outside 0-1 range raises error."""
        mock_response = {
            "intent": "dataset_stats",
            "parameters": {},
            "confidence": 1.5  # Invalid
        }
        
        with patch.object(mock_classifier, '_call_llm', return_value=str(mock_response).replace("'", '"')):
            with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
                mock_classifier.classify("Test query")
    
    def test_invalid_json_response(self, mock_classifier):
        """Test that invalid JSON raises error."""
        with patch.object(mock_classifier, '_call_llm', return_value="Not valid JSON"):
            with pytest.raises(ValueError, match="Invalid JSON response"):
                mock_classifier.classify("Test query")


class TestErrorHandling:
    """Test error handling."""
    
    def test_no_api_key(self):
        """Test that missing API key raises error."""
        classifier = IntentClassifier(api_key=None)
        
        with pytest.raises(ValueError, match="API key not configured"):
            classifier.classify("Test query")
    
    def test_llm_api_failure(self, mock_classifier):
        """Test handling of LLM API failures."""
        with patch.object(mock_classifier, '_call_llm', side_effect=Exception("API error")):
            with pytest.raises(ValueError, match="Failed to classify query"):
                mock_classifier.classify("Test query")


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
