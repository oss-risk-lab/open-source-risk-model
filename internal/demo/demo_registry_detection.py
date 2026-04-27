#!/usr/bin/env python3
"""
Demo script to show registry detection in action.

This script demonstrates the new registry detection feature by building
a graph for a repository and showing the detected registries.
"""

from src.open_source_risk_model.graph.builder import GraphBuilder
from src.open_source_risk_model.graph.schema import NodeType, EdgeType


def demo_registry_detection(repo_full_name: str):
    """
    Demonstrate registry detection for a given repository.
    
    Args:
        repo_full_name: Repository in owner/repo format
    """
    print(f"\n{'='*60}")
    print(f"Registry Detection Demo: {repo_full_name}")
    print(f"{'='*60}\n")
    
    # Minimal score data for demo
    score_data = {
        "repo": {"url": f"https://github.com/{repo_full_name}"},
        "overall": {
            "maintenance_risk": 0.3,
            "maintenance_label": "low",
            "coverage": 0.8,
            "confidence": "high",
        },
        "features": [],
        "top_drivers": [],
    }
    
    # Build graph
    print("Building graph...")
    builder = GraphBuilder(repo_full_name, score_data)
    graph = builder.build()
    
    # Find registry nodes
    registry_nodes = [n for n in graph.nodes if n.type == NodeType.REGISTRY]
    
    if registry_nodes:
        print(f"\n✓ Detected {len(registry_nodes)} package registry(ies):\n")
        
        for node in registry_nodes:
            print(f"  Registry Type: {node.metadata['registry_type']}")
            print(f"  Package Name:  {node.metadata['package_name']}")
            print(f"  Detected From: {node.metadata['detected_from']}")
            print(f"  Confidence:    {node.provenance['match_confidence']:.2f}")
            print()
        
        # Show edges
        published_as_edges = [e for e in graph.edges if e.relationship_type == EdgeType.PUBLISHED_AS]
        print(f"✓ Created {len(published_as_edges)} PUBLISHED_AS edge(s)")
        
    else:
        print("✗ No package registries detected")
        print("  (Repository may not have package manifest files)")
    
    # Show graph summary
    print(f"\nGraph Summary:")
    print(f"  Total Nodes: {len(graph.nodes)}")
    print(f"  Total Edges: {len(graph.edges)}")
    
    # Show node type breakdown
    node_types = {}
    for node in graph.nodes:
        node_type = node.type.value
        node_types[node_type] = node_types.get(node_type, 0) + 1
    
    print(f"\n  Node Types:")
    for node_type, count in sorted(node_types.items()):
        print(f"    {node_type}: {count}")
    
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    # Demo with different types of repositories
    
    # Python package (PyPI)
    demo_registry_detection("psf/requests")
    
    # JavaScript package (npm)
    # demo_registry_detection("expressjs/express")
    
    # Java package (Maven)
    # demo_registry_detection("spring-projects/spring-boot")
