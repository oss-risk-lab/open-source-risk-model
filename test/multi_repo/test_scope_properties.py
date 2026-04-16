"""Property-based tests for multi-repo scope computation functions.

Uses Hypothesis to verify invariants of merge_graphs, compute_system_risk_summary,
compute_scope_status, compute_priority_risks, resolve_dependency_input, and
get_top_risk_drivers.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

from collections import Counter

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from open_source_risk_model.graph.schema import Graph, Node, Edge, NodeType, EdgeType
from app import (
    merge_graphs,
    compute_system_risk_summary,
    compute_scope_status,
    compute_priority_risks,
    resolve_dependency_input,
    get_top_risk_drivers,
    PACKAGE_TO_REPO,
    SEVERITY_BASE,
    _risk_label_from_score,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating valid node IDs (short, readable)
node_id_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-:",
    min_size=1,
    max_size=20,
)

# Strategy for repo names in owner/repo format
repo_name_st = st.from_regex(r"[a-z]{2,8}/[a-z]{2,8}", fullmatch=True)

# Strategy for node types suitable for package/dependency nodes
package_node_type_st = st.sampled_from([NodeType.PACKAGE])

# Strategy for edge types
edge_type_st = st.sampled_from(list(EdgeType))

# Strategy for risk scores (0.0 to 1.0)
risk_score_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


def node_st(node_ids=None):
    """Strategy for generating a Node."""
    id_strategy = st.sampled_from(node_ids) if node_ids else node_id_st
    return st.builds(
        Node,
        id=id_strategy,
        type=st.sampled_from(list(NodeType)),
        label=st.text(min_size=1, max_size=10),
        metadata=st.just({}),
        provenance=st.just({}),
    )


def edge_st(node_ids):
    """Strategy for generating an Edge between known node IDs."""
    return st.builds(
        Edge,
        source=st.sampled_from(node_ids),
        target=st.sampled_from(node_ids),
        relationship_type=edge_type_st,
        metadata=st.just({}),
        provenance=st.just({}),
    )


@st.composite
def graph_with_nodes_st(draw, node_ids=None, min_nodes=1, max_nodes=5):
    """Strategy for generating a Graph with nodes and edges."""
    if node_ids is None:
        node_ids = draw(
            st.lists(node_id_st, min_size=min_nodes, max_size=max_nodes, unique=True)
        )
    assume(len(node_ids) >= 1)
    nodes = []
    seen = set()
    for nid in node_ids:
        if nid not in seen:
            seen.add(nid)
            n = draw(node_st(node_ids=[nid]))
            nodes.append(n)
    edges = draw(st.lists(edge_st(node_ids), min_size=0, max_size=4))
    g = Graph(nodes=nodes, edges=edges)
    return g


@st.composite
def graphs_with_overlap_st(draw, min_graphs=2, max_graphs=4):
    """Strategy for generating multiple graphs with overlapping node IDs."""
    # Generate a shared pool of node IDs
    all_ids = draw(st.lists(node_id_st, min_size=3, max_size=10, unique=True))
    assume(len(all_ids) >= 3)
    num_graphs = draw(st.integers(min_value=min_graphs, max_value=max_graphs))
    result = []
    for _ in range(num_graphs):
        # Each graph picks a subset of the shared IDs (at least 1)
        subset = draw(
            st.lists(
                st.sampled_from(all_ids), min_size=1, max_size=len(all_ids), unique=True
            )
        )
        g = draw(graph_with_nodes_st(node_ids=subset))
        repo = draw(repo_name_st)
        result.append((repo, g))
    return result


def per_repo_result_st(with_error=None):
    """Strategy for generating a per-repo result dict."""
    if with_error is True:
        return st.fixed_dictionaries({
            "repo": repo_name_st,
            "risk_score": st.none(),
            "risk_label": st.none(),
            "error": st.text(min_size=1, max_size=30),
        })
    if with_error is False:
        return st.fixed_dictionaries({
            "repo": repo_name_st,
            "risk_score": risk_score_st,
            "risk_label": st.sampled_from(["LOW", "MEDIUM", "HIGH"]),
            "error": st.none(),
        })
    # Mixed: either success or error
    return st.one_of(
        per_repo_result_st(with_error=True),
        per_repo_result_st(with_error=False),
    )


def consistent_per_repo_result_st():
    """Strategy for a per-repo result where risk_label matches risk_score thresholds."""
    return risk_score_st.flatmap(
        lambda score: st.fixed_dictionaries({
            "repo": repo_name_st,
            "risk_score": st.just(score),
            "risk_label": st.just(_risk_label_from_score(score)),
            "error": st.none(),
        })
    )


# ---------------------------------------------------------------------------
# Property 3: Graph merge deduplication and source tracking
# **Validates: Requirements 2.6, 2.7**
# ---------------------------------------------------------------------------

class TestMergeGraphsProperties:
    """Property 3: Graph merge deduplication and source tracking."""

    @given(data=graphs_with_overlap_st())
    @settings(max_examples=50)
    def test_unique_node_ids_after_merge(self, data):
        """(a) Each unique node ID appears exactly once in merged output."""
        result = merge_graphs(data, [])
        node_ids = [n["id"] for n in result["nodes"]]
        assert len(node_ids) == len(set(node_ids))

    @given(data=graphs_with_overlap_st())
    @settings(max_examples=50)
    def test_source_repos_tracking(self, data):
        """(b) Each merged node's source_repos contains all repos that contributed it."""
        result = merge_graphs(data, [])
        # Build expected source_repos per node ID
        expected = {}
        for repo_name, graph_obj in data:
            for node in graph_obj.nodes:
                expected.setdefault(node.id, set()).add(repo_name)
        for merged_node in result["nodes"]:
            nid = merged_node["id"]
            assert set(merged_node["source_repos"]) == expected[nid]

    @given(data=graphs_with_overlap_st())
    @settings(max_examples=50)
    def test_different_edge_types_preserved(self, data):
        """(c) Edges with different relationship types between same nodes are preserved."""
        result = merge_graphs(data, [])
        # Collect all unique (source, target, type) from input
        input_edge_keys = set()
        for _, graph_obj in data:
            for edge in graph_obj.edges:
                input_edge_keys.add((edge.source, edge.target, edge.relationship_type.value))
        # All unique input edge keys should appear in output
        output_edge_keys = set()
        for e in result["edges"]:
            output_edge_keys.add((e["source"], e["target"], e["relationship_type"]))
        assert input_edge_keys == output_edge_keys

    @given(data=graphs_with_overlap_st())
    @settings(max_examples=50)
    def test_edge_dedup_same_type(self, data):
        """(d) Edges with same (source, target, type) appear exactly once."""
        result = merge_graphs(data, [])
        edge_keys = [
            (e["source"], e["target"], e["relationship_type"]) for e in result["edges"]
        ]
        assert len(edge_keys) == len(set(edge_keys))

    @given(data=graphs_with_overlap_st())
    @settings(max_examples=50)
    def test_total_node_count_bounded(self, data):
        """(e) Total node count <= sum of input node counts."""
        result = merge_graphs(data, [])
        total_input_nodes = sum(len(g.nodes) for _, g in data)
        assert len(result["nodes"]) <= total_input_nodes


# ---------------------------------------------------------------------------
# Property 4: System risk summary correctness
# **Validates: Requirements 2.8**
# ---------------------------------------------------------------------------

class TestSystemRiskSummaryProperties:
    """Property 4: System risk summary correctness."""

    @given(results=st.lists(per_repo_result_st(), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_total_repos_equals_input_length(self, results):
        """(a) total_repos equals input list length."""
        summary = compute_system_risk_summary(results, {"nodes": [], "edges": []})
        assert summary["total_repos"] == len(results)

    @given(results=st.lists(per_repo_result_st(), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_risk_category_counts_sum(self, results):
        """(b) high + medium + low = count of non-error repos."""
        summary = compute_system_risk_summary(results, {"nodes": [], "edges": []})
        non_error = sum(1 for r in results if r.get("error") is None)
        assert (
            summary["high_risk_repos"]
            + summary["medium_risk_repos"]
            + summary["low_risk_repos"]
        ) == non_error

    @given(results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_aggregate_score_is_mean(self, results):
        """(c) aggregate_risk_score is arithmetic mean of non-error scores."""
        summary = compute_system_risk_summary(results, {"nodes": [], "edges": []})
        valid_scores = [r["risk_score"] for r in results if r.get("error") is None]
        if valid_scores:
            expected_mean = sum(valid_scores) / len(valid_scores)
            assert abs(summary["aggregate_risk_score"] - expected_mean) < 1e-9
        else:
            assert summary["aggregate_risk_score"] == 0.0

    @given(results=st.lists(consistent_per_repo_result_st(), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_aggregate_label_matches_score(self, results):
        """(d) aggregate_label matches _risk_label_from_score(aggregate_score)."""
        summary = compute_system_risk_summary(results, {"nodes": [], "edges": []})
        expected_label = _risk_label_from_score(summary["aggregate_risk_score"])
        assert summary["aggregate_label"] == expected_label


# ---------------------------------------------------------------------------
# Property 5: Status computation from processing outcomes
# **Validates: Requirements 2.10**
# ---------------------------------------------------------------------------

class TestScopeStatusProperties:
    """Property 5: Status computation."""

    @given(results=st.lists(per_repo_result_st(with_error=False), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_all_succeed_complete(self, results):
        """All succeed → 'complete'."""
        assert compute_scope_status(results) == "complete"

    @given(results=st.lists(per_repo_result_st(with_error=True), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_all_fail_failed(self, results):
        """All fail → 'failed'."""
        assert compute_scope_status(results) == "failed"

    @given(
        successes=st.lists(per_repo_result_st(with_error=False), min_size=1, max_size=5),
        failures=st.lists(per_repo_result_st(with_error=True), min_size=1, max_size=5),
    )
    @settings(max_examples=50)
    def test_mixed_partial(self, successes, failures):
        """Mixed → 'partial'."""
        combined = successes + failures
        assert compute_scope_status(combined) == "partial"


# ---------------------------------------------------------------------------
# Property 6: Priority risk ranking by score
# **Validates: Requirements 2.11**
# ---------------------------------------------------------------------------

class TestPriorityRisksProperties:
    """Property 6: Priority risk ranking."""

    @given(results=st.lists(per_repo_result_st(), min_size=0, max_size=8))
    @settings(max_examples=50)
    def test_sorted_descending_by_priority_score(self, results):
        """(a) Sorted by priority_score descending."""
        merged = {"nodes": [], "edges": []}
        risks = compute_priority_risks(results, merged)
        scores = [r["priority_score"] for r in risks]
        assert scores == sorted(scores, reverse=True)

    @given(results=st.lists(per_repo_result_st(), min_size=0, max_size=8))
    @settings(max_examples=50)
    def test_limited_to_five(self, results):
        """(b) Limited to at most 5 items."""
        merged = {"nodes": [], "edges": []}
        risks = compute_priority_risks(results, merged)
        assert len(risks) <= 5

    @given(results=st.lists(per_repo_result_st(), min_size=0, max_size=8))
    @settings(max_examples=50)
    def test_required_fields_present(self, results):
        """(c) Each item has required fields."""
        merged = {"nodes": [], "edges": []}
        risks = compute_priority_risks(results, merged)
        required = {"name", "type", "reason", "severity", "priority_score", "used_by_repos"}
        for item in risks:
            assert required.issubset(item.keys()), f"Missing fields: {required - item.keys()}"


# ---------------------------------------------------------------------------
# Property 7: Dependency resolution — mapped vs unmapped
# **Validates: Requirements 2.9**
# ---------------------------------------------------------------------------

class TestDependencyResolutionProperties:
    """Property 7: Dependency resolution."""

    @given(dep=st.sampled_from(list(PACKAGE_TO_REPO.keys())))
    @settings(max_examples=50)
    def test_mapped_dependency(self, dep):
        """For any dep in PACKAGE_TO_REPO, resolution returns mapped=True with correct repo."""
        result = resolve_dependency_input(dep)
        assert result["mapped"] is True
        assert result["repo"] == PACKAGE_TO_REPO[dep]
        assert result["kind"] == "repo"
        assert result["package_name"] == dep

    @given(
        dep=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_unmapped_dependency(self, dep):
        """For any dep NOT in mapping, returns mapped=False with repo=None."""
        assume(dep not in PACKAGE_TO_REPO)
        result = resolve_dependency_input(dep)
        assert result["mapped"] is False
        assert result["repo"] is None
        assert result["kind"] == "package_only"
        assert result["package_name"] == dep


# ---------------------------------------------------------------------------
# Property 8: Top risk drivers sorting
# **Validates: Requirements 5.4**
# ---------------------------------------------------------------------------

class TestTopRiskDriversProperties:
    """Property 8: Top risk drivers sorting."""

    @given(results=st.lists(per_repo_result_st(), min_size=0, max_size=12))
    @settings(max_examples=50)
    def test_sorted_descending_by_risk_score(self, results):
        """Top risk drivers are sorted descending by risk_score."""
        drivers = get_top_risk_drivers(results)
        scores = [d["risk_score"] for d in drivers]
        assert scores == sorted(scores, reverse=True)

    @given(results=st.lists(per_repo_result_st(), min_size=0, max_size=12))
    @settings(max_examples=50)
    def test_limited_to_five(self, results):
        """Limited to 5 items."""
        drivers = get_top_risk_drivers(results)
        assert len(drivers) <= 5

    @given(results=st.lists(per_repo_result_st(), min_size=0, max_size=12))
    @settings(max_examples=50)
    def test_excludes_error_results(self, results):
        """Only non-error results appear in drivers."""
        drivers = get_top_risk_drivers(results)
        for d in drivers:
            # Each driver should correspond to a non-error input
            matching = [r for r in results if r.get("repo") == d["repo"] and r.get("error") is None]
            assert len(matching) >= 1

    @given(results=st.lists(per_repo_result_st(), min_size=0, max_size=12))
    @settings(max_examples=50)
    def test_required_fields(self, results):
        """Each driver has repo, risk_score, risk_label."""
        drivers = get_top_risk_drivers(results)
        for d in drivers:
            assert "repo" in d
            assert "risk_score" in d
            assert "risk_label" in d


# ---------------------------------------------------------------------------
# Endpoint property tests — require FastAPI TestClient and mocking
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app import app, SCOPE_STORE


# Strategy for valid scope names
scope_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 -_",
    min_size=1,
    max_size=30,
)

# Strategy for valid owner/repo strings (accepted by _normalize_repo_name)
valid_repo_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_.-]{0,7}/[a-zA-Z][a-zA-Z0-9_.-]{0,7}", fullmatch=True)


def _make_mock_graph():
    """Create a minimal Graph object with one node for mocking build_graph."""
    g = Graph(
        nodes=[Node(id="mock-node-1", type=NodeType.REPO, label="mock", metadata={}, provenance={})],
        edges=[],
    )
    return g


# ---------------------------------------------------------------------------
# Property 1: Scope creation round-trip
# **Validates: Requirements 1.1, 1.2, 3.1**
# ---------------------------------------------------------------------------
# Property 2: Scope ID uniqueness
# **Validates: Requirements 1.2**
# ---------------------------------------------------------------------------

class TestScopeEndpointRoundTripProperties:
    """Property 1 & 2: Scope creation round-trip and ID uniqueness."""

    @given(
        name=scope_name_st,
        repos=st.lists(valid_repo_st, min_size=1, max_size=3, unique=True),
    )
    @settings(max_examples=20)
    @patch("app.build_graph")
    @patch("app.score_repo")
    def test_scope_creation_round_trip(self, mock_score, mock_build, name, repos):
        """POST creates a scope, GET returns the same data.

        **Validates: Requirements 1.1, 3.1**
        """
        SCOPE_STORE.clear()
        mock_score.return_value = {"risk_score": 0.5}
        mock_build.return_value = _make_mock_graph()

        client = TestClient(app)
        post_resp = client.post("/api/ingest-scope", json={"name": name, "repos": repos})
        assert post_resp.status_code == 200, post_resp.text
        post_data = post_resp.json()
        scope_id = post_data["scope_id"]
        assert isinstance(scope_id, str) and len(scope_id) > 0

        get_resp = client.get(f"/api/scope/{scope_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()

        assert get_data["scope_id"] == scope_id
        assert get_data["name"] == name
        assert get_data["status"] in ("complete", "partial", "failed")

    @given(
        names=st.lists(scope_name_st, min_size=5, max_size=10),
    )
    @settings(max_examples=20)
    @patch("app.build_graph")
    @patch("app.score_repo")
    def test_scope_id_uniqueness(self, mock_score, mock_build, names):
        """Creating N scopes yields N distinct scope_ids.

        **Validates: Requirements 1.2**
        """
        SCOPE_STORE.clear()
        mock_score.return_value = {"risk_score": 0.5}
        mock_build.return_value = _make_mock_graph()

        client = TestClient(app)
        scope_ids = []
        for name in names:
            resp = client.post(
                "/api/ingest-scope",
                json={"name": name, "repos": ["owner/repo"]},
            )
            assert resp.status_code == 200
            scope_ids.append(resp.json()["scope_id"])

        assert len(scope_ids) == len(set(scope_ids)), "Scope IDs must be unique"


# ---------------------------------------------------------------------------
# Property 9: Oversized repo list rejection
# **Validates: Requirements 2.3**
# ---------------------------------------------------------------------------

class TestOversizedRepoListProperties:
    """Property 9: Oversized repo list rejection."""

    @given(
        repos=st.lists(valid_repo_st, min_size=11, max_size=20, unique=True),
    )
    @settings(max_examples=20)
    def test_oversized_repo_list_returns_422(self, repos):
        """POST with >10 repos returns 422.

        **Validates: Requirements 2.3**
        """
        SCOPE_STORE.clear()
        client = TestClient(app)
        resp = client.post(
            "/api/ingest-scope",
            json={"name": "test-scope", "repos": repos},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Property 10: Partial failure resilience
# **Validates: Requirements 2.5**
# ---------------------------------------------------------------------------

class TestPartialFailureResilienceProperties:
    """Property 10: Partial failure resilience."""

    @given(
        good_repos=st.lists(valid_repo_st, min_size=1, max_size=4, unique=True),
        bad_repos=st.lists(valid_repo_st, min_size=1, max_size=4, unique=True),
    )
    @settings(max_examples=20)
    @patch("app.build_graph")
    @patch("app.score_repo")
    def test_partial_failure_produces_valid_results(self, mock_score, mock_build, good_repos, bad_repos):
        """When some repos fail, status is 'partial' and errors are recorded.

        **Validates: Requirements 2.5**
        """
        # Ensure no overlap between good and bad repos
        bad_set = set(bad_repos)
        good_repos = [r for r in good_repos if r not in bad_set]
        assume(len(good_repos) >= 1)

        all_repos = good_repos + bad_repos
        SCOPE_STORE.clear()

        def side_effect_score(repo):
            if repo in bad_set:
                raise RuntimeError(f"Simulated failure for {repo}")
            return {"risk_score": 0.5}

        mock_score.side_effect = side_effect_score
        mock_build.return_value = _make_mock_graph()

        client = TestClient(app)
        resp = client.post(
            "/api/ingest-scope",
            json={"name": "partial-test", "repos": all_repos},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "partial"

        # Check per_repo_results in system_risk_summary
        per_repo = data["system_risk_summary"]["per_repo_results"]
        error_repos = [r["repo"] for r in per_repo if r.get("error") is not None]
        success_repos = [r["repo"] for r in per_repo if r.get("error") is None]

        assert len(error_repos) == len(bad_repos)
        assert len(success_repos) >= len(good_repos)
