"""Risk rule evaluators for the insight layer.

Pure functions that take signal dataclasses and return SignalEvidence.
No DB access, no API calls, no side effects.
"""
from __future__ import annotations

from .graph_signals import CVESignal, MaintainerSignal, ReleaseSignal
from .models import SignalEvidence


def evaluate_cve_risk(signal: CVESignal) -> SignalEvidence:
    """Evaluate CVE signal into risk evidence (Req 4.1-4.4)."""
    meta = {
        "total_count": signal.total_count,
        "has_critical": signal.has_critical,
        "has_high": signal.has_high,
        "cve_ids": signal.cve_ids,
    }
    if signal.has_critical or signal.has_high:
        return SignalEvidence(
            signal_name="cve_risk",
            severity="high",
            score_contribution=0.4,
            reason=f"{signal.total_count} CVE(s) found, including critical/high severity",
            metadata=meta,
        )
    if signal.total_count > 0:
        return SignalEvidence(
            signal_name="cve_risk",
            severity="medium",
            score_contribution=0.2,
            reason=f"{signal.total_count} CVE(s) found, no critical/high severity",
            metadata=meta,
        )
    return SignalEvidence(
        signal_name="cve_risk",
        severity="info",
        score_contribution=0.0,
        reason="No known CVEs",
        metadata=meta,
    )


def evaluate_maintainer_risk(signal: MaintainerSignal) -> SignalEvidence:
    """Evaluate maintainer concentration into risk evidence (Req 5.1-5.5)."""
    fraction = signal.top_contributor_fraction
    username = signal.top_contributor_username or "unknown"
    pct = f"{fraction:.0%}"
    meta = {
        "top_contributor_username": username,
        "top_contributor_fraction": fraction,
        "human_maintainer_count": signal.human_maintainer_count,
    }

    if fraction > 0.8:
        return SignalEvidence(
            signal_name="maintainer_concentration",
            severity="high",
            score_contribution=0.3,
            reason=f"Top contributor {username} accounts for {pct} of commits",
            metadata=meta,
        )
    if fraction > 0.65:
        return SignalEvidence(
            signal_name="maintainer_concentration",
            severity="medium",
            score_contribution=0.15,
            reason=f"Top contributor {username} accounts for {pct} of commits",
            metadata=meta,
        )
    if fraction > 0.5:
        return SignalEvidence(
            signal_name="maintainer_concentration",
            severity="mild",
            score_contribution=0.05,
            reason=f"Top contributor {username} accounts for {pct} of commits",
            metadata=meta,
        )
    return SignalEvidence(
        signal_name="maintainer_concentration",
        severity="info",
        score_contribution=0.0,
        reason=f"Maintainer concentration is healthy ({pct} top contributor)",
        metadata=meta,
    )


def evaluate_release_risk(signal: ReleaseSignal) -> SignalEvidence:
    """Evaluate release staleness into risk evidence (Req 6.1-6.6).

    Absence of release metadata does not contribute positive risk (Req 6.6).
    """
    meta = {
        "days_since_latest": signal.days_since_latest,
        "has_releases": signal.has_releases,
        "latest_tag": signal.latest_tag,
        "total_releases": signal.total_releases,
    }
    if not signal.has_releases:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="info",
            score_contribution=0.0,
            reason="No release data available",
            metadata=meta,
        )
    if signal.days_since_latest is None:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="info",
            score_contribution=0.0,
            reason="Latest release could not be determined",
            metadata=meta,
        )
    days = signal.days_since_latest
    if days > 365:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="high",
            score_contribution=0.3,
            reason=f"Last release was {days} days ago (over 1 year)",
            metadata=meta,
        )
    if days > 180:
        return SignalEvidence(
            signal_name="release_staleness",
            severity="medium",
            score_contribution=0.15,
            reason=f"Last release was {days} days ago (over 6 months)",
            metadata=meta,
        )
    return SignalEvidence(
        signal_name="release_staleness",
        severity="info",
        score_contribution=0.0,
        reason=f"Last release was {days} days ago",
        metadata=meta,
    )
