"""
Regression test: GraphBuilder must write dependency data to GRAPH_DB_PATH.

DependencyRepository and PackageMappingRepository both default to the
hardcoded relative path "data/graphs.db". GraphBuilder constructed them with
no db_path, so they ignored GRAPH_DB_PATH entirely.

This was invisible while the DB lived at the default location — both paths
were the same file. The moment the database moved to a mounted disk
(GRAPH_DB_PATH=/var/data/graphs.db on Render), the two diverged:

  - _parse_and_store_dependencies wrote rows to  data/graphs.db
  - /api/stats read dependency coverage from     /var/data/graphs.db

so analysis coverage silently reported 0% forever, with no error anywhere.
"""

import os

from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.schema import GraphConfig


def test_builder_db_path_follows_env(monkeypatch, tmp_path):
    """GraphBuilder.db_path must come from GRAPH_DB_PATH, not the default."""
    disk_db = os.path.join(tmp_path, "var-data", "graphs.db")
    monkeypatch.setenv("GRAPH_DB_PATH", disk_db)

    builder = GraphBuilder("psf/requests", {}, GraphConfig(parse_dependencies=False))
    assert builder.db_path == disk_db


def test_builder_defaults_when_env_unset(monkeypatch):
    """Without GRAPH_DB_PATH, fall back to the historical default."""
    monkeypatch.delenv("GRAPH_DB_PATH", raising=False)

    builder = GraphBuilder("psf/requests", {}, GraphConfig(parse_dependencies=False))
    assert builder.db_path == "data/graphs.db"


def test_dependency_repo_uses_configured_db_path(monkeypatch, tmp_path):
    """The dependency repository must target GRAPH_DB_PATH, not data/graphs.db.

    This is the assertion that would have caught the 0%-coverage bug.
    """
    disk_db = os.path.join(tmp_path, "var-data", "graphs.db")
    monkeypatch.setenv("GRAPH_DB_PATH", disk_db)

    builder = GraphBuilder("psf/requests", {}, GraphConfig(parse_dependencies=True))

    assert builder.dependency_repo is not None
    assert builder.dependency_repo.db_path == disk_db
    assert builder.dependency_repo.db_path != "data/graphs.db"
