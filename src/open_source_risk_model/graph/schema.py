"""
Graph schema definitions for supply chain risk modeling.

Defines node types, edge types, and the graph structure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass
class GraphConfig:
    """
    Configuration for graph generation.
    
    Controls various aspects of graph building including node limits,
    data source inclusion, and performance settings.
    
    Attributes:
        include_cves: Whether to include CVE nodes (may be slow)
        max_releases: Maximum number of release nodes to include
        max_maintainers: Maximum number of maintainer nodes to include
        max_risk_factors: Maximum number of risk factor nodes to include
        cve_timeout_seconds: Timeout for CVE API requests
        cache_ttl_hours: Cache time-to-live in hours
    """
    
    include_cves: bool = True
    max_releases: int = 10
    max_maintainers: int = 5
    max_risk_factors: int = 5
    cve_timeout_seconds: int = 5
    cache_ttl_hours: int = 24
    
    @classmethod
    def from_env(cls) -> GraphConfig:
        """
        Create configuration from environment variables.
        
        Supported environment variables:
        - GRAPH_INCLUDE_CVES: "true" or "false" (default: true)
        - GRAPH_MAX_RELEASES: integer (default: 10)
        - GRAPH_MAX_MAINTAINERS: integer (default: 5)
        - GRAPH_MAX_RISK_FACTORS: integer (default: 5)
        - GRAPH_CVE_TIMEOUT_SECONDS: integer (default: 5)
        - GRAPH_CACHE_TTL_HOURS: integer (default: 24)
        
        Returns:
            GraphConfig instance with values from environment or defaults
        """
        def get_bool(key: str, default: bool) -> bool:
            """Get boolean from environment variable."""
            value = os.getenv(key)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes")
        
        def get_int(key: str, default: int) -> int:
            """Get integer from environment variable."""
            value = os.getenv(key)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default
        
        return cls(
            include_cves=get_bool("GRAPH_INCLUDE_CVES", True),
            max_releases=get_int("GRAPH_MAX_RELEASES", 10),
            max_maintainers=get_int("GRAPH_MAX_MAINTAINERS", 5),
            max_risk_factors=get_int("GRAPH_MAX_RISK_FACTORS", 5),
            cve_timeout_seconds=get_int("GRAPH_CVE_TIMEOUT_SECONDS", 5),
            cache_ttl_hours=get_int("GRAPH_CACHE_TTL_HOURS", 24),
        )


class NodeType(str, Enum):
    """Types of nodes in the supply chain graph."""
    
    REPO = "repo"
    RELEASE = "release"
    MAINTAINER = "maintainer"
    CVE = "cve"
    REGISTRY = "registry"
    RISK_FACTOR = "risk_factor"
    DEPLOYMENT = "deployment"  # placeholder for future


class EdgeType(str, Enum):
    """Types of edges (relationships) in the supply chain graph."""
    
    HAS_RELEASE = "has_release"
    PUBLISHED_AS = "published_as"
    HAS_CVE = "has_cve"
    MAINTAINED_BY = "maintained_by"
    HAS_RISK_FACTOR = "has_risk_factor"
    USED_IN = "used_in"
    DEPLOYED_TO = "deployed_to"


@dataclass
class Node:
    """
    A node in the supply chain graph.
    
    Attributes:
        id: Unique identifier (stable across requests)
        type: Node type from NodeType enum
        label: Human-readable label
        metadata: Additional node-specific data
        provenance: Data provenance information (source, timestamp, confidence)
    """
    
    id: str
    type: NodeType
    label: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "metadata": self.metadata,
            "provenance": self.provenance,
        }


@dataclass
class Edge:
    """
    An edge (relationship) in the supply chain graph.
    
    Attributes:
        source: Source node ID
        target: Target node ID
        relationship_type: Type of relationship from EdgeType enum
        metadata: Additional edge-specific data
        provenance: Data provenance information (source, timestamp, confidence)
    """
    
    source: str
    target: str
    relationship_type: EdgeType
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "source": self.source,
            "target": self.target,
            "relationship_type": self.relationship_type.value,
            "metadata": self.metadata,
            "provenance": self.provenance,
        }


@dataclass
class Graph:
    """
    Supply chain risk graph.
    
    Attributes:
        nodes: List of nodes in the graph
        edges: List of edges in the graph
        metadata: Graph-level metadata (version, timestamp, etc.)
    """
    
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_node(self, node: Node) -> None:
        """Add a node to the graph."""
        self.nodes.append(node)
    
    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)
    
    def validate(self) -> List[str]:
        """
        Validate graph structure.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check for duplicate node IDs
        node_ids = [n.id for n in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            errors.append("Duplicate node IDs found")
        
        # Check that all edges reference valid nodes
        node_id_set = set(node_ids)
        for edge in self.edges:
            if edge.source not in node_id_set:
                errors.append(f"Edge references invalid source node: {edge.source}")
            if edge.target not in node_id_set:
                errors.append(f"Edge references invalid target node: {edge.target}")
        
        # Check that exactly one repo node exists
        repo_nodes = [n for n in self.nodes if n.type == NodeType.REPO]
        if len(repo_nodes) == 0:
            errors.append("Graph must contain exactly one repo node")
        elif len(repo_nodes) > 1:
            errors.append("Graph contains multiple repo nodes")
        
        # Validate provenance fields for nodes
        for node in self.nodes:
            node_errors = self._validate_provenance(node.provenance, f"Node {node.id}")
            errors.extend(node_errors)
        
        # Validate provenance fields for edges
        for edge in self.edges:
            edge_errors = self._validate_provenance(
                edge.provenance, 
                f"Edge {edge.source} -> {edge.target}"
            )
            errors.extend(edge_errors)
        
        return errors
    
    def _validate_provenance(self, provenance: Dict[str, Any], context: str) -> List[str]:
        """
        Validate provenance metadata.
        
        Args:
            provenance: Provenance dictionary to validate
            context: Context string for error messages
        
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check for required fields
        if not provenance:
            errors.append(f"{context}: Missing provenance metadata")
            return errors
        
        if "source" not in provenance:
            errors.append(f"{context}: Missing 'source' in provenance")
        
        if "fetched_at" not in provenance and "established_at" not in provenance:
            errors.append(f"{context}: Missing timestamp in provenance (fetched_at or established_at)")
        
        # Validate confidence if present
        if "confidence" in provenance:
            confidence = provenance["confidence"]
            if not isinstance(confidence, (int, float)):
                errors.append(f"{context}: Confidence must be numeric")
            elif confidence < 0.0 or confidence > 1.0:
                errors.append(f"{context}: Confidence must be between 0.0 and 1.0, got {confidence}")
        
        if "data_confidence" in provenance:
            data_confidence = provenance["data_confidence"]
            if not isinstance(data_confidence, (int, float)):
                errors.append(f"{context}: data_confidence must be numeric")
            elif data_confidence < 0.0 or data_confidence > 1.0:
                errors.append(f"{context}: data_confidence must be between 0.0 and 1.0, got {data_confidence}")
        
        if "match_confidence" in provenance:
            match_confidence = provenance["match_confidence"]
            if not isinstance(match_confidence, (int, float)):
                errors.append(f"{context}: match_confidence must be numeric")
            elif match_confidence < 0.0 or match_confidence > 1.0:
                errors.append(f"{context}: match_confidence must be between 0.0 and 1.0, got {match_confidence}")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
        }
