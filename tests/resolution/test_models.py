"""Tests for resolution data models."""
import pytest

from open_source_risk_model.resolution.models import (
    RESOLUTION_STATUSES,
    PackageIdentity,
    make_node_key,
    DependencyDeclaration,
    ResolutionEdge,
    ResolutionSummary,
)


class TestPackageIdentity:
    def test_frozen_and_hashable(self):
        """PackageIdentity is frozen and usable in sets."""
        p1 = PackageIdentity(ecosystem="pypi", name="requests")
        p2 = PackageIdentity(ecosystem="pypi", name="flask")
        s = {p1, p2}
        assert len(s) == 2
        assert p1 in s

    def test_frozen_rejects_mutation(self):
        p = PackageIdentity(ecosystem="pypi", name="requests")
        with pytest.raises(AttributeError):
            p.name = "other"

    def test_equality_same(self):
        """Same ecosystem+name → equal."""
        a = PackageIdentity(ecosystem="pypi", name="requests")
        b = PackageIdentity(ecosystem="pypi", name="requests")
        assert a == b

    def test_equality_different_ecosystem(self):
        """Different ecosystem → not equal."""
        a = PackageIdentity(ecosystem="pypi", name="debug")
        b = PackageIdentity(ecosystem="npm", name="debug")
        assert a != b


class TestMakeNodeKey:
    def test_basic(self):
        """make_node_key returns (ecosystem, name) — version ignored in MVP."""
        assert make_node_key("pypi", "requests") == ("pypi", "requests")

    def test_version_ignored(self):
        """Version parameter is ignored in MVP."""
        assert make_node_key("pypi", "requests", "2.31.0") == ("pypi", "requests")

    def test_none_ecosystem_for_repo(self):
        """Works for repo-as-parent with None ecosystem."""
        assert make_node_key(None, "owner/repo") == (None, "owner/repo")


class TestResolutionStatuses:
    def test_contains_exactly_six_values(self):
        expected = {
            "resolved",
            "error",
            "cycle_detected",
            "max_depth_reached",
            "unsupported_ecosystem",
            "budget_exhausted",
        }
        assert RESOLUTION_STATUSES == expected
        assert len(RESOLUTION_STATUSES) == 6


class TestResolutionEdge:
    def test_defaults(self):
        """ResolutionEdge has correct default values."""
        edge = ResolutionEdge(
            repo_full_name="owner/repo",
            parent_ecosystem=None,
            parent_package="owner/repo",
            child_ecosystem="pypi",
            child_package="requests",
            declared_specifier=">=2.0",
            resolved_version="2.31.0",
            depth=1,
        )
        assert edge.resolution_status == "resolved"
        assert edge.error_reason is None
        assert edge.source_registry is None


class TestResolutionSummary:
    def _make_edge(self, status="resolved", depth=1):
        return ResolutionEdge(
            repo_full_name="owner/repo",
            parent_ecosystem=None,
            parent_package="owner/repo",
            child_ecosystem="pypi",
            child_package="pkg",
            declared_specifier=None,
            resolved_version="1.0.0" if status == "resolved" else None,
            depth=depth,
            resolution_status=status,
        )

    def test_from_edges_counts_statuses(self):
        """from_edges correctly counts each status type."""
        edges = [
            self._make_edge("resolved"),
            self._make_edge("resolved"),
            self._make_edge("error"),
            self._make_edge("cycle_detected"),
            self._make_edge("max_depth_reached"),
            self._make_edge("unsupported_ecosystem"),
            self._make_edge("budget_exhausted"),
        ]
        summary = ResolutionSummary.from_edges("owner/repo", edges, 5, 2, 1.5)
        assert summary.total_edges == 7
        assert summary.resolved_count == 2
        assert summary.error_count == 1
        assert summary.cycle_count == 1
        assert summary.max_depth_reached_count == 1
        assert summary.unsupported_ecosystem_count == 1
        assert summary.budget_exhausted_count == 1
        assert summary.api_calls_made == 5
        assert summary.cache_hits == 2
        assert summary.elapsed_seconds == 1.5

    def test_from_edges_actual_max_depth(self):
        """from_edges computes actual_max_depth from edge depths."""
        edges = [
            self._make_edge("resolved", depth=1),
            self._make_edge("resolved", depth=3),
            self._make_edge("resolved", depth=2),
        ]
        summary = ResolutionSummary.from_edges("owner/repo", edges, 0, 0, 0.0)
        assert summary.actual_max_depth == 3

    def test_from_edges_edges_per_depth(self):
        """from_edges populates edges_per_depth histogram correctly."""
        edges = [
            self._make_edge("resolved", depth=1),
            self._make_edge("resolved", depth=1),
            self._make_edge("error", depth=2),
            self._make_edge("resolved", depth=3),
        ]
        summary = ResolutionSummary.from_edges("owner/repo", edges, 0, 0, 0.0)
        assert summary.edges_per_depth == {1: 2, 2: 1, 3: 1}

    def test_from_edges_empty(self):
        """from_edges with empty edge list returns zero counts and empty histogram."""
        summary = ResolutionSummary.from_edges("owner/repo", [], 0, 0, 0.0)
        assert summary.total_edges == 0
        assert summary.resolved_count == 0
        assert summary.error_count == 0
        assert summary.cycle_count == 0
        assert summary.max_depth_reached_count == 0
        assert summary.unsupported_ecosystem_count == 0
        assert summary.budget_exhausted_count == 0
        assert summary.actual_max_depth == 0
        assert summary.edges_per_depth == {}
