"""
Build data/universe/universe_v1.txt from four strata using only local data.

No API calls are made. Sources: graphs.db, data/raw_snapshots/, data/expansion_repos_*.json.

Strata (first wins in cross-stratum deduplication):
  A  Core ingested repos        graphs.db repo_ingestion_runs + raw_snapshots/ filenames
  B  Top-starred expansion      data/expansion_repos_*.json, sorted by stars desc, capped at 300
  C  Dependency-graph tail      package_mappings repos (confidence >= 0.75), stars < 2000 where
                                 known, capped at 600 after dedup
  D  At-risk signals            repo_maintainers bus factor > 0.8 + stale repos (days_since_last_release
                                 > 365 from repo_graphs risk_factor nodes), uncapped

Usage:
    python scripts/build_universe_v1.py [--db data/graphs.db] [--output data/universe/universe_v1.txt]
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

STRATUM_B_CAP = 300
STRATUM_C_CAP = 600
STRATUM_C_MIN_CONFIDENCE = 0.75
STARS_THRESHOLD = 2000


def _valid(repo: str) -> bool:
    return bool(REPO_RE.match(repo))


def _raw_snapshot_filename_to_repo(name: str) -> str | None:
    """Convert 'Owner__repo.json' to 'Owner/repo', None if not parseable."""
    stem = name.removesuffix(".json")
    if "__" not in stem:
        return None
    owner, _, rest = stem.partition("__")
    if not owner or not rest:
        return None
    repo = f"{owner}/{rest}"
    return repo if _valid(repo) else None


def build_stratum_a(db_path: Path, raw_snapshots_dir: Path) -> list[str]:
    """Core repos: ingestion_runs union raw_snapshot filenames."""
    repos: set[str] = set()

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT repo_full_name FROM repo_ingestion_runs WHERE repo_full_name IS NOT NULL")
        for (r,) in cur.fetchall():
            if _valid(r):
                repos.add(r)
    finally:
        conn.close()

    if raw_snapshots_dir.is_dir():
        for f in raw_snapshots_dir.glob("*.json"):
            r = _raw_snapshot_filename_to_repo(f.name)
            if r:
                repos.add(r)

    return sorted(repos, key=str.casefold)


def build_stratum_b(data_dir: Path, exclude: set[str]) -> list[str]:
    """Top-starred expansion repos from expansion_repos_*.json, capped at STRATUM_B_CAP."""
    candidates: list[tuple[str, int]] = []

    for f in sorted(data_dir.glob("expansion_repos_*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for entry in doc.get("repositories", []):
            name = entry.get("full_name", "")
            stars = entry.get("stars", 0) or 0
            if _valid(name):
                candidates.append((name, stars))

    # Deduplicate within stratum, keep highest-star occurrence, sort desc
    seen: dict[str, int] = {}
    for name, stars in candidates:
        if name not in seen or stars > seen[name]:
            seen[name] = stars

    ranked = sorted(seen.items(), key=lambda x: -x[1])
    result = [name for name, _ in ranked if name not in exclude]
    return result[:STRATUM_B_CAP]


def build_stratum_c(db_path: Path, exclude: set[str], known_stars: dict[str, int]) -> list[str]:
    """Dependency-graph repos from package_mappings, filtered to stars < STARS_THRESHOLD where known."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT repo_full_name FROM package_mappings "
            "WHERE repo_full_name IS NOT NULL AND repo_full_name != '' AND confidence >= ?",
            (STRATUM_C_MIN_CONFIDENCE,),
        )
        rows = [r for (r,) in cur.fetchall()]
    finally:
        conn.close()

    result = []
    for repo in rows:
        if not _valid(repo):
            continue
        if repo in exclude:
            continue
        stars = known_stars.get(repo)
        if stars is not None and stars >= STARS_THRESHOLD:
            continue
        result.append(repo)

    result.sort(key=str.casefold)
    return result[:STRATUM_C_CAP]


def build_stratum_d(db_path: Path, raw_snapshots_dir: Path, exclude: set[str]) -> list[str]:
    """At-risk repos: bus factor > 0.8 and stale releases (> 365 days)."""
    repos: set[str] = set()

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Bus-factor signal: one contributor owns > 80% of commits
        cur.execute(
            "SELECT DISTINCT repo_full_name FROM repo_maintainers "
            "WHERE contribution_fraction > 0.8 AND repo_full_name IS NOT NULL"
        )
        for (r,) in cur.fetchall():
            if _valid(r):
                repos.add(r)

        # Stale-release signal from repo_graphs risk_factor nodes
        cur.execute("SELECT repo_full_name, graph_json FROM repo_graphs")
        for repo, gjson in cur.fetchall():
            if not _valid(repo):
                continue
            try:
                g = json.loads(gjson)
            except (json.JSONDecodeError, ValueError):
                continue
            for node in g.get("nodes", []):
                if node.get("type") == "risk_factor":
                    meta = node.get("metadata", {})
                    if meta.get("key") == "days_since_last_release":
                        val = meta.get("raw_value")
                        if val is not None and val > 365:
                            repos.add(repo)
    finally:
        conn.close()

    # Also check raw_snapshots for stale-release signal
    if raw_snapshots_dir.is_dir():
        for f in raw_snapshots_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            repo = data.get("full_name", "")
            if not _valid(repo):
                continue
            dslr = data.get("features", {}).get("days_since_last_release")
            if dslr is not None and dslr > 365:
                repos.add(repo)

    result = sorted(repos - exclude, key=str.casefold)
    return result


def _build_known_stars(data_dir: Path, raw_snapshots_dir: Path) -> dict[str, int]:
    """Build a mapping of repo -> stars from all available local sources."""
    stars: dict[str, int] = {}

    for f in sorted(data_dir.glob("expansion_repos_*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for entry in doc.get("repositories", []):
            name = entry.get("full_name", "")
            s = entry.get("stars") or 0
            if _valid(name):
                stars[name] = max(stars.get(name, 0), s)

    if raw_snapshots_dir.is_dir():
        for f in raw_snapshots_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            repo = data.get("full_name", "")
            feats = data.get("features", {})
            s = feats.get("stars_count") or feats.get("stargazers_count") or 0
            if _valid(repo) and s:
                stars[repo] = max(stars.get(repo, 0), int(s))

    return stars


def write_universe(output_path: Path, strata: dict[str, list[str]]) -> int:
    """Write universe_v1.txt with labeled comment headers. Returns total repo count."""
    lines = [
        "# Deep Signal Observatory -- Universe v1",
        "# Auto-generated by scripts/build_universe_v1.py",
        "# Format: owner/repo (one per line, # comments and blank lines ignored)",
        "",
    ]
    total = 0
    labels = {
        "A": "Stratum A: core ingested repos (graphs.db + raw_snapshots/)",
        "B": "Stratum B: top-starred expansion candidates",
        "C": "Stratum C: dependency-graph long tail (package_mappings)",
        "D": "Stratum D: at-risk signals (bus factor + stale release)",
    }
    for key, repos in strata.items():
        lines.append(f"# --- {labels[key]} ---")
        lines.extend(repos)
        lines.append("")
        total += len(repos)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return total


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build data/universe/universe_v1.txt from local data.")
    parser.add_argument("--db", type=Path, default=Path("data/graphs.db"), help="Path to graphs.db")
    parser.add_argument(
        "--raw-snapshots-dir",
        type=Path,
        default=Path("data/raw_snapshots"),
        help="Directory containing raw snapshot JSON files",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing expansion_repos_*.json files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/universe/universe_v1.txt"),
        help="Output path for universe file",
    )
    args = parser.parse_args(argv)

    print("Building universe v1 ...")
    print(f"  DB:              {args.db}")
    print(f"  Raw snapshots:   {args.raw_snapshots_dir}")
    print(f"  Data dir:        {args.data_dir}")
    print()

    known_stars = _build_known_stars(args.data_dir, args.raw_snapshots_dir)
    print(f"  Known star counts: {len(known_stars)} repos")

    stratum_a = build_stratum_a(args.db, args.raw_snapshots_dir)
    seen: set[str] = set(stratum_a)

    stratum_b = build_stratum_b(args.data_dir, seen)
    seen.update(stratum_b)

    stratum_c = build_stratum_c(args.db, seen, known_stars)
    seen.update(stratum_c)

    stratum_d = build_stratum_d(args.db, args.raw_snapshots_dir, seen)
    seen.update(stratum_d)

    strata = {"A": stratum_a, "B": stratum_b, "C": stratum_c, "D": stratum_d}
    total = write_universe(args.output, strata)

    shortfall = max(0, 1200 - total)

    print()
    print("=== Universe v1 census ===")
    print(f"  Stratum A (core ingested):      {len(stratum_a):>5}")
    print(f"  Stratum B (top-starred, cap {STRATUM_B_CAP}): {len(stratum_b):>5}")
    print(f"  Stratum C (dep-graph tail, cap {STRATUM_C_CAP}): {len(stratum_c):>5}")
    print(f"  Stratum D (at-risk signals):    {len(stratum_d):>5}")
    print(f"  {'─' * 36}")
    print(f"  Total:                          {total:>5}")
    if shortfall:
        print(f"  SHORTFALL vs 1200-target:       {shortfall:>5}  (add more expansion data to close gap)")
    else:
        print(f"  Target 1200-1500:               {'OK' if total <= 1500 else 'OVER'}")
    print()
    print(f"  Written: {args.output}")


if __name__ == "__main__":
    main()
