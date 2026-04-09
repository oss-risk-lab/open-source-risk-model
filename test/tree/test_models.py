"""Unit tests for dependency tree data models."""

import json

import pytest

from open_source_risk_model.tree.models import (
    DependencyTreeResponse,
    FilterConfig,
    ProvenanceInfo,
    RiskMetadata,
    SummaryMetrics,
    TreeNode,
)


class TestTreeNodeDefaults:
    """Test dataclass construction with defaults."""

    def test_tree_node_defaults(self):
        node = TreeNode()
        assert node.id == ""
        assert node.node_type == "package"
        assert node.name == ""
        assert node.version is None
        assert node.depth == 0
        assert node.children == []
        assert node.children_truncated is False
        assert node.child_count is None
        assert node.dependency_type == "direct"
        assert node.ecosystem is None
        assert node.specifier is None
        assert node.risk_metadata is None
        assert node.resolution_status == "resolved"
        assert node.error_reason is None

    def test_risk_metadata_defaults(self):
        rm = RiskMetadata()
        assert rm.risk_score is None
        assert rm.risk_level is None
        assert rm.vulnerability_count == 0
        assert rm.release_recency_days is None
        assert rm.maintainer_count is None
        assert rm.score_source == "unavailable"
        assert rm.score_completeness == "missing"

    def test_summary_metrics_defaults(self):
        sm = SummaryMetrics()
        assert sm.total_dependencies == 0
        assert sm.filters_applied == []

    def test_provenance_defaults(self):
        p = ProvenanceInfo()
        assert p.data_source == "database"
        assert p.data_completeness == "full"
        assert p.error_details == []
        assert p.live_fetched_nodes == []
        assert p.construction_time_ms is None

    def test_filter_config_defaults(self):
        fc = FilterConfig()
        assert fc.max_depth is None
        assert fc.high_risk_only is False
        assert fc.vulnerable_only is False
        assert fc.direct_only is False


class TestNestedTreeSerialization:
    """Test nested tree serialization (root → children → grandchildren)."""

    def _build_sample_tree(self):
        grandchild = TreeNode(
            id="pkg:npm/qs@6.11.0",
            node_type="package",
            name="qs",
            version="6.11.0",
            depth=2,
            dependency_type="transitive",
            ecosystem="npm",
            risk_metadata=RiskMetadata(
                risk_score=25.0,
                risk_level="low",
                vulnerability_count=0,
                score_source="repo_graph",
                score_completeness="full",
            ),
        )
        child = TreeNode(
            id="pkg:npm/express@4.18.0",
            node_type="package",
            name="express",
            version="4.18.0",
            depth=1,
            dependency_type="direct",
            ecosystem="npm",
            children=[grandchild],
            risk_metadata=RiskMetadata(
                risk_score=45.0,
                risk_level="medium",
                vulnerability_count=2,
                release_recency_days=180,
                maintainer_count=5,
                score_source="repo_graph",
                score_completeness="full",
            ),
        )
        root = TreeNode(
            id="owner/repo",
            node_type="repository",
            name="owner/repo",
            version=None,
            depth=0,
            dependency_type="direct",
            children=[child],
        )
        return root

    def test_nested_serialization_structure(self):
        root = self._build_sample_tree()
        d = root.to_dict()

        assert d["id"] == "owner/repo"
        assert d["node_type"] == "repository"
        assert d["depth"] == 0
        assert len(d["children"]) == 1

        child_d = d["children"][0]
        assert child_d["id"] == "pkg:npm/express@4.18.0"
        assert child_d["name"] == "express"
        assert child_d["version"] == "4.18.0"
        assert child_d["depth"] == 1
        assert len(child_d["children"]) == 1

        grandchild_d = child_d["children"][0]
        assert grandchild_d["id"] == "pkg:npm/qs@6.11.0"
        assert grandchild_d["depth"] == 2
        assert grandchild_d["dependency_type"] == "transitive"

    def test_risk_metadata_serialized(self):
        root = self._build_sample_tree()
        d = root.to_dict()
        child_d = d["children"][0]

        rm = child_d["risk_metadata"]
        assert rm["risk_score"] == 45.0
        assert rm["risk_level"] == "medium"
        assert rm["vulnerability_count"] == 2
        assert rm["release_recency_days"] == 180
        assert rm["maintainer_count"] == 5
        assert rm["score_source"] == "repo_graph"
        assert rm["score_completeness"] == "full"

    def test_json_serializable(self):
        root = self._build_sample_tree()
        d = root.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["id"] == "owner/repo"


class TestErrorNodeSerialization:
    """Test error node serialization."""

    def test_error_node_includes_status_and_reason(self):
        node = TreeNode(
            id="pkg:npm/foo@unknown",
            node_type="package",
            name="foo",
            version=None,
            depth=1,
            dependency_type="direct",
            ecosystem="npm",
            resolution_status="error",
            error_reason="Manifest fetch failed",
        )
        d = node.to_dict()

        assert d["node_type"] == "package"
        assert d["resolution_status"] == "error"
        assert d["error_reason"] == "Manifest fetch failed"
        assert d["version"] is None  # version always included
        assert "risk_metadata" not in d  # None risk_metadata omitted

    def test_resolved_node_omits_resolution_status(self):
        node = TreeNode(
            id="pkg:npm/lodash@4.17.21",
            node_type="package",
            name="lodash",
            version="4.17.21",
            resolution_status="resolved",
        )
        d = node.to_dict()
        assert "resolution_status" not in d
        assert "error_reason" not in d


class TestNoneFieldOmission:
    """Test omission of None optional fields."""

    def test_none_ecosystem_omitted(self):
        node = TreeNode(id="test", name="test", ecosystem=None)
        d = node.to_dict()
        assert "ecosystem" not in d

    def test_none_specifier_omitted(self):
        node = TreeNode(id="test", name="test", specifier=None)
        d = node.to_dict()
        assert "specifier" not in d

    def test_none_risk_metadata_omitted(self):
        node = TreeNode(id="test", name="test", risk_metadata=None)
        d = node.to_dict()
        assert "risk_metadata" not in d

    def test_none_child_count_omitted(self):
        node = TreeNode(id="test", name="test", child_count=None)
        d = node.to_dict()
        assert "child_count" not in d

    def test_false_children_truncated_omitted(self):
        node = TreeNode(id="test", name="test", children_truncated=False)
        d = node.to_dict()
        assert "children_truncated" not in d

    def test_version_always_included_even_when_none(self):
        node = TreeNode(id="test", name="test", version=None)
        d = node.to_dict()
        assert "version" in d
        assert d["version"] is None

    def test_risk_metadata_none_optional_fields_omitted(self):
        rm = RiskMetadata(
            risk_score=50.0,
            risk_level="medium",
            vulnerability_count=1,
            release_recency_days=None,
            maintainer_count=None,
            score_source="repo_graph",
            score_completeness="partial",
        )
        d = rm.to_dict()
        assert "release_recency_days" not in d
        assert "maintainer_count" not in d
        assert d["risk_score"] == 50.0


class TestCanonicalFieldNames:
    """Test stable JSON field names match Canonical Field Names table."""

    def test_tree_node_field_names(self):
        node = TreeNode(
            id="pkg:npm/lodash@4.17.21",
            node_type="package",
            name="lodash",
            version="4.17.21",
            depth=1,
            dependency_type="direct",
            ecosystem="npm",
            children_truncated=True,
            child_count=5,
            specifier="^4.0.0",
            risk_metadata=RiskMetadata(
                risk_score=45.0,
                risk_level="medium",
                vulnerability_count=2,
                score_source="repo_graph",
                score_completeness="full",
            ),
        )
        d = node.to_dict()

        # Canonical field names from the spec
        assert "id" in d
        assert "node_type" in d
        assert "name" in d
        assert "version" in d
        assert "depth" in d
        assert "children" in d
        assert "children_truncated" in d
        assert "child_count" in d
        assert "dependency_type" in d
        assert "ecosystem" in d
        assert "specifier" in d
        assert "risk_metadata" in d

        # Risk metadata canonical fields
        rm = d["risk_metadata"]
        assert "risk_score" in rm
        assert "risk_level" in rm
        assert "vulnerability_count" in rm
        assert "score_source" in rm
        assert "score_completeness" in rm

        # Ensure no synonyms are used
        assert "registry_type" not in d
        assert "dependency_kind" not in d

    def test_provenance_field_names(self):
        p = ProvenanceInfo(
            data_source="database",
            data_completeness="full",
            last_updated="2024-01-15T10:30:00Z",
            total_nodes=10,
            construction_time_ms=245,
        )
        d = p.to_dict()
        assert "data_source" in d
        assert "data_completeness" in d
        assert "last_updated" in d
        assert "total_nodes" in d
        assert "nodes_with_risk_data" in d
        assert "nodes_with_missing_risk" in d
        assert "nodes_with_errors" in d
        assert "error_details" in d
        assert "live_fetched_nodes" in d
        assert "construction_time_ms" in d


class TestCanonicalIdFormat:
    """Test canonical ID format."""

    def test_canonical_id_with_version(self):
        node = TreeNode(
            id="pkg:npm/lodash@4.17.21",
            name="lodash",
            version="4.17.21",
            ecosystem="npm",
        )
        assert node.id == "pkg:npm/lodash@4.17.21"

    def test_canonical_id_with_unknown_version(self):
        node = TreeNode(
            id="pkg:npm/lodash@unknown",
            name="lodash",
            version=None,
            ecosystem="npm",
        )
        assert node.id == "pkg:npm/lodash@unknown"

    def test_canonical_id_pypi(self):
        node = TreeNode(
            id="pkg:pypi/requests@2.31.0",
            name="requests",
            version="2.31.0",
            ecosystem="pypi",
        )
        assert node.id == "pkg:pypi/requests@2.31.0"

    def test_canonical_id_maven(self):
        node = TreeNode(
            id="pkg:maven/com.google.guava@31.1",
            name="com.google.guava",
            version="31.1",
            ecosystem="maven",
        )
        assert node.id == "pkg:maven/com.google.guava@31.1"


class TestDependencyTreeResponseSerialization:
    """Test DependencyTreeResponse serialization."""

    def test_full_response_serialization(self):
        root = TreeNode(
            id="owner/repo",
            node_type="repository",
            name="owner/repo",
            depth=0,
        )
        metrics = SummaryMetrics(
            total_dependencies=5,
            direct_dependencies=3,
            transitive_dependencies=2,
            filters_applied=["high_risk_only"],
        )
        prov = ProvenanceInfo(
            data_source="database",
            data_completeness="full",
            last_updated="2024-01-15T10:30:00Z",
        )
        resp = DependencyTreeResponse(
            repo="owner/repo",
            tree=root,
            summary_metrics=metrics,
            provenance=prov,
        )
        d = resp.to_dict()

        assert d["repo"] == "owner/repo"
        assert "tree" in d
        assert "summary_metrics" in d
        assert "provenance" in d
        assert d["summary_metrics"]["filters_applied"] == ["high_risk_only"]

    def test_json_serializable(self):
        resp = DependencyTreeResponse(
            repo="test/repo",
            tree=TreeNode(id="test/repo", node_type="repository", name="test/repo"),
            summary_metrics=SummaryMetrics(),
            provenance=ProvenanceInfo(last_updated="2024-01-01T00:00:00Z"),
        )
        json_str = json.dumps(resp.to_dict())
        parsed = json.loads(json_str)
        assert parsed["repo"] == "test/repo"
