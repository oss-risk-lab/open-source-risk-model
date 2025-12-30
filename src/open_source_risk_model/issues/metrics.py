from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _load_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def compute_issue_metrics(repo_dir: str) -> Dict[str, float]:
    """
    Compute deterministic issue lifecycle metrics for a repo.

    repo_dir example:
      data/issues/numpy__numpy
    """
    repo_path = Path(repo_dir)
    issues = _load_jsonl(repo_path / "issues.jsonl")
    comments = _load_jsonl(repo_path / "comments.jsonl")

    now = datetime.now(timezone.utc)

    # Group comments by issue_number
    comments_by_issue: Dict[int, List[Dict]] = {}
    for c in comments:
        comments_by_issue.setdefault(c["issue_number"], []).append(c)

    # --- Metric accumulators ---
    response_times_days: List[float] = []
    close_times_days: List[float] = []
    open_issue_ages_days: List[float] = []

    unanswered_30d = 0
    eligible_unanswered = 0

    for issue in issues:
        issue_number = issue["issue_number"]
        created_at = _parse_ts(issue.get("created_at"))
        closed_at = _parse_ts(issue.get("closed_at"))
        state = issue.get("state")

        if not created_at:
            continue

        issue_comments = comments_by_issue.get(issue_number, [])

        # ---- time to first maintainer response ----
        maintainer_comments = [
            c for c in issue_comments
            if c.get("is_maintainer") and not c.get("author_is_bot")
        ]

        if maintainer_comments:
            first = min(
                maintainer_comments,
                key=lambda c: _parse_ts(c["created_at"])
            )
            first_ts = _parse_ts(first["created_at"])
            if first_ts:
                delta_days = (first_ts - created_at).total_seconds() / 86400
                if delta_days >= 0:
                    response_times_days.append(delta_days)

        # ---- close time ----
        if closed_at:
            delta_days = (closed_at - created_at).total_seconds() / 86400
            if delta_days >= 0:
                close_times_days.append(delta_days)

        # ---- open issue age ----
        if state == "open":
            age_days = (now - created_at).total_seconds() / 86400
            if age_days >= 0:
                open_issue_ages_days.append(age_days)

            # unanswered logic
            age_30d = age_days >= 30
            if age_30d:
                eligible_unanswered += 1
                if not maintainer_comments:
                    unanswered_30d += 1

    metrics: Dict[str, float] = {}

    if response_times_days:
        metrics["avg_time_to_first_maintainer_response_days"] = (
            sum(response_times_days) / len(response_times_days)
        )

    if eligible_unanswered > 0:
        metrics["fraction_unanswered_30d"] = (
            unanswered_30d / eligible_unanswered
        )

    if close_times_days:
        metrics["median_time_to_close_days"] = median(close_times_days)

    if open_issue_ages_days:
        open_issue_ages_days.sort()
        p90_idx = int(0.9 * (len(open_issue_ages_days) - 1))
        metrics["open_issue_age_p90_days"] = open_issue_ages_days[p90_idx]

    return metrics
