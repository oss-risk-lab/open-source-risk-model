"""Integration tests for compute_repo_insight() with Phase 5 actionable insights fields.

Verifies that the Phase 5 integration in compute.py correctly populates
priority_recommendations, risk_clusters, risk_narrative, and overall_confidence
in the RepoInsight output, and that existing fields remain unchanged.

Requirements: 7.1–7.7, 12.1–12.5
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from open_source_risk_model.insights.compute import compute_repo_insight
from open_source_risk_model.insights.actionable import (
    ActionableInsight,
    OverallConfidence,
    RiskCluster,
    RiskNarrative,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph_repo(graph_data):
    """Create a mock GraphRepository that returns the given graph_data."""
    repo = MagicMock()
    repo.get_graph.return_value = graph_data
    return repo


def _graph_with_packages():
    """Graph data with package nodes that have dependency metadata."""
    return {
        "repo": "test/repo",
        "graph": {
            "nodes": [
                {
                    "type": "repository",
                    "label": "test/repo",
                    "metadata": {
                        "maintenance_risk": 0.3,
                        "maintenance_label": "LOW",
                    },
                },
                {
                    "type": "package",
                    "label": "lodash",
                    "metadata": {
                        "package_name": "lodash",
                        "dependency_scope": "runtime",
                        "scope_confidence": "high",
                        "vulnerability_count": 3,
                        "risk_score": 85.0,
                        "depth": 1,
                    },
                    "provenance": {},
                },
                {
                    "type": "package",
                    "label": "express",
                    "metadata": {
                        "package_name": "express",
                        "dependency_scope": "runtime",
                        "scope_confidence": "medium",
                        "vulnerability_count": 1,
                        "risk_score": 60.0,
                        "depth": 1,
                    },
                    "provenance": {},
                },
                {
                    "type": "package",
                    "label": "jest",
                    "metadata": {
                        "package_name": "jest",
                        "dependency_scope": "dev",
                        "scope_confidence": "high",
                        "vulnerability_count": 0,
                        "risk_score": 20.0,
                        "depth": 1,
                    },
                    "provenance": {},
                },
                {
                    "type": "package",
                    "label": "debug",
                    "metadata": {
                        "package_name": "debug",
                        "dependency_scope": "runtime",
                        "scope_confidence": "low",
                        "vulnerability_count": 0,
                        "risk_score": 40.0,
                        "depth": 2,
                    },
                    "provenance": {},
                },
            ],
            "edges": [],
        },
        "metadata": {"node_count": 5},
    }


def _graph_without_packages():
    """Graph data with only a repo node (no package nodes)."""
    return {
        "repo": "test/empty-repo",
        "graph": {
            "nodes": [
                {
                    "type": "repo",
                    "metadata": {
                        "maintenance_risk": 0.5,
                        "maintenance_label": "MEDIUM",
                    },
                },
            ],
            "edges": [],
        },
        "metadata": {"node_count": 1},
    }


# ---------------------------------------------------------------------------
# Test: Phase 5 fields present in to_dict() output
# ---------------------------------------------------------------------------


class TestPhase5FieldsInOutput:
    """Verify compute_repo_insight() output includes Phase 5 fields when serialized."""

    def test_to_dict_includes_priority_recommendations(self):
        """to_dict() includes priority_recommendations list."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        result = insight.to_dict()

        assert "priority_recommendations" in result
        assert isinstance(result["priority_recommendations"], list)
        assert len(result["priority_recommendations"]) > 0

    def test_to_dict_includes_risk_clusters(self):
        """to_dict() includes risk_clusters list with exactly 4 clusters."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        result = insight.to_dict()

        assert "risk_clusters" in result
        assert isinstance(result["risk_clusters"], list)
        assert len(result["risk_clusters"]) == 4

    def test_to_dict_includes_risk_narrative(self):
        """to_dict() includes risk_narrative dict with summary, key_findings, recommendation."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        result = insight.to_dict()

        assert "risk_narrative" in result
        assert result["risk_narrative"] is not None
        assert "summary" in result["risk_narrative"]
        assert "key_findings" in result["risk_narrative"]
        assert "recommendation" in result["risk_narrative"]

    def test_to_dict_includes_overall_confidence(self):
        """to_dict() includes overall_confidence dict with score, label, explanation."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        result = insight.to_dict()

        assert "overall_confidence" in result
        assert result["overall_confidence"] is not None
        assert "score" in result["overall_confidence"]
        assert "label" in result["overall_confidence"]
        assert "explanation" in result["overall_confidence"]

    def test_priority_recommendations_structure(self):
        """Each recommendation has required fields."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        result = insight.to_dict()

        for rec in result["priority_recommendations"]:
            assert "package_name" in rec
            assert "dependency_scope" in rec
            assert "dependency_type" in rec
            assert "reason" in rec
            assert "priority_score" in rec
            assert "action" in rec
            assert 0.0 < rec["priority_score"] <= 1.0

    def test_risk_clusters_structure(self):
        """Each cluster has required fields and known cluster names."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        result = insight.to_dict()

        expected_names = {
            "Runtime Risk Cluster",
            "Transitive Risk Cluster",
            "Vulnerability Cluster",
            "Unknown Scope Cluster",
        }
        actual_names = {c["cluster_name"] for c in result["risk_clusters"]}
        assert actual_names == expected_names

        for cluster in result["risk_clusters"]:
            assert "cluster_name" in cluster
            assert "summary" in cluster
            assert "count" in cluster
            assert "risk_contribution" in cluster
            assert "example_packages" in cluster


# ---------------------------------------------------------------------------
# Test: Existing fields remain unchanged
# ---------------------------------------------------------------------------


class TestExistingFieldsUnchanged:
    """Verify existing response fields remain unchanged after Phase 5 integration."""

    def test_repo_full_name_preserved(self):
        """repo_full_name is correctly set."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        assert insight.repo_full_name == "test/repo"

    def test_graph_signal_score_unchanged(self):
        """graph_signal_score is computed from direct signals only."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        # Score should be based on CVE, maintainer, release signals
        assert isinstance(insight.graph_signal_score, float)
        assert 0.0 <= insight.graph_signal_score <= 1.0

    def test_graph_signal_label_unchanged(self):
        """graph_signal_label is one of HIGH, MEDIUM, LOW."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        assert insight.graph_signal_label in ("HIGH", "MEDIUM", "LOW")

    def test_direct_signals_still_present(self):
        """direct_signals list is still populated with 3 signals."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        assert len(insight.direct_signals) == 3
        signal_names = [s.signal_name for s in insight.direct_signals]
        assert "cve_risk" in signal_names
        assert "maintainer_concentration" in signal_names
        assert "release_staleness" in signal_names

    def test_scope_weighted_risk_still_present(self):
        """scope_weighted_risk dict is still populated."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        assert insight.scope_weighted_risk is not None
        assert "scope_weighted_dependency_risk" in insight.scope_weighted_risk
        assert "risk_label" in insight.scope_weighted_risk

    def test_reasons_include_scope_aware_reasons(self):
        """reasons list includes scope-aware reasons from Phase 4."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        # With runtime packages that have vulnerabilities, we expect scope-aware reasons
        assert isinstance(insight.reasons, list)
        assert len(insight.reasons) > 0


# ---------------------------------------------------------------------------
# Test: Safe defaults when no dependency data
# ---------------------------------------------------------------------------


class TestSafeDefaultsNoDependencyData:
    """Verify repo without dependency data returns safe defaults for Phase 5 fields."""

    def test_no_packages_returns_empty_recommendations(self):
        """No package nodes → empty priority_recommendations."""
        graph_repo = _make_graph_repo(_graph_without_packages())
        insight = compute_repo_insight("test/empty-repo", graph_repo)
        assert insight.priority_recommendations == []

    def test_no_packages_returns_four_empty_clusters(self):
        """No package nodes → 4 clusters with count=0."""
        graph_repo = _make_graph_repo(_graph_without_packages())
        insight = compute_repo_insight("test/empty-repo", graph_repo)
        assert len(insight.risk_clusters) == 4
        for cluster in insight.risk_clusters:
            assert cluster.count == 0
            assert cluster.risk_contribution == 0.0

    def test_no_packages_returns_low_confidence(self):
        """No package nodes → low confidence with safe default."""
        graph_repo = _make_graph_repo(_graph_without_packages())
        insight = compute_repo_insight("test/empty-repo", graph_repo)
        assert insight.overall_confidence is not None
        assert insight.overall_confidence.score == 0.0
        assert insight.overall_confidence.label == "low"

    def test_no_packages_returns_narrative(self):
        """No package nodes → narrative still generated (insufficient data message)."""
        graph_repo = _make_graph_repo(_graph_without_packages())
        insight = compute_repo_insight("test/empty-repo", graph_repo)
        assert insight.risk_narrative is not None
        assert isinstance(insight.risk_narrative.summary, str)
        assert len(insight.risk_narrative.summary) > 0

    def test_no_graph_data_returns_defaults(self):
        """None graph data → early return with default Phase 5 fields."""
        graph_repo = _make_graph_repo(None)
        insight = compute_repo_insight("test/no-graph", graph_repo)
        # Early return path — Phase 5 fields should be at their defaults
        assert insight.priority_recommendations == []
        assert insight.risk_clusters == []
        assert insight.risk_narrative is None
        assert insight.overall_confidence is None

    def test_safe_defaults_serialization(self):
        """Safe defaults serialize correctly via to_dict()."""
        graph_repo = _make_graph_repo(_graph_without_packages())
        insight = compute_repo_insight("test/empty-repo", graph_repo)
        result = insight.to_dict()

        assert result["priority_recommendations"] == []
        assert len(result["risk_clusters"]) == 4
        assert result["overall_confidence"]["score"] == 0.0
        assert result["overall_confidence"]["label"] == "low"
        assert result["risk_narrative"] is not None


# ---------------------------------------------------------------------------
# Test: No new API endpoints created
# ---------------------------------------------------------------------------


class TestNoNewEndpoints:
    """Verify no new API endpoints were created — Phase 5 is additive to existing structure."""

    def test_insight_output_is_additive(self):
        """Phase 5 fields are added to existing RepoInsight, not a separate endpoint."""
        graph_repo = _make_graph_repo(_graph_with_packages())
        insight = compute_repo_insight("test/repo", graph_repo)
        result = insight.to_dict()

        # Existing fields still present
        assert "repo_full_name" in result
        assert "graph_signal_score" in result
        assert "graph_signal_label" in result
        assert "reasons" in result
        assert "direct_signals" in result

        # Phase 5 fields are part of the same dict (not a separate response)
        assert "priority_recommendations" in result
        assert "risk_clusters" in result
        assert "risk_narrative" in result
        assert "overall_confidence" in result

    def test_compute_repo_insight_signature_unchanged(self):
        """compute_repo_insight() still accepts (repo_full_name, graph_repo) only."""
        import inspect
        sig = inspect.signature(compute_repo_insight)
        params = list(sig.parameters.keys())
        assert params == ["repo_full_name", "graph_repo"]
