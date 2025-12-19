# -----------------------------------------------------------------------------
# build_days_since_last_push_population.py
#
# Utility script for constructing a baseline population dataset specifically
# for the "days_since_last_push" feature.
#
# Reads raw GitHub repo metadata (often via JSON or the GitHub API), computes
# the days_since_last_push numeric value for each repository, and produces a
# clean sorted array suitable for saving into a baseline population JSON file.
#
# Intended to be run before using option_c mappings to ensure that a fresh,
# representative population distribution exists in data/baseline/.
# -----------------------------------------------------------------------------

import os
import sys
import json
import datetime as dt

import requests

# --- Add src/ to sys.path in case we want package imports later ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# --- GitHub token from environment ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN env var is not set. "
        "Export it in your shell before running this script."
    )

session = requests.Session()
session.headers.update(
    {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "open-source-risk-model-colin",
    }
)

now = dt.datetime.now(dt.timezone.utc)

# 
BASE_QUERY = "stars:>10 fork:false pushed:<2024-12-01"

PER_PAGE = 100
MAX_PAGES = 5  # 5 * 100 = up to 500 repos

days_since_last_push_values: list[float] = []


def main():
    total_seen = 0

    for page in range(1, MAX_PAGES + 1):
        params = {
            "q": BASE_QUERY,
            "per_page": PER_PAGE,
            "page": page,
        }
        url = "https://api.github.com/search/repositories"
        resp = session.get(url, params=params, timeout=15)

        if resp.status_code != 200:
            print(f"[WARN] search page {page}: HTTP {resp.status_code} -> {resp.text[:200]}")
            break

        data = resp.json()
        items = data.get("items", [])
        if not items:
            print(f"[INFO] No more items on page {page}.")
            break

        for repo in items:
            full_name = repo.get("full_name", "<unknown>")
            pushed_at = repo.get("pushed_at")
            if not pushed_at:
                print(f"[WARN] {full_name}: no pushed_at field")
                continue

            pushed_dt = dt.datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            delta = now - pushed_dt
            days = delta.total_seconds() / 86400.0

            days_since_last_push_values.append(days)
            total_seen += 1

            # Print a few samples early on, then sparsely
            if total_seen <= 15 or total_seen % 100 == 0:
                print(f"{total_seen:4d}. {full_name:40s} -> {days:7.1f} days")

    print()
    print(f"Collected {len(days_since_last_push_values)} values")

    # Save distribution for 'broad' Option C mapping
    output_dir = os.path.join(PROJECT_ROOT, "data", "baseline")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "days_since_last_push_population_broad.json")

    with open(output_path, "w") as f:
        json.dump(days_since_last_push_values, f, indent=2)

    print(f"Saved broad population to: {output_path}")


if __name__ == "__main__":
    main()
