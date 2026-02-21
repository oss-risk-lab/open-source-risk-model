import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from open_source_risk_model.issues.normalize import normalize_issue, normalize_comment
from open_source_risk_model.storage.issues_store import IssueStore

GITHUB_API_URL = "https://api.github.com"


# ---------------------------
# Errors / status
# ---------------------------

@dataclass(frozen=True)
class GitHubRequestError(Exception):
    status_code: int
    message: str
    url: str
    remaining: Optional[int] = None
    reset_epoch: Optional[int] = None

    def as_meta(self) -> Dict[str, Any]:
        return {
            "status_code": self.status_code,
            "message": self.message,
            "url": self.url,
            "remaining": self.remaining,
            "reset_epoch": self.reset_epoch,
        }


def _github_session() -> requests.Session:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set in environment.")
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "open-source-risk-model",
        }
    )
    return s


def _request_json(
    session: requests.Session,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Request a GitHub endpoint and return JSON list payloads with sane error metadata."""
    resp = session.get(url, params=params, timeout=timeout)

    if resp.status_code >= 400:
        remaining = resp.headers.get("X-RateLimit-Remaining")
        reset = resp.headers.get("X-RateLimit-Reset")
        try:
            remaining_i = int(remaining) if remaining is not None else None
        except Exception:
            remaining_i = None
        try:
            reset_i = int(reset) if reset is not None else None
        except Exception:
            reset_i = None

        # GitHub rate limiting commonly shows up as 403 with remaining=0
        msg = ""
        try:
            payload = resp.json()
            msg = payload.get("message") or ""
        except Exception:
            msg = resp.text or ""

        raise GitHubRequestError(
            status_code=resp.status_code,
            message=msg,
            url=url,
            remaining=remaining_i,
            reset_epoch=reset_i,
        )

    data = resp.json()
    return data or []


def _paginate_json_list(
    session: requests.Session,
    url: str,
    *,
    per_page: int = 100,
    max_pages: int = 50,
    base_params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    params = dict(base_params or {})
    params["per_page"] = per_page

    for page in range(1, max_pages + 1):
        params["page"] = page
        chunk = _request_json(session, url, params=params)
        if not chunk:
            break
        out.extend(chunk)
        # defensive stop: if GitHub returns fewer than per_page, last page
        if len(chunk) < per_page:
            break

    return out


def fetch_issues_updated_since(
    full_name: str,
    store: IssueStore,
    days_back: int = 365,
    per_page: int = 100,
    max_pages: int = 25,
    *,
    compact_after: bool = True,
) -> Dict[str, Any]:
    """
    Fetch issues updated within the last `days_back` days and store
    normalized issues + comments using IssueStore.

    Behavior:
      - REST /repos/{owner}/{repo}/issues
      - sorted by updated desc
      - stops paging once updated_at is older than cutoff
      - skips PRs (normalize_issue returns {})

    Improvements:
      - comment pagination (per_page=100)
      - structured error metadata (rate limiting, auth, etc.)
      - optional de-dupe compaction after sync
    """
    session = _github_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    owner, repo = full_name.split("/")
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues"

    issues_written = 0
    comments_written = 0
    pages_fetched = 0
    errors: List[Dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        params = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": per_page,
            "page": page,
        }

        try:
            raw_issues: List[Dict[str, Any]] = _request_json(session, url, params=params, timeout=30)
        except GitHubRequestError as e:
            errors.append(e.as_meta())
            break

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

            # Fetch comments only if any exist (PAGINATE)
            if (raw.get("comments") or 0) > 0:
                comments_url = norm.get("comments_url")
                issue_number = norm.get("issue_number")
                if comments_url and issue_number:
                    try:
                        raw_comments: List[Dict[str, Any]] = _paginate_json_list(
                            session,
                            comments_url,
                            per_page=100,
                            max_pages=50,
                            base_params=None,
                        )
                    except GitHubRequestError as e:
                        errors.append(e.as_meta())
                        continue

                    norm_comments = [
                        normalize_comment(full_name, int(issue_number), c) for c in raw_comments
                    ]
                    store.append_comments(full_name, norm_comments)
                    comments_written += len(norm_comments)

        if norm_issues_batch:
            store.append_issues(full_name, norm_issues_batch)
            issues_written += len(norm_issues_batch)

        if stop_paging:
            break

    compact_stats: Dict[str, Any] = {}
    if compact_after:
        try:
            compact_stats = store.compact_repo(full_name)
        except Exception as e:
            compact_stats = {"error": str(e)}

    manifest = store.load_manifest(full_name)
    manifest.update(
        {
            "last_fetch_utc": datetime.now(timezone.utc).isoformat(),
            "days_back": days_back,
            "per_page": per_page,
            "max_pages": max_pages,
            "pages_fetched_last_run": pages_fetched,
            "truncated": (pages_fetched >= max_pages),
            "issues_written_last_run": issues_written,
            "comments_written_last_run": comments_written,
            "compact_stats": compact_stats,
            "errors": errors,
            "status": ("ok" if not errors else "partial"),
        }
    )
    store.save_manifest(full_name, manifest)
    return manifest
