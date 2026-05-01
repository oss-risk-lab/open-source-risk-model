#!/usr/bin/env python3
"""Build Phase 5 demo data for a repository.

Reads the existing graph for a repo from repo_graphs, preserves all existing
nodes (repo, risk_factor, maintainer, release, registry), and adds realistic
`package` type nodes with proper metadata so that the Phase 4/5 insight
pipeline produces meaningful output for every panel.

Usage:
    python scripts/build_phase5_demo.py [owner/repo]

Default repo: psf/requests
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = "data/graphs.db"

# ---------------------------------------------------------------------------
# Realistic dependency data for psf/requests
# ---------------------------------------------------------------------------

PACKAGE_NODES = [
    # Direct dependencies (depth=1)
    {
        "package_name": "urllib3",
        "dependency_scope": "runtime",
        "scope_confidence": "high",
        "vulnerability_count": 2,
        "risk_score": 45.0,
        "depth": 1,
    },
    {
        "package_name": "certifi",
        "dependency_scope": "runtime",
        "scope_confidence": "high",
        "vulnerability_count": 1,
        "risk_score": 30.0,
        "depth": 1,
    },
    {
        "package_name": "idna",
        "dependency_scope": "runtime",
        "scope_confidence": "high",
        "vulnerability_count": 0,
        "risk_score": 15.0,
        "depth": 1,
    },
    {
        "package_name": "charset-normalizer",
        "dependency_scope": "runtime",
        "scope_confidence": "high",
        "vulnerability_count": 0,
        "risk_score": 20.0,
        "depth": 1,
    },
    # Transitive dependencies (depth=2)
    {
        "package_name": "h11",
        "dependency_scope": "runtime",
        "scope_confidence": "medium",
        "vulnerability_count": 0,
        "risk_score": 25.0,
        "depth": 2,
    },
    {
        "package_name": "sniffio",
        "dependency_scope": "runtime",
        "scope_confidence": "low",
        "vulnerability_count": 0,
        "risk_score": 10.0,
        "depth": 2,
    },
    {
        "package_name": "brotli",
        "dependency_scope": "optional",
        "scope_confidence": "medium",
        "vulnerability_count": 1,
        "risk_score": 35.0,
        "depth": 2,
    },
    {
        "package_name": "PySocks",
        "dependency_scope": "optional",
        "scope_confidence": "medium",
        "vulnerability_count": 0,
        "risk_score": 40.0,
        "depth": 2,
    },
    # Additional interesting dependencies
    {
        "package_name": "cryptography",
        "dependency_scope": "runtime",
        "scope_confidence": "high",
        "vulnerability_count": 3,
        "risk_score": 72.0,
        "depth": 1,
    },
    {
        "package_name": "pyOpenSSL",
        "dependency_scope": "runtime",
        "scope_confidence": "medium",
        "vulnerability_count": 1,
        "risk_score": 55.0,
        "depth": 2,
    },
    {
        "package_name": "setuptools",
        "dependency_scope": "build",
        "scope_confidence": "high",
        "vulnerability_count": 2,
        "risk_score": 60.0,
        "depth": 1,
    },
]


def _make_package_node(pkg: dict) -> dict:
    """Create a graph node dict for a package dependency."""
    name = pkg["package_name"]
    depth = pkg["depth"]
    dep_type = "direct" if depth == 1 else "transitive"
    now = datetime.now(timezone.utc).isoformat()

    return {
        "id": f"package:{name}",
        "type": "package",
        "label": name,
        "metadata": {
            "package_name": name,
            "dependency_scope": pkg["dependency_scope"],
            "scope_confidence": pkg["scope_confidence"],
            "vulnerability_count": pkg["vulnerability_count"],
            "risk_score": pkg["risk_score"],
            "depth": depth,
            "dependency_type": dep_type,
        },
        "provenance": {
            "source": "phase5_demo_seeder",
            "fetched_at": now,
            "data_confidence": 0.9,
        },
    }


def _make_depends_on_edge(repo_id: str, parent_id: str, pkg_id: str, depth: int) -> dict:
    """Create a DEPENDS_ON edge from parent to package."""
    now = datetime.now(timezone.utc).isoformat()
    source = repo_id if depth == 1 else parent_id
    return {
        "source": source,
        "target": pkg_id,
        "relationship_type": "depends_on",
        "metadata": {"dependency_type": "direct" if depth == 1 else "transitive"},
        "provenance": {
            "source": "phase5_demo_seeder",
            "established_at": now,
        },
    }


def main() -> None:
    repo = sys.argv[1] if len(sys.argv) > 1 else "psf/requests"
    print(f"=== Phase 5 Demo Seeder for {repo} ===\n")

    # Read existing graph
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT graph_json FROM repo_graphs WHERE repo_full_name = ?", (repo,)
    )
    row = cursor.fetchone()

    if row is None:
        print(f"ERROR: No existing graph found for {repo} in {DB_PATH}")
        conn.close()
        sys.exit(1)

    graph = json.loads(row[0])
    existing_nodes = graph.get("nodes", [])
    existing_edges = graph.get("edges", [])
    metadata = graph.get("metadata", {})

    # Count existing node types
    existing_types: dict[str, int] = {}
    for n in existing_nodes:
        t = n.get("type", "unknown")
        existing_types[t] = existing_types.get(t, 0) + 1

    print(f"Existing graph: {len(existing_nodes)} nodes, {len(existing_edges)} edges")
    print(f"  Node types: {existing_types}")

    # Remove any existing package nodes (idempotent re-run)
    existing_pkg_ids = {n["id"] for n in existing_nodes if n.get("type") == "package"}
    filtered_nodes = [n for n in existing_nodes if n.get("type") != "package"]
    filtered_edges = [
        e for e in existing_edges
        if e.get("target") not in existing_pkg_ids
        and e.get("source") not in existing_pkg_ids
    ]

    if existing_pkg_ids:
        print(f"  Removed {len(existing_pkg_ids)} existing package nodes (idempotent)")

    # Find repo node ID for edge creation
    repo_node_id = None
    for n in filtered_nodes:
        if n.get("type") == "repo":
            repo_node_id = n["id"]
            break

    if repo_node_id is None:
        print("ERROR: No repo node found in graph")
        conn.close()
        sys.exit(1)

    # Build new package nodes and edges
    new_nodes = []
    new_edges = []
    # For transitive deps, pick a plausible parent
    # urllib3 is a direct dep that could pull in transitive deps
    direct_parent_map = {
        "h11": "package:urllib3",
        "sniffio": "package:urllib3",
        "brotli": "package:urllib3",
        "PySocks": "package:urllib3",
        "pyOpenSSL": "package:cryptography",
    }

    for pkg in PACKAGE_NODES:
        node = _make_package_node(pkg)
        new_nodes.append(node)

        parent_id = direct_parent_map.get(pkg["package_name"], repo_node_id)
        edge = _make_depends_on_edge(repo_node_id, parent_id, node["id"], pkg["depth"])
        new_edges.append(edge)

    # Merge
    all_nodes = filtered_nodes + new_nodes
    all_edges = filtered_edges + new_edges

    updated_graph = {
        "nodes": all_nodes,
        "edges": all_edges,
        "metadata": metadata,
    }

    # Save back
    now = datetime.now(timezone.utc).isoformat()
    graph_json = json.dumps(updated_graph)
    conn.execute(
        """
        UPDATE repo_graphs
        SET graph_json = ?,
            node_count = ?,
            edge_count = ?,
            updated_at = ?
        WHERE repo_full_name = ?
        """,
        (graph_json, len(all_nodes), len(all_edges), now, repo),
    )
    conn.commit()
    conn.close()

    # Summary
    print(f"\nAdded {len(new_nodes)} package nodes:")
    for pkg in PACKAGE_NODES:
        dep_type = "direct" if pkg["depth"] == 1 else "transitive"
        vuln = f", {pkg['vulnerability_count']} CVE(s)" if pkg["vulnerability_count"] > 0 else ""
        print(
            f"  {pkg['package_name']:20s}  scope={pkg['dependency_scope']:8s}  "
            f"confidence={pkg['scope_confidence']:6s}  risk={pkg['risk_score']:5.1f}  "
            f"depth={pkg['depth']}  ({dep_type}){vuln}"
        )

    print(f"\nAdded {len(new_edges)} depends_on edges")
    print(f"\nUpdated graph: {len(all_nodes)} nodes, {len(all_edges)} edges")
    print(f"\nDone! Graph for {repo} is now Phase 5 ready.")


if __name__ == "__main__":
    main()
