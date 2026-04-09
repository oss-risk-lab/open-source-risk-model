"""Integration tests for GET /api/insights/{owner}/{repo} endpoint."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app, _repo_exists_in_db
from open_source_risk_model.insights.models import RepoInsight, SignalEvidence


client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_insight(repo: str = "owner/repo", **kwargs) -> RepoInsight:
    """Build a RepoInsight with sensible defaults."""
    defaults = dict(
        repo_full_name=repo,
        graph_signal_score=0.4,
        graph_signal_label="MEDIUM",
        reasons=["2 CVE(s) found, including critical/high severity"],
        direct_signals=[
            SignalEvidence(
                signal_name="cve_risk",
                severity="high",
                score_contribution=0.4,
                reason="2 CVE(s) found, including critical/high severity",
            ),
            SignalEvidence(
                signal_name="maintainer_concentration",
                severity="info",
                score_contribution=0.0,
                reason="Maintainer concentration is healthy (30% top contributor)",
            ),
            SignalEvidence(
                signal_name="release_staleness",
                severity="info",
                score_contribution=0.0,
                reason="Last release was 10 days ago",
            ),
        ],
    )
    defaults.update(kwargs)
    return RepoInsight(**defaults)


def _default_insight(repo: str = "owner/repo") -> RepoInsight:
    """Build a default RepoInsight (no graph data)."""
    return RepoInsight(
        repo_full_name=repo,
        reasons=["No graph data available"],
    )


# ---------------------------------------------------------------------------
# 200 responses
# ---------------------------------------------------------------------------


class TestInsightsEndpoint200:
    """Tests for successful 200 responses."""

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight")
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_200_with_computed_insight(
        self, mock_graph_repo, mock_compute, mock_exists
    ):
        insight = _make_insight("test-owner/test-repo")
        mock_compute.return_value = insight

        resp = client.get("/api/insights/test-owner/test-repo")

        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_full_name"] == "test-owner/test-repo"
        assert data["graph_signal_score"] == 0.4
        assert data["graph_signal_label"] == "MEDIUM"
        assert len(data["direct_signals"]) == 3
        assert data["direct_signals"][0]["signal_name"] == "cve_risk"
        assert data["direct_signals"][1]["signal_name"] == "maintainer_concentration"
        assert data["direct_signals"][2]["signal_name"] == "release_staleness"

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight")
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_200_with_default_insight_no_graph_data(
        self, mock_graph_repo, mock_compute, mock_exists
    ):
        insight = _default_insight("owner/empty")
        mock_compute.return_value = insight

        resp = client.get("/api/insights/owner/empty")

        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_full_name"] == "owner/empty"
        assert data["graph_signal_score"] == 0.0
        assert data["graph_signal_label"] == "LOW"
        assert "No graph data available" in data["reasons"]
        assert data["direct_signals"] == []

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight")
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_200_response_includes_top_risky_dependencies(
        self, mock_graph_repo, mock_compute, mock_exists
    ):
        insight = _make_insight("owner/repo")
        mock_compute.return_value = insight

        resp = client.get("/api/insights/owner/repo")

        assert resp.status_code == 200
        data = resp.json()
        assert "top_risky_dependencies" in data
        assert data["top_risky_dependencies"] == []


# ---------------------------------------------------------------------------
# 404 response
# ---------------------------------------------------------------------------


class TestInsightsEndpoint404:
    """Tests for 404 responses when repo is not in DB."""

    @patch("api.app._repo_exists_in_db", return_value=False)
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_404_repo_not_found(self, mock_graph_repo, mock_exists):
        resp = client.get("/api/insights/nonexistent/repo")

        assert resp.status_code == 404
        data = resp.json()
        assert "nonexistent/repo" in data["detail"]


# ---------------------------------------------------------------------------
# 500 response
# ---------------------------------------------------------------------------


class TestInsightsEndpoint500:
    """Tests for 500 responses on unexpected errors."""

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight", side_effect=RuntimeError("boom"))
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_500_unexpected_error(
        self, mock_graph_repo, mock_compute, mock_exists
    ):
        resp = client.get("/api/insights/owner/repo")

        assert resp.status_code == 500
        data = resp.json()
        assert "Internal error" in data["detail"]


# ---------------------------------------------------------------------------
# 503 response — DB disabled
# ---------------------------------------------------------------------------


class TestInsightsEndpoint503:
    """Tests for 503 when graph_repo is None (DB disabled)."""

    @patch("api.app.graph_repo", None)
    def test_503_db_disabled(self):
        resp = client.get("/api/insights/owner/repo")

        assert resp.status_code == 503
        data = resp.json()
        assert "not available" in data["detail"]
