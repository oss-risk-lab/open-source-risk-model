"""
Property-based tests for the ScopeClassifier module.

Feature: dependency-scope-classification, Property 1: Output domain validity

Validates: Requirements 7.2, 16.2

Uses the hypothesis library to generate arbitrary inputs and verify that
classify() always returns values within the valid enum sets and never raises
exceptions.
"""

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.dependencies.scope_classifier import (
    DependencyScope,
    ScopeConfidence,
    classify,
)

# Valid output sets
VALID_SCOPES = {s.value for s in DependencyScope}
VALID_CONFIDENCES = {c.value for c in ScopeConfidence}


class TestOutputDomainValidity:
    """Property 1: Output Domain Validity.

    For any input to classify() — including arbitrary strings for ecosystem,
    manifest_type, dependency_group, and source_file, and arbitrary booleans
    for is_optional — the returned dependency_scope SHALL be one of
    {runtime, dev, test, build, optional, peer, unknown} and the returned
    scope_confidence SHALL be one of {high, medium, low}. The function SHALL
    never return None, raise an exception, or produce a value outside these
    sets.

    **Validates: Requirements 7.2, 16.2**
    """

    @given(
        ecosystem=st.text(),
        manifest_type=st.text(),
        dependency_group=st.text(),
        source_file=st.text(),
        is_optional=st.booleans(),
    )
    @settings(max_examples=200)
    def test_scope_is_always_valid_enum(
        self,
        ecosystem: str,
        manifest_type: str,
        dependency_group: str,
        source_file: str,
        is_optional: bool,
    ):
        """classify() always returns a scope in the valid enum set."""
        scope, confidence = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        assert scope.value in VALID_SCOPES, (
            f"scope {scope!r} not in {VALID_SCOPES}"
        )

    @given(
        ecosystem=st.text(),
        manifest_type=st.text(),
        dependency_group=st.text(),
        source_file=st.text(),
        is_optional=st.booleans(),
    )
    @settings(max_examples=200)
    def test_confidence_is_always_valid_enum(
        self,
        ecosystem: str,
        manifest_type: str,
        dependency_group: str,
        source_file: str,
        is_optional: bool,
    ):
        """classify() always returns a confidence in the valid enum set."""
        scope, confidence = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        assert confidence.value in VALID_CONFIDENCES, (
            f"confidence {confidence!r} not in {VALID_CONFIDENCES}"
        )

    @given(
        ecosystem=st.text(),
        manifest_type=st.text(),
        dependency_group=st.text(),
        source_file=st.text(),
        is_optional=st.booleans(),
    )
    @settings(max_examples=200)
    def test_classify_never_returns_none(
        self,
        ecosystem: str,
        manifest_type: str,
        dependency_group: str,
        source_file: str,
        is_optional: bool,
    ):
        """classify() never returns None for either element of the tuple."""
        result = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        assert result is not None, "classify() returned None"
        assert result[0] is not None, "scope is None"
        assert result[1] is not None, "confidence is None"

    @given(
        ecosystem=st.text(),
        manifest_type=st.text(),
        dependency_group=st.text(),
        source_file=st.text(),
        is_optional=st.booleans(),
    )
    @settings(max_examples=200)
    def test_classify_never_raises(
        self,
        ecosystem: str,
        manifest_type: str,
        dependency_group: str,
        source_file: str,
        is_optional: bool,
    ):
        """classify() never raises an exception for any input."""
        # If this raises, hypothesis will report the failing example.
        scope, confidence = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        # Verify the return types are the expected enum types
        assert isinstance(scope, DependencyScope)
        assert isinstance(confidence, ScopeConfidence)


class TestClassificationDeterminism:
    """Property 2: Classification Determinism.

    For any valid manifest metadata input (ecosystem, manifest_type,
    dependency_group, source_file, is_optional), calling classify() twice
    with identical arguments SHALL produce identical (dependency_scope,
    scope_confidence) results. The function is pure and stateless.

    Feature: dependency-scope-classification, Property 2: Classification determinism

    **Validates: Requirements 16.1**
    """

    @given(
        ecosystem=st.text(),
        manifest_type=st.text(),
        dependency_group=st.text(),
        source_file=st.text(),
        is_optional=st.booleans(),
    )
    @settings(max_examples=200)
    def test_classify_twice_returns_identical_scope(
        self,
        ecosystem: str,
        manifest_type: str,
        dependency_group: str,
        source_file: str,
        is_optional: bool,
    ):
        """Calling classify() twice with the same args returns the same scope."""
        result1 = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        result2 = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        assert result1[0] == result2[0], (
            f"Scope mismatch: {result1[0]!r} != {result2[0]!r}"
        )

    @given(
        ecosystem=st.text(),
        manifest_type=st.text(),
        dependency_group=st.text(),
        source_file=st.text(),
        is_optional=st.booleans(),
    )
    @settings(max_examples=200)
    def test_classify_twice_returns_identical_confidence(
        self,
        ecosystem: str,
        manifest_type: str,
        dependency_group: str,
        source_file: str,
        is_optional: bool,
    ):
        """Calling classify() twice with the same args returns the same confidence."""
        result1 = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        result2 = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        assert result1[1] == result2[1], (
            f"Confidence mismatch: {result1[1]!r} != {result2[1]!r}"
        )

    @given(
        ecosystem=st.text(),
        manifest_type=st.text(),
        dependency_group=st.text(),
        source_file=st.text(),
        is_optional=st.booleans(),
    )
    @settings(max_examples=200)
    def test_classify_twice_returns_identical_tuple(
        self,
        ecosystem: str,
        manifest_type: str,
        dependency_group: str,
        source_file: str,
        is_optional: bool,
    ):
        """Calling classify() twice with the same args returns the exact same tuple."""
        result1 = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        result2 = classify(
            ecosystem=ecosystem,
            manifest_type=manifest_type,
            dependency_group=dependency_group,
            source_file=source_file,
            is_optional=is_optional,
        )
        assert result1 == result2, (
            f"Results differ: {result1!r} != {result2!r}"
        )
