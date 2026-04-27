"""Property-based tests for insight layer upgrade functions.

Uses Hypothesis to verify invariants of compute_system_risk_summary() new fields:
risk_explanation, key_factors, recommended_action, primary_risk_factor.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from app import (
    compute_system_risk_summary,
    compute_priority_risks,
    get_top_risk_drivers,
    compute_insight_statements,
    _risk_label_from_score,
    _generate_risk_explanation,
    _generate_key_factors,
    _get_recommended_action,
    _extract_primary_risk_factor,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

repo_name_st = st.from_regex(r"[a-z]{2,8}/[a-z]{2,8}", fullmatch=True)

risk_score_st = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)


def consistent_per_repo_result_st():
    """Strategy for a per-repo result where risk_label matches risk_score via _risk_label_from_score()."""
    return risk_score_st.flatmap(
        lambda score: st.fixed_dictionaries({
            "repo": repo_name_st,
            "risk_score": st.just(score),
            "risk_label": st.just(_risk_label_from_score(score)),
            "error": st.none(),
        })
    )


@st.composite
def merged_graph_st(draw):
    """Strategy for generating a merged graph dict with package/dependency nodes.

    Each node has metadata with risk_score and cve_count, matching the shape
    expected by compute_system_risk_summary().
    """
    num_nodes = draw(st.integers(min_value=0, max_value=8))
    nodes = []
    seen_ids = set()
    for _ in range(num_nodes):
        node_id = draw(st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=3, max_size=15,
        ))
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        node_type = draw(st.sampled_from(["package", "dependency"]))
        node_risk_score = draw(st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ))
        cve_count = draw(st.integers(min_value=0, max_value=10))
        source_repos = draw(st.lists(repo_name_st, min_size=0, max_size=3))
        nodes.append({
            "id": node_id,
            "type": node_type,
            "label": node_id,
            "metadata": {
                "risk_score": node_risk_score,
                "cve_count": cve_count,
            },
            "provenance": {},
            "source_repos": source_repos,
        })
    return {"nodes": nodes, "edges": []}


# ---------------------------------------------------------------------------
# Helper: compute summary from generated inputs
# ---------------------------------------------------------------------------

def _compute_summary(per_repo_results, merged_graph):
    """Call compute_system_risk_summary and return the result dict."""
    return compute_system_risk_summary(per_repo_results, merged_graph)


# ---------------------------------------------------------------------------
# Property 3: Risk explanation follows pattern and matches aggregate label
# **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
# ---------------------------------------------------------------------------

class TestRiskExplanationPatternProperty:
    """Property 3: Risk explanation follows pattern and matches aggregate label."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_risk_explanation_contains_because(self, per_repo_results, merged_graph):
        """(a) risk_explanation contains the word 'because'.

        **Validates: Requirements 2.1**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        explanation = summary["risk_explanation"]
        assert "because" in explanation

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_risk_explanation_starts_with_your_system_shows(self, per_repo_results, merged_graph):
        """(b) risk_explanation starts with 'Your system shows'.

        **Validates: Requirements 2.1**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        explanation = summary["risk_explanation"]
        assert explanation.startswith("Your system shows")

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_risk_explanation_ends_with_period(self, per_repo_results, merged_graph):
        """(c) risk_explanation ends with a period.

        **Validates: Requirements 2.1**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        explanation = summary["risk_explanation"]
        assert explanation.endswith(".")

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_risk_explanation_references_factor(self, per_repo_results, merged_graph):
        """(d) risk_explanation references at least one factor from dependencies, repos, or maintenance.

        **Validates: Requirements 2.2**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        explanation = summary["risk_explanation"].lower()
        factor_keywords = [
            "dependenc", "repositor", "maintenance", "repo", "risk factor",
        ]
        assert any(kw in explanation for kw in factor_keywords), (
            f"Explanation does not reference any known factor: {summary['risk_explanation']}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_risk_explanation_low_references_absence(self, per_repo_results, merged_graph):
        """(e) When aggregate label is LOW, explanation references absence of high-risk factors.

        **Validates: Requirements 2.3**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        if summary["aggregate_label"] != "LOW":
            return  # Only check LOW
        explanation = summary["risk_explanation"].lower()
        absence_keywords = ["no vulnerable", "no high-risk", "no significant risk"]
        assert any(kw in explanation for kw in absence_keywords), (
            f"LOW explanation does not reference absence: {summary['risk_explanation']}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_risk_explanation_medium_high_references_factors(self, per_repo_results, merged_graph):
        """(f) When aggregate label is MEDIUM or HIGH, explanation references specific risk factors.

        **Validates: Requirements 2.4**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        if summary["aggregate_label"] not in ("MEDIUM", "HIGH"):
            return  # Only check MEDIUM/HIGH
        explanation = summary["risk_explanation"].lower()
        factor_keywords = [
            "vulnerable", "high maintenance risk", "high-risk",
            "maintenance risk scores", "exceed",
        ]
        assert any(kw in explanation for kw in factor_keywords), (
            f"MEDIUM/HIGH explanation does not reference specific factors: {summary['risk_explanation']}"
        )


# ---------------------------------------------------------------------------
# Property 4: Key factors list length invariant
# **Validates: Requirements 2.5, 2.6**
# ---------------------------------------------------------------------------

class TestKeyFactorsLengthProperty:
    """Property 4: Key factors list length invariant."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_key_factors_between_1_and_5(self, per_repo_results, merged_graph):
        """key_factors list contains between 1 and 5 entries inclusive.

        **Validates: Requirements 2.5, 2.6**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        key_factors = summary["key_factors"]
        assert isinstance(key_factors, list)
        assert 1 <= len(key_factors) <= 5, (
            f"key_factors length {len(key_factors)} not in [1, 5]: {key_factors}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_key_factors_all_non_empty_strings(self, per_repo_results, merged_graph):
        """Each entry in key_factors is a non-empty string.

        **Validates: Requirements 2.5, 2.6**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        for factor in summary["key_factors"]:
            assert isinstance(factor, str)
            assert len(factor) > 0, "key_factors contains an empty string"


# ---------------------------------------------------------------------------
# Property 5: Recommended action maps to aggregate label
# **Validates: Requirements 2.7, 2.8, 2.9, 2.10**
# ---------------------------------------------------------------------------

class TestRecommendedActionMappingProperty:
    """Property 5: Recommended action maps to aggregate label."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_recommended_action_matches_label(self, per_repo_results, merged_graph):
        """recommended_action is exactly the expected string for the aggregate label.

        **Validates: Requirements 2.7, 2.8, 2.9, 2.10**
        """
        expected_actions = {
            "LOW": "No immediate action required.",
            "MEDIUM": "Monitor dependencies and maintenance activity.",
            "HIGH": "Review vulnerable dependencies and high-risk repositories immediately.",
        }
        summary = _compute_summary(per_repo_results, merged_graph)
        label = summary["aggregate_label"]
        assert label in expected_actions, f"Unexpected aggregate label: {label}"
        assert summary["recommended_action"] == expected_actions[label], (
            f"For label {label}, expected '{expected_actions[label]}' "
            f"but got '{summary['recommended_action']}'"
        )


# ---------------------------------------------------------------------------
# Property 12: Risk explanation never contains generic fallback text
# **Validates: Design Decision 6 (No generic fallbacks)**
# ---------------------------------------------------------------------------

class TestNoGenericFallbackProperty:
    """Property 12: Risk explanation never contains generic fallback text."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_risk_explanation_no_generic_fallback(self, per_repo_results, merged_graph):
        """risk_explanation never contains vague placeholder text.

        **Validates: Design Decision 6 (No generic fallbacks)**
        """
        forbidden_phrases = [
            "assessed from available data",
            "risk level assessed",
            "unable to determine",
            "data not available",
            "assessment pending",
        ]
        summary = _compute_summary(per_repo_results, merged_graph)
        explanation = summary["risk_explanation"].lower()
        for phrase in forbidden_phrases:
            assert phrase not in explanation, (
                f"risk_explanation contains forbidden generic text '{phrase}': "
                f"{summary['risk_explanation']}"
            )


# ---------------------------------------------------------------------------
# Property 14: Primary risk factor is always a non-empty data-derived string
# **Validates: Design Decision 8 (Primary risk factor extraction)**
# ---------------------------------------------------------------------------

class TestPrimaryRiskFactorProperty:
    """Property 14: Primary risk factor is always a non-empty data-derived string."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_primary_risk_factor_non_empty(self, per_repo_results, merged_graph):
        """primary_risk_factor is a non-empty string.

        **Validates: Design Decision 8**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        prf = summary["primary_risk_factor"]
        assert isinstance(prf, str)
        assert len(prf) > 0, "primary_risk_factor is empty"

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_primary_risk_factor_no_generic_placeholder(self, per_repo_results, merged_graph):
        """primary_risk_factor never contains generic placeholder text.

        **Validates: Design Decision 8**
        """
        forbidden_phrases = [
            "assessed from available data",
            "risk level assessed",
            "unable to determine",
            "data not available",
            "assessment pending",
        ]
        summary = _compute_summary(per_repo_results, merged_graph)
        prf = summary["primary_risk_factor"].lower()
        for phrase in forbidden_phrases:
            assert phrase not in prf, (
                f"primary_risk_factor contains forbidden generic text '{phrase}': "
                f"{summary['primary_risk_factor']}"
            )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_primary_risk_factor_references_vulnerable_deps_when_present(self, per_repo_results, merged_graph):
        """When vulnerable dependencies exist (cve_count > 0), primary_risk_factor references them.

        **Validates: Design Decision 8**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        if summary["vulnerable_dependencies"] == 0:
            return  # Only check when vulnerable deps exist
        prf = summary["primary_risk_factor"].lower()
        assert "vulnerable" in prf, (
            f"With {summary['vulnerable_dependencies']} vulnerable deps, "
            f"primary_risk_factor should reference them: {summary['primary_risk_factor']}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_primary_risk_factor_references_absence_when_no_risk(self, per_repo_results, merged_graph):
        """When no risk factors exist, primary_risk_factor references absence of risk factors.

        **Validates: Design Decision 8**
        """
        summary = _compute_summary(per_repo_results, merged_graph)
        has_vuln = summary["vulnerable_dependencies"] > 0
        has_high_repos = summary["high_risk_repos"] > 0
        has_high_deps = summary["high_risk_dependencies"] > 0
        if has_vuln or has_high_repos or has_high_deps:
            return  # Only check when no risk factors
        prf = summary["primary_risk_factor"].lower()
        absence_keywords = ["no vulnerable", "no significant risk"]
        assert any(kw in prf for kw in absence_keywords), (
            f"With no risk factors, primary_risk_factor should reference absence: "
            f"{summary['primary_risk_factor']}"
        )


# ---------------------------------------------------------------------------
# Property 7: Risk driver signals have valid structure
# **Validates: Requirements 4.1**
# ---------------------------------------------------------------------------

class TestRiskDriverSignalStructureProperty:
    """Property 7: Risk driver signals have valid structure."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_signal_has_non_empty_signal_field(self, per_repo_results, merged_graph):
        """(a) Every signal has a non-empty 'signal' string.

        **Validates: Requirements 4.1**
        """
        signals = get_top_risk_drivers(per_repo_results, merged_graph)
        for s in signals:
            assert "signal" in s, f"Signal missing 'signal' field: {s}"
            assert isinstance(s["signal"], str), f"Signal 'signal' is not a string: {s}"
            assert len(s["signal"]) > 0, f"Signal 'signal' is empty: {s}"

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_signal_has_valid_category(self, per_repo_results, merged_graph):
        """(b) Every signal has a 'category' that is one of the valid values.

        **Validates: Requirements 4.1**
        """
        valid_categories = {"vulnerability", "maintenance", "dependency"}
        signals = get_top_risk_drivers(per_repo_results, merged_graph)
        for s in signals:
            assert "category" in s, f"Signal missing 'category' field: {s}"
            assert s["category"] in valid_categories, (
                f"Signal category '{s['category']}' not in {valid_categories}: {s}"
            )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_signal_has_valid_severity(self, per_repo_results, merged_graph):
        """(c) Every signal has a 'severity' that is one of the valid values.

        **Validates: Requirements 4.1**
        """
        valid_severities = {"info", "low", "medium", "high"}
        signals = get_top_risk_drivers(per_repo_results, merged_graph)
        for s in signals:
            assert "severity" in s, f"Signal missing 'severity' field: {s}"
            assert s["severity"] in valid_severities, (
                f"Signal severity '{s['severity']}' not in {valid_severities}: {s}"
            )


# ---------------------------------------------------------------------------
# Property 8: Vulnerability signals match vulnerability state
# **Validates: Requirements 4.2, 4.5**
# ---------------------------------------------------------------------------

class TestVulnerabilitySignalsProperty:
    """Property 8: Vulnerability signals match vulnerability state."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_zero_vuln_deps_produces_info_vulnerability_signal(self, per_repo_results, merged_graph):
        """When no vulnerable deps exist, output includes vulnerability/info signal.

        **Validates: Requirements 4.2**
        """
        # Count vulnerable deps in the graph
        nodes = merged_graph.get("nodes", [])
        vuln_count = sum(
            1 for n in nodes
            if n.get("type") in ("package", "dependency")
            and (n.get("metadata", {}) or {}).get("cve_count", 0) > 0
        )
        assume(vuln_count == 0)

        signals = get_top_risk_drivers(per_repo_results, merged_graph)
        vuln_info_signals = [
            s for s in signals
            if s["category"] == "vulnerability" and s["severity"] == "info"
        ]
        assert len(vuln_info_signals) >= 1, (
            f"With 0 vulnerable deps, expected a vulnerability/info signal but got: {signals}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_nonzero_vuln_deps_produces_high_vulnerability_signal(self, per_repo_results, merged_graph):
        """When N > 0 vulnerable deps exist, output includes vulnerability/high signal.

        **Validates: Requirements 4.5**
        """
        nodes = merged_graph.get("nodes", [])
        vuln_count = sum(
            1 for n in nodes
            if n.get("type") in ("package", "dependency")
            and (n.get("metadata", {}) or {}).get("cve_count", 0) > 0
        )
        assume(vuln_count > 0)

        signals = get_top_risk_drivers(per_repo_results, merged_graph)
        vuln_high_signals = [
            s for s in signals
            if s["category"] == "vulnerability" and s["severity"] == "high"
        ]
        assert len(vuln_high_signals) >= 1, (
            f"With {vuln_count} vulnerable deps, expected a vulnerability/high signal but got: {signals}"
        )


# ---------------------------------------------------------------------------
# Property 9: Maintenance signals and positive signal guarantee
# **Validates: Requirements 4.3, 4.4, 4.7**
# ---------------------------------------------------------------------------

class TestMaintenanceSignalsProperty:
    """Property 9: Maintenance signals and positive signal guarantee."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_all_low_repos_produces_maintenance_info_and_at_least_one_signal(self, per_repo_results, merged_graph):
        """When all repos are LOW risk, output includes maintenance/info signal and >= 1 total signal.

        **Validates: Requirements 4.3, 4.7**
        """
        # Only consider cases where all repos have LOW risk_label
        assume(all(r.get("risk_label") == "LOW" for r in per_repo_results))

        signals = get_top_risk_drivers(per_repo_results, merged_graph)

        # Must have at least 1 signal overall
        assert len(signals) >= 1, (
            f"Expected at least 1 signal but got empty list"
        )

        # Must include a maintenance/info signal
        maint_info = [
            s for s in signals
            if s["category"] == "maintenance" and s["severity"] == "info"
        ]
        assert len(maint_info) >= 1, (
            f"With all LOW repos, expected a maintenance/info signal but got: {signals}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_high_risk_repos_produces_maintenance_high_signal(self, per_repo_results, merged_graph):
        """When N > 0 repos have HIGH risk_label, output includes maintenance/high signal.

        **Validates: Requirements 4.4**
        """
        high_count = sum(1 for r in per_repo_results if r.get("risk_label") == "HIGH")
        assume(high_count > 0)

        signals = get_top_risk_drivers(per_repo_results, merged_graph)
        maint_high = [
            s for s in signals
            if s["category"] == "maintenance" and s["severity"] == "high"
        ]
        assert len(maint_high) >= 1, (
            f"With {high_count} HIGH repos, expected a maintenance/high signal but got: {signals}"
        )


# ---------------------------------------------------------------------------
# Property 13: Risk driver signals are ordered by severity then category
# **Validates: Design Decision 7 (Signal ordering)**
# ---------------------------------------------------------------------------

class TestSignalOrderingProperty:
    """Property 13: Risk driver signals are ordered by severity then category."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_signals_sorted_by_severity_then_category(self, per_repo_results, merged_graph):
        """Signals are sorted: high > medium > low > info; within same severity: vulnerability > maintenance > dependency.

        **Validates: Design Decision 7 (Signal ordering)**
        """
        severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        category_order = {"vulnerability": 0, "maintenance": 1, "dependency": 2}

        signals = get_top_risk_drivers(per_repo_results, merged_graph)

        for i in range(len(signals) - 1):
            curr = signals[i]
            nxt = signals[i + 1]
            curr_key = (severity_order[curr["severity"]], category_order[curr["category"]])
            nxt_key = (severity_order[nxt["severity"]], category_order[nxt["category"]])
            assert curr_key <= nxt_key, (
                f"Signal ordering violated at index {i}: "
                f"{curr} (key={curr_key}) should come before {nxt} (key={nxt_key})"
            )


# ---------------------------------------------------------------------------
# Property 6: Medium or high-risk repos guarantee non-empty priority risks
# **Validates: Requirements 3.4**
# ---------------------------------------------------------------------------

class TestPriorityRisksGuaranteeProperty:
    """Property 6: Medium or high-risk repos guarantee non-empty priority risks."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_medium_or_high_risk_repos_produce_non_empty_priority_risks(self, per_repo_results, merged_graph):
        """When at least one repo has MEDIUM or HIGH risk_label, compute_priority_risks() returns non-empty list.

        **Validates: Requirements 3.4**
        """
        # Only consider cases where at least one repo has MEDIUM or HIGH risk
        assume(any(
            r.get("risk_label") in ("MEDIUM", "HIGH")
            for r in per_repo_results
        ))

        risks = compute_priority_risks(per_repo_results, merged_graph)
        assert len(risks) >= 1, (
            f"Expected at least 1 priority risk when MEDIUM/HIGH repos exist, "
            f"but got empty list. per_repo_results: {per_repo_results}"
        )


# Need compute_top_risky_dependencies for Property 2
from app import merge_graphs, compute_top_risky_dependencies


# ---------------------------------------------------------------------------
# Strategy: unmapped dependency names
# ---------------------------------------------------------------------------

unmapped_dep_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=3, max_size=20,
)


# ---------------------------------------------------------------------------
# Property 1: Unmapped dependencies are counted in total_unique_dependencies
# **Validates: Requirements 1.1, 1.2**
# ---------------------------------------------------------------------------

class TestUnmappedDepsCountedProperty:
    """Property 1: Unmapped dependencies are counted in total_unique_dependencies."""

    @given(
        unmapped_names=st.lists(
            unmapped_dep_name_st,
            min_size=1, max_size=10,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_total_unique_dependencies_gte_unmapped_count(self, unmapped_names):
        """For any list of unmapped dependency names, total_unique_dependencies >= len(unmapped_names).

        **Validates: Requirements 1.1, 1.2**
        """
        unmapped_nodes = [
            {"id": f"pkg:{name}", "type": "package", "label": name}
            for name in unmapped_names
        ]
        merged = merge_graphs([], unmapped_nodes)
        summary = compute_system_risk_summary([], merged)
        assert summary["total_unique_dependencies"] >= len(unmapped_names), (
            f"total_unique_dependencies ({summary['total_unique_dependencies']}) "
            f"< unmapped count ({len(unmapped_names)})"
        )


# ---------------------------------------------------------------------------
# Property 2: Unmapped dependencies appear in risky deps with default values
# **Validates: Requirements 1.3, 5.2**
# ---------------------------------------------------------------------------

class TestUnmappedDepsDefaultValuesProperty:
    """Property 2: Unmapped dependencies appear in risky deps with default values."""

    @given(
        unmapped_names=st.lists(
            unmapped_dep_name_st,
            min_size=1, max_size=10,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_unmapped_deps_have_default_risk_values(self, unmapped_names):
        """For any unmapped package nodes, compute_top_risky_dependencies() includes each
        with risk_score=0, risk_label='LOW', cve_count=0.

        **Validates: Requirements 1.3, 5.2**
        """
        unmapped_nodes = [
            {"id": f"pkg:{name}", "type": "package", "label": name}
            for name in unmapped_names
        ]
        merged = merge_graphs([], unmapped_nodes)
        risky_deps = compute_top_risky_dependencies(merged)

        # Build lookup by package_name
        dep_lookup = {d["package_name"]: d for d in risky_deps}

        for name in unmapped_names:
            assert name in dep_lookup, (
                f"Unmapped dep '{name}' not found in risky deps output. "
                f"Got: {[d['package_name'] for d in risky_deps]}"
            )
            dep = dep_lookup[name]
            assert dep["risk_score"] == 0, (
                f"Expected risk_score=0 for '{name}', got {dep['risk_score']}"
            )
            assert dep["risk_label"] == "LOW", (
                f"Expected risk_label='LOW' for '{name}', got {dep['risk_label']}"
            )
            assert dep["cve_count"] == 0, (
                f"Expected cve_count=0 for '{name}', got {dep['cve_count']}"
            )


# ---------------------------------------------------------------------------
# Property 10: Insight statements count invariant
# **Validates: Requirements 6.2, 6.7**
# ---------------------------------------------------------------------------

class TestInsightStatementsCountProperty:
    """Property 10: Insight statements count invariant."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=0, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100)
    def test_insight_statements_between_1_and_6(self, per_repo_results, merged_graph):
        """compute_insight_statements() returns between 1 and 6 non-empty strings.

        **Validates: Requirements 6.2, 6.7**
        """
        summary = compute_system_risk_summary(per_repo_results, merged_graph)
        statements = compute_insight_statements(summary, per_repo_results, merged_graph)

        assert isinstance(statements, list), (
            f"Expected list, got {type(statements)}"
        )
        assert 1 <= len(statements) <= 6, (
            f"Expected 1–6 statements, got {len(statements)}: {statements}"
        )
        for stmt in statements:
            assert isinstance(stmt, str), (
                f"Expected string, got {type(stmt)}: {stmt}"
            )
            assert len(stmt) > 0, "Insight statement is empty"


# ---------------------------------------------------------------------------
# Property 11: Insight statement content matches input conditions
# **Validates: Requirements 6.3, 6.4, 6.5, 6.6**
# ---------------------------------------------------------------------------

class TestInsightStatementContentProperty:
    """Property 11: Insight statement content matches input conditions."""

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=0, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_no_vulnerable_deps_produces_clean_supply_chain_statement(self, per_repo_results, merged_graph):
        """When no vulnerable dependencies exist, output includes a statement about clean supply chain.

        **Validates: Requirements 6.3**
        """
        summary = compute_system_risk_summary(per_repo_results, merged_graph)
        assume(summary.get("vulnerable_dependencies", 0) == 0)

        statements = compute_insight_statements(summary, per_repo_results, merged_graph)
        joined = " ".join(s.lower() for s in statements)
        assert "supply chain" in joined or "clean" in joined, (
            f"With 0 vulnerable deps, expected a statement about clean supply chain. "
            f"Got: {statements}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_all_low_risk_repos_produces_consistent_maintenance_statement(self, per_repo_results, merged_graph):
        """When all repos show low maintenance risk, output includes a statement about consistent maintenance.

        **Validates: Requirements 6.4**
        """
        assume(all(r.get("risk_label") == "LOW" for r in per_repo_results))

        summary = compute_system_risk_summary(per_repo_results, merged_graph)
        statements = compute_insight_statements(summary, per_repo_results, merged_graph)
        joined = " ".join(s.lower() for s in statements)
        assert "maintenance practices" in joined or "consistent" in joined, (
            f"With all LOW repos, expected a statement about consistent maintenance. "
            f"Got: {statements}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_high_risk_repos_produces_attention_statement(self, per_repo_results, merged_graph):
        """When N high-risk repos exist (N > 0), output includes a statement referencing those repos.

        **Validates: Requirements 6.5**
        """
        high_count = sum(1 for r in per_repo_results if r.get("risk_label") == "HIGH")
        assume(high_count > 0)

        summary = compute_system_risk_summary(per_repo_results, merged_graph)
        statements = compute_insight_statements(summary, per_repo_results, merged_graph)
        joined = " ".join(s.lower() for s in statements)
        assert "attention" in joined or "elevated maintenance risk" in joined, (
            f"With {high_count} HIGH repos, expected a statement about attention/elevated risk. "
            f"Got: {statements}"
        )

    @given(
        per_repo_results=st.lists(consistent_per_repo_result_st(), min_size=0, max_size=8),
        merged_graph=merged_graph_st(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_shared_deps_produces_concentration_statement(self, per_repo_results, merged_graph):
        """When M dependencies are shared across multiple repos (M >= 2), output includes a statement about concentration.

        **Validates: Requirements 6.6**
        """
        summary = compute_system_risk_summary(per_repo_results, merged_graph)
        assume(summary.get("dependencies_used_by_multiple_repos", 0) >= 2)

        statements = compute_insight_statements(summary, per_repo_results, merged_graph)
        joined = " ".join(s.lower() for s in statements)
        assert "shared" in joined or "concentration" in joined, (
            f"With {summary['dependencies_used_by_multiple_repos']} shared deps, "
            f"expected a statement about concentration. Got: {statements}"
        )
