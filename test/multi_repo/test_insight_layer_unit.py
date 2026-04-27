"""Unit tests for insight layer upgrade — unmapped dependency handling.

Tests that unmapped dependencies flow correctly through merge_graphs(),
compute_system_risk_summary(), and compute_top_risky_dependencies().
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

from app import (
    merge_graphs,
    compute_system_risk_summary,
    compute_top_risky_dependencies,
    _generate_risk_explanation,
    _generate_key_factors,
    _get_recommended_action,
    _extract_primary_risk_factor,
    get_top_risk_drivers,
    compute_insight_statements,
    compute_system_risk_summary,
)


class TestUnmappedDependencyFlow:
    """Task 4.1: Verify unmapped dependencies appear correctly in all outputs."""

    def test_unmapped_node_appears_in_merged_graph(self):
        """Unmapped deps appear as nodes in merged graph with type 'package' and empty source_repos."""
        unmapped_nodes = [
            {"id": "pkg:nonexistent-lib", "type": "package", "label": "nonexistent-lib"}
        ]
        merged = merge_graphs([], unmapped_nodes)
        nodes = merged["nodes"]
        assert len(nodes) == 1
        node = nodes[0]
        assert node["id"] == "pkg:nonexistent-lib"
        assert node["type"] == "package"
        assert node["label"] == "nonexistent-lib"
        assert node["source_repos"] == []
        assert node["metadata"] == {}

    def test_multiple_unmapped_nodes_in_merged_graph(self):
        """Multiple unmapped deps all appear in the merged graph."""
        unmapped_nodes = [
            {"id": "pkg:lib-a", "type": "package", "label": "lib-a"},
            {"id": "pkg:lib-b", "type": "package", "label": "lib-b"},
            {"id": "pkg:lib-c", "type": "package", "label": "lib-c"},
        ]
        merged = merge_graphs([], unmapped_nodes)
        node_ids = {n["id"] for n in merged["nodes"]}
        assert node_ids == {"pkg:lib-a", "pkg:lib-b", "pkg:lib-c"}

    def test_unmapped_deps_counted_in_total_unique_dependencies(self):
        """Unmapped deps are counted in total_unique_dependencies."""
        unmapped_nodes = [
            {"id": "pkg:nonexistent-lib", "type": "package", "label": "nonexistent-lib"},
            {"id": "pkg:another-lib", "type": "package", "label": "another-lib"},
        ]
        merged = merge_graphs([], unmapped_nodes)
        summary = compute_system_risk_summary([], merged)
        assert summary["total_unique_dependencies"] >= 2

    def test_unmapped_deps_in_risky_dependencies_with_defaults(self):
        """Unmapped deps appear in compute_top_risky_dependencies() with default values."""
        unmapped_nodes = [
            {"id": "pkg:nonexistent-lib", "type": "package", "label": "nonexistent-lib"}
        ]
        merged = merge_graphs([], unmapped_nodes)
        risky_deps = compute_top_risky_dependencies(merged)
        assert len(risky_deps) == 1
        dep = risky_deps[0]
        assert dep["package_name"] == "nonexistent-lib"
        assert dep["risk_score"] == 0
        assert dep["risk_label"] == "LOW"
        assert dep["cve_count"] == 0
        assert dep["used_by_repos"] == []

    def test_unmapped_deps_mixed_with_empty_repos(self):
        """Unmapped deps work correctly when per_repo_results is empty."""
        unmapped_nodes = [
            {"id": "pkg:scikit-learn", "type": "package", "label": "scikit-learn"},
            {"id": "pkg:nonexistent-lib", "type": "package", "label": "nonexistent-lib"},
        ]
        merged = merge_graphs([], unmapped_nodes)

        # Verify summary counts
        summary = compute_system_risk_summary([], merged)
        assert summary["total_unique_dependencies"] == 2
        assert summary["total_repos"] == 0

        # Verify risky deps output
        risky_deps = compute_top_risky_dependencies(merged)
        dep_names = {d["package_name"] for d in risky_deps}
        assert "scikit-learn" in dep_names
        assert "nonexistent-lib" in dep_names
        for dep in risky_deps:
            assert dep["risk_score"] == 0
            assert dep["risk_label"] == "LOW"
            assert dep["cve_count"] == 0
            assert dep["used_by_repos"] == []


class TestRiskExplanationUnit:
    """Task 10.1: Unit tests for risk explanation, key factors, recommended action, and primary risk factor."""

    # --- Risk explanation tests ---

    def test_low_no_vulnerabilities_explanation(self):
        """LOW with no vulnerabilities produces explanation containing expected phrases."""
        result = _generate_risk_explanation(
            aggregate_label="LOW",
            high_risk_repos=0,
            vulnerable_dependencies=0,
            high_risk_dependencies=0,
            total_repos=3,
        )
        assert "low risk" in result.lower()
        assert "because" in result
        assert "no vulnerable" in result.lower()

    def test_high_with_3_vulnerable_deps_explanation(self):
        """HIGH with 3 vulnerable deps produces explanation referencing them."""
        result = _generate_risk_explanation(
            aggregate_label="HIGH",
            high_risk_repos=0,
            vulnerable_dependencies=3,
            high_risk_dependencies=0,
            total_repos=5,
        )
        assert "high risk" in result.lower()
        assert "3 vulnerable" in result.lower()

    # --- Recommended action tests ---

    def test_recommended_action_low(self):
        assert _get_recommended_action("LOW") == "No immediate action required."

    def test_recommended_action_medium(self):
        assert _get_recommended_action("MEDIUM") == "Monitor dependencies and maintenance activity."

    def test_recommended_action_high(self):
        assert _get_recommended_action("HIGH") == "Review vulnerable dependencies and high-risk repositories immediately."

    # --- Primary risk factor priority tests ---

    def test_primary_risk_factor_vulnerable_deps_first(self):
        """Vulnerable deps take priority over high repos and high deps."""
        result = _extract_primary_risk_factor("HIGH", vulnerable_dependencies=2, high_risk_repos=3, high_risk_dependencies=4)
        assert "2 vulnerable" in result.lower()
        assert "drive" in result.lower() or "elevated" in result.lower()

    def test_primary_risk_factor_high_repos_second(self):
        """High-risk repos take priority when no vulnerable deps."""
        result = _extract_primary_risk_factor("HIGH", vulnerable_dependencies=0, high_risk_repos=3, high_risk_dependencies=4)
        assert "3 high-risk repositor" in result.lower()

    def test_primary_risk_factor_high_deps_third(self):
        """High-risk deps used when no vulnerable deps or high repos."""
        result = _extract_primary_risk_factor("MEDIUM", vulnerable_dependencies=0, high_risk_repos=0, high_risk_dependencies=5)
        assert "5 high-risk dependenc" in result.lower()

    def test_primary_risk_factor_low_aggregate(self):
        """LOW aggregate with no risk factors references absence of vulnerabilities."""
        result = _extract_primary_risk_factor("LOW", vulnerable_dependencies=0, high_risk_repos=0, high_risk_dependencies=0)
        assert "no vulnerable" in result.lower()

    def test_primary_risk_factor_fallback(self):
        """Non-LOW aggregate with no specific factors still produces data-derived text."""
        result = _extract_primary_risk_factor("MEDIUM", vulnerable_dependencies=0, high_risk_repos=0, high_risk_dependencies=0)
        assert "no significant risk factors" in result.lower()

    # --- Key factors length tests ---

    def test_key_factors_returns_at_least_1(self):
        factors = _generate_key_factors("LOW", 0, 0, 0, 0, 0)
        assert len(factors) >= 1

    def test_key_factors_returns_at_most_5(self):
        factors = _generate_key_factors("HIGH", 3, 2, 5, 4, 100)
        assert len(factors) <= 5

    def test_key_factors_all_nonempty_strings(self):
        factors = _generate_key_factors("MEDIUM", 1, 2, 3, 4, 50)
        for f in factors:
            assert isinstance(f, str)
            assert len(f) > 0

    def test_key_factors_various_inputs(self):
        """Key factors returns 1-5 items for various input combinations."""
        test_cases = [
            ("LOW", 0, 0, 0, 0, 0),
            ("LOW", 0, 0, 0, 0, 10),
            ("MEDIUM", 1, 2, 0, 0, 5),
            ("HIGH", 3, 2, 5, 4, 100),
        ]
        for args in test_cases:
            factors = _generate_key_factors(*args)
            assert 1 <= len(factors) <= 5, f"Expected 1-5 factors for {args}, got {len(factors)}"


class TestSignalRiskDriversUnit:
    """Task 10.2: Unit tests for signal-based risk drivers."""

    def test_zero_repos_returns_info_signal(self):
        """Empty per_repo_results returns at least 1 info signal."""
        signals = get_top_risk_drivers([], {"nodes": [], "edges": []})
        assert len(signals) >= 1
        assert signals[0]["severity"] == "info"

    def test_signal_ordering_severity_then_category(self):
        """Signals are ordered by severity (high→medium→low→info) then category."""
        per_repo = [
            {"repo": "a", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
            {"repo": "b", "risk_score": 0.4, "risk_label": "MEDIUM", "error": None},
        ]
        vuln_node = {
            "id": "pkg:vuln-lib", "type": "package", "label": "vuln-lib",
            "source_repos": [], "metadata": {"cve_count": 2, "risk_score": 0.9},
        }
        merged = {"nodes": [vuln_node], "edges": []}
        signals = get_top_risk_drivers(per_repo, merged)

        severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        category_order = {"vulnerability": 0, "maintenance": 1, "dependency": 2}
        for i in range(len(signals) - 1):
            s_cur = (severity_order[signals[i]["severity"]], category_order[signals[i]["category"]])
            s_nxt = (severity_order[signals[i + 1]["severity"]], category_order[signals[i + 1]["category"]])
            assert s_cur <= s_nxt, f"Signal {i} ({signals[i]}) should come before signal {i+1} ({signals[i+1]})"

    def test_positive_signal_guarantee_all_low(self):
        """All LOW repos with no vuln deps guarantees at least 1 positive (info) signal."""
        per_repo = [
            {"repo": "a", "risk_score": 0.1, "risk_label": "LOW", "error": None},
            {"repo": "b", "risk_score": 0.2, "risk_label": "LOW", "error": None},
        ]
        merged = {"nodes": [], "edges": []}
        signals = get_top_risk_drivers(per_repo, merged)
        info_signals = [s for s in signals if s["severity"] == "info"]
        assert len(info_signals) >= 1, "Expected at least 1 positive info signal for all-LOW repos"

    def test_vulnerability_signal_zero_vuln_deps(self):
        """0 vuln deps → info-level vulnerability signal."""
        per_repo = [{"repo": "a", "risk_score": 0.1, "risk_label": "LOW", "error": None}]
        merged = {"nodes": [], "edges": []}
        signals = get_top_risk_drivers(per_repo, merged)
        vuln_signals = [s for s in signals if s["category"] == "vulnerability"]
        assert len(vuln_signals) >= 1
        assert vuln_signals[0]["severity"] == "info"

    def test_vulnerability_signal_with_vuln_deps(self):
        """N > 0 vuln deps → high-level vulnerability signal."""
        per_repo = [{"repo": "a", "risk_score": 0.1, "risk_label": "LOW", "error": None}]
        vuln_node = {
            "id": "pkg:bad-lib", "type": "package", "label": "bad-lib",
            "source_repos": [], "metadata": {"cve_count": 3, "risk_score": 0.7},
        }
        merged = {"nodes": [vuln_node], "edges": []}
        signals = get_top_risk_drivers(per_repo, merged)
        vuln_signals = [s for s in signals if s["category"] == "vulnerability"]
        assert len(vuln_signals) >= 1
        assert vuln_signals[0]["severity"] == "high"


class TestInsightStatementsUnit:
    """Task 10.3: Unit tests for insight statements."""

    def _make_summary(self, **overrides):
        """Helper to build a system_risk_summary dict with defaults."""
        base = {
            "total_repos": 3,
            "high_risk_repos": 0,
            "medium_risk_repos": 0,
            "low_risk_repos": 3,
            "total_unique_dependencies": 5,
            "dependencies_used_by_multiple_repos": 0,
            "high_risk_dependencies": 0,
            "vulnerable_dependencies": 0,
            "aggregate_risk_score": 0.1,
            "aggregate_label": "LOW",
        }
        base.update(overrides)
        return base

    def test_all_healthy_produces_stability_statement(self):
        """All LOW repos, no vuln deps → stability statement present."""
        summary = self._make_summary()
        per_repo = [
            {"repo": "a", "risk_score": 0.1, "risk_label": "LOW", "error": None},
            {"repo": "b", "risk_score": 0.1, "risk_label": "LOW", "error": None},
            {"repo": "c", "risk_score": 0.1, "risk_label": "LOW", "error": None},
        ]
        merged = {"nodes": [], "edges": []}
        stmts = compute_insight_statements(summary, per_repo, merged)
        combined = " ".join(stmts).lower()
        assert "stable" in combined or "well-maintained" in combined

    def test_mixed_risk_levels_produce_statements(self):
        """Mixed risk levels produce appropriate statements."""
        summary = self._make_summary(
            high_risk_repos=2,
            low_risk_repos=1,
            vulnerable_dependencies=0,
        )
        per_repo = [
            {"repo": "a", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
            {"repo": "b", "risk_score": 0.7, "risk_label": "HIGH", "error": None},
            {"repo": "c", "risk_score": 0.1, "risk_label": "LOW", "error": None},
        ]
        merged = {"nodes": [], "edges": []}
        stmts = compute_insight_statements(summary, per_repo, merged)
        combined = " ".join(stmts).lower()
        assert "attention" in combined or "require" in combined or "elevated" in combined

    def test_statement_count_bounds(self):
        """Statements count is always between 1 and 6."""
        # Minimal case
        summary_min = self._make_summary(total_repos=0, low_risk_repos=0)
        stmts_min = compute_insight_statements(summary_min, [], {"nodes": [], "edges": []})
        assert 1 <= len(stmts_min) <= 6

        # Maximal case — trigger as many conditions as possible
        summary_max = self._make_summary(
            high_risk_repos=3,
            low_risk_repos=0,
            vulnerable_dependencies=5,
            dependencies_used_by_multiple_repos=4,
            high_risk_dependencies=2,
        )
        per_repo = [
            {"repo": "a", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
            {"repo": "b", "risk_score": 0.7, "risk_label": "HIGH", "error": None},
            {"repo": "c", "risk_score": 0.65, "risk_label": "HIGH", "error": None},
        ]
        stmts_max = compute_insight_statements(summary_max, per_repo, {"nodes": [], "edges": []})
        assert 1 <= len(stmts_max) <= 6

    def test_high_risk_repos_produce_attention_statement(self):
        """High-risk repos produce a statement about needing attention."""
        summary = self._make_summary(
            high_risk_repos=2,
            low_risk_repos=1,
        )
        per_repo = [
            {"repo": "a", "risk_score": 0.8, "risk_label": "HIGH", "error": None},
            {"repo": "b", "risk_score": 0.7, "risk_label": "HIGH", "error": None},
            {"repo": "c", "risk_score": 0.1, "risk_label": "LOW", "error": None},
        ]
        merged = {"nodes": [], "edges": []}
        stmts = compute_insight_statements(summary, per_repo, merged)
        attention_stmts = [s for s in stmts if "attention" in s.lower() or "require" in s.lower()]
        assert len(attention_stmts) >= 1, f"Expected attention statement for high-risk repos, got: {stmts}"
