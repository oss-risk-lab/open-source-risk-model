"""
Property-based tests for API Response Structure Completeness.

Feature: dependency-tree-view
Property 9: API Response Structure Completeness — for any valid tree,
the API response contains all required top-level fields (repo, tree,
summary_metrics, provenance), tree nodes have canonical field names,
and the response is valid JSON.

Validates: Requirements 4.2, 4.4, 4.5, 9.1
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st, assume

from open_source_risk_model.tree.models import (
    DependencyTreeResponse,
    FilterConfig,
    ProvenanceInfo,
    RiskMetadata,
    SummaryMetrics,
    TreeNode,
)
from open_source_risk_model.tree.service import TreeService
from open_source_risk_model.tree.tree_utils import walk_tree


# ======================================================================
# Helpers
# ======================================================================


def _classify(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 30:
        return "low"
    if score <= 70:
        return "medium"
    return "high"


def _make_risk_metadata(
    risk_score: float | None,
    vulnerability_count: int = 0,
) -> RiskMetadata:
    return RiskMetadata(
        risk_score=risk_score,
        risk_level=_classify(risk_score),
        vulnerability_count=vulnerability_count,
        score_source="repo_graph" if risk_score is not None else "unavailable",
        score_completeness="full" if risk_score is not None else "missing",
    )


def _service() -> TreeService:
    return TreeService(db_path=":memory:")


# ======================================================================
# Strategies
# ======================================================================

risk_scores = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)

ecosystems = st.sampled_from(["npm", "pypi", "maven", "go"])

vuln_counts = st.integers(min_value=0, max_value=10)

versions = st.one_of(
    st.none(),
    st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True),
)


@st.composite
def tree_strategy(draw, max_depth=3, max_children=4):
    """Generate a random dependency tree with a repository root."""
    counter = [0]

    def build_node(depth: int) -> TreeNode:
        counter[0] += 1
        name = f"pkg{counter[0]}"
        eco = draw(ecosystems)
        ver = draw(versions)
        score = draw(risk_scores)
        vulns = draw(vuln_counts)

        dep_type = "direct" if depth == 1 else "transitive"
        ver_part = ver if ver else "unknown"

        children = []
        if depth < max_depth:
            num_children = draw(st.integers(min_value=0, max_value=max_children))
            for _ in range(num_children):
                children.append(build_node(depth + 1))

        return TreeNode(
            id=f"pkg:{eco}/{name}@{ver_part}",
            node_type="package",
            name=name,
            version=ver,
            depth=depth,
            dependency_type=dep_type,
            ecosystem=eco,
            risk_metadata=_make_risk_metadata(score, vulns),
            children=children,
        )

    num_direct = draw(st.integers(min_value=0, max_value=5))
    direct_children = [build_node(1) for _ in range(num_direct)]

    root = TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        depth=0,
        dependency_type="direct",
        children=direct_children,
    )
    return root


# ======================================================================
# Canonical field name sets
# ======================================================================

# Required top-level keys in the serialized response
REQUIRED_RESPONSE_KEYS = {"repo", "tree", "summary_metrics", "provenance"}

# Required keys on every serialized tree node
REQUIRED_NODE_KEYS = {"id", "node_type", "name", "version", "depth", "children", "dependency_type"}

# Required keys on summary_metrics
REQUIRED_METRICS_KEYS = {
    "total_dependencies",
    "direct_dependencies",
    "transitive_dependencies",
    "high_risk_count",
    "vulnerable_count",
    "max_depth",
    "filters_applied",
}

# Required keys on provenance
REQUIRED_PROVENANCE_KEYS = {
    "data_source",
    "data_completeness",
    "last_updated",
    "total_nodes",
    "nodes_with_risk_data",
    "nodes_with_missing_risk",
    "nodes_with_errors",
    "error_details",
    "live_fetched_nodes",
}


# ======================================================================
# Property 9: API Response Structure Completeness
# ======================================================================


@pytest.mark.property_test
class TestAPIResponseStructureCompleteness:
    """
    **Validates: Requirements 4.2, 4.4, 4.5, 9.1**

    For any valid tree, the API response contains all required top-level
    fields (repo, tree, summary_metrics, provenance), tree nodes have
    canonical field names, and the response is valid JSON.
    """

    @given(root=tree_strategy())
    @settings(max_examples=100, deadline=None)
    def test_response_has_all_required_top_level_fields(self, root: TreeNode):
        """to_dict() on a DependencyTreeResponse always includes repo, tree,
        summary_metrics, and provenance."""
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        d = response.to_dict()
        assert REQUIRED_RESPONSE_KEYS.issubset(d.keys()), (
            f"Missing top-level keys: {REQUIRED_RESPONSE_KEYS - d.keys()}"
        )

    @given(root=tree_strategy())
    @settings(max_examples=100, deadline=None)
    def test_response_serializes_to_valid_json(self, root: TreeNode):
        """The serialized response is valid JSON (round-trips through
        json.dumps / json.loads without error)."""
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        d = response.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert REQUIRED_RESPONSE_KEYS.issubset(parsed.keys())

    @given(root=tree_strategy())
    @settings(max_examples=100, deadline=None)
    def test_tree_nodes_have_canonical_field_names(self, root: TreeNode):
        """Every node in the serialized tree contains the canonical field
        names defined in the design document."""
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        d = response.to_dict()
        tree_dict = d["tree"]

        # Walk the serialized tree and check each node
        stack = [tree_dict]
        while stack:
            node = stack.pop()
            missing = REQUIRED_NODE_KEYS - node.keys()
            assert not missing, (
                f"Node '{node.get('name', '?')}' missing canonical keys: {missing}"
            )
            for child in node.get("children", []):
                stack.append(child)

    @given(root=tree_strategy())
    @settings(max_examples=100, deadline=None)
    def test_summary_metrics_has_required_fields(self, root: TreeNode):
        """The summary_metrics object contains all required fields."""
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        d = response.to_dict()
        metrics = d["summary_metrics"]
        missing = REQUIRED_METRICS_KEYS - metrics.keys()
        assert not missing, f"summary_metrics missing keys: {missing}"

    @given(root=tree_strategy())
    @settings(max_examples=100, deadline=None)
    def test_provenance_has_required_fields(self, root: TreeNode):
        """The provenance object contains all required fields."""
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        d = response.to_dict()
        provenance = d["provenance"]
        missing = REQUIRED_PROVENANCE_KEYS - provenance.keys()
        assert not missing, f"provenance missing keys: {missing}"

    @given(root=tree_strategy())
    @settings(max_examples=100, deadline=None)
    def test_no_forbidden_field_synonyms_in_nodes(self, root: TreeNode):
        """Nodes must not contain forbidden synonyms like 'registry_type',
        'dependency_kind', or 'maintainer_health'."""
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        forbidden = {"registry_type", "dependency_kind", "maintainer_health"}
        d = response.to_dict()

        stack = [d["tree"]]
        while stack:
            node = stack.pop()
            found = forbidden & node.keys()
            assert not found, (
                f"Node '{node.get('name', '?')}' has forbidden synonyms: {found}"
            )
            for child in node.get("children", []):
                stack.append(child)

    @given(root=tree_strategy())
    @settings(max_examples=100, deadline=None)
    def test_repo_field_matches_tree_root_id(self, root: TreeNode):
        """The top-level 'repo' field matches the tree root's id."""
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        d = response.to_dict()
        assert d["repo"] == d["tree"]["id"]

    def test_zero_dependency_tree_has_complete_structure(self):
        """A tree with zero dependencies still has all required fields."""
        root = TreeNode(
            id="owner/repo",
            node_type="repository",
            name="owner/repo",
            depth=0,
            dependency_type="direct",
            children=[],
        )
        svc = _service()
        filters = FilterConfig()
        response = svc._transform_for_response(
            canonical_tree=root,
            data_source="database",
            filters=filters,
        )

        d = response.to_dict()
        assert REQUIRED_RESPONSE_KEYS.issubset(d.keys())
        assert d["tree"]["children"] == []
        assert d["summary_metrics"]["total_dependencies"] == 0
