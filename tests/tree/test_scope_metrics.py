"""
Property-based tests for scope count metrics in SummaryMetricsCalculator.

Feature: dependency-scope-classification, Property 3: Scope count conservation

Validates: Requirements 11.1, 11.2
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections import Counter

import pytest
from hypothesis import given, settings, strategies as st

from open_source_risk_model.tree.metrics import SummaryMetricsCalculator
from open_source_risk_model.tree.models import TreeNode


# ======================================================================
# Strategies
# ======================================================================

VALID_SCOPES = ["runtime", "dev", "test", "build", "optional", "peer", "unknown"]

scope_strategy = st.sampled_from(VALID_SCOPES)

package_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz",
    min_size=2,
    max_size=10,
).filter(lambda s: s[0].isalpha())

dependency_strategy = st.fixed_dictionaries(
    {
        "package_name": package_name_strategy,
        "dependency_scope": scope_strategy,
        "scope_confidence": st.sampled_from(["high", "medium", "low"]),
    }
)

# Generate lists of 0..30 dependencies
dependency_list_strategy = st.lists(
    dependency_strategy,
    min_size=0,
    max_size=30,
)


# ======================================================================
# Helpers
# ======================================================================


def _create_temp_db(dependencies: list[dict], repo_full_name: str = "owner/repo") -> str:
    """Create a temporary SQLite database with repo_dependencies rows.

    Returns the path to the temporary database file.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE repo_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            specifier TEXT,
            extras TEXT,
            markers TEXT,
            dependency_group TEXT DEFAULT 'prod',
            is_direct BOOLEAN NOT NULL DEFAULT 1,
            is_optional BOOLEAN NOT NULL DEFAULT 0,
            manifest_path TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            resolved_repo TEXT,
            resolution_confidence REAL,
            resolution_method TEXT,
            dependency_scope TEXT DEFAULT 'unknown',
            scope_confidence TEXT DEFAULT 'low'
        )
    """)

    for i, dep in enumerate(dependencies):
        conn.execute(
            """
            INSERT INTO repo_dependencies
                (repo_full_name, package_name, registry_type, manifest_path,
                 confidence, created_at, dependency_scope, scope_confidence)
            VALUES (?, ?, 'pypi', 'requirements.txt', 1.0, '2024-01-01',
                    ?, ?)
            """,
            (
                repo_full_name,
                f"{dep['package_name']}_{i}",  # unique per row
                dep["dependency_scope"],
                dep["scope_confidence"],
            ),
        )

    conn.commit()
    conn.close()
    return db_path


def _minimal_tree_root() -> TreeNode:
    """Create a minimal root TreeNode (no children).

    Scope counts come from the DB, not the tree, so a bare root suffices.
    """
    return TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        depth=0,
        dependency_type="direct",
    )


# ======================================================================
# Property 3: Scope Count Conservation
# ======================================================================


class TestScopeCountConservation:
    """
    **Validates: Requirements 11.1, 11.2**

    Feature: dependency-scope-classification, Property 3: Scope count conservation

    Property 3: Scope Count Conservation — Sum of all direct_* scope counts
    equals direct_total_dependency_count. Each individual count matches the
    expected count from the generated data.
    """

    @given(deps=dependency_list_strategy)
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_scope_sum_equals_total(self, deps):
        """**Validates: Requirements 11.1, 11.2**

        The sum of direct_runtime + direct_dev + direct_test + direct_build +
        direct_optional + direct_peer + direct_unknown must equal
        direct_total_dependency_count.
        """
        repo_name = "owner/test-repo"
        db_path = _create_temp_db(deps, repo_name)

        try:
            calc = SummaryMetricsCalculator(db_path=db_path)
            metrics = calc.calculate_metrics(
                _minimal_tree_root(), [], repo_full_name=repo_name
            )

            scope_sum = (
                metrics.direct_runtime_dependency_count
                + metrics.direct_dev_dependency_count
                + metrics.direct_test_dependency_count
                + metrics.direct_build_dependency_count
                + metrics.direct_optional_dependency_count
                + metrics.direct_peer_dependency_count
                + metrics.direct_unknown_dependency_count
            )

            assert scope_sum == metrics.direct_total_dependency_count, (
                f"Sum of scope counts ({scope_sum}) != "
                f"direct_total ({metrics.direct_total_dependency_count})"
            )
        finally:
            os.unlink(db_path)

    @given(deps=dependency_list_strategy)
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_individual_counts_match_generated_data(self, deps):
        """**Validates: Requirements 11.1, 11.2**

        Each direct_*_dependency_count must match the number of dependencies
        with that scope in the generated data.
        """
        repo_name = "owner/test-repo"
        db_path = _create_temp_db(deps, repo_name)

        try:
            calc = SummaryMetricsCalculator(db_path=db_path)
            metrics = calc.calculate_metrics(
                _minimal_tree_root(), [], repo_full_name=repo_name
            )

            # Build expected counts from input
            expected: Counter[str] = Counter()
            for dep in deps:
                expected[dep["dependency_scope"]] += 1

            assert metrics.direct_runtime_dependency_count == expected.get("runtime", 0)
            assert metrics.direct_dev_dependency_count == expected.get("dev", 0)
            assert metrics.direct_test_dependency_count == expected.get("test", 0)
            assert metrics.direct_build_dependency_count == expected.get("build", 0)
            assert metrics.direct_optional_dependency_count == expected.get("optional", 0)
            assert metrics.direct_peer_dependency_count == expected.get("peer", 0)
            assert metrics.direct_unknown_dependency_count == expected.get("unknown", 0)
            assert metrics.direct_total_dependency_count == len(deps)
        finally:
            os.unlink(db_path)

    @given(deps=dependency_list_strategy)
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_total_equals_input_length(self, deps):
        """**Validates: Requirements 11.1, 11.2**

        direct_total_dependency_count must equal the number of dependencies
        inserted into the database.
        """
        repo_name = "owner/test-repo"
        db_path = _create_temp_db(deps, repo_name)

        try:
            calc = SummaryMetricsCalculator(db_path=db_path)
            metrics = calc.calculate_metrics(
                _minimal_tree_root(), [], repo_full_name=repo_name
            )

            assert metrics.direct_total_dependency_count == len(deps), (
                f"direct_total ({metrics.direct_total_dependency_count}) "
                f"!= input count ({len(deps)})"
            )
        finally:
            os.unlink(db_path)


# ======================================================================
# Strategies for Property 4
# ======================================================================

# Strategy to generate a child TreeNode at a given depth
def _make_child_node(name: str, depth: int) -> TreeNode:
    """Create a leaf TreeNode at the specified depth."""
    return TreeNode(
        id=name,
        node_type="package",
        name=name,
        depth=depth,
        dependency_type="direct" if depth == 1 else "transitive",
    )


def _build_random_tree(direct_count: int, transitive_per_direct: list[int]) -> TreeNode:
    """Build a tree with the given number of direct children.

    Each direct child gets a number of transitive children specified by
    the corresponding entry in *transitive_per_direct*.
    """
    root = TreeNode(
        id="owner/repo",
        node_type="repository",
        name="owner/repo",
        depth=0,
        dependency_type="direct",
    )
    for i in range(direct_count):
        child = _make_child_node(f"pkg-{i}", depth=1)
        trans_count = transitive_per_direct[i] if i < len(transitive_per_direct) else 0
        for j in range(trans_count):
            grandchild = _make_child_node(f"pkg-{i}-trans-{j}", depth=2)
            child.children.append(grandchild)
        root.children.append(child)
    return root


# Strategy: number of direct deps (0..20), each with 0..5 transitive deps
tree_strategy = st.integers(min_value=0, max_value=20).flatmap(
    lambda n: st.tuples(
        st.just(n),
        st.lists(
            st.integers(min_value=0, max_value=5),
            min_size=n,
            max_size=n,
        ),
    )
)


# ======================================================================
# Property 4: Existing Metrics Preservation
# ======================================================================


class TestExistingMetricsPreservation:
    """
    **Validates: Requirements 14.2**

    Feature: dependency-scope-classification, Property 4: Existing metrics preservation

    Property 4: Existing Metrics Preservation — After scope classification is
    added, the existing invariant total_dependencies == direct_dependencies +
    transitive_dependencies continues to hold for any dependency tree.
    """

    @given(data=tree_strategy)
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_total_equals_direct_plus_transitive(self, data):
        """**Validates: Requirements 14.2**

        For any randomly generated dependency tree, total_dependencies must
        equal direct_dependencies + transitive_dependencies.
        """
        direct_count, transitive_per_direct = data
        root = _build_random_tree(direct_count, transitive_per_direct)

        calc = SummaryMetricsCalculator(db_path=":memory:")
        metrics = calc.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.total_dependencies == metrics.direct_dependencies + metrics.transitive_dependencies, (
            f"total ({metrics.total_dependencies}) != "
            f"direct ({metrics.direct_dependencies}) + "
            f"transitive ({metrics.transitive_dependencies})"
        )

    @given(data=tree_strategy)
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_direct_count_matches_depth_one_nodes(self, data):
        """**Validates: Requirements 14.2**

        direct_dependencies must equal the number of depth-1 nodes in the tree.
        """
        direct_count, transitive_per_direct = data
        root = _build_random_tree(direct_count, transitive_per_direct)

        calc = SummaryMetricsCalculator(db_path=":memory:")
        metrics = calc.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.direct_dependencies == direct_count, (
            f"direct_dependencies ({metrics.direct_dependencies}) != "
            f"expected direct count ({direct_count})"
        )

    @given(data=tree_strategy)
    @settings(max_examples=200)
    @pytest.mark.property_test
    def test_transitive_count_matches_deeper_nodes(self, data):
        """**Validates: Requirements 14.2**

        transitive_dependencies must equal the number of nodes with depth > 1.
        """
        direct_count, transitive_per_direct = data
        root = _build_random_tree(direct_count, transitive_per_direct)

        expected_transitive = sum(transitive_per_direct)

        calc = SummaryMetricsCalculator(db_path=":memory:")
        metrics = calc.calculate_metrics(root, [], repo_full_name=None)

        assert metrics.transitive_dependencies == expected_transitive, (
            f"transitive_dependencies ({metrics.transitive_dependencies}) != "
            f"expected transitive count ({expected_transitive})"
        )
