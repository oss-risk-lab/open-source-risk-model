#!/usr/bin/env python3
"""Compute and print insights for all repos. Does NOT persist results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.open_source_risk_model.insights.compute import compute_repo_insight
from src.open_source_risk_model.persistence.graph_repo import GraphRepository


def main():
    db_path = "data/graphs.db"
    # Create a single GraphRepository and reuse it for all repos
    graph_repo = GraphRepository(db_path)
    repos = graph_repo.list_repos(limit=10000)

    total = len(repos)
    success = 0
    failed = 0

    for repo_info in repos:
        name = repo_info["repo_full_name"]
        try:
            insight = compute_repo_insight(name, graph_repo=graph_repo)
            label = insight.graph_signal_label
            score = insight.graph_signal_score
            reasons = "; ".join(insight.reasons) if insight.reasons else "none"
            print(f"  {name}: {label} ({score:.3f}) — {reasons}")
            success += 1
        except Exception as e:
            print(f"  {name}: ERROR — {e}", file=sys.stderr)
            failed += 1

    print(f"\nTotal: {total} | Success: {success} | Failed: {failed}")


if __name__ == "__main__":
    main()
