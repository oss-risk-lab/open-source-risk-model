"""
Configuration loader for ingestion system.

Loads and validates configuration from YAML files with sensible defaults.
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class IngestionConfig:
    """Configuration for GitHub API ingestion system."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config file. If None, uses default location.
        """
        if config_path is None:
            # Default to config/ingestion_config.yaml relative to project root
            config_path = self._find_config_file()

        self.config = self._load_config(config_path)

    def _find_config_file(self) -> str:
        """Find the default config file location."""
        # Try multiple possible locations
        possible_paths = [
            "config/ingestion_config.yaml",
            "../config/ingestion_config.yaml",
            "../../config/ingestion_config.yaml",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        # If not found, return default path (will use defaults)
        return "config/ingestion_config.yaml"

    def _load_config(self, config_path: str) -> dict[str, Any]:
        """Load configuration from YAML file with defaults."""
        defaults = self._get_defaults()

        if not os.path.exists(config_path):
            return defaults

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
                # Merge with defaults
                return self._merge_configs(defaults, config or {})
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
            return defaults

    def _get_defaults(self) -> dict[str, Any]:
        """Get default configuration values."""
        return {
            "graphql": {
                "initial_batch_size": 10,
                "min_batch_size": 1,
                "max_batch_size": 30,
                "batch_size_increase_factor": 1.2,
                "batch_size_decrease_factor": 0.5,
                "timeout_seconds": 30,
                "track_query_costs": True,
            },
            "rest": {
                "timeout_seconds": 30,
                "max_pages_per_request": 10,
            },
            "rate_limiting": {
                "warning_threshold": 100,
                "rest_limit": 5000,
                "graphql_limit": 5000,
            },
            "caching": {
                "ttl_seconds": 3600,
                "cache_dir": "data/github_cache",
                "enable_disk_persistence": True,
            },
            "ingestion": {
                "default_mode": "full",
                "retry_attempts": 3,
                "retry_backoff_base": 2,
                "retry_max_wait": 60,
                "progress_report_interval": 10,
            },
            "features": {
                "minimum_coverage_threshold": 0.6,
            },
            "persistence": {
                "live_ingestion_mode": "cache",
                "auto_promote_to_database": False,
            },
            "entity_normalization": {
                "mapping_file": "config/package_repo_mappings.yaml",
            },
            "mvp_scope": {
                "enable_deep_issue_enrichment": False,
                "max_issues_per_repo": 100,
                "enable_hybrid_comparison": True,
            },
        }

    def _merge_configs(
        self, defaults: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        """Recursively merge config with defaults."""
        result = defaults.copy()
        for key, value in config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get configuration value by nested keys.

        Args:
            *keys: Nested keys to traverse (e.g., 'graphql', 'initial_batch_size')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


class PackageMappingConfig:
    """Configuration for package-to-repo mappings."""

    def __init__(self, mapping_path: Optional[str] = None):
        """
        Load package mappings from YAML file.

        Args:
            mapping_path: Path to mapping file. If None, uses default location.
        """
        if mapping_path is None:
            mapping_path = self._find_mapping_file()

        self.mappings = self._load_mappings(mapping_path)

    def _find_mapping_file(self) -> str:
        """Find the default mapping file location."""
        possible_paths = [
            "config/package_repo_mappings.yaml",
            "../config/package_repo_mappings.yaml",
            "../../config/package_repo_mappings.yaml",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        return "config/package_repo_mappings.yaml"

    def _load_mappings(self, mapping_path: str) -> dict[str, dict[str, str]]:
        """Load package mappings from YAML file."""
        if not os.path.exists(mapping_path):
            return {}

        try:
            with open(mapping_path, "r") as f:
                mappings = yaml.safe_load(f)
                return mappings or {}
        except Exception as e:
            print(f"Warning: Failed to load mappings from {mapping_path}: {e}")
            return {}

    def get_repo(self, package_name: str, ecosystem: Optional[str] = None) -> Optional[str]:
        """
        Get repository identifier for a package.

        Args:
            package_name: Package name to look up
            ecosystem: Ecosystem (pypi, npm, maven, cargo). If None, searches all.

        Returns:
            Repository identifier (owner/repo) or None if not found
        """
        if ecosystem:
            return self.mappings.get(ecosystem, {}).get(package_name)

        # Search all ecosystems
        for eco_mappings in self.mappings.values():
            if package_name in eco_mappings:
                return eco_mappings[package_name]

        return None

    def get_all_for_ecosystem(self, ecosystem: str) -> dict[str, str]:
        """Get all mappings for a specific ecosystem."""
        return self.mappings.get(ecosystem, {})
