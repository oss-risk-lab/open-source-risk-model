"""
Regression tests for scan-on-miss behavior of the insights endpoint.

The homepage "Scan a Repository" button navigates to the insights detail view,
which calls GET /api/insights/{owner}/{repo}. Previously that endpoint was
compute-only and returned 404 for any repo not already in the DB — so on fresh
deploys (Render recreates the DB each deploy) scanning any repo failed.

get_repo_insights now ingests on demand when the repo is missing, then computes.
"""

import os

import pytest

import api.app as app
from api.app import GraphRepository
from src.open_source_risk_model.persistence.db import init_database


@pytest.fixture
def wired_graph_repo(tmp_path, monkeypatch):
    """Point the app at a fresh, empty DB (mirrors a fresh deploy)."""
    db_path = os.path.join(tmp_path, "graphs.db")
    init_database(db_path)
    monkeypatch.setattr(app, "graph_repo", GraphRepository(db_path=db_path))
    monkeypatch.setenv("GRAPH_DB_PATH", db_path)
    return db_path


def test_missing_repo_triggers_on_demand_ingest(wired_graph_repo, monkeypatch):
    """A repo not in the DB must trigger _ingest_repo_on_demand, not 404 outright."""
    calls = []

    def fake_ingest(repo_full_name):
        calls.append(repo_full_name)  # simulate ingest that finds nothing to persist

    monkeypatch.setattr(app, "_ingest_repo_on_demand", fake_ingest)

    with pytest.raises(app.HTTPException) as exc:
        app.get_repo_insights("psf", "requests")

    # Ingest was attempted; only after it still-missing do we 404.
    assert calls == ["psf/requests"]
    assert exc.value.status_code == 404


def test_ingested_repo_is_computed_without_reingest(wired_graph_repo, monkeypatch):
    """After on-demand ingest persists the repo, the insight is computed and returned."""
    from src.open_source_risk_model.graph.schema import Graph, Node, NodeType
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    def fake_ingest(repo_full_name):
        # Simulate a successful scan by persisting a minimal graph.
        node = Node(
            id=f"repo:{repo_full_name}",
            type=NodeType.REPO,
            label=repo_full_name,
            metadata={"url": f"https://github.com/{repo_full_name}"},
            provenance={"source": "github_api", "fetched_at": now, "data_confidence": 1.0},
        )
        graph = Graph(nodes=[node], edges=[], metadata={"schema_version": "1.0", "generated_at": now})
        app.graph_repo.save_graph(repo_full_name, graph, generation_time_ms=1)

    monkeypatch.setattr(app, "_ingest_repo_on_demand", fake_ingest)

    result = app.get_repo_insights("psf", "requests")
    assert result["repo_full_name"] == "psf/requests"
