"""
Database initialization and connection management for graph persistence.

This module handles SQLite database setup, schema creation, and connection
management with appropriate pragmas for concurrency and performance.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Database schema version
SCHEMA_VERSION = 2  # Updated for dependency graph support


def init_database(db_path: str = "data/graphs.db") -> None:
    """
    Initialize the database with schema.
    
    Creates all tables, indexes, and schema version tracking.
    This function is idempotent - safe to call multiple times.
    
    Args:
        db_path: Path to SQLite database file
    
    Raises:
        DatabaseError: If database initialization fails
    """
    from .errors import DatabaseError
    
    try:
        # Ensure directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        conn = get_connection(db_path)
        
        # Create schema
        conn.executescript("""
            -- Schema version tracking
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            
            -- Repository graphs table
            CREATE TABLE IF NOT EXISTS repo_graphs (
                repo_full_name TEXT PRIMARY KEY,
                graph_json TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                node_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data_sources TEXT NOT NULL,
                warnings TEXT,
                generation_time_ms INTEGER
            );
            
            -- Ingestion jobs table
            CREATE TABLE IF NOT EXISTS ingestion_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                repo_list TEXT NOT NULL,
                total_repos INTEGER NOT NULL,
                processed_repos INTEGER DEFAULT 0,
                successful_repos INTEGER DEFAULT 0,
                failed_repos INTEGER DEFAULT 0,
                errors TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                config TEXT
            );
            
            -- Maintainer index table
            CREATE TABLE IF NOT EXISTS repo_maintainers (
                repo_full_name TEXT NOT NULL,
                maintainer_username TEXT NOT NULL,
                contribution_fraction REAL NOT NULL,
                commit_count INTEGER NOT NULL,
                PRIMARY KEY (repo_full_name, maintainer_username),
                FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
            );
            
            -- CVE index table
            CREATE TABLE IF NOT EXISTS repo_cves (
                repo_full_name TEXT NOT NULL,
                cve_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                cvss_score REAL,
                affected_releases TEXT,
                PRIMARY KEY (repo_full_name, cve_id),
                FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
            );
            
            -- Registry index table
            CREATE TABLE IF NOT EXISTS repo_registries (
                repo_full_name TEXT NOT NULL,
                registry_type TEXT NOT NULL,
                package_name TEXT NOT NULL,
                latest_version TEXT,
                PRIMARY KEY (repo_full_name, registry_type, package_name),
                FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
            );
            
            -- Dependency edges table (NEW for Step 2)
            CREATE TABLE IF NOT EXISTS repo_dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_full_name TEXT NOT NULL,
                package_name TEXT NOT NULL,
                registry_type TEXT NOT NULL,
                specifier TEXT,
                extras TEXT,
                markers TEXT,
                dependency_group TEXT DEFAULT 'prod',
                is_direct BOOLEAN NOT NULL DEFAULT 1,
                is_optional BOOLEAN NOT NULL DEFAULT 0,
                manifest_path TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE,
                UNIQUE(repo_full_name, package_name, manifest_path)
            );
            
            -- Package-to-repo mappings cache (NEW for Step 2)
            CREATE TABLE IF NOT EXISTS package_mappings (
                package_name TEXT NOT NULL,
                registry_type TEXT NOT NULL,
                repo_full_name TEXT,
                resolution_method TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (package_name, registry_type)
            );
            
            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_repo_graphs_updated_at 
                ON repo_graphs(updated_at);
            
            CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status 
                ON ingestion_jobs(status);
            
            CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_created_at 
                ON ingestion_jobs(created_at);
            
            CREATE INDEX IF NOT EXISTS idx_repo_maintainers_username 
                ON repo_maintainers(maintainer_username);
            
            CREATE INDEX IF NOT EXISTS idx_repo_cves_cve_id 
                ON repo_cves(cve_id);
            
            CREATE INDEX IF NOT EXISTS idx_repo_cves_severity 
                ON repo_cves(severity);
            
            CREATE INDEX IF NOT EXISTS idx_repo_registries_package 
                ON repo_registries(registry_type, package_name);
            
            -- Dependency indexes (NEW for Step 2)
            CREATE INDEX IF NOT EXISTS idx_repo_dependencies_repo 
                ON repo_dependencies(repo_full_name);
            
            CREATE INDEX IF NOT EXISTS idx_repo_dependencies_package 
                ON repo_dependencies(package_name, registry_type);
            
            CREATE INDEX IF NOT EXISTS idx_repo_dependencies_direct 
                ON repo_dependencies(is_direct);
            
            CREATE INDEX IF NOT EXISTS idx_repo_dependencies_group 
                ON repo_dependencies(dependency_group);
            
            CREATE INDEX IF NOT EXISTS idx_package_mappings_repo 
                ON package_mappings(repo_full_name);
            
            CREATE INDEX IF NOT EXISTS idx_package_mappings_confidence 
                ON package_mappings(confidence);
        """)
        
        # Insert schema version (idempotent with INSERT OR IGNORE)
        conn.execute("""
            INSERT OR IGNORE INTO schema_version (version, applied_at)
            VALUES (?, datetime('now'))
        """, (SCHEMA_VERSION,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Database initialized at {db_path} with schema version {SCHEMA_VERSION}")
    
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise DatabaseError(f"Database initialization failed: {e}")


def get_connection(db_path: str = "data/graphs.db") -> sqlite3.Connection:
    """
    Get a database connection with appropriate pragmas.
    
    Configures SQLite for better concurrency and performance:
    - WAL mode for concurrent reads/writes
    - NORMAL synchronous mode for better performance
    - 5 second busy timeout for handling concurrent access
    
    Args:
        db_path: Path to SQLite database file
    
    Returns:
        SQLite connection object
    
    Raises:
        DatabaseError: If connection fails
    """
    from .errors import DatabaseError
    
    try:
        conn = sqlite3.connect(db_path)
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Use NORMAL synchronous mode for better performance
        conn.execute("PRAGMA synchronous=NORMAL")
        
        # Set busy timeout to 5 seconds
        conn.execute("PRAGMA busy_timeout=5000")
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys=ON")
        
        return conn
    
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        raise DatabaseError(f"Database connection failed: {e}")
