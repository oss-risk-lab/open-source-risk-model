"""
Unit tests for EntityNormalizer.

Tests specific examples, edge cases, and ambiguity handling.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.open_source_risk_model.ingestion.entity_normalizer import (
    EntityNormalizer,
    NormalizationResult,
)


class TestEntityNormalizerBasics:
    """Test basic entity normalization functionality."""

    def test_normalize_repository_exact_format(self):
        """Test normalizing repository in exact owner/repo format."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_repository("numpy/numpy")

        assert result == "numpy/numpy"

    def test_normalize_repository_already_normalized(self):
        """Test normalizing already normalized repository."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_repository("django/django")

        assert result == "django/django"

    def test_normalize_package_exact_repo_format(self):
        """Test normalizing package that's already in owner/repo format."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("numpy/numpy")

        assert result.canonical_identifier == "numpy/numpy"
        assert result.confidence == 1.0
        assert result.alternatives == []
        assert result.warning is None

    def test_normalize_package_with_ecosystem(self):
        """Test normalizing known package with ecosystem specified."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("numpy", "pypi")

        assert result.canonical_identifier == "numpy/numpy"
        assert result.confidence == 0.95
        assert result.alternatives == []
        assert result.warning is None

    def test_normalize_package_without_ecosystem_unique(self):
        """Test normalizing known package without ecosystem (unique match)."""
        normalizer = EntityNormalizer()

        # numpy should be unique to pypi
        result = normalizer.normalize_package("numpy")

        # Should find it with lower confidence
        assert result.canonical_identifier == "numpy/numpy"
        assert result.confidence == 0.80
        assert result.alternatives == []
        assert result.warning is not None
        assert "Inferred" in result.warning

    def test_normalize_unknown_package(self):
        """Test normalizing unknown package."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("totally-unknown-package-xyz")

        assert result.canonical_identifier is None
        assert result.confidence == 0.0
        assert result.alternatives == []
        assert result.warning is not None
        assert "Unknown package" in result.warning


class TestEntityNormalizerAmbiguity:
    """Test ambiguity handling in entity normalization."""

    def test_ambiguous_package_multiple_ecosystems(self):
        """Test handling package that exists in multiple ecosystems."""
        # Create a temporary mapping with ambiguous package
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "pypi": {"request": "psf/requests"},
                    "npm": {"request": "request/request"},
                },
                f,
            )
            temp_file = f.name

        try:
            normalizer = EntityNormalizer(temp_file)

            # Without ecosystem, should be ambiguous
            result = normalizer.normalize_package("request")

            assert result.canonical_identifier is None
            assert result.confidence == 0.0
            assert len(result.alternatives) == 2
            assert "psf/requests" in result.alternatives
            assert "request/request" in result.alternatives
            assert result.warning is not None
            assert "Ambiguous" in result.warning
            assert "multiple ecosystems" in result.warning
        finally:
            Path(temp_file).unlink()

    def test_ambiguous_package_with_ecosystem_resolves(self):
        """Test that specifying ecosystem resolves ambiguity."""
        # Create a temporary mapping with ambiguous package
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "pypi": {"request": "psf/requests"},
                    "npm": {"request": "request/request"},
                },
                f,
            )
            temp_file = f.name

        try:
            normalizer = EntityNormalizer(temp_file)

            # With ecosystem, should resolve
            result_pypi = normalizer.normalize_package("request", "pypi")
            result_npm = normalizer.normalize_package("request", "npm")

            assert result_pypi.canonical_identifier == "psf/requests"
            assert result_pypi.confidence == 0.95
            assert result_pypi.alternatives == []

            assert result_npm.canonical_identifier == "request/request"
            assert result_npm.confidence == 0.95
            assert result_npm.alternatives == []
        finally:
            Path(temp_file).unlink()

    def test_unknown_package_with_ecosystem(self):
        """Test unknown package with ecosystem specified."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("unknown-package", "pypi")

        assert result.canonical_identifier is None
        assert result.confidence == 0.0
        assert result.alternatives == []
        assert result.warning is not None
        assert "Unknown package" in result.warning
        assert "pypi" in result.warning


class TestEntityNormalizerMappings:
    """Test mapping file loading and usage."""

    def test_load_mappings_success(self):
        """Test loading mappings from YAML file."""
        # Create a temporary mapping file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "pypi": {"test-package": "test-org/test-repo"},
                    "npm": {"another-package": "another-org/another-repo"},
                },
                f,
            )
            temp_file = f.name

        try:
            normalizer = EntityNormalizer(temp_file)

            assert "pypi" in normalizer.mappings
            assert "npm" in normalizer.mappings
            assert normalizer.mappings["pypi"]["test-package"] == "test-org/test-repo"
            assert (
                normalizer.mappings["npm"]["another-package"]
                == "another-org/another-repo"
            )
        finally:
            Path(temp_file).unlink()

    def test_load_mappings_file_not_found(self):
        """Test loading mappings from non-existent file."""
        with pytest.raises(FileNotFoundError):
            EntityNormalizer("non-existent-file.yaml")

    def test_load_mappings_invalid_yaml(self):
        """Test loading mappings from invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_file = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                EntityNormalizer(temp_file)
        finally:
            Path(temp_file).unlink()

    def test_default_mapping_file(self):
        """Test that default mapping file is loaded if it exists."""
        # This test assumes config/package_repo_mappings.yaml exists
        default_path = Path("config/package_repo_mappings.yaml")
        if default_path.exists():
            normalizer = EntityNormalizer()

            # Should have loaded mappings
            assert len(normalizer.mappings) > 0
            assert "pypi" in normalizer.mappings
            assert "npm" in normalizer.mappings


class TestEntityNormalizerConfidenceThresholds:
    """Test confidence threshold behavior."""

    def test_confidence_exact_format(self):
        """Test confidence for exact owner/repo format."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("owner/repo")

        assert result.confidence == 1.0

    def test_confidence_ecosystem_mapping(self):
        """Test confidence for ecosystem mapping."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("numpy", "pypi")

        assert result.confidence == 0.95

    def test_confidence_inferred_mapping(self):
        """Test confidence for inferred mapping."""
        normalizer = EntityNormalizer()

        # numpy should be unique, so inferred confidence
        result = normalizer.normalize_package("numpy")

        if result.canonical_identifier:
            assert result.confidence == 0.80

    def test_confidence_unresolved(self):
        """Test confidence for unresolved package."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("unknown-package-xyz")

        assert result.confidence == 0.0


class TestEntityNormalizerEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_package_name(self):
        """Test normalizing empty package name."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("")

        # Should handle gracefully
        assert result.confidence == 0.0

    def test_package_name_with_special_characters(self):
        """Test normalizing package name with special characters."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("@scope/package")

        # Should handle gracefully (not in owner/repo format)
        assert result.confidence in [0.0, 0.80, 0.95]

    def test_case_sensitivity(self):
        """Test that normalization is case-sensitive."""
        normalizer = EntityNormalizer()

        result_lower = normalizer.normalize_package("numpy", "pypi")
        result_upper = normalizer.normalize_package("NUMPY", "pypi")

        # numpy exists, NUMPY doesn't
        assert result_lower.canonical_identifier == "numpy/numpy"
        assert result_upper.canonical_identifier is None

    def test_multiple_slashes_in_identifier(self):
        """Test handling identifier with multiple slashes."""
        normalizer = EntityNormalizer()

        result = normalizer.normalize_package("owner/repo/extra")

        # Should not match owner/repo pattern
        assert result.confidence in [0.0, 0.80]  # Either unknown or inferred

    def test_normalization_result_immutability(self):
        """Test that normalization results are independent."""
        normalizer = EntityNormalizer()

        result1 = normalizer.normalize_package("numpy", "pypi")
        result2 = normalizer.normalize_package("flask", "pypi")

        # Results should be independent
        assert result1.canonical_identifier != result2.canonical_identifier
        assert result1.canonical_identifier == "numpy/numpy"
        assert result2.canonical_identifier == "pallets/flask"


class TestEntityNormalizerRealWorldExamples:
    """Test real-world package normalization examples."""

    def test_python_packages(self):
        """Test normalizing common Python packages."""
        normalizer = EntityNormalizer()

        packages = [
            ("numpy", "numpy/numpy"),
            ("pandas", "pandas-dev/pandas"),
            ("flask", "pallets/flask"),
            ("django", "django/django"),
            ("requests", "psf/requests"),
            ("pytest", "pytest-dev/pytest"),
        ]

        for package, expected_repo in packages:
            result = normalizer.normalize_package(package, "pypi")
            assert result.canonical_identifier == expected_repo
            assert result.confidence == 0.95

    def test_javascript_packages(self):
        """Test normalizing common JavaScript packages."""
        normalizer = EntityNormalizer()

        packages = [
            ("react", "facebook/react"),
            ("vue", "vuejs/vue"),
            ("angular", "angular/angular"),
            ("express", "expressjs/express"),
            ("webpack", "webpack/webpack"),
        ]

        for package, expected_repo in packages:
            result = normalizer.normalize_package(package, "npm")
            assert result.canonical_identifier == expected_repo
            assert result.confidence == 0.95

    def test_rust_packages(self):
        """Test normalizing common Rust packages."""
        normalizer = EntityNormalizer()

        packages = [
            ("serde", "serde-rs/serde"),
            ("tokio", "tokio-rs/tokio"),
        ]

        for package, expected_repo in packages:
            result = normalizer.normalize_package(package, "cargo")
            assert result.canonical_identifier == expected_repo
            assert result.confidence == 0.95

    def test_cross_ecosystem_conflicts(self):
        """Test handling packages that might exist in multiple ecosystems."""
        normalizer = EntityNormalizer()

        # Test with ecosystem specified - should resolve
        result_pypi = normalizer.normalize_package("requests", "pypi")
        assert result_pypi.canonical_identifier == "psf/requests"
        assert result_pypi.confidence == 0.95

        # Test without ecosystem - should still work if unique
        result_no_eco = normalizer.normalize_package("requests")
        # requests is unique to pypi in our mappings
        assert result_no_eco.canonical_identifier == "psf/requests"
        assert result_no_eco.confidence == 0.80
