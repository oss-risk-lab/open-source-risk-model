#!/usr/bin/env python3
"""Debug and verify Phase 5 demo data for a repository.

Reads the graph for a repo, prints diagnostic info about package nodes,
then calls compute_repo_insight() and prints the full Phase 5 output
to verify all panels produce meaningful data.

Usage:
    python scripts/debug_phase5_demo_repo.py [owner/repo]

Default repo: psf/requests
"""

from __future__ import annotations

import json
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.open_source_risk_model.persistence.graph_repo import GraphRepository
from src.open_source_risk_model.insights.compute import compute_repo_insight


def _separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main() -> None:
    repo = sys.argv[1] if len(sys.argv) > 1 else "psf/requests"
    print(f"=== Phase 5 Debug for {repo} ===")

    graph_repo = GraphRepository(db_path="data/graphs.db")

    # ---------------------------------------------------------------
    # 1. Graph diagnostics
    # ---------------------------------------------------------------
    _separator("1. GRAPH DIAGNOSTICS")

    graph_data = graph_repo.get_graph(repo)
    if graph_data is None:
        print(f"ERROR: No graph found for {repo}")
        sys.exit(1)

    graph = graph_data.get("graph", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    print(f"Total nodes: {len(nodes)}")
    print(f"Total edges: {len(edges)}")

    # Node type breakdown
    type_counts: dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"Node types: {type_counts}")

    # Package node details
    pkg_nodes = [n for n in nodes if n.get("type") == "package"]
    print(f"\nPackage nodes: {len(pkg_nodes)}")

    if not pkg_nodes:
        print("WARNING: No package nodes found! Phase 4/5 will produce empty output.")
        print("Run scripts/build_phase5_demo.py first.")
        sys.exit(1)

    # Scope breakdown
    scope_counts: dict[str, int] = {}
    for n in pkg_nodes:
        scope = n.get("metadata", {}).get("dependency_scope", "unknown")
        scope_counts[scope] = scope_counts.get(scope, 0) + 1
    print(f"Scope breakdown: {scope_counts}")

    # Depth breakdown
    depth_counts: dict[int, int] = {}
    for n in pkg_nodes:
        depth = n.get("metadata", {}).get("depth", 0)
        depth_counts[depth] = depth_counts.get(depth, 0) + 1
    print(f"Depth breakdown: {depth_counts}")

    # Per-package summary
    print("\nPackage details:")
    for n in pkg_nodes:
        meta = n.get("metadata", {})
        print(
            f"  {meta.get('package_name', '?'):20s}  "
            f"scope={meta.get('dependency_scope', '?'):8s}  "
            f"conf={meta.get('scope_confidence', '?'):6s}  "
            f"risk={meta.get('risk_score', '?'):>5}  "
            f"vuln={meta.get('vulnerability_count', 0)}  "
            f"depth={meta.get('depth', '?')}"
        )

    # ---------------------------------------------------------------
    # 2. Compute insight
    # ---------------------------------------------------------------
    _separator("2. COMPUTE REPO INSIGHT")

    insight = compute_repo_insight(repo, graph_repo)
    insight_dict = insight.to_dict()

    # ---------------------------------------------------------------
    # 3. Phase 1-3 signals
    # ---------------------------------------------------------------
    _separator("3. PHASE 1-3: BASE SIGNALS")

    print(f"Base maintenance risk: {insight_dict.get('base_maintenance_risk')}")
    print(f"Base maintenance label: {insight_dict.get('base_maintenance_label')}")
    print(f"Graph signal score: {insight_dict.get('graph_signal_score')}")
    print(f"Graph signal label: {insight_dict.get('graph_signal_label')}")
    print(f"Reasons ({len(insight_dict.get('reasons', []))}):")
    for r in insight_dict.get("reasons", []):
        print(f"  - {r}")
    print(f"Direct signals ({len(insight_dict.get('direct_signals', []))}):")
    for s in insight_dict.get("direct_signals", []):
        print(f"  - {s['signal_name']}: {s['severity']} ({s['score_contribution']:.3f}) — {s['reason']}")

    # ---------------------------------------------------------------
    # 4. Phase 4: Scope-weighted risk
    # ---------------------------------------------------------------
    _separator("4. PHASE 4: SCOPE-WEIGHTED RISK")

    swr = insight_dict.get("scope_weighted_risk")
    if swr:
        print(f"scope_weighted_dependency_risk: {swr.get('scope_weighted_dependency_risk')}")
        print(f"risk_label: {swr.get('risk_label')}")
        print(f"scope_note: {swr.get('scope_note')}")
        print(f"confidence_note: {swr.get('confidence_note')}")
        top_drivers = swr.get("top_drivers", [])
        print(f"top_drivers ({len(top_drivers)}):")
        for d in top_drivers:
            print(f"  - {d.get('package')}: scope={d.get('scope')}, contribution={d.get('contribution')}")
    else:
        print("WARNING: scope_weighted_risk is None!")

    # ---------------------------------------------------------------
    # 5. Phase 5: Actionable Insights
    # ---------------------------------------------------------------
    _separator("5. PHASE 5: PRIORITY RECOMMENDATIONS")

    recs = insight_dict.get("priority_recommendations", [])
    print(f"Count: {len(recs)}")
    for r in recs:
        print(
            f"  [{r['priority_score']:.4f}] {r['package_name']:20s}  "
            f"scope={r['dependency_scope']:8s}  type={r['dependency_type']:10s}  "
            f"action=\"{r['action']}\""
        )
        print(f"           reason: {r['reason']}")

    _separator("6. PHASE 5: RISK CLUSTERS")

    clusters = insight_dict.get("risk_clusters", [])
    print(f"Count: {len(clusters)}")
    for c in clusters:
        print(
            f"  {c['cluster_name']:30s}  count={c['count']:2d}  "
            f"risk_contribution={c['risk_contribution']:.4f}  "
            f"examples={c['example_packages']}"
        )
        print(f"    summary: {c['summary']}")

    _separator("7. PHASE 5: RISK NARRATIVE")

    narrative = insight_dict.get("risk_narrative")
    if narrative:
        print(f"Summary: {narrative.get('summary')}")
        print(f"Key findings ({len(narrative.get('key_findings', []))}):")
        for f in narrative.get("key_findings", []):
            print(f"  - {f}")
        print(f"Recommendation: {narrative.get('recommendation')}")
    else:
        print("WARNING: risk_narrative is None!")

    _separator("8. PHASE 5: OVERALL CONFIDENCE")

    confidence = insight_dict.get("overall_confidence")
    if confidence:
        print(f"Score: {confidence.get('score')}")
        print(f"Label: {confidence.get('label')}")
        print(f"Explanation: {confidence.get('explanation')}")
    else:
        print("WARNING: overall_confidence is None!")

    # ---------------------------------------------------------------
    # Validation summary
    # ---------------------------------------------------------------
    _separator("VALIDATION SUMMARY")

    checks = {
        "Package nodes present": len(pkg_nodes) > 0,
        "scope_weighted_risk non-empty": swr is not None and swr.get("scope_weighted_dependency_risk", 0) > 0,
        "top_drivers non-empty": swr is not None and len(swr.get("top_drivers", [])) > 0,
        "priority_recommendations non-empty": len(recs) > 0,
        "risk_clusters present (4)": len(clusters) == 4,
        "risk_clusters have non-zero counts": any(c["count"] > 0 for c in clusters),
        "risk_narrative present": narrative is not None and len(narrative.get("summary", "")) > 0,
        "risk_narrative has key_findings": narrative is not None and len(narrative.get("key_findings", [])) > 0,
        "overall_confidence present": confidence is not None and confidence.get("score", 0) > 0,
        "reasons include scope-aware": any("runtime" in r.lower() or "scope" in r.lower() for r in insight_dict.get("reasons", [])),
    }

    all_pass = True
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {check}")

    print()
    if all_pass:
        print("ALL CHECKS PASSED — Phase 5 demo is fully functional!")
    else:
        print("SOME CHECKS FAILED — review output above for details.")

    # ---------------------------------------------------------------
    # Full JSON output (for API verification)
    # ---------------------------------------------------------------
    _separator("FULL API JSON OUTPUT")
    print(json.dumps(insight_dict, indent=2, default=str))


if __name__ == "__main__":
    main()
