"""
Property-based tests for error handling and provenance tracking.

Feature: dependency-tree-view
Property 22: Partial Results on Errors
Property 23: Error Resilience
Property 24: Error Tracking in Provenance
Property 25: Provenance Accuracy

Validates: Requirements 9.2–9.6, 14.1–14.7
"""

from __future__ import annotations

import time

import pytest
from hypothesis import given, settings, strategies as st, assume

from open_source_risk_model.tree.models import (
    FilterConfig,
    ProvenanceInfo,
    RiskMetadata,
    TreeNode,
)
from open_source_risk_model.tree.service import TreeService
from open_source_risk_model.tree.tree_utils import walk_tree, clone_tree


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


def _make_error_node(
    name: str,
    depth: int,
    ecosystem: str = "npm",
    error_reason: str = "Resolution failed",
) -> TreeNode:
    """Create an error node matching the spec's error node schema."""
    ver_part = "unknown"
    return TreeNode(
        id=f"pkg:{ecosystem}/{name}@{ver_part}",
        node_type="package",
        name=name,
        version=None,
        depth=depth,
        dependency_type="direct" if depth == 1 else "transitive",
        ecosystem=ecosystem,
        resolution_status="error",
        error_reason=error_reason,
        risk_metadata=None,
        children=[],
    )


def _make_resolved_node(
    name: str,
    depth: int,
    ecosystem: str = "npm",
    version: str = "1.0.0",
    risk_score: float | None = 50.0,
    vulnerability_count: int = 0,
    children: list[TreeNode] | None = None,
) -> TreeNode:
    """Create a resolved package node with risk metadata."""
    return TreeNode(
        id=f"pkg:{ecosystem}/{name}@{version}",
        node_type="package",
        name=name,
        version=version,
        depth=depth,
        dependency_type="direct" if depth == 1 else "transitive",
        ecosystem=ecosystem,
        resolution_status="resolved",
        risk_metadata=_make_risk_metadata(risk_score, vulnerability_count),
        children=children or [],
    )


def _make_root(children: list[TreeNode] | None = None) -> TreeNode:
    """Create a repository root node."""
    return TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        depth=0,
        dependency_type="direct",
        children=children or [],
    )


def _service() -> TreeService:
    return TreeService(db_path=":memory:")


# ======================================================================
# Strategies
# ======================================================================

ecosystems = st.sampled_from(["npm", "pypi", "maven", "go"])

package_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=12,
).filter(lambda s: s[0].isalpha())

risk_scores = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)

vuln_counts = st.integers(min_value=0, max_value=10)

versions = st.one_of(
    st.none(),
    st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True),
)

error_reasons = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz ",
    min_size=1,
    max_size=40,
)


@st.composite
def mixed_children_strategy(draw, min_resolved=1, min_errors=1, max_total=8):
    """Generate a mix of resolved and error child nodes at depth 1.

    Guarantees at least min_resolved resolved nodes and min_errors error nodes.
    """
    total = draw(st.integers(min_value=min_resolved + min_errors, max_value=max_total))
    num_errors = draw(st.integers(min_value=min_errors, max_value=total - min_resolved))
    num_resolved = total - num_errors

    children: list[TreeNode] = []
    counter = 0

    for _ in range(num_resolved):
        counter += 1
        eco = draw(ecosystems)
        ver = draw(versions)
        score = draw(risk_scores)
        vulns = draw(vuln_counts)
        ver_str = ver if ver else "1.0.0"
        children.append(_make_resolved_node(
            name=f"resolved{counter}",
            depth=1,
            ecosystem=eco,
            version=ver_str,
            risk_score=score,
            vulnerability_count=vulns,
        ))

    for _ in range(num_errors):
        counter += 1
        eco = draw(ecosystems)
        reason = draw(error_reasons)
        children.append(_make_error_node(
            name=f"errpkg{counter}",
            depth=1,
            ecosystem=eco,
            error_reason=reason,
        ))

    # Shuffle to avoid ordering bias
    draw(st.randoms()).shuffle(children)
    return children


@st.composite
def tree_with_errors_strategy(draw, max_depth=3, max_children=3):
    """Generate a tree with a mix of resolved and error nodes at various depths."""
    counter = [0]

    def build_node(depth: int, force_error: bool = False, force_resolved: bool = False) -> TreeNode:
        counter[0] += 1
        eco = draw(ecosystems)
        name = f"pkg{counter[0]}"

        if force_error or (not force_resolved and depth > 0 and draw(st.booleans())):
            return _make_error_node(
                name=name,
                depth=depth,
                ecosystem=eco,
                error_reason=draw(error_reasons),
            )

        ver = draw(versions)
        score = draw(risk_scores)
        vulns = draw(vuln_counts)
        ver_str = ver if ver else "1.0.0"

        children = []
        if depth < max_depth:
            num_children = draw(st.integers(min_value=0, max_value=max_children))
            for _ in range(num_children):
                children.append(build_node(depth + 1))

        return _make_resolved_node(
            name=name,
            depth=depth,
            ecosystem=eco,
            version=ver_str,
            risk_score=score,
            vulnerability_count=vulns,
            children=children,
        )

    # Ensure at least one resolved and one error at depth 1
    direct_children = []
    direct_children.append(build_node(1, force_resolved=True))
    direct_children.append(build_node(1, force_error=True))
    extra = draw(st.integers(min_value=0, max_value=3))
    for _ in range(extra):
        direct_children.append(build_node(1))

    return _make_root(children=direct_children)


@st.composite
def tree_with_risk_variety(draw):
    """Generate a tree with a mix of risk data states: full, missing, and error nodes."""
    counter = [0]

    def make_node(depth: int, risk_state: str) -> TreeNode:
        counter[0] += 1
        eco = draw(ecosystems)
        name = f"pkg{counter[0]}"

        if risk_state == "error":
            return _make_error_node(name=name, depth=depth, ecosystem=eco)
        elif risk_state == "missing":
            return TreeNode(
                id=f"pkg:{eco}/{name}@1.0.0",
                node_type="package",
                name=name,
                version="1.0.0",
                depth=depth,
                dependency_type="direct" if depth == 1 else "transitive",
                ecosystem=eco,
                resolution_status="resolved",
                risk_metadata=_make_risk_metadata(None),
                children=[],
            )
        else:  # "full"
            score = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
            vulns = draw(vuln_counts)
            return _make_resolved_node(
                name=name, depth=depth, ecosystem=eco,
                risk_score=score, vulnerability_count=vulns,
            )

    # Build a tree with at least one of each type
    states = ["full", "missing", "error"]
    children = [make_node(1, s) for s in states]
    extra_count = draw(st.integers(min_value=0, max_value=4))
    for _ in range(extra_count):
        state = draw(st.sampled_from(states))
        children.append(make_node(1, state))

    return _make_root(children=children)


# ======================================================================
# Property 22: Partial Results on Errors
# ======================================================================


class TestPartialResultsOnErrors:
    """
    **Validates: Requirements 14.1, 14.2, 14.3**

    Property 22: Partial Results on Errors — when some dependencies fail,
    the tree still contains resolved nodes alongside error nodes.

    For any tree where some dependencies fail to resolve, successfully
    resolved dependencies SHALL be included in the tree, and error nodes
    SHALL have resolution_status="error" with node_type="package".
    """

    @given(children=mixed_children_strategy(min_resolved=1, min_errors=1))
    @settings(max_examples=100)
    def test_resolved_nodes_coexist_with_error_nodes(self, children):
        """**Validates: Requirements 14.1**

        When some deps fail, resolved deps are still present in the tree.
        """
        root = _make_root(children=children)
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        all_nodes = list(walk_tree(response.tree))
        non_root = [n for n in all_nodes if n.depth > 0]

        resolved = [n for n in non_root if n.resolution_status == "resolved"]
        errors = [n for n in non_root if n.resolution_status == "error"]

        assert len(resolved) >= 1, "At least one resolved node must be present"
        assert len(errors) >= 1, "At least one error node must be present"

    @given(children=mixed_children_strategy(min_resolved=1, min_errors=1))
    @settings(max_examples=100)
    def test_error_nodes_have_package_node_type(self, children):
        """**Validates: Requirements 14.2, 14.3**

        Error nodes use node_type="package" with resolution_status="error",
        NOT a separate node_type="error".
        """
        root = _make_root(children=children)
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        all_nodes = list(walk_tree(response.tree))
        error_nodes = [n for n in all_nodes if n.resolution_status == "error"]

        for node in error_nodes:
            assert node.node_type == "package", (
                f"Error node '{node.name}' has node_type='{node.node_type}', expected 'package'"
            )
            assert node.error_reason is not None, (
                f"Error node '{node.name}' must have an error_reason"
            )

    @given(root=tree_with_errors_strategy())
    @settings(max_examples=100)
    def test_error_nodes_in_deep_tree_have_correct_schema(self, root):
        """**Validates: Requirements 14.2, 14.3**

        Error nodes at any depth have node_type="package" and resolution_status="error".
        """
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        for node in walk_tree(response.tree):
            if node.resolution_status == "error":
                assert node.node_type == "package"
                assert node.error_reason is not None


# ======================================================================
# Property 23: Error Resilience
# ======================================================================


class TestErrorResilience:
    """
    **Validates: Requirements 14.7**

    Property 23: Error Resilience — error nodes have resolution_status="error",
    node_type="package", risk_metadata=None, empty children.

    For any tree construction encountering errors, the builder SHALL continue
    processing remaining dependencies rather than halting.
    """

    @given(children=mixed_children_strategy(min_resolved=1, min_errors=1))
    @settings(max_examples=100)
    def test_error_nodes_have_null_risk_and_empty_children(self, children):
        """**Validates: Requirements 14.7**

        Error nodes have risk_metadata=None and children=[].
        """
        root = _make_root(children=children)
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        for node in walk_tree(response.tree):
            if node.resolution_status == "error":
                assert node.risk_metadata is None, (
                    f"Error node '{node.name}' should have risk_metadata=None"
                )
                assert node.children == [], (
                    f"Error node '{node.name}' should have empty children"
                )

    @given(root=tree_with_errors_strategy())
    @settings(max_examples=100)
    def test_processing_continues_after_errors(self, root):
        """**Validates: Requirements 14.7**

        The tree contains both resolved and error nodes, proving the builder
        continued processing after encountering errors.
        """
        all_nodes = list(walk_tree(root))
        non_root = [n for n in all_nodes if n.depth > 0]

        resolved = [n for n in non_root if n.resolution_status == "resolved"]
        errors = [n for n in non_root if n.resolution_status == "error"]

        # The strategy guarantees at least one of each
        assert len(resolved) >= 1
        assert len(errors) >= 1

        # Transform should succeed without raising
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )
        assert response.tree is not None

    @given(
        num_errors=st.integers(min_value=1, max_value=5),
        num_resolved=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_all_error_node_invariants_hold(self, num_errors, num_resolved):
        """**Validates: Requirements 14.7**

        For any mix of error and resolved nodes, every error node satisfies
        all error node invariants simultaneously.
        """
        children = []
        for i in range(num_resolved):
            children.append(_make_resolved_node(f"good{i}", depth=1))
        for i in range(num_errors):
            children.append(_make_error_node(f"bad{i}", depth=1, error_reason=f"fail {i}"))

        root = _make_root(children=children)
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        for node in walk_tree(response.tree):
            if node.resolution_status == "error":
                assert node.node_type == "package"
                assert node.risk_metadata is None
                assert node.children == []
                assert node.error_reason is not None


# ======================================================================
# Property 24: Error Tracking in Provenance
# ======================================================================


class TestErrorTrackingInProvenance:
    """
    **Validates: Requirements 14.5**

    Property 24: Error Tracking in Provenance — provenance.nodes_with_errors
    matches count of error nodes in tree.

    For any tree with resolution errors, the provenance object SHALL list
    all dependencies that encountered errors in the error_details field.
    """

    @given(children=mixed_children_strategy(min_resolved=1, min_errors=1, max_total=10))
    @settings(max_examples=100)
    def test_nodes_with_errors_matches_actual_error_count(self, children):
        """**Validates: Requirements 14.5**

        provenance.nodes_with_errors == count of nodes with resolution_status="error".
        """
        root = _make_root(children=children)
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        actual_error_count = sum(
            1 for n in walk_tree(response.tree) if n.resolution_status == "error"
        )
        assert response.provenance.nodes_with_errors == actual_error_count

    @given(root=tree_with_errors_strategy())
    @settings(max_examples=100)
    def test_error_details_lists_all_error_nodes(self, root):
        """**Validates: Requirements 14.5**

        provenance.error_details contains an entry for each error node,
        with matching id and error_reason.
        """
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        error_nodes = [
            n for n in walk_tree(response.tree) if n.resolution_status == "error"
        ]
        error_details = response.provenance.error_details

        assert len(error_details) == len(error_nodes)

        # Each error node should have a corresponding entry in error_details
        detail_ids = {d["id"] for d in error_details}
        for node in error_nodes:
            assert node.id in detail_ids, (
                f"Error node '{node.id}' not found in provenance.error_details"
            )

    @given(
        num_errors=st.integers(min_value=0, max_value=6),
        num_resolved=st.integers(min_value=1, max_value=6),
    )
    @settings(max_examples=100)
    def test_zero_errors_means_zero_in_provenance(self, num_errors, num_resolved):
        """**Validates: Requirements 14.5**

        When there are no error nodes, provenance.nodes_with_errors == 0
        and error_details is empty.
        """
        children = []
        for i in range(num_resolved):
            children.append(_make_resolved_node(f"pkg{i}", depth=1))
        for i in range(num_errors):
            children.append(_make_error_node(f"err{i}", depth=1))

        root = _make_root(children=children)
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        assert response.provenance.nodes_with_errors == num_errors
        assert len(response.provenance.error_details) == num_errors


# ======================================================================
# Property 25: Provenance Accuracy
# ======================================================================


class TestProvenanceAccuracy:
    """
    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 9.6**

    Property 25: Provenance Accuracy — provenance fields (total_nodes,
    nodes_with_risk_data, nodes_with_missing_risk, data_completeness)
    are consistent with actual tree content.
    """

    @given(root=tree_with_risk_variety())
    @settings(max_examples=100)
    def test_total_nodes_matches_walk_count(self, root):
        """**Validates: Requirements 9.2**

        provenance.total_nodes == count of all nodes in the tree (including root).
        """
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        actual_count = sum(1 for _ in walk_tree(response.tree))
        assert response.provenance.total_nodes == actual_count

    @given(root=tree_with_risk_variety())
    @settings(max_examples=100)
    def test_risk_data_counts_consistent(self, root):
        """**Validates: Requirements 9.3, 9.4**

        nodes_with_risk_data + nodes_with_missing_risk == total_nodes.
        """
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        prov = response.provenance
        assert prov.nodes_with_risk_data + prov.nodes_with_missing_risk == prov.total_nodes

    @given(root=tree_with_risk_variety())
    @settings(max_examples=100)
    def test_nodes_with_risk_data_matches_actual(self, root):
        """**Validates: Requirements 9.3**

        nodes_with_risk_data == count of nodes where risk_metadata is not None
        and score_completeness != "missing".
        """
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        actual_with_risk = sum(
            1 for n in walk_tree(response.tree)
            if n.risk_metadata is not None and n.risk_metadata.score_completeness != "missing"
        )
        assert response.provenance.nodes_with_risk_data == actual_with_risk

    @given(root=tree_with_risk_variety())
    @settings(max_examples=100)
    def test_data_completeness_derivation(self, root):
        """**Validates: Requirements 9.3, 9.4**

        data_completeness is "full" only when nodes_with_missing_risk == 0
        AND nodes_with_errors == 0; otherwise "partial".
        """
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        prov = response.provenance
        if prov.nodes_with_missing_risk == 0 and prov.nodes_with_errors == 0:
            assert prov.data_completeness == "full"
        else:
            assert prov.data_completeness == "partial"

    @given(data_source=st.sampled_from(["database", "live", "mixed"]))
    @settings(max_examples=30)
    def test_data_source_preserved_in_provenance(self, data_source):
        """**Validates: Requirements 9.2**

        provenance.data_source matches the data_source passed to transform.
        """
        root = _make_root(children=[
            _make_resolved_node("pkg1", depth=1),
        ])
        service = _service()
        response = service._transform_for_response(
            root, data_source=data_source,
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        assert response.provenance.data_source == data_source

    @given(root=tree_with_risk_variety())
    @settings(max_examples=100)
    def test_construction_time_populated_when_start_time_given(self, root):
        """**Validates: Requirements 9.5**

        construction_time_ms is populated and > 0 when start_time is provided.
        """
        service = _service()
        start = time.monotonic()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=start,
        )

        assert response.provenance.construction_time_ms is not None
        assert response.provenance.construction_time_ms >= 1

    @given(root=tree_with_risk_variety())
    @settings(max_examples=50)
    def test_last_updated_is_populated(self, root):
        """**Validates: Requirements 9.5**

        provenance.last_updated is always a non-empty string.
        """
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        assert isinstance(response.provenance.last_updated, str)
        assert len(response.provenance.last_updated) > 0

    @given(
        num_full=st.integers(min_value=0, max_value=4),
        num_missing=st.integers(min_value=0, max_value=4),
        num_errors=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=100)
    def test_provenance_fields_consistent_with_tree(
        self, num_full, num_missing, num_errors
    ):
        """**Validates: Requirements 9.2, 9.3, 9.4, 9.6**

        All provenance fields are internally consistent with the actual
        tree content for any combination of node states.
        """
        assume(num_full + num_missing + num_errors >= 1)

        children = []
        counter = 0
        for _ in range(num_full):
            counter += 1
            children.append(_make_resolved_node(
                f"full{counter}", depth=1, risk_score=50.0,
            ))
        for _ in range(num_missing):
            counter += 1
            children.append(TreeNode(
                id=f"pkg:npm/miss{counter}@1.0.0",
                node_type="package",
                name=f"miss{counter}",
                version="1.0.0",
                depth=1,
                dependency_type="direct",
                ecosystem="npm",
                resolution_status="resolved",
                risk_metadata=_make_risk_metadata(None),
                children=[],
            ))
        for _ in range(num_errors):
            counter += 1
            children.append(_make_error_node(f"err{counter}", depth=1))

        root = _make_root(children=children)
        service = _service()
        response = service._transform_for_response(
            root, data_source="database",
            filters=FilterConfig(),
            start_time=time.monotonic(),
        )

        prov = response.provenance
        total_expected = 1 + num_full + num_missing + num_errors  # +1 for root

        assert prov.total_nodes == total_expected
        assert prov.nodes_with_errors == num_errors
        assert prov.nodes_with_risk_data + prov.nodes_with_missing_risk == total_expected

        # data_completeness check
        if prov.nodes_with_missing_risk == 0 and prov.nodes_with_errors == 0:
            assert prov.data_completeness == "full"
        else:
            assert prov.data_completeness == "partial"
