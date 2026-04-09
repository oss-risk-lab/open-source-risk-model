"""Unit tests for the GET /api/demo-repos endpoint.

Tests cover:
- Returns enriched list with only validated repos
- Handles missing insights gracefully (risk_label null)
- DB unavailable fallback returns unenriched list from YAML

Requirements: 3.1, 3.2
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.app import app
from open_source_risk_model.config.demo_repos import DemoRepo, DemoRepoConfig
from open_source_risk_model.insights.models import RepoInsight

client = TestClient(app, raise_server_exceptions=False)


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_config(repos: list[DemoRepo]) -> DemoRepoConfig:
    return DemoRepoConfig(repos=repos)


SAMPLE_REPOS = [
    DemoRepo(repo="numpy/numpy", tags=["popular", "well-maintained"]),
    DemoRepo(repo="pallets/flask", tags=["popular"]),
    DemoRepo(repo="Marak/colors.js", tags=["high-risk"]),
]


def _make_insight(repo: str, score: float, label: str) -> RepoInsight:
    return RepoInsight(
        repo_full_name=repo,
        graph_signal_score=score,
        graph_signal_label=label,
    )


# ── Tests ─────────────────────────────────────────────────────────────


def test_returns_enriched_list_with_only_validated_repos():
    """Validated repos are returned with correct risk_label enrichment.

    Only repos that pass validate_demo_repos appear in the response,
    each enriched with the risk_label from compute_repo_insight.

    Validates: Requirements 3.1, 3.2
    """
    # Only numpy and flask pass validation (colors.js excluded)
    validated = [SAMPLE_REPOS[0], SAMPLE_REPOS[1]]

    insights = {
        "numpy/numpy": _make_insight("numpy/numpy", 0.1, "LOW"),
        "pallets/flask": _make_insight("pallets/flask", 0.7, "HIGH"),
    }

    mock_gr = MagicMock()

    def fake_compute(repo_name, gr):
        return insights[repo_name]

    with (
        patch("api.app.load_demo_repos", return_value=_make_config(SAMPLE_REPOS)),
        patch("api.app.validate_demo_repos", return_value=validated),
        patch("api.app.GraphRepository", return_value=mock_gr),
        patch("api.app.compute_repo_insight", side_effect=fake_compute),
    ):
        response = client.get("/api/demo-repos")

    assert response.status_code == 200
    data = response.json()
    repos = data["repos"]

    # Only validated repos returned (colors.js excluded)
    assert len(repos) == 2

    # Check first repo enrichment
    assert repos[0]["repo"] == "numpy/numpy"
    assert repos[0]["name"] == "numpy"
    assert repos[0]["owner"] == "numpy"
    assert repos[0]["tags"] == ["popular", "well-maintained"]
    assert repos[0]["risk_label"] == "LOW"

    # Check second repo enrichment
    assert repos[1]["repo"] == "pallets/flask"
    assert repos[1]["name"] == "flask"
    assert repos[1]["owner"] == "pallets"
    assert repos[1]["tags"] == ["popular"]
    assert repos[1]["risk_label"] == "HIGH"


def test_handles_missing_insights_gracefully():
    """When compute_repo_insight fails for a repo, risk_label is null.

    The endpoint should catch the exception and set risk_label to None
    rather than failing the entire response.

    Validates: Requirements 3.1, 3.2
    """
    validated = [SAMPLE_REPOS[0], SAMPLE_REPOS[1]]

    def fake_compute(repo_name, gr):
        if repo_name == "numpy/numpy":
            return _make_insight("numpy/numpy", 0.4, "MEDIUM")
        # Flask insight computation fails
        raise RuntimeError("DB read error")

    mock_gr = MagicMock()

    with (
        patch("api.app.load_demo_repos", return_value=_make_config(SAMPLE_REPOS)),
        patch("api.app.validate_demo_repos", return_value=validated),
        patch("api.app.GraphRepository", return_value=mock_gr),
        patch("api.app.compute_repo_insight", side_effect=fake_compute),
    ):
        response = client.get("/api/demo-repos")

    assert response.status_code == 200
    data = response.json()
    repos = data["repos"]

    assert len(repos) == 2

    # numpy got its insight
    assert repos[0]["risk_label"] == "MEDIUM"

    # flask failed — risk_label should be null
    assert repos[1]["risk_label"] is None


def test_db_unavailable_fallback_returns_unenriched_list():
    """When validate_demo_repos raises (DB unavailable), all YAML repos
    are returned with risk_label=null.

    The endpoint falls back to the full YAML config without enrichment.

    Validates: Requirements 3.1, 3.2
    """
    with (
        patch("api.app.load_demo_repos", return_value=_make_config(SAMPLE_REPOS)),
        patch(
            "api.app.validate_demo_repos",
            side_effect=Exception("Database is not available"),
        ),
    ):
        response = client.get("/api/demo-repos")

    assert response.status_code == 200
    data = response.json()
    repos = data["repos"]

    # All YAML repos returned (not just validated subset)
    assert len(repos) == 3

    # All have risk_label=null
    for repo_entry in repos:
        assert repo_entry["risk_label"] is None

    # Verify structure of each entry
    assert repos[0]["repo"] == "numpy/numpy"
    assert repos[0]["name"] == "numpy"
    assert repos[0]["owner"] == "numpy"
    assert repos[0]["tags"] == ["popular", "well-maintained"]

    assert repos[1]["repo"] == "pallets/flask"
    assert repos[1]["name"] == "flask"
    assert repos[1]["owner"] == "pallets"

    assert repos[2]["repo"] == "Marak/colors.js"
    assert repos[2]["name"] == "colors.js"
    assert repos[2]["owner"] == "Marak"
    assert repos[2]["tags"] == ["high-risk"]
