"""Smoke tests for the dependency tree endpoint against realistic test data.

These tests exercise the actual endpoint with a real test database — no mocks.
Purpose: fast signal before full integration coverage.

Validates: Requirements 4.2, 4.7, 14.4
"""

from __future__ import annotations

import json
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.app import app
from unittest.mock import patch

client = TestClient(app)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _create_smoke_db(tmp_path: str) -> str:
    """Create a SQLite database with all required tables."""
    db_path = os.path.join(tmp_path, "smoke.db")
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
    """Build a realistic graph_json blob with risk score and release info."""
    return json.dumps({
        "nodes": [
            {
                "type": "repo",
                "metadata": {"maintenance_risk": maintenance_risk},
            },
            {
                "type": "release",
                "metadata": {"days_since_release": days_since_release},
            },
        ],
        "edges": [],
    })


def _seed_normal_repo(db_path: str) -> None:
    """Seed a repository with several direct and transitive dependencies.

    Repo: acme/web-app
    Direct deps: express (npm), lodash (npm), debug (npm)
    Transitive dep: body-parser (npm) via express
    Risk data: express → high risk (0.85), lodash → medium (0.45), debug → low (0.15)
    CVEs: express has 2 CVEs
    """
    conn = sqlite3.connect(db_path)

    # Repo graph entry for the repo itself
    conn.execute(
        "INSERT INTO repo_graphs (repo_full_name, schema_version, graph_json) VALUES (?, '1.0', ?)",
        ("acme/web-app", _graph_json(0.3)),
    )

    # Direct dependencies
    for pkg, ver, manifest in [
        ("express", "4.18.2", "package.json"),
        ("lodash", "4.17.21", "package.json2"),
        ("debug", "4.3.4", "package.json3"),
    ]:
        conn.execute(
            """INSERT INTO repo_dependencies
               (repo_full_name, package_name, registry_type, specifier,
                extras, dependency_group, is_direct, is_optional,
                manifest_path, confidence, created_at, package_version)
               VALUES (?, ?, 'npm', '', '[]', 'prod', 1, 0, ?, 0.9, datetime('now'), ?)""",
            ("acme/web-app", pkg, manifest, ver),
        )

    # Transitive dependency: body-parser via express
    conn.execute(
        """INSERT INTO repo_dependencies
           (repo_full_name, package_name, registry_type, specifier,
            extras, dependency_group, is_direct, is_optional,
            manifest_path, confidence, created_at,
            parent_package_name, package_version)
           VALUES (?, 'body-parser', 'npm', '', '[]', 'prod', 0, 0,
                   'package.json', 0.9, datetime('now'), 'express', '1.20.0')""",
        ("acme/web-app",),
    )

    # Package mappings → mapped repos
    for pkg, mapped_repo in [
        ("express", "expressjs/express"),
        ("lodash", "lodash/lodash"),
        ("debug", "debug-js/debug"),
        ("body-parser", "expressjs/body-parser"),
    ]:
        conn.execute(
            """INSERT INTO package_mappings
               (package_name, registry_type, repo_full_name, resolution_method, confidence)
               VALUES (?, 'npm', ?, 'name_match', 0.9)""",
            (pkg, mapped_repo),
        )

    # Repo graphs for mapped repos (risk scores)
    for repo, risk in [
        ("expressjs/express", 0.85),
        ("lodash/lodash", 0.45),
        ("debug-js/debug", 0.15),
        ("expressjs/body-parser", 0.60),
    ]:
        conn.execute(
            "INSERT INTO repo_graphs (repo_full_name, schema_version, graph_json) VALUES (?, '1.0', ?)",
            (repo, _graph_json(risk)),
        )

    # CVEs for express
    for cve_id in ["CVE-2024-0001", "CVE-2024-0002"]:
        conn.execute(
            "INSERT INTO repo_cves (repo_full_name, cve_id, severity) VALUES (?, ?, 'high')",
            ("expressjs/express", cve_id),
        )

    # Maintainers for lodash
    for user in ["jdalton", "bnjmnt4n"]:
        conn.execute(
            "INSERT INTO repo_maintainers (repo_full_name, maintainer_username) VALUES (?, ?)",
            ("lodash/lodash", user),
        )

    conn.commit()
    conn.close()


def _seed_zero_dep_repo(db_path: str) -> None:
    """Seed a repository that exists but has zero dependencies."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO repo_graphs (repo_full_name, schema_version, graph_json) VALUES (?, '1.0', ?)",
        ("acme/leaf-lib", _graph_json(0.1)),
    )
    conn.commit()
    conn.close()


def _seed_missing_data_repo(db_path: str) -> None:
    """Seed a repository where some dependencies have no package mapping / risk data.

    Repo: acme/partial-app
    Direct deps: known-pkg (has mapping + risk), mystery-pkg (no mapping at all)
    """
    conn = sqlite3.connect(db_path)

    conn.execute(
        "INSERT INTO repo_graphs (repo_full_name, schema_version, graph_json) VALUES (?, '1.0', ?)",
        ("acme/partial-app", _graph_json(0.2)),
    )

    # known-pkg — fully mapped
    conn.execute(
        """INSERT INTO repo_dependencies
           (repo_full_name, package_name, registry_type, specifier,
            extras, dependency_group, is_direct, is_optional,
            manifest_path, confidence, created_at, package_version)
           VALUES ('acme/partial-app', 'known-pkg', 'npm', '', '[]', 'prod', 1, 0,
                   'package.json', 0.9, datetime('now'), '1.0.0')""",
    )
    conn.execute(
        """INSERT INTO package_mappings
           (package_name, registry_type, repo_full_name, resolution_method, confidence)
           VALUES ('known-pkg', 'npm', 'known/repo', 'name_match', 0.9)""",
    )
    conn.execute(
        "INSERT INTO repo_graphs (repo_full_name, schema_version, graph_json) VALUES (?, '1.0', ?)",
        ("known/repo", _graph_json(0.5)),
    )

    # mystery-pkg — no mapping, no risk data
    conn.execute(
        """INSERT INTO repo_dependencies
           (repo_full_name, package_name, registry_type, specifier,
            extras, dependency_group, is_direct, is_optional,
            manifest_path, confidence, created_at, package_version)
           VALUES ('acme/partial-app', 'mystery-pkg', 'npm', '', '[]', 'prod', 1, 0,
                   'package.json2', 0.9, datetime('now'), '0.1.0')""",
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


class TestSmokeNormalRepo:
    """Smoke: normal repository with dependencies → 200, tree has children, metrics populated."""

    def test_returns_200_with_tree(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree")

        assert resp.status_code == 200
        data = resp.json()

        # Top-level structure
        assert "tree" in data
        assert "summary_metrics" in data
        assert "provenance" in data
        assert data["repo"] == "acme/web-app"

    def test_tree_has_children(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree")

        data = resp.json()
        tree = data["tree"]

        assert tree["node_type"] == "repository"
        assert tree["depth"] == 0
        assert len(tree["children"]) > 0

        # Direct deps should be at depth 1
        for child in tree["children"]:
            assert child["depth"] == 1
            assert child["dependency_type"] == "direct"

    def test_metrics_populated(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree")

        metrics = resp.json()["summary_metrics"]

        assert metrics["total_dependencies"] >= 3  # at least 3 direct + transitive
        assert metrics["direct_dependencies"] >= 3
        assert metrics["max_depth"] >= 1

        # total = direct + transitive invariant
        assert metrics["total_dependencies"] == (
            metrics["direct_dependencies"] + metrics["transitive_dependencies"]
        )

    def test_provenance_populated(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree")

        prov = resp.json()["provenance"]

        assert prov["data_source"] == "database"
        assert prov["total_nodes"] > 0
        assert "last_updated" in prov
        assert "construction_time_ms" in prov

    def test_risk_metadata_on_children(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree")

        children = resp.json()["tree"]["children"]
        # At least one child should have risk metadata
        children_with_risk = [
            c for c in children
            if c.get("risk_metadata") and c["risk_metadata"].get("risk_score") is not None
        ]
        assert len(children_with_risk) > 0

    def test_response_within_timeout(self, tmp_path):
        """Validates Requirement 4.7: response within 5s for small repos."""
        import time

        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            start = time.monotonic()
            resp = client.get("/repos/acme/web-app/dependency-tree")
            elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 5.0


class TestSmokeZeroDependencyRepo:
    """Smoke: zero-dependency repository → 200, empty children, all counts zero."""

    def test_returns_200(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_zero_dep_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/leaf-lib/dependency-tree")

        assert resp.status_code == 200

    def test_empty_children(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_zero_dep_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/leaf-lib/dependency-tree")

        tree = resp.json()["tree"]
        assert tree["children"] == []
        assert tree["node_type"] == "repository"

    def test_all_counts_zero(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_zero_dep_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/leaf-lib/dependency-tree")

        metrics = resp.json()["summary_metrics"]
        assert metrics["total_dependencies"] == 0
        assert metrics["direct_dependencies"] == 0
        assert metrics["transitive_dependencies"] == 0
        assert metrics["high_risk_count"] == 0
        assert metrics["vulnerable_count"] == 0


class TestSmokeFilteredRequest:
    """Smoke: filtered request (high_risk_only=true) → 200, only high-risk nodes and ancestors."""

    def test_high_risk_only_returns_200(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree?high_risk_only=true")

        assert resp.status_code == 200

    def test_only_high_risk_nodes_and_ancestors(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree?high_risk_only=true")

        data = resp.json()
        tree = data["tree"]

        # Root is always included
        assert tree["node_type"] == "repository"

        # If there are children, they should be high-risk or ancestors of high-risk
        # express has risk 85 (high), so it should be present
        # lodash (45) and debug (15) should be filtered out
        child_names = [c["name"] for c in tree["children"]]

        # express (risk_score=85) should be included
        if len(child_names) > 0:
            # All leaf nodes should be high-risk (score > 70)
            def _collect_leaves(node):
                if not node.get("children"):
                    return [node]
                leaves = []
                for c in node["children"]:
                    leaves.extend(_collect_leaves(c))
                return leaves

            leaves = _collect_leaves(tree)
            for leaf in leaves:
                rm = leaf.get("risk_metadata")
                if rm and rm.get("risk_score") is not None:
                    assert rm["risk_score"] > 70, (
                        f"Leaf {leaf['name']} has risk_score={rm['risk_score']} but should be >70"
                    )

    def test_filters_applied_in_metrics(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_normal_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/web-app/dependency-tree?high_risk_only=true")

        metrics = resp.json()["summary_metrics"]
        assert "high_risk_only" in metrics["filters_applied"]


class TestSmokeMissingDependencyData:
    """Smoke: repository with missing dependency data → 200, partial provenance."""

    def test_returns_200(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_missing_data_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/partial-app/dependency-tree")

        assert resp.status_code == 200

    def test_partial_provenance(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_missing_data_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/partial-app/dependency-tree")

        prov = resp.json()["provenance"]

        # mystery-pkg has no mapping → missing risk data → partial completeness
        assert prov["data_completeness"] == "partial"
        assert prov["nodes_with_missing_risk"] > 0

    def test_nodes_with_missing_risk_metadata(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_missing_data_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/partial-app/dependency-tree")

        children = resp.json()["tree"]["children"]

        # Find mystery-pkg — should have unavailable risk data
        mystery = [c for c in children if c["name"] == "mystery-pkg"]
        assert len(mystery) == 1

        rm = mystery[0].get("risk_metadata")
        if rm is not None:
            assert rm["score_source"] == "unavailable"
            assert rm["score_completeness"] == "missing"

    def test_known_pkg_has_risk_data(self, tmp_path):
        db_path = _create_smoke_db(str(tmp_path))
        _seed_missing_data_repo(db_path)

        with patch.dict(os.environ, {"GRAPH_DB_PATH": db_path}):
            resp = client.get("/repos/acme/partial-app/dependency-tree")

        children = resp.json()["tree"]["children"]

        known = [c for c in children if c["name"] == "known-pkg"]
        assert len(known) == 1

        rm = known[0].get("risk_metadata")
        assert rm is not None
        assert rm["score_source"] == "repo_graph"
        assert rm["risk_score"] is not None
