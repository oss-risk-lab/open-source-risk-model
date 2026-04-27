"""Property-based tests for the insight engine orchestrator.

Verifies:
- Property 1: score bounded 0.0–1.0
- Property 3: label thresholds (HIGH≥0.6, MEDIUM≥0.3, LOW otherwise)
- Property 5: reasons count matches non-info signals
- Property 4: deterministic signal order

**Validates: Requirements 7.4, 7.5, 7.6, 7.10, 8.1, 8.2**
"""
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from open_source_risk_model.insights.compute import compute_repo_insight


# ── Strategies ────────────────────────────────────────────────────────

# Generate realistic graph node lists
cve_node_st = st.fixed_dictionaries(
    {
        "type": st.just("cve"),
        "metadata": st.fixed_dictionaries(
            {
                "cve_id": st.text(min_size=3, max_size=20, alphabet="CVE-0123456789"),
            },
            optional={
                "cvss_score": st.one_of(
                    st.none(),
                    st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
                ),
                "severity": st.one_of(st.just(""), st.text(min_size=0, max_size=30)),
            },
        ),
    }
)

maintainer_node_st = st.fixed_dictionaries(
    {
        "type": st.just("maintainer"),
        "metadata": st.fixed_dictionaries(
            {
                "username": st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnop"),
                "contribution_fraction": st.floats(
                    min_value=0.0, max_value=1.0, allow_nan=False
                ),
            }
        ),
    }
)

release_node_st = st.fixed_dictionaries(
    {
        "type": st.just("release"),
        "metadata": st.fixed_dictionaries(
            {
                "tag_name": st.text(min_size=1, max_size=10, alphabet="v0123456789."),
                "is_latest": st.booleans(),
                "days_ago": st.integers(min_value=0, max_value=3000),
            }
        ),
    }
)

repo_node_st = st.fixed_dictionaries(
    {
        "type": st.just("repo"),
        "metadata": st.fixed_dictionaries(
            {},
            optional={
                "maintenance_risk": st.one_of(
                    st.none(),
                    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
                ),
                "maintenance_label": st.one_of(
                    st.none(), st.sampled_from(["HIGH", "MEDIUM", "LOW"])
                ),
            },
        ),
    }
)


def graph_data_strategy():
    """Generate graph data dicts with at least one repo node."""
    return st.builds(
        lambda repo, cves, maintainers, releases: {
            "repo": "test/repo",
            "graph": {
                "nodes": [repo] + cves + maintainers + releases,
                "edges": [],
            },
            "metadata": {},
        },
        repo=repo_node_st,
        cves=st.lists(cve_node_st, min_size=0, max_size=5),
        maintainers=st.lists(maintainer_node_st, min_size=0, max_size=5),
        releases=st.lists(release_node_st, min_size=0, max_size=5),
    )


def _make_graph_repo(graph_data):
    repo = MagicMock()
    repo.get_graph.return_value = graph_data
    return repo


# ── Property 1: Score bounded 0.0–1.0 (Req 8.1, 8.2) ────────────────
# **Validates: Requirements 8.1, 8.2**


@given(graph_data=graph_data_strategy())
@settings(max_examples=300)
def test_score_bounded(graph_data):
    """graph_signal_score is always in [0.0, 1.0]."""
    graph_repo = _make_graph_repo(graph_data)
    insight = compute_repo_insight("test/repo", graph_repo)
    assert 0.0 <= insight.graph_signal_score <= 1.0


# ── Property 3: Label thresholds (Req 7.5) ───────────────────────────
# **Validates: Requirements 7.5**


@given(graph_data=graph_data_strategy())
@settings(max_examples=300)
def test_label_thresholds(graph_data):
    """Label matches score thresholds: HIGH≥0.6, MEDIUM≥0.3, LOW otherwise."""
    graph_repo = _make_graph_repo(graph_data)
    insight = compute_repo_insight("test/repo", graph_repo)

    score = insight.graph_signal_score
    label = insight.graph_signal_label

    if score >= 0.6:
        assert label == "HIGH", f"score={score} should be HIGH, got {label}"
    elif score >= 0.3:
        assert label == "MEDIUM", f"score={score} should be MEDIUM, got {label}"
    else:
        assert label == "LOW", f"score={score} should be LOW, got {label}"


# ── Property 5: Reasons count matches non-info signals (Req 7.6) ─────
# **Validates: Requirements 7.6**


@given(graph_data=graph_data_strategy())
@settings(max_examples=300)
def test_reasons_count_matches_non_info_signals(graph_data):
    """Number of reasons equals number of non-info signals."""
    graph_repo = _make_graph_repo(graph_data)
    insight = compute_repo_insight("test/repo", graph_repo)

    non_info_count = sum(
        1 for s in insight.direct_signals if s.severity != "info"
    )
    assert len(insight.reasons) == non_info_count


# ── Property 4: Deterministic signal order (Req 7.10) ────────────────
# **Validates: Requirements 7.10**


@given(graph_data=graph_data_strategy())
@settings(max_examples=300)
def test_deterministic_signal_order(graph_data):
    """direct_signals always in order: cve_risk, maintainer_concentration, release_staleness."""
    graph_repo = _make_graph_repo(graph_data)
    insight = compute_repo_insight("test/repo", graph_repo)

    assert len(insight.direct_signals) == 3
    assert insight.direct_signals[0].signal_name == "cve_risk"
    assert insight.direct_signals[1].signal_name == "maintainer_concentration"
    assert insight.direct_signals[2].signal_name == "release_staleness"
