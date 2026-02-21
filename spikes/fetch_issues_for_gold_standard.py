# spikes/fetch_issues_for_gold_standard.py

import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from open_source_risk_model.data_ingestion.gold_standard_repos import GOLD_STANDARD_REPOS
from open_source_risk_model.storage.issues_store import IssueStore
from open_source_risk_model.data_ingestion.github_issues import fetch_issues_updated_since


def _parse_iso(dt_str: str):
    # Manifest uses timezone-aware ISO strings
    return datetime.fromisoformat(dt_str)


def should_skip_repo(store: IssueStore, full_name: str, max_age: timedelta) -> bool:
    manifest = store.load_manifest(full_name) or {}
    updated = manifest.get("updated_at_utc")
    if not updated:
        return False
    try:
        last = _parse_iso(updated)
    except Exception:
        return False
    age = datetime.now(timezone.utc) - last
    return age <= max_age


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-back", type=int, default=7)
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--max-age-hours", type=float, default=24.0)
    ap.add_argument("--refresh", action="store_true", help="Force re-fetch even if manifest is fresh")
    args = ap.parse_args()

    store = IssueStore()
    max_age = timedelta(hours=args.max_age_hours)

    print(f"Gold repos: {len(GOLD_STANDARD_REPOS)}")
    print(f"Config: days_back={args.days_back}, max_pages={args.max_pages}, per_page={args.per_page}")
    print(f"Skip if fetched within last {args.max_age_hours}h: {not args.refresh}")
    print()

    ok, skipped, failed = 0, 0, 0

    for full_name in GOLD_STANDARD_REPOS:
        issue_dir = Path("data/issues") / full_name.replace("/", "__")

        if (not args.refresh) and should_skip_repo(store, full_name, max_age):
            print(f"SKIP {full_name:30s} (fresh manifest) -> {issue_dir}")
            skipped += 1
            continue

        try:
            print(f"FETCH {full_name} ...")
            manifest = fetch_issues_updated_since(
                full_name,
                store,
                days_back=args.days_back,
                max_pages=args.max_pages,
                per_page=args.per_page,
            )

            issues_written = manifest.get("issues_written_last_run", 0)
            comments_written = manifest.get("comments_written_last_run", 0)
            pages = manifest.get("pages_fetched_last_run", 0)
            last_fetch = manifest.get("last_fetch_utc")

            print(
                f"OK   {full_name:30s} pages={pages} "
                f"issues+={issues_written} comments+={comments_written} "
                f"last_fetch={last_fetch} -> {issue_dir}"
            )
            ok += 1

        except Exception as e:
            print(f"FAIL {full_name:30s} {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"Done. ok={ok}, skipped={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
