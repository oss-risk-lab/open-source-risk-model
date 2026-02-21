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
    contributors_count: Optional[int]
    open_issues_count: int
    issues_per_contributor: Optional[float]
    fraction_issues_closed_12mo: Optional[float]
    fraction_open_issues_stale_180d: Optional[float]
    contributors_last_12mo: int
    top_contributor_fraction_12mo: Optional[float]
    archived: bool
    license_spdx_id: Optional[str]
    # --- meta for missing-data handling ---
    has_issues: bool = True
    feature_status: Dict[str, str] = None  # type: ignore


    def as_raw_dict(self) -> Dict[str, Any]:
        """
        Shape expected by compute_composite_risk.
        Adds __meta__ for missing-data handling.
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
            "__meta__": {
                # filled in by fetch_repo_features()
                "has_issues": getattr(self, "has_issues", True),
                "feature_status": getattr(self, "feature_status", {}),
            },
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


def _days_since_last_release(full_name: str, session: requests.Session) -> tuple[Optional[float], str]:
    """
    Returns (days_since_release, status)

    status:
      - "ok"
      - "not_applicable"        (no releases exist)
      - "forbidden"      (403 not rate limit exhausted)
      - "rate_limited"   (403 with remaining=0 or 429)
      - "error"          (other failures)
    """
    url = f"{GITHUB_API_URL}/repos/{full_name}/releases/latest"
    try:
        resp = session.get(url, timeout=20)
    except requests.exceptions.RequestException:
        return None, "error"

    if resp.status_code == 404:
        # Repo has no GitHub Releases (common for linux, some others)
        return None, "not_applicable"

    if resp.status_code == 429 or (
        resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0"
    ):
        return None, "rate_limited"

    if resp.status_code == 403:
        return None, "forbidden"

    if resp.status_code >= 400:
        return None, "error"

    release = resp.json() or {}
    ts = release.get("published_at") or release.get("created_at")
    if not ts:
        return None, "error"

    released_at = _parse_iso8601(ts)
    return _days_since(released_at), "ok"

def _count_contributors(full_name: str, session: requests.Session) -> tuple[Optional[int], str]:
    """
    Returns (contributors_count, status)

    status:
      - "ok"
      - "forbidden"     (contributors list disabled or no access)
      - "rate_limited"  (rate limit exhausted)
      - "not_found"     (404)
      - "error"         (other failures)

    Implementation notes:
    - Uses per_page=1 and parses Link rel="last" page number to get an exact count
      in a single request (avoids paging through huge repos like torvalds/linux).
    - Falls back to len(first_page) when Link header is absent.
    """
    import time
    from urllib.parse import urlparse, parse_qs

    url = f"{GITHUB_API_URL}/repos/{full_name}/contributors"
    params = {"per_page": 1, "anon": "true"}  # per_page=1 => last page number == exact count

    max_attempts = 5
    base_sleep = 1.0

    def _is_rate_limited(resp: requests.Response) -> bool:
        return (
            resp.status_code == 429
            or (resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0")
        )

    def _sleep_backoff(resp: requests.Response, attempt: int) -> None:
        # Prefer GitHub reset header, otherwise exponential backoff.
        reset = resp.headers.get("X-RateLimit-Reset")
        if reset and reset.isdigit():
            wait = max(0, int(reset) - int(time.time())) + 1
            time.sleep(min(wait, 30))  # clamp so CLI doesn't hang forever
        else:
            time.sleep(base_sleep * (2 ** (attempt - 1)))

    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.get(url, params=params, timeout=20)
        except requests.exceptions.RequestException:
            time.sleep(base_sleep * (2 ** (attempt - 1)))
            continue

        if _is_rate_limited(resp):
            return None, "rate_limited"

        if resp.status_code == 404:
            return None, "not_found"

        if resp.status_code == 403:
            return None, "forbidden"

        if resp.status_code >= 400:
            if attempt < max_attempts:
                _sleep_backoff(resp, attempt)
                continue
            return None, "error"

        # 200 OK
        try:
            users = resp.json() or []
        except Exception:
            return None, "error"

        link = resp.headers.get("Link", "") or ""
        last_url = None
        for part in link.split(","):
            if 'rel="last"' in part:
                last_url = part[part.find("<") + 1 : part.find(">")]
                break

        if last_url:
            try:
                qs = parse_qs(urlparse(last_url).query)
                page = qs.get("page", [None])[0]
                if page is not None:
                    return int(page), "ok"
            except Exception:
                pass

        # No pagination => 0 or 1 contributors
        return int(len(users)), "ok"

    return None, "error"

def _search_issues_total_count(query: str, session: requests.Session) -> tuple[Optional[int], str]:
    """
    Returns (total_count, status)

    status:
      - "ok"
      - "disabled"      (not used here, but kept for symmetry)
      - "rejected"      (422)
      - "rate_limited"  (429 or rate limit exhausted)
      - "forbidden"     (403 other)
      - "error"         (network / other 4xx/5xx after retries)
    """
    import time

    url = f"{GITHUB_API_URL}/search/issues"
    params = {"q": query, "per_page": 1}

    max_attempts = 5
    base_sleep = 1.0

    last_status = "error"

    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.get(url, params=params, timeout=20)
        except requests.exceptions.RequestException:
            last_status = "error"
            time.sleep(base_sleep * (2 ** (attempt - 1)))
            continue

        if resp.status_code == 422:
            return None, "rejected"

        if resp.status_code in (502, 503, 504):
            last_status = "error"
            time.sleep(base_sleep * (2 ** (attempt - 1)))
            continue

        if resp.status_code == 429 or (
            resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0"
        ):
            last_status = "rate_limited"
            time.sleep(base_sleep * (2 ** (attempt - 1)))
            continue

        if resp.status_code == 403:
            return None, "forbidden"

        if resp.status_code >= 400:
            return None, "error"

        data = resp.json() or {}
        total = data.get("total_count")
        if isinstance(total, int):
            return total, "ok"

        return None, "error"

    return None, last_status


def _fraction_issues_closed_12mo(full_name: str, session: requests.Session) -> tuple[Optional[float], str]:
    """
    fraction = (# issues created in last 12mo AND closed) / (# issues created in last 12mo)
    Returns (fraction, status).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()

    opened_q = f"repo:{full_name} is:issue created:>{since}"
    closed_q = f"repo:{full_name} is:issue created:>{since} is:closed"

    opened, st_opened = _search_issues_total_count(opened_q, session)
    if opened is None:
        return None, st_opened
    if opened == 0:
        return None, "not_applicable"

    closed, st_closed = _search_issues_total_count(closed_q, session)
    if closed is None:
        return None, st_closed

    frac = closed / opened
    return max(0.0, min(1.0, frac)), "ok"

def _fraction_open_issues_stale_180d(
    full_name: str,
    session: requests.Session,
) -> tuple[Optional[float], str]:
    """
    fraction = (# open issues created before cutoff) / (# open issues total)
    Returns (fraction, status).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).date().isoformat()

    open_total_q = f"repo:{full_name} is:issue is:open"
    open_stale_q = f"repo:{full_name} is:issue is:open created:<{cutoff}"

    open_total, st_total = _search_issues_total_count(open_total_q, session)
    if open_total is None:
        return None, st_total
    if open_total == 0:
        return None, "not_applicable"

    open_stale, st_stale = _search_issues_total_count(open_stale_q, session)
    if open_stale is None:
        return None, st_stale

    frac = open_stale / open_total
    return max(0.0, min(1.0, frac)), "ok"


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
    has_issues = bool(repo.get("has_issues", True))
    feature_status: Dict[str, str] = {}

    pushed_at = _parse_iso8601(repo["pushed_at"])
    days_since_last_push = _days_since(pushed_at)

    days_since_last_release, st_release = _days_since_last_release(full_name, session)
    feature_status["days_since_last_release"] = st_release

    stargazers_count = int(repo["stargazers_count"])
    open_issues_count = int(repo["open_issues_count"])

    if not has_issues:
        fraction_issues_closed_12mo, st1 = None, "not_applicable"
        fraction_open_issues_stale_180d, st2 = None, "not_applicable"
    else:
        fraction_issues_closed_12mo, st1 = _fraction_issues_closed_12mo(full_name, session)
        fraction_open_issues_stale_180d, st2 = _fraction_open_issues_stale_180d(full_name, session)

    feature_status["fraction_issues_closed_12mo"] = st1
    feature_status["fraction_open_issues_stale_180d"] = st2

    
    contributors_last_12mo = _contributors_last_12mo(full_name, session)
    top_contributor_fraction_12mo = _top_contributor_fraction_12mo(full_name, session)
    archived = bool(repo["archived"])

    license_obj = repo.get("license") or {}
    license_spdx_id = license_obj.get("spdx_id")

    contributors_count, st_contrib = _count_contributors(full_name, session)
    feature_status["contributors_count"] = st_contrib
    if contributors_count is None:
        print(f"NOTE {full_name}: contributors_count unavailable (status={st_contrib})")

    if contributors_count is None or contributors_count == 0:
        issues_per_contributor = None
        feature_status["issues_per_contributor"] = "not_applicable"
    else:
        issues_per_contributor = open_issues_count / float(contributors_count)
        feature_status["issues_per_contributor"] = "ok"

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
        has_issues=has_issues,
        feature_status=feature_status,
    )
