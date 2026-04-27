"""Tests for RepoInsight serialization and round-trip behavior.

Validates Requirements 8.3, 8.4, 11.3, 11.4, 11.5, 11.6.
"""
import pytest

from src.open_source_risk_model.insights.models import (
    RepoInsight,
    SignalEvidence,
    DependencyRisk,
)


def _make_full_insight(
    graph_signal_score: float = 0.55,
    cve_contribution: float = 0.4,
    maintainer_contribution: float = 0.15,
    release_contribution: float = 0.0,
) -> RepoInsight:
    """Helper to build a fully-populated RepoInsight."""
    return RepoInsight(
        repo_full_name="owner/repo",
        base_maintenance_risk=0.42,
        base_maintenance_label="MEDIUM",
        graph_signal_score=graph_signal_score,
        graph_signal_label="MEDIUM",
        reasons=[
            "3 CVE(s) found, including critical/high severity",
            "Top contributor alice accounts for 70% of commits",
        ],
        direct_signals=[
            SignalEvidence(
                signal_name="cve_risk",
                severity="high",
                score_contribution=cve_contribution,
                reason="3 CVE(s) found, including critical/high severity",
            ),
            SignalEvidence(
                signal_name="maintainer_concentration",
                severity="medium",
                score_contribution=maintainer_contribution,
                reason="Top contributor alice accounts for 70% of commits",
            ),
            SignalEvidence(
                signal_name="release_staleness",
                severity="info",
                score_contribution=release_contribution,
                reason="Last release was 30 days ago",
            ),
        ],
    )


# ── 6.1 Round-trip: serialize → construct → serialize produces identical output ──


class TestToDictRoundTrip:
    """Validates Req 8.4, 11.6: round-trip serialization property."""

    def test_round_trip_full_insight(self):
        """Serialize, reconstruct from dict fields, serialize again — dicts match."""
        insight = _make_full_insight()
        d1 = insight.to_dict()

        # Reconstruct a new RepoInsight from the serialized dict fields
        reconstructed = RepoInsight(
            repo_full_name=d1["repo_full_name"],
            base_maintenance_risk=d1["base_maintenance_risk"],
            base_maintenance_label=d1["base_maintenance_label"],
            graph_signal_score=d1["graph_signal_score"],
            graph_signal_label=d1["graph_signal_label"],
            reasons=list(d1["reasons"]),
            direct_signals=[
                SignalEvidence(
                    signal_name=s["signal_name"],
                    severity=s["severity"],
                    score_contribution=s["score_contribution"],
                    reason=s["reason"],
                )
                for s in d1["direct_signals"]
            ],
        )
        d2 = reconstructed.to_dict()

        assert d1 == d2

    def test_round_trip_default_insight(self):
        """Default RepoInsight round-trips cleanly."""
        insight = RepoInsight(repo_full_name="org/default")
        d1 = insight.to_dict()

        reconstructed = RepoInsight(
            repo_full_name=d1["repo_full_name"],
            base_maintenance_risk=d1["base_maintenance_risk"],
            base_maintenance_label=d1["base_maintenance_label"],
            graph_signal_score=d1["graph_signal_score"],
            graph_signal_label=d1["graph_signal_label"],
            reasons=list(d1["reasons"]),
            direct_signals=[
                SignalEvidence(
                    signal_name=s["signal_name"],
                    severity=s["severity"],
                    score_contribution=s["score_contribution"],
                    reason=s["reason"],
                )
                for s in d1["direct_signals"]
            ],
        )
        d2 = reconstructed.to_dict()

        assert d1 == d2

    def test_round_trip_preserves_all_fields(self):
        """Every top-level key survives the round-trip."""
        insight = _make_full_insight()
        d1 = insight.to_dict()
        expected_keys = {
            "repo_full_name",
            "base_maintenance_risk",
            "base_maintenance_label",
            "graph_signal_score",
            "graph_signal_label",
            "reasons",
            "direct_signals",
            "top_risky_dependencies",
        }
        assert set(d1.keys()) == expected_keys


# ── 6.2 Rounding: graph_signal_score and score_contribution ≤ 3 decimal places ──


def _decimal_places(value: float) -> int:
    """Return the number of decimal places in a float's string representation."""
    s = f"{value:.10f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".")[1])


class TestToDictRounding:
    """Validates Req 8.3, 11.3: rounding to at most 3 decimal places."""

    def test_graph_signal_score_rounded(self):
        """graph_signal_score with many decimals is rounded to 3 places."""
        insight = _make_full_insight(graph_signal_score=0.33333333)
        d = insight.to_dict()
        assert d["graph_signal_score"] == round(0.33333333, 3)
        assert _decimal_places(d["graph_signal_score"]) <= 3

    def test_score_contribution_rounded(self):
        """Each score_contribution in direct_signals is rounded to 3 places."""
        insight = _make_full_insight(
            cve_contribution=0.123456789,
            maintainer_contribution=0.987654321,
            release_contribution=0.111111111,
        )
        d = insight.to_dict()
        for signal in d["direct_signals"]:
            assert _decimal_places(signal["score_contribution"]) <= 3

    def test_rounding_values_correct(self):
        """Verify specific rounded values."""
        insight = _make_full_insight(
            graph_signal_score=0.55555555,
            cve_contribution=0.44444444,
            maintainer_contribution=0.11111111,
            release_contribution=0.0,
        )
        d = insight.to_dict()
        assert d["graph_signal_score"] == 0.556
        assert d["direct_signals"][0]["score_contribution"] == 0.444
        assert d["direct_signals"][1]["score_contribution"] == 0.111
        assert d["direct_signals"][2]["score_contribution"] == 0.0

    def test_already_rounded_values_unchanged(self):
        """Values that already have ≤3 decimal places are not altered."""
        insight = _make_full_insight(
            graph_signal_score=0.5,
            cve_contribution=0.4,
            maintainer_contribution=0.15,
            release_contribution=0.0,
        )
        d = insight.to_dict()
        assert d["graph_signal_score"] == 0.5
        assert d["direct_signals"][0]["score_contribution"] == 0.4
        assert d["direct_signals"][1]["score_contribution"] == 0.15


# ── 6.3 Deterministic signal order ──


class TestDeterministicSignalOrder:
    """Validates Req 7.10, 11.4: direct_signals order is always
    cve_risk, maintainer_concentration, release_staleness."""

    def test_signal_order_in_to_dict(self):
        """to_dict() preserves the canonical signal order."""
        insight = _make_full_insight()
        d = insight.to_dict()
        signal_names = [s["signal_name"] for s in d["direct_signals"]]
        assert signal_names == [
            "cve_risk",
            "maintainer_concentration",
            "release_staleness",
        ]

    def test_signal_order_with_three_signals(self):
        """Explicitly constructed signals in correct order stay ordered."""
        signals = [
            SignalEvidence(
                signal_name="cve_risk",
                severity="info",
                score_contribution=0.0,
                reason="No known CVEs",
            ),
            SignalEvidence(
                signal_name="maintainer_concentration",
                severity="info",
                score_contribution=0.0,
                reason="Healthy maintainer distribution",
            ),
            SignalEvidence(
                signal_name="release_staleness",
                severity="info",
                score_contribution=0.0,
                reason="Recent release",
            ),
        ]
        insight = RepoInsight(
            repo_full_name="test/repo",
            direct_signals=signals,
        )
        d = insight.to_dict()
        names = [s["signal_name"] for s in d["direct_signals"]]
        assert names == [
            "cve_risk",
            "maintainer_concentration",
            "release_staleness",
        ]


# ── 6.4 top_risky_dependencies defaults to empty list in v1 ──


class TestTopRiskyDependenciesDefault:
    """Validates Req 11.5: top_risky_dependencies defaults to empty list."""

    def test_default_empty_list(self):
        """A default RepoInsight has top_risky_dependencies == []."""
        insight = RepoInsight(repo_full_name="org/project")
        d = insight.to_dict()
        assert d["top_risky_dependencies"] == []

    def test_full_insight_empty_list(self):
        """A fully-populated insight (without explicit deps) still has empty list."""
        insight = _make_full_insight()
        d = insight.to_dict()
        assert d["top_risky_dependencies"] == []
