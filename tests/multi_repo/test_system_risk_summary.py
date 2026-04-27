"""Unit tests for compute_system_risk_summary() function."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

from app import compute_system_risk_summary


class TestComputeSystemRiskSummary:
    def test_empty_inputs(self):
        result = compute_system_risk_summary([], {"nodes": [], "edges": []})
        assert result["total_repos"] == 0
        assert result["high_risk_repos"] == 0
        assert result["medium_risk_repos"] == 0
        assert result["low_risk_repos"] == 0
        assert result["aggregate_risk_score"] == 0.0
        assert result["aggregate_label"] == "LOW"
        assert result["total_unique_dependencies"] == 0
        assert result["per_repo_results"] == []

    def test_single_repo_low_risk(self):
        per_repo = [{"repo": "owner/repo", "risk_score": 0.2, "risk_label": "LOW", "error": None}]
        graph = {"nodes": [], "edges": []}
        result = compute_system_risk_summary(per_repo, graph)
        assert result["total_repos"] == 1
        assert result["low_risk_repos"] == 1
        assert result["high_risk_repos"] == 0
        assert result["medium_risk_repos"] == 0
        assert result["aggregate_risk_score"] == 0.2
        assert result["aggregate_label"] == "LOW"

    def test_multiple_repos_mixed_risk(self):
        per_repo = [
            {"repo": "a/a", "risk_score": 0.1, "risk_label": "LOW", "error": None},
            {"repo": "b/b", "risk_score": 0.5, "risk_label": "MEDIUM", "error": None},
            {"repo": "c/c", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
        ]
        graph = {"nodes": [], "edges": []}
        result = compute_system_risk_summary(per_repo, graph)
        assert result["total_repos"] == 3
        assert result["low_risk_repos"] == 1
        assert result["medium_risk_repos"] == 1
        assert result["high_risk_repos"] == 1
        # Mean of 0.1, 0.5, 0.8 ≈ 0.4667
        assert abs(result["aggregate_risk_score"] - (0.1 + 0.5 + 0.8) / 3) < 1e-9
        assert result["aggregate_label"] == "MEDIUM"

    def test_error_repos_excluded_from_counts(self):
        per_repo = [
            {"repo": "a/a", "risk_score": 0.7, "risk_label": "HIGH", "error": None},
            {"repo": "b/b", "risk_score": None, "risk_label": None, "error": "fetch failed"},
        ]
        graph = {"nodes": [], "edges": []}
        result = compute_system_risk_summary(per_repo, graph)
        assert result["total_repos"] == 2
        assert result["high_risk_repos"] == 1
        assert result["low_risk_repos"] == 0
        assert result["medium_risk_repos"] == 0
        # Only non-error score used
        assert result["aggregate_risk_score"] == 0.7
        assert result["aggregate_label"] == "HIGH"

    def test_all_error_repos(self):
        per_repo = [
            {"repo": "a/a", "risk_score": None, "risk_label": None, "error": "fail1"},
            {"repo": "b/b", "risk_score": None, "risk_label": None, "error": "fail2"},
        ]
        graph = {"nodes": [], "edges": []}
        result = compute_system_risk_summary(per_repo, graph)
        assert result["total_repos"] == 2
        assert result["aggregate_risk_score"] == 0.0
        assert result["aggregate_label"] == "LOW"

    def test_dependency_metrics_from_graph(self):
        nodes = [
            {"id": "pkg:flask", "type": "package", "source_repos": ["a/a", "b/b"], "metadata": {"risk_score": 0.7, "cve_count": 2}},
            {"id": "pkg:requests", "type": "dependency", "source_repos": ["a/a"], "metadata": {"risk_score": 0.3, "cve_count": 0}},
            {"id": "pkg:numpy", "type": "package", "source_repos": ["c/c"], "metadata": {"risk_score": 0.65, "cve_count": 1}},
            {"id": "repo:a/a", "type": "repo", "source_repos": ["a/a"], "metadata": {}},
        ]
        graph = {"nodes": nodes, "edges": []}
        result = compute_system_risk_summary([], graph)
        assert result["total_unique_dependencies"] == 3  # flask, requests, numpy (package or dependency type)
        assert result["dependencies_used_by_multiple_repos"] == 1  # flask
        assert result["high_risk_dependencies"] == 2  # flask (0.7) and numpy (0.65)
        assert result["vulnerable_dependencies"] == 2  # flask (2 CVEs) and numpy (1 CVE)

    def test_system_summary_sentence(self):
        per_repo = [
            {"repo": "a/a", "risk_score": 0.5, "risk_label": "MEDIUM", "error": None},
            {"repo": "b/b", "risk_score": 0.4, "risk_label": "MEDIUM", "error": None},
        ]
        nodes = [
            {"id": "pkg:x", "type": "package", "source_repos": ["a/a"], "metadata": {"risk_score": 0.8, "cve_count": 1}},
        ]
        graph = {"nodes": nodes, "edges": []}
        result = compute_system_risk_summary(per_repo, graph)
        summary = result["system_summary"]
        assert "medium risk" in summary.lower()
        assert "2 repositories" in summary
        assert "1 high-risk dependency" in summary
        assert "1 vulnerable dependency" in summary

    def test_system_summary_single_repo(self):
        per_repo = [{"repo": "a/a", "risk_score": 0.1, "risk_label": "LOW", "error": None}]
        graph = {"nodes": [], "edges": []}
        result = compute_system_risk_summary(per_repo, graph)
        assert "1 repository" in result["system_summary"]

    def test_system_summary_no_risky_deps(self):
        per_repo = [{"repo": "a/a", "risk_score": 0.1, "risk_label": "LOW", "error": None}]
        graph = {"nodes": [{"id": "pkg:safe", "type": "package", "source_repos": [], "metadata": {"risk_score": 0.1, "cve_count": 0}}], "edges": []}
        result = compute_system_risk_summary(per_repo, graph)
        # No high-risk or vulnerable deps, so summary should end with just the repo count
        assert "high-risk" not in result["system_summary"]
        assert "vulnerable" not in result["system_summary"]

    def test_per_repo_results_passed_through(self):
        per_repo = [
            {"repo": "a/a", "risk_score": 0.5, "risk_label": "MEDIUM", "error": None},
        ]
        result = compute_system_risk_summary(per_repo, {"nodes": [], "edges": []})
        assert result["per_repo_results"] is per_repo

    def test_node_with_none_metadata(self):
        """Nodes with None metadata should not crash."""
        nodes = [
            {"id": "pkg:x", "type": "package", "source_repos": [], "metadata": None},
        ]
        result = compute_system_risk_summary([], {"nodes": nodes, "edges": []})
        assert result["total_unique_dependencies"] == 1
        assert result["high_risk_dependencies"] == 0
        assert result["vulnerable_dependencies"] == 0
