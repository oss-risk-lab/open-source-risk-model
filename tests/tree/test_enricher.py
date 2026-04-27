"""Unit tests for RiskMetadataEnricher."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from open_source_risk_model.tree.enricher import RiskMetadataEnricher
from open_source_risk_model.tree.models import TreeNode


# ======================================================================
# Helpers
# ======================================================================


def _create_test_db(
    *,
    package_mappings: list[tuple] | None = None,
    repo_graphs: list[dict] | None = None,
    repo_cves: list[tuple] | None = None,
    repo_maintainers: list[tuple] | None = None,
) -> str:
    """Create a temporary SQLite database with test data.

    Returns the path to the database file.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE package_mappings (
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            repo_full_name TEXT,
            resolution_method TEXT NOT NULL DEFAULT 'test',
            confidence REAL NOT NULL DEFAULT 1.0,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT '2024-01-01T00:00:00Z',
            updated_at TEXT NOT NULL DEFAULT '2024-01-01T00:00:00Z',
            PRIMARY KEY (package_name, registry_type)
        );

        CREATE TABLE repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            graph_json TEXT NOT NULL,
            schema_version TEXT NOT NULL DEFAULT '1.0',
            node_count INTEGER NOT NULL DEFAULT 0,
            edge_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT '2024-01-01T00:00:00Z',
            updated_at TEXT NOT NULL DEFAULT '2024-01-15T10:30:00Z',
            data_sources TEXT NOT NULL DEFAULT '[]',
            warnings TEXT,
            generation_time_ms INTEGER DEFAULT 0
        );

        CREATE TABLE repo_cves (
            repo_full_name TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'UNKNOWN',
            cvss_score REAL,
            affected_releases TEXT,
            PRIMARY KEY (repo_full_name, cve_id)
        );

        CREATE TABLE repo_maintainers (
            repo_full_name TEXT NOT NULL,
            maintainer_username TEXT NOT NULL,
            contribution_fraction REAL NOT NULL DEFAULT 0.0,
            commit_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (repo_full_name, maintainer_username)
        );
    """)

    if package_mappings:
        conn.executemany(
            "INSERT INTO package_mappings (package_name, registry_type, repo_full_name) VALUES (?, ?, ?)",
            package_mappings,
        )

    if repo_graphs:
        for rg in repo_graphs:
            conn.execute(
                "INSERT INTO repo_graphs (repo_full_name, graph_json, node_count, edge_count) VALUES (?, ?, ?, ?)",
                (rg["repo"], rg["graph_json"], rg.get("node_count", 1), rg.get("edge_count", 0)),
            )

    if repo_cves:
        conn.executemany(
            "INSERT INTO repo_cves (repo_full_name, cve_id, severity) VALUES (?, ?, ?)",
            repo_cves,
        )

    if repo_maintainers:
        conn.executemany(
            "INSERT INTO repo_maintainers (repo_full_name, maintainer_username, contribution_fraction, commit_count) VALUES (?, ?, ?, ?)",
            repo_maintainers,
        )

    conn.commit()
    conn.close()
    return db_path


def _make_graph_json(
    repo: str,
    maintenance_risk: float | None = None,
    days_since_release: int | None = None,
) -> str:
    """Build a minimal graph JSON with a repo node and optional release node."""
    nodes = []
    repo_meta: dict = {}
    if maintenance_risk is not None:
        repo_meta["maintenance_risk"] = maintenance_risk
    nodes.append({"id": f"repo:{repo}", "type": "repo", "label": repo, "metadata": repo_meta})

    if days_since_release is not None:
        nodes.append({
            "id": f"release:{repo}:latest",
            "type": "release",
            "label": "latest",
            "metadata": {"days_since_release": days_since_release},
        })

    return json.dumps({"nodes": nodes, "edges": []})


def _make_node(name: str, ecosystem: str = "npm", version: str = "1.0.0") -> TreeNode:
    """Create a package TreeNode with a canonical ID."""
    return TreeNode(
        id=f"pkg:{ecosystem}/{name}@{version}",
        node_type="package",
        name=name,
        version=version,
        ecosystem=ecosystem,
    )


# ======================================================================
# Tests
# ======================================================================


class TestBatchEnrichmentWithFullData:
    """Test enrichment when package_mappings and repo_graphs have full data."""

    def test_enriches_with_risk_score_and_vuln_count(self):
        db_path = _create_test_db(
            package_mappings=[("lodash", "npm", "lodash/lodash")],
            repo_graphs=[{
                "repo": "lodash/lodash",
                "graph_json": _make_graph_json("lodash/lodash", maintenance_risk=0.45, days_since_release=30),
            }],
            repo_cves=[
                ("lodash/lodash", "CVE-2021-1234", "HIGH"),
                ("lodash/lodash", "CVE-2021-5678", "MEDIUM"),
            ],
            repo_maintainers=[
                ("lodash/lodash", "jdalton", 0.8, 500),
                ("lodash/lodash", "contributor2", 0.2, 100),
            ],
        )

        node = _make_node("lodash", "npm", "4.17.21")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata is not None
        assert node.risk_metadata.risk_score == 45.0
        assert node.risk_metadata.risk_level == "medium"
        assert node.risk_metadata.vulnerability_count == 2
        assert node.risk_metadata.release_recency_days == 30
        assert node.risk_metadata.maintainer_count == 2
        assert node.risk_metadata.score_source == "repo_graph"
        assert node.risk_metadata.score_completeness == "full"

        os.unlink(db_path)

    def test_multiple_nodes_enriched(self):
        db_path = _create_test_db(
            package_mappings=[
                ("lodash", "npm", "lodash/lodash"),
                ("express", "npm", "expressjs/express"),
            ],
            repo_graphs=[
                {"repo": "lodash/lodash", "graph_json": _make_graph_json("lodash/lodash", maintenance_risk=0.3)},
                {"repo": "expressjs/express", "graph_json": _make_graph_json("expressjs/express", maintenance_risk=0.8)},
            ],
        )

        nodes = [
            _make_node("lodash", "npm", "4.17.21"),
            _make_node("express", "npm", "4.18.0"),
        ]
        RiskMetadataEnricher.enrich_nodes(nodes, db_path)

        assert nodes[0].risk_metadata.risk_score == 30.0
        assert nodes[0].risk_metadata.risk_level == "low"
        assert nodes[1].risk_metadata.risk_score == 80.0
        assert nodes[1].risk_metadata.risk_level == "high"

        os.unlink(db_path)


class TestNoPackageMapping:
    """Test enrichment when package_mappings has no entry for a package."""

    def test_no_mapping_sets_unavailable(self):
        db_path = _create_test_db()

        node = _make_node("unknown-pkg", "npm", "1.0.0")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata is not None
        assert node.risk_metadata.risk_score is None
        assert node.risk_metadata.risk_level is None
        assert node.risk_metadata.vulnerability_count == 0
        assert node.risk_metadata.score_source == "unavailable"
        assert node.risk_metadata.score_completeness == "missing"

        os.unlink(db_path)


class TestPartialRepoGraphData:
    """Test enrichment when repo_graphs has partial data."""

    def test_mapping_exists_but_no_repo_graph(self):
        """Mapping exists in package_mappings but no entry in repo_graphs."""
        db_path = _create_test_db(
            package_mappings=[("lodash", "npm", "lodash/lodash")],
        )

        node = _make_node("lodash", "npm", "4.17.21")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata is not None
        assert node.risk_metadata.risk_score is None
        assert node.risk_metadata.score_source == "unavailable"
        assert node.risk_metadata.score_completeness == "missing"

        os.unlink(db_path)

    def test_repo_graph_without_risk_score(self):
        """repo_graphs entry exists but no maintenance_risk in graph JSON."""
        graph_json = json.dumps({"nodes": [{"id": "repo:x/y", "type": "repo", "label": "x/y", "metadata": {}}], "edges": []})
        db_path = _create_test_db(
            package_mappings=[("lodash", "npm", "x/y")],
            repo_graphs=[{"repo": "x/y", "graph_json": graph_json}],
        )

        node = _make_node("lodash", "npm", "4.17.21")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata.risk_score is None
        assert node.risk_metadata.score_source == "unavailable"
        assert node.risk_metadata.score_completeness == "missing"

        os.unlink(db_path)

    def test_repo_graph_with_score_but_no_optional_fields(self):
        """repo_graphs has risk score but no release/maintainer data → partial."""
        db_path = _create_test_db(
            package_mappings=[("lodash", "npm", "lodash/lodash")],
            repo_graphs=[{
                "repo": "lodash/lodash",
                "graph_json": _make_graph_json("lodash/lodash", maintenance_risk=0.5),
            }],
            # No maintainers, no release recency
        )

        node = _make_node("lodash", "npm", "4.17.21")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata.risk_score == 50.0
        assert node.risk_metadata.score_source == "repo_graph"
        assert node.risk_metadata.score_completeness == "partial"
        assert node.risk_metadata.release_recency_days is None
        assert node.risk_metadata.maintainer_count is None

        os.unlink(db_path)


class TestRiskLevelClassification:
    """Test _classify_risk_level at boundary values."""

    def test_none_score(self):
        assert RiskMetadataEnricher._classify_risk_level(None) is None

    def test_zero_is_low(self):
        assert RiskMetadataEnricher._classify_risk_level(0) == "low"

    def test_30_is_low(self):
        assert RiskMetadataEnricher._classify_risk_level(30) == "low"

    def test_31_is_medium(self):
        assert RiskMetadataEnricher._classify_risk_level(31) == "medium"

    def test_70_is_medium(self):
        assert RiskMetadataEnricher._classify_risk_level(70) == "medium"

    def test_71_is_high(self):
        assert RiskMetadataEnricher._classify_risk_level(71) == "high"

    def test_100_is_high(self):
        assert RiskMetadataEnricher._classify_risk_level(100) == "high"


class TestEmptyNodeList:
    """Test enrichment with an empty node list."""

    def test_empty_list_returns_empty(self):
        db_path = _create_test_db()
        result = RiskMetadataEnricher.enrich_nodes([], db_path)
        assert result == []
        os.unlink(db_path)


class TestScoreSourceAndCompleteness:
    """Test that score_source and score_completeness are set correctly in each scenario."""

    def test_full_data(self):
        db_path = _create_test_db(
            package_mappings=[("pkg", "npm", "owner/repo")],
            repo_graphs=[{
                "repo": "owner/repo",
                "graph_json": _make_graph_json("owner/repo", maintenance_risk=0.6, days_since_release=10),
            }],
            repo_maintainers=[("owner/repo", "dev1", 1.0, 100)],
        )

        node = _make_node("pkg", "npm", "1.0.0")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata.score_source == "repo_graph"
        assert node.risk_metadata.score_completeness == "full"

        os.unlink(db_path)

    def test_partial_data(self):
        db_path = _create_test_db(
            package_mappings=[("pkg", "npm", "owner/repo")],
            repo_graphs=[{
                "repo": "owner/repo",
                "graph_json": _make_graph_json("owner/repo", maintenance_risk=0.6),
            }],
        )

        node = _make_node("pkg", "npm", "1.0.0")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata.score_source == "repo_graph"
        assert node.risk_metadata.score_completeness == "partial"

        os.unlink(db_path)

    def test_no_mapping(self):
        db_path = _create_test_db()

        node = _make_node("pkg", "npm", "1.0.0")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata.score_source == "unavailable"
        assert node.risk_metadata.score_completeness == "missing"

        os.unlink(db_path)

    def test_mapping_no_repo_graph(self):
        db_path = _create_test_db(
            package_mappings=[("pkg", "npm", "owner/repo")],
        )

        node = _make_node("pkg", "npm", "1.0.0")
        RiskMetadataEnricher.enrich_nodes([node], db_path)

        assert node.risk_metadata.score_source == "unavailable"
        assert node.risk_metadata.score_completeness == "missing"

        os.unlink(db_path)


class TestSharedCanonicalId:
    """Test that same canonical ID is enriched once and shared across multiple node instances."""

    def test_same_id_gets_same_metadata(self):
        db_path = _create_test_db(
            package_mappings=[("lodash", "npm", "lodash/lodash")],
            repo_graphs=[{
                "repo": "lodash/lodash",
                "graph_json": _make_graph_json("lodash/lodash", maintenance_risk=0.45, days_since_release=30),
            }],
            repo_cves=[("lodash/lodash", "CVE-2021-1234", "HIGH")],
        )

        # Two separate TreeNode instances with the same canonical ID
        node1 = _make_node("lodash", "npm", "4.17.21")
        node2 = _make_node("lodash", "npm", "4.17.21")
        assert node1 is not node2

        RiskMetadataEnricher.enrich_nodes([node1, node2], db_path)

        # Both should have identical metadata values
        assert node1.risk_metadata.risk_score == node2.risk_metadata.risk_score
        assert node1.risk_metadata.risk_level == node2.risk_metadata.risk_level
        assert node1.risk_metadata.vulnerability_count == node2.risk_metadata.vulnerability_count
        assert node1.risk_metadata.score_source == node2.risk_metadata.score_source
        assert node1.risk_metadata.score_completeness == node2.risk_metadata.score_completeness

        # But they should be separate RiskMetadata instances
        assert node1.risk_metadata is not node2.risk_metadata

        os.unlink(db_path)


class TestRepositoryNodeSkipped:
    """Test that repository root nodes are not enriched."""

    def test_repository_node_not_enriched(self):
        db_path = _create_test_db()

        root = TreeNode(id="owner/repo", node_type="repository", name="owner/repo", depth=0)
        RiskMetadataEnricher.enrich_nodes([root], db_path)

        assert root.risk_metadata is None

        os.unlink(db_path)
