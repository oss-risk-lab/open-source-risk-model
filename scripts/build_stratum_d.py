"""
Sample fragility-tail repos from package_mappings for Stratum D.

Queries GitHub GraphQL for every package_mappings repo not already in the universe,
filters to repos that are stale (no push in >= MIN_STALE_DAYS), alive (not archived,
not missing), and appends them as a dated Stratum D block to universe_v1.txt.

The script is designed to be re-run: repos already in the universe are excluded from
each run. Each run produces one dated block. The snapshot collector handles duplicates
across blocks automatically (load_universe returns a flat list; GraphQL aliases
deduplicate on their own).

Usage:
    GITHUB_TOKEN=<pat> python scripts/build_stratum_d.py \\
        --universe data/universe/universe_v1.txt \\
        --db data/graphs.db \\
        [--min-stale-days 180] \\
        [--min-confidence 0.90] \\
        [--cap 300] \\
        [--dry-run]
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GRAPHQL_URL = "https://api.github.com/graphql"
GRAPHQL_BATCH_SIZE = 70
DEFAULT_MIN_STALE_DAYS = 180
DEFAULT_MIN_CONFIDENCE = 0.90
DEFAULT_CAP = 300
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2, 4, 8)  # seconds between retry attempts
_INTER_BATCH_SLEEP = 0.8    # seconds between successful batches (avoids secondary rate limits)


def _valid_repo(repo: str) -> bool:
    return bool(REPO_RE.match(repo))


def load_universe(path: Path) -> set[str]:
    """Read universe file; return all non-comment, non-blank lines as a set."""
    repos: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                repos.add(line)
    return repos


def load_candidates(db_path: Path, exclude: set[str], min_confidence: float) -> list[str]:
    """Return distinct repos from package_mappings not in exclude, sorted case-insensitively."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT repo_full_name FROM package_mappings "
            "WHERE confidence >= ? AND repo_full_name IS NOT NULL AND repo_full_name != ''",
            (min_confidence,),
        )
        return sorted(
            {r for (r,) in cur.fetchall() if _valid_repo(r) and r not in exclude},
            key=str.casefold,
        )
    finally:
        conn.close()


def build_batch_query(repos: list[str]) -> tuple[str, dict[int, str]]:
    """Build a batched GraphQL query. Returns (query_string, index_to_repo mapping)."""
    index_to_repo: dict[int, str] = {}
    parts = ["query {"]
    for idx, repo in enumerate(repos):
        owner, name = repo.split("/", 1)
        alias = f"repo_{idx}"
        index_to_repo[idx] = repo
        parts.append(
            f'  {alias}: repository(owner: "{owner}", name: "{name}") {{\n'
            "    pushedAt isArchived stargazerCount\n"
            "    releases(first: 1) { totalCount }\n"
            "  }"
        )
    parts.append("}")
    return "\n".join(parts), index_to_repo


def days_since(iso_str: Optional[str], now: datetime) -> Optional[float]:
    """Return days between an ISO 8601 timestamp and now, or None if unparseable."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (now - dt).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return None


def fragility_score(days_since_push: float, releases_total: int, stars: int) -> float:
    """Compute a sortable fragility score — higher means more fragile.

    Primary signal: days since last push (raw staleness).
    Bonuses:
      +90  if releases_total == 0  (project never cut a formal release)
      +30  if stars < 50           (very small project, low community rescue probability)
    """
    score = days_since_push
    if releases_total == 0:
        score += 90.0
    if stars < 50:
        score += 30.0
    return score


def _graphql_post(
    token: str, query: str, session: Optional[requests.Session] = None
) -> dict[str, Any]:
    """POST a GraphQL query and return the raw response body.

    Unlike GraphQLClient.execute_query(), this function does NOT raise on
    GraphQL-level errors. GitHub returns ``{"data": {...}, "errors": [...]}``
    when some aliases in a batch resolve to non-existent repos. We log the
    errors and proceed with the partial ``data`` dict so one dead repo in a
    batch of 70 does not discard 69 valid results.

    Raises on HTTP-level failures (non-200 status, network errors) after
    _MAX_RETRIES attempts with exponential backoff.
    """
    sess = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = json.dumps({"query": query}).encode()

    last_exc: Exception | None = None
    for attempt, backoff in enumerate((_RETRY_BACKOFF + (0,))[:_MAX_RETRIES], 1):
        try:
            resp = sess.post(GRAPHQL_URL, data=payload, headers=headers, timeout=30)
            if resp.status_code in (403, 429, 503):
                # 403 = secondary rate limit, 429/503 = primary or gateway
                retry_after = int(resp.headers.get("Retry-After", backoff or 60))
                wait = max(retry_after, backoff or 60)
                logger.warning("HTTP %d on attempt %d/%d; sleeping %ds", resp.status_code, attempt, _MAX_RETRIES, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            if "errors" in body:
                msgs = "; ".join(e.get("message", "?") for e in body["errors"][:3])
                logger.debug("GraphQL partial errors (data still used): %s", msgs)
            return body
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES and backoff:
                logger.warning("Attempt %d/%d failed (%s); retrying in %ds", attempt, _MAX_RETRIES, exc, backoff)
                time.sleep(backoff)

    raise RuntimeError(f"Batch failed after {_MAX_RETRIES} attempts") from last_exc


def screen_candidates(
    token_or_client: Any,
    candidates: list[str],
    min_stale_days: int,
    cap: int,
    _session: Optional[requests.Session] = None,
    _now: Optional[datetime] = None,
) -> list[tuple[str, float]]:
    """
    Batch-query GitHub GraphQL for all candidates and return qualifying repos.

    ``token_or_client`` accepts either a raw token string (production path) or a
    mock object with an ``execute_query`` method (test path). When a mock is
    detected, its ``execute_query`` return value is used directly as the response
    body so tests remain fast and network-free.

    Returns list of (repo_full_name, fragility_score) sorted by score DESC,
    then by repo name for determinism, capped at cap.

    Filtering:
      - Repo must exist (not null in GraphQL response — i.e., not deleted/private).
      - Repo must not be archived.
      - days_since_last_push >= min_stale_days.
    """
    use_mock = not isinstance(token_or_client, str)
    now = _now or datetime.now(timezone.utc)
    scored: list[tuple[str, float]] = []
    total_batches = (len(candidates) + GRAPHQL_BATCH_SIZE - 1) // GRAPHQL_BATCH_SIZE
    logger.info("Screening %d candidates in %d batches ...", len(candidates), total_batches)

    for batch_num, start in enumerate(range(0, len(candidates), GRAPHQL_BATCH_SIZE), 1):
        batch = candidates[start : start + GRAPHQL_BATCH_SIZE]
        query, index_to_repo = build_batch_query(batch)

        try:
            if use_mock:
                body = token_or_client.execute_query(query, variables={})
            else:
                body = _graphql_post(token_or_client, query, _session)
        except Exception as exc:
            logger.warning("Batch %d/%d failed: %s", batch_num, total_batches, exc)
            continue

        data = (body.get("data") or {}) if isinstance(body, dict) else {}

        for idx, repo in index_to_repo.items():
            repo_data = data.get(f"repo_{idx}")
            if not repo_data:
                continue  # deleted, private, or GraphQL error — skip
            if repo_data.get("isArchived"):
                continue  # archived — already in a known terminal state

            push_days = days_since(repo_data.get("pushedAt"), now)
            if push_days is None or push_days < min_stale_days:
                continue

            releases = repo_data.get("releases") or {}
            releases_total = releases.get("totalCount", 0)
            stars = repo_data.get("stargazerCount") or 0
            score = fragility_score(push_days, releases_total, stars)
            scored.append((repo, score))

        if not use_mock:
            time.sleep(_INTER_BATCH_SLEEP)

        if batch_num % 5 == 0 or batch_num == total_batches:
            logger.info(
                "  Batch %d/%d done — %d repos qualify so far",
                batch_num,
                total_batches,
                len(scored),
            )

    scored.sort(key=lambda x: (-x[1], x[0].casefold()))
    return scored[:cap]


def append_to_universe(
    universe_path: Path,
    repos: list[str],
    added_date: date,
    min_stale_days: int,
    min_confidence: float,
) -> None:
    """Append a dated Stratum D block to the universe file."""
    block = (
        f"\n# --- Stratum D: stale push >= {min_stale_days}d [sampled {added_date}] ---\n"
        f"# Criteria: package_mappings confidence >= {min_confidence},"
        f" days_since_push >= {min_stale_days}, not archived, cap {len(repos)}\n"
        + "\n".join(repos)
        + "\n"
    )
    with universe_path.open("a", encoding="utf-8") as f:
        f.write(block)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Sample fragility-tail repos from package_mappings for Stratum D.",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=Path("data/universe/universe_v1.txt"),
        help="Universe file to read and append to (default: data/universe/universe_v1.txt)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/graphs.db"),
        help="Path to graphs.db (default: data/graphs.db)",
    )
    parser.add_argument(
        "--min-stale-days",
        type=int,
        default=DEFAULT_MIN_STALE_DAYS,
        help=f"Minimum days since last push to qualify (default: {DEFAULT_MIN_STALE_DAYS})",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help=f"Minimum package_mappings confidence (default: {DEFAULT_MIN_CONFIDENCE})",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=DEFAULT_CAP,
        help=f"Maximum repos to add in this run (default: {DEFAULT_CAP})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print qualifying repos without modifying the universe file",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    if not args.universe.exists():
        logger.error("Universe file not found: %s", args.universe)
        sys.exit(1)
    if not args.db.exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)

    existing = load_universe(args.universe)
    logger.info("Universe currently contains %d repos", len(existing))

    candidates = load_candidates(args.db, existing, args.min_confidence)
    logger.info(
        "Candidate pool: %d repos (confidence >= %.2f, not in universe)",
        len(candidates),
        args.min_confidence,
    )
    if not candidates:
        logger.info("No new candidates. Universe unchanged.")
        return

    selected = screen_candidates(token, candidates, args.min_stale_days, args.cap)

    print()
    print("=== Stratum D sampling results ===")
    print(f"  Candidates screened : {len(candidates)}")
    print(f"  Qualifying (filtered): {len(selected)}")
    print()

    if not selected:
        print("  No repos met the staleness criteria. Universe unchanged.")
        return

    if args.dry_run:
        print(f"  DRY RUN — would add {len(selected)} repos to {args.universe}:")
        for i, (repo, score) in enumerate(selected[:20]):
            print(f"    {i + 1:3}.  {repo:55} score={score:.0f}")
        if len(selected) > 20:
            print(f"    ... and {len(selected) - 20} more")
        return

    today = date.today()
    repo_list = [repo for repo, _ in selected]
    append_to_universe(args.universe, repo_list, today, args.min_stale_days, args.min_confidence)

    new_total = len(existing) + len(repo_list)
    print(f"  Written {len(repo_list)} repos to {args.universe}")
    print(f"  Universe now: {new_total} repos (was {len(existing)})")
    print()
    print("  Top 10 by fragility score:")
    for i, (repo, score) in enumerate(selected[:10]):
        print(f"    {i + 1:2}.  {repo:55} score={score:.0f}")


if __name__ == "__main__":
    main()
