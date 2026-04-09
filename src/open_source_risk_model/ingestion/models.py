"""
Pydantic models for GitHub API ingestion.

All external data structures (API responses, persisted payloads) use Pydantic BaseModel
for validation, parsing, and safer serialization.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class WeeklyActivity(BaseModel):
    """Weekly contributor activity statistics."""

    week_timestamp: int = Field(..., description="Unix timestamp for week start")
    additions: int = Field(..., ge=0, description="Lines added")
    deletions: int = Field(..., ge=0, description="Lines deleted")
    commits: int = Field(..., ge=0, description="Number of commits")


class RepositorySnapshot(BaseModel):
    """GitHub repository snapshot from GraphQL API."""

    repo_full_name: str = Field(
        ..., description="Repository identifier in owner/repo format"
    )
    pushed_at: datetime = Field(..., description="Last push timestamp")
    latest_release: Optional[datetime] = Field(
        None, description="Latest release timestamp"
    )
    stargazer_count: int = Field(..., ge=0, description="Number of stars")
    is_archived: bool = Field(..., description="Whether repository is archived")
    license_info: Optional[str] = Field(None, description="License identifier")
    open_issues_count: int = Field(..., ge=0, description="Number of open issues")
    fetched_at: datetime = Field(..., description="When this snapshot was fetched")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ContributorRecord(BaseModel):
    """Contributor data from GitHub REST API."""

    login: str = Field(..., description="GitHub username")
    contributions: int = Field(..., ge=0, description="Total contributions")
    weeks: list[WeeklyActivity] = Field(
        default_factory=list, description="Weekly activity breakdown"
    )
    fetched_at: datetime = Field(..., description="When this data was fetched")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class IssueRecord(BaseModel):
    """Issue data from GitHub REST API."""

    number: int = Field(..., ge=1, description="Issue number")
    state: str = Field(..., description="Issue state: open or closed")
    created_at: datetime = Field(..., description="Issue creation timestamp")
    closed_at: Optional[datetime] = Field(None, description="Issue closure timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    comments: int = Field(..., ge=0, description="Number of comments")
    author_association: str = Field(
        ..., description="Author's association with repo"
    )
    labels: list[str] = Field(default_factory=list, description="Issue labels")
    fetched_at: datetime = Field(..., description="When this data was fetched")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class MaintenanceRiskScore(BaseModel):
    """Computed maintenance risk score with metadata."""

    repo_full_name: str = Field(..., description="Repository identifier")
    score: float = Field(..., ge=0.0, le=1.0, description="Risk score on 0-1 scale")
    risk_band: str = Field(
        ..., description="Risk classification: low, medium, high, critical"
    )
    features: dict[str, float] = Field(
        ..., description="Feature values used in scoring"
    )
    feature_weights: dict[str, float] = Field(
        ..., description="Weights applied to features"
    )
    score_completeness: str = Field(..., description="full or provisional")
    missing_feature_categories: list[str] = Field(
        default_factory=list, description="Missing feature categories"
    )
    computed_at: datetime = Field(..., description="When score was computed")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class DataProvenance(BaseModel):
    """Metadata about data source and freshness."""

    source: str = Field(..., description="database or live_fetch")
    last_updated: datetime = Field(..., description="When data was last updated")
    score_completeness: str = Field(..., description="full or provisional")
    missing_feature_categories: list[str] = Field(
        default_factory=list, description="Missing feature categories"
    )
    api_calls_made: Optional[int] = Field(
        None, ge=0, description="API calls made during fetch"
    )
    ingestion_time_seconds: Optional[float] = Field(
        None, ge=0.0, description="Time taken to ingest"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class EvidenceScope(BaseModel):
    """Tracks the scope of evidence used in query results."""

    source_level: str = Field(
        ..., description="scored_features, raw_ingestion, or hybrid"
    )
    includes_live_fetch: bool = Field(
        ..., description="Whether live fetching was performed"
    )
    includes_cached_results: bool = Field(
        ..., description="Whether cached results were used"
    )
    includes_database_results: bool = Field(
        ..., description="Whether database results were used"
    )


class IngestionResult(BaseModel):
    """Result of ingesting a single repository."""

    repo_full_name: str
    success: bool
    features: Optional[dict[str, float]] = None
    maintenance_risk_score: Optional[float] = None
    score_completeness: str  # "full" or "provisional"
    api_calls_made: int = Field(..., ge=0)
    ingestion_time_seconds: float = Field(..., ge=0.0)
    error: Optional[str] = None
    missing_feature_categories: list[str] = Field(default_factory=list)


class IngestionSummary(BaseModel):
    """Summary of batch ingestion operation."""

    total_repos: int = Field(..., ge=0)
    successful: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    total_api_calls: int = Field(..., ge=0)
    total_time_seconds: float = Field(..., ge=0.0)
    avg_api_calls_per_repo: float = Field(..., ge=0.0)
    avg_time_per_repo: float = Field(..., ge=0.0)
    rate_limit_remaining: dict[str, int]
