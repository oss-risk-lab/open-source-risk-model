"""
ScopeRepository — SQLite-backed persistence for multi-repo analysis sessions.

Replaces the in-memory SCOPE_STORE dict so scope results survive server restarts.
Scopes are stored as JSON blobs keyed by scope_id.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from .db import get_connection

logger = logging.getLogger(__name__)


class ScopeRepository:
    """Persistent store for ingest-scope analysis sessions."""

    def __init__(self, db_path: str = "data/graphs.db"):
        self.db_path = db_path

    def save(self, scope_id: str, data: dict) -> None:
        """Insert or replace a scope session."""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO scope_sessions
                    (scope_id, name, status, result_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    scope_id,
                    data.get("name", ""),
                    data.get("status", "unknown"),
                    json.dumps(data),
                    data.get("created_at", datetime.now(timezone.utc).isoformat()),
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save scope {scope_id}: {e}")
            raise
        finally:
            conn.close()

    def get(self, scope_id: str) -> Optional[dict]:
        """Return the stored scope dict, or None if not found."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT result_json FROM scope_sessions WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return json.loads(row[0])
