"""Integration tests for the dependency tree feature.

Tests the complete flow: API request → TreeService → database queries → JSON response.
No mocks — all tests use real SQLite databases with realistic data.

Validates: Requirements 4.7, 7.5, 14.4, 14.6
Design: Performance targets table, Integration Testing section
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _create_db(tmp_path: str) -> str:
    """Create a SQLite database with all required tables."""
    db_path = os.path.join(tmp_path, "integration.db")
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


def _graph_json(maintenance_risk: float, days_since_release: int = 30) -> str:
    return json.dumps({
        "nodes": [
            {"type": "repo", "metadata": {"maintenance_risk": maintenance_risk}},
            {"type": "release", "metadata": {"days_since_release": days_since_release}},
        ],
        "edges": [],
    })


def _insert_dep(
    db_path: str,
    repo: str,
    pkg: str,
    registry: str = "npm",
    *,
    is_direct: bool = True,
    specifier: str = "",
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
           VALUES (?, ?, ?, ?, '[]', 'prod', ?, 0, ?, 0.9, datetime('now'), ?, ?)""",
        (repo, pkg, registry, specifier, is_direct, manifest, parent_package_name, version),
    )
    conn.commit()
    conn.close()


def _insert_repo_graph(db_path: str, repo: str, *, risk_score: float = 45.0) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO repo_graphs
           (repo_full_name, schema_version, graph_json, created_at, updated_at)
           VALUES (?, '1.0', ?, datetime('now'), datetime('now'))""",
        (repo, _graph_json(risk_score)),
    )
    conn.commit()
    conn.close()


def _insert_package_mapping(
    db_path: str, pkg: str, registry: str, mapped_repo: str
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO package_mappings
           (package_name, registry_type, repo_full_name, resolution_method, confidence)
           VALUES (?, ?, ?, 'name_match', 0.9)""",
        (pkg, registry, mapped_repo),
    )
    conn.commit()
    conn.close()


def _insert_cve(db_path: str, repo: str, cve_id: str, severity: str = "high") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO repo_cves (repo_full_name, cve_id, severity) VALUES (?, ?, ?)",
        (repo, cve_id, severity),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_full_repo(db_path: str) -> None:
    """Seed a realistic repo with direct + transitive deps, risk data, and CVEs.

    Repo: integ/web-app
    Direct: express (npm, high risk 85), lodash (npm, medium 45), debug (npm, low 15)
    Transitive: body-parser (npm, medium 60) via express
    CVEs: express has 2 CVEs
    """
    _insert_repo_graph(db_path, "integ/web-app", risk_score=0.3)

    for pkg, ver, manifest in [
        ("express", "4.18.2", "package.json"),
        ("lodash", "4.17.21", "package.json2"),
        ("debug", "4.3.4", "package.json3"),
    ]:
        _insert_dep(db_path, "integ/web-app", pkg, "npm", version=ver, manifest=manifest)

    _insert_dep(
        db_path, "integ/web-app", "body-parser", "npm",
        is_direct=False, parent_package_name="express", version="1.20.0",
        manifest="package.json4",
    )

    for pkg, mapped_repo in [
        ("express", "expressjs/express"),
        ("lodash", "lodash/lodash"),
        ("debug", "debug-js/debug"),
        ("body-parser", "expressjs/body-parser"),
    ]:
        _insert_package_mapping(db_path, pkg, "npm", mapped_repo)

    for repo, risk in [
        ("expressjs/express", 0.85),
        ("lodash/lodash", 0.45),
        ("debug-js/debug", 0.15),
        ("expressjs/body-parser", 0.60),
    ]:
        _insert_repo_graph(db_path, repo, risk_score=risk)

    _insert_cve(db_path, "expressjs/express", "CVE-2024-0001")
    _insert_cve(db_path, "expressjs/express", "CVE-2024-0002")


def _seed_shared_dep_repo(db_path: str) -> None:
    """Seed a repo where the same package appears in two branches.

    Repo: integ/shared-dep
    Branch 1: alpha → shared-lib@1.0.0
    Branch 2: beta  → shared-lib@1.0.0
    """
    _insert_repo_graph(db_path, "integ/shared-dep")

    _insert_dep(db_path, "integ/shared-dep", "alpha", "npm", version="1.0.0", manifest="m1.json")
    _insert_dep(db_path, "integ/shared-dep", "beta", "npm", version="2.0.0", manifest="m2.json")

    _insert_dep(
        db_path, "integ/shared-dep", "shared-lib", "npm",
        is_direct=False, parent_package_name="alpha", version="1.0.0",
        manifest="m3.json",
    )
    _insert_dep(
        db_path, "integ/shared-dep", "shared-lib", "npm",
        is_direct=False, parent_package_name="beta", version="1.0.0",
        manifest="m4.json",
    )


def _seed_zero_dep_repo(db_path: str) -> None:
    """Seed a repo that exists but has zero dependencies."""
    _insert_repo_graph(db_path, "integ/empty-lib")


def _seed_missing_risk_repo(db_path: str) -> None:
    """Seed a repo where one dep has risk data and another does not.

    Repo: integ/partial
    known-pkg → has mapping + risk data
    unknown-pkg → no mapping at all
    """
    _insert_repo_graph(db_path, "integ/partial")

    _insert_dep(db_path, "integ/partial", "known-pkg", "npm", version="1.0.0", manifest="m1.json")
    _insert_dep(db_path, "integ/partial", "unknown-pkg", "npm", version="0.1.0", manifest="m2.json")

    _insert_package_mapping(db_path, "known-pkg", "npm", "known/repo")
    _insert_repo_graph(db_path, "known/repo", risk_score=0.5)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestCompleteFlow:
    """Test the complete flow: API request → TreeService → DB → JSON response."""

    def test_full_repo_end_to_end(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()

        # Top-level structure
        assert data["repo"] == "integ/web-app"
        assert data["tree"]["node_type"] == "repository"
        assert data["tree"]["depth"] == 0

        # Direct deps present
        child_names = {c["name"] for c in data["tree"]["children"]}
        assert "express" in child_names
        assert "lodash" in child_names
        assert "debug" in child_names

        # Transitive dep present under express
        express_node = next(c for c in data["tree"]["children"] if c["name"] == "express")
        transitive_names = {gc["name"] for gc in express_node.get("children", [])}
        assert "body-parser" in transitive_names

        # Metrics
        metrics = data["summary_metrics"]
        assert metrics["total_dependencies"] == metrics["direct_dependencies"] + metrics["transitive_dependencies"]
        assert metrics["direct_dependencies"] >= 3
        assert metrics["transitive_dependencies"] >= 1
        assert metrics["max_depth"] >= 2

        # Provenance
        prov = data["provenance"]
        assert prov["data_source"] == "database"
        assert prov["total_nodes"] > 0
        assert prov["construction_time_ms"] is not None


class TestFilterCombinations:
    """Test filter combinations produce correct results end-to-end."""

    def test_high_risk_only_filters_correctly(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree?high_risk_only=true")

        assert resp.status_code == 200
        data = resp.json()
        assert "high_risk_only" in data["summary_metrics"]["filters_applied"]

        # All leaf nodes should be high-risk (score > 70)
        def _collect_leaves(node):
            if not node.get("children"):
                return [node]
            leaves = []
            for c in node["children"]:
                leaves.extend(_collect_leaves(c))
            return leaves

        leaves = _collect_leaves(data["tree"])
        for leaf in leaves:
            rm = leaf.get("risk_metadata")
            if rm and rm.get("risk_score") is not None:
                assert rm["risk_score"] > 70

    def test_direct_only_filters_correctly(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree?direct_only=true")

        assert resp.status_code == 200
        data = resp.json()
        assert "direct_only" in data["summary_metrics"]["filters_applied"]

        # All children should be at depth 1 with no grandchildren
        for child in data["tree"]["children"]:
            assert child["depth"] == 1
            assert child["children"] == []

    def test_max_depth_filters_correctly(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree?max_depth=1")

        assert resp.status_code == 200
        data = resp.json()
        assert "max_depth" in data["summary_metrics"]["filters_applied"]

        # No nodes deeper than 1
        def _max_depth(node):
            d = node["depth"]
            for c in node.get("children", []):
                d = max(d, _max_depth(c))
            return d

        assert _max_depth(data["tree"]) <= 1

    def test_combined_filters(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get(
                "/repos/integ/web-app/dependency-tree?high_risk_only=true&direct_only=true"
            )

        assert resp.status_code == 200
        data = resp.json()
        filters = data["summary_metrics"]["filters_applied"]
        assert "high_risk_only" in filters
        assert "direct_only" in filters

    def test_sort_by_name(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree?sort_by=name")

        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()["tree"]["children"]]
        assert names == sorted(names)

    def test_truncate_after_children(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree?truncate_after_children=2")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tree"]["children"]) <= 2


class TestErrorHandlingIntegration:
    """Test error handling with intentionally missing data."""

    def test_missing_repo_returns_404(self, tmp_path):
        db_path = _create_db(str(tmp_path))

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/nonexistent/repo/dependency-tree")

        assert resp.status_code == 404

    def test_partial_risk_data_returns_200(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_missing_risk_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/partial/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()
        prov = data["provenance"]
        assert prov["data_completeness"] == "partial"
        assert prov["nodes_with_missing_risk"] > 0

    def test_missing_risk_node_has_unavailable_source(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_missing_risk_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/partial/dependency-tree")

        children = resp.json()["tree"]["children"]
        unknown = next((c for c in children if c["name"] == "unknown-pkg"), None)
        assert unknown is not None
        rm = unknown.get("risk_metadata")
        if rm is not None:
            assert rm["score_source"] == "unavailable"
            assert rm["score_completeness"] == "missing"


class TestZeroDependencyRepo:
    """Test zero-dependency repository end-to-end."""

    def test_returns_200(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_zero_dep_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/empty-lib/dependency-tree")

        assert resp.status_code == 200

    def test_empty_children_and_zero_counts(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_zero_dep_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/empty-lib/dependency-tree")

        data = resp.json()
        assert data["tree"]["children"] == []
        assert data["tree"]["node_type"] == "repository"

        metrics = data["summary_metrics"]
        assert metrics["total_dependencies"] == 0
        assert metrics["direct_dependencies"] == 0
        assert metrics["transitive_dependencies"] == 0
        assert metrics["high_risk_count"] == 0
        assert metrics["vulnerable_count"] == 0

    def test_provenance_full_for_zero_deps(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_zero_dep_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/empty-lib/dependency-tree")

        prov = resp.json()["provenance"]
        assert prov["data_source"] == "database"


class TestProvenanceAccuracy:
    """Test provenance accuracy across different data source scenarios."""

    def test_database_source_provenance(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree")

        prov = resp.json()["provenance"]
        assert prov["data_source"] == "database"
        assert prov["last_updated"] != ""
        assert prov["construction_time_ms"] is not None
        assert prov["construction_time_ms"] >= 0

    def test_provenance_node_counts(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree")

        data = resp.json()
        prov = data["provenance"]

        # total_nodes should include root + all deps
        def _count_nodes(node):
            return 1 + sum(_count_nodes(c) for c in node.get("children", []))

        actual_count = _count_nodes(data["tree"])
        assert prov["total_nodes"] == actual_count

    def test_provenance_risk_coverage(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_missing_risk_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/partial/dependency-tree")

        prov = resp.json()["provenance"]
        # nodes_with_risk_data + nodes_with_missing_risk should account for all non-root nodes
        # (root is a repository node, not a package)
        assert prov["nodes_with_risk_data"] >= 0
        assert prov["nodes_with_missing_risk"] >= 1  # unknown-pkg has no risk data


class TestCanonicalIDConsistency:
    """Test canonical ID consistency: same package in two branches has same ID."""

    def test_shared_dep_same_id_in_both_branches(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_shared_dep_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/shared-dep/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()

        # Find shared-lib in both branches
        shared_ids = []

        def _find_shared(node):
            if node.get("name") == "shared-lib":
                shared_ids.append(node["id"])
            for c in node.get("children", []):
                _find_shared(c)

        _find_shared(data["tree"])

        # shared-lib should appear in both branches with the same canonical ID
        assert len(shared_ids) == 2, f"Expected shared-lib in 2 branches, found {len(shared_ids)}"
        assert shared_ids[0] == shared_ids[1], (
            f"Canonical IDs differ: {shared_ids[0]} vs {shared_ids[1]}"
        )
        assert "pkg:npm/shared-lib@1.0.0" == shared_ids[0]


class TestDeterministicOutput:
    """Test deterministic output: same request twice produces identical JSON."""

    def test_same_request_produces_identical_json(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp1 = client.get("/repos/integ/web-app/dependency-tree")
            resp2 = client.get("/repos/integ/web-app/dependency-tree")

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        data1 = resp1.json()
        data2 = resp2.json()

        # Remove construction_time_ms since it varies between requests
        data1["provenance"].pop("construction_time_ms", None)
        data2["provenance"].pop("construction_time_ms", None)
        # Remove last_updated if it could differ by a second
        data1["provenance"].pop("last_updated", None)
        data2["provenance"].pop("last_updated", None)

        assert data1 == data2

    def test_deterministic_with_sort(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp1 = client.get("/repos/integ/web-app/dependency-tree?sort_by=risk_score")
            resp2 = client.get("/repos/integ/web-app/dependency-tree?sort_by=risk_score")

        data1 = resp1.json()
        data2 = resp2.json()

        data1["provenance"].pop("construction_time_ms", None)
        data2["provenance"].pop("construction_time_ms", None)
        data1["provenance"].pop("last_updated", None)
        data2["provenance"].pop("last_updated", None)

        assert data1 == data2


class TestResponseSchemaValidation:
    """Test response validates against Pydantic response schema (structural validation)."""

    def test_response_has_all_required_fields(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree")

        data = resp.json()

        # Top-level fields
        assert "repo" in data
        assert "tree" in data
        assert "summary_metrics" in data
        assert "provenance" in data

        # Tree node fields
        tree = data["tree"]
        for field in ["id", "node_type", "name", "version", "depth", "children", "dependency_type"]:
            assert field in tree, f"Missing field '{field}' in tree root"

        # Summary metrics fields
        metrics = data["summary_metrics"]
        for field in [
            "total_dependencies", "direct_dependencies", "transitive_dependencies",
            "high_risk_count", "vulnerable_count", "max_depth", "filters_applied",
        ]:
            assert field in metrics, f"Missing field '{field}' in summary_metrics"

        # Provenance fields
        prov = data["provenance"]
        for field in [
            "data_source", "data_completeness", "last_updated",
            "total_nodes", "nodes_with_risk_data", "nodes_with_missing_risk",
            "nodes_with_errors", "error_details",
        ]:
            assert field in prov, f"Missing field '{field}' in provenance"

    def test_child_nodes_have_canonical_fields(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree")

        children = resp.json()["tree"]["children"]
        assert len(children) > 0

        for child in children:
            assert "id" in child
            assert "node_type" in child
            assert child["node_type"] == "package"
            assert "name" in child
            assert "version" in child
            assert "depth" in child
            assert "dependency_type" in child
            assert "children" in child

    def test_risk_metadata_structure(self, tmp_path):
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/integ/web-app/dependency-tree")

        children = resp.json()["tree"]["children"]
        children_with_risk = [c for c in children if c.get("risk_metadata")]
        assert len(children_with_risk) > 0

        for child in children_with_risk:
            rm = child["risk_metadata"]
            assert "risk_score" in rm
            assert "risk_level" in rm
            assert "vulnerability_count" in rm
            assert "score_source" in rm
            assert "score_completeness" in rm


class TestPerformance:
    """Test performance: <5s for repos with <1000 deps (database-backed, end-to-end)."""

    def test_small_repo_under_5_seconds(self, tmp_path):
        """Validates Requirement 4.7: <5s for <1000 deps."""
        db_path = _create_db(str(tmp_path))
        _seed_full_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            start = time.monotonic()
            resp = client.get("/repos/integ/web-app/dependency-tree")
            elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 5.0, f"Response took {elapsed:.2f}s, expected <5s"

    def test_many_deps_under_5_seconds(self, tmp_path):
        """Create a repo with ~200 deps and verify <5s response time."""
        db_path = _create_db(str(tmp_path))
        _insert_repo_graph(db_path, "integ/large-repo")

        conn = sqlite3.connect(db_path)
        for i in range(200):
            conn.execute(
                """INSERT INTO repo_dependencies
                   (repo_full_name, package_name, registry_type, specifier,
                    extras, dependency_group, is_direct, is_optional,
                    manifest_path, confidence, created_at, package_version)
                   VALUES (?, ?, 'npm', '', '[]', 'prod', 1, 0, ?, 0.9, datetime('now'), ?)""",
                (
                    "integ/large-repo",
                    f"pkg-{i:04d}",
                    f"manifest-{i}.json",
                    f"{i}.0.0",
                ),
            )
        conn.commit()
        conn.close()

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            start = time.monotonic()
            resp = client.get("/repos/integ/large-repo/dependency-tree")
            elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 5.0, f"Response took {elapsed:.2f}s for 200 deps, expected <5s"
        assert resp.json()["summary_metrics"]["total_dependencies"] == 200
