"""
GraphRepository implementation for storing and retrieving repository graphs.

Provides CRUD operations for graph data with transaction support,
index management, and validation.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..graph.schema import Graph, NodeType, EdgeType
from .db import get_connection
from .errors import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


class GraphRepository:
    """Repository for storing and retrieving repository graphs."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize GraphRepository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
    
    def save_graph(
        self,
        repo_full_name: str,
        graph: Graph,
        generation_time_ms: int
    ) -> None:
        """
        Save or update a repository graph.
        
        Validates the graph, saves it to the database, and updates
        all index tables in a single transaction.
        
        Args:
            repo_full_name: Repository identifier (owner/repo)
            graph: Complete graph object
            generation_time_ms: Time taken to generate graph
        
        Raises:
            ValidationError: If graph validation fails
            DatabaseError: If save operation fails
        """
        # Validate graph before saving
        validation_errors = graph.validate()
        if validation_errors:
            raise ValidationError(f"Invalid graph for {repo_full_name}: {', '.join(validation_errors)}")
        
        conn = get_connection(self.db_path)
        
        try:
            conn.execute("BEGIN TRANSACTION")
            
            # Serialize graph to JSON
            graph_json = json.dumps(graph.to_dict())
            now = datetime.now(timezone.utc).isoformat()
            
            # Get existing created_at if updating
            cursor = conn.execute("""
                SELECT created_at FROM repo_graphs WHERE repo_full_name = ?
            """, (repo_full_name,))
            row = cursor.fetchone()
            created_at = row[0] if row else now
            
            # Upsert repo_graphs
            conn.execute("""
                INSERT OR REPLACE INTO repo_graphs
                (repo_full_name, graph_json, schema_version, node_count, edge_count,
                 created_at, updated_at, data_sources, warnings, generation_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                repo_full_name,
                graph_json,
                graph.metadata.get("schema_version", "1.0"),
                len(graph.nodes),
                len(graph.edges),
                created_at,
                now,
                json.dumps(graph.metadata.get("data_sources", [])),
                json.dumps(graph.metadata.get("warnings", [])) if graph.metadata.get("warnings") else None,
                generation_time_ms
            ))
            
            # Update indexes
            self._update_indexes(conn, repo_full_name, graph)
            
            conn.commit()
            logger.info(f"Saved graph for {repo_full_name} ({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
        
        except ValidationError:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save graph for {repo_full_name}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to save graph: {e}")
        finally:
            conn.close()
    
    def _update_indexes(
        self,
        conn: sqlite3.Connection,
        repo_full_name: str,
        graph: Graph
    ) -> None:
        """
        Update index tables from graph data.
        
        Deletes existing indexes for the repository and rebuilds them
        from the current graph data. Uses O(1) node lookups for efficiency.
        
        Args:
            conn: Database connection (must be in transaction)
            repo_full_name: Repository identifier
            graph: Graph object to extract index data from
        """
        # Delete existing indexes for this repo
        conn.execute("DELETE FROM repo_maintainers WHERE repo_full_name = ?", (repo_full_name,))
        conn.execute("DELETE FROM repo_cves WHERE repo_full_name = ?", (repo_full_name,))
        conn.execute("DELETE FROM repo_registries WHERE repo_full_name = ?", (repo_full_name,))
        
        # Build node lookup dict for O(1) access
        node_by_id = {node.id: node for node in graph.nodes}
        
        # Extract and insert maintainers
        for node in graph.nodes:
            if node.type == NodeType.MAINTAINER:
                username = node.metadata.get("username")
                if username:
                    conn.execute("""
                        INSERT INTO repo_maintainers
                        (repo_full_name, maintainer_username, contribution_fraction, commit_count)
                        VALUES (?, ?, ?, ?)
                    """, (
                        repo_full_name,
                        username,
                        node.metadata.get("contribution_fraction", 0.0),
                        node.metadata.get("commit_count", 0)
                    ))
        
        # Extract and insert CVEs
        for node in graph.nodes:
            if node.type == NodeType.CVE:
                cve_id = node.metadata.get("cve_id")
                if cve_id:
                    # Find affected releases using node lookup dict (O(1) per edge)
                    affected_releases = []
                    for edge in graph.edges:
                        if edge.target == node.id and edge.relationship_type == EdgeType.HAS_CVE:
                            release_node = node_by_id.get(edge.source)
                            if release_node and release_node.type == NodeType.RELEASE:
                                tag_name = release_node.metadata.get("tag_name", "")
                                if tag_name:
                                    affected_releases.append(tag_name)
                    
                    conn.execute("""
                        INSERT INTO repo_cves
                        (repo_full_name, cve_id, severity, cvss_score, affected_releases)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        repo_full_name,
                        cve_id,
                        node.metadata.get("severity", "UNKNOWN"),
                        node.metadata.get("cvss_score"),
                        json.dumps(affected_releases) if affected_releases else None
                    ))
        
        # Extract and insert registries
        for node in graph.nodes:
            if node.type == NodeType.REGISTRY:
                registry_type = node.metadata.get("registry_type")
                package_name = node.metadata.get("package_name")
                if registry_type and package_name:
                    # Use INSERT OR REPLACE to handle duplicate registries in the same graph
                    conn.execute("""
                        INSERT OR REPLACE INTO repo_registries
                        (repo_full_name, registry_type, package_name, latest_version)
                        VALUES (?, ?, ?, ?)
                    """, (
                        repo_full_name,
                        registry_type,
                        package_name,
                        node.metadata.get("latest_version")
                    ))
    
    def get_graph(self, repo_full_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a repository graph.
        
        Returns the graph in the exact format expected by /api/graph endpoint,
        including all metadata fields.
        
        Args:
            repo_full_name: Repository identifier
        
        Returns:
            Graph data as dict (includes graph, metadata, timestamps)
            None if not found
        
        Raises:
            DatabaseError: If retrieval fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM repo_graphs WHERE repo_full_name = ?
            """, (repo_full_name,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Return in exact /api/graph format
            return {
                "repo": row["repo_full_name"],
                "schema_version": row["schema_version"],
                "generated_at": row["updated_at"],
                "graph": json.loads(row["graph_json"]),
                "metadata": {
                    "node_count": row["node_count"],
                    "edge_count": row["edge_count"],
                    "data_sources": json.loads(row["data_sources"]),
                    "warnings": json.loads(row["warnings"]) if row["warnings"] else [],
                    "generation_time_ms": row["generation_time_ms"],
                    "cache_hit": True,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            }
        
        except Exception as e:
            logger.error(f"Failed to get graph for {repo_full_name}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to retrieve graph: {e}")
        finally:
            conn.close()
    
    def delete_graph(self, repo_full_name: str) -> bool:
        """
        Delete a repository graph and all associated indexes.
        
        Uses CASCADE deletion to automatically remove index entries.
        
        Args:
            repo_full_name: Repository identifier
        
        Returns:
            True if deleted, False if not found
        
        Raises:
            DatabaseError: If deletion fails
        """
        conn = get_connection(self.db_path)
        
        try:
            cursor = conn.execute("""
                DELETE FROM repo_graphs WHERE repo_full_name = ?
            """, (repo_full_name,))
            conn.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted graph for {repo_full_name}")
            
            return deleted
        
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete graph for {repo_full_name}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to delete graph: {e}")
        finally:
            conn.close()
    
    def list_repos(
        self,
        limit: int = 100,
        offset: int = 0,
        older_than: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        List repositories with metadata.
        
        Args:
            limit: Maximum number of results
            offset: Pagination offset
            older_than: Filter for repos updated before this time
        
        Returns:
            List of repo metadata dicts (name, node_count, updated_at, etc.)
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            conn.row_factory = sqlite3.Row
            
            # Build query with optional filter
            query = """
                SELECT repo_full_name, node_count, edge_count, created_at, updated_at,
                       data_sources, generation_time_ms
                FROM repo_graphs
            """
            params = []
            
            if older_than:
                query += " WHERE updated_at < ?"
                params.append(older_than.isoformat())
            
            query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                {
                    "repo_full_name": row["repo_full_name"],
                    "node_count": row["node_count"],
                    "edge_count": row["edge_count"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "data_sources": json.loads(row["data_sources"]),
                    "generation_time_ms": row["generation_time_ms"]
                }
                for row in rows
            ]
        
        except Exception as e:
            logger.error(f"Failed to list repos: {e}", exc_info=True)
            raise DatabaseError(f"Failed to list repositories: {e}")
        finally:
            conn.close()
    
    def get_repo_count(self) -> int:
        """
        Get total number of stored repositories.
        
        Returns:
            Count of repositories in database
        
        Raises:
            DatabaseError: If query fails
        """
        conn = get_connection(self.db_path)
        
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM repo_graphs")
            count = cursor.fetchone()[0]
            return count
        
        except Exception as e:
            logger.error(f"Failed to get repo count: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get repository count: {e}")
        finally:
            conn.close()
