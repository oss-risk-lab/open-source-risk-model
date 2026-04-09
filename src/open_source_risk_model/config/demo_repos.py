"""Demo repository configuration loader and validator.

Loads curated demo repos from demo_repos.yaml and validates
each against the database for graph data, dependencies, and
computed insights.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..insights.compute import compute_repo_insight
from ..persistence.db import get_connection
from ..persistence.graph_repo import GraphRepository

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).parent / "demo_repos.yaml"


@dataclass
class DemoRepo:
    """A single demo repository entry."""
    repo: str            # "owner/repo"
    tags: list[str] = field(default_factory=list)


@dataclass
class DemoRepoConfig:
    """Container for the full demo repo configuration."""
    repos: list[DemoRepo] = field(default_factory=list)


def load_demo_repos() -> DemoRepoConfig:
    """Load and parse demo_repos.yaml from the config directory.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If the YAML content is invalid or unparseable.
    """
    if not _YAML_PATH.exists():
        raise FileNotFoundError(f"Demo repos config not found: {_YAML_PATH}")

    try:
        with open(_YAML_PATH, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in demo repos config: {exc}") from exc

    if not isinstance(data, dict) or "repos" not in data:
        raise ValueError("Demo repos config must contain a 'repos' key")

    repos: list[DemoRepo] = []
    for entry in data["repos"]:
        if not isinstance(entry, dict) or "repo" not in entry:
            raise ValueError(f"Each repo entry must have a 'repo' field, got: {entry}")
        repos.append(
            DemoRepo(
                repo=entry["repo"],
                tags=entry.get("tags", []),
            )
        )

    return DemoRepoConfig(repos=repos)


def validate_demo_repos(db_path: str) -> list[DemoRepo]:
    """Load demo repos and validate each against the database.

    Checks three conditions per repo:
      1. Exists in ``repo_graphs`` table
      2. Has at least one row in ``repo_dependencies`` table
      3. ``compute_repo_insight`` returns a non-null score

    Logs a warning for every repo that fails a check, identifying
    the repo name and the missing data category.

    Returns only repos passing ALL three checks.
    """
    config = load_demo_repos()
    conn = get_connection(db_path)
    graph_repo = GraphRepository(db_path)
    validated: list[DemoRepo] = []

    try:
        for demo in config.repos:
            repo_name = demo.repo
            passed = True

            # Check 1: exists in repo_graphs
            cursor = conn.execute(
                "SELECT 1 FROM repo_graphs WHERE repo_full_name = ?",
                (repo_name,),
            )
            if cursor.fetchone() is None:
                logger.warning("%s: missing graph data", repo_name)
                passed = False

            # Check 2: has entry in repo_dependencies
            cursor = conn.execute(
                "SELECT 1 FROM repo_dependencies WHERE repo_full_name = ?",
                (repo_name,),
            )
            if cursor.fetchone() is None:
                logger.warning("%s: missing dependencies data", repo_name)
                passed = False

            # Check 3: compute_repo_insight returns non-null score
            try:
                insight = compute_repo_insight(repo_name, graph_repo)
                if insight.graph_signal_score is None:
                    logger.warning("%s: missing insight score", repo_name)
                    passed = False
            except Exception:
                logger.warning("%s: missing insight score", repo_name)
                passed = False

            if passed:
                validated.append(demo)
    finally:
        conn.close()

    return validated
