"""
Unit tests for scope propagation helpers: SCOPE_PRIORITY, CONFIDENCE_PRIORITY,
resolve_scope(), and aggregate_node_scope().

Validates: Requirements 2.1, 2.2, 2.3
"""

import pytest

from src.open_source_risk_model.dependencies.scope_classifier import (
    CONFIDENCE_PRIORITY,
    SCOPE_PRIORITY,
    aggregate_node_scope,
    resolve_scope,
)


class TestScopePriority:
    """Assert SCOPE_PRIORITY matches the exact expected dict."""

    def test_scope_priority_exact_match(self):
        """Validates: Requirements 2.1"""
        expected = {
            "runtime": 7,
            "optional": 6,
            "peer": 5,
            "build": 4,
            "test": 3,
            "dev": 2,
            "unknown": 1,
        }
        assert SCOPE_PRIORITY == expected

    def test_confidence_priority_exact_match(self):
        expected = {"high": 3, "medium": 2, "low": 1}
        assert CONFIDENCE_PRIORITY == expected


class TestResolveScope:
    """Tests for resolve_scope() pairwise resolution."""

    def test_runtime_beats_dev(self):
        """Validates: Requirements 2.2"""
        result = resolve_scope(("dev", "high"), ("runtime", "low"))
        assert result == ("runtime", "low")

    def test_runtime_beats_dev_reversed(self):
        result = resolve_scope(("runtime", "low"), ("dev", "high"))
        assert result == ("runtime", "low")

    def test_tie_breaking_by_confidence(self):
        """Validates: Requirements 2.3"""
        result = resolve_scope(("runtime", "low"), ("runtime", "high"))
        assert result == ("runtime", "high")

    def test_tie_breaking_confidence_reversed(self):
        result = resolve_scope(("runtime", "high"), ("runtime", "low"))
        assert result == ("runtime", "high")

    def test_optional_beats_build(self):
        result = resolve_scope(("optional", "low"), ("build", "high"))
        assert result == ("optional", "low")

    def test_peer_beats_test(self):
        result = resolve_scope(("peer", "medium"), ("test", "high"))
        assert result == ("peer", "medium")

    def test_unknown_loses_to_everything(self):
        for scope in ["runtime", "optional", "peer", "build", "test", "dev"]:
            result = resolve_scope(("unknown", "high"), (scope, "low"))
            assert result == (scope, "low"), f"unknown should lose to {scope}"

    def test_unrecognized_scope_gets_priority_zero(self):
        """Unrecognized scope strings get priority 0 (defense-in-depth)."""
        result = resolve_scope(("garbage", "high"), ("unknown", "low"))
        assert result == ("unknown", "low")

    def test_both_unrecognized_returns_first_on_tie(self):
        result = resolve_scope(("foo", "high"), ("bar", "low"))
        assert result == ("foo", "high")

    def test_same_scope_same_confidence(self):
        result = resolve_scope(("dev", "medium"), ("dev", "medium"))
        assert result == ("dev", "medium")


class TestAggregateNodeScope:
    """Tests for aggregate_node_scope() reduction."""

    def test_empty_input(self):
        result = aggregate_node_scope([])
        assert result == ("unknown", "low")

    def test_single_input(self):
        result = aggregate_node_scope([("runtime", "high")])
        assert result == ("runtime", "high")

    def test_multiple_inputs_runtime_wins(self):
        edges = [("dev", "high"), ("runtime", "low"), ("test", "medium")]
        result = aggregate_node_scope(edges)
        assert result == ("runtime", "low")

    def test_multiple_same_scope_highest_confidence_wins(self):
        edges = [("build", "low"), ("build", "high"), ("build", "medium")]
        result = aggregate_node_scope(edges)
        assert result == ("build", "high")

    def test_all_unknown(self):
        edges = [("unknown", "low"), ("unknown", "low")]
        result = aggregate_node_scope(edges)
        assert result == ("unknown", "low")

    def test_mixed_with_unknown(self):
        edges = [("unknown", "low"), ("dev", "medium")]
        result = aggregate_node_scope(edges)
        assert result == ("dev", "medium")
