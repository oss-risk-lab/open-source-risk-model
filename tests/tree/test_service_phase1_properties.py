"""
Property-based tests for TreeService Phase 1: Canonical Tree Assembly.

Feature: dependency-tree-view
Property 1: Tree Structure Correctness
Property 18: Deterministic Construction
Property 3: Cycle Detection Termination
Property 19: Shared Dependency Duplication

Validates: Requirements 1.1–1.7, 8.1–8.5
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest
from hypothesis import given, settings, strategies as st, assume

from open_source_risk_model.tree.models import TreeNode
from open_source_risk_model.tree.service import TreeService, _make_canonical_id
from open_source_risk_model.tree.tree_utils import walk_tree


# ======================================================================
# Helpers
# ======================================================================


def _create_test_db(tmp_dir: str) -> str:
    """Create a minimal SQLite database with the required tables."""
    fd, db_path = tempfile.mkstemp(suffix=".db", dir=tmp_dir)
    os.close(fd)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
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
            manifest_path TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            resolved_repo TEXT,
            resolution_confidence REAL,
            resolution_method TEXT,
            parent_package_name TEXT,
            parent_package_version TEXT,
            package_version TEXT,
            UNIQUE(repo_full_name, package_name, manifest_path)
        );

        CREATE TABLE IF NOT EXISTS repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            schema_version TEXT,
            graph_json TEXT,
            node_count INTEGER DEFAULT 0,
            edge_count INTEGER DEFAULT 0,
            data_sources TEXT DEFAULT '[]',
            warnings TEXT DEFAULT '[]',
            generation_time_ms INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS package_mappings (
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            repo_full_name TEXT,
            resolution_method TEXT NOT NULL,
            confidence REAL NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (package_name, registry_type)
        );

        CREATE TABLE IF NOT EXISTS repo_cves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            severity TEXT,
            description TEXT,
            published_date TEXT,
            source TEXT DEFAULT 'ghsa',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS repo_maintainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_full_name TEXT NOT NULL,
            maintainer_username TEXT NOT NULL,
            role TEXT DEFAULT 'contributor',
            contributions INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.close()
    return db_path


def _insert_dep(
    db_path: str,
    repo: str,
    pkg: str,
    registry: str = "npm",
    *,
    is_direct: bool = True,
    version: str | None = None,
    parent_package_name: str | None = None,
    manifest: str = "package.json",
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO repo_dependencies
           (repo_full_name, package_name, registry_type, specifier,
            extras, dependency_group, is_direct, is_optional,
            manifest_path, confidence, created_at,
            parent_package_name, package_version)
           VALUES (?, ?, ?, '', '[]', 'prod', ?, 0, ?, 0.9, datetime('now'), ?, ?)""",
        (repo, pkg, registry, is_direct, manifest, parent_package_name, version),
    )
    conn.commit()
    conn.close()


def _insert_repo_graph(db_path: str, repo: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', '{}', datetime('now'), datetime('now'))""",
        (repo,),
    )
    conn.commit()
    conn.close()


def _verify_depth_invariants(node: TreeNode, expected_depth: int = 0) -> None:
    """Recursively verify that depth = parent.depth + 1 for all nodes."""
    assert node.depth == expected_depth, (
        f"Node '{node.name}' has depth {node.depth}, expected {expected_depth}"
    )
    for child in node.children:
        _verify_depth_invariants(child, expected_depth + 1)


def _trees_structurally_equal(a: TreeNode, b: TreeNode) -> bool:
    """Check two trees have identical structure, IDs, and ordering."""
    if a.id != b.id or a.name != b.name or a.depth != b.depth:
        return False
    if a.node_type != b.node_type or a.dependency_type != b.dependency_type:
        return False
    if a.version != b.version or a.ecosystem != b.ecosystem:
        return False
    if len(a.children) != len(b.children):
        return False
    return all(
        _trees_structurally_equal(ac, bc)
        for ac, bc in zip(a.children, b.children)
    )


# ======================================================================
# Strategies
# ======================================================================

# Package names: lowercase alpha start, then alphanumeric/dash
package_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=2,
    max_size=15,
).filter(lambda s: s[0].isalpha() and not s.endswith("-"))

versions = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True)

ecosystems = st.sampled_from(["npm", "pypi", "maven", "go"])


# Strategy: generate a list of unique direct dependency names
direct_dep_sets = st.lists(
    package_names,
    min_size=1,
    max_size=10,
    unique=True,
)


# ======================================================================
# Property 1: Tree Structure Correctness
# ======================================================================


class TestTreeStructureCorrectness:
    """
    **Validates: Requirements 1.1, 1.2, 1.3, 1.7**

    Property 1: Tree Structure Correctness — root at depth 0, direct
    dependencies at depth 1, transitive at depth = parent.depth + 1.
    """

    @given(
        dep_names=direct_dep_sets,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100, deadline=None)
    def test_root_at_depth_0_direct_at_depth_1(self, dep_names, eco, ver):
        """**Validates: Requirements 1.1, 1.2**

        For any set of direct dependencies, the root is at depth 0
        and all direct deps are at depth 1.
        """
        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/test-repo"
        for i, name in enumerate(dep_names):
            _insert_dep(
                db_path, repo, name, eco,
                is_direct=True, version=ver,
                manifest=f"manifest_{i}.json",
            )

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(repo)

        # Root invariants
        assert root.depth == 0
        assert root.node_type == "repository"
        assert root.id == repo

        # All direct children at depth 1
        for child in root.children:
            assert child.depth == 1
            assert child.dependency_type == "direct"

        # Number of children matches input
        assert len(root.children) == len(dep_names)

    @given(
        direct_name=package_names,
        transitive_names=st.lists(package_names, min_size=1, max_size=5, unique=True),
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_transitive_depth_equals_parent_plus_one(
        self, direct_name, transitive_names, eco, ver
    ):
        """**Validates: Requirements 1.3, 1.7**

        Transitive deps have depth = parent.depth + 1. Verify the
        depth invariant holds recursively for a chain of dependencies.
        """
        # Ensure direct_name is not in transitive_names
        assume(direct_name not in transitive_names)

        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/test-repo"
        # Insert direct dep
        _insert_dep(db_path, repo, direct_name, eco, is_direct=True, version=ver)

        # Build a chain: direct -> trans[0] -> trans[1] -> ...
        parent = direct_name
        for i, tname in enumerate(transitive_names):
            _insert_dep(
                db_path, repo, tname, eco,
                is_direct=False, version=ver,
                parent_package_name=parent,
                manifest=f"chain_{i}.json",
            )
            parent = tname

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(repo)

        # Verify depth invariant recursively
        _verify_depth_invariants(root, expected_depth=0)

        # Verify the chain depth: deepest node should be at
        # depth = 1 (direct) + len(transitive_names)
        all_nodes = list(walk_tree(root))
        max_depth = max(n.depth for n in all_nodes)
        assert max_depth == 1 + len(transitive_names)


# ======================================================================
# Property 18: Deterministic Construction
# ======================================================================


class TestDeterministicConstruction:
    """
    **Validates: Requirements 8.1, 8.2, 8.5**

    Property 18: Deterministic Construction — same input produces
    same output (same tree structure, same node ordering).
    """

    @given(
        dep_names=direct_dep_sets,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_same_input_same_output(self, dep_names, eco, ver):
        """**Validates: Requirements 8.1, 8.2, 8.5**

        Building the tree twice from the same database produces
        identical tree structures with the same node ordering.
        """
        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/deterministic-repo"
        for i, name in enumerate(dep_names):
            _insert_dep(
                db_path, repo, name, eco,
                is_direct=True, version=ver,
                manifest=f"manifest_{i}.json",
            )

        svc = TreeService(db_path)
        root1, source1 = svc._build_canonical_tree(repo)
        root2, source2 = svc._build_canonical_tree(repo)

        assert source1 == source2
        assert _trees_structurally_equal(root1, root2), (
            "Two builds from the same data produced different tree structures"
        )

    @given(
        direct_name=package_names,
        trans_name=package_names,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_deterministic_with_transitive(self, direct_name, trans_name, eco, ver):
        """**Validates: Requirements 8.1, 8.5**

        Determinism holds for trees with transitive dependencies too.
        """
        assume(direct_name != trans_name)

        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/det-trans-repo"
        _insert_dep(db_path, repo, direct_name, eco, is_direct=True, version=ver)
        _insert_dep(
            db_path, repo, trans_name, eco,
            is_direct=False, version=ver,
            parent_package_name=direct_name,
            manifest="trans.json",
        )

        svc = TreeService(db_path)
        root1, _ = svc._build_canonical_tree(repo)
        root2, _ = svc._build_canonical_tree(repo)

        assert _trees_structurally_equal(root1, root2)


# ======================================================================
# Property 3: Cycle Detection Termination
# ======================================================================


class TestCycleDetectionTermination:
    """
    **Validates: Requirements 1.6**

    Property 3: Cycle Detection Termination — tree construction always
    terminates for any dependency graph, including those with cycles.
    """

    @given(
        cycle_size=st.integers(min_value=2, max_value=6),
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_cycle_terminates(self, cycle_size, eco, ver):
        """**Validates: Requirements 1.6**

        Generate a cycle of N packages (A->B->C->...->A) and verify
        tree construction terminates with finite nodes.
        """
        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/cycle-repo"
        # Generate unique package names for the cycle
        pkg_names = [f"cycle-pkg-{i}" for i in range(cycle_size)]

        # First package is direct
        _insert_dep(db_path, repo, pkg_names[0], eco, is_direct=True, version=ver)

        # Each subsequent package is transitive, child of the previous
        for i in range(1, cycle_size):
            _insert_dep(
                db_path, repo, pkg_names[i], eco,
                is_direct=False, version=ver,
                parent_package_name=pkg_names[i - 1],
                manifest=f"cycle_{i}.json",
            )

        # Close the cycle: last package depends on first
        _insert_dep(
            db_path, repo, pkg_names[0], eco,
            is_direct=False, version=ver,
            parent_package_name=pkg_names[cycle_size - 1],
            manifest="cycle_close.json",
        )

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(repo)

        # Must terminate — we got here without hanging
        all_nodes = list(walk_tree(root))
        assert len(all_nodes) > 0

        # Root is always present
        assert root.depth == 0
        assert root.node_type == "repository"

        # The tree is finite — total nodes bounded by cycle_size + 2
        # (root + cycle_size nodes + 1 cycle-terminated duplicate)
        assert len(all_nodes) <= cycle_size + 2

    @given(
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=50)
    def test_self_cycle_terminates(self, eco, ver):
        """**Validates: Requirements 1.6**

        A package that depends on itself terminates.
        """
        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/self-cycle-repo"
        _insert_dep(db_path, repo, "self-ref", eco, is_direct=True, version=ver)
        # self-ref depends on itself
        _insert_dep(
            db_path, repo, "self-ref", eco,
            is_direct=False, version=ver,
            parent_package_name="self-ref",
            manifest="self.json",
        )

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(repo)

        all_nodes = list(walk_tree(root))
        # Root + self-ref + self-ref (cycle-terminated)
        assert len(all_nodes) >= 2
        # Must be finite
        assert len(all_nodes) <= 4


# ======================================================================
# Property 19: Shared Dependency Duplication
# ======================================================================


class TestSharedDependencyDuplication:
    """
    **Validates: Requirements 8.3**

    Property 19: Shared Dependency Duplication — when the same package
    appears under multiple parents, it appears as a separate TreeNode
    instance in each branch with the same canonical ID.
    """

    @given(
        parent_names=st.lists(package_names, min_size=2, max_size=5, unique=True),
        shared_name=package_names,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_shared_dep_separate_instances_same_id(
        self, parent_names, shared_name, eco, ver
    ):
        """**Validates: Requirements 8.3**

        A shared transitive dependency appears in each branch independently
        with the same canonical ID but as distinct TreeNode instances.
        """
        # Ensure shared_name is not one of the parent names
        assume(shared_name not in parent_names)

        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/shared-dep-repo"

        # Insert each parent as a direct dep
        for i, pname in enumerate(parent_names):
            _insert_dep(
                db_path, repo, pname, eco,
                is_direct=True, version=ver,
                manifest=f"parent_{i}.json",
            )

        # Insert shared dep as transitive under each parent
        for i, pname in enumerate(parent_names):
            _insert_dep(
                db_path, repo, shared_name, eco,
                is_direct=False, version=ver,
                parent_package_name=pname,
                manifest=f"shared_{i}.json",
            )

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(repo)

        # Find all instances of the shared dependency
        shared_nodes = [n for n in walk_tree(root) if n.name == shared_name]

        # Should appear once per parent
        assert len(shared_nodes) == len(parent_names), (
            f"Expected {len(parent_names)} instances of '{shared_name}', "
            f"got {len(shared_nodes)}"
        )

        # All instances share the same canonical ID
        expected_id = _make_canonical_id(eco, shared_name, ver)
        for node in shared_nodes:
            assert node.id == expected_id

        # All instances are distinct objects
        for i in range(len(shared_nodes)):
            for j in range(i + 1, len(shared_nodes)):
                assert shared_nodes[i] is not shared_nodes[j], (
                    "Shared dependency nodes must be distinct TreeNode instances"
                )

        # Each shared node is at depth 2 (child of a direct dep)
        for node in shared_nodes:
            assert node.depth == 2
            assert node.dependency_type == "transitive"


# ======================================================================
# Property 2: Node Identity and Structure Invariants
# ======================================================================


class TestNodeIdentityInvariants:
    """
    **Validates: Requirements 1.4, 1.5, 8.4**

    Property 2: Node Identity — unique canonical IDs per package+version,
    consistent across builds. Same package+version always produces the
    same canonical ID; different package+version combinations produce
    different canonical IDs.
    """

    @given(
        name=package_names,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_same_package_version_same_id(self, name, eco, ver):
        """**Validates: Requirements 1.4, 8.4**

        Calling _make_canonical_id with the same ecosystem, name, and
        version always produces the same canonical ID.
        """
        id1 = _make_canonical_id(eco, name, ver)
        id2 = _make_canonical_id(eco, name, ver)
        assert id1 == id2, (
            f"Same inputs produced different IDs: {id1!r} vs {id2!r}"
        )
        # Verify format: pkg:{ecosystem}/{name}@{version}
        assert id1 == f"pkg:{eco}/{name}@{ver}"

    @given(
        name_a=package_names,
        ver_a=versions,
        name_b=package_names,
        ver_b=versions,
        eco=ecosystems,
    )
    @settings(max_examples=100)
    def test_different_package_version_different_id(
        self, name_a, ver_a, name_b, ver_b, eco
    ):
        """**Validates: Requirements 1.4**

        Different package+version combinations produce different
        canonical IDs (within the same ecosystem).
        """
        assume(name_a != name_b or ver_a != ver_b)

        id_a = _make_canonical_id(eco, name_a, ver_a)
        id_b = _make_canonical_id(eco, name_b, ver_b)
        assert id_a != id_b, (
            f"Different packages produced same ID: "
            f"({name_a}@{ver_a}) and ({name_b}@{ver_b}) -> {id_a!r}"
        )

    @given(
        dep_names=st.lists(package_names, min_size=1, max_size=8, unique=True),
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_canonical_ids_consistent_across_builds(self, dep_names, eco, ver):
        """**Validates: Requirements 1.4, 1.5, 8.4**

        Building the tree twice from the same data produces nodes with
        identical canonical IDs and recorded depth values.
        """
        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/identity-repo"
        for i, name in enumerate(dep_names):
            _insert_dep(
                db_path, repo, name, eco,
                is_direct=True, version=ver,
                manifest=f"manifest_{i}.json",
            )

        svc = TreeService(db_path)
        root1, _ = svc._build_canonical_tree(repo)
        root2, _ = svc._build_canonical_tree(repo)

        nodes1 = sorted(walk_tree(root1), key=lambda n: n.id)
        nodes2 = sorted(walk_tree(root2), key=lambda n: n.id)

        assert len(nodes1) == len(nodes2)
        for n1, n2 in zip(nodes1, nodes2):
            assert n1.id == n2.id, (
                f"Canonical ID mismatch across builds: {n1.id!r} vs {n2.id!r}"
            )
            assert n1.depth == n2.depth, (
                f"Depth mismatch for {n1.id}: {n1.depth} vs {n2.depth}"
            )

    @given(
        name=package_names,
        eco=ecosystems,
    )
    @settings(max_examples=100)
    def test_missing_version_uses_unknown(self, name, eco):
        """**Validates: Requirements 1.4**

        When version is None or empty, the canonical ID uses @unknown.
        """
        id_none = _make_canonical_id(eco, name, None)
        id_empty = _make_canonical_id(eco, name, "")
        expected = f"pkg:{eco}/{name}@unknown"

        assert id_none == expected, f"None version: {id_none!r} != {expected!r}"
        assert id_empty == expected, f"Empty version: {id_empty!r} != {expected!r}"
        # Both produce the same ID
        assert id_none == id_empty

    @given(
        dep_names=st.lists(package_names, min_size=2, max_size=6, unique=True),
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_all_nodes_have_unique_ids_within_tree(self, dep_names, eco, ver):
        """**Validates: Requirements 1.4, 1.5**

        Within a single tree build, every node has a recorded depth and
        all package nodes with distinct names have unique canonical IDs.
        """
        tmp_dir = tempfile.mkdtemp()
        db_path = _create_test_db(tmp_dir)

        repo = "owner/unique-id-repo"
        for i, name in enumerate(dep_names):
            _insert_dep(
                db_path, repo, name, eco,
                is_direct=True, version=ver,
                manifest=f"manifest_{i}.json",
            )

        svc = TreeService(db_path)
        root, _ = svc._build_canonical_tree(repo)

        all_nodes = list(walk_tree(root))

        # Every node has a recorded depth value (non-negative)
        for node in all_nodes:
            assert node.depth >= 0, f"Node {node.id} has invalid depth {node.depth}"

        # Package nodes with distinct names have unique IDs
        package_nodes = [n for n in all_nodes if n.node_type == "package"]
        ids_by_name = {}
        for node in package_nodes:
            if node.name not in ids_by_name:
                ids_by_name[node.name] = node.id
            else:
                # Same name should have same ID (same version in this test)
                assert ids_by_name[node.name] == node.id

        # Distinct names → distinct IDs
        unique_names = set(ids_by_name.keys())
        unique_ids = set(ids_by_name.values())
        assert len(unique_names) == len(unique_ids), (
            f"Different package names mapped to same ID: "
            f"names={unique_names}, ids={unique_ids}"
        )
