import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests

from open_source_risk_model.issues.normalize import normalize_issue, normalize_comment
from open_source_risk_model.storage.issues_store import IssueStore

GITHUB_API_URL = "https://api.github.com"


def _github_session() -> requests.Session:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set in environment.")
    s = requests.Session()
    s.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "open-source-risk-model",
    })
    return s


def fetch_issues_updated_since(
    full_name: str,
    store: IssueStore,
    days_back: int = 365,
    per_page: int = 100,
    max_pages: int = 25,
) -> Dict[str, Any]:
    """
    Fetch issues updated within the last `days_back` days and store
    normalized issues + comments using IssueStore.

    MVP behavior:
      - REST /repos/{owner}/{repo}/issues
      - sorted by updated desc
      - stops paging once updated_at is older than cutoff
      - skips PRs (normalize_issue returns {})

    Notes:
      - This is not a perfect incremental sync yet (we're append-only).
      - That's OK for MVP; we'll add de-dupe/compaction later.
    """
    session = _github_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    owner, repo = full_name.split("/")
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues"

    issues_written = 0
    comments_written = 0
    pages_fetched = 0

    for page in range(1, max_pages + 1):
        params = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": per_page,
            "page": page,
        }

        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        raw_issues: List[Dict[str, Any]] = resp.json() or []
        if not raw_issues:
            break

        pages_fetched += 1

        norm_issues_batch: List[Dict[str, Any]] = []
        stop_paging = False

        for raw in raw_issues:
            updated_at = raw.get("updated_at")
            if updated_at:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if dt < cutoff:
                    stop_paging = True
                    break

            norm = normalize_issue(full_name, raw)
            if not norm:
                continue  # PRs or invalid payloads

            norm_issues_batch.append(norm)

            # Fetch comments only if any exist
            if (raw.get("comments") or 0) > 0:
                comments_url = norm.get("comments_url")
                issue_number = norm.get("issue_number")
                if comments_url and issue_number:
                    c_resp = session.get(comments_url, timeout=30)
                    c_resp.raise_for_status()
                    raw_comments: List[Dict[str, Any]] = c_resp.json() or []
                    norm_comments = [
                        normalize_comment(full_name, int(issue_number), c)
                        for c in raw_comments
                    ]
                    store.append_comments(full_name, norm_comments)
                    comments_written += len(norm_comments)

        if norm_issues_batch:
            store.append_issues(full_name, norm_issues_batch)
            issues_written += len(norm_issues_batch)

        if stop_paging:
            break

    manifest = store.load_manifest(full_name)
    manifest.update({
        "last_fetch_utc": datetime.now(timezone.utc).isoformat(),
        "days_back": days_back,
        "per_page": per_page,
        "max_pages": max_pages,
        "pages_fetched_last_run": pages_fetched,
        "issues_written_last_run": issues_written,
        "comments_written_last_run": comments_written,
    })
    store.save_manifest(full_name, manifest)
    return manifest
