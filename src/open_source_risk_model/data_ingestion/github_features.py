# src/open_source_risk_model/data_ingestion/github_features.py

import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import requests
from collections import Counter

GITHUB_API_URL = "https://api.github.com"


@dataclass
class RepoFeatures:
    days_since_last_push: float
    days_since_last_release: Optional[float]
    stargazers_count: int
    contributors_count: int
    open_issues_count: int
    issues_per_contributor: float
    fraction_issues_closed_12mo: Optional[float]
    fraction_open_issues_stale_180d: Optional[float]
    contributors_last_12mo: int
    top_contributor_fraction_12mo: Optional[float]
    archived: bool
    license_spdx_id: Optional[str]

    def as_raw_dict(self) -> Dict[str, Any]:
        """
        Shape expected by compute_composite_risk.
        """
        return {
            "days_since_last_push": self.days_since_last_push,
            "days_since_last_release": self.days_since_last_release,
            "stargazers_count": self.stargazers_count,
            "contributors_count": self.contributors_count,
            "open_issues_count": self.open_issues_count,
            "issues_per_contributor": self.issues_per_contributor,
            "fraction_issues_closed_12mo": self.fraction_issues_closed_12mo,
            "fraction_open_issues_stale_180d": self.fraction_open_issues_stale_180d,
            "contributors_last_12mo": self.contributors_last_12mo,
            "top_contributor_fraction_12mo": self.top_contributor_fraction_12mo,
            "archived": self.archived,
            "license_spdx_id": self.license_spdx_id,
        }


def _github_session() -> requests.Session:
    token = os.environ.get("GITHUB_TOKEN")
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    return session


def _parse_iso8601(s: str) -> datetime:
    # GitHub timestamps are like "2025-01-01T12:34:56Z"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _days_since(dt: datetime) -> float:
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 86400.0


def _days_since_last_release(full_name: str, session: requests.Session) -> Optional[float]:
    """
    Returns days since the latest published GitHub release.
    If the repository has no releases, returns None.
    """
    url = f"{GITHUB_API_URL}/repos/{full_name}/releases/latest"
    resp = session.get(url)

    if resp.status_code == 404:
        return None  # no releases exist

    resp.raise_for_status()
    release = resp.json()

    ts = release.get("published_at") or release.get("created_at")
    if not ts:
        return None

    released_at = _parse_iso8601(ts)
    return _days_since(released_at)


def _count_contributors(full_name: str, session: requests.Session) -> int:
    """
    Count contributors by paging through /contributors.

    Some huge repos (like torvalds/linux) have this endpoint disabled and return 403.
    In that case, fall back to a safe default so the pipeline can continue.
    """
    url = f"{GITHUB_API_URL}/repos/{full_name}/contributors"
    params = {"per_page": 100, "anon": "true"}
    total = 0

    while url:
        resp = session.get(url, params=params)

        # Handle special cases explicitly
        if resp.status_code == 403:
            # Could be rate limiting or "contributors list is disabled for this repo"
            print(f"Warning: contributors API forbidden for {full_name}, "
                  f"falling back to default contributors_count=100")
            return 100

        if resp.status_code == 404:
            print(f"Warning: contributors API not found for {full_name}, "
                  f"falling back to default contributors_count=1")
            return 1

        resp.raise_for_status()
        users = resp.json()
        total += len(users)

        link = resp.headers.get("Link", "")
        next_url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part[part.find("<") + 1 : part.find(">")]
                break
        url = next_url
        params = None  # only for the first page

    # Fallback: never let this be zero, to avoid divide-by-zero downstream
    return total or 1

def _search_issues_total_count(query: str, session: requests.Session) -> Optional[int]:
    """
    Uses GitHub Search Issues API and returns total_count.
    Returns None if GitHub rejects the query (422) or other non-success cases
    where we cannot trust the count.
    """
    url = f"{GITHUB_API_URL}/search/issues"
    resp = session.get(url, params={"q": query, "per_page": 1})

    if resp.status_code == 422:
        print(f"Warning: GitHub search rejected query (422): {query}")
        return None

    resp.raise_for_status()
    data = resp.json()
    return int(data.get("total_count", 0))


def _fraction_issues_closed_12mo(full_name: str, session: requests.Session) -> Optional[float]:
    """
    fraction = (# issues created in last 12mo AND closed) / (# issues created in last 12mo)
    Returns None if denominator is 0 or if search queries fail (422 -> None).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()

    opened_q = f"repo:{full_name} is:issue created:>{since}"
    closed_q = f"repo:{full_name} is:issue created:>{since} is:closed"

    opened = _search_issues_total_count(opened_q, session)
    if opened is None or opened == 0:
        return None

    closed = _search_issues_total_count(closed_q, session)
    if closed is None:
        return None

    frac = closed / opened
    return max(0.0, min(1.0, frac))

def _fraction_open_issues_stale_180d(
    full_name: str,
    session: requests.Session,
) -> Optional[float]:
    """
    fraction = (# open issues created before cutoff) / (# open issues total)

    Returns:
      - float in [0, 1] if queries succeed
      - None if GitHub search rejects queries (422) or denominator is 0
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).date().isoformat()

    open_total_q = f"repo:{full_name} is:issue is:open"
    open_stale_q = f"repo:{full_name} is:issue is:open created:<{cutoff}"

    open_total = _search_issues_total_count(open_total_q, session)
    if open_total is None or open_total == 0:
        return None

    open_stale = _search_issues_total_count(open_stale_q, session)
    if open_stale is None:
        return None

    frac = open_stale / open_total
    return max(0.0, min(1.0, frac))


def _contributors_last_12mo(full_name: str, session: requests.Session, max_pages: int = 2) -> int:
    """
    Approx count of unique commit authors in the last 12 months.
    Scans up to `max_pages` pages of commits (100 per page).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()

    seen = set()
    url = f"{GITHUB_API_URL}/repos/{full_name}/commits"
    params = {"since": since, "per_page": 100, "page": 1}

    for page in range(1, max_pages + 1):
        params["page"] = page
        resp = session.get(url, params=params)

        if resp.status_code == 409:
            # empty repo
            return 0

        resp.raise_for_status()
        commits = resp.json()
        if not commits:
            break

        for c in commits:
            author = c.get("author") or {}
            login = author.get("login")
            if login:
                seen.add(login)
            else:
                # fallback to commit author identity
                commit_author = ((c.get("commit") or {}).get("author") or {})
                key = commit_author.get("email") or commit_author.get("name")
                if key:
                    seen.add(str(key))

        if len(commits) < 100:
            break

    return len(seen)

def _top_contributor_fraction_12mo(
    full_name: str,
    session: requests.Session,
    *,
    max_pages: int = 2,   # 2 pages * 100 commits/page = up to 200 sampled commits
) -> Optional[float]:
    """
    Bus factor proxy: fraction of commits in the last ~12 months attributable to the top contributor.

    Primary: GitHub Stats API /stats/contributors (best signal).
    Fallback: sample commits from /commits?since=... and compute dominance from the sample.

    Returns:
      - float in [0, 1] if available
      - None if no usable data
    """
    # -------------------------
    # 1) Primary: stats endpoint
    # -------------------------
    stats_url = f"{GITHUB_API_URL}/repos/{full_name}/stats/contributors"
    resp = session.get(stats_url)

    if resp.status_code == 200:
        data = resp.json() or []
        totals = []
        for c in data:
            weeks = c.get("weeks") or []
            commits_last_52 = sum(int(w.get("c", 0)) for w in weeks[-52:])
            if commits_last_52 > 0:
                totals.append(commits_last_52)

        if totals:
            top = max(totals)
            total = sum(totals)
            if total > 0:
                frac = top / total
                return max(0.0, min(1.0, frac))

        # If stats returns 200 but empty/unhelpful, fall through to fallback

    elif resp.status_code in (202, 403, 404):
        # 202 = computing, 403/404 = unavailable; use fallback
        pass
    else:
        # Unexpected error: still try fallback rather than hard failing
        pass

    # ------------------------------------------
    # 2) Fallback: sample commits since 12 months
    # ------------------------------------------
    since = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    commits_url = f"{GITHUB_API_URL}/repos/{full_name}/commits"

    counts: Counter[str] = Counter()
    total_sampled = 0

    params = {"since": since, "per_page": 100, "page": 1}

    for page in range(1, max_pages + 1):
        params["page"] = page
        r = session.get(commits_url, params=params)

        if r.status_code == 409:
            # empty repo
            return None

        # If commits endpoint is forbidden or not found, we can't compute fallback
        if r.status_code in (403, 404):
            return None

        r.raise_for_status()
        commits = r.json() or []
        if not commits:
            break

        for c in commits:
            # Prefer GitHub login if present
            author = (c.get("author") or {})
            login = author.get("login")
            if login:
                key = f"login:{login}"
            else:
                # Fall back to commit identity
                commit_author = ((c.get("commit") or {}).get("author") or {})
                email = commit_author.get("email")
                name = commit_author.get("name")
                key = f"id:{email or name or 'unknown'}"

            counts[key] += 1
            total_sampled += 1

        if len(commits) < 100:
            break

    if total_sampled <= 0 or not counts:
        return None

    top = max(counts.values())
    frac = top / float(total_sampled)
    return max(0.0, min(1.0, frac))


def fetch_repo_features(full_name: str, session: Optional[requests.Session] = None) -> RepoFeatures:
    """
    Fetch GitHub metadata for owner/repo and compute all current features.
    """
    if session is None:
        session = _github_session()

    repo_resp = session.get(f"{GITHUB_API_URL}/repos/{full_name}")
    repo_resp.raise_for_status()
    repo = repo_resp.json()

    pushed_at = _parse_iso8601(repo["pushed_at"])
    days_since_last_push = _days_since(pushed_at)

    days_since_last_release = _days_since_last_release(full_name, session)

    stargazers_count = int(repo["stargazers_count"])
    open_issues_count = int(repo["open_issues_count"])
    fraction_issues_closed_12mo = _fraction_issues_closed_12mo(full_name, session)
    fraction_open_issues_stale_180d = _fraction_open_issues_stale_180d(full_name, session)
    contributors_last_12mo = _contributors_last_12mo(full_name, session)
    top_contributor_fraction_12mo = _top_contributor_fraction_12mo(full_name, session)
    archived = bool(repo["archived"])

    license_obj = repo.get("license") or {}
    license_spdx_id = license_obj.get("spdx_id")

    contributors_count = _count_contributors(full_name, session)
    if contributors_count <= 0:
        contributors_count = 1  # avoid divide by zero

    issues_per_contributor = open_issues_count / float(contributors_count)

    return RepoFeatures(
        days_since_last_push=days_since_last_push,
        days_since_last_release=days_since_last_release,
        stargazers_count=stargazers_count,
        contributors_count=contributors_count,
        open_issues_count=open_issues_count,
        issues_per_contributor=issues_per_contributor,
        fraction_issues_closed_12mo=fraction_issues_closed_12mo,
        fraction_open_issues_stale_180d=fraction_open_issues_stale_180d,
        contributors_last_12mo=contributors_last_12mo,
        top_contributor_fraction_12mo=top_contributor_fraction_12mo,
        archived=archived,
        license_spdx_id=license_spdx_id,
    )
