"""
Unit tests for the ScopeClassifier module.

Exhaustive table-driven tests for every row in the classification rules table,
plus fallback and defensive handling tests.

Validates: Requirements 15.1–15.5
"""

import pytest

from src.open_source_risk_model.dependencies.scope_classifier import (
    DependencyScope,
    ScopeConfidence,
    classify,
)


# ---------------------------------------------------------------------------
# Table-driven parametrized tests — one entry per classification rule row
# ---------------------------------------------------------------------------

CLASSIFICATION_RULES = [
    # --- npm / package.json (Req 15.1) ---
    pytest.param(
        "npm", "package.json", "prod", "", False,
        DependencyScope.RUNTIME, ScopeConfidence.HIGH,
        id="npm-prod",
    ),
    pytest.param(
        "npm", "package.json", "dev", "", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="npm-dev",
    ),
    pytest.param(
        "npm", "package.json", "optional", "", False,
        DependencyScope.OPTIONAL, ScopeConfidence.HIGH,
        id="npm-optional",
    ),
    pytest.param(
        "npm", "package.json", "peer", "", False,
        DependencyScope.PEER, ScopeConfidence.MEDIUM,
        id="npm-peer",
    ),
    # --- pypi / pyproject.toml PEP 621 (Req 15.2) ---
    pytest.param(
        "pypi", "pyproject.toml", "prod", "", False,
        DependencyScope.RUNTIME, ScopeConfidence.HIGH,
        id="pyproject-pep621-prod",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "extras", "", True,
        DependencyScope.OPTIONAL, ScopeConfidence.HIGH,
        id="pyproject-pep621-optional-deps",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "dev", "", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="pyproject-pep621-dev",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "lint", "", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="pyproject-pep621-lint",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "typecheck", "", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="pyproject-pep621-typecheck",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "tooling", "", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="pyproject-pep621-tooling",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "test", "", False,
        DependencyScope.TEST, ScopeConfidence.HIGH,
        id="pyproject-pep621-test",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "docs", "", False,
        DependencyScope.BUILD, ScopeConfidence.MEDIUM,
        id="pyproject-pep621-docs",
    ),
    # --- pypi / pyproject.toml Poetry (Req 15.2) ---
    # Poetry main deps use group="prod" just like PEP 621
    pytest.param(
        "pypi", "pyproject.toml", "prod", "", False,
        DependencyScope.RUNTIME, ScopeConfidence.HIGH,
        id="pyproject-poetry-prod",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "dev", "", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="pyproject-poetry-dev",
    ),
    pytest.param(
        "pypi", "pyproject.toml", "test", "", False,
        DependencyScope.TEST, ScopeConfidence.HIGH,
        id="pyproject-poetry-test",
    ),
    # Poetry docs group — implementation returns (build, medium)
    pytest.param(
        "pypi", "pyproject.toml", "docs", "", False,
        DependencyScope.BUILD, ScopeConfidence.MEDIUM,
        id="pyproject-poetry-docs",
    ),
    # Poetry optional / extras
    pytest.param(
        "pypi", "pyproject.toml", "myextras", "", True,
        DependencyScope.OPTIONAL, ScopeConfidence.HIGH,
        id="pyproject-poetry-optional-extras",
    ),
    # --- pypi / requirements.txt (Req 15.3) ---
    pytest.param(
        "pypi", "requirements.txt", "prod", "requirements.txt", False,
        DependencyScope.RUNTIME, ScopeConfidence.MEDIUM,
        id="requirements-plain",
    ),
    pytest.param(
        "pypi", "requirements.txt", "prod", "requirements-dev.txt", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="requirements-dev-suffix",
    ),
    pytest.param(
        "pypi", "requirements.txt", "prod", "dev-requirements.txt", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="requirements-dev-prefix",
    ),
    pytest.param(
        "pypi", "requirements.txt", "prod", "requirements-test.txt", False,
        DependencyScope.TEST, ScopeConfidence.HIGH,
        id="requirements-test-suffix",
    ),
    pytest.param(
        "pypi", "requirements.txt", "prod", "test-requirements.txt", False,
        DependencyScope.TEST, ScopeConfidence.HIGH,
        id="requirements-test-prefix",
    ),
    pytest.param(
        "pypi", "requirements.txt", "prod", "requirements-docs.txt", False,
        DependencyScope.BUILD, ScopeConfidence.MEDIUM,
        id="requirements-docs-suffix",
    ),
    pytest.param(
        "pypi", "requirements.txt", "prod", "docs-requirements.txt", False,
        DependencyScope.BUILD, ScopeConfidence.MEDIUM,
        id="requirements-docs-prefix",
    ),
    pytest.param(
        "pypi", "requirements.txt", "prod", "constraints.txt", False,
        DependencyScope.UNKNOWN, ScopeConfidence.LOW,
        id="requirements-unrecognized",
    ),
    # --- cargo / Cargo.toml (Req 15.4) ---
    pytest.param(
        "cargo", "Cargo.toml", "prod", "", False,
        DependencyScope.RUNTIME, ScopeConfidence.HIGH,
        id="cargo-prod",
    ),
    pytest.param(
        "cargo", "Cargo.toml", "dev", "", False,
        DependencyScope.DEV, ScopeConfidence.HIGH,
        id="cargo-dev",
    ),
    pytest.param(
        "cargo", "Cargo.toml", "build", "", False,
        DependencyScope.BUILD, ScopeConfidence.HIGH,
        id="cargo-build",
    ),
    # --- Fallback (Req 15.5) ---
    pytest.param(
        "unknown_eco", "unknown_manifest", "unknown", "", False,
        DependencyScope.UNKNOWN, ScopeConfidence.LOW,
        id="fallback-unrecognized-ecosystem",
    ),
]


@pytest.mark.parametrize(
    "ecosystem, manifest_type, dependency_group, source_file, is_optional, "
    "expected_scope, expected_confidence",
    CLASSIFICATION_RULES,
)
def test_classification_rules(
    ecosystem,
    manifest_type,
    dependency_group,
    source_file,
    is_optional,
    expected_scope,
    expected_confidence,
):
    """Validates: Requirements 15.1–15.5"""
    scope, confidence = classify(
        ecosystem=ecosystem,
        manifest_type=manifest_type,
        dependency_group=dependency_group,
        source_file=source_file,
        is_optional=is_optional,
    )
    assert scope == expected_scope
    assert confidence == expected_confidence


# ---------------------------------------------------------------------------
# Fallback / edge-case tests
# ---------------------------------------------------------------------------


class TestFallbackClassification:
    """Tests for unrecognized ecosystems and manifests (Req 15.5)."""

    def test_completely_unknown_ecosystem(self):
        scope, conf = classify("java", "pom.xml", "compile", "pom.xml")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_empty_strings(self):
        scope, conf = classify("", "", "", "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_npm_unknown_group(self):
        """npm with an unrecognized group falls back to unknown."""
        scope, conf = classify("npm", "package.json", "bundled", "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_cargo_unknown_group(self):
        """Cargo with an unrecognized group falls back to unknown."""
        scope, conf = classify("cargo", "Cargo.toml", "bench", "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_pyproject_unknown_group(self):
        """pyproject.toml with an unrecognized group falls back to unknown."""
        scope, conf = classify("pypi", "pyproject.toml", "benchmarks", "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW


class TestDependencyGroupNoneHandling:
    """Tests that dependency_group=None is handled defensively."""

    def test_none_group_npm(self):
        """None group should not raise; falls back to unknown."""
        scope, conf = classify("npm", "package.json", None, "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_none_group_pyproject(self):
        scope, conf = classify("pypi", "pyproject.toml", None, "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_none_group_cargo(self):
        scope, conf = classify("cargo", "Cargo.toml", None, "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_none_group_unknown_ecosystem(self):
        scope, conf = classify("ruby", "Gemfile", None, "")
        assert scope == DependencyScope.UNKNOWN
        assert conf == ScopeConfidence.LOW

    def test_none_group_requirements(self):
        """requirements.txt classification uses source_file, not group."""
        scope, conf = classify(
            "pypi", "requirements.txt", None, "requirements.txt"
        )
        assert scope == DependencyScope.RUNTIME
        assert conf == ScopeConfidence.MEDIUM


class TestCaseInsensitivity:
    """Verify ecosystem and manifest matching is case-insensitive."""

    def test_npm_uppercase(self):
        scope, conf = classify("NPM", "package.json", "prod", "")
        assert scope == DependencyScope.RUNTIME

    def test_pypi_mixed_case(self):
        scope, conf = classify("PyPI", "pyproject.toml", "prod", "")
        assert scope == DependencyScope.RUNTIME

    def test_cargo_uppercase(self):
        scope, conf = classify("CARGO", "Cargo.toml", "prod", "")
        assert scope == DependencyScope.RUNTIME


class TestOptionalFlagInteraction:
    """Verify is_optional flag behavior in pyproject.toml classification."""

    def test_optional_in_dev_group_stays_dev(self):
        """is_optional=True but group='dev' → dev, not optional."""
        scope, conf = classify("pypi", "pyproject.toml", "dev", "", True)
        assert scope == DependencyScope.DEV
        assert conf == ScopeConfidence.HIGH

    def test_optional_in_test_group_stays_test(self):
        """is_optional=True but group='test' → test, not optional."""
        scope, conf = classify("pypi", "pyproject.toml", "test", "", True)
        assert scope == DependencyScope.TEST
        assert conf == ScopeConfidence.HIGH

    def test_optional_in_docs_group_stays_build(self):
        """is_optional=True but group='docs' → build, not optional."""
        scope, conf = classify("pypi", "pyproject.toml", "docs", "", True)
        assert scope == DependencyScope.BUILD
        assert conf == ScopeConfidence.MEDIUM

    def test_optional_in_custom_group_is_optional(self):
        """is_optional=True with non-dev/test/docs group → optional."""
        scope, conf = classify("pypi", "pyproject.toml", "viz", "", True)
        assert scope == DependencyScope.OPTIONAL
        assert conf == ScopeConfidence.HIGH
