from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional


WINDOW_DAYS_DEFAULT = 365


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    # Normalize to timezone-aware UTC to avoid naive/aware subtraction issues
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _p90(values: List[float]) -> float:
    values = sorted(values)
    n = len(values)
    if n == 0:
        raise ValueError("p90 called on empty list")

    x = 0.9 * n
    ceil_x = int(x) if x == int(x) else int(x) + 1
    idx = max(0, min(n - 1, ceil_x - 1))
    return values[idx]

# Option A: all metrics use ONLY issues created within the last WINDOW_DAYS.
# This makes metrics represent "recent" issue health rather than lifetime backlog.
def compute_issue_metrics(
    repo_dir: str,
    *,
    window_days: int = WINDOW_DAYS_DEFAULT,
    now: Optional[datetime] = None,
    include_debug: bool = False,
) -> Dict[str, float]:
    """
    Option A: compute issue lifecycle metrics using ONLY issues created within
    the recent window [now - window_days, now].
    """
    repo_path = Path(repo_dir)
    issues = _load_jsonl(repo_path / "issues.jsonl")
    comments = _load_jsonl(repo_path / "comments.jsonl")

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    cutoff = now - timedelta(days=window_days)

    # Group comments by issue_number
    comments_by_issue: Dict[int, List[Dict[str, Any]]] = {}
    for c in comments:
        num = c.get("issue_number")
        if isinstance(num, int):
            comments_by_issue.setdefault(num, []).append(c)

    # --- Metric accumulators ---
    response_times_days: List[float] = []
    close_times_days: List[float] = []
    open_issue_ages_days: List[float] = []

    unanswered_30d = 0
    eligible_unanswered = 0

    for issue in issues:
        # Optional: skip PRs if they can appear in your issues dataset
        if issue.get("pull_request") is not None:
            continue

        issue_number = issue.get("issue_number")
        if not isinstance(issue_number, int):
            continue

        created_at = _parse_ts(issue.get("created_at"))
        if not created_at:
            continue

        # OPTION A: ignore issues created before cutoff
        if created_at < cutoff:
            continue

        closed_at = _parse_ts(issue.get("closed_at"))
        state = issue.get("state")

        issue_comments = comments_by_issue.get(issue_number, [])

        # ---- time to first maintainer response ----
        maintainer_comment_ts: List[datetime] = []
        for c in issue_comments:
            if not c.get("is_maintainer"):
                continue
            if c.get("author_is_bot"):
                continue
            ts = _parse_ts(c.get("created_at"))
            if ts:
                maintainer_comment_ts.append(ts)

        first_ts = min(maintainer_comment_ts) if maintainer_comment_ts else None
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

            # unanswered logic (only for issues >= 30d old inside the window)
            if age_days >= 30:
                eligible_unanswered += 1
                if not maintainer_comment_ts:
                    unanswered_30d += 1

    metrics: Dict[str, float] = {}

    if response_times_days:
        metrics["avg_time_to_first_maintainer_response_days"] = (
            sum(response_times_days) / len(response_times_days)
        )

    if eligible_unanswered > 0:
        metrics["fraction_unanswered_after_30d"] = unanswered_30d / eligible_unanswered

    if close_times_days:
        metrics["median_time_to_close_days"] = median(close_times_days)

    if open_issue_ages_days:
        raw_p90 = _p90(open_issue_ages_days)
        metrics["open_issue_age_p90_days"] = raw_p90

    return metrics
