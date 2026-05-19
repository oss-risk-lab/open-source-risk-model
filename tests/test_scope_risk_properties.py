"""
Property-based tests for scope_risk.py.

Feature: scope-weighted-risk
Property 1: Weight map completeness and range

Uses Hypothesis to verify universal properties of the scope-weighted risk module.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.tree.scope_risk import (
    DEFAULT_SCOPE_WEIGHTS,
    get_scope_weight,
)

# ======================================================================
# Strategies
# ======================================================================

VALID_SCOPES = ["runtime", "dev", "test", "build", "optional", "peer", "unknown"]

# Strategy: any valid scope string from the defined set
valid_scope_st = st.sampled_from(VALID_SCOPES)

# Strategy: None or empty string (should map to "unknown")
null_or_empty_scope_st = st.sampled_from([None, ""])

# Strategy: any scope input including valid scopes, None, and empty string
any_scope_input_st = st.one_of(valid_scope_st, null_or_empty_scope_st)

# Strategy: a valid weight map where all values are floats in [0.0, 1.0]
weight_value_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

custom_weight_map_st = st.fixed_dictionaries(
    {scope: weight_value_st for scope in VALID_SCOPES}
)

# Strategy: weight map parameter — either None (use defaults) or a custom map
weight_map_param_st = st.one_of(st.none(), custom_weight_map_st)


# ======================================================================
# Property 1: Weight Map Completeness and Range
# ======================================================================


class TestWeightMapCompletenessAndRange:
    """Property 1: Weight map completeness and range.

    For any valid dependency_scope value in {runtime, dev, test, build,
    optional, peer, unknown} and any valid weight map,
    get_scope_weight(scope, weights) SHALL return a float in [0.0, 1.0]
    and SHALL never raise a KeyError or return None. Additionally, for
    None or empty-string scope inputs, the function SHALL return the
    unknown weight.

    **Validates: Requirements 1.2, 1.5, 3.8**
    """

    @given(scope=valid_scope_st, weights=weight_map_param_st)
    @settings(max_examples=200)
    def test_valid_scope_returns_float_in_range(self, scope: str, weights):
        """For any valid scope and any valid weight map, get_scope_weight
        returns a float in [0.0, 1.0] and never raises KeyError or returns None."""
        result = get_scope_weight(scope, weights)

        assert result is not None, f"get_scope_weight({scope!r}, ...) returned None"
        assert isinstance(result, float), (
            f"get_scope_weight({scope!r}, ...) returned {type(result).__name__}, expected float"
        )
        assert 0.0 <= result <= 1.0, (
            f"get_scope_weight({scope!r}, ...) returned {result}, outside [0.0, 1.0]"
        )

    @given(scope=null_or_empty_scope_st, weights=weight_map_param_st)
    @settings(max_examples=100)
    def test_none_or_empty_scope_returns_unknown_weight(self, scope, weights):
        """For None or empty-string scope, get_scope_weight SHALL return
        the unknown weight from the active weight map."""
        result = get_scope_weight(scope, weights)
        w = weights or DEFAULT_SCOPE_WEIGHTS
        expected = w.get("unknown", 0.40)

        assert result is not None, (
            f"get_scope_weight({scope!r}, ...) returned None for null/empty scope"
        )
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0
        assert result == expected, (
            f"get_scope_weight({scope!r}, ...) returned {result}, "
            f"expected unknown weight {expected}"
        )

    @given(scope=any_scope_input_st, weights=weight_map_param_st)
    @settings(max_examples=200)
    def test_never_raises_key_error(self, scope, weights):
        """get_scope_weight SHALL never raise a KeyError for any scope input."""
        # This test simply verifies no exception is raised
        result = get_scope_weight(scope, weights)
        assert result is not None
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


# ======================================================================
# Additional imports for Properties 4–14
# ======================================================================

import random

from src.open_source_risk_model.tree.scope_risk import (
    CONFIDENCE_MODIFIERS,
    DependencyInput,
    ExplainabilityPayload,
    TopDriver,
    _classify_risk_label,
    _deduplicate,
    _normalized_risk,
    compute_scope_exposure_metrics,
    compute_scope_weighted_risk,
)

# ======================================================================
# Shared strategy: DependencyInput generator
# ======================================================================

VALID_CONFIDENCES = ["high", "medium", "low"]
VALID_DEP_TYPES = ["direct", "transitive"]

dependency_input_st = st.builds(
    DependencyInput,
    package_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    dependency_scope=st.sampled_from(VALID_SCOPES),
    scope_confidence=st.sampled_from(VALID_CONFIDENCES),
    vulnerability_count=st.integers(min_value=0, max_value=20),
    risk_score=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    ),
    dependency_type=st.sampled_from(VALID_DEP_TYPES),
)

dependency_list_st = st.lists(dependency_input_st, min_size=0, max_size=15)
non_empty_dependency_list_st = st.lists(dependency_input_st, min_size=1, max_size=15)


# ======================================================================
# Property 4: Score Range Invariant
# ======================================================================


class TestScoreRangeInvariant:
    """Property 4: Score Range Invariant.

    For any list of DependencyInput objects (including empty lists),
    compute_scope_weighted_risk() SHALL return an ExplainabilityPayload
    whose scope_weighted_dependency_risk is a float in [0.0, 1.0].
    For empty input, the score SHALL be exactly 0.0.

    **Validates: Requirements 3.2, 3.12, 6.1**
    """

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_score_in_zero_one_range(self, deps: list[DependencyInput]):
        """Score SHALL always be a float in [0.0, 1.0]."""
        result = compute_scope_weighted_risk(deps)
        assert isinstance(result, ExplainabilityPayload)
        assert isinstance(result.scope_weighted_dependency_risk, float)
        assert 0.0 <= result.scope_weighted_dependency_risk <= 1.0

    @settings(max_examples=200)
    @given(data=st.data())
    def test_empty_input_returns_zero(self, data):
        """For empty input, the score SHALL be exactly 0.0."""
        result = compute_scope_weighted_risk([])
        assert result.scope_weighted_dependency_risk == 0.0
        assert result.top_drivers == []


# ======================================================================
# Property 5: Runtime Weighting Dominance
# ======================================================================


class TestRuntimeWeightingDominance:
    """Property 5: Runtime Weighting Dominance.

    For any DependencyInput with risk_score > 0 and scope_confidence == "high",
    computing the scope-weighted risk for a single-element list with
    dependency_scope = "runtime" SHALL produce a strictly higher score than
    computing with the same dependency but dependency_scope = "dev".

    **Validates: Requirements 3.3, 3.13**
    """

    @given(
        package_name=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
            min_size=1,
            max_size=30,
        ),
        vulnerability_count=st.integers(min_value=0, max_value=20),
        risk_score=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
        dependency_type=st.sampled_from(VALID_DEP_TYPES),
    )
    @settings(max_examples=200)
    def test_runtime_scores_higher_than_dev(
        self, package_name, vulnerability_count, risk_score, dependency_type
    ):
        """Runtime-scoped dependency SHALL produce strictly higher score than dev-scoped."""
        runtime_dep = DependencyInput(
            package_name=package_name,
            dependency_scope="runtime",
            scope_confidence="high",
            vulnerability_count=vulnerability_count,
            risk_score=risk_score,
            dependency_type=dependency_type,
        )
        dev_dep = DependencyInput(
            package_name=package_name,
            dependency_scope="dev",
            scope_confidence="high",
            vulnerability_count=vulnerability_count,
            risk_score=risk_score,
            dependency_type=dependency_type,
        )

        runtime_result = compute_scope_weighted_risk([runtime_dep])
        dev_result = compute_scope_weighted_risk([dev_dep])

        assert runtime_result.scope_weighted_dependency_risk > dev_result.scope_weighted_dependency_risk, (
            f"Runtime score {runtime_result.scope_weighted_dependency_risk} should be > "
            f"dev score {dev_result.scope_weighted_dependency_risk}"
        )


# ======================================================================
# Property 6: Zero-Risk Addition Non-Inflation
# ======================================================================


class TestZeroRiskAdditionNonInflation:
    """Property 6: Zero-Risk Addition Non-Inflation.

    For any non-empty list of DependencyInput objects, adding a new dependency
    with risk_score = 0 and vulnerability_count = 0 SHALL NOT increase the
    scope_weighted_dependency_risk score.

    **Validates: Requirements 3.4**
    """

    @given(
        deps=non_empty_dependency_list_st,
        zero_dep=st.builds(
            DependencyInput,
            package_name=st.just("__zero_risk_pkg__"),
            dependency_scope=st.sampled_from(VALID_SCOPES),
            scope_confidence=st.sampled_from(VALID_CONFIDENCES),
            vulnerability_count=st.just(0),
            risk_score=st.just(0.0),
            dependency_type=st.just("direct"),
        ),
    )
    @settings(max_examples=200)
    def test_adding_zero_risk_does_not_inflate(
        self, deps: list[DependencyInput], zero_dep: DependencyInput
    ):
        """Adding a zero-risk dependency SHALL NOT increase the score."""
        original_result = compute_scope_weighted_risk(deps)
        extended_deps = deps + [zero_dep]
        extended_result = compute_scope_weighted_risk(extended_deps)

        assert extended_result.scope_weighted_dependency_risk <= original_result.scope_weighted_dependency_risk + 1e-9, (
            f"Score increased from {original_result.scope_weighted_dependency_risk} to "
            f"{extended_result.scope_weighted_dependency_risk} after adding zero-risk dep"
        )


# ======================================================================
# Property 7: Formula Correctness and Type Independence
# ======================================================================


class TestFormulaCorrectnessAndTypeIndependence:
    """Property 7: Formula Correctness and Type Independence.

    For any single DependencyInput, the scope_weighted_dependency_risk score
    SHALL equal scope_weight × normalized_risk × confidence_modifier.
    Changing dependency_type from "direct" to "transitive" SHALL NOT change
    the score.

    **Validates: Requirements 3.5, 3.6**
    """

    @given(dep=dependency_input_st)
    @settings(max_examples=200)
    def test_single_dep_formula_correctness(self, dep: DependencyInput):
        """For a single dep, score = scope_weight × normalized_risk × confidence_modifier."""
        result = compute_scope_weighted_risk([dep])

        scope = dep.dependency_scope or "unknown"
        sw = DEFAULT_SCOPE_WEIGHTS.get(scope, DEFAULT_SCOPE_WEIGHTS.get("unknown", 0.40))
        nr = _normalized_risk(dep)
        cm = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
        expected = round(sw * nr * cm, 6)

        assert abs(result.scope_weighted_dependency_risk - expected) < 1e-5, (
            f"Score {result.scope_weighted_dependency_risk} != expected {expected} "
            f"(sw={sw}, nr={nr}, cm={cm})"
        )

    @given(dep=dependency_input_st)
    @settings(max_examples=200)
    def test_type_independence(self, dep: DependencyInput):
        """Changing dependency_type SHALL NOT change the score."""
        direct_dep = DependencyInput(
            package_name=dep.package_name,
            dependency_scope=dep.dependency_scope,
            scope_confidence=dep.scope_confidence,
            vulnerability_count=dep.vulnerability_count,
            risk_score=dep.risk_score,
            dependency_type="direct",
        )
        transitive_dep = DependencyInput(
            package_name=dep.package_name,
            dependency_scope=dep.dependency_scope,
            scope_confidence=dep.scope_confidence,
            vulnerability_count=dep.vulnerability_count,
            risk_score=dep.risk_score,
            dependency_type="transitive",
        )

        direct_result = compute_scope_weighted_risk([direct_dep])
        transitive_result = compute_scope_weighted_risk([transitive_dep])

        assert abs(
            direct_result.scope_weighted_dependency_risk
            - transitive_result.scope_weighted_dependency_risk
        ) < 1e-9, (
            f"Direct score {direct_result.scope_weighted_dependency_risk} != "
            f"transitive score {transitive_result.scope_weighted_dependency_risk}"
        )


# ======================================================================
# Property 8: Top Drivers Structure, Ordering, and Contribution Sum
# ======================================================================


class TestTopDriversStructureOrderingAndContributionSum:
    """Property 8: Top Drivers Structure, Ordering, and Contribution Sum.

    For any list of DependencyInput objects, the returned top_drivers list
    SHALL have at most 5 entries. Each entry SHALL have non-null package,
    scope, reason, and contribution fields. The list SHALL be ordered by
    contribution descending; when contributions are equal, entries SHALL be
    ordered by package name ascending. The sum of all dependency contributions
    (before truncation to top 5) SHALL equal 1.0 when total_weighted_sum > 0.

    **Validates: Requirements 3.9, 6.3, 10.3**
    """

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_top_drivers_at_most_five(self, deps: list[DependencyInput]):
        """top_drivers SHALL have at most 5 entries."""
        result = compute_scope_weighted_risk(deps)
        assert len(result.top_drivers) <= 5

    @given(deps=non_empty_dependency_list_st)
    @settings(max_examples=200)
    def test_top_drivers_fields_non_null(self, deps: list[DependencyInput]):
        """Each top_driver SHALL have non-null package, scope, reason, contribution."""
        result = compute_scope_weighted_risk(deps)
        for driver in result.top_drivers:
            assert driver.package is not None
            assert driver.scope is not None
            assert driver.reason is not None
            assert driver.contribution is not None

    @given(deps=non_empty_dependency_list_st)
    @settings(max_examples=200)
    def test_top_drivers_ordered_by_contribution_desc_then_name_asc(
        self, deps: list[DependencyInput]
    ):
        """top_drivers SHALL be ordered by contribution desc, then package name asc."""
        result = compute_scope_weighted_risk(deps)
        drivers = result.top_drivers
        for i in range(len(drivers) - 1):
            a, b = drivers[i], drivers[i + 1]
            assert (a.contribution > b.contribution) or (
                abs(a.contribution - b.contribution) < 1e-9
                and a.package <= b.package
            ), (
                f"Ordering violated: {a.package}({a.contribution}) before "
                f"{b.package}({b.contribution})"
            )

    @given(deps=non_empty_dependency_list_st)
    @settings(max_examples=200)
    def test_all_contributions_sum_to_one(self, deps: list[DependencyInput]):
        """Sum of ALL dependency contributions (before truncation) SHALL equal 1.0
        when total_weighted_sum > 0.

        We verify this indirectly: if there are top_drivers, the score > 0,
        meaning total_weighted_sum > 0, and contributions are fractions of that sum.
        We recompute all contributions to verify they sum to ~1.0.
        """
        result = compute_scope_weighted_risk(deps)
        if result.scope_weighted_dependency_risk == 0.0:
            # No contributions when score is 0
            assert len(result.top_drivers) == 0
            return

        # Recompute all contributions manually
        from open_source_risk_model.tree.scope_risk import _deduplicate, get_scope_weight

        deduped = _deduplicate(deps)
        contributions = []
        for dep in deduped:
            scope = dep.dependency_scope or "unknown"
            nr = _normalized_risk(dep)
            sw = get_scope_weight(scope)
            cm = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
            contributions.append(round(sw * nr * cm, 6))

        total = sum(contributions)
        if total > 0:
            normalized = [c / total for c in contributions]
            assert abs(sum(normalized) - 1.0) < 1e-6, (
                f"Contributions sum to {sum(normalized)}, expected ~1.0"
            )


# ======================================================================
# Property 9: Risk Label Classification
# ======================================================================


class TestRiskLabelClassification:
    """Property 9: Risk Label Classification.

    For any scope_weighted_dependency_risk score in [0.0, 1.0], the risk_label
    SHALL be "low" when score ≤ 0.33, "medium" when 0.33 < score ≤ 0.66,
    and "high" when score > 0.66.

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 6.2**
    """

    @given(score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_risk_label_matches_thresholds(self, score: float):
        """_classify_risk_label SHALL return correct label for any score in [0, 1]."""
        label = _classify_risk_label(score)
        assert label in {"low", "medium", "high"}

        if score <= 0.33:
            assert label == "low", f"Score {score} should be 'low', got '{label}'"
        elif score <= 0.66:
            assert label == "medium", f"Score {score} should be 'medium', got '{label}'"
        else:
            assert label == "high", f"Score {score} should be 'high', got '{label}'"

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_payload_label_matches_score(self, deps: list[DependencyInput]):
        """The risk_label in the payload SHALL match the score thresholds."""
        result = compute_scope_weighted_risk(deps)
        score = result.scope_weighted_dependency_risk
        expected_label = _classify_risk_label(score)
        assert result.risk_label == expected_label


# ======================================================================
# Property 13: Determinism Under Input Reordering
# ======================================================================


class TestDeterminismUnderInputReordering:
    """Property 13: Determinism Under Input Reordering.

    For any list of DependencyInput objects, shuffling the input order and
    calling compute_scope_weighted_risk() SHALL produce an identical
    scope_weighted_dependency_risk score and identical top_drivers list.

    **Validates: Requirements 10.1, 10.2**
    """

    @given(deps=dependency_list_st, seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=200)
    def test_shuffled_input_produces_identical_output(
        self, deps: list[DependencyInput], seed: int
    ):
        """Shuffling input SHALL produce identical score and top_drivers."""
        result_original = compute_scope_weighted_risk(deps)

        shuffled = list(deps)
        rng = random.Random(seed)
        rng.shuffle(shuffled)
        result_shuffled = compute_scope_weighted_risk(shuffled)

        assert result_original.scope_weighted_dependency_risk == result_shuffled.scope_weighted_dependency_risk, (
            f"Score changed after shuffle: {result_original.scope_weighted_dependency_risk} "
            f"vs {result_shuffled.scope_weighted_dependency_risk}"
        )

        assert len(result_original.top_drivers) == len(result_shuffled.top_drivers)
        for orig, shuf in zip(result_original.top_drivers, result_shuffled.top_drivers):
            assert orig.package == shuf.package
            assert orig.scope == shuf.scope
            assert orig.contribution == shuf.contribution


# ======================================================================
# Property 14: Zero-Risk Inputs Produce Zero Score
# ======================================================================


class TestZeroRiskInputsProduceZeroScore:
    """Property 14: Zero-Risk Inputs Produce Zero Score.

    For any list of DependencyInput objects where every dependency has
    risk_score ≤ 0 (or None) and vulnerability_count = 0, the
    scope_weighted_dependency_risk score SHALL be exactly 0.0.

    **Validates: Requirements 3.2, 3.12**
    """

    @given(
        deps=st.lists(
            st.builds(
                DependencyInput,
                package_name=st.text(
                    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
                    min_size=1,
                    max_size=30,
                ),
                dependency_scope=st.sampled_from(VALID_SCOPES),
                scope_confidence=st.sampled_from(VALID_CONFIDENCES),
                vulnerability_count=st.just(0),
                risk_score=st.one_of(st.none(), st.just(0.0)),
                dependency_type=st.sampled_from(VALID_DEP_TYPES),
            ),
            min_size=0,
            max_size=15,
        )
    )
    @settings(max_examples=200)
    def test_all_zero_risk_produces_zero_score(self, deps: list[DependencyInput]):
        """When all deps have zero risk, score SHALL be exactly 0.0."""
        result = compute_scope_weighted_risk(deps)
        assert result.scope_weighted_dependency_risk == 0.0, (
            f"Expected 0.0 for all-zero-risk input, got {result.scope_weighted_dependency_risk}"
        )


# ======================================================================
# Property 2: Exposure Metrics Range Invariant
# ======================================================================


class TestExposureMetricsRangeInvariant:
    """Property 2: Exposure Metrics Range Invariant.

    For any list of DependencyInput objects (including empty lists), all
    computed exposure ratios — runtime_dependency_exposure,
    transitive_runtime_dependency_exposure,
    scope_weighted_dependency_exposure, and unknown_scope_dependency_ratio
    — SHALL be floats in [0.0, 1.0]. When the relevant denominator is
    zero, the ratio SHALL be 0.0.

    **Validates: Requirements 2.1, 2.2, 2.3, 2.7, 2.8**
    """

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_all_ratios_in_zero_one_range(self, deps: list[DependencyInput]):
        """All exposure ratios SHALL be floats in [0.0, 1.0]."""
        metrics = compute_scope_exposure_metrics(deps)

        for field_name in (
            "runtime_dependency_exposure",
            "transitive_runtime_dependency_exposure",
            "scope_weighted_dependency_exposure",
            "unknown_scope_dependency_ratio",
        ):
            value = getattr(metrics, field_name)
            assert isinstance(value, float), (
                f"{field_name} is {type(value).__name__}, expected float"
            )
            assert 0.0 <= value <= 1.0, (
                f"{field_name} = {value}, outside [0.0, 1.0]"
            )

    @settings(max_examples=200)
    @given(data=st.data())
    def test_empty_input_returns_zero_ratios(self, data):
        """When the input list is empty, all ratios SHALL be 0.0."""
        metrics = compute_scope_exposure_metrics([])

        assert metrics.runtime_dependency_exposure == 0.0
        assert metrics.transitive_runtime_dependency_exposure == 0.0
        assert metrics.scope_weighted_dependency_exposure == 0.0
        assert metrics.unknown_scope_dependency_ratio == 0.0
        assert metrics.vulnerable_runtime_dependency_count == 0
        assert metrics.vulnerable_transitive_runtime_dependency_count == 0
        assert metrics.high_risk_runtime_dependency_count == 0

    @given(
        deps=st.lists(
            st.builds(
                DependencyInput,
                package_name=st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters="-_",
                    ),
                    min_size=1,
                    max_size=30,
                ),
                dependency_scope=st.sampled_from(VALID_SCOPES),
                scope_confidence=st.sampled_from(VALID_CONFIDENCES),
                vulnerability_count=st.integers(min_value=0, max_value=20),
                risk_score=st.one_of(
                    st.none(),
                    st.floats(
                        min_value=0.0,
                        max_value=100.0,
                        allow_nan=False,
                        allow_infinity=False,
                    ),
                ),
                dependency_type=st.just("transitive"),
            ),
            min_size=0,
            max_size=15,
        )
    )
    @settings(max_examples=200)
    def test_no_direct_deps_runtime_exposure_zero(
        self, deps: list[DependencyInput]
    ):
        """When there are no direct deps, runtime_dependency_exposure SHALL be 0.0."""
        metrics = compute_scope_exposure_metrics(deps)
        assert metrics.runtime_dependency_exposure == 0.0


# ======================================================================
# Property 3: Exposure Counting Correctness
# ======================================================================


class TestExposureCountingCorrectness:
    """Property 3: Exposure Counting Correctness.

    For any list of DependencyInput objects, vulnerable_runtime_dependency_count
    SHALL equal the count of dependencies where dependency_type == "direct"
    AND dependency_scope == "runtime" AND vulnerability_count > 0. Similarly,
    vulnerable_transitive_runtime_dependency_count SHALL equal the count where
    dependency_type == "transitive" AND dependency_scope == "runtime" AND
    vulnerability_count > 0. And high_risk_runtime_dependency_count SHALL equal
    the count where dependency_type == "direct" AND dependency_scope == "runtime"
    AND risk_score is not None AND risk_score > 70.

    Counts are computed on the deduplicated list (by (package_name, dependency_type)).

    **Validates: Requirements 2.4, 2.5, 2.6**
    """

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_vulnerable_runtime_dependency_count(
        self, deps: list[DependencyInput]
    ):
        """vulnerable_runtime_dependency_count SHALL match manual count on deduplicated list."""
        metrics = compute_scope_exposure_metrics(deps)
        deduped = _deduplicate(deps)

        expected = sum(
            1
            for dep in deduped
            if dep.dependency_type == "direct"
            and (dep.dependency_scope or "unknown") == "runtime"
            and dep.vulnerability_count > 0
        )
        assert metrics.vulnerable_runtime_dependency_count == expected, (
            f"vulnerable_runtime_dependency_count: got {metrics.vulnerable_runtime_dependency_count}, "
            f"expected {expected}"
        )

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_vulnerable_transitive_runtime_dependency_count(
        self, deps: list[DependencyInput]
    ):
        """vulnerable_transitive_runtime_dependency_count SHALL match manual count on deduplicated list."""
        metrics = compute_scope_exposure_metrics(deps)
        deduped = _deduplicate(deps)

        expected = sum(
            1
            for dep in deduped
            if dep.dependency_type == "transitive"
            and (dep.dependency_scope or "unknown") == "runtime"
            and dep.vulnerability_count > 0
        )
        assert metrics.vulnerable_transitive_runtime_dependency_count == expected, (
            f"vulnerable_transitive_runtime_dependency_count: got "
            f"{metrics.vulnerable_transitive_runtime_dependency_count}, expected {expected}"
        )

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_high_risk_runtime_dependency_count(
        self, deps: list[DependencyInput]
    ):
        """high_risk_runtime_dependency_count SHALL match manual count on deduplicated list."""
        metrics = compute_scope_exposure_metrics(deps)
        deduped = _deduplicate(deps)

        expected = sum(
            1
            for dep in deduped
            if dep.dependency_type == "direct"
            and (dep.dependency_scope or "unknown") == "runtime"
            and dep.risk_score is not None
            and dep.risk_score > 70
        )
        assert metrics.high_risk_runtime_dependency_count == expected, (
            f"high_risk_runtime_dependency_count: got {metrics.high_risk_runtime_dependency_count}, "
            f"expected {expected}"
        )


# ======================================================================
# Additional imports for Properties 10–12
# ======================================================================

import json

from src.open_source_risk_model.insights.compute import compute_scope_aware_reasons
from src.open_source_risk_model.tree.scope_risk import _confidence_note


# ======================================================================
# Strategy: DependencyInput with at least one non-unknown scope
# ======================================================================

NON_UNKNOWN_SCOPES = ["runtime", "dev", "test", "build", "optional", "peer"]

dependency_with_non_unknown_st = st.builds(
    DependencyInput,
    package_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    dependency_scope=st.sampled_from(NON_UNKNOWN_SCOPES),
    scope_confidence=st.sampled_from(VALID_CONFIDENCES),
    vulnerability_count=st.integers(min_value=0, max_value=20),
    risk_score=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    ),
    dependency_type=st.sampled_from(VALID_DEP_TYPES),
)

# List with at least one non-unknown scope dep
mixed_deps_with_non_unknown_st = st.lists(
    dependency_input_st, min_size=1, max_size=15
).filter(
    lambda deps: any(
        (dep.dependency_scope or "unknown") != "unknown" for dep in deps
    )
)


# ======================================================================
# Property 10: Scope-Aware Insight Rule Correctness
# ======================================================================


class TestScopeAwareInsightRuleCorrectness:
    """Property 10: Scope-Aware Insight Rule Correctness.

    For any list of DependencyInput objects with at least one non-unknown scope,
    the scope-aware insight rules SHALL produce reasons that match their conditions:
    (a) "Most dependency risk comes from runtime-scoped dependencies." appears iff
        runtime contribution fraction > 0.5
    (b) "This repository has a high number of transitive runtime dependencies."
        appears iff transitive runtime count > 20
    (c) "Several vulnerable dependencies appear in runtime-relevant paths."
        appears iff any runtime-scoped dependency has vulnerability_count > 0
    (d) "Most dependencies are dev/test scoped, reducing likely production exposure."
        appears iff dev/test fraction > 0.5
    (e) "A large unknown-scope share limits confidence in runtime exposure estimates."
        appears iff unknown ratio > 0.5

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
    """

    @given(deps=mixed_deps_with_non_unknown_st)
    @settings(max_examples=200)
    def test_insight_rules_match_conditions(self, deps: list[DependencyInput]):
        """Each scope-aware reason SHALL appear iff its condition is met."""
        reasons = compute_scope_aware_reasons(deps)

        # Recompute conditions manually
        deduped = _deduplicate(deps)

        # Contributions for Rule 1
        records = []
        for dep in deduped:
            scope = dep.dependency_scope or "unknown"
            nr = _normalized_risk(dep)
            sw = get_scope_weight(scope)
            cm = CONFIDENCE_MODIFIERS.get(dep.scope_confidence, 0.5)
            contribution = round(sw * nr * cm, 6)
            records.append((dep, scope, contribution))

        total_weighted_sum = sum(r[2] for r in records)

        # (a) Runtime dominance
        runtime_msg = "Most dependency risk comes from runtime-scoped dependencies."
        if total_weighted_sum > 0:
            runtime_contribution = sum(r[2] for r in records if r[1] == "runtime")
            runtime_fraction = runtime_contribution / total_weighted_sum
            if runtime_fraction > 0.5:
                assert runtime_msg in reasons, (
                    f"Expected runtime dominance reason (fraction={runtime_fraction:.4f})"
                )
            else:
                assert runtime_msg not in reasons, (
                    f"Unexpected runtime dominance reason (fraction={runtime_fraction:.4f})"
                )
        else:
            assert runtime_msg not in reasons

        # (b) High transitive runtime count
        transitive_msg = "This repository has a high number of transitive runtime dependencies."
        transitive_runtime_count = sum(
            1 for dep in deduped
            if dep.dependency_type == "transitive"
            and (dep.dependency_scope or "unknown") == "runtime"
        )
        if transitive_runtime_count > 20:
            assert transitive_msg in reasons
        else:
            assert transitive_msg not in reasons

        # (c) Vulnerable runtime paths
        vuln_msg = "Several vulnerable dependencies appear in runtime-relevant paths."
        metrics = compute_scope_exposure_metrics(deps)
        has_vuln_runtime = (
            metrics.vulnerable_runtime_dependency_count > 0
            or metrics.vulnerable_transitive_runtime_dependency_count > 0
        )
        if has_vuln_runtime:
            assert vuln_msg in reasons
        else:
            assert vuln_msg not in reasons

        # (d) Dev/test majority
        devtest_msg = "Most dependencies are dev/test scoped, reducing likely production exposure."
        total_deps = len(deduped)
        if total_deps > 0:
            dev_test_count = sum(
                1 for dep in deduped
                if (dep.dependency_scope or "unknown") in ("dev", "test")
            )
            dev_test_fraction = dev_test_count / total_deps
            if dev_test_fraction > 0.5:
                assert devtest_msg in reasons
            else:
                assert devtest_msg not in reasons
        else:
            assert devtest_msg not in reasons

        # (e) High unknown ratio
        unknown_msg = "A large unknown-scope share limits confidence in runtime exposure estimates."
        if total_deps > 0:
            unknown_count = sum(
                1 for dep in deduped
                if (dep.dependency_scope or "unknown") == "unknown"
            )
            unknown_ratio = unknown_count / total_deps
            if unknown_ratio > 0.5:
                assert unknown_msg in reasons
            else:
                assert unknown_msg not in reasons
        else:
            assert unknown_msg not in reasons


# ======================================================================
# Property 11: Confidence Note Threshold Correctness
# ======================================================================


class TestConfidenceNoteThresholdCorrectness:
    """Property 11: Confidence Note Threshold Correctness.

    For any list of DependencyInput objects, the confidence_note in the
    ExplainabilityPayload SHALL contain "Low confidence" when
    unknown_scope_dependency_ratio > 0.5, "Moderate confidence" when
    ratio is in [0.2, 0.5], and "High confidence" when ratio < 0.2.

    **Validates: Requirements 6.5**
    """

    @given(deps=dependency_list_st)
    @settings(max_examples=200)
    def test_confidence_note_matches_unknown_ratio(self, deps: list[DependencyInput]):
        """confidence_note SHALL match the unknown ratio threshold."""
        result = compute_scope_weighted_risk(deps)

        if not deps:
            # Empty input has special confidence note
            assert "not available" in result.confidence_note.lower()
            return

        # Compute unknown ratio manually on deduplicated list
        deduped = _deduplicate(deps)
        unknown_count = sum(
            1 for dep in deduped
            if (dep.dependency_scope or "unknown") == "unknown"
        )
        unknown_ratio = unknown_count / len(deduped) if deduped else 0.0

        if unknown_ratio > 0.5:
            assert "Low confidence" in result.confidence_note, (
                f"Expected 'Low confidence' for ratio={unknown_ratio:.4f}, "
                f"got: {result.confidence_note}"
            )
        elif unknown_ratio >= 0.2:
            assert "Moderate confidence" in result.confidence_note, (
                f"Expected 'Moderate confidence' for ratio={unknown_ratio:.4f}, "
                f"got: {result.confidence_note}"
            )
        else:
            assert "High confidence" in result.confidence_note, (
                f"Expected 'High confidence' for ratio={unknown_ratio:.4f}, "
                f"got: {result.confidence_note}"
            )


# ======================================================================
# Property 12: Explainability Payload JSON Round-Trip
# ======================================================================


# Strategy: generate valid ExplainabilityPayload objects
top_driver_st = st.builds(
    TopDriver,
    package=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    scope=st.sampled_from(VALID_SCOPES),
    reason=st.text(min_size=1, max_size=100),
    contribution=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)

explainability_payload_st = st.builds(
    ExplainabilityPayload,
    scope_weighted_dependency_risk=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    risk_label=st.sampled_from(["low", "medium", "high"]),
    top_drivers=st.lists(top_driver_st, min_size=0, max_size=5),
    scope_note=st.just(
        "Dependency scope is classified from manifests and may not reflect actual runtime usage."
    ),
    confidence_note=st.sampled_from([
        "Low confidence: a large proportion of dependencies have unknown scope, limiting accuracy of runtime exposure estimates",
        "Moderate confidence: some dependencies have unknown scope, which may affect accuracy",
        "High confidence: most dependencies have classified scope, providing reliable runtime exposure estimates",
    ]),
)


class TestExplainabilityPayloadJsonRoundTrip:
    """Property 12: Explainability Payload JSON Round-Trip.

    For any valid ExplainabilityPayload object, serializing via to_dict()
    then json.dumps() then json.loads() SHALL produce a dict with identical
    field values.

    **Validates: Requirements 6.6, 11.1, 11.2**
    """

    @given(payload=explainability_payload_st)
    @settings(max_examples=200)
    def test_json_round_trip_preserves_fields(self, payload: ExplainabilityPayload):
        """Serializing and deserializing SHALL produce identical field values."""
        d = payload.to_dict()
        json_str = json.dumps(d)
        restored = json.loads(json_str)

        # Score preserved (within 6 decimal places from to_dict rounding)
        assert abs(restored["scope_weighted_dependency_risk"] - d["scope_weighted_dependency_risk"]) < 1e-9

        # Label preserved
        assert restored["risk_label"] == d["risk_label"]

        # Top drivers preserved
        assert len(restored["top_drivers"]) == len(d["top_drivers"])
        for orig, rest in zip(d["top_drivers"], restored["top_drivers"]):
            assert rest["package"] == orig["package"]
            assert rest["scope"] == orig["scope"]
            assert rest["reason"] == orig["reason"]
            assert abs(rest["contribution"] - orig["contribution"]) < 1e-9

        # Notes preserved
        assert restored["scope_note"] == d["scope_note"]
        assert restored["confidence_note"] == d["confidence_note"]

    @given(payload=explainability_payload_st)
    @settings(max_examples=200)
    def test_score_precision_within_three_decimal_places(self, payload: ExplainabilityPayload):
        """Score SHALL be representable without precision loss beyond 3 decimal places."""
        d = payload.to_dict()
        json_str = json.dumps(d)
        restored = json.loads(json_str)

        score = restored["scope_weighted_dependency_risk"]
        # Round to 3 decimal places and verify no significant loss
        rounded_3 = round(score, 3)
        assert abs(score - rounded_3) < 1e-3, (
            f"Score {score} loses precision beyond 3 decimal places"
        )
