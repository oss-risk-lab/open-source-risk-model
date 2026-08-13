"""
Regression test for fresh-database CVE schema.

Reproduces the bug where init_database ran _migrate_schema BEFORE the
CREATE TABLE statements, so on a fresh database the repo_cves migration
was skipped and the table was created without ghsa_id/cve_aliases —
causing graph_repo's CVE insert to fail with:
    sqlite3.OperationalError: table repo_cves has no column named ghsa_id

This hit every deploy on Render, where the DB is recreated on each deploy.
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

from src.open_source_risk_model.graph.schema import (
    Graph,
    Node,
    Edge,
    NodeType,
    EdgeType,
)
from src.open_source_risk_model.persistence.db import init_database, get_connection
from src.open_source_risk_model.persistence.graph_repo import GraphRepository


def test_fresh_db_repo_cves_has_migrated_columns(tmp_path):
    """A freshly initialized DB must include ghsa_id and cve_aliases on repo_cves."""
    db_path = os.path.join(tmp_path, "fresh.db")
    init_database(db_path)

    conn = get_connection(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(repo_cves)")}
    finally:
        conn.close()

    assert "ghsa_id" in columns
    assert "cve_aliases" in columns


def test_fresh_db_save_graph_with_cve_persists(tmp_path):
    """save_graph with a CVE node must persist against a fresh DB (no schema error)."""
    db_path = os.path.join(tmp_path, "fresh.db")
    init_database(db_path)

    now = datetime.now(timezone.utc).isoformat()
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={"url": "https://github.com/test/repo"},
        provenance={"source": "github_api", "fetched_at": now, "data_confidence": 1.0},
    )
    release_node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={"tag_name": "v1.0.0", "published_at": now},
        provenance={"source": "github_api", "fetched_at": now, "data_confidence": 1.0},
    )
    cve_node = Node(
        id="cve:CVE-2024-1234",
        type=NodeType.CVE,
        label="CVE-2024-1234",
        metadata={
            "cve_id": "CVE-2024-1234",
            "severity": "HIGH",
            "cvss_score": 7.5,
            "ghsa_id": "GHSA-xxxx-yyyy-zzzz",
            "aliases": ["CVE-2024-1234", "GHSA-xxxx-yyyy-zzzz"],
        },
        provenance={"source": "osv", "fetched_at": now, "data_confidence": 0.9},
    )
    has_release = Edge(
        source="repo:test/repo",
        target="release:test/repo:v1.0.0",
        relationship_type=EdgeType.HAS_RELEASE,
        metadata={},
        provenance={"source": "github_api", "established_at": now, "confidence": 1.0},
    )
    has_cve = Edge(
        source="release:test/repo:v1.0.0",
        target="cve:CVE-2024-1234",
        relationship_type=EdgeType.HAS_CVE,
        metadata={},
        provenance={"source": "osv", "established_at": now, "confidence": 0.9},
    )
    graph = Graph(
        nodes=[repo_node, release_node, cve_node],
        edges=[has_release, has_cve],
        metadata={"schema_version": "1.0", "generated_at": now},
    )

    repo = GraphRepository(db_path)
    # Before the fix this raised sqlite3.OperationalError: no column named ghsa_id
    repo.save_graph("test/repo", graph, generation_time_ms=1)

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT cve_id, ghsa_id, cve_aliases FROM repo_cves WHERE repo_full_name = ?",
            ("test/repo",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "CVE-2024-1234"
    assert row[1] == "GHSA-xxxx-yyyy-zzzz"
    assert "GHSA-xxxx-yyyy-zzzz" in row[2]
