"""
Live repository ingestor for on-demand ingestion.

Performs live ingestion with flexible persistence modes:
- temporary: In-query use only
- cache: Store with 1-hour TTL
- database: Promote to main database
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from ..ingestion.cache_manager import CacheManager
from ..ingestion.config import IngestionConfig
from ..ingestion.ingestion_pipeline import IngestionPipeline
from ..ingestion.models import DataProvenance
from ..persistence.db import get_connection
from .models import RepoSummary


class LiveRepoIngestor:
    """Perform on-demand repository ingestion."""

    def __init__(
        self,
        github_token: str,
        cache_dir: str = "data/github_cache",
        db_path: str = "data/graphs.db",
        config: Optional[IngestionConfig] = None,
    ):
        """
        Initialize live repo ingestor.

        Args:
            github_token: GitHub API token
            cache_dir: Directory for cache storage
            db_path: Path to SQLite database
            config: Ingestion configuration (uses defaults if None)
        """
        self.github_token = github_token
        self.cache_dir = cache_dir
        self.db_path = db_path
        self.config = config or IngestionConfig()
        # Override cache_dir in config if provided
        if cache_dir:
            self.config.config["caching"]["cache_dir"] = cache_dir
        self.cache_manager = CacheManager(config=self.config)
        self.pipeline = IngestionPipeline(
            github_token=github_token, config=self.config, cache_manager=self.cache_manager
        )

    def ingest(
        self,
        repo_identifiers: list[str],
        mode: str = "provisional",
        persistence_mode: str = "cache",
    ) -> list[RepoSummary]:
        """
        Ingest repositories on demand, returning summary data.

        Args:
            repo_identifiers: List of repository identifiers (owner/repo)
            mode: "provisional" (snapshot + contributors) or "full" (+ issues)
            persistence_mode: "temporary", "cache", or "database"

        Returns:
            List of RepoSummary objects for successfully ingested repos
        """
        if not repo_identifiers:
            return []

        summaries = []

        for repo_id in repo_identifiers:
            # Check cache first (1-hour TTL)
            if persistence_mode in ["cache", "database"]:
                cached_summary = self._get_from_cache(repo_id, mode)
                if cached_summary:
                    summaries.append(cached_summary)
                    continue

            # Perform live ingestion
            result = self.pipeline.ingest_single(repo_id, mode=mode)

            if not result.success:
                # Skip failed ingestions
                continue

            # Create summary
            provenance = DataProvenance(
                source="live_fetch",
                last_updated=datetime.now(timezone.utc),
                score_completeness=result.score_completeness,
                missing_feature_categories=result.missing_feature_categories,
                api_calls_made=result.api_calls_made,
                ingestion_time_seconds=result.ingestion_time_seconds,
            )

            summary = RepoSummary(
                repo_full_name=result.repo_full_name,
                maintenance_risk_score=result.maintenance_risk_score or 0.0,
                risk_band=self._calculate_risk_band(
                    result.maintenance_risk_score or 0.0
                ),
                features=result.features or {},
                provenance=provenance,
            )

            # Persist based on mode
            if persistence_mode == "cache":
                self._save_to_cache(summary, mode)
            elif persistence_mode == "database":
                self._save_to_database(summary, result)
                # Also save to cache for faster subsequent access
                self._save_to_cache(summary, mode)

            summaries.append(summary)

        return summaries

    def _get_from_cache(self, repo_id: str, mode: str) -> Optional[RepoSummary]:
        """
        Retrieve cached ingestion result.

        Args:
            repo_id: Repository identifier
            mode: Ingestion mode (provisional or full)

        Returns:
            RepoSummary if cached and not expired, None otherwise
        """
        cache_key = f"live:{repo_id}:{mode}"
        cached_data = self.cache_manager.get(cache_key)

        if not cached_data:
            return None

        # Reconstruct RepoSummary from cached data
        try:
            return RepoSummary(**cached_data)
        except Exception:
            # Invalid cache data, ignore
            return None

    def _save_to_cache(self, summary: RepoSummary, mode: str) -> None:
        """
        Save ingestion result to cache.

        Args:
            summary: Repository summary to cache
            mode: Ingestion mode (provisional or full)
        """
        cache_key = f"live:{summary.repo_full_name}:{mode}"
        # Convert to dict for JSON serialization
        cache_data = summary.model_dump()
        # Convert datetime to ISO format
        cache_data["provenance"]["last_updated"] = cache_data["provenance"][
            "last_updated"
        ].isoformat()
        self.cache_manager.set(cache_key, cache_data, ttl_seconds=3600)

    def _save_to_database(self, summary: RepoSummary, result) -> None:
        """
        Save ingestion result to database.

        Args:
            summary: Repository summary to save
            result: Full ingestion result with raw data
        """
        conn = get_connection(self.db_path)
        try:
            # Ensure table exists
            self._ensure_ingestion_results_table(conn)

            # Insert or replace
            conn.execute(
                """
                INSERT OR REPLACE INTO ingestion_results
                (repo_full_name, maintenance_risk_score, risk_band, features_json,
                 score_completeness, ingested_at, snapshot_json, contributors_json,
                 issues_json, metadata_json, api_calls_used, ingestion_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    summary.repo_full_name,
                    summary.maintenance_risk_score,
                    summary.risk_band,
                    json.dumps(summary.features),
                    summary.provenance.score_completeness,
                    summary.provenance.last_updated.isoformat(),
                    None,  # snapshot_json - not stored in IngestionResult
                    None,  # contributors_json
                    None,  # issues_json
                    json.dumps(
                        {
                            "api_calls": result.api_calls_made,
                            "duration_ms": int(result.ingestion_time_seconds * 1000),
                            "missing_categories": result.missing_feature_categories,
                        }
                    ),
                    result.api_calls_made,
                    int(result.ingestion_time_seconds * 1000),
                ),
            )

            conn.commit()
        finally:
            conn.close()

    def _ensure_ingestion_results_table(self, conn: sqlite3.Connection) -> None:
        """
        Ensure ingestion_results table exists.

        Args:
            conn: Database connection
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_results (
                repo_full_name TEXT PRIMARY KEY,
                maintenance_risk_score REAL NOT NULL,
                risk_band TEXT NOT NULL,
                features_json TEXT NOT NULL,
                score_completeness TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                snapshot_json TEXT,
                contributors_json TEXT,
                issues_json TEXT,
                metadata_json TEXT,
                api_calls_used INTEGER,
                ingestion_time_ms INTEGER
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ingestion_results_updated
            ON ingestion_results(ingested_at)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ingestion_results_score
            ON ingestion_results(maintenance_risk_score)
        """)

    def _calculate_risk_band(self, score: float) -> str:
        """
        Calculate risk band from score.

        Args:
            score: Maintenance risk score (0.0-1.0)

        Returns:
            Risk band: low, medium, high, or critical
        """
        if score < 0.3:
            return "low"
        elif score < 0.6:
            return "medium"
        elif score < 0.8:
            return "high"
        else:
            return "critical"
