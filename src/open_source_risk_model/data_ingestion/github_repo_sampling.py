# src/open_source_risk_model/data_ingestion/github_repo_sampling.py
# -----------------------------------------------------------------------------
# github_repo_sampling.py
#
# GitHub API data collection script.
# Queries public repository metadata, extracts attributes such as last push
# date, star count, size, etc., and computes derived numeric features including
# days_since_last_push.
#
# Writes JSON arrays to data/baseline/ containing raw numeric population values.
# These JSON files are later consumed by feature_mappings/option_c.py via the
# dispatcher.
#
# Run this occasionally to refresh baseline population snapshots.
# -----------------------------------------------------------------------------

import os
import datetime as dt
import random
from typing import List, Literal

import requests

DaysList = List[float]
Mode = Literal["active", "typical", "stale", "combined"]

# --- Base queries for different "types" of repos ---

# Recently updated, healthy repos ("what good looks like")
BASE_QUERY_ACTIVE = "stars:>100 fork:false pushed:>2025-01-01"

# Broad, normal OSS (mixture of fresh and somewhat stale)
BASE_QUERY_TYPICAL = "stars:>10 fork:false"

# Popular but dormant / stale repos (latent risk tail)
BASE_QUERY_STALE = "stars:>100 fork:false pushed:<2024-01-01"

# Search API constants
SEARCH_URL = "https://api.github.com/search/repositories"
PER_PAGE = 100
MAX_PAGES = 10  # we'll never request more than this in one call


def _get_session() -> requests.Session:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN env var is not set. "
            "Export it in your shell before using github_repo_sampling."
        )

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "open-source-risk-model-colin",
        }
    )
    return session


def _days_since(timestamp: str, *, now: dt.datetime) -> float:
    """
    Convert an ISO8601 timestamp (GitHub 'pushed_at') to days since that time.
    """
    pushed_dt = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    delta = now - pushed_dt
    return delta.total_seconds() / 86400.0


def _sample_days_since_last_push(
    base_query: str,
    *,
    n: int = 500,
    use_random_pages: bool = True,
    sort_updated: bool = False,
) -> DaysList:
    """
    Core sampling helper: hits the GitHub search API and returns a list of
    'days_since_last_push' values for repos matching base_query.
    """
    session = _get_session()
    now = dt.datetime.now(dt.timezone.utc)

    # Decide how many pages we *might* need
    num_pages_needed = max(1, min(MAX_PAGES, (n + PER_PAGE - 1) // PER_PAGE))

    if use_random_pages:
        # GitHub search caps at ~1000 results => 10 pages of 100 per_page.
        pages = sorted(random.sample(range(1, 11), num_pages_needed))
    else:
        pages = list(range(1, num_pages_needed + 1))

    days_values: DaysList = []

    for page in pages:
        params = {
            "q": base_query,
            "per_page": PER_PAGE,
            "page": page,
        }
        if sort_updated:
            params["sort"] = "updated"
            params["order"] = "desc"

        resp = session.get(SEARCH_URL, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] search page {page}: HTTP {resp.status_code} -> {resp.text[:200]}")
            continue

        data = resp.json()
        items = data.get("items", [])
        if not items:
            break

        for repo in items:
            pushed_at = repo.get("pushed_at")
            if not pushed_at:
                continue
            days = _days_since(pushed_at, now=now)
            days_values.append(days)

            if len(days_values) >= n:
                return days_values

    return days_values


# --- Public API: sampling functions for each type ---


def sample_active_days_since_last_push(n: int = 500) -> DaysList:
    """
    Sample 'active' repos: high stars, very recent pushes.
    """
    return _sample_days_since_last_push(
        BASE_QUERY_ACTIVE,
        n=n,
        use_random_pages=False,  # we want the freshest ones
        sort_updated=True,
    )


def sample_typical_days_since_last_push(n: int = 500) -> DaysList:
    """
    Sample 'typical' repos: broad mix of OSS, not restricted by recency.
    """
    return _sample_days_since_last_push(
        BASE_QUERY_TYPICAL,
        n=n,
        use_random_pages=True,
        sort_updated=False,
    )


def sample_stale_days_since_last_push(n: int = 500) -> DaysList:
    """
    Sample 'stale' repos: popular but not updated recently.
    """
    return _sample_days_since_last_push(
        BASE_QUERY_STALE,
        n=n,
        use_random_pages=True,
        sort_updated=False,
    )


def build_days_since_last_push_population(mode: Mode = "combined", n_each: int = 500) -> DaysList:
    """
    Build a population list of 'days_since_last_push' for use with Option C.

    mode:
      - 'active'   -> only active sample
      - 'typical'  -> only typical sample
      - 'stale'    -> only stale sample
      - 'combined' -> active + typical + stale
    """
    if mode not in ("active", "typical", "stale", "combined"):
        raise ValueError(f"Unknown mode: {mode}")

    if mode == "active":
        return sample_active_days_since_last_push(n_each)
    if mode == "typical":
        return sample_typical_days_since_last_push(n_each)
    if mode == "stale":
        return sample_stale_days_since_last_push(n_each)

    # combined
    active = sample_active_days_since_last_push(n_each)
    typical = sample_typical_days_since_last_push(n_each)
    stale = sample_stale_days_since_last_push(n_each)

    return active + typical + stale

