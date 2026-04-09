"""
GitHub API ingestion module with hybrid GraphQL/REST strategy.

This module provides optimized repository data ingestion using:
- GraphQL for repository snapshots (batch fetching)
- REST API for activity data (contributors, issues)
- Adaptive batching and rate limiting
- Caching with configurable TTL
"""

from .config import IngestionConfig, PackageMappingConfig
from .models import (
    ContributorRecord,
    DataProvenance,
    EvidenceScope,
    IngestionResult,
    IngestionSummary,
    IssueRecord,
    MaintenanceRiskScore,
    RepositorySnapshot,
    WeeklyActivity,
)

__all__ = [
    "RepositorySnapshot",
    "WeeklyActivity",
    "ContributorRecord",
    "IssueRecord",
    "MaintenanceRiskScore",
    "DataProvenance",
    "EvidenceScope",
    "IngestionResult",
    "IngestionSummary",
    "IngestionConfig",
    "PackageMappingConfig",
]
