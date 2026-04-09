"""Extract raw signals from graph JSON.

Pure functions — no DB access, no API calls.
Input: parsed graph dict (from repo_graphs.graph_json).
Output: structured signal data for rules to consume.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Known bot accounts to exclude from maintainer analysis
BOT_SUFFIXES = ("[bot]",)

# Additional bot username patterns (CI robots, merge bots, etc.)
BOT_PATTERNS = (
    "-ci-robot",
    "mergebot",
    "camperbot",
    "-robot",
    "-release-bot",
    "renovate-bot",
    "localstack-bot",
)


@dataclass
class CVESignal:
    """Raw CVE data extracted from graph."""
    total_count: int = 0
    cve_ids: list[str] = field(default_factory=list)
    severities: list[str] = field(default_factory=list)  # raw CVSS strings
    has_critical: bool = False
    has_high: bool = False


@dataclass
class MaintainerSignal:
    """Raw maintainer concentration data."""
    top_contributor_username: Optional[str] = None
    top_contributor_fraction: float = 0.0
    human_maintainer_count: int = 0
    total_maintainer_count: int = 0


@dataclass
class ReleaseSignal:
    """Raw release staleness data."""
    has_releases: bool = False
    latest_tag: Optional[str] = None
    days_since_latest: Optional[int] = None
    total_releases: int = 0


@dataclass
class BaseRiskSignal:
    """Existing maintenance risk from the repo node."""
    maintenance_risk: Optional[float] = None
    maintenance_label: Optional[str] = None
    confidence: Optional[str] = None


def _is_bot(username: str) -> bool:
    if any(username.endswith(s) for s in BOT_SUFFIXES):
        return True
    lower = username.lower()
    return any(p in lower for p in BOT_PATTERNS)


def _parse_cvss_severity(cvss_string: str) -> Optional[str]:
    """Attempt to extract severity bucket from CVSS vector string.

    Returns 'critical', 'high', 'medium', 'low', or None.
    Handles both CVSS:3.x and CVSS:4.0 vector formats.
    """
    if not cvss_string:
        return None
    # Look for AV:N/AC:L patterns that suggest network-accessible, low-complexity
    parts = cvss_string.upper().split("/")
    attack_vector = None
    attack_complexity = None
    for p in parts:
        if p.startswith("AV:"):
            attack_vector = p[3:]
        elif p.startswith("AC:"):
            attack_complexity = p[3:]
    # Simple heuristic: network + low complexity = at least high
    if attack_vector == "N" and attack_complexity == "L":
        return "high"
    elif attack_vector == "N":
        return "medium"
    return "low"

def _severity_from_cvss_score(score: float | None) -> str | None:
    """Map numeric CVSS score to severity bucket.

    ≥9.0 → critical, ≥7.0 → high, ≥4.0 → medium, <4.0 → low.
    Returns None if score is None.
    """
    if score is None:
        return None
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


def _extract_severity_bucket(meta: dict) -> str | None:
    """Three-step fallback chain for severity extraction (Req 1.2-1.4).

    1. Normalized cvss_score field → map to bucket
    2. CVSS vector string in severity field → parse to bucket
    3. Neither → return None (count-only)
    """
    # Step 1: normalized cvss_score field
    cvss_score = meta.get("cvss_score")
    if cvss_score is not None:
        try:
            return _severity_from_cvss_score(float(cvss_score))
        except (ValueError, TypeError):
            pass

    # Step 2: CVSS vector string
    severity_str = meta.get("severity", "")
    if severity_str:
        bucket = _parse_cvss_severity(severity_str)
        if bucket:
            return bucket

    # Step 3: count-only fallback
    return None



def extract_cve_signal(graph: dict[str, Any]) -> CVESignal:
    """Extract CVE signal from graph nodes.

    Uses the three-step severity fallback chain via _extract_severity_bucket().
    """
    signal = CVESignal()
    for node in graph.get("nodes", []):
        if node.get("type") != "cve":
            continue
        signal.total_count += 1
        meta = node.get("metadata", {})
        cve_id = meta.get("cve_id") or meta.get("ghsa_id") or meta.get("id", "")
        signal.cve_ids.append(cve_id)
        severity_str = meta.get("severity", "")
        signal.severities.append(severity_str)
        bucket = _extract_severity_bucket(meta)
        if bucket == "critical":
            signal.has_critical = True
        elif bucket == "high":
            signal.has_high = True
    return signal


def extract_maintainer_signal(graph: dict[str, Any]) -> MaintainerSignal:
    """Extract maintainer concentration from graph nodes.

    Filters out bot accounts before computing concentration.
    """
    signal = MaintainerSignal()
    humans = []
    for node in graph.get("nodes", []):
        if node.get("type") != "maintainer":
            continue
        signal.total_maintainer_count += 1
        meta = node.get("metadata", {})
        username = meta.get("username", "")
        if _is_bot(username):
            continue
        fraction = meta.get("contribution_fraction", 0.0)
        humans.append((username, fraction))
    signal.human_maintainer_count = len(humans)
    if humans:
        humans.sort(key=lambda x: x[1], reverse=True)
        signal.top_contributor_username = humans[0][0]
        signal.top_contributor_fraction = humans[0][1]
    return signal


def extract_release_signal(graph: dict[str, Any]) -> ReleaseSignal:
    """Extract release staleness from graph nodes."""
    signal = ReleaseSignal()
    for node in graph.get("nodes", []):
        if node.get("type") != "release":
            continue
        signal.total_releases += 1
        signal.has_releases = True
        meta = node.get("metadata", {})
        if meta.get("is_latest"):
            signal.latest_tag = meta.get("tag_name")
            signal.days_since_latest = meta.get("days_ago")
    return signal


def extract_base_risk(graph: dict[str, Any]) -> BaseRiskSignal:
    """Extract existing maintenance risk from the repo node."""
    for node in graph.get("nodes", []):
        if node.get("type") != "repo":
            continue
        meta = node.get("metadata", {})
        return BaseRiskSignal(
            maintenance_risk=meta.get("maintenance_risk"),
            maintenance_label=meta.get("maintenance_label"),
            confidence=meta.get("confidence"),
        )
    return BaseRiskSignal()
