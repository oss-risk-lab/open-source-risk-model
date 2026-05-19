"""
Unit tests for scope_risk.py weight map and data models.

Feature: scope-weighted-risk
Task 1.3: Write unit tests for weight map and data models

Requirements: 1.1, 1.3, 1.4, 6.1–6.4
"""

from __future__ import annotations

import pytest

from src.open_source_risk_model.tree.scope_risk import (
    DEFAULT_SCOPE_WEIGHTS,
    ExplainabilityPayload,
    TopDriver,
    get_scope_weight,
)


# ======================================================================
# Weight Map Tests (Req 1.1, 1.3, 1.4)
# ======================================================================


class TestDefaultScopeWeights:
    """Verify DEFAULT_SCOPE_WEIGHTS constant structure and values."""

    def test_has_seven_entries(self):
        """DEFAULT_SCOPE_WEIGHTS SHALL define weights for all seven scope values (Req 1.1)."""
        assert len(DEFAULT_SCOPE_WEIGHTS) == 7

    def test_correct_values(self):
        """Each scope weight SHALL match the specified default (Req 1.1)."""
        expected = {
            "runtime": 1.00,
            "optional": 0.75,
            "peer": 0.65,
            "build": 0.50,
            "test": 0.35,
            "dev": 0.25,
            "unknown": 0.40,
        }
        assert DEFAULT_SCOPE_WEIGHTS == expected

    def test_unknown_between_dev_and_build(self):
        """Unknown weight SHALL be greater than dev (0.25) and less than build (0.50) (Req 1.3)."""
        assert DEFAULT_SCOPE_WEIGHTS["dev"] < DEFAULT_SCOPE_WEIGHTS["unknown"] < DEFAULT_SCOPE_WEIGHTS["build"]


class TestGetScopeWeightCustomOverride:
    """Verify get_scope_weight with custom weights overrides defaults (Req 1.4)."""

    def test_custom_weights_override_defaults(self):
        """When custom weights are provided, they SHALL be used instead of defaults."""
        custom = {
            "runtime": 0.50,
            "dev": 0.10,
            "unknown": 0.20,
        }
        assert get_scope_weight("runtime", custom) == 0.50
        assert get_scope_weight("dev", custom) == 0.10

    def test_custom_weights_unknown_fallback(self):
        """When scope is missing from custom weights, fall back to custom unknown entry."""
        custom = {"unknown": 0.99}
        assert get_scope_weight("nonexistent", custom) == 0.99

    def test_custom_weights_no_unknown_falls_to_hardcoded(self):
        """When custom weights lack both the scope and 'unknown', fall back to 0.40."""
        custom = {"runtime": 0.80}
        assert get_scope_weight("nonexistent", custom) == 0.40


# ======================================================================
# ExplainabilityPayload Tests (Req 6.1–6.4)
# ======================================================================


class TestExplainabilityPayloadToDict:
    """Verify ExplainabilityPayload.to_dict() produces all required fields."""

    @pytest.fixture()
    def sample_payload(self) -> ExplainabilityPayload:
        return ExplainabilityPayload(
            scope_weighted_dependency_risk=0.42,
            risk_label="medium",
            top_drivers=[
                TopDriver(
                    package="requests",
                    scope="runtime",
                    reason="High risk runtime dependency",
                    contribution=0.65,
                ),
                TopDriver(
                    package="pytest",
                    scope="test",
                    reason="Vulnerable test dependency",
                    contribution=0.20,
                ),
            ],
            scope_note="Dependency scope is classified from manifests and may not reflect actual runtime usage.",
            confidence_note="High confidence: most dependencies have classified scope, providing reliable runtime exposure estimates.",
        )

    def test_to_dict_has_all_required_fields(self, sample_payload: ExplainabilityPayload):
        """to_dict() SHALL produce all required fields (Req 6.1–6.4)."""
        d = sample_payload.to_dict()
        assert "scope_weighted_dependency_risk" in d
        assert "risk_label" in d
        assert "top_drivers" in d
        assert "scope_note" in d
        assert "confidence_note" in d

    def test_to_dict_score_value(self, sample_payload: ExplainabilityPayload):
        """scope_weighted_dependency_risk SHALL be a float in [0.0, 1.0] (Req 6.1)."""
        d = sample_payload.to_dict()
        assert isinstance(d["scope_weighted_dependency_risk"], float)
        assert 0.0 <= d["scope_weighted_dependency_risk"] <= 1.0

    def test_to_dict_risk_label(self, sample_payload: ExplainabilityPayload):
        """risk_label SHALL be one of {low, medium, high} (Req 6.2)."""
        d = sample_payload.to_dict()
        assert d["risk_label"] in {"low", "medium", "high"}

    def test_to_dict_top_drivers_structure(self, sample_payload: ExplainabilityPayload):
        """Each top_driver SHALL have package, scope, reason, contribution (Req 6.3)."""
        d = sample_payload.to_dict()
        assert isinstance(d["top_drivers"], list)
        assert len(d["top_drivers"]) == 2
        for driver in d["top_drivers"]:
            assert "package" in driver
            assert "scope" in driver
            assert "reason" in driver
            assert "contribution" in driver

    def test_to_dict_scope_note_static_string(self, sample_payload: ExplainabilityPayload):
        """scope_note SHALL be the expected static string (Req 6.4)."""
        d = sample_payload.to_dict()
        assert d["scope_note"] == (
            "Dependency scope is classified from manifests and may not reflect actual runtime usage."
        )

    def test_to_dict_confidence_note_present(self, sample_payload: ExplainabilityPayload):
        """confidence_note SHALL be a non-empty string (Req 6.4)."""
        d = sample_payload.to_dict()
        assert isinstance(d["confidence_note"], str)
        assert len(d["confidence_note"]) > 0

    def test_to_dict_empty_drivers(self):
        """to_dict() with empty top_drivers SHALL produce an empty list."""
        payload = ExplainabilityPayload(
            scope_weighted_dependency_risk=0.0,
            risk_label="low",
            top_drivers=[],
            scope_note="Dependency scope is classified from manifests and may not reflect actual runtime usage.",
            confidence_note="Scope data is not available for this repository.",
        )
        d = payload.to_dict()
        assert d["top_drivers"] == []
        assert d["scope_weighted_dependency_risk"] == 0.0
        assert d["risk_label"] == "low"


# ======================================================================
# Additional imports for compute_scope_weighted_risk unit tests
# ======================================================================

from src.open_source_risk_model.tree.scope_risk import (
    DependencyInput,
    compute_scope_weighted_risk,
    _classify_risk_label,
)


# ======================================================================
# compute_scope_weighted_risk Unit Tests (Req 3.1–3.13, 4.1–4.4)
# ======================================================================


class TestComputeScopeWeightedRiskEmpty:
    """Test empty input returns score=0.0 and empty top_drivers (Req 3.12)."""

    def test_empty_list_returns_zero_score(self):
        """Empty input SHALL return score=0.0."""
        result = compute_scope_weighted_risk([])
        assert result.scope_weighted_dependency_risk == 0.0

    def test_empty_list_returns_low_label(self):
        """Empty input SHALL return risk_label='low'."""
        result = compute_scope_weighted_risk([])
        assert result.risk_label == "low"

    def test_empty_list_returns_empty_top_drivers(self):
        """Empty input SHALL return empty top_drivers list."""
        result = compute_scope_weighted_risk([])
        assert result.top_drivers == []


class TestComputeScopeWeightedRiskRuntimeVsDev:
    """Test single runtime dependency vs single dev dependency (Req 3.13)."""

    def test_runtime_higher_than_dev(self):
        """A runtime dep SHALL produce a higher score than a dev dep with same risk."""
        runtime_dep = DependencyInput(
            package_name="express",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=3,
            risk_score=75.0,
            dependency_type="direct",
        )
        dev_dep = DependencyInput(
            package_name="express",
            dependency_scope="dev",
            scope_confidence="high",
            vulnerability_count=3,
            risk_score=75.0,
            dependency_type="direct",
        )

        runtime_result = compute_scope_weighted_risk([runtime_dep])
        dev_result = compute_scope_weighted_risk([dev_dep])

        assert runtime_result.scope_weighted_dependency_risk > dev_result.scope_weighted_dependency_risk

    def test_runtime_dep_is_top_driver(self):
        """When both runtime and dev deps exist, runtime should rank higher in top_drivers."""
        runtime_dep = DependencyInput(
            package_name="express",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=2,
            risk_score=80.0,
            dependency_type="direct",
        )
        dev_dep = DependencyInput(
            package_name="jest",
            dependency_scope="dev",
            scope_confidence="high",
            vulnerability_count=2,
            risk_score=80.0,
            dependency_type="direct",
        )

        result = compute_scope_weighted_risk([runtime_dep, dev_dep])
        assert len(result.top_drivers) == 2
        assert result.top_drivers[0].package == "express"
        assert result.top_drivers[0].scope == "runtime"


class TestComputeScopeWeightedRiskNullScope:
    """Test null/missing scope treated as unknown (Req 3.8)."""

    def test_none_scope_treated_as_unknown(self):
        """A dependency with dependency_scope=None SHALL be treated as 'unknown'."""
        dep = DependencyInput(
            package_name="mystery-pkg",
            dependency_scope=None,
            scope_confidence="high",
            vulnerability_count=1,
            risk_score=50.0,
            dependency_type="direct",
        )
        result = compute_scope_weighted_risk([dep])

        # Should produce a valid score (not crash)
        assert 0.0 <= result.scope_weighted_dependency_risk <= 1.0

        # The top driver scope should be "unknown"
        if result.top_drivers:
            assert result.top_drivers[0].scope == "unknown"

    def test_empty_string_scope_treated_as_unknown(self):
        """A dependency with dependency_scope='' SHALL be treated as 'unknown'."""
        dep = DependencyInput(
            package_name="mystery-pkg",
            dependency_scope="",
            scope_confidence="medium",
            vulnerability_count=0,
            risk_score=60.0,
            dependency_type="transitive",
        )
        result = compute_scope_weighted_risk([dep])
        assert 0.0 <= result.scope_weighted_dependency_risk <= 1.0

        if result.top_drivers:
            assert result.top_drivers[0].scope == "unknown"


# ======================================================================
# SummaryMetrics Extension Tests (Req 8.3, 8.5)
# Task 5.3: Verify new exposure fields on SummaryMetrics
# ======================================================================

from src.open_source_risk_model.tree.models import SummaryMetrics


class TestSummaryMetricsExistingFieldsUnchanged:
    """Verify existing fields remain unchanged after adding new Phase 4 fields (Req 8.3)."""

    def test_default_existing_fields_unchanged(self):
        """Creating SummaryMetrics with defaults SHALL preserve all existing field defaults."""
        m = SummaryMetrics()
        assert m.total_dependencies == 0
        assert m.direct_dependencies == 0
        assert m.transitive_dependencies == 0
        assert m.high_risk_count == 0
        assert m.vulnerable_count == 0
        assert m.max_depth == 0
        assert m.riskiest_branch is None
        assert m.filters_applied == []
        # Phase 1 scope counts
        assert m.direct_runtime_dependency_count == 0
        assert m.direct_dev_dependency_count == 0
        assert m.direct_test_dependency_count == 0
        assert m.direct_build_dependency_count == 0
        assert m.direct_optional_dependency_count == 0
        assert m.direct_peer_dependency_count == 0
        assert m.direct_unknown_dependency_count == 0
        assert m.direct_total_dependency_count == 0
        assert m.scope_counts_are_direct_only is True
        assert m.transitive_runtime_dependency_count == 0

    def test_new_phase4_fields_default_to_zero(self):
        """New Phase 4 exposure fields SHALL default to 0 / 0.0."""
        m = SummaryMetrics()
        assert m.runtime_dependency_exposure == 0.0
        assert m.transitive_runtime_dependency_exposure == 0.0
        assert m.scope_weighted_dependency_exposure == 0.0
        assert m.vulnerable_runtime_dependency_count == 0
        assert m.vulnerable_transitive_runtime_dependency_count == 0
        assert m.high_risk_runtime_dependency_count == 0
        assert m.unknown_scope_dependency_ratio == 0.0


class TestSummaryMetricsToDictNewFields:
    """Verify new fields serialize correctly in to_dict() (Req 8.5)."""

    def test_new_fields_appear_in_to_dict(self):
        """to_dict() SHALL include all new Phase 4 exposure fields."""
        m = SummaryMetrics(
            runtime_dependency_exposure=0.75,
            transitive_runtime_dependency_exposure=0.5,
            scope_weighted_dependency_exposure=0.6,
            vulnerable_runtime_dependency_count=3,
            vulnerable_transitive_runtime_dependency_count=1,
            high_risk_runtime_dependency_count=2,
            unknown_scope_dependency_ratio=0.1,
        )
        d = m.to_dict()
        assert d["runtime_dependency_exposure"] == 0.75
        assert d["transitive_runtime_dependency_exposure"] == 0.5
        assert d["scope_weighted_dependency_exposure"] == 0.6
        assert d["vulnerable_runtime_dependency_count"] == 3
        assert d["vulnerable_transitive_runtime_dependency_count"] == 1
        assert d["high_risk_runtime_dependency_count"] == 2
        assert d["unknown_scope_dependency_ratio"] == 0.1

    def test_existing_fields_still_in_to_dict(self):
        """to_dict() SHALL still include all existing fields (Req 8.3)."""
        m = SummaryMetrics(total_dependencies=10, direct_dependencies=5)
        d = m.to_dict()
        assert d["total_dependencies"] == 10
        assert d["direct_dependencies"] == 5
        assert "high_risk_count" in d
        assert "vulnerable_count" in d
        assert "max_depth" in d
        assert "filters_applied" in d
        assert "direct_runtime_dependency_count" in d
        assert "transitive_runtime_dependency_count" in d


# ======================================================================
# Insight Layer Integration Tests (Req 5.6, 8.1, 8.2)
# Task 6.6: Verify insight layer integration
# ======================================================================

from unittest.mock import MagicMock

from src.open_source_risk_model.insights.compute import (
    compute_repo_insight,
    compute_scope_aware_reasons,
)
from src.open_source_risk_model.insights.models import RepoInsight


class TestRepoInsightScopeWeightedRiskField:
    """Verify scope_weighted_risk field on RepoInsight (Req 7.2, 8.1, 8.2)."""

    def test_scope_weighted_risk_defaults_to_none(self):
        """scope_weighted_risk SHALL default to None."""
        insight = RepoInsight(repo_full_name="owner/repo")
        assert insight.scope_weighted_risk is None

    def test_existing_fields_unchanged_with_scope_weighted_risk(self):
        """Existing fields SHALL remain unchanged when scope_weighted_risk is set (Req 8.1, 8.2)."""
        insight = RepoInsight(
            repo_full_name="owner/repo",
            base_maintenance_risk=0.45,
            base_maintenance_label="MEDIUM",
            graph_signal_score=0.35,
            graph_signal_label="MEDIUM",
            reasons=["Some existing reason"],
            scope_weighted_risk={"scope_weighted_dependency_risk": 0.5, "risk_label": "medium"},
        )
        assert insight.base_maintenance_risk == 0.45
        assert insight.base_maintenance_label == "MEDIUM"
        assert insight.graph_signal_score == 0.35
        assert insight.graph_signal_label == "MEDIUM"

    def test_to_dict_includes_scope_weighted_risk_when_present(self):
        """to_dict() SHALL include scope_weighted_risk when it is not None."""
        payload_dict = {
            "scope_weighted_dependency_risk": 0.42,
            "risk_label": "medium",
            "top_drivers": [],
            "scope_note": "test note",
            "confidence_note": "test confidence",
        }
        insight = RepoInsight(
            repo_full_name="owner/repo",
            scope_weighted_risk=payload_dict,
        )
        d = insight.to_dict()
        assert "scope_weighted_risk" in d
        assert d["scope_weighted_risk"] == payload_dict

    def test_to_dict_excludes_scope_weighted_risk_when_none(self):
        """to_dict() SHALL NOT include scope_weighted_risk when it is None."""
        insight = RepoInsight(repo_full_name="owner/repo")
        d = insight.to_dict()
        assert "scope_weighted_risk" not in d

    def test_to_dict_preserves_existing_fields(self):
        """to_dict() SHALL still include all existing fields (Req 8.1, 8.2)."""
        insight = RepoInsight(
            repo_full_name="owner/repo",
            base_maintenance_risk=0.6,
            base_maintenance_label="HIGH",
            graph_signal_score=0.5,
            graph_signal_label="MEDIUM",
            reasons=["Existing reason"],
        )
        d = insight.to_dict()
        assert d["base_maintenance_risk"] == 0.6
        assert d["base_maintenance_label"] == "HIGH"
        assert d["graph_signal_score"] == 0.5
        assert d["graph_signal_label"] == "MEDIUM"
        assert d["reasons"] == ["Existing reason"]


class TestScopeAwareReasonsAppended:
    """Verify scope-aware reasons are appended, not replacing existing reasons (Req 5.6)."""

    def test_scope_reasons_appended_to_existing(self):
        """Scope-aware reasons SHALL be appended to existing reasons, not replace them."""
        # Create a mock graph_repo that returns graph data with package nodes
        graph_repo = MagicMock()
        graph_repo.get_graph.return_value = {
            "graph": {
                "nodes": [
                    {
                        "type": "repo",
                        "metadata": {
                            "maintenance_risk": 0.5,
                            "maintenance_label": "MEDIUM",
                        },
                    },
                    {
                        "type": "cve",
                        "metadata": {
                            "cve_id": "CVE-2024-001",
                            "severity": "AV:N/AC:L",
                            "cvss_score": 8.0,
                        },
                    },
                    {
                        "type": "maintainer",
                        "metadata": {
                            "username": "dev1",
                            "contribution_fraction": 0.4,
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
                    # Package nodes with runtime scope and vulnerabilities
                    {
                        "type": "package",
                        "label": "express",
                        "metadata": {
                            "package_name": "express",
                            "dependency_scope": "runtime",
                            "scope_confidence": "high",
                            "vulnerability_count": 2,
                            "risk_score": 75.0,
                            "depth": 1,
                        },
                    },
                ],
            }
        }

        result = compute_repo_insight("owner/repo", graph_repo)

        # Existing reasons from graph signals should be present
        # (CVE signal with high severity should produce a reason)
        assert any("CVE" in r for r in result.reasons), (
            f"Expected CVE-related reason in {result.reasons}"
        )

        # Scope-aware reasons should also be present (vulnerable runtime paths)
        assert any("runtime" in r.lower() for r in result.reasons), (
            f"Expected scope-aware reason in {result.reasons}"
        )

        # scope_weighted_risk should be set
        assert result.scope_weighted_risk is not None
        assert "scope_weighted_dependency_risk" in result.scope_weighted_risk

    def test_no_scope_reasons_when_no_package_nodes(self):
        """When no package nodes exist, safe defaults should be used (Req 7.4)."""
        graph_repo = MagicMock()
        graph_repo.get_graph.return_value = {
            "graph": {
                "nodes": [
                    {
                        "type": "repo",
                        "metadata": {
                            "maintenance_risk": 0.3,
                            "maintenance_label": "LOW",
                        },
                    },
                ],
            }
        }

        result = compute_repo_insight("owner/repo", graph_repo)

        # scope_weighted_risk should be safe defaults
        assert result.scope_weighted_risk is not None
        assert result.scope_weighted_risk["scope_weighted_dependency_risk"] == 0.0
        assert result.scope_weighted_risk["risk_label"] == "low"
        assert result.scope_weighted_risk["top_drivers"] == []
        assert "not available" in result.scope_weighted_risk["confidence_note"].lower()


class TestComputeScopeAwareReasons:
    """Unit tests for the compute_scope_aware_reasons helper function."""

    def test_empty_deps_returns_empty(self):
        """Empty dependency list SHALL return empty reasons."""
        assert compute_scope_aware_reasons([]) == []

    def test_all_unknown_scopes_returns_empty(self):
        """When all scopes are unknown, no scope-aware reasons SHALL be generated (Req 5.7)."""
        deps = [
            DependencyInput(
                package_name="pkg1",
                dependency_scope="unknown",
                scope_confidence="low",
                vulnerability_count=5,
                risk_score=80.0,
                dependency_type="direct",
            ),
            DependencyInput(
                package_name="pkg2",
                dependency_scope="unknown",
                scope_confidence="low",
                vulnerability_count=3,
                risk_score=60.0,
                dependency_type="transitive",
            ),
        ]
        assert compute_scope_aware_reasons(deps) == []

    def test_vulnerable_runtime_generates_reason(self):
        """Vulnerable runtime dependency SHALL generate appropriate reason (Req 5.3)."""
        deps = [
            DependencyInput(
                package_name="express",
                dependency_scope="runtime",
                scope_confidence="high",
                vulnerability_count=2,
                risk_score=75.0,
                dependency_type="direct",
            ),
        ]
        reasons = compute_scope_aware_reasons(deps)
        assert "Several vulnerable dependencies appear in runtime-relevant paths." in reasons

    def test_dev_test_majority_generates_reason(self):
        """Dev/test majority SHALL generate appropriate reason (Req 5.4)."""
        deps = [
            DependencyInput(
                package_name="pytest",
                dependency_scope="test",
                scope_confidence="high",
                vulnerability_count=0,
                risk_score=10.0,
                dependency_type="direct",
            ),
            DependencyInput(
                package_name="eslint",
                dependency_scope="dev",
                scope_confidence="high",
                vulnerability_count=0,
                risk_score=5.0,
                dependency_type="direct",
            ),
            DependencyInput(
                package_name="express",
                dependency_scope="runtime",
                scope_confidence="high",
                vulnerability_count=0,
                risk_score=10.0,
                dependency_type="direct",
            ),
        ]
        reasons = compute_scope_aware_reasons(deps)
        assert "Most dependencies are dev/test scoped, reducing likely production exposure." in reasons
