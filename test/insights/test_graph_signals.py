"""Unit tests for CVSS severity fallback chain in graph_signals.py.

Covers:
- _severity_from_cvss_score() bucket mapping
- _extract_severity_bucket() three-step fallback
- extract_cve_signal() integration with the fallback chain
"""
import pytest

from src.open_source_risk_model.insights.graph_signals import (
    _severity_from_cvss_score,
    _extract_severity_bucket,
    extract_cve_signal,
)


# ── _severity_from_cvss_score ──────────────────────────────────────────

class TestSeverityFromCvssScore:
    def test_none_returns_none(self):
        assert _severity_from_cvss_score(None) is None

    def test_critical_at_9(self):
        assert _severity_from_cvss_score(9.0) == "critical"

    def test_critical_above_9(self):
        assert _severity_from_cvss_score(10.0) == "critical"

    def test_high_at_7(self):
        assert _severity_from_cvss_score(7.0) == "high"

    def test_high_at_8_9(self):
        assert _severity_from_cvss_score(8.9) == "high"

    def test_medium_at_4(self):
        assert _severity_from_cvss_score(4.0) == "medium"

    def test_medium_at_6_9(self):
        assert _severity_from_cvss_score(6.9) == "medium"

    def test_low_below_4(self):
        assert _severity_from_cvss_score(3.9) == "low"

    def test_low_at_zero(self):
        assert _severity_from_cvss_score(0.0) == "low"


# ── _extract_severity_bucket ───────────────────────────────────────────

class TestExtractSeverityBucket:
    """Tests the three-step fallback chain."""

    def test_step1_cvss_score_critical(self):
        """Step 1: cvss_score present → maps to bucket."""
        meta = {"cvss_score": 9.8}
        assert _extract_severity_bucket(meta) == "critical"

    def test_step1_cvss_score_high(self):
        meta = {"cvss_score": 7.5}
        assert _extract_severity_bucket(meta) == "high"

    def test_step1_cvss_score_medium(self):
        meta = {"cvss_score": 5.0}
        assert _extract_severity_bucket(meta) == "medium"

    def test_step1_cvss_score_low(self):
        meta = {"cvss_score": 2.0}
        assert _extract_severity_bucket(meta) == "low"

    def test_step1_cvss_score_as_string(self):
        """cvss_score stored as string should still work."""
        meta = {"cvss_score": "9.1"}
        assert _extract_severity_bucket(meta) == "critical"

    def test_step1_takes_priority_over_severity_field(self):
        """When both cvss_score and severity are present, cvss_score wins."""
        meta = {"cvss_score": 3.0, "severity": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N"}
        assert _extract_severity_bucket(meta) == "low"

    def test_step2_cvss_vector_fallback(self):
        """Step 2: no cvss_score, but severity has CVSS vector."""
        meta = {"severity": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N"}
        assert _extract_severity_bucket(meta) == "high"

    def test_step2_cvss_vector_network_only(self):
        meta = {"severity": "CVSS:3.1/AV:N/AC:H/PR:N/UI:N"}
        assert _extract_severity_bucket(meta) == "medium"

    def test_step3_count_only_no_fields(self):
        """Step 3: neither cvss_score nor severity → None."""
        meta = {}
        assert _extract_severity_bucket(meta) is None

    def test_step3_count_only_empty_severity(self):
        meta = {"severity": ""}
        assert _extract_severity_bucket(meta) is None

    def test_step1_invalid_cvss_score_falls_through(self):
        """Invalid cvss_score falls through to step 2."""
        meta = {"cvss_score": "not-a-number", "severity": "CVSS:3.1/AV:N/AC:L"}
        assert _extract_severity_bucket(meta) == "high"

    def test_step1_invalid_cvss_score_no_severity_returns_none(self):
        """Invalid cvss_score with no severity → None."""
        meta = {"cvss_score": "bad"}
        assert _extract_severity_bucket(meta) is None


# ── extract_cve_signal integration ─────────────────────────────────────

class TestExtractCveSignalFallback:
    """Tests that extract_cve_signal uses the fallback chain correctly."""

    def test_cvss_score_sets_critical(self):
        """CVE with cvss_score ≥ 9.0 sets has_critical."""
        graph = {"nodes": [
            {"type": "cve", "metadata": {"cve_id": "CVE-2024-001", "cvss_score": 9.8}},
        ]}
        signal = extract_cve_signal(graph)
        assert signal.total_count == 1
        assert signal.has_critical is True

    def test_cvss_score_sets_high(self):
        """CVE with cvss_score ≥ 7.0 sets has_high."""
        graph = {"nodes": [
            {"type": "cve", "metadata": {"cve_id": "CVE-2024-002", "cvss_score": 7.5}},
        ]}
        signal = extract_cve_signal(graph)
        assert signal.has_high is True
        assert signal.has_critical is False

    def test_cvss_score_medium_no_flags(self):
        """CVE with cvss_score in medium range sets neither flag."""
        graph = {"nodes": [
            {"type": "cve", "metadata": {"cve_id": "CVE-2024-003", "cvss_score": 5.0}},
        ]}
        signal = extract_cve_signal(graph)
        assert signal.total_count == 1
        assert signal.has_critical is False
        assert signal.has_high is False

    def test_vector_fallback_when_no_score(self):
        """Falls back to CVSS vector parsing when no cvss_score."""
        graph = {"nodes": [
            {"type": "cve", "metadata": {
                "cve_id": "CVE-2024-004",
                "severity": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N",
            }},
        ]}
        signal = extract_cve_signal(graph)
        assert signal.has_high is True

    def test_count_only_when_no_severity_info(self):
        """Count-only: no cvss_score, no severity → counted but no flags."""
        graph = {"nodes": [
            {"type": "cve", "metadata": {"cve_id": "CVE-2024-005"}},
        ]}
        signal = extract_cve_signal(graph)
        assert signal.total_count == 1
        assert signal.cve_ids == ["CVE-2024-005"]
        assert signal.has_critical is False
        assert signal.has_high is False

    def test_mixed_fallback_steps(self):
        """Multiple CVEs using different fallback steps."""
        graph = {"nodes": [
            # Step 1: cvss_score → critical
            {"type": "cve", "metadata": {"cve_id": "CVE-A", "cvss_score": 9.5}},
            # Step 2: vector → high
            {"type": "cve", "metadata": {"cve_id": "CVE-B", "severity": "CVSS:3.1/AV:N/AC:L"}},
            # Step 3: count-only
            {"type": "cve", "metadata": {"cve_id": "CVE-C"}},
        ]}
        signal = extract_cve_signal(graph)
        assert signal.total_count == 3
        assert signal.has_critical is True
        assert signal.has_high is True
        assert set(signal.cve_ids) == {"CVE-A", "CVE-B", "CVE-C"}

    def test_no_cve_nodes(self):
        """Empty graph returns default signal."""
        graph = {"nodes": [{"type": "repo", "metadata": {}}]}
        signal = extract_cve_signal(graph)
        assert signal.total_count == 0
        assert signal.cve_ids == []
        assert signal.has_critical is False
        assert signal.has_high is False
