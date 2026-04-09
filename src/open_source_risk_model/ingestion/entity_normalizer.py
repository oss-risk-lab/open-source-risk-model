"""
Entity normalization for repository and package identifiers.

Implements strict rule hierarchy for normalizing package names to repository identifiers:
1. Exact owner/repo format (confidence: 1.0)
2. Exact package mapping by ecosystem from YAML (confidence: 0.95)
3. Inferred mapping from aliases (confidence: 0.80)
4. Unresolved entity warning (confidence: 0.0)
"""

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class NormalizationResult(BaseModel):
    """Result of entity normalization."""

    canonical_identifier: Optional[str] = Field(
        None, description="Normalized repo identifier"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in normalization"
    )
    alternatives: list[str] = Field(
        default_factory=list, description="Alternative mappings if ambiguous"
    )
    warning: Optional[str] = Field(
        None, description="Warning message if unresolved or ambiguous"
    )


class EntityNormalizer:
    """
    Normalizes entity identifiers to canonical forms with explicit precedence rules.

    Rule hierarchy (strict precedence):
    1. Exact owner/repo format (confidence: 1.0)
    2. Exact package mapping by ecosystem from YAML (confidence: 0.95)
    3. Inferred mapping from aliases (confidence: 0.80)
    4. Unresolved entity warning (confidence: 0.0)
    """

    # Regex pattern for valid owner/repo format
    # GitHub allows alphanumeric, hyphens, and underscores
    # Owner: 1-39 chars, Repo: 1-100 chars
    REPO_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,38}/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")

    def __init__(self, mapping_file: Optional[str] = None):
        """
        Initialize entity normalizer.

        Args:
            mapping_file: Path to package-to-repo mapping YAML file.
                         Defaults to config/package_repo_mappings.yaml
        """
        self.mappings: dict[str, dict[str, str]] = {}
        if mapping_file:
            self.load_mappings(mapping_file)
        else:
            # Try default location
            default_path = Path("config/package_repo_mappings.yaml")
            if default_path.exists():
                self.load_mappings(str(default_path))

    def load_mappings(self, mapping_file: str) -> None:
        """
        Load package-to-repo mapping table from YAML file.

        Args:
            mapping_file: Path to YAML file containing mappings

        Raises:
            FileNotFoundError: If mapping file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        path = Path(mapping_file)
        if not path.exists():
            raise FileNotFoundError(f"Mapping file not found: {mapping_file}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        # Store mappings by ecosystem
        self.mappings = {}
        for ecosystem, packages in data.items():
            if isinstance(packages, dict) and ecosystem not in [
                "Ambiguity resolution strategy"
            ]:
                self.mappings[ecosystem] = packages

    def normalize_repository(self, repo_ref: str) -> str:
        """
        Normalize repository reference to owner/repo format.

        Args:
            repo_ref: Repository reference (may already be in owner/repo format)

        Returns:
            Normalized repository identifier in owner/repo format

        Examples:
            >>> normalizer.normalize_repository("numpy/numpy")
            "numpy/numpy"
            >>> normalizer.normalize_repository("django/django")
            "django/django"
        """
        # Rule 1: Already in exact owner/repo format
        if self.REPO_PATTERN.match(repo_ref):
            return repo_ref

        # If not in owner/repo format, return as-is
        # (caller should use normalize_package for package names)
        return repo_ref

    def normalize_package(
        self, package_name: str, ecosystem: Optional[str] = None
    ) -> NormalizationResult:
        """
        Normalize package name to repository identifier with confidence.

        Applies strict rule hierarchy:
        1. Exact owner/repo format (confidence: 1.0)
        2. Exact package mapping by ecosystem (confidence: 0.95)
        3. Inferred mapping from aliases (confidence: 0.80)
        4. Unresolved entity warning (confidence: 0.0)

        Args:
            package_name: Package name to normalize
            ecosystem: Optional ecosystem (pypi, npm, maven, cargo)

        Returns:
            NormalizationResult with canonical identifier and confidence

        Examples:
            >>> normalizer.normalize_package("numpy", "pypi")
            NormalizationResult(canonical_identifier="numpy/numpy", confidence=0.95, ...)

            >>> normalizer.normalize_package("numpy/numpy")
            NormalizationResult(canonical_identifier="numpy/numpy", confidence=1.0, ...)

            >>> normalizer.normalize_package("unknown-package")
            NormalizationResult(canonical_identifier=None, confidence=0.0, warning="...", ...)
        """
        # Rule 1: Exact owner/repo format (highest priority)
        if self.REPO_PATTERN.match(package_name):
            return NormalizationResult(
                canonical_identifier=package_name,
                confidence=1.0,
                alternatives=[],
                warning=None,
            )

        # Rule 2: Exact package mapping by ecosystem (from YAML)
        if ecosystem and ecosystem in self.mappings:
            if package_name in self.mappings[ecosystem]:
                return NormalizationResult(
                    canonical_identifier=self.mappings[ecosystem][package_name],
                    confidence=0.95,
                    alternatives=[],
                    warning=None,
                )

        # Rule 3: Inferred mapping from known repo/package aliases
        # Check if package name exists uniquely across all ecosystems
        if not ecosystem:
            matches = self._find_across_ecosystems(package_name)

            if len(matches) == 1:
                # Unique match across all ecosystems
                ecosystem_name, repo = matches[0]
                return NormalizationResult(
                    canonical_identifier=repo,
                    confidence=0.80,
                    alternatives=[],
                    warning=f"Inferred from {ecosystem_name} ecosystem (no ecosystem specified)",
                )
            elif len(matches) > 1:
                # Ambiguous - exists in multiple ecosystems
                repos = [repo for _, repo in matches]
                ecosystems = [eco for eco, _ in matches]
                return NormalizationResult(
                    canonical_identifier=None,
                    confidence=0.0,
                    alternatives=repos,
                    warning=f"Ambiguous: '{package_name}' exists in multiple ecosystems: {', '.join(ecosystems)}. Please specify ecosystem.",
                )

        # Rule 4: Unresolved entity warning (lowest priority)
        return NormalizationResult(
            canonical_identifier=None,
            confidence=0.0,
            alternatives=[],
            warning=f"Unknown package: '{package_name}'"
            + (f" in ecosystem '{ecosystem}'" if ecosystem else ""),
        )

    def _find_across_ecosystems(
        self, package_name: str
    ) -> list[tuple[str, str]]:
        """
        Find package across all ecosystems.

        Args:
            package_name: Package name to search for

        Returns:
            List of (ecosystem, repo_identifier) tuples
        """
        matches = []
        for ecosystem, packages in self.mappings.items():
            if package_name in packages:
                matches.append((ecosystem, packages[package_name]))
        return matches
