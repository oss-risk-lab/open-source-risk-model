"""Unit tests for risk rule evaluators.

Covers all threshold boundaries, edge cases, and metadata population.
"""
import pytest

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


# ── CVE Risk ──────────────────────────────────────────────────────────


class TestEvaluateCveRisk:
    """Tests for evaluate_cve_risk() — Req 4."""

    def test_critical_cve_returns_high(self):
        signal = CVESignal(total_count=1, cve_ids=["CVE-2024-001"], has_critical=True, has_high=False)
        result = evaluate_cve_risk(signal)
        assert result.severity == "high"
        assert result.score_contribution == 0.4
        assert result.signal_name == "cve_risk"

    def test_high_cve_returns_high(self):
        signal = CVESignal(total_count=2, cve_ids=["CVE-1", "CVE-2"], has_critical=False, has_high=True)
        result = evaluate_cve_risk(signal)
        assert result.severity == "high"
        assert result.score_contribution == 0.4

    def test_critical_and_high_returns_high(self):
        signal = CVESignal(total_count=3, cve_ids=["A", "B", "C"], has_critical=True, has_high=True)
        result = evaluate_cve_risk(signal)
        assert result.severity == "high"
        assert result.score_contribution == 0.4

    def test_medium_only_cves(self):
        signal = CVESignal(total_count=2, cve_ids=["CVE-1", "CVE-2"], has_critical=False, has_high=False)
        result = evaluate_cve_risk(signal)
        assert result.severity == "medium"
        assert result.score_contribution == 0.2

    def test_single_low_cve(self):
        signal = CVESignal(total_count=1, cve_ids=["CVE-1"], has_critical=False, has_high=False)
        result = evaluate_cve_risk(signal)
        assert result.severity == "medium"
        assert result.score_contribution == 0.2

    def test_zero_cves_returns_info(self):
        signal = CVESignal(total_count=0, cve_ids=[], has_critical=False, has_high=False)
        result = evaluate_cve_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0

    def test_reason_is_nonempty(self):
        signal = CVESignal()
        result = evaluate_cve_risk(signal)
        assert len(result.reason) > 0

    def test_metadata_populated_with_cves(self):
        signal = CVESignal(total_count=2, cve_ids=["CVE-1", "CVE-2"], has_critical=True, has_high=False)
        result = evaluate_cve_risk(signal)
        assert result.metadata["total_count"] == 2
        assert result.metadata["has_critical"] is True
        assert result.metadata["has_high"] is False
        assert result.metadata["cve_ids"] == ["CVE-1", "CVE-2"]

    def test_metadata_populated_zero_cves(self):
        signal = CVESignal()
        result = evaluate_cve_risk(signal)
        assert result.metadata["total_count"] == 0
        assert result.metadata["has_critical"] is False
        assert result.metadata["has_high"] is False
        assert result.metadata["cve_ids"] == []


# ── Maintainer Risk ───────────────────────────────────────────────────


class TestEvaluateMaintainerRisk:
    """Tests for evaluate_maintainer_risk() — Req 5."""

    def test_fraction_above_0_8_returns_high(self):
        signal = MaintainerSignal(
            top_contributor_username="alice",
            top_contributor_fraction=0.85,
            human_maintainer_count=3,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "high"
        assert result.score_contribution == 0.3

    def test_fraction_exactly_0_8_returns_medium(self):
        """0.8 is NOT > 0.8, so it falls to the next bucket."""
        signal = MaintainerSignal(
            top_contributor_username="bob",
            top_contributor_fraction=0.8,
            human_maintainer_count=2,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "medium"
        assert result.score_contribution == 0.15

    def test_fraction_above_0_65_returns_medium(self):
        signal = MaintainerSignal(
            top_contributor_username="carol",
            top_contributor_fraction=0.7,
            human_maintainer_count=4,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "medium"
        assert result.score_contribution == 0.15

    def test_fraction_exactly_0_65_returns_mild(self):
        """0.65 is NOT > 0.65, so it falls to the next bucket."""
        signal = MaintainerSignal(
            top_contributor_username="dave",
            top_contributor_fraction=0.65,
            human_maintainer_count=3,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "mild"
        assert result.score_contribution == 0.05

    def test_fraction_above_0_5_returns_mild(self):
        signal = MaintainerSignal(
            top_contributor_username="eve",
            top_contributor_fraction=0.55,
            human_maintainer_count=5,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "mild"
        assert result.score_contribution == 0.05

    def test_fraction_exactly_0_5_returns_info(self):
        """0.5 is NOT > 0.5, so it falls to info."""
        signal = MaintainerSignal(
            top_contributor_username="frank",
            top_contributor_fraction=0.5,
            human_maintainer_count=2,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0

    def test_fraction_below_0_5_returns_info(self):
        signal = MaintainerSignal(
            top_contributor_username="grace",
            top_contributor_fraction=0.3,
            human_maintainer_count=10,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0

    def test_zero_fraction_returns_info(self):
        signal = MaintainerSignal(
            top_contributor_fraction=0.0,
            human_maintainer_count=0,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0

    def test_none_username_defaults_to_unknown(self):
        signal = MaintainerSignal(
            top_contributor_username=None,
            top_contributor_fraction=0.9,
            human_maintainer_count=1,
        )
        result = evaluate_maintainer_risk(signal)
        assert "unknown" in result.reason

    def test_reason_contains_username_and_percentage(self):
        signal = MaintainerSignal(
            top_contributor_username="alice",
            top_contributor_fraction=0.85,
            human_maintainer_count=3,
        )
        result = evaluate_maintainer_risk(signal)
        assert "alice" in result.reason
        assert "85%" in result.reason

    def test_metadata_populated(self):
        signal = MaintainerSignal(
            top_contributor_username="alice",
            top_contributor_fraction=0.75,
            human_maintainer_count=4,
        )
        result = evaluate_maintainer_risk(signal)
        assert result.metadata["top_contributor_username"] == "alice"
        assert result.metadata["top_contributor_fraction"] == 0.75
        assert result.metadata["human_maintainer_count"] == 4


# ── Release Risk ──────────────────────────────────────────────────────


class TestEvaluateReleaseRisk:
    """Tests for evaluate_release_risk() — Req 6."""

    def test_over_365_days_returns_high(self):
        signal = ReleaseSignal(has_releases=True, days_since_latest=400, latest_tag="v1.0", total_releases=5)
        result = evaluate_release_risk(signal)
        assert result.severity == "high"
        assert result.score_contribution == 0.3

    def test_exactly_365_days_returns_medium(self):
        """365 is NOT > 365, so it falls to medium bucket (> 180)."""
        signal = ReleaseSignal(has_releases=True, days_since_latest=365, latest_tag="v2.0", total_releases=3)
        result = evaluate_release_risk(signal)
        assert result.severity == "medium"
        assert result.score_contribution == 0.15

    def test_over_180_days_returns_medium(self):
        signal = ReleaseSignal(has_releases=True, days_since_latest=200, latest_tag="v3.0", total_releases=10)
        result = evaluate_release_risk(signal)
        assert result.severity == "medium"
        assert result.score_contribution == 0.15

    def test_exactly_180_days_returns_info(self):
        """180 is NOT > 180, so it falls to info."""
        signal = ReleaseSignal(has_releases=True, days_since_latest=180, latest_tag="v4.0", total_releases=2)
        result = evaluate_release_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0

    def test_recent_release_returns_info(self):
        signal = ReleaseSignal(has_releases=True, days_since_latest=30, latest_tag="v5.0", total_releases=20)
        result = evaluate_release_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0

    def test_zero_days_returns_info(self):
        signal = ReleaseSignal(has_releases=True, days_since_latest=0, latest_tag="v6.0", total_releases=1)
        result = evaluate_release_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0

    def test_no_releases_returns_info_zero_score(self):
        signal = ReleaseSignal(has_releases=False)
        result = evaluate_release_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0
        assert "No release data" in result.reason

    def test_has_releases_but_none_days_returns_info_zero_score(self):
        signal = ReleaseSignal(has_releases=True, days_since_latest=None, total_releases=3)
        result = evaluate_release_risk(signal)
        assert result.severity == "info"
        assert result.score_contribution == 0.0
        assert "could not be determined" in result.reason

    def test_reason_is_nonempty(self):
        signal = ReleaseSignal()
        result = evaluate_release_risk(signal)
        assert len(result.reason) > 0

    def test_metadata_populated_with_releases(self):
        signal = ReleaseSignal(has_releases=True, days_since_latest=100, latest_tag="v1.0", total_releases=5)
        result = evaluate_release_risk(signal)
        assert result.metadata["days_since_latest"] == 100
        assert result.metadata["has_releases"] is True
        assert result.metadata["latest_tag"] == "v1.0"
        assert result.metadata["total_releases"] == 5

    def test_metadata_populated_no_releases(self):
        signal = ReleaseSignal(has_releases=False)
        result = evaluate_release_risk(signal)
        assert result.metadata["days_since_latest"] is None
        assert result.metadata["has_releases"] is False
        assert result.metadata["latest_tag"] is None
        assert result.metadata["total_releases"] == 0

    def test_absence_of_release_data_never_positive_score(self):
        """Req 6.6: absence of release metadata SHALL NOT contribute positive risk."""
        for signal in [
            ReleaseSignal(has_releases=False),
            ReleaseSignal(has_releases=True, days_since_latest=None),
        ]:
            result = evaluate_release_risk(signal)
            assert result.score_contribution == 0.0
