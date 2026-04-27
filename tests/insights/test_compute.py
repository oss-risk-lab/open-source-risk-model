"""Unit tests for the insight engine orchestrator (compute.py).

Covers: full pipeline, missing graph, empty nodes list, stub graph
with single repo node, malformed graph JSON, base risk defaults,
deterministic ordering, and no-rescoring invariant.
"""
import inspect
import textwrap
from unittest.mock import MagicMock

import pytest

from open_source_risk_model.insights.compute import (
    _has_meaningful_graph,
    compute_repo_insight,
)


def _make_graph_repo(graph_data):
    """Create a mock GraphRepository that returns the given graph_data."""
    repo = MagicMock()
    repo.get_graph.return_value = graph_data
    return repo


# ── Helper: _has_meaningful_graph ─────────────────────────────────────


class TestHasMeaningfulGraph:
    def test_none_returns_false(self):
        assert _has_meaningful_graph(None) is False

    def test_no_graph_key_returns_false(self):
        assert _has_meaningful_graph({"repo": "a/b"}) is False

    def test_empty_nodes_returns_false(self):
        assert _has_meaningful_graph({"graph": {"nodes": []}}) is False

    def test_no_nodes_key_returns_false(self):
        assert _has_meaningful_graph({"graph": {"edges": []}}) is False

    def test_nodes_not_a_list_returns_false(self):
        assert _has_meaningful_graph({"graph": {"nodes": "not-a-list"}}) is False

    def test_single_node_returns_true(self):
        assert _has_meaningful_graph({"graph": {"nodes": [{"type": "repo"}]}}) is True

    def test_multiple_nodes_returns_true(self):
        data = {"graph": {"nodes": [{"type": "repo"}, {"type": "cve"}]}}
        assert _has_meaningful_graph(data) is True


# ── Full pipeline ─────────────────────────────────────────────────────


class TestComputeRepoInsightFullPipeline:
    """Test the full signal extraction → rule evaluation → score pipeline."""

    def _full_graph(self):
        return {
            "repo": "owner/repo",
            "graph": {
                "nodes": [
                    {
                        "type": "repo",
                        "metadata": {
                            "maintenance_risk": 0.45,
                            "maintenance_label": "MEDIUM",
                        },
                    },
                    {
                        "type": "cve",
                        "metadata": {
                            "cve_id": "CVE-2024-001",
                            "cvss_score": 9.8,
                            "severity": "CRITICAL",
                        },
                    },
                    {
                        "type": "maintainer",
                        "metadata": {
                            "username": "alice",
                            "contribution_fraction": 0.9,
                        },
                    },
                    {
                        "type": "release",
                        "metadata": {
                            "tag_name": "v1.0.0",
                            "is_latest": True,
                            "days_ago": 400,
                        },
                    },
                ],
                "edges": [],
            },
            "metadata": {"node_count": 4},
        }

    def test_full_pipeline_score(self):
        graph_repo = _make_graph_repo(self._full_graph())
        insight = compute_repo_insight("owner/repo", graph_repo)

        # CVE critical → 0.4, maintainer >0.8 → 0.3, release >365 → 0.3
        # sum = 1.0, capped at 1.0
        assert insight.graph_signal_score == 1.0
        assert insight.graph_signal_label == "HIGH"

    def test_full_pipeline_base_risk(self):
        graph_repo = _make_graph_repo(self._full_graph())
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.base_maintenance_risk == 0.45
        assert insight.base_maintenance_label == "MEDIUM"

    def test_full_pipeline_reasons(self):
        graph_repo = _make_graph_repo(self._full_graph())
        insight = compute_repo_insight("owner/repo", graph_repo)
        # All three signals are non-info, so 3 reasons
        assert len(insight.reasons) == 3

    def test_full_pipeline_signal_order(self):
        graph_repo = _make_graph_repo(self._full_graph())
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.direct_signals[0].signal_name == "cve_risk"
        assert insight.direct_signals[1].signal_name == "maintainer_concentration"
        assert insight.direct_signals[2].signal_name == "release_staleness"

    def test_full_pipeline_top_risky_deps_empty(self):
        graph_repo = _make_graph_repo(self._full_graph())
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.top_risky_dependencies == []


# ── Missing graph ─────────────────────────────────────────────────────


class TestMissingGraph:
    def test_none_graph_returns_default(self):
        graph_repo = _make_graph_repo(None)
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.reasons == ["No graph data available"]
        assert insight.graph_signal_score == 0.0
        assert insight.graph_signal_label == "LOW"
        assert insight.direct_signals == []

    def test_empty_nodes_returns_default(self):
        graph_repo = _make_graph_repo({"graph": {"nodes": []}})
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.reasons == ["No graph data available"]

    def test_no_nodes_key_returns_default(self):
        graph_repo = _make_graph_repo({"graph": {}})
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.reasons == ["No graph data available"]


# ── Malformed graph JSON ──────────────────────────────────────────────


class TestMalformedGraph:
    def test_nodes_not_a_list(self):
        graph_repo = _make_graph_repo({"graph": {"nodes": "not-a-list"}})
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.reasons == ["No graph data available"]
        assert insight.graph_signal_score == 0.0

    def test_graph_key_not_a_dict(self):
        graph_repo = _make_graph_repo({"graph": "invalid"})
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.reasons == ["No graph data available"]


# ── Stub graph with single repo node ─────────────────────────────────


class TestStubGraph:
    def test_single_repo_node_is_valid(self):
        graph_data = {
            "graph": {
                "nodes": [
                    {
                        "type": "repo",
                        "metadata": {
                            "maintenance_risk": 0.3,
                            "maintenance_label": "MEDIUM",
                        },
                    }
                ],
                "edges": [],
            }
        }
        graph_repo = _make_graph_repo(graph_data)
        insight = compute_repo_insight("owner/repo", graph_repo)

        # No CVEs, no maintainers, no releases → all info → score 0.0
        assert insight.graph_signal_score == 0.0
        assert insight.graph_signal_label == "LOW"
        assert insight.reasons == []  # all signals are info
        assert len(insight.direct_signals) == 3
        assert insight.base_maintenance_risk == 0.3
        assert insight.base_maintenance_label == "MEDIUM"


# ── Base risk defaults when repo node lacks fields ────────────────────


class TestBaseRiskDefaults:
    def test_repo_node_missing_risk_fields(self):
        graph_data = {
            "graph": {
                "nodes": [{"type": "repo", "metadata": {}}],
                "edges": [],
            }
        }
        graph_repo = _make_graph_repo(graph_data)
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.base_maintenance_risk is None
        assert insight.base_maintenance_label is None

    def test_no_repo_node_at_all(self):
        graph_data = {
            "graph": {
                "nodes": [{"type": "maintainer", "metadata": {"username": "a", "contribution_fraction": 0.5}}],
                "edges": [],
            }
        }
        graph_repo = _make_graph_repo(graph_data)
        insight = compute_repo_insight("owner/repo", graph_repo)
        assert insight.base_maintenance_risk is None
        assert insight.base_maintenance_label is None


# ── Deterministic ordering ────────────────────────────────────────────


class TestDeterministicOrdering:
    def test_signal_order_is_always_deterministic(self):
        """Run multiple times to confirm ordering is stable."""
        graph_data = {
            "graph": {
                "nodes": [
                    {"type": "repo", "metadata": {}},
                    {"type": "cve", "metadata": {"cve_id": "CVE-1", "cvss_score": 5.0}},
                    {"type": "maintainer", "metadata": {"username": "bob", "contribution_fraction": 0.7}},
                    {"type": "release", "metadata": {"tag_name": "v1", "is_latest": True, "days_ago": 200}},
                ],
                "edges": [],
            }
        }
        for _ in range(10):
            graph_repo = _make_graph_repo(graph_data)
            insight = compute_repo_insight("owner/repo", graph_repo)
            names = [s.signal_name for s in insight.direct_signals]
            assert names == ["cve_risk", "maintainer_concentration", "release_staleness"]


# ── Score computation edge cases ──────────────────────────────────────


class TestScoreComputation:
    def test_medium_label_threshold(self):
        """Score exactly 0.3 → MEDIUM."""
        graph_data = {
            "graph": {
                "nodes": [
                    {"type": "repo", "metadata": {}},
                    {"type": "maintainer", "metadata": {"username": "alice", "contribution_fraction": 0.85}},
                ],
                "edges": [],
            }
        }
        graph_repo = _make_graph_repo(graph_data)
        insight = compute_repo_insight("owner/repo", graph_repo)
        # maintainer >0.8 → 0.3, CVE 0, release 0 → total 0.3
        assert insight.graph_signal_score == 0.3
        assert insight.graph_signal_label == "MEDIUM"

    def test_low_label_below_threshold(self):
        """Score below 0.3 → LOW."""
        graph_data = {
            "graph": {
                "nodes": [
                    {"type": "repo", "metadata": {}},
                    {"type": "cve", "metadata": {"cve_id": "CVE-1"}},
                ],
                "edges": [],
            }
        }
        graph_repo = _make_graph_repo(graph_data)
        insight = compute_repo_insight("owner/repo", graph_repo)
        # CVE with no severity → medium → 0.2, rest 0 → total 0.2
        assert insight.graph_signal_score == 0.2
        assert insight.graph_signal_label == "LOW"


# ── No-rescoring invariant (Property 13) ──────────────────────────────


class TestNoRescoringInvariant:
    """Verify compute.py does not import score_repo or ingestion modules."""

    def test_no_score_repo_import(self):
        """Reads compute.py source and asserts no score_repo import."""
        import open_source_risk_model.insights.compute as compute_mod

        source = inspect.getsource(compute_mod)
        assert "score_repo" not in source, "compute.py must not import or reference score_repo"

    def test_no_ingestion_module_import(self):
        """Reads compute.py source and asserts no ingestion module imports."""
        import open_source_risk_model.insights.compute as compute_mod

        source = inspect.getsource(compute_mod)
        assert "from ..ingestion" not in source, "compute.py must not import ingestion modules"
        assert "from open_source_risk_model.ingestion" not in source
        assert "import open_source_risk_model.ingestion" not in source
