#!/usr/bin/env python3
"""QA validation script for demo repositories.

Tests all demo repos against the Deep Signal API endpoints to confirm
the application is ready for deployment.

Usage:
    python scripts/validate_demo_repos.py --api-base http://127.0.0.1:8000

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Data model for test results
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """A single endpoint test result."""

    repo: str               # "owner/repo" or "global" for non-repo tests
    endpoint: str           # e.g. "/api/insights/numpy/numpy"
    passed: bool
    status_code: Optional[int] = None
    body_summary: str = ""


# ---------------------------------------------------------------------------
# Report generation (testable independently — used by Property 3)
# ---------------------------------------------------------------------------

def generate_report(results: list[TestResult]) -> tuple[str, int, int, int]:
    """Build a human-readable QA report from a list of test results.

    Returns:
        A tuple of (report_text, passed_count, failed_count, total_count).
    """
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    lines: list[str] = []

    # Report failures first
    for r in results:
        if not r.passed:
            status_str = str(r.status_code) if r.status_code is not None else "N/A"
            body_str = r.body_summary[:200] if r.body_summary else "(no body)"
            lines.append(
                f"FAIL  repo={r.repo}  endpoint={r.endpoint}  "
                f"status={status_str}  body={body_str}"
            )

    # Summary line
    lines.append(f"PASSED: {passed} | FAILED: {failed} | TOTAL: {total}")

    report_text = "\n".join(lines)
    return report_text, passed, failed, total


# ---------------------------------------------------------------------------
# Individual endpoint testers
# ---------------------------------------------------------------------------

def _summarize_body(resp: requests.Response, max_len: int = 200) -> str:
    """Return a short summary of the response body."""
    try:
        text = resp.text[:max_len]
    except Exception:
        text = "(unreadable)"
    return text


def test_insights(api_base: str, owner: str, repo: str) -> TestResult:
    """GET /api/insights/{owner}/{repo} — 200, non-null score."""
    endpoint = f"/api/insights/{owner}/{repo}"
    url = f"{api_base}{endpoint}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return TestResult(
                repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
                status_code=resp.status_code, body_summary=_summarize_body(resp),
            )
        data = resp.json()
        score = data.get("graph_signal_score")
        if score is None:
            return TestResult(
                repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
                status_code=200, body_summary="score is null",
            )
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=True,
            status_code=200,
        )
    except Exception as exc:
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
            body_summary=str(exc),
        )


def test_graph(api_base: str, owner: str, repo: str) -> TestResult:
    """GET /api/graph?repo={owner}/{repo} — 200, ≥1 node, ≥1 edge."""
    endpoint = f"/api/graph?repo={owner}/{repo}"
    url = f"{api_base}{endpoint}"
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            return TestResult(
                repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
                status_code=resp.status_code, body_summary=_summarize_body(resp),
            )
        data = resp.json()
        graph = data.get("graph", {})
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        if len(nodes) < 1 or len(edges) < 1:
            return TestResult(
                repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
                status_code=200,
                body_summary=f"nodes={len(nodes)}, edges={len(edges)}",
            )
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=True,
            status_code=200,
        )
    except Exception as exc:
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
            body_summary=str(exc),
        )


def test_dependency_tree(api_base: str, owner: str, repo: str) -> TestResult:
    """GET /repos/{owner}/{repo}/dependency-tree — 200, non-empty tree."""
    endpoint = f"/repos/{owner}/{repo}/dependency-tree"
    url = f"{api_base}{endpoint}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return TestResult(
                repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
                status_code=resp.status_code, body_summary=_summarize_body(resp),
            )
        data = resp.json()
        tree = data.get("tree")
        if not tree:
            return TestResult(
                repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
                status_code=200, body_summary="tree is empty or missing",
            )
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=True,
            status_code=200,
        )
    except Exception as exc:
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
            body_summary=str(exc),
        )


def test_score(api_base: str, owner: str, repo: str) -> TestResult:
    """GET /api/score?repo={owner}/{repo} — 200."""
    endpoint = f"/api/score?repo={owner}/{repo}"
    url = f"{api_base}{endpoint}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return TestResult(
                repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
                status_code=resp.status_code, body_summary=_summarize_body(resp),
            )
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=True,
            status_code=200,
        )
    except Exception as exc:
        return TestResult(
            repo=f"{owner}/{repo}", endpoint=endpoint, passed=False,
            body_summary=str(exc),
        )


# ---------------------------------------------------------------------------
# Global endpoint testers
# ---------------------------------------------------------------------------

def test_stats(api_base: str) -> TestResult:
    """GET /api/stats — 200, valid fields with total_repos > 0."""
    endpoint = "/api/stats"
    url = f"{api_base}{endpoint}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return TestResult(
                repo="global", endpoint=endpoint, passed=False,
                status_code=resp.status_code, body_summary=_summarize_body(resp),
            )
        data = resp.json()
        total = data.get("total_repos")
        fully = data.get("fully_analyzed_repos")
        ratio = data.get("coverage_ratio")
        if total is None or fully is None or ratio is None:
            return TestResult(
                repo="global", endpoint=endpoint, passed=False,
                status_code=200, body_summary="missing required fields",
            )
        if total <= 0:
            return TestResult(
                repo="global", endpoint=endpoint, passed=False,
                status_code=200, body_summary=f"total_repos={total} (expected > 0)",
            )
        return TestResult(
            repo="global", endpoint=endpoint, passed=True,
            status_code=200,
        )
    except Exception as exc:
        return TestResult(
            repo="global", endpoint=endpoint, passed=False,
            body_summary=str(exc),
        )


def test_demo_repos_endpoint(api_base: str) -> TestResult:
    """GET /api/demo-repos — 200, non-empty list."""
    endpoint = "/api/demo-repos"
    url = f"{api_base}{endpoint}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return TestResult(
                repo="global", endpoint=endpoint, passed=False,
                status_code=resp.status_code, body_summary=_summarize_body(resp),
            )
        data = resp.json()
        repos = data.get("repos", [])
        if len(repos) == 0:
            return TestResult(
                repo="global", endpoint=endpoint, passed=False,
                status_code=200, body_summary="repos list is empty",
            )
        return TestResult(
            repo="global", endpoint=endpoint, passed=True,
            status_code=200,
        )
    except Exception as exc:
        return TestResult(
            repo="global", endpoint=endpoint, passed=False,
            body_summary=str(exc),
        )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_validation(api_base: str) -> list[TestResult]:
    """Run all QA validation tests and return the list of results."""
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

    from open_source_risk_model.config.demo_repos import validate_demo_repos

    db_path = os.getenv("GRAPH_DB_PATH", "data/graphs.db")
    validated = validate_demo_repos(db_path)

    if len(validated) < 5:
        print(
            f"WARNING: Only {len(validated)} validated demo repos found "
            f"(minimum 5 required). Testing all available."
        )

    results: list[TestResult] = []

    # Global endpoint tests
    results.append(test_stats(api_base))
    results.append(test_demo_repos_endpoint(api_base))

    # Per-repo endpoint tests
    for demo in validated:
        owner, repo = demo.repo.split("/", 1)
        results.append(test_insights(api_base, owner, repo))
        results.append(test_graph(api_base, owner, repo))
        results.append(test_dependency_tree(api_base, owner, repo))
        results.append(test_score(api_base, owner, repo))

    return results


def main(api_base: str = "http://127.0.0.1:8000") -> int:
    """Run QA validation and return exit code (0 = all pass, 1 = any fail)."""
    print(f"Running QA validation against {api_base} ...")

    results = run_validation(api_base)
    report, passed, failed, total = generate_report(results)

    print(report)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="QA validation script for Deep Signal demo repos"
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8000",
        help="Base URL of the Deep Signal API (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()
    sys.exit(main(api_base=args.api_base))
