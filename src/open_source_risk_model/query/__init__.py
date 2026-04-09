"""
Query module for intent-based dependency graph queries.

This module provides a safe query interface that:
1. Never generates SQL from LLM output
2. Uses strict intent allowlist
3. Computes results on-the-fly from database
"""

from .models import (
    CoverageReport,
    Entity,
    NormalizationResult,
    ParsedQuery,
    QueryResponse,
    RepoFullEvidence,
    RepoStatus,
    RepoSummary,
    RetrievalPlan,
)

__all__ = [
    "Entity",
    "ParsedQuery",
    "NormalizationResult",
    "RepoStatus",
    "CoverageReport",
    "RetrievalPlan",
    "RepoSummary",
    "RepoFullEvidence",
    "QueryResponse",
]
