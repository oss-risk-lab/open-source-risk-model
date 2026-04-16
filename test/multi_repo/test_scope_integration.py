"""Integration tests for multi-repo scope endpoints.

Tests full endpoint flows with mocked score_repo and build_graph,
including partial failure, dependency resolution, and summary generation.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from open_source_risk_model.graph.schema import Graph, Node, NodeType, Edge, EdgeType
from app import app, SCOPE_STORE

client = TestClient(app)


def _make_graph(repo_name: str, dep_label: str = None, cve_count: int = 0) -> Graph:
    """Build a minimal Graph with a repo node and optionally a package node."""
    g = Graph()
    g.add_node(Node(
        id=f"repo:{repo_name}",
        type=NodeType.REPO,
        label=repo_name,
        metadata={"risk_score": 0.5},
        provenance={"source": "test", "fetched_at": "2024-01-01T00:00:00Z"},
    ))
    if dep_label:
        g.add_node(Node(
            id=f"pkg:pypi/{dep_label}",
            type=NodeType.PACKAGE,
            label=dep_label,
            metadata={"risk_score": 0.4, "cve_count": cve_count},
            provenance={"source": "test", "fetched_at": "2024-01-01T00:00:00Z"},
        ))
        g.add_edge(Edge(
            source=f"repo:{repo_name}",
            target=f"pkg:pypi/{dep_label}",
            relationship_type=EdgeType.DEPENDS_ON,
            provenance={"source": "test", "fetched_at": "2024-01-01T00:00:00Z"},
        ))
    return g


@pytest.fixture(autouse=True)
def clear_scope_store():
    """Clear the in-memory scope store before each test."""
    SCOPE_STORE.clear()
    yield
    SCOPE_STORE.clear()


# ---- 1. Full endpoint flow: POST then GET, verify data consistency ----

@patch("app.build_graph")
@patch("app.score_repo")
def test_full_post_then_get_flow(mock_score, mock_build):
    """POST creates scope, GET retrieves same data."""
    mock_score.return_value = {"risk_score": 0.35, "repo": "alpha/one"}
    mock_build.return_value = _make_graph("alpha/one", dep_label="shared-lib")

    # POST to create scope
    post_resp = client.post("/api/ingest-scope", json={
        "name": "Integration Test",
        "repos": ["alpha/one"],
        "dependencies": [],
    })
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    scope_id = post_data["scope_id"]

    # GET to retrieve scope
    get_resp = client.get(f"/api/scope/{scope_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()

    # Core fields must match between POST and GET
    assert get_data["scope_id"] == scope_id
    assert get_data["status"] == post_data["status"]
    assert get_data["system_risk_summary"] == post_data["system_risk_summary"]
    assert get_data["priority_risks"] == post_data["priority_risks"]
    assert get_data["top_risk_drivers"] == post_data["top_risk_drivers"]
    assert get_data["graph"]["nodes"] == post_data["graph"]["nodes"]
    assert get_data["graph"]["edges"] == post_data["graph"]["edges"]


# ---- 2. Partial failure: one repo fails, others succeed ----

@patch("app.build_graph")
@patch("app.score_repo")
def test_partial_failure_status(mock_score, mock_build):
    """When one repo fails and another succeeds, status is 'partial'."""

    def _score_side_effect(repo, **kwargs):
        if repo == "fail/repo":
            raise RuntimeError("GitHub API error")
        return {"risk_score": 0.5, "repo": repo}

    def _build_side_effect(repo, score_data, config):
        return _make_graph(repo, dep_label="common-dep")

    mock_score.side_effect = _score_side_effect
    mock_build.side_effect = _build_side_effect

    resp = client.post("/api/ingest-scope", json={
        "name": "Partial Scope",
        "repos": ["good/repo", "fail/repo"],
        "dependencies": [],
    })
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "partial"

    # Errors dict should contain the failed repo
    assert "fail/repo" in data["errors"]
    assert "GitHub API error" in data["errors"]["fail/repo"]

    # system_risk_summary should still have per_repo_results for both
    per_repo = data["system_risk_summary"]["per_repo_results"]
    assert len(per_repo) == 2

    good = next(r for r in per_repo if r["repo"] == "good/repo")
    assert good["error"] is None
    assert good["risk_score"] is not None

    failed = next(r for r in per_repo if r["repo"] == "fail/repo")
    assert failed["error"] is not None


# ---- 3. Dependency resolution: mixed mapped/unmapped ----

@patch("app.build_graph")
@patch("app.score_repo")
def test_dependency_resolution_mixed(mock_score, mock_build):
    """Mapped deps go through pipeline; unmapped become graph-only nodes."""
    mock_score.return_value = {"risk_score": 0.4, "repo": "pallets/flask"}
    mock_build.return_value = _make_graph("pallets/flask", dep_label="werkzeug")

    resp = client.post("/api/ingest-scope", json={
        "name": "Dep Test",
        "repos": [],
        "dependencies": ["flask", "some-unknown-pkg"],
    })
    assert resp.status_code == 200
    data = resp.json()

    graph_nodes = data["graph"]["nodes"]
    node_ids = [n["id"] for n in graph_nodes]

    # "flask" is mapped to pallets/flask → should have repo node from pipeline
    assert any("pallets/flask" in nid for nid in node_ids)

    # "some-unknown-pkg" is unmapped → should appear as pkg:some-unknown-pkg
    assert "pkg:some-unknown-pkg" in node_ids

    # The unmapped node should be type "package"
    unmapped = next(n for n in graph_nodes if n["id"] == "pkg:some-unknown-pkg")
    assert unmapped["type"] == "package"
    assert unmapped["label"] == "some-unknown-pkg"


# ---- 4. System summary sentence generation ----

@patch("app.build_graph")
@patch("app.score_repo")
def test_system_summary_sentence(mock_score, mock_build):
    """System summary sentence contains expected keywords."""
    mock_score.return_value = {"risk_score": 0.25, "repo": "test/repo"}
    mock_build.return_value = _make_graph("test/repo", dep_label="safe-lib")

    resp = client.post("/api/ingest-scope", json={
        "name": "Summary Test",
        "repos": ["test/repo"],
        "dependencies": [],
    })
    assert resp.status_code == 200
    data = resp.json()

    summary = data["system_risk_summary"]
    sentence = summary.get("system_summary", "")

    # Should mention risk level and repo count
    assert "risk" in sentence.lower()
    assert "1" in sentence or "repositor" in sentence.lower()
