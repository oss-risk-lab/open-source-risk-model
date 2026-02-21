"""
Unit tests for IndexRepository.

Tests cross-repo query operations:
- Maintainer queries
- CVE queries
- Package queries
- Shared maintainer queries
"""

import os
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
from src.open_source_risk_model.persistence.db import init_database
from src.open_source_risk_model.persistence.graph_repo import GraphRepository
from src.open_source_risk_model.persistence.index_repo import IndexRepository


def create_test_graph_with_maintainer(username, contribution_fraction=0.5, commit_count=100):
    """Helper to create a graph with a specific maintainer."""
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={"url": "https://github.com/test/repo"},
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    maintainer_node = Node(
        id=f"maintainer:{username}",
        type=NodeType.MAINTAINER,
        label=username,
        metadata={
            "username": username,
            "contribution_fraction": contribution_fraction,
            "commit_count": commit_count,
        },
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    edge = Edge(
        source="repo:test/repo",
        target=f"maintainer:{username}",
        relationship_type=EdgeType.MAINTAINED_BY,
        metadata={},
        provenance={"source": "github_api", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
    )
    
    return Graph(
        nodes=[repo_node, maintainer_node],
        edges=[edge],
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api"],
            "warnings": []
        }
    )


def create_test_graph_with_cve(cve_id, severity="HIGH", cvss_score=7.5):
    """Helper to create a graph with a specific CVE."""
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={"url": "https://github.com/test/repo"},
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    release_node = Node(
        id="release:test/repo:v1.0.0",
        type=NodeType.RELEASE,
        label="v1.0.0",
        metadata={"tag_name": "v1.0.0", "published_at": datetime.now(timezone.utc).isoformat()},
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    cve_node = Node(
        id=f"cve:{cve_id}",
        type=NodeType.CVE,
        label=cve_id,
        metadata={
            "cve_id": cve_id,
            "severity": severity,
            "cvss_score": cvss_score,
        },
        provenance={"source": "osv", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    edges = [
        Edge(
            source="repo:test/repo",
            target="release:test/repo:v1.0.0",
            relationship_type=EdgeType.HAS_RELEASE,
            metadata={},
            provenance={"source": "github_api", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
        ),
        Edge(
            source="release:test/repo:v1.0.0",
            target=f"cve:{cve_id}",
            relationship_type=EdgeType.HAS_CVE,
            metadata={},
            provenance={"source": "osv", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
        )
    ]
    
    return Graph(
        nodes=[repo_node, release_node, cve_node],
        edges=edges,
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api", "osv"],
            "warnings": []
        }
    )


def create_test_graph_with_package(registry_type, package_name, latest_version="1.0.0"):
    """Helper to create a graph with a specific package."""
    repo_node = Node(
        id="repo:test/repo",
        type=NodeType.REPO,
        label="test/repo",
        metadata={"url": "https://github.com/test/repo"},
        provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    registry_node = Node(
        id=f"registry:{registry_type}:{package_name}",
        type=NodeType.REGISTRY,
        label=f"{registry_type}:{package_name}",
        metadata={
            "registry_type": registry_type,
            "package_name": package_name,
            "latest_version": latest_version,
        },
        provenance={"source": "registry", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
    )
    
    edge = Edge(
        source="repo:test/repo",
        target=f"registry:{registry_type}:{package_name}",
        relationship_type=EdgeType.PUBLISHED_AS,
        metadata={},
        provenance={"source": "registry", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
    )
    
    return Graph(
        nodes=[repo_node, registry_node],
        edges=[edge],
        metadata={
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": ["github_api", "registry"],
            "warnings": []
        }
    )


class TestIndexRepository:
    """Unit tests for IndexRepository."""
    
    def test_find_repos_by_maintainer_single_repo(self):
        """Test finding repos by maintainer with a single result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            graph_repo = GraphRepository(db_path)
            index_repo = IndexRepository(db_path)
            
            # Save graph with maintainer
            graph = create_test_graph_with_maintainer("alice", contribution_fraction=0.75, commit_count=500)
            graph_repo.save_graph("test/repo", graph, generation_time_ms=1000)
            
            # Query by maintainer
            results = index_repo.find_repos_by_maintainer("alice")
            
            assert len(results) == 1
            assert results[0]["repo_full_name"] == "test/repo"
            assert results[0]["contribution_fraction"] == 0.75
            assert results[0]["commit_count"] == 500
    
    def test_find_repos_by_maintainer_multiple_repos(self):
        """Test finding repos by maintainer with multiple results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            graph_repo = GraphRepository(db_path)
            index_repo = IndexRepository(db_path)
            
            # Save multiple graphs with same maintainer
            for i, repo_name in enumerate(["test/repo1", "test/repo2", "test/repo3"]):
                graph = create_test_graph_with_maintainer("bob", contribution_fraction=0.5 + i * 0.1, commit_count=100 * (i + 1))
                graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
            
            # Query by maintainer
            results = index_repo.find_repos_by_maintainer("bob")
            
            assert len(results) == 3
            repo_names = {r["repo_full_name"] for r in results}
            assert repo_names == {"test/repo1", "test/repo2", "test/repo3"}
            
            # Verify results are sorted by contribution_fraction DESC
            assert results[0]["contribution_fraction"] >= results[1]["contribution_fraction"]
            assert results[1]["contribution_fraction"] >= results[2]["contribution_fraction"]
    
    def test_find_repos_by_maintainer_not_found(self):
        """Test finding repos by maintainer when none exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            index_repo = IndexRepository(db_path)
            
            # Query for non-existent maintainer
            results = index_repo.find_repos_by_maintainer("nonexistent")
            
            assert len(results) == 0
    
    def test_find_repos_by_cve_single_repo(self):
        """Test finding repos by CVE with a single result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            graph_repo = GraphRepository(db_path)
            index_repo = IndexRepository(db_path)
            
            # Save graph with CVE
            graph = create_test_graph_with_cve("CVE-2024-1234", severity="HIGH", cvss_score=8.5)
            graph_repo.save_graph("test/repo", graph, generation_time_ms=1000)
            
            # Query by CVE
            results = index_repo.find_repos_by_cve("CVE-2024-1234")
            
            assert len(results) == 1
            assert results[0]["repo_full_name"] == "test/repo"
            assert results[0]["severity"] == "HIGH"
            assert results[0]["cvss_score"] == 8.5
            assert "v1.0.0" in results[0]["affected_releases"]
    
    def test_find_repos_by_cve_multiple_repos(self):
        """Test finding repos by CVE with multiple results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            graph_repo = GraphRepository(db_path)
            index_repo = IndexRepository(db_path)
            
            # Save multiple graphs with same CVE
            for i, repo_name in enumerate(["test/repo1", "test/repo2", "test/repo3"]):
                graph = create_test_graph_with_cve("CVE-2024-5678", severity="CRITICAL", cvss_score=9.0 - i * 0.5)
                graph_repo.save_graph(repo_name, graph, generation_time_ms=1000)
            
            # Query by CVE
            results = index_repo.find_repos_by_cve("CVE-2024-5678")
            
            assert len(results) == 3
            repo_names = {r["repo_full_name"] for r in results}
            assert repo_names == {"test/repo1", "test/repo2", "test/repo3"}
            
            # Verify results are sorted by cvss_score DESC
            assert results[0]["cvss_score"] >= results[1]["cvss_score"]
            assert results[1]["cvss_score"] >= results[2]["cvss_score"]
    
    def test_find_repos_by_cve_not_found(self):
        """Test finding repos by CVE when none exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            index_repo = IndexRepository(db_path)
            
            # Query for non-existent CVE
            results = index_repo.find_repos_by_cve("CVE-2024-9999")
            
            assert len(results) == 0
    
    def test_find_repo_by_package_found(self):
        """Test finding repo by package when it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            graph_repo = GraphRepository(db_path)
            index_repo = IndexRepository(db_path)
            
            # Save graph with package
            graph = create_test_graph_with_package("pypi", "my-package", latest_version="2.3.4")
            graph_repo.save_graph("test/repo", graph, generation_time_ms=1000)
            
            # Query by package
            result = index_repo.find_repo_by_package("pypi", "my-package")
            
            assert result is not None
            assert result["repo_full_name"] == "test/repo"
            assert result["registry_type"] == "pypi"
            assert result["package_name"] == "my-package"
            assert result["latest_version"] == "2.3.4"
    
    def test_find_repo_by_package_not_found(self):
        """Test finding repo by package when it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            index_repo = IndexRepository(db_path)
            
            # Query for non-existent package
            result = index_repo.find_repo_by_package("npm", "nonexistent-package")
            
            assert result is None
    
    def test_find_repos_sharing_maintainer_found(self):
        """Test finding repos sharing maintainers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            graph_repo = GraphRepository(db_path)
            index_repo = IndexRepository(db_path)
            
            # Save repos with shared maintainers
            # repo1: alice, bob
            graph1 = create_test_graph_with_maintainer("alice")
            # Add bob to graph1
            bob_node = Node(
                id="maintainer:bob",
                type=NodeType.MAINTAINER,
                label="bob",
                metadata={"username": "bob", "contribution_fraction": 0.3, "commit_count": 50},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            )
            graph1.nodes.append(bob_node)
            graph1.edges.append(Edge(
                source="repo:test/repo",
                target="maintainer:bob",
                relationship_type=EdgeType.MAINTAINED_BY,
                metadata={},
                provenance={"source": "github_api", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
            ))
            graph_repo.save_graph("test/repo1", graph1, generation_time_ms=1000)
            
            # repo2: bob, charlie
            graph2 = create_test_graph_with_maintainer("bob")
            charlie_node = Node(
                id="maintainer:charlie",
                type=NodeType.MAINTAINER,
                label="charlie",
                metadata={"username": "charlie", "contribution_fraction": 0.4, "commit_count": 75},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            )
            graph2.nodes.append(charlie_node)
            graph2.edges.append(Edge(
                source="repo:test/repo",
                target="maintainer:charlie",
                relationship_type=EdgeType.MAINTAINED_BY,
                metadata={},
                provenance={"source": "github_api", "established_at": datetime.now(timezone.utc).isoformat(), "confidence": 1.0}
            ))
            graph_repo.save_graph("test/repo2", graph2, generation_time_ms=1000)
            
            # repo3: alice
            graph3 = create_test_graph_with_maintainer("alice")
            graph_repo.save_graph("test/repo3", graph3, generation_time_ms=1000)
            
            # Find repos sharing maintainers with repo1
            results = index_repo.find_repos_sharing_maintainer("test/repo1")
            
            # Should find repo2 (shares bob) and repo3 (shares alice)
            assert len(results) == 2
            repo_names = {r["repo_full_name"] for r in results}
            assert repo_names == {"test/repo2", "test/repo3"}
            
            # Verify shared maintainers are listed
            repo2_result = next(r for r in results if r["repo_full_name"] == "test/repo2")
            assert "bob" in repo2_result["shared_maintainers"]
            
            repo3_result = next(r for r in results if r["repo_full_name"] == "test/repo3")
            assert "alice" in repo3_result["shared_maintainers"]
    
    def test_find_repos_sharing_maintainer_no_maintainers(self):
        """Test finding repos sharing maintainers when reference repo has no maintainers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            graph_repo = GraphRepository(db_path)
            index_repo = IndexRepository(db_path)
            
            # Save repo without maintainers
            repo_node = Node(
                id="repo:test/repo",
                type=NodeType.REPO,
                label="test/repo",
                metadata={"url": "https://github.com/test/repo"},
                provenance={"source": "github_api", "fetched_at": datetime.now(timezone.utc).isoformat(), "data_confidence": 1.0}
            )
            graph = Graph(
                nodes=[repo_node],
                edges=[],
                metadata={
                    "schema_version": "1.0",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "data_sources": ["github_api"],
                    "warnings": []
                }
            )
            graph_repo.save_graph("test/repo", graph, generation_time_ms=1000)
            
            # Query for shared maintainers
            results = index_repo.find_repos_sharing_maintainer("test/repo")
            
            assert len(results) == 0
    
    def test_find_repos_sharing_maintainer_not_found(self):
        """Test finding repos sharing maintainers when reference repo doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            init_database(db_path)
            index_repo = IndexRepository(db_path)
            
            # Query for non-existent repo
            results = index_repo.find_repos_sharing_maintainer("nonexistent/repo")
            
            assert len(results) == 0
