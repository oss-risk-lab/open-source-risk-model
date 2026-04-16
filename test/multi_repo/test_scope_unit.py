"""Unit tests for multi-repo scope endpoints and helper functions.

Tests POST /api/ingest-scope, GET /api/scope/{scope_id}, compute_priority_risks,
and resolve_dependency_input using FastAPI TestClient with mocked pipelines.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from open_source_risk_model.graph.schema import Graph, Node, NodeType, Edge, EdgeType
from app import (
    app,
    SCOPE_STORE,
    PACKAGE_TO_REPO,
    SEVERITY_BASE,
    compute_priority_risks,
    resolve_dependency_input,
)

client = TestClient(app)


def _make_mock_graph(repo_name: str) -> Graph:
    """Create a minimal valid Graph object for mocking."""
    g = Graph()
    g.add_node(Node(
        id=f"repo:{repo_name}",
        type=NodeType.REPO,
        label=repo_name,
        metadata={"risk_score": 0.45},
        provenance={"source": "test", "fetched_at": "2024-01-01T00:00:00Z"},
    ))
    g.add_node(Node(
        id=f"pkg:pypi/dep-{repo_name.replace('/', '-')}",
        type=NodeType.PACKAGE,
        label=f"dep-{repo_name.replace('/', '-')}",
        metadata={"risk_score": 0.3, "cve_count": 0},
        provenance={"source": "test", "fetched_at": "2024-01-01T00:00:00Z"},
    ))
    g.add_edge(Edge(
        source=f"repo:{repo_name}",
        target=f"pkg:pypi/dep-{repo_name.replace('/', '-')}",
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


# ---- 1. POST returns 200 with valid input and response matches schema ----

@patch("app.build_graph")
@patch("app.score_repo")
def test_post_ingest_scope_valid_input(mock_score, mock_build):
    """POST /api/ingest-scope with valid repos returns 200 and correct schema."""
    mock_score.return_value = {"risk_score": 0.45, "repo": "owner/repo"}
    mock_build.return_value = _make_mock_graph("owner/repo")

    resp = client.post("/api/ingest-scope", json={
        "name": "Test Scope",
        "repos": ["owner/repo"],
        "dependencies": [],
    })

    assert resp.status_code == 200
    data = resp.json()

    # Verify all required top-level fields exist
    required_fields = {
        "scope_id", "status", "system_risk_summary",
        "priority_risks", "top_risk_drivers",
        "top_risky_dependencies", "graph", "errors",
    }
    assert required_fields.issubset(set(data.keys())), (
        f"Missing fields: {required_fields - set(data.keys())}"
    )

    assert isinstance(data["scope_id"], str)
    assert data["status"] in ("complete", "partial", "failed")
    assert isinstance(data["system_risk_summary"], dict)
    assert isinstance(data["priority_risks"], list)
    assert isinstance(data["top_risk_drivers"], list)
    assert isinstance(data["top_risky_dependencies"], list)
    assert isinstance(data["graph"], dict)
    assert "nodes" in data["graph"]
    assert "edges" in data["graph"]
    assert isinstance(data["errors"], dict)


# ---- 2. POST returns 422 for empty input ----

def test_post_ingest_scope_empty_input():
    """POST /api/ingest-scope with empty repos and dependencies returns 422."""
    resp = client.post("/api/ingest-scope", json={
        "name": "Empty Scope",
        "repos": [],
        "dependencies": [],
    })
    assert resp.status_code == 422


# ---- 3. POST returns 422 for >10 repos ----

def test_post_ingest_scope_too_many_repos():
    """POST /api/ingest-scope with >10 repos returns 422."""
    repos = [f"owner/repo{i}" for i in range(11)]
    resp = client.post("/api/ingest-scope", json={
        "name": "Big Scope",
        "repos": repos,
        "dependencies": [],
    })
    assert resp.status_code == 422


# ---- 4. GET returns 404 for unknown scope_id ----

def test_get_scope_unknown_id():
    """GET /api/scope/{scope_id} with unknown ID returns 404."""
    resp = client.get("/api/scope/scope_nonexistent_id")
    assert resp.status_code == 404


# ---- 5. Priority score formula correctness ----

def test_priority_score_formula():
    """compute_priority_risks produces scores matching the documented formula."""
    per_repo_results = [
        {"repo": "owner/high-risk", "risk_score": 0.75, "risk_label": "HIGH", "error": None},
    ]
    merged_graph = {
        "nodes": [
            {
                "id": "pkg:pypi/vuln-dep",
                "type": "package",
                "label": "vuln-dep",
                "metadata": {"risk_score": 0.8, "cve_count": 3},
                "source_repos": ["owner/high-risk", "owner/other"],
            },
        ],
        "edges": [],
    }

    risks = compute_priority_risks(per_repo_results, merged_graph)

    # The high-risk repo should be a candidate
    repo_risk = next((r for r in risks if r["name"] == "owner/high-risk"), None)
    if repo_risk:
        # severity=high, usage_count=0, cve_count=0
        expected = SEVERITY_BASE["high"] + (0 * 0.5) + (0 * 1.0)
        assert repo_risk["priority_score"] == expected

    # The vuln-dep should be a candidate (CVE source: cve_count=3 → severity=high)
    dep_risk = next((r for r in risks if r["name"] == "vuln-dep"), None)
    assert dep_risk is not None
    # cve_count=3 → severity=high, usage_count=2
    expected_cve = SEVERITY_BASE["high"] + (2 * 0.5) + (3 * 1.0)
    # Also a multi-repo candidate: severity=medium, usage_count=2, cve_count=3
    expected_multi = SEVERITY_BASE["medium"] + (2 * 0.5) + (3 * 1.0)
    # The higher score wins due to deduplication
    assert dep_risk["priority_score"] == max(expected_cve, expected_multi)


# ---- 6. Dependency resolution: mapped → full pipeline, unmapped → graph-only ----

def test_resolve_dependency_mapped():
    """resolve_dependency_input returns repo mapping for known packages."""
    for pkg, repo in PACKAGE_TO_REPO.items():
        result = resolve_dependency_input(pkg)
        assert result["kind"] == "repo"
        assert result["repo"] == repo
        assert result["package_name"] == pkg
        assert result["mapped"] is True


def test_resolve_dependency_unmapped():
    """resolve_dependency_input returns package-only for unknown packages."""
    result = resolve_dependency_input("totally-unknown-package-xyz")
    assert result["kind"] == "package_only"
    assert result["repo"] is None
    assert result["package_name"] == "totally-unknown-package-xyz"
    assert result["mapped"] is False
