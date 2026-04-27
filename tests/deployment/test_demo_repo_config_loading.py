"""Unit tests for demo repo config loading.

Tests valid YAML loading, error handling for missing/invalid files,
and validation of repo entries with valid/invalid tags and missing fields.

Requirements: 2.1, 2.2, 2.3
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from open_source_risk_model.config.demo_repos import (
    DemoRepo,
    DemoRepoConfig,
    load_demo_repos,
)


class TestLoadDemoReposValid:
    """Test successful loading of the actual YAML config."""

    def test_loads_actual_yaml_file(self):
        """load_demo_repos() returns a DemoRepoConfig from the real YAML file."""
        config = load_demo_repos()
        assert isinstance(config, DemoRepoConfig)

    def test_actual_yaml_has_19_repos(self):
        """The actual demo_repos.yaml contains exactly 19 repos."""
        config = load_demo_repos()
        assert len(config.repos) == 19

    def test_all_entries_are_demo_repo_instances(self):
        """Every entry in the loaded config is a DemoRepo."""
        config = load_demo_repos()
        for repo in config.repos:
            assert isinstance(repo, DemoRepo)

    def test_each_repo_has_owner_slash_name_format(self):
        """Every repo string follows the 'owner/repo' format."""
        config = load_demo_repos()
        for repo in config.repos:
            parts = repo.repo.split("/")
            assert len(parts) == 2, f"Expected owner/repo format, got: {repo.repo}"
            assert len(parts[0]) > 0
            assert len(parts[1]) > 0


class TestLoadDemoReposMissingFile:
    """Test that a missing YAML file raises FileNotFoundError."""

    def test_missing_file_raises_file_not_found(self, tmp_path):
        """When the YAML file doesn't exist, FileNotFoundError is raised."""
        fake_path = tmp_path / "nonexistent.yaml"
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", fake_path):
            with pytest.raises(FileNotFoundError):
                load_demo_repos()


class TestLoadDemoReposInvalidYAML:
    """Test that invalid YAML content raises ValueError."""

    def test_invalid_yaml_syntax_raises_value_error(self, tmp_path):
        """Malformed YAML raises ValueError."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("repos:\n  - repo: [unterminated")
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", bad_yaml):
            with pytest.raises(ValueError, match="Invalid YAML"):
                load_demo_repos()

    def test_yaml_without_repos_key_raises_value_error(self, tmp_path):
        """YAML that parses but lacks a 'repos' key raises ValueError."""
        no_repos = tmp_path / "no_repos.yaml"
        no_repos.write_text("something_else:\n  - foo\n")
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", no_repos):
            with pytest.raises(ValueError, match="must contain a 'repos' key"):
                load_demo_repos()

    def test_yaml_with_scalar_root_raises_value_error(self, tmp_path):
        """YAML that parses to a scalar (not a dict) raises ValueError."""
        scalar_yaml = tmp_path / "scalar.yaml"
        scalar_yaml.write_text("just a string\n")
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", scalar_yaml):
            with pytest.raises(ValueError, match="must contain a 'repos' key"):
                load_demo_repos()


class TestLoadDemoReposMissingRepoField:
    """Test that entries missing the 'repo' field raise ValueError."""

    def test_entry_without_repo_field_raises_value_error(self, tmp_path):
        """A repo entry missing the 'repo' key raises ValueError."""
        bad_entry = tmp_path / "missing_repo.yaml"
        bad_entry.write_text("repos:\n  - tags: ['popular']\n")
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", bad_entry):
            with pytest.raises(ValueError, match="must have a 'repo' field"):
                load_demo_repos()

    def test_entry_as_plain_string_raises_value_error(self, tmp_path):
        """A repo entry that is a plain string (not a dict) raises ValueError."""
        plain_str = tmp_path / "plain_string.yaml"
        plain_str.write_text("repos:\n  - numpy/numpy\n")
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", plain_str):
            with pytest.raises(ValueError, match="must have a 'repo' field"):
                load_demo_repos()


class TestLoadDemoReposTags:
    """Test that valid tags are accepted and loaded correctly."""

    ALLOWED_TAGS = {"high-risk", "deep-tree", "well-maintained", "popular", "vulnerable"}

    def test_actual_config_tags_are_from_allowed_set(self):
        """All tags in the actual YAML are from the allowed tag set."""
        config = load_demo_repos()
        for repo in config.repos:
            for tag in repo.tags:
                assert tag in self.ALLOWED_TAGS, (
                    f"Unexpected tag '{tag}' on repo {repo.repo}"
                )

    def test_tags_loaded_correctly(self, tmp_path):
        """Tags from YAML are loaded into the DemoRepo.tags list."""
        yaml_file = tmp_path / "tags.yaml"
        yaml_file.write_text(
            "repos:\n"
            "  - repo: owner/name\n"
            '    tags: ["high-risk", "popular"]\n'
        )
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", yaml_file):
            config = load_demo_repos()
        assert config.repos[0].tags == ["high-risk", "popular"]

    def test_missing_tags_defaults_to_empty_list(self, tmp_path):
        """A repo entry without tags gets an empty list."""
        yaml_file = tmp_path / "no_tags.yaml"
        yaml_file.write_text("repos:\n  - repo: owner/name\n")
        with patch("open_source_risk_model.config.demo_repos._YAML_PATH", yaml_file):
            config = load_demo_repos()
        assert config.repos[0].tags == []
