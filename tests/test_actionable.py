"""
Tests for actionable insights data models and functions (Phase 5).

Feature: actionable-insights, Property 8: Serialization Round-Trip

Uses Hypothesis for property-based tests and pytest for unit tests.
"""

from __future__ import annotations

import json
import string
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given, settings, strategies as st

from open_source_risk_model.insights.actionable import (
    ActionableInsight,
    OverallConfidence,
    RepoSnapshotDiff,
    RiskCluster,
    RiskNarrative,
    compare_repo_snapshots,
    compute_overall_confidence,
    generate_priority_recommendations,
    generate_risk_clusters,
    generate_risk_narrative,
)
from open_source_risk_model.insights.models import RepoInsight
from open_source_risk_model.tree.scope_risk import (
    CONFIDENCE_MODIFIERS,
    DEFAULT_SCOPE_WEIGHTS,
    DependencyInput,
    _deduplicate,
    _normalized_risk,
    get_scope_weight,
)


# ======================================================================
# Strategies for generating random data model instances
# ======================================================================

VALID_SCOPES = ["runtime", "dev", "test", "build", "optional", "peer", "unknown"]
VALID_CONFIDENCES = ["high", "medium", "low"]
VALID_TYPES = ["direct", "transitive"]

# Package name strategy
package_name_st = st.text(
    min_size=1,
    max_size=50,
    alphabet=string.ascii_lowercase + string.digits + "-_.",
)

# Float strategies
priority_score_st = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
risk_contribution_st = st.floats(
    min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
)
confidence_score_st = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
risk_score_change_st = st.floats(
    min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False
)

# String strategies
reason_st = st.text(min_size=1, max_size=200)
action_st = st.sampled_from([
    "Upgrade to patched version",
    "Review high-risk dependency",
    "Investigate unknown scope",
    "Monitor dependency risk",
])
label_st = st.sampled_from(["high", "medium", "low"])
explanation_st = st.text(min_size=1, max_size=200)
summary_st = st.text(min_size=1, max_size=300)
recommendation_st = st.text(min_size=0, max_size=200)

# List strategies
key_findings_st = st.lists(st.text(min_size=1, max_size=100), min_size=0, max_size=5)
example_packages_st = st.lists(package_name_st, min_size=0, max_size=3)
dep_list_st = st.lists(package_name_st, min_size=0, max_size=10)


# Composite strategies for each data model
@st.composite
def actionable_insight_st(draw):
    return ActionableInsight(
        package_name=draw(package_name_st),
        dependency_scope=draw(st.sampled_from(VALID_SCOPES)),
        dependency_type=draw(st.sampled_from(VALID_TYPES)),
        reason=draw(reason_st),
        priority_score=draw(priority_score_st),
        action=draw(action_st),
    )


@st.composite
def risk_cluster_st(draw):
    return RiskCluster(
        cluster_name=draw(st.text(min_size=1, max_size=50)),
        summary=draw(summary_st),
        count=draw(st.integers(min_value=0, max_value=100)),
        risk_contribution=draw(risk_contribution_st),
        example_packages=draw(example_packages_st),
    )


@st.composite
def risk_narrative_st(draw):
    return RiskNarrative(
        summary=draw(summary_st),
        key_findings=draw(key_findings_st),
        recommendation=draw(recommendation_st),
    )


@st.composite
def overall_confidence_st(draw):
    return OverallConfidence(
        score=draw(confidence_score_st),
        label=draw(label_st),
        explanation=draw(explanation_st),
    )


@st.composite
def repo_snapshot_diff_st(draw):
    return RepoSnapshotDiff(
        new_risky_dependencies=draw(dep_list_st),
        removed_dependencies=draw(dep_list_st),
        risk_score_change=draw(risk_score_change_st),
        risk_label_change=draw(st.one_of(st.none(), st.text(min_size=1, max_size=30))),
    )


# ======================================================================
# Property 8: Serialization Round-Trip
# Feature: actionable-insights, Property 8: Serialization Round-Trip
# ======================================================================


class TestSerializationRoundTrip:
    """Property 8: Serialization Round-Trip.

    Generate random instances of all 5 data models, verify to_dict() →
    json.dumps() → json.loads() preserves field values, numeric precision
    to 6 decimal places, and list element ordering.

    **Validates: Requirements 1.5, 14.1, 14.2, 14.3, 14.4, 14.5**
    """

    @given(insight=actionable_insight_st())
    @settings(max_examples=100)
    def test_actionable_insight_round_trip(self, insight: ActionableInsight):
        """ActionableInsight serialization round-trip preserves all fields."""
        d = insight.to_dict()
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)

        assert deserialized["package_name"] == insight.package_name
        assert deserialized["dependency_scope"] == insight.dependency_scope
        assert deserialized["dependency_type"] == insight.dependency_type
        assert deserialized["reason"] == insight.reason
        assert deserialized["action"] == insight.action
        assert deserialized["priority_score"] == round(insight.priority_score, 6)

    @given(cluster=risk_cluster_st())
    @settings(max_examples=100)
    def test_risk_cluster_round_trip(self, cluster: RiskCluster):
        """RiskCluster serialization round-trip preserves all fields."""
        d = cluster.to_dict()
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)

        assert deserialized["cluster_name"] == cluster.cluster_name
        assert deserialized["summary"] == cluster.summary
        assert deserialized["count"] == cluster.count
        assert deserialized["risk_contribution"] == round(cluster.risk_contribution, 6)
        assert deserialized["example_packages"] == list(cluster.example_packages)

    @given(narrative=risk_narrative_st())
    @settings(max_examples=100)
    def test_risk_narrative_round_trip(self, narrative: RiskNarrative):
        """RiskNarrative serialization round-trip preserves all fields."""
        d = narrative.to_dict()
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)

        assert deserialized["summary"] == narrative.summary
        assert deserialized["key_findings"] == list(narrative.key_findings)
        assert deserialized["recommendation"] == narrative.recommendation

    @given(confidence=overall_confidence_st())
    @settings(max_examples=100)
    def test_overall_confidence_round_trip(self, confidence: OverallConfidence):
        """OverallConfidence serialization round-trip preserves all fields."""
        d = confidence.to_dict()
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)

        assert deserialized["score"] == round(confidence.score, 6)
        assert deserialized["label"] == confidence.label
        assert deserialized["explanation"] == confidence.explanation

    @given(diff=repo_snapshot_diff_st())
    @settings(max_examples=100)
    def test_repo_snapshot_diff_round_trip(self, diff: RepoSnapshotDiff):
        """RepoSnapshotDiff serialization round-trip preserves all fields."""
        d = diff.to_dict()
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)

        assert deserialized["new_risky_dependencies"] == list(diff.new_risky_dependencies)
        assert deserialized["removed_dependencies"] == list(diff.removed_dependencies)
        assert deserialized["risk_score_change"] == round(diff.risk_score_change, 6)
        assert deserialized["risk_label_change"] == diff.risk_label_change


# ======================================================================
# Unit Tests: Data Model Construction and Serialization (Task 1.3)
# ======================================================================


class TestDataModelFrozen:
    """Verify each dataclass is frozen (immutable)."""

    def test_actionable_insight_is_frozen(self):
        """ActionableInsight is immutable — setting attribute raises FrozenInstanceError."""
        insight = ActionableInsight(
            package_name="lodash",
            dependency_scope="runtime",
            dependency_type="direct",
            reason="runtime-scoped: 3 known CVE(s)",
            priority_score=0.85,
            action="Upgrade to patched version",
        )
        with pytest.raises(FrozenInstanceError):
            insight.package_name = "other"  # type: ignore[misc]

    def test_risk_cluster_is_frozen(self):
        """RiskCluster is immutable — setting attribute raises FrozenInstanceError."""
        cluster = RiskCluster(
            cluster_name="Runtime Risk Cluster",
            summary="Dependencies in runtime scope with elevated risk.",
            count=5,
            risk_contribution=0.65,
            example_packages=["lodash", "express"],
        )
        with pytest.raises(FrozenInstanceError):
            cluster.count = 10  # type: ignore[misc]

    def test_risk_narrative_is_frozen(self):
        """RiskNarrative is immutable — setting attribute raises FrozenInstanceError."""
        narrative = RiskNarrative(
            summary="This repository has moderate dependency risk.",
            key_findings=["Finding 1"],
            recommendation="Review runtime dependencies.",
        )
        with pytest.raises(FrozenInstanceError):
            narrative.summary = "changed"  # type: ignore[misc]

    def test_overall_confidence_is_frozen(self):
        """OverallConfidence is immutable — setting attribute raises FrozenInstanceError."""
        confidence = OverallConfidence(
            score=0.75,
            label="high",
            explanation="Most dependencies have classified scope.",
        )
        with pytest.raises(FrozenInstanceError):
            confidence.score = 0.5  # type: ignore[misc]

    def test_repo_snapshot_diff_is_frozen(self):
        """RepoSnapshotDiff is immutable — setting attribute raises FrozenInstanceError."""
        diff = RepoSnapshotDiff(
            new_risky_dependencies=["axios"],
            removed_dependencies=["moment"],
            risk_score_change=0.15,
            risk_label_change="low → medium",
        )
        with pytest.raises(FrozenInstanceError):
            diff.risk_score_change = 0.0  # type: ignore[misc]


class TestToDictFields:
    """Verify to_dict() produces all required fields for each model."""

    def test_actionable_insight_to_dict_fields(self):
        """ActionableInsight.to_dict() contains all required fields."""
        insight = ActionableInsight(
            package_name="requests",
            dependency_scope="runtime",
            dependency_type="direct",
            reason="runtime-scoped: 2 known CVE(s), risk score 75/100",
            priority_score=0.75,
            action="Upgrade to patched version",
        )
        d = insight.to_dict()
        assert set(d.keys()) == {
            "package_name",
            "dependency_scope",
            "dependency_type",
            "reason",
            "priority_score",
            "action",
        }
        assert d["package_name"] == "requests"
        assert d["dependency_scope"] == "runtime"
        assert d["dependency_type"] == "direct"
        assert d["reason"] == "runtime-scoped: 2 known CVE(s), risk score 75/100"
        assert d["priority_score"] == 0.75
        assert d["action"] == "Upgrade to patched version"

    def test_risk_cluster_to_dict_fields(self):
        """RiskCluster.to_dict() contains all required fields."""
        cluster = RiskCluster(
            cluster_name="Vulnerability Cluster",
            summary="Dependencies with known vulnerabilities.",
            count=3,
            risk_contribution=0.456789,
            example_packages=["lodash", "express", "axios"],
        )
        d = cluster.to_dict()
        assert set(d.keys()) == {
            "cluster_name",
            "summary",
            "count",
            "risk_contribution",
            "example_packages",
        }
        assert d["cluster_name"] == "Vulnerability Cluster"
        assert d["count"] == 3
        assert d["example_packages"] == ["lodash", "express", "axios"]

    def test_risk_narrative_to_dict_fields(self):
        """RiskNarrative.to_dict() contains all required fields."""
        narrative = RiskNarrative(
            summary="This repository has low dependency risk.",
            key_findings=["All dependencies are well-maintained."],
            recommendation="Continue monitoring dependency health.",
        )
        d = narrative.to_dict()
        assert set(d.keys()) == {"summary", "key_findings", "recommendation"}
        assert d["summary"] == "This repository has low dependency risk."
        assert d["key_findings"] == ["All dependencies are well-maintained."]
        assert d["recommendation"] == "Continue monitoring dependency health."

    def test_overall_confidence_to_dict_fields(self):
        """OverallConfidence.to_dict() contains all required fields."""
        confidence = OverallConfidence(
            score=0.85,
            label="high",
            explanation="Most dependencies have classified scope.",
        )
        d = confidence.to_dict()
        assert set(d.keys()) == {"score", "label", "explanation"}
        assert d["label"] == "high"

    def test_repo_snapshot_diff_to_dict_fields(self):
        """RepoSnapshotDiff.to_dict() contains all required fields."""
        diff = RepoSnapshotDiff(
            new_risky_dependencies=["axios", "lodash"],
            removed_dependencies=["moment"],
            risk_score_change=-0.123456789,
            risk_label_change="medium → low",
        )
        d = diff.to_dict()
        assert set(d.keys()) == {
            "new_risky_dependencies",
            "removed_dependencies",
            "risk_score_change",
            "risk_label_change",
        }
        assert d["new_risky_dependencies"] == ["axios", "lodash"]
        assert d["removed_dependencies"] == ["moment"]
        assert d["risk_label_change"] == "medium → low"


class TestFloatRounding:
    """Verify float rounding to 6 decimal places in serialized output."""

    def test_actionable_insight_rounds_priority_score(self):
        """ActionableInsight.to_dict() rounds priority_score to 6 decimal places."""
        insight = ActionableInsight(
            package_name="pkg",
            dependency_scope="runtime",
            dependency_type="direct",
            reason="test",
            priority_score=0.123456789012,
            action="Monitor dependency risk",
        )
        d = insight.to_dict()
        assert d["priority_score"] == 0.123457  # rounded to 6 dp

    def test_risk_cluster_rounds_risk_contribution(self):
        """RiskCluster.to_dict() rounds risk_contribution to 6 decimal places."""
        cluster = RiskCluster(
            cluster_name="Test",
            summary="Test cluster",
            count=1,
            risk_contribution=0.987654321,
            example_packages=[],
        )
        d = cluster.to_dict()
        assert d["risk_contribution"] == 0.987654  # rounded to 6 dp

    def test_overall_confidence_rounds_score(self):
        """OverallConfidence.to_dict() rounds score to 6 decimal places."""
        confidence = OverallConfidence(
            score=0.777777777,
            label="high",
            explanation="test",
        )
        d = confidence.to_dict()
        assert d["score"] == 0.777778  # rounded to 6 dp

    def test_repo_snapshot_diff_rounds_risk_score_change(self):
        """RepoSnapshotDiff.to_dict() rounds risk_score_change to 6 decimal places."""
        diff = RepoSnapshotDiff(
            new_risky_dependencies=[],
            removed_dependencies=[],
            risk_score_change=0.111111111,
            risk_label_change=None,
        )
        d = diff.to_dict()
        assert d["risk_score_change"] == 0.111111  # rounded to 6 dp

    def test_risk_narrative_no_float_fields(self):
        """RiskNarrative has no float fields — to_dict() has no rounding concerns."""
        narrative = RiskNarrative(
            summary="Summary text",
            key_findings=["Finding 1", "Finding 2"],
            recommendation="Do something.",
        )
        d = narrative.to_dict()
        # All fields are strings or lists of strings — no floats to round
        assert isinstance(d["summary"], str)
        assert isinstance(d["key_findings"], list)
        assert isinstance(d["recommendation"], str)


# ======================================================================
# Strategy for DependencyInput generation (shared across property tests)
# ======================================================================


@st.composite
def dependency_input_st(draw):
    return DependencyInput(
        package_name=draw(st.text(min_size=1, max_size=30, alphabet=string.ascii_lowercase + string.digits + "-_.")),
        dependency_scope=draw(st.sampled_from(["runtime", "dev", "test", "build", "optional", "peer", "unknown"])),
        scope_confidence=draw(st.sampled_from(["high", "medium", "low"])),
        vulnerability_count=draw(st.integers(min_value=0, max_value=20)),
        risk_score=draw(st.one_of(st.none(), st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))),
        dependency_type=draw(st.sampled_from(["direct", "transitive"])),
    )


# ======================================================================
# Property 1: Priority Score Formula Correctness and Range
# Feature: actionable-insights, Property 1: Priority Score Formula Correctness and Range
# ======================================================================


class TestPriorityScoreFormula:
    """Property 1: Priority Score Formula Correctness and Range.

    Generate random DependencyInput lists, verify each output's priority_score
    matches the formula and is in (0.0, 1.0].

    **Validates: Requirements 1.2, 2.2, 2.6, 13.7**
    """

    @given(deps=st.lists(dependency_input_st(), min_size=0, max_size=15))
    @settings(max_examples=100)
    def test_priority_score_matches_formula_and_range(self, deps: list[DependencyInput]):
        """Each output priority_score matches the formula and is in (0.0, 1.0]."""
        from open_source_risk_model.tree.scope_risk import DEFAULT_SCOPE_WEIGHTS, _deduplicate as _dedup

        results = generate_priority_recommendations(deps)

        # Deduplicate using the same logic as the implementation
        deduped = _dedup(deps) if deps else []

        for insight in results:
            # Find the deduped dep that matches this insight
            matching = [
                d for d in deduped
                if d.package_name == insight.package_name
                and d.dependency_type == insight.dependency_type
            ]
            assert len(matching) == 1, f"Expected exactly 1 deduped match for {insight.package_name}/{insight.dependency_type}"
            dep = matching[0]

            scope = dep.dependency_scope or "unknown"
            scope_weight = get_scope_weight(scope)
            normalized_risk = _normalized_risk(dep)
            confidence_modifier = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
            expected_score = round(min(scope_weight * normalized_risk * confidence_modifier, 1.0), 6)

            assert insight.priority_score == expected_score, (
                f"Expected {expected_score}, got {insight.priority_score} for {insight.package_name}"
            )

            # Verify range: strictly > 0 (zeros excluded) and <= 1.0
            assert 0.0 < insight.priority_score <= 1.0, (
                f"priority_score {insight.priority_score} out of range (0.0, 1.0]"
            )


# ======================================================================
# Property 2: Action Assignment Rule Correctness
# Feature: actionable-insights, Property 2: Action Assignment Rule Correctness
# ======================================================================


class TestActionAssignmentRules:
    """Property 2: Action Assignment Rule Correctness.

    Generate random DependencyInput objects with priority_score > 0,
    verify action matches first applicable rule and is exactly one of
    the four defined strings.

    **Validates: Requirements 1.3, 2.7**
    """

    VALID_ACTIONS = {
        "Upgrade to patched version",
        "Review high-risk dependency",
        "Investigate unknown scope",
        "Monitor dependency risk",
    }

    @given(deps=st.lists(dependency_input_st(), min_size=1, max_size=15))
    @settings(max_examples=100)
    def test_action_matches_first_applicable_rule(self, deps: list[DependencyInput]):
        """Each output action matches the first applicable rule."""
        from open_source_risk_model.tree.scope_risk import _deduplicate as _dedup

        results = generate_priority_recommendations(deps)
        deduped = _dedup(deps)

        for insight in results:
            # Action must be one of the four valid strings
            assert insight.action in self.VALID_ACTIONS, (
                f"Invalid action: {insight.action}"
            )

            # Find the deduped dep that matches this insight
            matching = [
                d for d in deduped
                if d.package_name == insight.package_name
                and d.dependency_type == insight.dependency_type
            ]
            assert len(matching) == 1
            dep = matching[0]
            scope = dep.dependency_scope or "unknown"

            # Verify first-match rule
            if dep.vulnerability_count > 0:
                expected_action = "Upgrade to patched version"
            elif dep.risk_score is not None and dep.risk_score > 70:
                expected_action = "Review high-risk dependency"
            elif scope == "unknown":
                expected_action = "Investigate unknown scope"
            else:
                expected_action = "Monitor dependency risk"

            assert insight.action == expected_action, (
                f"Expected action '{expected_action}', got '{insight.action}' "
                f"for {insight.package_name} (vuln={dep.vulnerability_count}, "
                f"risk={dep.risk_score}, scope={scope})"
            )


# ======================================================================
# Property 3: Recommendations Output Structure
# Feature: actionable-insights, Property 3: Recommendations Output Structure
# ======================================================================


class TestRecommendationsOutputStructure:
    """Property 3: Recommendations Output Structure.

    Generate random lists of DependencyInput, verify at most 10 results,
    sorted by (-priority_score, package_name), no zero-score entries,
    no duplicate (package_name, dependency_type) pairs.

    **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
    """

    @given(deps=st.lists(dependency_input_st(), min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_output_structure_invariants(self, deps: list[DependencyInput]):
        """Output satisfies all structural invariants."""
        results = generate_priority_recommendations(deps)

        # At most 10 results
        assert len(results) <= 10

        # No zero-score entries
        for insight in results:
            assert insight.priority_score > 0.0, (
                f"Zero-score entry found: {insight.package_name}"
            )

        # Sorted by (-priority_score, package_name, dependency_type)
        for i in range(len(results) - 1):
            curr = results[i]
            nxt = results[i + 1]
            assert (curr.priority_score > nxt.priority_score) or (
                curr.priority_score == nxt.priority_score
                and (curr.package_name < nxt.package_name or (
                    curr.package_name == nxt.package_name
                    and curr.dependency_type <= nxt.dependency_type
                ))
            ), (
                f"Sort violation at index {i}: "
                f"({curr.priority_score}, {curr.package_name}, {curr.dependency_type}) vs "
                f"({nxt.priority_score}, {nxt.package_name}, {nxt.dependency_type})"
            )

        # No duplicate (package_name, dependency_type) pairs
        seen = set()
        for insight in results:
            key = (insight.package_name, insight.dependency_type)
            assert key not in seen, f"Duplicate key found: {key}"
            seen.add(key)


# ======================================================================
# Unit Tests: generate_priority_recommendations() (Task 2.5)
# ======================================================================


class TestGeneratePriorityRecommendations:
    """Unit tests for generate_priority_recommendations()."""

    def test_empty_input_returns_empty_list(self):
        """Empty input returns empty list (Req 2.9)."""
        result = generate_priority_recommendations([])
        assert result == []

    def test_single_dependency_known_values(self):
        """Single dependency with known values produces exact expected output."""
        dep = DependencyInput(
            package_name="lodash",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=3,
            risk_score=85.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])

        assert len(results) == 1
        insight = results[0]
        assert insight.package_name == "lodash"
        assert insight.dependency_scope == "runtime"
        assert insight.dependency_type == "direct"
        assert insight.action == "Upgrade to patched version"

        # Verify priority_score formula:
        # scope_weight("runtime") = 1.0
        # _normalized_risk: max(85/100, min(3,5)*0.1) = max(0.85, 0.3) = 0.85
        # confidence_modifier("high") = 1.0
        # priority_score = round(min(1.0 * 0.85 * 1.0, 1.0), 6) = 0.85
        assert insight.priority_score == 0.85

        # Verify reason string
        assert insight.reason == "runtime-scoped: 3 known CVE(s), risk score 85/100"

    def test_deduplication_removes_duplicates_before_scoring(self):
        """Deduplication removes duplicates before scoring (Req 2.3)."""
        dep1 = DependencyInput(
            package_name="axios",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=1,
            risk_score=50.0,
            dependency_type="direct",
        )
        dep2 = DependencyInput(
            package_name="axios",
            dependency_scope="dev",
            scope_confidence="low",
            vulnerability_count=0,
            risk_score=30.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep1, dep2])

        # Should only have one entry for axios/direct
        axios_results = [r for r in results if r.package_name == "axios"]
        assert len(axios_results) == 1

    def test_zero_score_dependencies_excluded(self):
        """Zero-score dependencies are excluded (Req 2.6)."""
        dep = DependencyInput(
            package_name="safe-pkg",
            dependency_scope="dev",
            scope_confidence="low",
            vulnerability_count=0,
            risk_score=0.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])
        assert results == []

    def test_at_most_10_results_returned(self):
        """At most 10 results returned (Req 2.5)."""
        deps = [
            DependencyInput(
                package_name=f"pkg-{i:02d}",
                dependency_scope="runtime",
                scope_confidence="high",
                vulnerability_count=1,
                risk_score=float(50 + i),
                dependency_type="direct",
            )
            for i in range(15)
        ]
        results = generate_priority_recommendations(deps)
        assert len(results) == 10

    def test_deterministic_reason_string_vuln_and_risk(self):
        """Reason string format for vulnerability + risk score signals."""
        dep = DependencyInput(
            package_name="express",
            dependency_scope="runtime",
            scope_confidence="medium",
            vulnerability_count=2,
            risk_score=60.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])
        assert len(results) == 1
        assert results[0].reason == "runtime-scoped: 2 known CVE(s), risk score 60/100"

    def test_deterministic_reason_string_risk_only(self):
        """Reason string format for risk score only (no vulnerabilities)."""
        dep = DependencyInput(
            package_name="moment",
            dependency_scope="dev",
            scope_confidence="high",
            vulnerability_count=0,
            risk_score=45.0,
            dependency_type="transitive",
        )
        results = generate_priority_recommendations([dep])
        assert len(results) == 1
        assert results[0].reason == "dev-scoped: risk score 45/100"

    def test_deterministic_reason_string_no_signals(self):
        """Reason string format when no specific signals (contributes to weighted risk)."""
        # This case: risk_score=None, vulnerability_count=0 but still has non-zero priority
        # Actually with risk_score=None and vuln=0, normalized_risk = max(0/100, 0) = 0
        # So priority_score would be 0 and it would be excluded.
        # We need risk_score=0 (not None) and vuln=0 to get "contributes to weighted risk"
        # But that also gives normalized_risk=0. So this case can't produce a non-zero score.
        # The "contributes to weighted risk" fallback only triggers when both signals are absent
        # but that means normalized_risk=0, so it's always excluded.
        # Let's verify this edge case: risk_score=None, vuln=0 → excluded
        dep = DependencyInput(
            package_name="trivial",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=0,
            risk_score=None,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])
        assert results == []

    def test_none_scope_treated_as_unknown(self):
        """dependency_scope=None is treated as 'unknown'."""
        dep = DependencyInput(
            package_name="mystery",
            dependency_scope=None,  # type: ignore[arg-type]
            scope_confidence="high",
            vulnerability_count=2,
            risk_score=50.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])
        assert len(results) == 1
        # scope treated as "unknown", but vuln > 0 so action is "Upgrade to patched version"
        assert results[0].dependency_scope == "unknown"
        assert results[0].action == "Upgrade to patched version"
        assert "unknown-scoped:" in results[0].reason

    def test_action_review_high_risk(self):
        """Action 'Review high-risk dependency' when risk_score > 70 and no vulns."""
        dep = DependencyInput(
            package_name="risky-lib",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=0,
            risk_score=75.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])
        assert len(results) == 1
        assert results[0].action == "Review high-risk dependency"

    def test_action_investigate_unknown_scope(self):
        """Action 'Investigate unknown scope' when scope is unknown and no vulns/high risk."""
        dep = DependencyInput(
            package_name="unknown-pkg",
            dependency_scope="unknown",
            scope_confidence="medium",
            vulnerability_count=0,
            risk_score=40.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])
        assert len(results) == 1
        assert results[0].action == "Investigate unknown scope"

    def test_action_monitor_dependency_risk(self):
        """Action 'Monitor dependency risk' as fallback."""
        dep = DependencyInput(
            package_name="stable-lib",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=0,
            risk_score=30.0,
            dependency_type="direct",
        )
        results = generate_priority_recommendations([dep])
        assert len(results) == 1
        assert results[0].action == "Monitor dependency risk"

# ======================================================================
# Property 4: Cluster Structure and Contribution Correctness
# Feature: actionable-insights, Property 4: Cluster Structure and Contribution Correctness
# ======================================================================


class TestClusterStructureAndContribution:
    """Property 4: Cluster Structure and Contribution Correctness.

    Generate random DependencyInput lists, verify exactly 4 clusters in fixed
    order, correct counts match filter criteria, correct risk_contribution
    formula, and example_packages at most 3 and correctly selected.

    **Validates: Requirements 3.3, 3.4, 3.5, 3.7**
    """

    EXPECTED_CLUSTER_NAMES = [
        "Runtime Risk Cluster",
        "Transitive Risk Cluster",
        "Vulnerability Cluster",
        "Unknown Scope Cluster",
    ]

    @given(deps=st.lists(dependency_input_st(), min_size=0, max_size=15))
    @settings(max_examples=100)
    def test_cluster_structure_and_contribution(self, deps: list[DependencyInput]):
        """Verify 4 clusters in fixed order, correct counts, contribution, and example_packages."""
        clusters = generate_risk_clusters(deps)

        # Exactly 4 clusters in fixed order
        assert len(clusters) == 4
        for i, expected_name in enumerate(self.EXPECTED_CLUSTER_NAMES):
            assert clusters[i].cluster_name == expected_name

        # Deduplicate using same logic as implementation
        deduped = _deduplicate(deps) if deps else []

        # Compute per-dependency contribution and normalized risk
        dep_data: list[tuple[DependencyInput, str, float, float]] = []
        for dep in deduped:
            scope = dep.dependency_scope or "unknown"
            nr = _normalized_risk(dep)
            contrib = round(
                get_scope_weight(scope) * nr * CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5),
                6,
            )
            dep_data.append((dep, scope, nr, contrib))

        # Compute total_contribution using sorted summation
        sorted_contribs = sorted((d[3] for d in dep_data), reverse=True)
        total_contribution = sum(sorted_contribs)

        # Define expected filters
        def runtime_filter(dep, scope, nr):
            return scope == "runtime" and nr > 0

        def transitive_filter(dep, scope, nr):
            return dep.dependency_type == "transitive" and nr > 0

        def vulnerability_filter(dep, scope, nr):
            return dep.vulnerability_count > 0

        def unknown_filter(dep, scope, nr):
            return scope == "unknown"

        filters = [runtime_filter, transitive_filter, vulnerability_filter, unknown_filter]

        for i, filter_fn in enumerate(filters):
            cluster = clusters[i]

            # Get matching deps
            matching = [
                (dep, scope, nr, contrib)
                for dep, scope, nr, contrib in dep_data
                if filter_fn(dep, scope, nr)
            ]

            # Verify count
            assert cluster.count == len(matching), (
                f"Cluster '{cluster.cluster_name}': expected count {len(matching)}, got {cluster.count}"
            )

            # Verify risk_contribution
            if total_contribution > 0 and matching:
                cluster_sum = sum(m[3] for m in matching)
                expected_contribution = round(cluster_sum / total_contribution, 6)
            else:
                expected_contribution = 0.0
            assert cluster.risk_contribution == expected_contribution, (
                f"Cluster '{cluster.cluster_name}': expected contribution {expected_contribution}, "
                f"got {cluster.risk_contribution}"
            )

            # Verify example_packages: at most 3
            assert len(cluster.example_packages) <= 3

            # Verify example_packages are correctly selected
            sorted_matching = sorted(matching, key=lambda m: (-m[2], m[0].package_name))
            expected_examples = [m[0].package_name for m in sorted_matching[:3]]
            assert cluster.example_packages == expected_examples, (
                f"Cluster '{cluster.cluster_name}': expected examples {expected_examples}, "
                f"got {cluster.example_packages}"
            )


# ======================================================================
# Unit Tests: generate_risk_clusters() (Task 3.3)
# ======================================================================


class TestGenerateRiskClusters:
    """Unit tests for generate_risk_clusters()."""

    def test_empty_input_returns_4_clusters_with_zero_counts(self):
        """Empty input returns 4 clusters with zero counts (Req 3.9)."""
        clusters = generate_risk_clusters([])

        assert len(clusters) == 4
        expected_names = [
            "Runtime Risk Cluster",
            "Transitive Risk Cluster",
            "Vulnerability Cluster",
            "Unknown Scope Cluster",
        ]
        for i, cluster in enumerate(clusters):
            assert cluster.cluster_name == expected_names[i]
            assert cluster.count == 0
            assert cluster.risk_contribution == 0.0
            assert cluster.example_packages == []

    def test_overlapping_clusters_runtime_with_vulnerabilities(self):
        """A runtime dependency with vulnerabilities appears in both Runtime Risk and Vulnerability clusters (Req 3.6)."""
        dep = DependencyInput(
            package_name="express",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=3,
            risk_score=80.0,
            dependency_type="direct",
        )
        clusters = generate_risk_clusters([dep])

        # Runtime Risk Cluster should contain it
        runtime_cluster = clusters[0]
        assert runtime_cluster.cluster_name == "Runtime Risk Cluster"
        assert runtime_cluster.count == 1
        assert "express" in runtime_cluster.example_packages

        # Vulnerability Cluster should also contain it
        vuln_cluster = clusters[2]
        assert vuln_cluster.cluster_name == "Vulnerability Cluster"
        assert vuln_cluster.count == 1
        assert "express" in vuln_cluster.example_packages

    def test_risk_contribution_can_sum_greater_than_one(self):
        """Cluster risk_contribution values can sum > 1.0 across clusters due to overlap."""
        # Create a dependency that appears in multiple clusters:
        # runtime + vulnerability + transitive
        dep = DependencyInput(
            package_name="risky-lib",
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=5,
            risk_score=90.0,
            dependency_type="transitive",
        )
        clusters = generate_risk_clusters([dep])

        # This dep matches: Runtime Risk (runtime + nr>0), Transitive Risk (transitive + nr>0),
        # and Vulnerability (vuln_count > 0). Each cluster gets contribution/total = 1.0
        total_risk_contribution = sum(c.risk_contribution for c in clusters)
        assert total_risk_contribution > 1.0, (
            f"Expected total risk_contribution > 1.0, got {total_risk_contribution}"
        )

# ======================================================================
# Property 6: Confidence Computation Correctness
# Feature: actionable-insights, Property 6: Confidence Computation Correctness
# ======================================================================


class TestConfidenceComputationCorrectness:
    """Property 6: Confidence Computation Correctness.

    Generate random DependencyInput lists, verify formula:
    score = round(0.4 * scope_confidence + 0.3 * unknown_penalty + 0.3 * data_coverage, 6),
    score in [0.0, 1.0], and label thresholds match.

    **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6, 5.7**
    """

    @given(deps=st.lists(dependency_input_st(), min_size=0, max_size=15))
    @settings(max_examples=100)
    def test_confidence_formula_and_label(self, deps: list[DependencyInput]):
        """Verify confidence score matches formula, is in [0.0, 1.0], and label thresholds are correct."""
        result = compute_overall_confidence(deps)

        # Deduplicate using same logic as implementation
        deduped = _deduplicate(deps) if deps else []

        if not deduped:
            # Empty input case
            assert result.score == 0.0
            assert result.label == "low"
            assert result.explanation == "No dependency data available for confidence assessment."
            return

        total_count = len(deduped)

        # Compute scope confidence score
        high_count = sum(1 for d in deduped if d.scope_confidence == "high")
        medium_count = sum(1 for d in deduped if d.scope_confidence == "medium")
        low_count = sum(1 for d in deduped if d.scope_confidence == "low")
        scope_confidence = min(max(
            (high_count * 1.0 + medium_count * 0.75 + low_count * 0.5) / total_count,
            0.0,
        ), 1.0)

        # Compute unknown scope penalty
        unknown_count = sum(
            1 for d in deduped
            if (d.dependency_scope or "unknown") == "unknown" or d.dependency_scope is None
        )
        unknown_penalty = min(max(1.0 - (unknown_count / total_count), 0.0), 1.0)

        # Compute data coverage score
        has_risk_count = sum(1 for d in deduped if d.risk_score is not None)
        data_coverage = min(max(has_risk_count / total_count, 0.0), 1.0)

        # Verify formula
        expected_score = round(0.4 * scope_confidence + 0.3 * unknown_penalty + 0.3 * data_coverage, 6)
        assert result.score == expected_score, (
            f"Expected score {expected_score}, got {result.score}"
        )

        # Verify score in [0.0, 1.0]
        assert 0.0 <= result.score <= 1.0, (
            f"Score {result.score} out of range [0.0, 1.0]"
        )

        # Verify label thresholds
        if result.score >= 0.7:
            assert result.label == "high", (
                f"Score {result.score} >= 0.7 but label is '{result.label}'"
            )
        elif result.score >= 0.4:
            assert result.label == "medium", (
                f"Score {result.score} >= 0.4 but label is '{result.label}'"
            )
        else:
            assert result.label == "low", (
                f"Score {result.score} < 0.4 but label is '{result.label}'"
            )


# ======================================================================
# Unit Tests: compute_overall_confidence() (Task 5.3)
# ======================================================================


class TestComputeOverallConfidence:
    """Unit tests for compute_overall_confidence()."""

    def test_empty_input_returns_zero_score_low_label(self):
        """Empty input returns score=0.0, label='low', specific explanation (Req 5.10)."""
        result = compute_overall_confidence([])
        assert result.score == 0.0
        assert result.label == "low"
        assert result.explanation == "No dependency data available for confidence assessment."

    def test_all_high_confidence_dependencies_produce_high_score(self):
        """All-high-confidence dependencies with known scope and risk data produce high score."""
        deps = [
            DependencyInput(
                package_name=f"pkg-{i}",
                dependency_scope="runtime",
                scope_confidence="high",
                vulnerability_count=0,
                risk_score=50.0,
                dependency_type="direct",
            )
            for i in range(10)
        ]
        result = compute_overall_confidence(deps)

        # scope_confidence: all high → (10*1.0)/10 = 1.0
        # unknown_penalty: 0 unknown → 1.0 - 0/10 = 1.0
        # data_coverage: all have risk_score → 10/10 = 1.0
        # score = 0.4*1.0 + 0.3*1.0 + 0.3*1.0 = 1.0
        assert result.score == 1.0
        assert result.label == "high"
        assert "high" in result.explanation.lower()

    def test_all_unknown_scope_dependencies_produce_low_score(self):
        """All-unknown-scope dependencies produce low score reflecting unknown state."""
        deps = [
            DependencyInput(
                package_name=f"pkg-{i}",
                dependency_scope="unknown",
                scope_confidence="low",
                vulnerability_count=0,
                risk_score=None,
                dependency_type="direct",
            )
            for i in range(10)
        ]
        result = compute_overall_confidence(deps)

        # scope_confidence: all low → (10*0.5)/10 = 0.5
        # unknown_penalty: all unknown → 1.0 - 10/10 = 0.0
        # data_coverage: all None → 0/10 = 0.0
        # score = 0.4*0.5 + 0.3*0.0 + 0.3*0.0 = 0.2
        assert result.score == 0.2
        assert result.label == "low"
        # Weakest component is unknown_penalty (0.0) tied with data_coverage (0.0)
        # min() picks first in dict iteration — unknown_penalty
        assert "unknown scope" in result.explanation.lower()


# ======================================================================
# Strategy for generating RepoInsight with scope_weighted_risk
# ======================================================================


@st.composite
def repo_insight_with_swr_st(draw):
    """Generate a RepoInsight with a populated scope_weighted_risk dict."""
    risk_label = draw(st.sampled_from(["high", "medium", "low"]))
    score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    top_drivers = draw(st.lists(
        st.fixed_dictionaries({
            "package": st.text(min_size=1, max_size=20, alphabet=string.ascii_lowercase),
            "scope": st.sampled_from(VALID_SCOPES),
            "reason": st.text(min_size=1, max_size=50),
            "contribution": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        }),
        min_size=0, max_size=5,
    ))
    return RepoInsight(
        repo_full_name="test/repo",
        scope_weighted_risk={
            "scope_weighted_dependency_risk": score,
            "risk_label": risk_label,
            "top_drivers": top_drivers,
        },
    )


# ======================================================================
# Property 5: Narrative Template Correctness
# Feature: actionable-insights, Property 5: Narrative Template Correctness
# ======================================================================


class TestNarrativeTemplateCorrectness:
    """Property 5: Narrative Template Correctness.

    Generate random RepoInsight + clusters, verify summary contains expected
    phrase for risk_label, findings <= 5, recommendation matches cluster-based rules.

    **Validates: Requirements 4.2, 4.3, 4.5, 4.6**
    """

    @given(
        insight=repo_insight_with_swr_st(),
        clusters=st.lists(risk_cluster_st(), min_size=0, max_size=6),
    )
    @settings(max_examples=100)
    def test_narrative_template_correctness(
        self,
        insight: RepoInsight,
        clusters: list[RiskCluster],
    ):
        """Verify narrative summary, findings count, and recommendation rules."""
        narrative = generate_risk_narrative(insight, clusters)

        # Extract risk_label from insight
        swr = insight.scope_weighted_risk
        assert swr is not None
        risk_label = swr["risk_label"]

        # Verify summary contains expected phrase for risk_label
        if risk_label == "high":
            assert "significant dependency risk" in narrative.summary
        elif risk_label == "medium":
            assert "moderate dependency risk" in narrative.summary
        else:
            assert "low dependency risk" in narrative.summary

        # Verify findings <= 5
        assert len(narrative.key_findings) <= 5

        # Verify each finding is a non-empty string
        for finding in narrative.key_findings:
            assert isinstance(finding, str)
            assert len(finding) > 0

        # Verify recommendation matches cluster-based rules
        vuln_cluster = next(
            (c for c in clusters if c.cluster_name == "Vulnerability Cluster"),
            None,
        )
        runtime_cluster = next(
            (c for c in clusters if c.cluster_name == "Runtime Risk Cluster"),
            None,
        )

        if vuln_cluster is not None and vuln_cluster.count > 0:
            assert "patching" in narrative.recommendation.lower()
            assert str(vuln_cluster.count) in narrative.recommendation
        elif runtime_cluster is not None and runtime_cluster.count > 0:
            assert "runtime" in narrative.recommendation.lower()
            assert str(runtime_cluster.count) in narrative.recommendation
        else:
            assert narrative.recommendation == "Continue monitoring dependency health."


# ======================================================================
# Unit Tests: generate_risk_narrative() (Task 6.3)
# ======================================================================


class TestGenerateRiskNarrative:
    """Unit tests for generate_risk_narrative()."""

    def test_none_scope_weighted_risk_returns_insufficient_data(self):
        """None scope_weighted_risk returns insufficient-data narrative (Req 4.9)."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk=None,
        )
        clusters = []
        narrative = generate_risk_narrative(insight, clusters)

        assert narrative.summary == "Insufficient data available for risk narrative generation."
        assert narrative.key_findings == []
        assert narrative.recommendation == "Continue monitoring dependency health."

    def test_high_risk_label_produces_significant_summary(self):
        """High risk label produces summary with 'significant dependency risk' (Req 4.3)."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.75,
                "risk_label": "high",
                "top_drivers": [],
            },
        )
        clusters = generate_risk_clusters([])
        narrative = generate_risk_narrative(insight, clusters)

        assert "significant dependency risk" in narrative.summary
        assert "75.0%" in narrative.summary

    def test_medium_risk_label_produces_moderate_summary(self):
        """Medium risk label produces summary with 'moderate dependency risk' (Req 4.3)."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.5,
                "risk_label": "medium",
                "top_drivers": [],
            },
        )
        clusters = generate_risk_clusters([])
        narrative = generate_risk_narrative(insight, clusters)

        assert "moderate dependency risk" in narrative.summary
        assert "50.0%" in narrative.summary

    def test_low_risk_label_produces_low_summary(self):
        """Low risk label produces summary with 'low dependency risk' (Req 4.3)."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.2,
                "risk_label": "low",
                "top_drivers": [],
            },
        )
        clusters = generate_risk_clusters([])
        narrative = generate_risk_narrative(insight, clusters)

        assert "low dependency risk" in narrative.summary
        assert "20.0%" in narrative.summary

    def test_recommendation_references_patching_when_vulnerabilities_exist(self):
        """Recommendation references patching when Vulnerability Cluster has count > 0 (Req 4.5)."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.6,
                "risk_label": "medium",
                "top_drivers": [
                    {"package": "lodash", "scope": "runtime", "reason": "3 CVEs", "contribution": 0.5},
                ],
            },
        )
        # Create clusters with a non-zero Vulnerability Cluster
        deps = [
            DependencyInput(
                package_name="lodash",
                dependency_scope="runtime",
                scope_confidence="high",
                vulnerability_count=3,
                risk_score=80.0,
                dependency_type="direct",
            ),
        ]
        clusters = generate_risk_clusters(deps)
        narrative = generate_risk_narrative(insight, clusters)

        assert "patching" in narrative.recommendation.lower()
        assert "1" in narrative.recommendation  # 1 vulnerable dependency

    def test_recommendation_references_runtime_when_no_vulnerabilities(self):
        """Recommendation references runtime deps when no vulns but Runtime Risk > 0 (Req 4.5)."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.4,
                "risk_label": "medium",
                "top_drivers": [],
            },
        )
        # Create clusters with Runtime Risk > 0 but no vulnerabilities
        deps = [
            DependencyInput(
                package_name="express",
                dependency_scope="runtime",
                scope_confidence="high",
                vulnerability_count=0,
                risk_score=60.0,
                dependency_type="direct",
            ),
        ]
        clusters = generate_risk_clusters(deps)
        narrative = generate_risk_narrative(insight, clusters)

        assert "runtime" in narrative.recommendation.lower()
        assert "1" in narrative.recommendation  # 1 runtime dependency

    def test_key_findings_from_top_drivers(self):
        """Key findings include top drivers from scope_weighted_risk."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.7,
                "risk_label": "high",
                "top_drivers": [
                    {"package": "axios", "scope": "runtime", "reason": "2 CVEs", "contribution": 0.4},
                    {"package": "lodash", "scope": "runtime", "reason": "1 CVE", "contribution": 0.3},
                ],
            },
        )
        clusters = generate_risk_clusters([])
        narrative = generate_risk_narrative(insight, clusters)

        assert len(narrative.key_findings) >= 2
        assert "axios" in narrative.key_findings[0]
        assert "40.0%" in narrative.key_findings[0]
        assert "lodash" in narrative.key_findings[1]
        assert "30.0%" in narrative.key_findings[1]

    def test_key_findings_limited_to_5(self):
        """Key findings are limited to at most 5."""
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.8,
                "risk_label": "high",
                "top_drivers": [
                    {"package": f"pkg-{i}", "scope": "runtime", "reason": "risk", "contribution": 0.1 * (6 - i)}
                    for i in range(6)
                ],
            },
        )
        # Also add clusters with non-zero contributions
        deps = [
            DependencyInput(
                package_name=f"dep-{i}",
                dependency_scope="runtime",
                scope_confidence="high",
                vulnerability_count=1,
                risk_score=80.0,
                dependency_type="direct",
            )
            for i in range(5)
        ]
        clusters = generate_risk_clusters(deps)
        narrative = generate_risk_narrative(insight, clusters)

        assert len(narrative.key_findings) <= 5


# ======================================================================
# Strategy for generating RepoInsight with priority_recommendations for snapshot tests
# ======================================================================


@st.composite
def repo_insight_for_snapshot_st(draw):
    """Generate a RepoInsight with priority_recommendations for snapshot comparison tests."""
    risk_label = draw(st.sampled_from(["high", "medium", "low"]))
    score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    # Generate some ActionableInsight objects for priority_recommendations
    recs = draw(st.lists(actionable_insight_st(), min_size=0, max_size=5))
    # Optionally make scope_weighted_risk None
    has_swr = draw(st.booleans())
    swr = {
        "scope_weighted_dependency_risk": score,
        "risk_label": risk_label,
        "top_drivers": [],
    } if has_swr else None
    return RepoInsight(
        repo_full_name="test/repo",
        scope_weighted_risk=swr,
        priority_recommendations=recs,
    )


# ======================================================================
# Property 9: Snapshot Diff Correctness
# Feature: actionable-insights, Property 9: Snapshot Diff Correctness
# ======================================================================


class TestSnapshotDiffCorrectness:
    """Property 9: Snapshot Diff Correctness.

    Generate random RepoInsight pairs (with priority_recommendations populated),
    verify risk_score_change formula, risk_label_change logic, and sorted diff
    lists using (package_name, dependency_type) identity.

    **Validates: Requirements 6.2, 6.3, 6.6, 6.9**
    """

    @given(
        old_insight=repo_insight_for_snapshot_st(),
        new_insight=repo_insight_for_snapshot_st(),
    )
    @settings(max_examples=100)
    def test_snapshot_diff_correctness(self, old_insight: RepoInsight, new_insight: RepoInsight):
        """Verify risk_score_change, risk_label_change, and sorted diff lists."""
        result = compare_repo_snapshots(old_insight, new_insight)

        # Extract expected values
        _default_swr = {"scope_weighted_dependency_risk": 0.0, "risk_label": "low"}
        old_swr = old_insight.scope_weighted_risk or _default_swr
        new_swr = new_insight.scope_weighted_risk or _default_swr

        old_score = old_swr.get("scope_weighted_dependency_risk", 0.0)
        new_score = new_swr.get("scope_weighted_dependency_risk", 0.0)
        old_label = old_swr.get("risk_label", "low")
        new_label = new_swr.get("risk_label", "low")

        # Verify risk_score_change formula
        expected_change = round(new_score - old_score, 6)
        assert result.risk_score_change == expected_change, (
            f"Expected risk_score_change {expected_change}, got {result.risk_score_change}"
        )

        # Verify risk_label_change logic
        if old_label != new_label:
            expected_label_change = f"{old_label} \u2192 {new_label}"
            assert result.risk_label_change == expected_label_change, (
                f"Expected risk_label_change '{expected_label_change}', got '{result.risk_label_change}'"
            )
        else:
            assert result.risk_label_change is None, (
                f"Expected risk_label_change None when labels are same, got '{result.risk_label_change}'"
            )

        # Verify sorted diff lists using (package_name, dependency_type) identity
        old_recs = getattr(old_insight, "priority_recommendations", None) or []
        new_recs = getattr(new_insight, "priority_recommendations", None) or []

        # Build identity sets
        old_identities: set[tuple[str, str]] = set()
        for rec in old_recs:
            if hasattr(rec, "package_name"):
                old_identities.add((rec.package_name, rec.dependency_type))
            elif isinstance(rec, dict):
                old_identities.add((rec["package_name"], rec["dependency_type"]))

        new_priority_map: dict[tuple[str, str], float] = {}
        for rec in new_recs:
            if hasattr(rec, "package_name"):
                key = (rec.package_name, rec.dependency_type)
                score = rec.priority_score
            elif isinstance(rec, dict):
                key = (rec["package_name"], rec["dependency_type"])
                score = rec["priority_score"]
            else:
                continue
            if key not in new_priority_map or score > new_priority_map[key]:
                new_priority_map[key] = score

        new_identities = set(new_priority_map.keys())

        # new_risky_dependencies: in new but not old, with priority_score > 0
        new_only = new_identities - old_identities
        expected_new_risky = sorted(
            {pkg for pkg, dep_type in new_only if new_priority_map.get((pkg, dep_type), 0.0) > 0}
        )
        assert result.new_risky_dependencies == expected_new_risky, (
            f"Expected new_risky {expected_new_risky}, got {result.new_risky_dependencies}"
        )

        # removed_dependencies: in old but not new
        removed_only = old_identities - new_identities
        expected_removed = sorted({pkg for pkg, _ in removed_only})
        assert result.removed_dependencies == expected_removed, (
            f"Expected removed {expected_removed}, got {result.removed_dependencies}"
        )

        # Verify all output lists are sorted
        assert result.new_risky_dependencies == sorted(result.new_risky_dependencies)
        assert result.removed_dependencies == sorted(result.removed_dependencies)


# ======================================================================
# Unit Tests: compare_repo_snapshots() (Task 7.3)
# ======================================================================


class TestCompareRepoSnapshots:
    """Unit tests for compare_repo_snapshots()."""

    def test_identical_snapshots_produce_no_changes(self):
        """Identical snapshots produce no changes (risk_score_change=0.0, risk_label_change=None, empty diff lists)."""
        recs = [
            ActionableInsight(
                package_name="lodash",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: 2 known CVE(s)",
                priority_score=0.85,
                action="Upgrade to patched version",
            ),
        ]
        insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.5,
                "risk_label": "medium",
                "top_drivers": [],
            },
            priority_recommendations=recs,
        )
        result = compare_repo_snapshots(insight, insight)

        assert result.risk_score_change == 0.0
        assert result.risk_label_change is None
        assert result.new_risky_dependencies == []
        assert result.removed_dependencies == []

    def test_none_scope_weighted_risk_treated_as_zero(self):
        """One snapshot with None scope_weighted_risk is treated as score=0.0, label='low' (Req 6.6)."""
        old_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk=None,
            priority_recommendations=[],
        )
        new_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.6,
                "risk_label": "medium",
                "top_drivers": [],
            },
            priority_recommendations=[],
        )
        result = compare_repo_snapshots(old_insight, new_insight)

        # old_score=0.0, new_score=0.6 → change=0.6
        assert result.risk_score_change == 0.6
        # old_label="low", new_label="medium" → "low → medium"
        assert result.risk_label_change == "low \u2192 medium"

    def test_new_risky_and_removed_dependencies_identified_and_sorted(self):
        """New risky and removed dependencies are correctly identified and sorted."""
        old_recs = [
            ActionableInsight(
                package_name="moment",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: risk score 60/100",
                priority_score=0.6,
                action="Monitor dependency risk",
            ),
            ActionableInsight(
                package_name="lodash",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: 1 known CVE(s)",
                priority_score=0.8,
                action="Upgrade to patched version",
            ),
        ]
        new_recs = [
            ActionableInsight(
                package_name="axios",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: 2 known CVE(s)",
                priority_score=0.9,
                action="Upgrade to patched version",
            ),
            ActionableInsight(
                package_name="lodash",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: 1 known CVE(s)",
                priority_score=0.8,
                action="Upgrade to patched version",
            ),
            ActionableInsight(
                package_name="express",
                dependency_scope="runtime",
                dependency_type="transitive",
                reason="runtime-scoped: risk score 75/100",
                priority_score=0.7,
                action="Review high-risk dependency",
            ),
        ]
        old_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.5,
                "risk_label": "medium",
                "top_drivers": [],
            },
            priority_recommendations=old_recs,
        )
        new_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.7,
                "risk_label": "high",
                "top_drivers": [],
            },
            priority_recommendations=new_recs,
        )
        result = compare_repo_snapshots(old_insight, new_insight)

        # risk_score_change: 0.7 - 0.5 = 0.2
        assert result.risk_score_change == 0.2
        # risk_label_change: "medium → high"
        assert result.risk_label_change == "medium \u2192 high"
        # new_risky: axios (direct) and express (transitive) are in new but not old
        # Both have priority_score > 0, sorted by package_name
        assert result.new_risky_dependencies == ["axios", "express"]
        # removed: moment (direct) is in old but not new
        assert result.removed_dependencies == ["moment"]

    def test_handles_dict_recommendations(self):
        """Handles priority_recommendations as list of dicts (from to_dict())."""
        old_recs = [
            {
                "package_name": "requests",
                "dependency_scope": "runtime",
                "dependency_type": "direct",
                "reason": "runtime-scoped: 1 known CVE(s)",
                "priority_score": 0.7,
                "action": "Upgrade to patched version",
            },
        ]
        new_recs = [
            {
                "package_name": "flask",
                "dependency_scope": "runtime",
                "dependency_type": "direct",
                "reason": "runtime-scoped: risk score 80/100",
                "priority_score": 0.65,
                "action": "Review high-risk dependency",
            },
        ]
        old_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.4,
                "risk_label": "medium",
                "top_drivers": [],
            },
            priority_recommendations=old_recs,
        )
        new_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.3,
                "risk_label": "low",
                "top_drivers": [],
            },
            priority_recommendations=new_recs,
        )
        result = compare_repo_snapshots(old_insight, new_insight)

        # risk_score_change: 0.3 - 0.4 = -0.1
        assert result.risk_score_change == -0.1
        # risk_label_change: "medium → low"
        assert result.risk_label_change == "medium \u2192 low"
        # new_risky: flask is in new but not old
        assert result.new_risky_dependencies == ["flask"]
        # removed: requests is in old but not new
        assert result.removed_dependencies == ["requests"]

    def test_both_none_scope_weighted_risk(self):
        """Both snapshots with None scope_weighted_risk produce zero change."""
        old_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk=None,
            priority_recommendations=[],
        )
        new_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk=None,
            priority_recommendations=[],
        )
        result = compare_repo_snapshots(old_insight, new_insight)

        assert result.risk_score_change == 0.0
        assert result.risk_label_change is None
        assert result.new_risky_dependencies == []
        assert result.removed_dependencies == []

    def test_zero_priority_score_excluded_from_new_risky(self):
        """Dependencies with priority_score=0 in new are not included in new_risky_dependencies."""
        old_recs: list = []
        new_recs = [
            ActionableInsight(
                package_name="safe-pkg",
                dependency_scope="dev",
                dependency_type="direct",
                reason="dev-scoped: contributes to weighted risk",
                priority_score=0.0,
                action="Monitor dependency risk",
            ),
            ActionableInsight(
                package_name="risky-pkg",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: 1 known CVE(s)",
                priority_score=0.8,
                action="Upgrade to patched version",
            ),
        ]
        old_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={"scope_weighted_dependency_risk": 0.3, "risk_label": "low", "top_drivers": []},
            priority_recommendations=old_recs,
        )
        new_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={"scope_weighted_dependency_risk": 0.5, "risk_label": "medium", "top_drivers": []},
            priority_recommendations=new_recs,
        )
        result = compare_repo_snapshots(old_insight, new_insight)

        # Only risky-pkg should be in new_risky (priority_score > 0)
        assert result.new_risky_dependencies == ["risky-pkg"]


# ======================================================================
# Property 7: Determinism Under Input Reordering
# Feature: actionable-insights, Property 7: Determinism Under Input Reordering
# ======================================================================


class TestDeterminismUnderInputReordering:
    """Property 7: Determinism Under Input Reordering.

    Generate random DependencyInput lists, shuffle input order, verify
    generate_priority_recommendations, generate_risk_clusters, and
    compute_overall_confidence all produce identical output for both orderings.

    **Validates: Requirements 2.10, 3.10, 5.12, 13.1, 13.2, 13.4, 13.6**
    """

    @given(deps=st.lists(dependency_input_st(), min_size=0, max_size=15))
    @settings(max_examples=100)
    def test_determinism_under_input_reordering(self, deps: list[DependencyInput]):
        """All three functions produce identical output regardless of input order."""
        import random

        # Create a shuffled copy
        shuffled_deps = list(deps)
        random.shuffle(shuffled_deps)

        # generate_priority_recommendations: compare list of to_dict() outputs
        recs_original = generate_priority_recommendations(deps)
        recs_shuffled = generate_priority_recommendations(shuffled_deps)
        assert [r.to_dict() for r in recs_original] == [r.to_dict() for r in recs_shuffled], (
            "generate_priority_recommendations produced different output for shuffled input"
        )

        # generate_risk_clusters: compare list of to_dict() outputs
        clusters_original = generate_risk_clusters(deps)
        clusters_shuffled = generate_risk_clusters(shuffled_deps)
        assert [c.to_dict() for c in clusters_original] == [c.to_dict() for c in clusters_shuffled], (
            "generate_risk_clusters produced different output for shuffled input"
        )

        # compute_overall_confidence: compare to_dict() output
        confidence_original = compute_overall_confidence(deps)
        confidence_shuffled = compute_overall_confidence(shuffled_deps)
        assert confidence_original.to_dict() == confidence_shuffled.to_dict(), (
            "compute_overall_confidence produced different output for shuffled input"
        )


# ======================================================================
# Property 10: Robustness With All-Unknown Scopes
# Feature: actionable-insights, Property 10: Robustness With All-Unknown Scopes
# ======================================================================


@st.composite
def unknown_scope_dependency_input_st(draw):
    return DependencyInput(
        package_name=draw(st.text(min_size=1, max_size=30, alphabet=string.ascii_lowercase + string.digits + "-_.")),
        dependency_scope=draw(st.sampled_from(["unknown", None])),
        scope_confidence=draw(st.sampled_from(["high", "medium", "low"])),
        vulnerability_count=draw(st.integers(min_value=0, max_value=20)),
        risk_score=draw(st.one_of(st.none(), st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))),
        dependency_type=draw(st.sampled_from(["direct", "transitive"])),
    )


class TestRobustnessWithAllUnknownScopes:
    """Property 10: Robustness With All-Unknown Scopes.

    Generate lists where every dependency has dependency_scope of "unknown" or None,
    verify all 5 core functions produce valid outputs without errors.

    **Validates: Requirements 12.6, 13.7**
    """

    @given(deps=st.lists(unknown_scope_dependency_input_st(), min_size=1, max_size=15))
    @settings(max_examples=100)
    def test_all_unknown_scope_robustness(self, deps: list[DependencyInput]):
        """All 5 core functions produce valid outputs with all-unknown scope inputs."""
        # 1. generate_priority_recommendations: returns a list (may be empty)
        recs = generate_priority_recommendations(deps)
        assert isinstance(recs, list)

        # 2. generate_risk_clusters: exactly 4 clusters, all deps in Unknown Scope Cluster
        clusters = generate_risk_clusters(deps)
        assert len(clusters) == 4

        # All deps should be in the Unknown Scope Cluster
        unknown_cluster = clusters[3]
        assert unknown_cluster.cluster_name == "Unknown Scope Cluster"

        # Deduplicate to get expected count
        deduped = _deduplicate(deps)
        assert unknown_cluster.count == len(deduped)

        # 3. compute_overall_confidence: score, label, explanation are valid
        confidence = compute_overall_confidence(deps)
        assert isinstance(confidence.score, float)
        assert 0.0 <= confidence.score <= 1.0
        assert confidence.label in ("high", "medium", "low")
        assert isinstance(confidence.explanation, str)
        assert len(confidence.explanation) > 0

        # 4. generate_risk_narrative: returns a RiskNarrative (use a mock RepoInsight)
        mock_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.5,
                "risk_label": "medium",
                "top_drivers": [],
            },
        )
        narrative = generate_risk_narrative(mock_insight, clusters)
        assert isinstance(narrative, RiskNarrative)

        # 5. compare_repo_snapshots: returns a RepoSnapshotDiff
        old_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.3,
                "risk_label": "low",
                "top_drivers": [],
            },
            priority_recommendations=recs,
        )
        new_insight = RepoInsight(
            repo_full_name="test/repo",
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.6,
                "risk_label": "medium",
                "top_drivers": [],
            },
            priority_recommendations=recs,
        )
        diff = compare_repo_snapshots(old_insight, new_insight)
        assert isinstance(diff, RepoSnapshotDiff)

# ======================================================================
# Unit Tests: RepoInsight Model Extension (Task 10.2)
# ======================================================================


class TestRepoInsightModelExtension:
    """Verify RepoInsight model extension with Phase 5 fields.

    Ensures existing fields remain unchanged, new fields serialize correctly,
    and safe defaults work when new fields are empty/None.

    **Validates: Requirements 7.6, 12.1–12.5**
    """

    def test_existing_fields_unchanged_after_extension(self):
        """Existing fields (base_maintenance_risk, graph_signal_score, etc.) remain unchanged (Req 12.1–12.4)."""
        insight = RepoInsight(
            repo_full_name="owner/repo",
            base_maintenance_risk=0.65,
            base_maintenance_label="MEDIUM",
            graph_signal_score=0.42,
            graph_signal_label="MEDIUM",
            reasons=["High CVE count", "Low maintainer activity"],
            scope_weighted_risk={
                "scope_weighted_dependency_risk": 0.55,
                "risk_label": "medium",
                "top_drivers": [{"package": "lodash", "scope": "runtime", "contribution": 0.3}],
            },
        )

        # Verify existing fields are accessible and correct
        assert insight.repo_full_name == "owner/repo"
        assert insight.base_maintenance_risk == 0.65
        assert insight.base_maintenance_label == "MEDIUM"
        assert insight.graph_signal_score == 0.42
        assert insight.graph_signal_label == "MEDIUM"
        assert insight.reasons == ["High CVE count", "Low maintainer activity"]
        assert insight.scope_weighted_risk["scope_weighted_dependency_risk"] == 0.55

        # Verify to_dict() still includes all existing fields
        d = insight.to_dict()
        assert d["repo_full_name"] == "owner/repo"
        assert d["base_maintenance_risk"] == 0.65
        assert d["base_maintenance_label"] == "MEDIUM"
        assert d["graph_signal_score"] == 0.42
        assert d["graph_signal_label"] == "MEDIUM"
        assert d["reasons"] == ["High CVE count", "Low maintainer activity"]
        assert d["scope_weighted_risk"]["scope_weighted_dependency_risk"] == 0.55

    def test_to_dict_includes_all_phase5_fields(self):
        """to_dict() includes all 4 new Phase 5 fields (Req 7.6)."""
        # Create actionable insight objects
        rec = ActionableInsight(
            package_name="lodash",
            dependency_scope="runtime",
            dependency_type="direct",
            reason="runtime-scoped: 3 known CVE(s), risk score 85/100",
            priority_score=0.85,
            action="Upgrade to patched version",
        )
        cluster = RiskCluster(
            cluster_name="Runtime Risk Cluster",
            summary="Dependencies in runtime scope with elevated risk.",
            count=5,
            risk_contribution=0.65,
            example_packages=["lodash", "express"],
        )
        narrative = RiskNarrative(
            summary="This repository has moderate dependency risk.",
            key_findings=["lodash contributes 30% of risk."],
            recommendation="Prioritize patching vulnerable dependencies.",
        )
        confidence = OverallConfidence(
            score=0.75,
            label="high",
            explanation="Most dependencies have classified scope and risk data.",
        )

        insight = RepoInsight(
            repo_full_name="owner/repo",
            priority_recommendations=[rec],
            risk_clusters=[cluster],
            risk_narrative=narrative,
            overall_confidence=confidence,
        )

        d = insight.to_dict()

        # Verify priority_recommendations serialized as list of dicts
        assert "priority_recommendations" in d
        assert len(d["priority_recommendations"]) == 1
        assert d["priority_recommendations"][0]["package_name"] == "lodash"
        assert d["priority_recommendations"][0]["priority_score"] == 0.85
        assert d["priority_recommendations"][0]["action"] == "Upgrade to patched version"

        # Verify risk_clusters serialized as list of dicts
        assert "risk_clusters" in d
        assert len(d["risk_clusters"]) == 1
        assert d["risk_clusters"][0]["cluster_name"] == "Runtime Risk Cluster"
        assert d["risk_clusters"][0]["count"] == 5
        assert d["risk_clusters"][0]["risk_contribution"] == 0.65

        # Verify risk_narrative serialized as dict
        assert "risk_narrative" in d
        assert d["risk_narrative"]["summary"] == "This repository has moderate dependency risk."
        assert d["risk_narrative"]["key_findings"] == ["lodash contributes 30% of risk."]
        assert d["risk_narrative"]["recommendation"] == "Prioritize patching vulnerable dependencies."

        # Verify overall_confidence serialized as dict
        assert "overall_confidence" in d
        assert d["overall_confidence"]["score"] == 0.75
        assert d["overall_confidence"]["label"] == "high"
        assert d["overall_confidence"]["explanation"] == "Most dependencies have classified scope and risk data."

    def test_safe_defaults_when_phase5_fields_empty_or_none(self):
        """Safe defaults when new fields are empty/None (Req 12.5)."""
        insight = RepoInsight(
            repo_full_name="owner/repo",
        )

        # Verify defaults
        assert insight.priority_recommendations == []
        assert insight.risk_clusters == []
        assert insight.risk_narrative is None
        assert insight.overall_confidence is None

        # Verify to_dict() handles empty/None gracefully
        d = insight.to_dict()
        assert d["priority_recommendations"] == []
        assert d["risk_clusters"] == []
        assert d["risk_narrative"] is None
        assert d["overall_confidence"] is None

    def test_scope_weighted_risk_serialization_unchanged(self):
        """scope_weighted_risk serialization remains as-is (Req 12.3)."""
        swr = {
            "scope_weighted_dependency_risk": 0.55,
            "risk_label": "medium",
            "top_drivers": [{"package": "lodash", "scope": "runtime", "contribution": 0.3}],
        }
        insight = RepoInsight(
            repo_full_name="owner/repo",
            scope_weighted_risk=swr,
        )

        d = insight.to_dict()
        assert d["scope_weighted_risk"] == swr

    def test_scope_weighted_risk_none_not_in_dict(self):
        """scope_weighted_risk=None means key is absent from to_dict() (existing behavior preserved)."""
        insight = RepoInsight(
            repo_full_name="owner/repo",
            scope_weighted_risk=None,
        )

        d = insight.to_dict()
        assert "scope_weighted_risk" not in d

    def test_multiple_recommendations_and_clusters_serialize(self):
        """Multiple recommendations and clusters serialize correctly."""
        recs = [
            ActionableInsight(
                package_name="lodash",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: 3 known CVE(s)",
                priority_score=0.85,
                action="Upgrade to patched version",
            ),
            ActionableInsight(
                package_name="express",
                dependency_scope="runtime",
                dependency_type="direct",
                reason="runtime-scoped: risk score 72/100",
                priority_score=0.72,
                action="Review high-risk dependency",
            ),
        ]
        clusters = [
            RiskCluster(
                cluster_name="Runtime Risk Cluster",
                summary="Dependencies in runtime scope with elevated risk.",
                count=5,
                risk_contribution=0.65,
                example_packages=["lodash", "express"],
            ),
            RiskCluster(
                cluster_name="Vulnerability Cluster",
                summary="Dependencies with known vulnerabilities.",
                count=2,
                risk_contribution=0.35,
                example_packages=["lodash"],
            ),
        ]

        insight = RepoInsight(
            repo_full_name="owner/repo",
            priority_recommendations=recs,
            risk_clusters=clusters,
        )

        d = insight.to_dict()
        assert len(d["priority_recommendations"]) == 2
        assert d["priority_recommendations"][0]["package_name"] == "lodash"
        assert d["priority_recommendations"][1]["package_name"] == "express"
        assert len(d["risk_clusters"]) == 2
        assert d["risk_clusters"][0]["cluster_name"] == "Runtime Risk Cluster"
        assert d["risk_clusters"][1]["cluster_name"] == "Vulnerability Cluster"

    def test_existing_direct_signals_and_top_risky_deps_unchanged(self):
        """Existing direct_signals and top_risky_dependencies serialization unchanged (Req 12.2)."""
        from open_source_risk_model.insights.models import DependencyRisk, SignalEvidence

        signal = SignalEvidence(
            signal_name="cve_risk",
            severity="high",
            score_contribution=0.8,
            reason="3 known CVEs",
        )
        dep_risk = DependencyRisk(
            package_name="lodash",
            registry_type="npm",
            risk_score=0.85,
            risk_label="HIGH",
            reasons=["Known vulnerabilities"],
            cve_count=3,
        )

        insight = RepoInsight(
            repo_full_name="owner/repo",
            direct_signals=[signal],
            top_risky_dependencies=[dep_risk],
            priority_recommendations=[],
            risk_clusters=[],
        )

        d = insight.to_dict()

        # Verify direct_signals serialization unchanged
        assert len(d["direct_signals"]) == 1
        assert d["direct_signals"][0]["signal_name"] == "cve_risk"
        assert d["direct_signals"][0]["severity"] == "high"
        assert d["direct_signals"][0]["score_contribution"] == 0.8
        assert d["direct_signals"][0]["reason"] == "3 known CVEs"

        # Verify top_risky_dependencies serialization unchanged
        assert len(d["top_risky_dependencies"]) == 1
        assert d["top_risky_dependencies"][0]["package_name"] == "lodash"
        assert d["top_risky_dependencies"][0]["registry_type"] == "npm"
        assert d["top_risky_dependencies"][0]["risk_score"] == 0.85
        assert d["top_risky_dependencies"][0]["risk_label"] == "HIGH"
        assert d["top_risky_dependencies"][0]["cve_count"] == 3
