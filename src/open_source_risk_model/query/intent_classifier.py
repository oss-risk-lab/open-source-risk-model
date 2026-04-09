"""
Intent Classifier using LLM

Classifies natural language queries into predefined intents.
Extracts parameters from user queries.

CRITICAL: LLM NEVER GENERATES SQL
- LLM only classifies intent and extracts parameters
- All SQL is hardcoded in IntentExecutor
- Strict JSON schema enforced
- Confidence gating (reject < 0.7)
"""

import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from open_source_risk_model.llm import LLMClient

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Available intent types (strict allowlist)."""
    LIST_DEPENDENCIES = "list_dependencies"
    FIND_DEPENDENTS = "find_dependents"
    GET_DEPENDENCY_TREE = "get_dependency_tree"
    CHECK_RESOLUTION = "check_resolution"
    LIST_UNRESOLVED = "list_unresolved"
    LIST_MANIFESTS = "list_manifests"
    COUNT_BY_MANIFEST_TYPE = "count_by_manifest_type"
    REPO_STATS = "repo_stats"
    DATASET_STATS = "dataset_stats"
    SEARCH_REPOS = "search_repos"
    SEARCH_PACKAGES = "search_packages"
    # New query coverage intents
    REPO_LOOKUP = "repo_lookup"
    REPO_COMPARISON = "repo_comparison"
    MISSING_REPO_HANDLING = "missing_repo_handling"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of intent classification."""
    intent: str
    parameters: Dict[str, Any]
    confidence: float
    reasoning: Optional[str] = None


class IntentClassifier:
    """
    Classifies natural language queries into intents.
    
    Uses LLM to:
    1. Classify query into one of 11 predefined intents
    2. Extract parameters from natural language
    3. Return confidence score
    
    Does NOT:
    - Generate SQL (all SQL is hardcoded)
    - Execute queries (that's IntentExecutor's job)
    - Access database (read-only classification)
    """
    
    # Confidence threshold for accepting classification
    CONFIDENCE_THRESHOLD = 0.7
    
    # Intent definitions for prompt formatting
    INTENT_DEFINITIONS = [
        {
            "name": "list_dependencies",
            "description": "List direct dependencies of a repository",
            "parameters": "repo_full_name (required), dependency_group (optional: prod/dev/optional)",
            "examples": [
                "What are the dependencies of django/django?",
                "List prod dependencies for flask"
            ]
        },
        {
            "name": "find_dependents",
            "description": "Find repositories that depend on a package",
            "parameters": "package_name (required), registry_type (optional: pypi/npm)",
            "examples": [
                "Which repos depend on flask?",
                "What uses the requests package?"
            ]
        },
        {
            "name": "get_dependency_tree",
            "description": "Get full dependency tree for a repository",
            "parameters": "repo_full_name (required), max_depth (optional: 1-5, default 3)",
            "examples": [
                "Show dependency tree for react",
                "Get the full dependency graph of django"
            ]
        },
        {
            "name": "check_resolution",
            "description": "Check if a package resolves to a GitHub repository",
            "parameters": "package_name (required), registry_type (required: pypi/npm)",
            "examples": [
                "Does numpy resolve to a GitHub repo?",
                "Check if flask has a GitHub repository"
            ]
        },
        {
            "name": "list_unresolved",
            "description": "List dependencies that couldn't be resolved",
            "parameters": "repo_full_name (optional)",
            "examples": [
                "Show unresolved dependencies",
                "Which dependencies of django couldn't be resolved?"
            ]
        },
        {
            "name": "list_manifests",
            "description": "List manifest files for a repository",
            "parameters": "repo_full_name (required)",
            "examples": [
                "What manifest files does react have?",
                "List manifests for django/django"
            ]
        },
        {
            "name": "count_by_manifest_type",
            "description": "Count manifests by type across all repositories",
            "parameters": "none",
            "examples": [
                "How many package.json vs requirements.txt files?",
                "Count manifests by type"
            ]
        },
        {
            "name": "repo_stats",
            "description": "Get statistics for a specific repository",
            "parameters": "repo_full_name (required)",
            "examples": [
                "Give me stats for django/django",
                "Show repository statistics for flask"
            ]
        },
        {
            "name": "dataset_stats",
            "description": "Get overall dataset statistics",
            "parameters": "none",
            "examples": [
                "How many repos do we have?",
                "Show dataset statistics",
                "What's in the database?"
            ]
        },
        {
            "name": "search_repos",
            "description": "Search repositories by name pattern",
            "parameters": "pattern (required)",
            "examples": [
                "Find repos with 'django' in the name",
                "Search for test repositories"
            ]
        },
        {
            "name": "search_packages",
            "description": "Search packages by name pattern",
            "parameters": "pattern (required), registry_type (optional: pypi/npm)",
            "examples": [
                "Find packages starting with 'pytest'",
                "Search for flask packages"
            ]
        },
        {
            "name": "repo_lookup",
            "description": "Look up maintenance risk score for a single repository (may fetch live if not in database)",
            "parameters": "repo_identifier (required: repo name or package name), ingestion_mode (optional: provisional/full), persistence_mode (optional: temporary/cache/database)",
            "examples": [
                "What's the maintenance risk score for numpy?",
                "How risky is the flask repository?",
                "Analyze the maintenance risk of django/django"
            ]
        },
        {
            "name": "repo_comparison",
            "description": "Compare maintenance risk scores for multiple repositories",
            "parameters": "repo_identifiers (required: list of repo/package names), ingestion_mode (optional: provisional/full), persistence_mode (optional: temporary/cache/database)",
            "examples": [
                "Compare flask vs django maintenance risk",
                "Which is safer: numpy or pandas?",
                "Compare maintenance risk for react, vue, and angular"
            ]
        },
        {
            "name": "missing_repo_handling",
            "description": "Force live ingestion for a repository not in database",
            "parameters": "repo_identifier (required: repo name or package name), ingestion_mode (optional: provisional/full), persistence_mode (optional: temporary/cache/database)",
            "examples": [
                "Fetch live data for new-package",
                "Ingest and analyze unknown-repo",
                "Get fresh data for this repository"
            ]
        }
    ]
    
    def __init__(self, llm_client: LLMClient):
        """
        Initialize intent classifier.
        
        Args:
            llm_client: LLMClient instance configured with provider and prompt manager
        """
        self.llm_client = llm_client
        logger.info("IntentClassifier initialized with LLMClient")
    
    def classify(self, query: str) -> ClassificationResult:
        """
        Classify a natural language query.
        
        Args:
            query: Natural language query from user
        
        Returns:
            ClassificationResult with intent, parameters, and confidence
        
        Raises:
            ValueError: If classification fails or confidence too low
        """
        # Call LLM using abstraction layer
        try:
            response = self.llm_client.complete(
                prompt_name="intent_classification",
                prompt_params={
                    "query": query,
                    "available_intents": self._format_intents()
                },
                response_format="json",
                temperature=0.0,
                max_tokens=500
            )
            
            result = self._parse_response(response.content)
            
            # Validate confidence
            if result.confidence < self.CONFIDENCE_THRESHOLD:
                logger.warning(
                    f"Low confidence classification: {result.confidence:.2f} < {self.CONFIDENCE_THRESHOLD}",
                    extra={"query": query, "intent": result.intent}
                )
                return ClassificationResult(
                    intent="unknown",
                    parameters={},
                    confidence=result.confidence,
                    reasoning=f"Confidence {result.confidence:.2f} below threshold {self.CONFIDENCE_THRESHOLD}"
                )
            
            # Validate intent is in allowlist
            if result.intent not in [e.value for e in IntentType]:
                logger.warning(f"Invalid intent from LLM: {result.intent}")
                return ClassificationResult(
                    intent="unknown",
                    parameters={},
                    confidence=0.0,
                    reasoning=f"Intent '{result.intent}' not in allowlist"
                )
            
            logger.info(
                f"Classified query",
                extra={
                    "query": query,
                    "intent": result.intent,
                    "confidence": result.confidence
                }
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Classification failed: {e}", exc_info=True)
            raise ValueError(f"Failed to classify query: {e}")
    
    def _format_intents(self) -> str:
        """
        Format intent definitions for the prompt.
        
        Returns:
            Formatted string with all intent definitions
        """
        formatted = []
        for i, intent in enumerate(self.INTENT_DEFINITIONS, 1):
            formatted.append(f"{i}. {intent['name']}")
            formatted.append(f"   Description: {intent['description']}")
            formatted.append(f"   Parameters: {intent['parameters']}")
            formatted.append(f"   Examples: {'; '.join(intent['examples'])}")
            formatted.append("")
        
        return "\n".join(formatted)
    
    def _parse_response(self, response: str) -> ClassificationResult:
        """
        Parse LLM response into ClassificationResult.
        
        Args:
            response: JSON response from LLM
        
        Returns:
            ClassificationResult
        
        Raises:
            ValueError: If response is invalid JSON or missing required fields
        """
        try:
            data = json.loads(response)
            
            # Validate required fields
            if "intent" not in data:
                raise ValueError("Missing 'intent' field in response")
            if "parameters" not in data:
                raise ValueError("Missing 'parameters' field in response")
            if "confidence" not in data:
                raise ValueError("Missing 'confidence' field in response")
            
            # Validate types
            if not isinstance(data["intent"], str):
                raise ValueError("'intent' must be a string")
            if not isinstance(data["parameters"], dict):
                raise ValueError("'parameters' must be a dictionary")
            if not isinstance(data["confidence"], (int, float)):
                raise ValueError("'confidence' must be a number")
            
            # Validate confidence range
            confidence = float(data["confidence"])
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"'confidence' must be between 0.0 and 1.0, got {confidence}")
            
            return ClassificationResult(
                intent=data["intent"],
                parameters=data["parameters"],
                confidence=confidence,
                reasoning=data.get("reasoning")
            )
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse response: {e}")


# Convenience function for quick classification
def classify_query(query: str, llm_client: LLMClient) -> ClassificationResult:
    """
    Classify a query using provided LLM client.
    
    Args:
        query: Natural language query
        llm_client: Configured LLMClient instance
    
    Returns:
        ClassificationResult
    """
    classifier = IntentClassifier(llm_client)
    return classifier.classify(query)
