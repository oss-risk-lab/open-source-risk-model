"""Property-based tests for risk rule evaluators.

Verifies:
- Every SignalEvidence has non-empty reason (Property 11)
- score_contribution is always 0.0–0.4 (bounded)
- No positive score from missing release data (Property 7)
- metadata dict is always populated
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from open_source_risk_model.insights.graph_signals import (
    CVESignal,
    MaintainerSignal,
    ReleaseSignal,
)
from open_source_risk_model.insights.risk_rules import (
    evaluate_cve_risk,
    evaluate_maintainer_risk,
    evaluate_release_risk,
)


# ── Strategies ────────────────────────────────────────────────────────

cve_signal_st = st.builds(
    CVESignal,
    total_count=st.integers(min_value=0, max_value=100),
    cve_ids=st.lists(st.text(min_size=1, max_size=30), max_size=100),
    has_critical=st.booleans(),
    has_high=st.booleans(),
)

maintainer_signal_st = st.builds(
    MaintainerSignal,
    top_contributor_username=st.one_of(st.none(), st.text(min_size=1, max_size=40)),
    top_contributor_fraction=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    human_maintainer_count=st.integers(min_value=0, max_value=500),
)

release_signal_st = st.builds(
    ReleaseSignal,
    has_releases=st.booleans(),
    latest_tag=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    days_since_latest=st.one_of(st.none(), st.integers(min_value=0, max_value=5000)),
    total_releases=st.integers(min_value=0, max_value=1000),
)


# ── Property: Every SignalEvidence has non-empty reason (Property 11) ─
# **Validates: Requirements 4.4, 5.5, 6.4**


@given(signal=cve_signal_st)
@settings(max_examples=200)
def test_cve_evidence_has_nonempty_reason(signal):
    """Every CVE SignalEvidence has a non-empty reason string."""
    result = evaluate_cve_risk(signal)
    assert isinstance(result.reason, str)
    assert len(result.reason) > 0


@given(signal=maintainer_signal_st)
@settings(max_examples=200)
def test_maintainer_evidence_has_nonempty_reason(signal):
    """Every maintainer SignalEvidence has a non-empty reason string."""
    result = evaluate_maintainer_risk(signal)
    assert isinstance(result.reason, str)
    assert len(result.reason) > 0


@given(signal=release_signal_st)
@settings(max_examples=200)
def test_release_evidence_has_nonempty_reason(signal):
    """Every release SignalEvidence has a non-empty reason string."""
    result = evaluate_release_risk(signal)
    assert isinstance(result.reason, str)
    assert len(result.reason) > 0


# ── Property: score_contribution is always 0.0–0.4 ───────────────────
# **Validates: Requirements 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3**


@given(signal=cve_signal_st)
@settings(max_examples=200)
def test_cve_score_bounded(signal):
    """CVE score_contribution is always in [0.0, 0.4]."""
    result = evaluate_cve_risk(signal)
    assert 0.0 <= result.score_contribution <= 0.4


@given(signal=maintainer_signal_st)
@settings(max_examples=200)
def test_maintainer_score_bounded(signal):
    """Maintainer score_contribution is always in [0.0, 0.3]."""
    result = evaluate_maintainer_risk(signal)
    assert 0.0 <= result.score_contribution <= 0.3


@given(signal=release_signal_st)
@settings(max_examples=200)
def test_release_score_bounded(signal):
    """Release score_contribution is always in [0.0, 0.3]."""
    result = evaluate_release_risk(signal)
    assert 0.0 <= result.score_contribution <= 0.3


# ── Property: No positive score from missing release data (Property 7) ─
# **Validates: Requirements 6.6**


@given(
    total_releases=st.integers(min_value=0, max_value=100),
    latest_tag=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
)
@settings(max_examples=200)
def test_no_positive_score_when_no_releases(total_releases, latest_tag):
    """When has_releases is False, score_contribution must be 0.0."""
    signal = ReleaseSignal(
        has_releases=False,
        days_since_latest=None,
        latest_tag=latest_tag,
        total_releases=total_releases,
    )
    result = evaluate_release_risk(signal)
    assert result.score_contribution == 0.0


@given(
    total_releases=st.integers(min_value=0, max_value=100),
    latest_tag=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
)
@settings(max_examples=200)
def test_no_positive_score_when_days_none(total_releases, latest_tag):
    """When has_releases is True but days_since_latest is None, score must be 0.0."""
    signal = ReleaseSignal(
        has_releases=True,
        days_since_latest=None,
        latest_tag=latest_tag,
        total_releases=total_releases,
    )
    result = evaluate_release_risk(signal)
    assert result.score_contribution == 0.0


# ── Property: metadata dict is always populated ───────────────────────
# **Validates: Requirements 4, 5, 6**


@given(signal=cve_signal_st)
@settings(max_examples=200)
def test_cve_metadata_always_populated(signal):
    """CVE metadata always has the required keys."""
    result = evaluate_cve_risk(signal)
    assert isinstance(result.metadata, dict)
    assert "total_count" in result.metadata
    assert "has_critical" in result.metadata
    assert "has_high" in result.metadata
    assert "cve_ids" in result.metadata


@given(signal=maintainer_signal_st)
@settings(max_examples=200)
def test_maintainer_metadata_always_populated(signal):
    """Maintainer metadata always has the required keys."""
    result = evaluate_maintainer_risk(signal)
    assert isinstance(result.metadata, dict)
    assert "top_contributor_username" in result.metadata
    assert "top_contributor_fraction" in result.metadata
    assert "human_maintainer_count" in result.metadata


@given(signal=release_signal_st)
@settings(max_examples=200)
def test_release_metadata_always_populated(signal):
    """Release metadata always has the required keys."""
    result = evaluate_release_risk(signal)
    assert isinstance(result.metadata, dict)
    assert "days_since_latest" in result.metadata
    assert "has_releases" in result.metadata
    assert "latest_tag" in result.metadata
    assert "total_releases" in result.metadata
