"""Property-based tests for QA report consistency.

Property 3: QA Report Consistency
For any set of test results (each being a pass or fail with associated repo name,
endpoint path, HTTP status code, and response summary), the QA script's summary
SHALL report passed + failed == total, and every failed test SHALL include the
repository name, endpoint path, HTTP status code, and response body summary in
its failure report.

**Validates: Requirements 5.6, 5.7**
"""
from __future__ import annotations

import sys
import os

# Ensure scripts/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from hypothesis import given, settings
from hypothesis import strategies as st

from validate_demo_repos import TestResult, generate_report

# ── Strategies ────────────────────────────────────────────────────────

_repo_name_st = st.builds(
    lambda owner, name: f"{owner}/{name}",
    owner=st.text(min_size=1, max_size=15, alphabet="abcdefghijklmnopqrstuvwxyz-_"),
    name=st.text(min_size=1, max_size=15, alphabet="abcdefghijklmnopqrstuvwxyz-_0123456789"),
)

_endpoint_st = st.sampled_from([
    "/api/insights/owner/repo",
    "/api/graph?repo=owner/repo",
    "/repos/owner/repo/dependency-tree",
    "/api/score?repo=owner/repo",
    "/api/stats",
    "/api/demo-repos",
])

_status_code_st = st.one_of(
    st.just(None),
    st.sampled_from([200, 400, 403, 404, 500, 502, 503]),
)

_body_summary_st = st.text(min_size=0, max_size=100, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
    blacklist_characters="\x00",
))

_test_result_st = st.builds(
    TestResult,
    repo=_repo_name_st,
    endpoint=_endpoint_st,
    passed=st.booleans(),
    status_code=_status_code_st,
    body_summary=_body_summary_st,
)

_test_results_list_st = st.lists(_test_result_st, min_size=0, max_size=50)


# ── Property 3: QA Report Consistency ─────────────────────────────────
# **Validates: Requirements 5.6, 5.7**


@given(results=_test_results_list_st)
@settings(max_examples=100)
def test_passed_plus_failed_equals_total(results: list[TestResult]):
    """passed + failed == total for any list of test results."""
    report_text, passed, failed, total = generate_report(results)

    assert passed + failed == total, (
        f"passed ({passed}) + failed ({failed}) != total ({total}). "
        f"Input had {len(results)} results."
    )
    assert total == len(results), (
        f"total ({total}) != len(results) ({len(results)})"
    )


@given(results=_test_results_list_st)
@settings(max_examples=100)
def test_failed_tests_include_required_details(results: list[TestResult]):
    """Every failed test result includes repo name, endpoint, status code, and body summary."""
    report_text, passed, failed, total = generate_report(results)

    failed_results = [r for r in results if not r.passed]

    for r in failed_results:
        # Repo name must appear in report
        assert r.repo in report_text, (
            f"Failed test repo '{r.repo}' not found in report.\n"
            f"Report:\n{report_text}"
        )
        # Endpoint path must appear in report
        assert r.endpoint in report_text, (
            f"Failed test endpoint '{r.endpoint}' not found in report.\n"
            f"Report:\n{report_text}"
        )
        # HTTP status code must appear in report
        status_str = str(r.status_code) if r.status_code is not None else "N/A"
        assert status_str in report_text, (
            f"Failed test status code '{status_str}' not found in report.\n"
            f"Report:\n{report_text}"
        )
        # Body summary must appear in report (or the fallback "(no body)")
        if r.body_summary:
            body_in_report = r.body_summary[:200]
            assert body_in_report in report_text, (
                f"Failed test body summary '{body_in_report}' not found in report.\n"
                f"Report:\n{report_text}"
            )
        else:
            assert "(no body)" in report_text, (
                f"Expected '(no body)' fallback in report for empty body_summary.\n"
                f"Report:\n{report_text}"
            )
