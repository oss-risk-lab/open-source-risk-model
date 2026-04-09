"""
Database retriever for query-time repository data access.

Provides split retrieval responsibilities:
- retrieve_summary: Fast query-time access to scores and features
- retrieve_full_evidence: Detailed inspection with raw ingestion data
"""

import json
import sqlite3
from datetime import datetime
from typing import Any

from ..ingestion.models import DataProvenance
from ..persistence.db import get_connection
from .models import RepoFullEvidence, RepoSummary


class DBRetriever:
    """Retrieve repository data from database."""

    def __init__(self, db_path: str = "data/graphs.db"):
        """
        Initialize database retriever.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def retrieve_summary(self, repo_identifiers: list[str]) -> list[RepoSummary]:
        """
        Retrieve summary data for query-time use (fast).

        Returns repository name, maintenance risk score, risk band,
        feature values, and data provenance.

        Args:
            repo_identifiers: List of repository identifiers (owner/repo)

        Returns:
            List of RepoSummary objects for found repositories
        """
        if not repo_identifiers:
            return []

        conn = get_connection(self.db_path)
        try:
            # Query ingestion_results table for summary data
            placeholders = ",".join("?" * len(repo_identifiers))
            query = f"""
                SELECT 
                    repo_full_name,
                    maintenance_risk_score,
                    risk_band,
                    features_json,
                    score_completeness,
                    ingested_at
                FROM ingestion_results
                WHERE repo_full_name IN ({placeholders})
            """

            cursor = conn.execute(query, repo_identifiers)
            rows = cursor.fetchall()

            summaries = []
            for row in rows:
                repo_full_name, score, risk_band, features_json, completeness, ingested_at = row

                # Parse features
                features = json.loads(features_json) if features_json else {}

                # Create provenance
                provenance = DataProvenance(
                    source="database",
                    last_updated=datetime.fromisoformat(ingested_at),
                    score_completeness=completeness,
                )

                summary = RepoSummary(
                    repo_full_name=repo_full_name,
                    maintenance_risk_score=score,
                    risk_band=risk_band,
                    features=features,
                    provenance=provenance,
                )
                summaries.append(summary)

            return summaries

        finally:
            conn.close()

    def retrieve_full_evidence(self, repo_identifier: str) -> RepoFullEvidence | None:
        """
        Retrieve complete evidence for detailed inspection (slower).

        Returns all summary data plus raw snapshot, contributors,
        issues, and ingestion metadata.

        Args:
            repo_identifier: Repository identifier (owner/repo)

        Returns:
            RepoFullEvidence object or None if not found
        """
        conn = get_connection(self.db_path)
        try:
            # Query ingestion_results table for full data
            query = """
                SELECT 
                    repo_full_name,
                    maintenance_risk_score,
                    risk_band,
                    features_json,
                    score_completeness,
                    ingested_at,
                    snapshot_json,
                    contributors_json,
                    issues_json,
                    metadata_json
                FROM ingestion_results
                WHERE repo_full_name = ?
            """

            cursor = conn.execute(query, (repo_identifier,))
            row = cursor.fetchone()

            if not row:
                return None

            (
                repo_full_name,
                score,
                risk_band,
                features_json,
                completeness,
                ingested_at,
                snapshot_json,
                contributors_json,
                issues_json,
                metadata_json,
            ) = row

            # Parse JSON fields
            features = json.loads(features_json) if features_json else {}
            snapshot = json.loads(snapshot_json) if snapshot_json else {}
            contributors = json.loads(contributors_json) if contributors_json else []
            issues = json.loads(issues_json) if issues_json else []
            metadata = json.loads(metadata_json) if metadata_json else {}

            # Create provenance
            provenance = DataProvenance(
                source="database",
                last_updated=datetime.fromisoformat(ingested_at),
                score_completeness=completeness,
            )

            # Create summary
            summary = RepoSummary(
                repo_full_name=repo_full_name,
                maintenance_risk_score=score,
                risk_band=risk_band,
                features=features,
                provenance=provenance,
            )

            # Create full evidence
            full_evidence = RepoFullEvidence(
                summary=summary,
                snapshot=snapshot,
                contributors=contributors,
                issues=issues,
                ingestion_metadata=metadata,
            )

            return full_evidence

        finally:
            conn.close()

    def _ensure_ingestion_results_table(self) -> None:
        """
        Ensure ingestion_results table exists.

        This table stores the new ingestion pipeline results.
        Called automatically when needed.
        """
        conn = get_connection(self.db_path)
        try:
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

            conn.commit()
        finally:
            conn.close()
