"""
Integration tests for scope-weighted risk API responses.

Feature: scope-weighted-risk
Task 8.3: Write integration tests for API responses

Requirements: 7.1–7.4
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from src.open_source_risk_model.tree.models import (
    DependencyTreeResponse,
    ProvenanceInfo,
    RiskMetadata,
    SummaryMetrics,
    TreeNode,
)


@pytest.fixture()
def client():
    """Create a FastAPI TestClient."""
    return TestClient(app)


# ======================================================================
# Helpers — build mock responses
# ======================================================================


def _make_tree_response_with_scope_metrics() -> DependencyTreeResponse:
    """Build a DependencyTreeResponse with Phase 4 exposure fields populated."""
    root = TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        depth=0,
        dependency_type="direct",
        children=[
            TreeNode(
                id="pypi:requests:2.31.0",
                node_type="package",
                name="requests",
                version="2.31.0",
                depth=1,
                dependency_type="direct",
                ecosystem="pypi",
                dependency_scope="runtime",
                scope_confidence="high",
                risk_metadata=RiskMetadata(
                    risk_score=45.0,
                    risk_level="medium",
                    vulnerability_count=1,
                    score_source="repo_graph",
                    score_completeness="full",
                ),
            ),
        ],
    )
    metrics = SummaryMetrics(
        total_dependencies=1,
        direct_dependencies=1,
        transitive_dependencies=0,
        high_risk_count=0,
        vulnerable_count=1,
        max_depth=1,
        # Phase 4 fields
        runtime_dependency_exposure=1.0,
        transitive_runtime_dependency_exposure=0.0,
        scope_weighted_dependency_exposure=1.0,
        vulnerable_runtime_dependency_count=1,
        vulnerable_transitive_runtime_dependency_count=0,
        high_risk_runtime_dependency_count=0,
        unknown_scope_dependency_ratio=0.0,
    )
    provenance = ProvenanceInfo(
        data_source="database",
        data_completeness="full",
        last_updated="2025-01-01T00:00:00Z",
        total_nodes=2,
        nodes_with_risk_data=1,
        nodes_with_missing_risk=1,
    )
    return DependencyTreeResponse(
        repo="owner/repo",
        tree=root,
        summary_metrics=metrics,
        provenance=provenance,
    )


def _make_insight_graph_with_scope_data() -> dict:
    """Build graph data that produces scope_weighted_risk in insights."""
    return {
        "graph": {
            "nodes": [
                {
                    "type": "repo",
                    "metadata": {
                        "maintenance_risk": 0.4,
                        "maintenance_label": "MEDIUM",
                    },
                },
                {
                    "type": "cve",
                    "metadata": {
                        "cve_id": "CVE-2024-001",
                        "severity": "AV:N/AC:L",
                        "cvss_score": 7.5,
                    },
                },
                {
                    "type": "maintainer",
                    "metadata": {
                        "username": "dev1",
                        "contribution_fraction": 0.6,
                    },
                },
                {
                    "type": "release",
                    "metadata": {
                        "is_latest": True,
                        "tag_name": "v1.0",
                        "days_ago": 30,
                    },
                },
                {
                    "type": "package",
                    "label": "requests",
                    "metadata": {
                        "package_name": "requests",
                        "dependency_scope": "runtime",
                        "scope_confidence": "high",
                        "vulnerability_count": 1,
                        "risk_score": 60.0,
                        "depth": 1,
                    },
                },
                {
                    "type": "package",
                    "label": "pytest",
                    "metadata": {
                        "package_name": "pytest",
                        "dependency_scope": "test",
                        "scope_confidence": "high",
                        "vulnerability_count": 0,
                        "risk_score": 10.0,
                        "depth": 1,
                    },
                },
            ],
        }
    }


def _make_insight_graph_without_scope_data() -> dict:
    """Build graph data with no package nodes (no scope data)."""
    return {
        "graph": {
            "nodes": [
                {
                    "type": "repo",
                    "metadata": {
                        "maintenance_risk": 0.2,
                        "maintenance_label": "LOW",
                    },
                },
            ],
        }
    }


# ======================================================================
# Test 1: /repos/{repo}/dependency-tree returns new exposure fields
# Validates: Requirement 7.1
# ======================================================================


class TestDependencyTreeExposureFields:
    """Test that the dependency tree API response includes Phase 4 exposure fields."""

    EXPOSURE_FIELDS = [
        "runtime_dependency_exposure",
        "transitive_runtime_dependency_exposure",
        "scope_weighted_dependency_exposure",
        "vulnerable_runtime_dependency_count",
        "vulnerable_transitive_runtime_dependency_count",
        "high_risk_runtime_dependency_count",
        "unknown_scope_dependency_ratio",
    ]

    @patch("api.app.TreeService")
    def test_dependency_tree_returns_exposure_fields(self, mock_tree_cls, client):
        """summary_metrics SHALL contain all 7 Phase 4 exposure fields (Req 7.1)."""
        mock_service = MagicMock()
        mock_service.get_dependency_tree.return_value = (
            _make_tree_response_with_scope_metrics()
        )
        mock_tree_cls.return_value = mock_service

        resp = client.get("/repos/owner/repo/dependency-tree")
        assert resp.status_code == 200

        data = resp.json()
        summary = data["summary_metrics"]

        for field_name in self.EXPOSURE_FIELDS:
            assert field_name in summary, (
                f"Missing field '{field_name}' in summary_metrics"
            )

    @patch("api.app.TreeService")
    def test_exposure_field_types(self, mock_tree_cls, client):
        """Exposure ratio fields SHALL be floats; count fields SHALL be ints."""
        mock_service = MagicMock()
        mock_service.get_dependency_tree.return_value = (
            _make_tree_response_with_scope_metrics()
        )
        mock_tree_cls.return_value = mock_service

        resp = client.get("/repos/owner/repo/dependency-tree")
        summary = resp.json()["summary_metrics"]

        # Ratio fields → float
        assert isinstance(summary["runtime_dependency_exposure"], (int, float))
        assert isinstance(summary["transitive_runtime_dependency_exposure"], (int, float))
        assert isinstance(summary["scope_weighted_dependency_exposure"], (int, float))
        assert isinstance(summary["unknown_scope_dependency_ratio"], (int, float))

        # Count fields → int
        assert isinstance(summary["vulnerable_runtime_dependency_count"], int)
        assert isinstance(summary["vulnerable_transitive_runtime_dependency_count"], int)
        assert isinstance(summary["high_risk_runtime_dependency_count"], int)

    @patch("api.app.TreeService")
    def test_existing_summary_fields_still_present(self, mock_tree_cls, client):
        """Existing summary_metrics fields SHALL remain present (Req 8.3)."""
        mock_service = MagicMock()
        mock_service.get_dependency_tree.return_value = (
            _make_tree_response_with_scope_metrics()
        )
        mock_tree_cls.return_value = mock_service

        resp = client.get("/repos/owner/repo/dependency-tree")
        summary = resp.json()["summary_metrics"]

        existing_fields = [
            "total_dependencies",
            "direct_dependencies",
            "transitive_dependencies",
            "high_risk_count",
            "vulnerable_count",
            "max_depth",
        ]
        for field_name in existing_fields:
            assert field_name in summary, (
                f"Existing field '{field_name}' missing from summary_metrics"
            )


# ======================================================================
# Test 2: /api/insights/{owner}/{repo} returns scope_weighted_risk
# Validates: Requirement 7.2
# ======================================================================


class TestInsightsEndpointScopeWeightedRisk:
    """Test that the insights API response includes scope_weighted_risk."""

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight")
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_insights_returns_scope_weighted_risk(
        self, mock_graph_repo, mock_compute, mock_exists, client
    ):
        """Response SHALL contain scope_weighted_risk with all required sub-fields (Req 7.2)."""
        from open_source_risk_model.insights.models import RepoInsight

        insight = RepoInsight(
            repo_full_name="owner/repo",
            base_maintenance_risk=0.4,
            base_maintenance_label="MEDIUM",
            graph_signal_score=0.3,
            graph_signal_label="MEDIUM",
            reasons=["Some reason"],
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.35,
                "risk_label": "medium",
                "top_drivers": [
                    {
                        "package": "requests",
                        "scope": "runtime",
                        "reason": "High risk runtime dependency",
                        "contribution": 0.8,
                    }
                ],
                "scope_note": "Dependency scope is classified from manifests and may not reflect actual runtime usage.",
                "confidence_note": "High confidence: most dependencies have classified scope, providing reliable runtime exposure estimates.",
            },
        )
        mock_compute.return_value = insight

        resp = client.get("/api/insights/owner/repo")
        assert resp.status_code == 200

        data = resp.json()
        assert "scope_weighted_risk" in data

        swr = data["scope_weighted_risk"]
        assert "scope_weighted_dependency_risk" in swr
        assert "risk_label" in swr
        assert "top_drivers" in swr
        assert "scope_note" in swr
        assert "confidence_note" in swr

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight")
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_insights_scope_weighted_risk_field_types(
        self, mock_graph_repo, mock_compute, mock_exists, client
    ):
        """scope_weighted_risk sub-fields SHALL have correct types."""
        from open_source_risk_model.insights.models import RepoInsight

        insight = RepoInsight(
            repo_full_name="owner/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.42,
                "risk_label": "medium",
                "top_drivers": [
                    {
                        "package": "express",
                        "scope": "runtime",
                        "reason": "Vulnerable runtime dep",
                        "contribution": 0.65,
                    }
                ],
                "scope_note": "test note",
                "confidence_note": "test confidence",
            },
        )
        mock_compute.return_value = insight

        resp = client.get("/api/insights/owner/repo")
        swr = resp.json()["scope_weighted_risk"]

        assert isinstance(swr["scope_weighted_dependency_risk"], (int, float))
        assert isinstance(swr["risk_label"], str)
        assert swr["risk_label"] in {"low", "medium", "high"}
        assert isinstance(swr["top_drivers"], list)
        assert isinstance(swr["scope_note"], str)
        assert isinstance(swr["confidence_note"], str)

        # Verify top driver structure
        for driver in swr["top_drivers"]:
            assert isinstance(driver["package"], str)
            assert isinstance(driver["scope"], str)
            assert isinstance(driver["reason"], str)
            assert isinstance(driver["contribution"], (int, float))


# ======================================================================
# Test 3: Repo without scope data returns safe defaults
# Validates: Requirement 7.4
# ======================================================================


class TestInsightsSafeDefaults:
    """Test that repos without scope data return safe defaults."""

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight")
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_no_scope_data_returns_safe_defaults(
        self, mock_graph_repo, mock_compute, mock_exists, client
    ):
        """When scope data is unavailable, safe defaults SHALL be returned (Req 7.4)."""
        from open_source_risk_model.insights.models import RepoInsight

        insight = RepoInsight(
            repo_full_name="owner/empty-repo",
            base_maintenance_risk=0.2,
            base_maintenance_label="LOW",
            graph_signal_score=0.1,
            graph_signal_label="LOW",
            reasons=["No graph data available"],
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.0,
                "risk_label": "low",
                "top_drivers": [],
                "scope_note": "Dependency scope is classified from manifests and may not reflect actual runtime usage.",
                "confidence_note": "Scope data is not available for this repository.",
            },
        )
        mock_compute.return_value = insight

        resp = client.get("/api/insights/owner/empty-repo")
        assert resp.status_code == 200

        data = resp.json()
        swr = data["scope_weighted_risk"]

        assert swr["scope_weighted_dependency_risk"] == 0.0
        assert swr["risk_label"] == "low"
        assert swr["top_drivers"] == []
        assert "not available" in swr["confidence_note"].lower()

    @patch("api.app._repo_exists_in_db", return_value=True)
    @patch("api.app.compute_repo_insight")
    @patch("api.app.graph_repo", new_callable=lambda: MagicMock)
    def test_safe_defaults_still_include_existing_fields(
        self, mock_graph_repo, mock_compute, mock_exists, client
    ):
        """Existing insight fields SHALL still be present alongside safe defaults (Req 8.1, 8.2)."""
        from open_source_risk_model.insights.models import RepoInsight

        insight = RepoInsight(
            repo_full_name="owner/empty-repo",
            base_maintenance_risk=0.2,
            base_maintenance_label="LOW",
            graph_signal_score=0.1,
            graph_signal_label="LOW",
            reasons=[],
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.0,
                "risk_label": "low",
                "top_drivers": [],
                "scope_note": "test",
                "confidence_note": "Scope data is not available for this repository.",
            },
        )
        mock_compute.return_value = insight

        resp = client.get("/api/insights/owner/empty-repo")
        data = resp.json()

        assert "base_maintenance_risk" in data
        assert "base_maintenance_label" in data
        assert "graph_signal_score" in data
        assert "graph_signal_label" in data
        assert data["base_maintenance_risk"] == 0.2
        assert data["graph_signal_score"] == 0.1


# ======================================================================
# Test 4: No new scope-weighted-risk specific endpoints
# Validates: Requirement 7.3
# ======================================================================


class TestNoNewEndpoints:
    """Verify no new scope-weighted-risk specific endpoints were created."""

    def test_no_scope_weighted_risk_endpoint(self, client):
        """There SHALL be no dedicated /api/scope-weighted-risk endpoint (Req 7.3)."""
        resp = client.get("/api/scope-weighted-risk")
        # Should be 404 (not found) or 405 (method not allowed), not 200
        assert resp.status_code in (404, 405, 422)

    def test_no_scope_risk_endpoint(self, client):
        """There SHALL be no dedicated /api/scope-risk endpoint."""
        resp = client.get("/api/scope-risk")
        assert resp.status_code in (404, 405, 422)

    def test_no_exposure_metrics_endpoint(self, client):
        """There SHALL be no dedicated /api/exposure-metrics endpoint."""
        resp = client.get("/api/exposure-metrics")
        assert resp.status_code in (404, 405, 422)

    def test_app_routes_do_not_contain_scope_weighted(self):
        """App routes SHALL NOT include any scope-weighted-risk specific paths (Req 7.3)."""
        scope_risk_paths = []
        for route in app.routes:
            path = getattr(route, "path", "")
            if "scope-weighted" in path or "scope_weighted" in path:
                scope_risk_paths.append(path)

        assert scope_risk_paths == [], (
            f"Found unexpected scope-weighted-risk endpoints: {scope_risk_paths}"
        )
