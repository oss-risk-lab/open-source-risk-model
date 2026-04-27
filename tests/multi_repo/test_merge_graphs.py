"""Unit tests for merge_graphs() function."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from open_source_risk_model.graph.schema import Graph, Node, Edge, NodeType, EdgeType

# Import merge_graphs from api/app.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))
from app import merge_graphs


def _make_node(id: str, ntype: NodeType = NodeType.PACKAGE, label: str = "") -> Node:
    return Node(id=id, type=ntype, label=label or id, metadata={}, provenance={})


def _make_edge(src: str, tgt: str, etype: EdgeType = EdgeType.DEPENDS_ON) -> Edge:
    return Edge(source=src, target=tgt, relationship_type=etype, metadata={}, provenance={})


class TestMergeGraphsBasic:
    def test_empty_inputs(self):
        result = merge_graphs([], [])
        assert result == {"nodes": [], "edges": []}

    def test_single_graph_no_unmapped(self):
        g = Graph()
        g.add_node(_make_node("n1"))
        g.add_node(_make_node("n2"))
        g.add_edge(_make_edge("n1", "n2"))
        result = merge_graphs([("repo/a", g)], [])
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1
        node_ids = {n["id"] for n in result["nodes"]}
        assert node_ids == {"n1", "n2"}
        assert result["nodes"][0]["source_repos"] == ["repo/a"]

    def test_dedup_nodes_first_wins(self):
        g1 = Graph()
        g1.add_node(Node(id="shared", type=NodeType.PACKAGE, label="first", metadata={"v": 1}, provenance={}))
        g2 = Graph()
        g2.add_node(Node(id="shared", type=NodeType.PACKAGE, label="second", metadata={"v": 2}, provenance={}))
        result = merge_graphs([("repo/a", g1), ("repo/b", g2)], [])
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["label"] == "first"
        assert result["nodes"][0]["metadata"] == {"v": 1}
        assert sorted(result["nodes"][0]["source_repos"]) == ["repo/a", "repo/b"]

    def test_edge_dedup_same_type(self):
        g1 = Graph()
        g1.add_node(_make_node("a"))
        g1.add_node(_make_node("b"))
        g1.add_edge(_make_edge("a", "b", EdgeType.DEPENDS_ON))
        g2 = Graph()
        g2.add_node(_make_node("a"))
        g2.add_node(_make_node("b"))
        g2.add_edge(_make_edge("a", "b", EdgeType.DEPENDS_ON))
        result = merge_graphs([("r1", g1), ("r2", g2)], [])
        assert len(result["edges"]) == 1

    def test_edge_different_types_preserved(self):
        g1 = Graph()
        g1.add_node(_make_node("a"))
        g1.add_node(_make_node("b"))
        g1.add_edge(_make_edge("a", "b", EdgeType.DEPENDS_ON))
        g2 = Graph()
        g2.add_node(_make_node("a"))
        g2.add_node(_make_node("b"))
        g2.add_edge(_make_edge("a", "b", EdgeType.HAS_RELEASE))
        result = merge_graphs([("r1", g1), ("r2", g2)], [])
        assert len(result["edges"]) == 2
        edge_types = {e["relationship_type"] for e in result["edges"]}
        assert edge_types == {"depends_on", "has_release"}

    def test_unmapped_nodes_appended(self):
        result = merge_graphs([], [
            {"id": "pkg:flask", "type": "package", "label": "flask"},
            {"id": "pkg:boto3", "type": "package", "label": "boto3"},
        ])
        assert len(result["nodes"]) == 2
        ids = {n["id"] for n in result["nodes"]}
        assert ids == {"pkg:flask", "pkg:boto3"}
        for n in result["nodes"]:
            assert n["source_repos"] == []

    def test_unmapped_node_not_overwrite_existing(self):
        g = Graph()
        g.add_node(_make_node("pkg:flask", NodeType.PACKAGE, "flask-from-graph"))
        result = merge_graphs([("r1", g)], [{"id": "pkg:flask", "type": "package", "label": "flask-unmapped"}])
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["label"] == "flask-from-graph"

    def test_source_repos_no_duplicates(self):
        g = Graph()
        g.add_node(_make_node("n1"))
        result = merge_graphs([("repo/a", g), ("repo/a", g)], [])
        assert result["nodes"][0]["source_repos"] == ["repo/a"]

    def test_return_plain_dicts(self):
        g = Graph()
        g.add_node(_make_node("n1", NodeType.REPO, "my-repo"))
        g.add_edge(_make_edge("n1", "n1", EdgeType.HAS_RELEASE))
        result = merge_graphs([("r", g)], [])
        node = result["nodes"][0]
        assert isinstance(node, dict)
        assert node["type"] == "repo"
        edge = result["edges"][0]
        assert isinstance(edge, dict)
        assert edge["relationship_type"] == "has_release"
