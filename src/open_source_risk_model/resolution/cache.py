import json
import sqlite3
from datetime import datetime, timezone, timedelta

from open_source_risk_model.persistence.db import get_connection
from .models import NormalizedPackageMetadata, DependencyDeclaration

DEFAULT_TTL_HOURS = 168        # 7 days for positive results (Req 6.5)
NEGATIVE_TTL_HOURS = 1         # 1 hour for negative results (Req 6.6)

_CACHE_MISS = object()  # sentinel


class ResolutionCache:
    """Two-tier cache for registry lookup results.

    HARD INVARIANT: The cache layer must NEVER trigger external API calls.
    It is a pure lookup/store abstraction. All registry calls must originate
    from the resolver after budget checks. There is no get_or_fetch() method.
    """

    def __init__(self, db_path: str, ttl_hours: int = DEFAULT_TTL_HOURS):
        self.db_path = db_path
        self.ttl = timedelta(hours=ttl_hours)
        self.negative_ttl = timedelta(hours=NEGATIVE_TTL_HOURS)
        self._session: dict[tuple[str, str], NormalizedPackageMetadata | None] = {}
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS package_metadata_cache (
                    ecosystem     TEXT NOT NULL,
                    package_name  TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    fetched_at    TEXT NOT NULL,
                    expires_at    TEXT NOT NULL,
                    PRIMARY KEY (ecosystem, package_name)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def lookup(self, ecosystem: str, name: str) -> tuple[NormalizedPackageMetadata | None, bool]:
        """Check both cache tiers for a package.
        Returns (metadata_or_none, was_found).
        was_found=True means a cache entry exists (even if metadata is None
        for a negative cache hit). was_found=False means cache miss."""
        key = (ecosystem, name)

        # Tier 1: session cache (Req 6.2)
        if key in self._session:
            return self._session[key], True

        # Tier 2: DB cache (Req 6.3)
        db_result = self._read_db_cache(key)
        if db_result is not _CACHE_MISS:
            self._session[key] = db_result
            return db_result, True

        return None, False

    def store(self, ecosystem: str, name: str,
              metadata: NormalizedPackageMetadata | None) -> None:
        """Write to both session and DB cache (Req 6.4).
        metadata=None stores a negative cache entry with shorter TTL (Req 6.6)."""
        key = (ecosystem, name)
        self._session[key] = metadata
        self._write_db_cache(key, metadata)

    def _read_db_cache(self, key: tuple[str, str]) -> NormalizedPackageMetadata | None:
        conn = get_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT metadata_json FROM package_metadata_cache
                   WHERE ecosystem = ? AND package_name = ?
                   AND expires_at > datetime('now')""",
                key,
            ).fetchone()
            if row is None:
                return _CACHE_MISS
            return self._deserialize(row["metadata_json"])
        finally:
            conn.close()

    def _write_db_cache(self, key: tuple[str, str],
                        metadata: NormalizedPackageMetadata | None) -> None:
        conn = get_connection(self.db_path)
        try:
            now = datetime.now(timezone.utc)
            ttl = self.ttl if metadata is not None else self.negative_ttl
            expires = now + ttl
            conn.execute(
                """INSERT OR REPLACE INTO package_metadata_cache
                   (ecosystem, package_name, metadata_json, fetched_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (key[0], key[1], self._serialize(metadata),
                 now.isoformat(), expires.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _serialize(metadata: NormalizedPackageMetadata | None) -> str:
        if metadata is None:
            return "null"
        return json.dumps({
            "name": metadata.name,
            "version": metadata.version,
            "ecosystem": metadata.ecosystem,
            "dependencies": [
                {"name": d.name, "specifier": d.specifier}
                for d in metadata.dependencies
            ],
            "source_url": metadata.source_url,
            "fetched_at": metadata.fetched_at,
        })

    @staticmethod
    def _deserialize(json_str: str) -> NormalizedPackageMetadata | None:
        if json_str == "null":
            return None
        data = json.loads(json_str)
        return NormalizedPackageMetadata(
            name=data["name"],
            version=data["version"],
            ecosystem=data["ecosystem"],
            dependencies=[
                DependencyDeclaration(name=d["name"], specifier=d.get("specifier"))
                for d in data["dependencies"]
            ],
            source_url=data["source_url"],
            fetched_at=data["fetched_at"],
        )
