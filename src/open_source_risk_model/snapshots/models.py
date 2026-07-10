"""
Dataclasses for temporal snapshot records and run manifests.

Schema version 1.0. All timestamps are UTC ISO 8601 strings.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


SCHEMA_VERSION = "1.0"
VALID_FETCH_STATUSES: frozenset[str] = frozenset({"success", "partial", "not_found", "error"})


@dataclass
class SnapshotRecord:
    """One immutable observation of a repository at a point in time."""

    schema_version: str
    run_id: str
    observed_at: str  # UTC ISO 8601 per-repo fetch completion time
    repo_full_name: str
    universe_version: str
    fetch_status: str  # success | partial | not_found | error
    error_message: Optional[str]
    features: dict[str, Any]  # canonical v1.0 feature keys; missing values are None
    raw: dict[str, Any]  # absolute timestamps and repo metadata
    feature_coverage: float  # fraction of non-null feature values (0.0 to 1.0)
    feature_status: dict[str, str]  # per-feature pipeline status flags

    def __post_init__(self) -> None:
        if self.fetch_status not in VALID_FETCH_STATUSES:
            raise ValueError(
                f"Invalid fetch_status {self.fetch_status!r}. "
                f"Must be one of {sorted(VALID_FETCH_STATUSES)}."
            )

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict matching the v1.0 schema."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "observed_at": self.observed_at,
            "repo_full_name": self.repo_full_name,
            "universe_version": self.universe_version,
            "fetch_status": self.fetch_status,
            "error_message": self.error_message,
            "features": self.features,
            "raw": self.raw,
            "feature_coverage": self.feature_coverage,
            "feature_status": self.feature_status,
        }


@dataclass
class RunManifest:
    """Summary of a completed snapshot run."""

    run_id: str
    started_at: str  # UTC ISO 8601
    completed_at: str  # UTC ISO 8601
    universe_version: str
    universe_sha256: str
    repos_total: int
    repos_success: int
    repos_partial: int
    repos_not_found: int
    repos_error: int
    error_sample: list[dict[str, str]]  # up to 20 entries: {repo, message}
    api_calls_estimate: int
    collector_git_sha: str
    schema_version: str
    epoch0: bool = field(default=False)  # True only for backfill manifests

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "universe_version": self.universe_version,
            "universe_sha256": self.universe_sha256,
            "repos_total": self.repos_total,
            "repos_success": self.repos_success,
            "repos_partial": self.repos_partial,
            "repos_not_found": self.repos_not_found,
            "repos_error": self.repos_error,
            "error_sample": self.error_sample,
            "api_calls_estimate": self.api_calls_estimate,
            "collector_git_sha": self.collector_git_sha,
        }
        if self.epoch0:
            d["epoch0"] = True
        return d
