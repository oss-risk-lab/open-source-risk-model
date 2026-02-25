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

import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

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
    
    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None):
        """
        Initialize intent classifier.
        
        Args:
            model: LLM model to use (default: gpt-4)
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        
        if not self.api_key:
            logger.warning("No OpenAI API key found. Classifier will not work.")
    
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
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        
        # Build prompt with strict JSON schema
        prompt = self._build_prompt(query)
        
        # Call LLM
        try:
            response = self._call_llm(prompt)
            result = self._parse_response(response)
            
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
    
    def _build_prompt(self, query: str) -> str:
        """Build LLM prompt with strict JSON schema."""
        return f"""You are a query intent classifier for a dependency graph database.

Your job is to classify user queries into predefined intents and extract parameters.

AVAILABLE INTENTS:

1. list_dependencies
   Description: List direct dependencies of a repository
   Parameters: repo_full_name (required), dependency_group (optional: prod/dev/optional)
   Examples: "What are the dependencies of django/django?"
             "List prod dependencies for flask"

2. find_dependents
   Description: Find repositories that depend on a package
   Parameters: package_name (required), registry_type (optional: pypi/npm)
   Examples: "Which repos depend on flask?"
             "What uses the requests package?"

3. get_dependency_tree
   Description: Get full dependency tree for a repository
   Parameters: repo_full_name (required), max_depth (optional: 1-5, default 3)
   Examples: "Show dependency tree for react"
             "Get the full dependency graph of django"

4. check_resolution
   Description: Check if a package resolves to a GitHub repository
   Parameters: package_name (required), registry_type (required: pypi/npm)
   Examples: "Does numpy resolve to a GitHub repo?"
             "Check if flask has a GitHub repository"

5. list_unresolved
   Description: List dependencies that couldn't be resolved
   Parameters: repo_full_name (optional)
   Examples: "Show unresolved dependencies"
             "Which dependencies of django couldn't be resolved?"

6. list_manifests
   Description: List manifest files for a repository
   Parameters: repo_full_name (required)
   Examples: "What manifest files does react have?"
             "List manifests for django/django"

7. count_by_manifest_type
   Description: Count manifests by type across all repositories
   Parameters: none
   Examples: "How many package.json vs requirements.txt files?"
             "Count manifests by type"

8. repo_stats
   Description: Get statistics for a specific repository
   Parameters: repo_full_name (required)
   Examples: "Give me stats for django/django"
             "Show repository statistics for flask"

9. dataset_stats
   Description: Get overall dataset statistics
   Parameters: none
   Examples: "How many repos do we have?"
             "Show dataset statistics"
             "What's in the database?"

10. search_repos
    Description: Search repositories by name pattern
    Parameters: pattern (required)
    Examples: "Find repos with 'django' in the name"
              "Search for test repositories"

11. search_packages
    Description: Search packages by name pattern
    Parameters: pattern (required), registry_type (optional: pypi/npm)
    Examples: "Find packages starting with 'pytest'"
              "Search for flask packages"

USER QUERY: "{query}"

Classify the query and extract parameters. Return ONLY valid JSON in this exact format:

{{
  "intent": "<intent_name>",
  "parameters": {{
    "param1": "value1",
    "param2": "value2"
  }},
  "confidence": 0.95,
  "reasoning": "Brief explanation of classification"
}}

RULES:
1. intent MUST be one of the 11 intents listed above
2. confidence MUST be a number between 0.0 and 1.0
3. If unsure (confidence < 0.7), use intent "unknown"
4. Extract ALL relevant parameters from the query
5. For repo names, use format "owner/repo" (e.g., "django/django")
6. For registry_type, infer from context (Python packages = pypi, JavaScript = npm)
7. Return ONLY the JSON object, no other text

RESPOND WITH JSON ONLY:"""
    
    def _call_llm(self, prompt: str) -> str:
        """
        Call LLM API.
        
        Args:
            prompt: Prompt to send to LLM
        
        Returns:
            LLM response text
        """
        try:
            import openai
            
            client = openai.OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise query classifier. Return only valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.0,  # Deterministic
                max_tokens=500,
                response_format={"type": "json_object"}  # Force JSON output
            )
            
            return response.choices[0].message.content
        
        except ImportError:
            raise ValueError("openai package not installed. Run: pip install openai")
        except Exception as e:
            raise ValueError(f"LLM API call failed: {e}")
    
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
def classify_query(query: str, model: str = "gpt-4") -> ClassificationResult:
    """
    Classify a query using default classifier.
    
    Args:
        query: Natural language query
        model: LLM model to use
    
    Returns:
        ClassificationResult
    """
    classifier = IntentClassifier(model=model)
    return classifier.classify(query)
