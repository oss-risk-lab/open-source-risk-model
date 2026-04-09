"""
Property-based tests for EntityNormalizer.

Feature: github-api-optimization-query-coverage
Property 34: Entity Normalization Consistency
"""

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.ingestion.entity_normalizer import (
    EntityNormalizer,
    NormalizationResult,
)


# Strategy for generating valid repository identifiers (owner/repo format)
@st.composite
def repo_identifier(draw):
    """Generate valid repository identifier in owner/repo format."""
    # GitHub allows alphanumeric, hyphens, underscores, and dots
    # Must start with alphanumeric
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
    start_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    
    # Generate owner (1-39 chars)
    owner_start = draw(st.sampled_from(start_chars))
    owner_rest = draw(st.text(alphabet=alphabet, min_size=0, max_size=38))
    owner = owner_start + owner_rest
    
    # Generate repo (1-100 chars)
    repo_start = draw(st.sampled_from(start_chars))
    repo_rest = draw(st.text(alphabet=alphabet, min_size=0, max_size=99))
    repo = repo_start + repo_rest
    
    return f"{owner}/{repo}"


# Strategy for generating known package names from mappings
known_packages = st.sampled_from(
    [
        ("numpy", "pypi"),
        ("pandas", "pypi"),
        ("flask", "pypi"),
        ("django", "pypi"),
        ("requests", "pypi"),
        ("pytest", "pypi"),
        ("react", "npm"),
        ("vue", "npm"),
        ("angular", "npm"),
        ("express", "npm"),
        ("webpack", "npm"),
        ("serde", "cargo"),
        ("tokio", "cargo"),
    ]
)


@pytest.mark.property_test
class TestEntityNormalizerProperties:
    """Property-based tests for entity normalization."""

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    @given(package_name=st.text(min_size=1, max_size=100), ecosystem=st.text(min_size=1, max_size=20))
    def test_normalization_determinism(self, package_name, ecosystem):
        """
        For any package name and ecosystem, normalizing multiple times should produce identical results.

        This validates that normalization is deterministic.
        """
        normalizer = EntityNormalizer()

        # Normalize twice
        result1 = normalizer.normalize_package(package_name, ecosystem)
        result2 = normalizer.normalize_package(package_name, ecosystem)

        # Results should be identical
        assert result1.canonical_identifier == result2.canonical_identifier
        assert result1.confidence == result2.confidence
        assert result1.alternatives == result2.alternatives
        assert result1.warning == result2.warning

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    @given(repo_id=repo_identifier())
    @settings(deadline=500)  # Allow more time for first run
    def test_exact_repo_format_highest_confidence(self, repo_id):
        """
        For any valid owner/repo format, normalization should return confidence 1.0.

        This validates Rule 1: Exact owner/repo format has highest priority.
        """
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package(repo_id)

        assert result.canonical_identifier == repo_id
        assert result.confidence == 1.0
        assert result.alternatives == []
        assert result.warning is None

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    @given(package_data=known_packages)
    def test_known_package_mapping_confidence(self, package_data):
        """
        For any known package with ecosystem, normalization should return confidence 0.95.

        This validates Rule 2: Exact package mapping by ecosystem.
        """
        package_name, ecosystem = package_data
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package(package_name, ecosystem)

        assert result.canonical_identifier is not None
        assert result.confidence == 0.95
        assert result.alternatives == []
        assert result.warning is None

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    @given(package_data=known_packages)
    def test_known_package_without_ecosystem_lower_confidence(self, package_data):
        """
        For any known package without ecosystem, if unique, confidence should be 0.80.

        This validates Rule 3: Inferred mapping from aliases.
        """
        package_name, _ = package_data
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package(package_name)

        # Should either find it with confidence 0.80 (unique) or 0.0 (ambiguous)
        assert result.confidence in [0.0, 0.80]

        if result.confidence == 0.80:
            # Unique match
            assert result.canonical_identifier is not None
            assert result.warning is not None  # Should mention inference
        else:
            # Ambiguous or not found
            assert result.canonical_identifier is None

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    @given(unknown_package=st.text(min_size=1, max_size=50).filter(
        lambda x: x not in ["numpy", "pandas", "flask", "django", "requests", "pytest",
                           "react", "vue", "angular", "express", "webpack", "serde", "tokio"]
    ))
    def test_unknown_package_zero_confidence(self, unknown_package):
        """
        For any unknown package, normalization should return confidence 0.0.

        This validates Rule 4: Unresolved entity warning.
        """
        # Skip if it looks like a repo identifier
        if "/" in unknown_package:
            return

        normalizer = EntityNormalizer()

        result = normalizer.normalize_package(unknown_package, "unknown_ecosystem")

        assert result.canonical_identifier is None
        assert result.confidence == 0.0
        assert result.warning is not None

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    @given(repo_id=repo_identifier())
    def test_normalize_repository_idempotent(self, repo_id):
        """
        For any repository identifier, normalize_repository should be idempotent.

        Normalizing an already normalized identifier should return the same value.
        """
        normalizer = EntityNormalizer()

        result1 = normalizer.normalize_repository(repo_id)
        result2 = normalizer.normalize_repository(result1)

        assert result1 == result2

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    def test_confidence_ordering(self):
        """
        Confidence values should follow strict ordering: exact > ecosystem > inferred > unresolved.

        This validates the rule hierarchy.
        """
        normalizer = EntityNormalizer()

        # Exact format
        exact = normalizer.normalize_package("numpy/numpy")
        # Known package with ecosystem
        ecosystem = normalizer.normalize_package("numpy", "pypi")
        # Known package without ecosystem (if unique)
        inferred = normalizer.normalize_package("numpy")
        # Unknown package
        unresolved = normalizer.normalize_package("totally-unknown-package-xyz")

        # Confidence ordering
        assert exact.confidence == 1.0
        assert ecosystem.confidence == 0.95
        assert inferred.confidence in [0.0, 0.80]  # Depends on uniqueness
        assert unresolved.confidence == 0.0

        # Exact > ecosystem > inferred
        assert exact.confidence > ecosystem.confidence
        if inferred.confidence > 0:
            assert ecosystem.confidence > inferred.confidence

    # Feature: github-api-optimization-query-coverage, Property 34: Entity Normalization Consistency
    @given(package_name=st.text(min_size=1, max_size=100))
    def test_result_structure_completeness(self, package_name):
        """
        For any package name, normalization result should have all required fields.

        This validates the NormalizationResult structure.
        """
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package(package_name)

        # All fields should be present
        assert hasattr(result, "canonical_identifier")
        assert hasattr(result, "confidence")
        assert hasattr(result, "alternatives")
        assert hasattr(result, "warning")

        # Confidence should be in valid range
        assert 0.0 <= result.confidence <= 1.0

        # Alternatives should be a list
        assert isinstance(result.alternatives, list)
