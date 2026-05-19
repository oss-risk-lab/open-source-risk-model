"""
Property-based tests for scope propagation helpers.

Feature: transitive-scope-propagation
Property 1: resolve_scope Priority Correctness

**Validates: Requirements 2.2, 2.3**
"""

from hypothesis import given, settings, strategies as st

from src.open_source_risk_model.dependencies.scope_classifier import (
    CONFIDENCE_PRIORITY,
    SCOPE_PRIORITY,
    resolve_scope,
)

# Strategies for valid scope and confidence values
valid_scopes = st.sampled_from(list(SCOPE_PRIORITY.keys()))
valid_confidences = st.sampled_from(list(CONFIDENCE_PRIORITY.keys()))
scope_tuple = st.tuples(valid_scopes, valid_confidences)


class TestResolveScopePriorityCorrectness:
    """Property 1: resolve_scope Priority Correctness.

    For any two (scope, confidence) tuples with valid values,
    resolve_scope() returns the tuple with the higher SCOPE_PRIORITY.
    On tie, the tuple with higher CONFIDENCE_PRIORITY is returned.

    **Validates: Requirements 2.2, 2.3**
    """

    @given(a=scope_tuple, b=scope_tuple)
    @settings(max_examples=200)
    def test_result_has_highest_scope_priority(self, a, b):
        """The returned tuple has scope priority >= both inputs."""
        result = resolve_scope(a, b)
        result_pri = SCOPE_PRIORITY[result[0]]
        assert result_pri >= SCOPE_PRIORITY[a[0]]
        assert result_pri >= SCOPE_PRIORITY[b[0]]

    @given(a=scope_tuple, b=scope_tuple)
    @settings(max_examples=200)
    def test_result_is_one_of_inputs(self, a, b):
        """The returned tuple is always one of the two inputs."""
        result = resolve_scope(a, b)
        assert result == a or result == b

    @given(a=scope_tuple, b=scope_tuple)
    @settings(max_examples=200)
    def test_tie_breaking_by_confidence(self, a, b):
        """When scope priorities are equal, higher confidence wins."""
        result = resolve_scope(a, b)
        if SCOPE_PRIORITY[a[0]] == SCOPE_PRIORITY[b[0]]:
            result_conf = CONFIDENCE_PRIORITY[result[1]]
            assert result_conf >= CONFIDENCE_PRIORITY[a[1]]
            assert result_conf >= CONFIDENCE_PRIORITY[b[1]]


# ---------------------------------------------------------------------------
# Property 5: Scope and Confidence Domain Validity
# ---------------------------------------------------------------------------

from open_source_risk_model.resolution.models import (
    ResolutionEdge,
    VALID_DEPENDENCY_SCOPES,
    VALID_SCOPE_CONFIDENCES,
)

# Strategies for Property 5
valid_dep_scopes = st.sampled_from(sorted(VALID_DEPENDENCY_SCOPES))
valid_scope_confs = st.sampled_from(sorted(VALID_SCOPE_CONFIDENCES))
invalid_scopes = st.text(min_size=1, max_size=20).filter(
    lambda s: s not in VALID_DEPENDENCY_SCOPES
)
invalid_confidences = st.text(min_size=1, max_size=20).filter(
    lambda s: s not in VALID_SCOPE_CONFIDENCES
)


class TestScopeAndConfidenceDomainValidity:
    """Property 5: Scope and Confidence Domain Validity.

    For any ResolutionEdge created with valid scope/confidence values,
    no ValueError is raised. For any invalid scope or confidence value,
    a ValueError IS raised.

    **Validates: Requirements 8.3, 14.1, 14.2**
    """

    @given(scope=valid_dep_scopes, confidence=valid_scope_confs)
    @settings(max_examples=200)
    def test_valid_scope_and_confidence_accepted(self, scope, confidence):
        """Valid scope + confidence combinations never raise ValueError."""
        edge = ResolutionEdge(
            repo_full_name="owner/repo",
            parent_ecosystem=None,
            parent_package="owner/repo",
            child_ecosystem="pypi",
            child_package="pkg",
            declared_specifier=None,
            resolved_version="1.0.0",
            depth=1,
            dependency_scope=scope,
            scope_confidence=confidence,
        )
        assert edge.dependency_scope == scope
        assert edge.scope_confidence == confidence

    @given(scope=invalid_scopes)
    @settings(max_examples=200)
    def test_invalid_scope_raises_value_error(self, scope):
        """Any scope string outside the valid set raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Invalid dependency_scope"):
            ResolutionEdge(
                repo_full_name="owner/repo",
                parent_ecosystem=None,
                parent_package="owner/repo",
                child_ecosystem="pypi",
                child_package="pkg",
                declared_specifier=None,
                resolved_version="1.0.0",
                depth=1,
                dependency_scope=scope,
            )

    @given(confidence=invalid_confidences)
    @settings(max_examples=200)
    def test_invalid_confidence_raises_value_error(self, confidence):
        """Any confidence string outside the valid set raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Invalid scope_confidence"):
            ResolutionEdge(
                repo_full_name="owner/repo",
                parent_ecosystem=None,
                parent_package="owner/repo",
                child_ecosystem="pypi",
                child_package="pkg",
                declared_specifier=None,
                resolved_version="1.0.0",
                depth=1,
                scope_confidence=confidence,
            )



# ---------------------------------------------------------------------------
# Property 8: Scope Propagation Determinism
# ---------------------------------------------------------------------------

import sqlite3
import tempfile
import os

from hypothesis import given, settings, strategies as st, assume

from open_source_risk_model.resolution.resolver import TransitiveResolver
from open_source_risk_model.resolution.models import (
    NormalizedPackageMetadata,
    DependencyDeclaration,
)
from open_source_risk_model.resolution.budget_tracker import BudgetConfig


# Strategy: generate a small dependency graph with scopes
_dep_scopes = st.sampled_from(["runtime", "dev", "test", "build", "optional", "peer", "unknown"])
_dep_confidences = st.sampled_from(["high", "medium", "low"])


@st.composite
def dependency_graph_with_scopes(draw):
    """Generate a random dependency graph with scoped direct deps.

    Returns:
        (direct_deps, registry_metadata) where:
        - direct_deps: list of dicts for repo_dependencies rows
        - registry_metadata: dict mapping package name → NormalizedPackageMetadata
    """
    # Generate 1-4 direct dependencies
    num_direct = draw(st.integers(min_value=1, max_value=4))
    direct_names = [f"pkg-{chr(97 + i)}" for i in range(num_direct)]

    direct_deps = []
    registry = {}

    for name in direct_names:
        scope = draw(_dep_scopes)
        confidence = draw(_dep_confidences)
        direct_deps.append({
            "repo_full_name": "owner/repo",
            "package_name": name,
            "registry_type": "pypi",
            "dependency_scope": scope,
            "scope_confidence": confidence,
        })

        # Each direct dep may have 0-2 transitive deps
        num_trans = draw(st.integers(min_value=0, max_value=2))
        trans_deps = []
        for j in range(num_trans):
            trans_name = f"{name}-sub-{j}"
            trans_deps.append(DependencyDeclaration(name=trans_name, specifier=None))
            # Transitive deps have no further children (depth limited)
            registry[trans_name] = NormalizedPackageMetadata(
                name=trans_name,
                version="1.0.0",
                ecosystem="pypi",
                dependencies=[],
                source_url=f"https://pypi.org/{trans_name}",
                fetched_at="2025-01-01T00:00:00Z",
            )

        registry[name] = NormalizedPackageMetadata(
            name=name,
            version="1.0.0",
            ecosystem="pypi",
            dependencies=trans_deps,
            source_url=f"https://pypi.org/{name}",
            fetched_at="2025-01-01T00:00:00Z",
        )

    return direct_deps, registry


def _setup_db_for_property(db_path: str, deps: list[dict]) -> None:
    """Create repo_dependencies table and insert rows."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repo_dependencies (
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
            manifest_path TEXT NOT NULL DEFAULT 'requirements.txt',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL DEFAULT '2025-01-01',
            resolved_repo TEXT,
            resolution_confidence REAL,
            resolution_method TEXT,
            dependency_scope TEXT DEFAULT 'unknown',
            scope_confidence TEXT DEFAULT 'low',
            UNIQUE(repo_full_name, package_name, manifest_path)
        )
    """)
    for dep in deps:
        conn.execute(
            """INSERT INTO repo_dependencies
               (repo_full_name, package_name, registry_type,
                dependency_scope, scope_confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (
                dep["repo_full_name"],
                dep["package_name"],
                dep["registry_type"],
                dep.get("dependency_scope"),
                dep.get("scope_confidence"),
            ),
        )
    conn.commit()
    conn.close()


class TestScopePropagationDeterminism:
    """Property 8: Scope Propagation Determinism.

    For any valid dependency graph with scopes, running scope propagation
    twice on identical input produces identical (dependency_scope,
    scope_confidence) assignments on every edge.

    **Validates: Requirements 13.1, 13.2**
    """

    @given(graph=dependency_graph_with_scopes())
    @settings(max_examples=200, deadline=None)
    def test_two_runs_produce_identical_edge_scopes(self, graph, tmp_path_factory):
        """Running resolution twice yields identical edge scopes."""
        direct_deps, registry = graph

        results = []
        for _ in range(2):
            # Use a fresh temp DB for each run
            tmp_dir = tmp_path_factory.mktemp("det")
            db_path = str(tmp_dir / "test.db")
            _setup_db_for_property(db_path, direct_deps)

            def mock_lookup(eco, name, _reg=registry):
                if name in _reg:
                    return _reg[name], True
                return None, False

            resolver = TransitiveResolver(
                db_path=db_path,
                max_depth=5,
                budget_config=BudgetConfig(global_budget=1000, min_delay_ms=0),
            )
            resolver.cache.lookup = mock_lookup

            edges, _ = resolver.resolve_repo("owner/repo")

            # Capture edge identity + scope as a sorted list of tuples
            edge_tuples = sorted(
                (
                    e.parent_package,
                    e.child_package,
                    e.depth,
                    e.dependency_scope,
                    e.scope_confidence,
                )
                for e in edges
            )
            results.append(edge_tuples)

        assert results[0] == results[1], (
            f"Non-deterministic scope propagation detected:\n"
            f"Run 1: {results[0]}\nRun 2: {results[1]}"
        )
