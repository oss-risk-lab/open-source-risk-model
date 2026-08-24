"""
Regression test for the save_graph CVE UNIQUE-constraint crash.

A real graph (e.g. psf/requests) contains the SAME CVE attached to multiple
release nodes, i.e. several CVE nodes that resolve to the same primary key
(repo_full_name, cve_id). The index writer used a plain INSERT, so the second
row raised:
    sqlite3.IntegrityError: UNIQUE constraint failed:
        repo_cves.repo_full_name, repo_cves.cve_id
which rolled back the whole save and surfaced as HTTP 500
"Failed to persist repository scan" for every CVE-bearing repo scanned.

save_graph now aggregates CVE nodes by primary id (unioning affected releases)
and upserts, so duplicates merge instead of crashing.
"""

import json
import os
from datetime import datetime, timezone

from src.open_source_risk_model.graph.schema import (
    Graph,
    Node,
    Edge,
    NodeType,
    EdgeType,
)
from src.open_source_risk_model.persistence.db import init_database, get_connection
from src.open_source_risk_model.persistence.graph_repo import GraphRepository


def _now():
    return datetime.now(timezone.utc).isoformat()


def _graph_with_duplicate_cve():
    """Two releases, both affected by the SAME CVE -> two CVE nodes, one cve_id."""
    now = _now()
    repo = Node(
        id="repo:psf/requests", type=NodeType.REPO, label="psf/requests",
        metadata={"url": "https://github.com/psf/requests"},
        provenance={"source": "github_api", "fetched_at": now, "data_confidence": 1.0},
    )
    rel1 = Node(
        id="release:psf/requests:v2.32.1", type=NodeType.RELEASE, label="v2.32.1",
        metadata={"tag_name": "v2.32.1", "published_at": now},
        provenance={"source": "github_api", "fetched_at": now, "data_confidence": 1.0},
    )
    rel2 = Node(
        id="release:psf/requests:v2.32.2", type=NodeType.RELEASE, label="v2.32.2",
        metadata={"tag_name": "v2.32.2", "published_at": now},
        provenance={"source": "github_api", "fetched_at": now, "data_confidence": 1.0},
    )
    # Same CVE id, two distinct nodes (one per affected release).
    cve1 = Node(
        id="cve:CVE-2024-47081:v2.32.1", type=NodeType.CVE, label="CVE-2024-47081",
        metadata={"cve_id": "CVE-2024-47081", "severity": "HIGH", "cvss_score": 7.5},
        provenance={"source": "osv", "fetched_at": now, "data_confidence": 0.9},
    )
    cve2 = Node(
        id="cve:CVE-2024-47081:v2.32.2", type=NodeType.CVE, label="CVE-2024-47081",
        metadata={"cve_id": "CVE-2024-47081", "severity": "HIGH", "cvss_score": 7.5},
        provenance={"source": "osv", "fetched_at": now, "data_confidence": 0.9},
    )
    edges = [
        Edge(source="repo:psf/requests", target="release:psf/requests:v2.32.1",
             relationship_type=EdgeType.HAS_RELEASE, metadata={},
             provenance={"source": "github_api", "established_at": now, "confidence": 1.0}),
        Edge(source="repo:psf/requests", target="release:psf/requests:v2.32.2",
             relationship_type=EdgeType.HAS_RELEASE, metadata={},
             provenance={"source": "github_api", "established_at": now, "confidence": 1.0}),
        Edge(source="release:psf/requests:v2.32.1", target="cve:CVE-2024-47081:v2.32.1",
             relationship_type=EdgeType.HAS_CVE, metadata={},
             provenance={"source": "osv", "established_at": now, "confidence": 0.9}),
        Edge(source="release:psf/requests:v2.32.2", target="cve:CVE-2024-47081:v2.32.2",
             relationship_type=EdgeType.HAS_CVE, metadata={},
             provenance={"source": "osv", "established_at": now, "confidence": 0.9}),
    ]
    return Graph(nodes=[repo, rel1, rel2, cve1, cve2], edges=edges,
                 metadata={"schema_version": "1.0", "generated_at": now})


def test_save_graph_with_duplicate_cve_nodes_does_not_crash(tmp_path):
    db = os.path.join(tmp_path, "graphs.db")
    init_database(db)
    repo = GraphRepository(db)

    # Before the fix this raised DatabaseError (UNIQUE constraint failed).
    repo.save_graph("psf/requests", _graph_with_duplicate_cve(), generation_time_ms=1)

    conn = get_connection(db)
    try:
        rows = conn.execute(
            "SELECT cve_id, affected_releases FROM repo_cves WHERE repo_full_name = ?",
            ("psf/requests",),
        ).fetchall()
    finally:
        conn.close()

    # One merged row, with both releases unioned.
    assert len(rows) == 1
    assert rows[0][0] == "CVE-2024-47081"
    releases = json.loads(rows[0][1])
    assert set(releases) == {"v2.32.1", "v2.32.2"}


def test_save_graph_is_idempotent_on_resave(tmp_path):
    db = os.path.join(tmp_path, "graphs.db")
    init_database(db)
    repo = GraphRepository(db)
    g = _graph_with_duplicate_cve()

    repo.save_graph("psf/requests", g, generation_time_ms=1)
    # Re-saving must not crash and must not duplicate rows.
    repo.save_graph("psf/requests", g, generation_time_ms=1)

    conn = get_connection(db)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM repo_cves WHERE repo_full_name = ?", ("psf/requests",)
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1
