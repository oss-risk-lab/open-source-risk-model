"""
Pydantic models for query processing and results.

All query-related data structures use Pydantic BaseModel for validation.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..ingestion.models import DataProvenance, EvidenceScope


class Entity(BaseModel):
    """Extracted entity from query."""

    type: str = Field(..., description="repository, package, or ecosystem")
    value: str = Field(..., description="Original value from query")
    normalized_value: str = Field(
        ..., description="Canonical form after normalization"
    )


class ParsedQuery(BaseModel):
    """Parsed query representation."""

    intent: str = Field(..., description="Classified intent")
    entities: list[Entity] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)


class NormalizationResult(BaseModel):
    """Result of entity normalization."""

    canonical_identifier: Optional[str] = Field(
        None, description="Normalized repo identifier"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in normalization"
    )
    alternatives: list[str] = Field(
        default_factory=list, description="Alternative mappings if ambiguous"
    )
    warning: Optional[str] = Field(
        None, description="Warning message if unresolved or ambiguous"
    )


class RepoStatus(BaseModel):
    """Status of a repository in the database."""

    repo_full_name: str
    last_updated: datetime
    score_completeness: str  # "full" or "provisional"


class CoverageReport(BaseModel):
    """Report of repository coverage in database."""

    coverage_mode: str = Field(
        ..., description="database_only, live_ingestion_required, or hybrid"
    )
    in_database: list[RepoStatus] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    invalid: list[str] = Field(default_factory=list)


class RetrievalPlan(BaseModel):
    """Plan for retrieving repository data."""

    use_database: bool
    use_live_ingestion: bool
    live_ingestion_mode: str = Field(..., description="provisional or full")
    repos_from_database: list[str] = Field(default_factory=list)
    repos_for_ingestion: list[str] = Field(default_factory=list)
    cost_classification: str = Field(
        ..., description="low, medium, or high (internal only)"
    )
    evidence_scope: EvidenceScope


class RepoSummary(BaseModel):
    """Summary data for query-time use."""

    repo_full_name: str
    maintenance_risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_band: str = Field(..., description="low, medium, high, or critical")
    features: dict[str, float]
    provenance: DataProvenance


class RepoFullEvidence(BaseModel):
    """Complete evidence for detailed inspection."""

    summary: RepoSummary
    snapshot: dict[str, Any]  # RepositorySnapshot as dict
    contributors: list[dict[str, Any]]  # ContributorRecord list as dicts
    issues: list[dict[str, Any]]  # IssueRecord list as dicts
    ingestion_metadata: dict[str, Any]


class QueryResponse(BaseModel):
    """Response to user query."""

    natural_language_response: str
    structured_results: list[RepoSummary]
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_scope: EvidenceScope
