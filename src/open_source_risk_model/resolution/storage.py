import sqlite3
from open_source_risk_model.persistence.db import get_connection
from .models import ResolutionEdge


class ResolvedDependencyStorage:
    def __init__(self, db_path: str = "data/graphs.db"):
        self.db_path = db_path
        self.ensure_tables()

    def ensure_tables(self) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS resolved_dependencies (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name   TEXT NOT NULL,
                    parent_ecosystem TEXT,
                    parent_package   TEXT NOT NULL,
                    child_ecosystem  TEXT,
                    child_package    TEXT NOT NULL,
                    declared_specifier TEXT,
                    resolved_version TEXT,
                    depth            INTEGER NOT NULL,
                    resolution_status TEXT NOT NULL DEFAULT 'resolved',
                    error_reason     TEXT,
                    source_registry  TEXT,
                    resolved_at      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_resolved_deps_repo
                    ON resolved_dependencies(repo_full_name);
                CREATE INDEX IF NOT EXISTS idx_resolved_deps_parent
                    ON resolved_dependencies(
                        repo_full_name, parent_ecosystem, parent_package
                    );
                CREATE INDEX IF NOT EXISTS idx_resolved_deps_depth
                    ON resolved_dependencies(repo_full_name, depth);
            """)

            # Migrate: add scope columns if missing (Req 1.1, 1.2, 1.3, 1.4)
            cursor = conn.execute("PRAGMA table_info(resolved_dependencies)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            if "dependency_scope" not in existing_columns:
                conn.execute(
                    "ALTER TABLE resolved_dependencies "
                    "ADD COLUMN dependency_scope TEXT DEFAULT 'unknown'"
                )
            if "scope_confidence" not in existing_columns:
                conn.execute(
                    "ALTER TABLE resolved_dependencies "
                    "ADD COLUMN scope_confidence TEXT DEFAULT 'low'"
                )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_resolved_deps_scope "
                "ON resolved_dependencies(dependency_scope)"
            )

            conn.commit()
        finally:
            conn.close()

    def store_edges(self, repo_full_name: str, edges: list[ResolutionEdge]) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "DELETE FROM resolved_dependencies WHERE repo_full_name = ?",
                (repo_full_name,),
            )
            conn.executemany(
                """INSERT INTO resolved_dependencies
                   (repo_full_name, parent_ecosystem, parent_package,
                    child_ecosystem, child_package, declared_specifier,
                    resolved_version, depth, resolution_status,
                    error_reason, source_registry, resolved_at,
                    dependency_scope, scope_confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (e.repo_full_name, e.parent_ecosystem, e.parent_package,
                     e.child_ecosystem, e.child_package, e.declared_specifier,
                     e.resolved_version, e.depth, e.resolution_status,
                     e.error_reason, e.source_registry, e.resolved_at,
                     e.dependency_scope, e.scope_confidence)
                    for e in edges
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def get_edges(self, repo_full_name: str) -> list[ResolutionEdge]:
        conn = get_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM resolved_dependencies
                   WHERE repo_full_name = ?
                   ORDER BY depth, parent_ecosystem, parent_package, child_package""",
                (repo_full_name,),
            ).fetchall()
            return [self._row_to_edge(r) for r in rows]
        finally:
            conn.close()

    def has_resolved_data(self, repo_full_name: str) -> bool:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                """SELECT 1 FROM resolved_dependencies
                   WHERE repo_full_name = ? AND resolution_status = 'resolved'
                   LIMIT 1""",
                (repo_full_name,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def get_oldest_resolved_at(self, repo_full_name: str) -> str | None:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT MIN(resolved_at) FROM resolved_dependencies "
                "WHERE repo_full_name = ?",
                (repo_full_name,),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def delete_resolved(self, repo_full_name: str) -> int:
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM resolved_dependencies WHERE repo_full_name = ?",
                (repo_full_name,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def _row_to_edge(row) -> ResolutionEdge:
        return ResolutionEdge(
            repo_full_name=row["repo_full_name"],
            parent_ecosystem=row["parent_ecosystem"],
            parent_package=row["parent_package"],
            child_ecosystem=row["child_ecosystem"],
            child_package=row["child_package"],
            declared_specifier=row["declared_specifier"],
            resolved_version=row["resolved_version"],
            depth=row["depth"],
            resolution_status=row["resolution_status"],
            error_reason=row["error_reason"],
            source_registry=row["source_registry"],
            resolved_at=row["resolved_at"],
            dependency_scope=row["dependency_scope"] or "unknown",
            scope_confidence=row["scope_confidence"] or "low",
        )
