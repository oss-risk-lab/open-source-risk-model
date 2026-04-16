"""Unit tests for compute_priority_risks() function."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.app import compute_priority_risks, SEVERITY_BASE


class TestComputePriorityRisks:
    """Tests for compute_priority_risks()."""

    def test_empty_inputs(self):
        """Returns empty list when no candidates exist."""
        result = compute_priority_risks([], {"nodes": [], "edges": []})
        assert result == []

    def test_high_risk_repo_candidate(self):
        """High-risk repos appear as candidates with type='repo'."""
        per_repo = [
            {"repo": "org/risky", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
        ]
        result = compute_priority_risks(per_repo, {"nodes": [], "edges": []})
        assert len(result) == 1
        assert result[0]["name"] == "org/risky"
        assert result[0]["type"] == "repo"
        assert result[0]["severity"] == "high"
        assert result[0]["priority_score"] == SEVERITY_BASE["high"]

    def test_skips_error_repos(self):
        """Repos with errors are not included as candidates."""
        per_repo = [
            {"repo": "org/broken", "risk_score": None, "risk_label": "HIGH", "error": "fail"},
        ]
        result = compute_priority_risks(per_repo, {"nodes": [], "edges": []})
        assert result == []

    def test_dep_with_cves(self):
        """Dependencies with CVEs appear as candidates."""
        graph = {
            "nodes": [
                {"id": "pkg:pypi/vuln", "type": "package", "label": "vuln",
                 "metadata": {"cve_count": 2}, "source_repos": ["a/b"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks([], graph)
        assert len(result) == 1
        assert result[0]["name"] == "vuln"
        assert result[0]["type"] == "dependency"
        assert result[0]["severity"] == "medium"  # cve_count=2, <3 so medium
        expected_score = SEVERITY_BASE["medium"] + (1 * 0.5) + (2 * 1.0)
        assert result[0]["priority_score"] == expected_score

    def test_dep_with_high_cve_count(self):
        """Dependencies with >= 3 CVEs get severity='high'."""
        graph = {
            "nodes": [
                {"id": "pkg:pypi/very-vuln", "type": "dependency", "label": "very-vuln",
                 "metadata": {"cve_count": 5}, "source_repos": ["a/b", "c/d"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks([], graph)
        assert len(result) == 1
        assert result[0]["severity"] == "high"
        expected_score = SEVERITY_BASE["high"] + (2 * 0.5) + (5 * 1.0)
        assert result[0]["priority_score"] == expected_score

    def test_dep_used_by_many_repos(self):
        """Dependencies used by >= 2 repos appear as concentration risk."""
        graph = {
            "nodes": [
                {"id": "pkg:pypi/popular", "type": "package", "label": "popular",
                 "metadata": {}, "source_repos": ["a/b", "c/d", "e/f"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks([], graph)
        assert len(result) == 1
        assert result[0]["name"] == "popular"
        assert result[0]["severity"] == "medium"
        expected_score = SEVERITY_BASE["medium"] + (3 * 0.5) + (0 * 1.0)
        assert result[0]["priority_score"] == expected_score
        assert result[0]["used_by_repos"] == ["a/b", "c/d", "e/f"]

    def test_deduplication_keeps_higher_score(self):
        """When a dep matches multiple criteria, the higher score wins."""
        graph = {
            "nodes": [
                {"id": "pkg:pypi/overlap", "type": "package", "label": "overlap",
                 "metadata": {"cve_count": 2}, "source_repos": ["a/b", "c/d"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks([], graph)
        # CVE candidate: SEVERITY_BASE["medium"] + 2*0.5 + 2*1.0 = 2+1+2 = 5.0
        # Multi-repo candidate: SEVERITY_BASE["medium"] + 2*0.5 + 2*1.0 = 2+1+2 = 5.0
        # Both equal, but CVE path runs first so CVE reason wins
        assert len(result) == 1
        assert result[0]["name"] == "overlap"

    def test_sorted_descending_by_score(self):
        """Results are sorted by priority_score descending."""
        per_repo = [
            {"repo": "org/high", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
        ]
        graph = {
            "nodes": [
                {"id": "pkg:pypi/vuln", "type": "package", "label": "vuln",
                 "metadata": {"cve_count": 4}, "source_repos": ["a/b", "c/d"]},
                {"id": "pkg:pypi/shared", "type": "package", "label": "shared",
                 "metadata": {}, "source_repos": ["a/b", "c/d"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks(per_repo, graph)
        scores = [r["priority_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_max_5_results(self):
        """Returns at most 5 items even with more candidates."""
        per_repo = [
            {"repo": f"org/repo{i}", "risk_score": 0.8, "risk_label": "HIGH", "error": None}
            for i in range(8)
        ]
        result = compute_priority_risks(per_repo, {"nodes": [], "edges": []})
        assert len(result) <= 5

    def test_all_required_fields_present(self):
        """Each result item has all required fields."""
        per_repo = [
            {"repo": "org/risky", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
        ]
        graph = {
            "nodes": [
                {"id": "pkg:pypi/vuln", "type": "package", "label": "vuln",
                 "metadata": {"cve_count": 1}, "source_repos": ["a/b"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks(per_repo, graph)
        required_fields = {"name", "type", "reason", "severity", "priority_score", "used_by_repos"}
        for item in result:
            assert required_fields.issubset(item.keys())

    def test_ignores_non_package_nodes(self):
        """Non-package/dependency nodes are not considered."""
        graph = {
            "nodes": [
                {"id": "repo:org/foo", "type": "repository", "label": "foo",
                 "metadata": {"cve_count": 5}, "source_repos": ["a/b"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks([], graph)
        assert result == []

    def test_low_and_medium_repos_excluded(self):
        """Only HIGH-risk repos become candidates, not LOW or MEDIUM."""
        per_repo = [
            {"repo": "org/low", "risk_score": 0.1, "risk_label": "LOW", "error": None},
            {"repo": "org/med", "risk_score": 0.4, "risk_label": "MEDIUM", "error": None},
        ]
        result = compute_priority_risks(per_repo, {"nodes": [], "edges": []})
        assert result == []

    def test_priority_score_formula(self):
        """Verify the exact priority_score formula."""
        graph = {
            "nodes": [
                {"id": "pkg:pypi/lib", "type": "dependency", "label": "lib",
                 "metadata": {"cve_count": 3}, "source_repos": ["a/b", "c/d", "e/f"]},
            ],
            "edges": [],
        }
        result = compute_priority_risks([], graph)
        # cve_count >= 3 → severity="high", usage_count=3
        # score = 3.0 + (3 * 0.5) + (3 * 1.0) = 3.0 + 1.5 + 3.0 = 7.5
        assert result[0]["priority_score"] == 7.5
