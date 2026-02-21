# Multi-Repo Persistent Graph - Design Document

## Overview

This design evolves the current single-repo supply chain graph system into a multi-repo persistent graph storage system. The current system generates graphs dynamically for individual repositories on demand, storing data in memory that disappears after each request. This design introduces:

1. **Persistent Storage:** Graph data stored in SQLite database with JSON blobs + index tables
2. **Batch Ingestion:** Background job system for ingesting multiple repositories
3. **Cross-Repo Queries:** Index-based lookups across repositories (maintainers, CVEs, registries)
4. **Backward Compatibility:** Existing `/api/graph` endpoint continues to work seamlessly

**Core Philosophy:** Pragmatic, incremental evolution. Store graphs as JSON blobs with strategic indexes for cross-repo queries. Avoid premature optimization for graph traversal—that's Step 2. Focus on persistence and batch ingestion.

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│  /api/graph (existing)    /api/ingest (new)                 │
│  /api/jobs (new)          /api/repos (new)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│  Graph Builder   │ │  Job Manager │ │  Query API   │
│  (existing)      │ │  (new)       │ │  (new)       │
└──────────────────┘ └──────────────┘ └──────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Persistence Layer                         │
│  • GraphRepository (CRUD for graphs)                         │
│  • JobRepository (job state management)                      │
│  • IndexRepository (cross-repo lookups)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      SQLite Database                         │
│  • repo_graphs (JSON blobs)                                  │
│  • ingestion_jobs (job state)                                │
│  • repo_maintainers (index)                                  │
│  • repo_cves (index)                                         │
│  • repo_registries (index)                                   │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **JSON Blob + Indexes:** Store complete graph as JSON per repo, with separate index tables for fast cross-repo lookups
2. **Backward Compatible:** Existing API works unchanged; database is transparent to consumers
3. **Graceful Degradation:** If database unavailable, fall back to dynamic generation
4. **Transactional Writes:** All-or-nothing per repository to prevent corruption
5. **Simple Job System:** Database-backed job table + polling worker, no external queue
6. **Abstracted Persistence:** Clean interface for future migration to PostgreSQL/Neo4j


## Database Schema

### Environment Configuration

The system supports the following environment variables:

```bash
# Database configuration
GRAPH_DB_PATH=data/graphs.db              # Path to SQLite database file
GRAPH_DB_ENABLED=true                     # Enable/disable persistence layer
GRAPH_TTL_HOURS=24                        # Cache TTL in hours
GRAPH_AUTO_REFRESH_STALE=false            # Auto-regenerate stale data (if false, return with is_stale flag)

# Job worker configuration
GRAPH_WORKER_POLL_INTERVAL=5              # Seconds between job queue polls
GRAPH_WORKER_ENABLED=true                 # Enable/disable background worker
```

**Configuration Behavior:**
- `GRAPH_DB_ENABLED=false`: Disables persistence layer entirely, falls back to pure dynamic generation
- `GRAPH_AUTO_REFRESH_STALE=false`: Returns stale cached data with `is_stale: true` metadata instead of regenerating
- `GRAPH_AUTO_REFRESH_STALE=true`: Automatically regenerates data when TTL exceeded (may cause slower responses)

### Table: repo_graphs

Stores the complete graph JSON for each repository.

```sql
CREATE TABLE repo_graphs (
    repo_full_name TEXT PRIMARY KEY,  -- e.g., "numpy/numpy"
    graph_json TEXT NOT NULL,          -- Complete graph as JSON string
    schema_version TEXT NOT NULL,      -- e.g., "1.0"
    node_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,          -- ISO timestamp
    updated_at TEXT NOT NULL,          -- ISO timestamp
    data_sources TEXT NOT NULL,        -- JSON array of sources, e.g., ["github_api", "osv"]
    warnings TEXT,                     -- JSON array of warnings (nullable)
    generation_time_ms INTEGER         -- Time to generate graph
);

CREATE INDEX idx_repo_graphs_updated_at ON repo_graphs(updated_at);
```

**Design Rationale:**
- `graph_json` stores the entire graph structure (nodes + edges + metadata) as JSON
- This avoids complex relational mapping and preserves the existing graph schema
- Indexes on `updated_at` enable freshness queries
- `repo_full_name` is the natural primary key (owner/repo format)

### Table: ingestion_jobs

Tracks batch ingestion job state.

```sql
CREATE TABLE ingestion_jobs (
    job_id TEXT PRIMARY KEY,           -- UUID
    status TEXT NOT NULL,              -- pending, running, completed, failed, interrupted
    repo_list TEXT NOT NULL,           -- JSON array of repo names
    total_repos INTEGER NOT NULL,
    processed_repos INTEGER DEFAULT 0,
    successful_repos INTEGER DEFAULT 0,
    failed_repos INTEGER DEFAULT 0,
    errors TEXT,                       -- JSON array of error objects
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    config TEXT                        -- JSON of GraphConfig used
);

CREATE INDEX idx_ingestion_jobs_status ON ingestion_jobs(status);
CREATE INDEX idx_ingestion_jobs_created_at ON ingestion_jobs(created_at);
```

**Design Rationale:**
- Simple state machine: pending → running → (completed | failed | interrupted)
- `repo_list` stored as JSON array for simplicity
- `errors` captures per-repo failures without blocking the job
- Indexes support filtering by status and time-based queries

### Table: repo_maintainers

Index for cross-repo maintainer lookups.

```sql
CREATE TABLE repo_maintainers (
    repo_full_name TEXT NOT NULL,
    maintainer_username TEXT NOT NULL,
    contribution_fraction REAL NOT NULL,
    commit_count INTEGER NOT NULL,
    PRIMARY KEY (repo_full_name, maintainer_username),
    FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
);

CREATE INDEX idx_repo_maintainers_username ON repo_maintainers(maintainer_username);
```

**Design Rationale:**
- Enables fast "find all repos by maintainer" queries
- Denormalized from graph JSON for query performance
- Cascade delete ensures cleanup when repo is removed

### Table: repo_cves

Index for cross-repo CVE lookups.

```sql
CREATE TABLE repo_cves (
    repo_full_name TEXT NOT NULL,
    cve_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    cvss_score REAL,
    affected_releases TEXT,            -- JSON array of release tags
    PRIMARY KEY (repo_full_name, cve_id),
    FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
);

CREATE INDEX idx_repo_cves_cve_id ON repo_cves(cve_id);
CREATE INDEX idx_repo_cves_severity ON repo_cves(severity);
```

**Design Rationale:**
- Enables fast "find all repos affected by CVE-X" queries
- `affected_releases` stored as JSON for flexibility
- Indexes on `cve_id` and `severity` support common query patterns

### Table: repo_registries

Index for cross-repo registry lookups.

```sql
CREATE TABLE repo_registries (
    repo_full_name TEXT NOT NULL,
    registry_type TEXT NOT NULL,       -- pypi, npm, maven, etc.
    package_name TEXT NOT NULL,
    latest_version TEXT,
    PRIMARY KEY (repo_full_name, registry_type, package_name),
    FOREIGN KEY (repo_full_name) REFERENCES repo_graphs(repo_full_name) ON DELETE CASCADE
);

CREATE INDEX idx_repo_registries_package ON repo_registries(registry_type, package_name);
```

**Design Rationale:**
- Enables fast "find repo for package X in registry Y" queries
- Composite primary key handles repos published to multiple registries
- Index on (registry_type, package_name) supports package lookup

### Schema Versioning

The database schema includes a version table for future migrations:

```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

INSERT INTO schema_version (version, applied_at) VALUES (1, datetime('now'));
```


## Persistence Layer Architecture

### Interface: GraphRepository

Abstraction for graph CRUD operations.

```python
from typing import Optional, List, Dict, Any
from datetime import datetime

class GraphRepository:
    """Repository for storing and retrieving repository graphs."""
    
    def save_graph(
        self,
        repo_full_name: str,
        graph: Graph,
        generation_time_ms: int
    ) -> None:
        """
        Save or update a repository graph.
        
        Args:
            repo_full_name: Repository identifier (owner/repo)
            graph: Complete graph object
            generation_time_ms: Time taken to generate graph
        
        Raises:
            DatabaseError: If save fails
        """
        pass
    
    def get_graph(self, repo_full_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a repository graph.
        
        Args:
            repo_full_name: Repository identifier
        
        Returns:
            Graph data as dict (includes graph, metadata, timestamps)
            None if not found
        """
        pass
    
    def delete_graph(self, repo_full_name: str) -> bool:
        """
        Delete a repository graph and all associated indexes.
        
        Args:
            repo_full_name: Repository identifier
        
        Returns:
            True if deleted, False if not found
        """
        pass
    
    def list_repos(
        self,
        limit: int = 100,
        offset: int = 0,
        older_than: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        List repositories with metadata.
        
        Args:
            limit: Maximum number of results
            offset: Pagination offset
            older_than: Filter for repos updated before this time
        
        Returns:
            List of repo metadata dicts (name, node_count, updated_at, etc.)
        """
        pass
    
    def get_repo_count(self) -> int:
        """Get total number of stored repositories."""
        pass
```

### Interface: IndexRepository

Abstraction for cross-repo index queries.

```python
class IndexRepository:
    """Repository for cross-repo indexed lookups."""
    
    def find_repos_by_maintainer(
        self,
        username: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all repositories maintained by a user.
        
        Args:
            username: GitHub username
            limit: Maximum results
        
        Returns:
            List of dicts with repo_full_name, contribution_fraction, commit_count
        """
        pass
    
    def find_repos_by_cve(
        self,
        cve_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all repositories affected by a CVE.
        
        Args:
            cve_id: CVE identifier (e.g., "CVE-2024-1234")
            limit: Maximum results
        
        Returns:
            List of dicts with repo_full_name, severity, affected_releases
        """
        pass
    
    def find_repo_by_package(
        self,
        registry_type: str,
        package_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find repository for a package in a registry.
        
        Args:
            registry_type: Registry type (pypi, npm, maven, etc.)
            package_name: Package name
        
        Returns:
            Dict with repo_full_name, latest_version, or None if not found
        """
        pass
    
    def find_repos_sharing_maintainer(
        self,
        repo_full_name: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find repositories sharing maintainers with the given repo.
        
        Args:
            repo_full_name: Reference repository
            limit: Maximum results
        
        Returns:
            List of dicts with repo_full_name, shared_maintainers (list of usernames)
        """
        pass
```

### Interface: JobRepository

Abstraction for job state management.

```python
from enum import Enum

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

class JobRepository:
    """Repository for ingestion job state."""
    
    def create_job(
        self,
        repo_list: List[str],
        config: Optional[GraphConfig] = None
    ) -> str:
        """
        Create a new ingestion job.
        
        Args:
            repo_list: List of repository identifiers
            config: Graph configuration for ingestion
        
        Returns:
            Job ID (UUID)
        """
        pass
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job details.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Job data dict or None if not found
        """
        pass
    
    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        processed: Optional[int] = None,
        successful: Optional[int] = None,
        failed: Optional[int] = None,
        errors: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Update job status and progress.
        
        Args:
            job_id: Job identifier
            status: New status
            processed: Number of repos processed (optional)
            successful: Number of successful ingestions (optional)
            failed: Number of failed ingestions (optional)
            errors: List of error objects (optional)
        """
        pass
    
    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List jobs with optional status filter.
        
        Args:
            status: Filter by status (optional)
            limit: Maximum results
            offset: Pagination offset
        
        Returns:
            List of job data dicts
        """
        pass
```

### Implementation: SQLiteGraphRepository

Concrete implementation using SQLite.

```python
import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

class SQLiteGraphRepository(GraphRepository):
    """SQLite implementation of GraphRepository."""
    
    def __init__(self, db_path: str = "data/graphs.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize database schema if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            # Set SQLite pragmas for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            
            # Create tables (schema from Database Schema section)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS repo_graphs (...);
                CREATE TABLE IF NOT EXISTS repo_maintainers (...);
                CREATE TABLE IF NOT EXISTS repo_cves (...);
                CREATE TABLE IF NOT EXISTS repo_registries (...);
                CREATE TABLE IF NOT EXISTS schema_version (...);
                -- Create indexes
            """)
            
            # Insert schema version (idempotent)
            conn.execute("""
                INSERT OR IGNORE INTO schema_version (version, applied_at)
                VALUES (1, datetime('now'))
            """)
    
    def save_graph(
        self,
        repo_full_name: str,
        graph: Graph,
        generation_time_ms: int
    ) -> None:
        """Save graph with transaction and index updates."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Serialize graph to JSON
                graph_json = json.dumps(graph.to_dict())
                now = datetime.now(timezone.utc).isoformat()
                
                # Upsert repo_graphs
                conn.execute("""
                    INSERT OR REPLACE INTO repo_graphs
                    (repo_full_name, graph_json, schema_version, node_count, edge_count,
                     created_at, updated_at, data_sources, warnings, generation_time_ms)
                    VALUES (?, ?, ?, ?, ?, COALESCE(
                        (SELECT created_at FROM repo_graphs WHERE repo_full_name = ?),
                        ?
                    ), ?, ?, ?, ?)
                """, (
                    repo_full_name, graph_json, graph.metadata.get("schema_version", "1.0"),
                    len(graph.nodes), len(graph.edges),
                    repo_full_name, now,  # For COALESCE
                    now,  # updated_at
                    json.dumps(graph.metadata.get("data_sources", [])),
                    json.dumps(graph.metadata.get("warnings", [])),
                    generation_time_ms
                ))
                
                # Update indexes
                self._update_indexes(conn, repo_full_name, graph)
                
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                raise DatabaseError(f"Failed to save graph: {e}")
    
    def _update_indexes(
        self,
        conn: sqlite3.Connection,
        repo_full_name: str,
        graph: Graph
    ) -> None:
        """Update index tables from graph data."""
        # Delete existing indexes for this repo
        conn.execute("DELETE FROM repo_maintainers WHERE repo_full_name = ?", (repo_full_name,))
        conn.execute("DELETE FROM repo_cves WHERE repo_full_name = ?", (repo_full_name,))
        conn.execute("DELETE FROM repo_registries WHERE repo_full_name = ?", (repo_full_name,))
        
        # Build node lookup dict for O(1) access (avoid O(N^2))
        node_by_id = {node.id: node for node in graph.nodes}
        
        # Extract and insert maintainers
        for node in graph.nodes:
            if node.type == NodeType.MAINTAINER:
                username = node.metadata.get("username")
                if username:
                    conn.execute("""
                        INSERT INTO repo_maintainers
                        (repo_full_name, maintainer_username, contribution_fraction, commit_count)
                        VALUES (?, ?, ?, ?)
                    """, (
                        repo_full_name,
                        username,
                        node.metadata.get("contribution_fraction", 0.0),
                        node.metadata.get("commit_count", 0)
                    ))
        
        # Extract and insert CVEs
        for node in graph.nodes:
            if node.type == NodeType.CVE:
                cve_id = node.metadata.get("cve_id")
                if cve_id:
                    # Find affected releases using node lookup dict
                    affected_releases = []
                    for edge in graph.edges:
                        if edge.target == node.id and edge.relationship_type == EdgeType.HAS_CVE:
                            # O(1) lookup instead of O(N) search
                            release_node = node_by_id.get(edge.source)
                            if release_node:
                                affected_releases.append(release_node.metadata.get("tag_name", ""))
                    
                    conn.execute("""
                        INSERT INTO repo_cves
                        (repo_full_name, cve_id, severity, cvss_score, affected_releases)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        repo_full_name,
                        cve_id,
                        node.metadata.get("severity", "UNKNOWN"),
                        node.metadata.get("cvss_score"),
                        json.dumps(affected_releases)
                    ))
        
        # Extract and insert registries
        for node in graph.nodes:
            if node.type == NodeType.REGISTRY:
                registry_type = node.metadata.get("registry_type")
                package_name = node.metadata.get("package_name")
                if registry_type and package_name:
                    conn.execute("""
                        INSERT INTO repo_registries
                        (repo_full_name, registry_type, package_name, latest_version)
                        VALUES (?, ?, ?, ?)
                    """, (
                        repo_full_name,
                        registry_type,
                        package_name,
                        node.metadata.get("latest_version")
                    ))
    
    def get_graph(self, repo_full_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve graph from database.
        
        Returns response in exact same format as /api/graph endpoint.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM repo_graphs WHERE repo_full_name = ?
            """, (repo_full_name,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Return in exact /api/graph format
            return {
                "repo": row["repo_full_name"],
                "schema_version": row["schema_version"],
                "generated_at": row["updated_at"],
                "graph": json.loads(row["graph_json"]),
                "metadata": {
                    "node_count": row["node_count"],
                    "edge_count": row["edge_count"],
                    "data_sources": json.loads(row["data_sources"]),
                    "warnings": json.loads(row["warnings"]) if row["warnings"] else [],
                    "generation_time_ms": row["generation_time_ms"],
                    "cache_hit": True,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            }
```

**Design Rationale:**
- Transaction ensures atomicity: graph + indexes updated together or not at all
- COALESCE preserves original `created_at` on updates
- Index extraction happens in same transaction as graph save
- JSON serialization handles complex graph structures without schema changes


## Job Management System

### Job Lifecycle

```
┌─────────┐
│ PENDING │  Job created, not yet started
└────┬────┘
     │
     ▼
┌─────────┐
│ RUNNING │  Worker processing repositories
└────┬────┘
     │
     ├──────────────┬──────────────┐
     ▼              ▼              ▼
┌───────────┐  ┌─────────┐  ┌──────────────┐
│ COMPLETED │  │ FAILED  │  │ INTERRUPTED  │
└───────────┘  └─────────┘  └──────────────┘
```

**State Transitions:**
- `PENDING → RUNNING`: Worker picks up job
- `RUNNING → COMPLETED`: All repos processed successfully (some individual repos may have failed, but job completed processing the entire list)
- `RUNNING → FAILED`: Job-level infrastructure failure prevented completion (e.g., database error, critical exception)
- `RUNNING → INTERRUPTED`: Server restart or manual cancellation

**Status Definitions:**
- **COMPLETED:** Job finished processing the entire repository list. Check `successful_repos` and `failed_repos` counts for details. A job can be COMPLETED even if some individual repositories failed—this indicates the job infrastructure worked correctly.
- **FAILED:** Job-level failure that prevented the job from completing its work. This indicates an infrastructure problem, not just individual repository failures.
- **INTERRUPTED:** Job was running when the server stopped. Job state is preserved but execution did not complete. Must be re-submitted to process remaining repositories.

### Job Worker

Background worker that polls for pending jobs and processes them.

```python
import asyncio
import uuid
from typing import List, Dict, Any

class IngestionWorker:
    """Background worker for processing ingestion jobs."""
    
    def __init__(
        self,
        job_repo: JobRepository,
        graph_repo: GraphRepository,
        poll_interval: int = 5
    ):
        self.job_repo = job_repo
        self.graph_repo = graph_repo
        self.poll_interval = poll_interval
        self.running = False
    
    async def start(self) -> None:
        """Start the worker loop."""
        self.running = True
        while self.running:
            try:
                # Find pending jobs
                pending_jobs = self.job_repo.list_jobs(
                    status=JobStatus.PENDING,
                    limit=1
                )
                
                if pending_jobs:
                    job = pending_jobs[0]
                    await self._process_job(job)
                else:
                    # No pending jobs, wait before polling again
                    await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
    
    def stop(self) -> None:
        """Stop the worker loop."""
        self.running = False
    
    async def _process_job(self, job: Dict[str, Any]) -> None:
        """Process a single ingestion job."""
        job_id = job["job_id"]
        repo_list = json.loads(job["repo_list"])
        config_dict = json.loads(job["config"]) if job["config"] else {}
        config = GraphConfig(**config_dict)
        
        # Mark job as running
        self.job_repo.update_job_status(
            job_id=job_id,
            status=JobStatus.RUNNING
        )
        
        processed = 0
        successful = 0
        failed = 0
        errors = []
        
        try:
            for repo_full_name in repo_list:
                try:
                    # Generate and save graph
                    await self._ingest_repository(repo_full_name, config)
                    successful += 1
                except Exception as e:
                    failed += 1
                    errors.append({
                        "repo": repo_full_name,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    logger.warning(f"Failed to ingest {repo_full_name}: {e}")
                
                processed += 1
                
                # Update progress periodically
                if processed % 10 == 0:
                    self.job_repo.update_job_status(
                        job_id=job_id,
                        status=JobStatus.RUNNING,
                        processed=processed,
                        successful=successful,
                        failed=failed,
                        errors=errors
                    )
            
            # Mark job as completed
            self.job_repo.update_job_status(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                processed=processed,
                successful=successful,
                failed=failed,
                errors=errors
            )
            
            logger.info(
                f"Job {job_id} completed: {successful} successful, {failed} failed"
            )
        
        except Exception as e:
            # Job-level failure
            self.job_repo.update_job_status(
                job_id=job_id,
                status=JobStatus.FAILED,
                processed=processed,
                successful=successful,
                failed=failed,
                errors=errors + [{
                    "error": f"Job failed: {str(e)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }]
            )
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
    
    async def _ingest_repository(
        self,
        repo_full_name: str,
        config: GraphConfig
    ) -> None:
        """Ingest a single repository."""
        start_time = time.time()
        
        # Import from correct modules (verify paths during implementation)
        # TODO: Confirm these import paths match actual project structure
        from open_source_risk_model.service.score_repo import score_repo
        from open_source_risk_model.graph.builder import build_graph
        
        # Score the repository
        score_data = score_repo(repo_full_name, refresh=True)
        
        # Build the graph
        graph = build_graph(repo_full_name, score_data, config)
        
        # Calculate generation time
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Save to database
        self.graph_repo.save_graph(repo_full_name, graph, generation_time_ms)
        
        logger.info(f"Ingested {repo_full_name} in {generation_time_ms}ms")
```

**Design Rationale:**
- Simple polling loop avoids external queue dependencies
- Async/await enables concurrent processing in future enhancements
- Per-repo error handling ensures one failure doesn't stop the job
- Progress updates every 10 repos balance responsiveness and database load
- Job state persisted in database survives server restarts

### Concurrency Strategy

For Step 1, we use a simple single-worker model:
- One worker thread polls for pending jobs
- Jobs processed sequentially
- Repositories within a job processed sequentially

**Future Enhancement (Step 2+):**
- Multiple worker threads/processes
- Concurrent repository processing within jobs
- Distributed job queue (Celery, RQ)


## API Design

### Modified Endpoint: GET /api/graph

The existing endpoint is enhanced to use the database when available.

**Behavior Changes:**
1. Check database first for cached graph
2. If found and not expired (based on TTL), return cached data
3. If not found or `refresh=true`, generate dynamically and save to database
4. If database unavailable, fall back to dynamic generation (no save)

**Implementation:**

```python
@app.get("/api/graph")
async def get_graph(
    repo: str,
    refresh: bool = False,
    include_cves: bool = True,
    max_releases: int = 10,
    max_maintainers: int = 5
):
    """Get repository supply chain graph (with database caching)."""
    try:
        # Parse repo identifier
        repo_full_name = parse_repo_identifier(repo)
        
        # Try database first (unless refresh requested)
        if not refresh:
            try:
                cached_graph = graph_repo.get_graph(repo_full_name)
                if cached_graph:
                    # Check TTL
                    updated_at = datetime.fromisoformat(cached_graph["generated_at"])
                    age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
                    
                    # Determine if we should use cached data
                    auto_refresh_stale = os.getenv("GRAPH_AUTO_REFRESH_STALE", "false").lower() == "true"
                    
                    if age_hours < config.cache_ttl_hours:
                        # Fresh data, return immediately
                        logger.info(f"Returning cached graph for {repo_full_name}")
                        return cached_graph
                    elif not auto_refresh_stale:
                        # Stale but auto-refresh disabled, return with stale indicator
                        logger.info(f"Returning stale cached graph for {repo_full_name}")
                        cached_graph["metadata"]["is_stale"] = True
                        cached_graph["metadata"]["age_hours"] = age_hours
                        return cached_graph
                    # else: fall through to regeneration
            except Exception as e:
                logger.warning(f"Database read failed, falling back to dynamic: {e}")
        
        # Generate graph dynamically
        start_time = time.time()
        score_data = score_repo(repo_full_name, refresh=refresh)
        
        config = GraphConfig(
            include_cves=include_cves,
            max_releases=max_releases,
            max_maintainers=max_maintainers
        )
        graph = build_graph(repo_full_name, score_data, config)
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Try to save to database
        try:
            graph_repo.save_graph(repo_full_name, graph, generation_time_ms)
            logger.info(f"Saved graph for {repo_full_name} to database")
        except Exception as e:
            logger.warning(f"Failed to save graph to database: {e}")
        
        # Return graph in existing format
        return {
            "repo": repo_full_name,
            "schema_version": graph.metadata.get("schema_version", "1.0"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "graph": graph.to_dict(),
            "metadata": {
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "data_sources": graph.metadata.get("data_sources", []),
                "warnings": graph.metadata.get("warnings", []),
                "generation_time_ms": generation_time_ms,
                "cache_hit": False
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get graph for {repo}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate graph: {str(e)}")
```

**Backward Compatibility:**
- Response format unchanged
- Query parameters unchanged
- Error responses unchanged
- `cache_hit` metadata field indicates whether data came from database

### New Endpoint: POST /api/ingest

Submit a batch ingestion job.

**Request:**

```json
{
  "repos": [
    "numpy/numpy",
    "pandas-dev/pandas",
    "scikit-learn/scikit-learn"
  ],
  "config": {
    "include_cves": true,
    "max_releases": 10,
    "max_maintainers": 5
  }
}
```

**Response (202 Accepted):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "total_repos": 3,
  "created_at": "2026-02-18T10:30:00Z",
  "message": "Ingestion job created successfully"
}
```

**Implementation:**

```python
from pydantic import BaseModel

class IngestRequest(BaseModel):
    repos: List[str]
    config: Optional[Dict[str, Any]] = None

@app.post("/api/ingest", status_code=202)
async def create_ingestion_job(request: IngestRequest):
    """Create a batch ingestion job."""
    try:
        # Validate repo list
        if not request.repos:
            raise HTTPException(status_code=400, detail="repos list cannot be empty")
        
        if len(request.repos) > 1000:
            raise HTTPException(status_code=400, detail="Maximum 1000 repos per job")
        
        # Parse config
        config = GraphConfig(**request.config) if request.config else GraphConfig()
        
        # Create job
        job_id = job_repo.create_job(request.repos, config)
        
        logger.info(f"Created ingestion job {job_id} with {len(request.repos)} repos")
        
        return {
            "job_id": job_id,
            "status": "pending",
            "total_repos": len(request.repos),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": "Ingestion job created successfully"
        }
    
    except Exception as e:
        logger.error(f"Failed to create ingestion job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")
```

### New Endpoint: GET /api/jobs/{job_id}

Query job status and progress.

**Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "total_repos": 100,
  "processed_repos": 45,
  "successful_repos": 43,
  "failed_repos": 2,
  "created_at": "2026-02-18T10:30:00Z",
  "started_at": "2026-02-18T10:30:05Z",
  "errors": [
    {
      "repo": "invalid/repo",
      "error": "Repository not found",
      "timestamp": "2026-02-18T10:32:15Z"
    }
  ]
}
```

**Implementation:**

```python
@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get ingestion job status."""
    try:
        job = job_repo.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        return job
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")
```

### New Endpoint: GET /api/jobs

List ingestion jobs with optional filtering.

**Query Parameters:**
- `status`: Filter by status (pending, running, completed, failed, interrupted)
- `limit`: Maximum results (default: 100)
- `offset`: Pagination offset (default: 0)

**Response:**

```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "total_repos": 100,
      "successful_repos": 98,
      "failed_repos": 2,
      "created_at": "2026-02-18T10:30:00Z",
      "completed_at": "2026-02-18T11:15:00Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### New Endpoint: GET /api/repos

List stored repositories with metadata.

**Query Parameters:**
- `limit`: Maximum results (default: 100)
- `offset`: Pagination offset (default: 0)
- `older_than`: ISO timestamp to filter repos updated before this time

**Response:**

```json
{
  "repos": [
    {
      "repo_full_name": "numpy/numpy",
      "node_count": 25,
      "edge_count": 30,
      "created_at": "2026-02-18T10:30:00Z",
      "updated_at": "2026-02-18T10:30:00Z",
      "data_sources": ["github_api", "osv"],
      "generation_time_ms": 2450
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### New Endpoint: GET /api/repos/by-maintainer/{username}

Find repositories by maintainer.

**Response:**

```json
{
  "maintainer": "charris",
  "repos": [
    {
      "repo_full_name": "numpy/numpy",
      "contribution_fraction": 0.23,
      "commit_count": 5234
    }
  ],
  "total": 1
}
```

### New Endpoint: GET /api/repos/by-cve/{cve_id}

Find repositories affected by a CVE.

**Response:**

```json
{
  "cve_id": "CVE-2024-1234",
  "repos": [
    {
      "repo_full_name": "numpy/numpy",
      "severity": "HIGH",
      "affected_releases": ["v1.25.0", "v1.25.1"]
    }
  ],
  "total": 1
}
```

### New Endpoint: GET /api/repos/by-package

Find repository by package name.

**Query Parameters:**
- `registry`: Registry type (pypi, npm, maven, etc.)
- `package`: Package name

**Response:**

```json
{
  "registry_type": "pypi",
  "package_name": "numpy",
  "repo_full_name": "numpy/numpy",
  "latest_version": "1.26.0"
}
```

### New Endpoint: DELETE /api/repos/{repo_full_name}

Delete a repository from the database.

**Response (204 No Content):**

```
(empty body)
```


## Data Models

### Graph Storage Format

Graphs are stored as JSON blobs in the `repo_graphs.graph_json` column. The format matches the existing `Graph.to_dict()` output:

```json
{
  "nodes": [
    {
      "id": "repo:numpy/numpy",
      "type": "repo",
      "label": "numpy/numpy",
      "metadata": {
        "url": "https://github.com/numpy/numpy",
        "maintenance_risk": 0.197,
        "maintenance_label": "low"
      },
      "provenance": {
        "source": "github_api",
        "fetched_at": "2026-02-18T10:30:00Z",
        "data_confidence": 1.0
      }
    }
  ],
  "edges": [
    {
      "source": "repo:numpy/numpy",
      "target": "release:numpy/numpy:v1.26.0",
      "relationship_type": "has_release",
      "metadata": {
        "days_ago": 150,
        "is_latest": true
      },
      "provenance": {
        "source": "github_api",
        "established_at": "2026-02-18T10:30:00Z",
        "confidence": 1.0
      }
    }
  ],
  "metadata": {
    "schema_version": "1.0",
    "generated_at": "2026-02-18T10:30:00Z",
    "data_sources": ["github_api", "osv"],
    "warnings": []
  }
}
```

**Design Rationale:**
- Reuses existing graph schema without modification
- JSON storage is flexible for schema evolution
- SQLite JSON functions enable querying within blobs if needed
- Serialization/deserialization handled by existing `Graph.to_dict()` and `Graph.from_dict()`

### Job State Format

Jobs are stored with the following structure:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "repo_list": ["numpy/numpy", "pandas-dev/pandas"],
  "total_repos": 2,
  "processed_repos": 1,
  "successful_repos": 1,
  "failed_repos": 0,
  "errors": [],
  "created_at": "2026-02-18T10:30:00Z",
  "started_at": "2026-02-18T10:30:05Z",
  "completed_at": null,
  "config": {
    "include_cves": true,
    "max_releases": 10,
    "max_maintainers": 5
  }
}
```

### Index Data Format

Index tables store denormalized data for fast lookups:

**repo_maintainers:**
```
repo_full_name | maintainer_username | contribution_fraction | commit_count
numpy/numpy    | charris             | 0.23                  | 5234
```

**repo_cves:**
```
repo_full_name | cve_id          | severity | cvss_score | affected_releases
numpy/numpy    | CVE-2024-1234   | HIGH     | 7.5        | ["v1.25.0", "v1.25.1"]
```

**repo_registries:**
```
repo_full_name | registry_type | package_name | latest_version
numpy/numpy    | pypi          | numpy        | 1.26.0
```


## Error Handling

### Database Errors

**Strategy:** Graceful degradation with fallback to dynamic generation.

```python
def get_graph_with_fallback(repo_full_name: str, config: GraphConfig) -> Dict[str, Any]:
    """Get graph with database fallback."""
    try:
        # Try database first
        cached = graph_repo.get_graph(repo_full_name)
        if cached:
            return cached
    except DatabaseError as e:
        logger.warning(f"Database read failed for {repo_full_name}: {e}")
        # Fall through to dynamic generation
    
    # Generate dynamically
    try:
        score_data = score_repo(repo_full_name)
        graph = build_graph(repo_full_name, score_data, config)
        
        # Try to save (best effort)
        try:
            graph_repo.save_graph(repo_full_name, graph, 0)
        except DatabaseError as e:
            logger.warning(f"Failed to save graph: {e}")
        
        return format_graph_response(graph)
    
    except Exception as e:
        logger.error(f"Failed to generate graph: {e}", exc_info=True)
        raise
```

### Ingestion Errors

**Strategy:** Per-repo error handling with job-level resilience.

**Error Categories:**

1. **Repository Not Found (404):**
   - Log error with repo name
   - Continue to next repo
   - Include in job error list

2. **GitHub API Rate Limit:**
   - Detect rate limit response
   - Wait until rate limit resets
   - Retry repository
   - If still failing, mark as error and continue

3. **CVE Fetch Timeout:**
   - Log warning
   - Continue with partial graph (no CVE nodes)
   - Include warning in graph metadata

4. **Database Write Failure:**
   - Roll back transaction for that repo
   - Log error
   - Continue to next repo
   - Include in job error list

5. **Job-Level Failure:**
   - Critical exception in worker loop
   - Mark job as FAILED
   - Persist partial progress
   - Log full stack trace

### Validation Errors

**Strategy:** Validate before saving to prevent invalid data in database.

```python
def save_graph_with_validation(
    repo_full_name: str,
    graph: Graph,
    generation_time_ms: int
) -> None:
    """Save graph with validation."""
    # Validate graph structure
    errors = graph.validate()
    if errors:
        raise ValidationError(f"Invalid graph: {errors}")
    
    # Validate required fields
    if not graph.nodes:
        raise ValidationError("Graph must contain at least one node")
    
    repo_nodes = [n for n in graph.nodes if n.type == NodeType.REPO]
    if len(repo_nodes) != 1:
        raise ValidationError("Graph must contain exactly one repo node")
    
    # Save to database
    graph_repo.save_graph(repo_full_name, graph, generation_time_ms)
```

### Concurrency Errors

**Strategy:** Database-level locking prevents concurrent writes to same repo.

```python
def save_graph_with_lock(
    repo_full_name: str,
    graph: Graph,
    generation_time_ms: int
) -> None:
    """Save graph with row-level locking."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")  # Acquire write lock
        try:
            # Check if repo exists and lock row
            cursor = conn.execute("""
                SELECT repo_full_name FROM repo_graphs
                WHERE repo_full_name = ?
            """, (repo_full_name,))
            
            # Perform save operations
            # ...
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
```

### Server Restart Handling

**Strategy:** Jobs marked as INTERRUPTED can be identified and re-submitted.

```python
def mark_interrupted_jobs() -> None:
    """Mark running jobs as interrupted on startup."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            UPDATE ingestion_jobs
            SET status = 'interrupted'
            WHERE status = 'running'
        """)
        conn.commit()
    
    logger.info("Marked interrupted jobs")
```

This function should be called on application startup to clean up jobs that were running when the server stopped.


## Migration Strategy

### Phase 1: Add Persistence Layer (No Breaking Changes)

1. **Add database schema and repositories:**
   - Create SQLite database with schema
   - Implement GraphRepository, JobRepository, IndexRepository
   - Add database initialization on startup

2. **Enhance `/api/graph` endpoint:**
   - Check database before dynamic generation
   - Save generated graphs to database
   - Maintain exact same response format
   - Add `cache_hit` metadata field

3. **Testing:**
   - Verify existing tests still pass
   - Add tests for database operations
   - Test fallback behavior when database unavailable

**Result:** Existing functionality works unchanged, with transparent caching.

### Phase 2: Add Ingestion System

1. **Implement job management:**
   - Add JobRepository implementation
   - Create IngestionWorker
   - Add worker startup/shutdown hooks

2. **Add new API endpoints:**
   - POST /api/ingest
   - GET /api/jobs/{job_id}
   - GET /api/jobs

3. **Testing:**
   - Test job creation and status tracking
   - Test batch ingestion with various repo lists
   - Test error handling and partial failures

**Result:** Batch ingestion capability available.

### Phase 3: Add Cross-Repo Queries

1. **Implement index queries:**
   - Add IndexRepository implementation
   - Ensure indexes populated during graph save

2. **Add query endpoints:**
   - GET /api/repos
   - GET /api/repos/by-maintainer/{username}
   - GET /api/repos/by-cve/{cve_id}
   - GET /api/repos/by-package

3. **Testing:**
   - Test index population
   - Test cross-repo queries
   - Test pagination

**Result:** Cross-repo exploration capability available.

### Phase 4: Production Hardening

1. **Add monitoring:**
   - Database size metrics
   - Ingestion job metrics
   - Query performance metrics

2. **Add maintenance tools:**
   - Database backup/restore scripts
   - Stale data cleanup
   - Index rebuild utility

3. **Documentation:**
   - API documentation updates
   - Deployment guide
   - Troubleshooting guide

**Result:** Production-ready system.

### Rollback Plan

If issues arise, the system can be rolled back by:

1. **Disable database writes:**
   - Set environment variable `DISABLE_GRAPH_PERSISTENCE=true`
   - System falls back to pure dynamic generation

2. **Disable ingestion endpoints:**
   - Remove ingestion routes from API
   - Existing `/api/graph` continues to work

3. **Database removal:**
   - Delete `data/graphs.db`
   - System operates as before persistence layer

**No data loss:** Dynamic generation always works as fallback.


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Persistence Properties

**Property 1: Graph Storage Round-Trip**

*For any* valid repository graph, saving it to the database and then retrieving it should produce an equivalent graph with all nodes, edges, metadata, and provenance preserved.

**Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.6**

**Rationale:** This is a fundamental round-trip property that ensures the persistence layer correctly stores and retrieves graph data without loss or corruption. If this property holds, it guarantees that all node fields (id, type, label, metadata, provenance), all edge fields (source, target, relationship_type, metadata, provenance), and the complete graph schema are preserved through the storage cycle.

---

**Property 2: Database Persistence Across Restarts**

*For any* set of repository graphs stored in the database, closing and reopening the database connection should preserve all graph data.

**Validates: Requirements 1.3**

**Rationale:** This validates that data is truly persisted to disk and not just held in memory. This is a critical property for a persistence layer.

---

**Property 3: Update Idempotency**

*For any* repository, ingesting it multiple times should result in exactly one entry in the database with the most recent data and an updated timestamp.

**Validates: Requirements 2.6, 7.4**

**Rationale:** This ensures the system correctly handles re-ingestion without creating duplicates. The updated timestamp validates that the system tracks data freshness.

---

### Batch Ingestion Properties

**Property 4: Batch Completeness**

*For any* list of valid repository identifiers, submitting a batch ingestion job should result in all repositories being processed (either successfully or with recorded errors).

**Validates: Requirements 2.1, 2.4**

**Rationale:** This ensures batch ingestion processes all repos in the list and correctly reports success/failure counts.

---

**Property 5: Ingestion Resilience**

*For any* batch ingestion job containing a mix of valid and invalid repositories, the job should complete successfully and process all valid repositories despite failures on invalid ones.

**Validates: Requirements 2.3, 9.4**

**Rationale:** This validates that partial failures don't stop the entire job. The system should be resilient to individual repository failures.

---

**Property 6: Transaction Atomicity**

*For any* repository ingestion that encounters a database write failure, no partial data should be saved to the database for that repository.

**Validates: Requirements 9.2**

**Rationale:** This ensures transactional integrity. Either a complete graph is saved or nothing is saved—no partial/corrupted data.

---

### Job Management Properties

**Property 7: Job State Persistence**

*For any* ingestion job, the job status, progress, and results should be persisted in the database and retrievable via job ID at any time, including after server restarts.

**Validates: Requirements 3.2, 3.3, 3.4, 3.6**

**Rationale:** This ensures job state is reliably tracked and persisted. Users can query job status at any time and get accurate information.

---

**Property 8: Async Job Creation**

*For any* batch ingestion request, the system should return a job ID immediately without waiting for ingestion to complete.

**Validates: Requirements 3.1**

**Rationale:** This validates the async nature of the ingestion system. Job creation should be fast regardless of batch size.

---

### Query Properties

**Property 9: Multi-Repo Query Completeness**

*For any* set of repository identifiers where some exist in the database and some don't, querying for all of them should return data for existing repos and indicate which repos are missing.

**Validates: Requirements 4.1, 4.5**

**Rationale:** This ensures multi-repo queries handle partial matches correctly and provide clear feedback about missing data.

---

**Property 10: Query Pagination Consistency**

*For any* query result set, paginating through it with different limit/offset values should return all results exactly once without duplicates or omissions.

**Validates: Requirements 4.4**

**Rationale:** This validates that pagination logic is correct. Users should be able to reliably page through large result sets.

---

**Property 11: Filter Correctness**

*For any* query with filters (by maintainer, CVE, registry, or age), all returned results should match the filter criteria and no matching results should be omitted.

**Validates: Requirements 4.2, 7.3, 10.1, 10.2, 10.3, 10.4**

**Rationale:** This ensures filter logic is correct across all query types. Filters should be precise—returning all matches and only matches.

---

**Property 12: Index-Based Lookup Consistency**

*For any* repository graph stored in the database, querying by indexed properties (maintainer username, CVE ID, or package name) should return that repository if and only if the graph contains nodes matching those properties.

**Validates: Requirements 5.5, 10.1, 10.2, 10.3**

**Rationale:** This validates that index tables are correctly populated and synchronized with graph data. Index queries should be consistent with the actual graph contents.

---

### Backward Compatibility Properties

**Property 13: API Response Schema Compatibility**

*For any* repository, the response from `/api/graph` should conform to the existing schema regardless of whether data comes from the database or dynamic generation.

**Validates: Requirements 6.1, 6.4**

**Rationale:** This ensures backward compatibility. Existing API consumers should see no difference in response format.

---

**Property 14: Cache Behavior Correctness**

*For any* repository in the database, querying without `refresh=true` should return cached data (cache_hit=true), while querying with `refresh=true` should regenerate and update the database.

**Validates: Requirements 6.2, 6.5**

**Rationale:** This validates cache hit/miss logic and refresh behavior. The system should correctly distinguish between cached and fresh data.

---

**Property 15: Fallback to Dynamic Generation**

*For any* repository, if the database is unavailable, the `/api/graph` endpoint should still return valid graph data generated dynamically.

**Validates: Requirements 6.3, 9.3**

**Rationale:** This ensures graceful degradation. The system should never fail completely due to database issues—it can always fall back to dynamic generation.

---

### Data Quality Properties

**Property 16: Graph Validation Before Storage**

*For any* graph that violates the graph schema (missing required fields, invalid references, duplicate IDs), attempting to save it should fail with a validation error and no data should be stored.

**Validates: Requirements 9.5**

**Rationale:** This prevents invalid data from entering the database. Validation acts as a gatekeeper for data quality.

---

**Property 17: Metadata Completeness**

*For any* query result (single repo, multi-repo, or cross-repo), the response should include all required metadata fields (timestamps, confidence, provenance, node/edge counts).

**Validates: Requirements 4.3, 7.2, 10.5**

**Rationale:** This ensures query responses are complete and provide users with the context they need to assess data quality and freshness.

---

**Property 18: TTL Enforcement**

*For any* repository graph in the database, if the age exceeds the configured TTL and `refresh=false`, the system should either regenerate the graph or clearly indicate the data is stale.

**Validates: Requirements 7.5**

**Rationale:** This ensures the system respects TTL configuration and doesn't serve excessively stale data without warning.

---

### Deletion Properties

**Property 19: Cascade Deletion Completeness**

*For any* repository, deleting it from the database should remove the graph data and all associated index entries (maintainers, CVEs, registries).

**Validates: Requirements 8.5**

**Rationale:** This ensures deletion is complete and doesn't leave orphaned index entries. The database should remain consistent after deletions.


## Testing Strategy

### Dual Testing Approach

The testing strategy combines unit tests and property-based tests to achieve comprehensive coverage:

**Unit Tests:**
- Specific examples and edge cases
- Integration points between components
- Error conditions and boundary cases
- API endpoint behavior
- Database schema validation

**Property-Based Tests:**
- Universal properties across all inputs
- Comprehensive input coverage through randomization
- Minimum 100 iterations per property test
- Each property test references its design document property

Together, unit tests catch concrete bugs while property tests verify general correctness.

### Property-Based Testing Configuration

**Library:** Use `hypothesis` for Python property-based testing

**Configuration:**
```python
from hypothesis import given, settings, strategies as st

@settings(max_examples=100)
@given(
    repo_name=st.text(min_size=3, max_size=50),
    graph=st.builds(Graph, ...)
)
def test_property_1_graph_storage_round_trip(repo_name, graph):
    """
    Feature: multi-repo-persistent-graph, Property 1: Graph Storage Round-Trip
    
    For any valid repository graph, saving it to the database and then
    retrieving it should produce an equivalent graph.
    """
    # Test implementation
    pass
```

**Test Tagging:**
Each property test must include a docstring with:
- Feature name: `multi-repo-persistent-graph`
- Property number and title from design document
- Brief description of the property

### Test Organization

```
test/
├── test_persistence_properties.py      # Properties 1-3
├── test_ingestion_properties.py        # Properties 4-6
├── test_job_properties.py              # Properties 7-8
├── test_query_properties.py            # Properties 9-12
├── test_compatibility_properties.py    # Properties 13-15
├── test_quality_properties.py          # Properties 16-19
├── test_api_endpoints.py               # Unit tests for API
├── test_repositories.py                # Unit tests for repository classes
├── test_worker.py                      # Unit tests for ingestion worker
└── test_integration.py                 # End-to-end integration tests
```

### Unit Test Focus Areas

**Database Operations:**
- Schema creation and migration
- Connection handling and pooling
- Transaction rollback on errors
- Index creation and maintenance

**API Endpoints:**
- Request validation
- Response formatting
- Error handling
- Authentication (if added)

**Job Worker:**
- Job state transitions
- Progress tracking
- Error accumulation
- Graceful shutdown

**Edge Cases:**
- Empty repository lists
- Very large graphs (200+ nodes)
- Concurrent access to same repository
- Database file corruption
- Network timeouts during ingestion

### Integration Tests

**End-to-End Scenarios:**

1. **Full Ingestion Cycle:**
   - Submit batch job with 10 repos
   - Wait for completion
   - Verify all repos in database
   - Query via API
   - Verify response format

2. **Cache Hit/Miss:**
   - Query repo not in database (miss)
   - Query same repo again (hit)
   - Query with refresh=true (regenerate)
   - Verify database updated

3. **Cross-Repo Queries:**
   - Ingest repos with shared maintainers
   - Query by maintainer
   - Verify all repos returned
   - Verify index consistency

4. **Error Recovery:**
   - Submit job with invalid repos
   - Verify job completes
   - Verify valid repos processed
   - Verify errors reported

5. **Server Restart:**
   - Create running job
   - Simulate restart
   - Verify job marked interrupted
   - Verify database intact

### Performance Testing

**Benchmarks:**
- Single repo save: < 50ms
- Single repo retrieve: < 20ms
- Batch ingestion (100 repos): < 30 minutes
- Multi-repo query (50 repos): < 500ms
- Index query: < 100ms

**Load Testing:**
- 1000 repos in database
- Concurrent API requests (10 simultaneous)
- Database size monitoring
- Memory usage during ingestion

### Test Data Generation

**Strategies for Property Tests:**

```python
# Generate valid repository names
repo_names = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'),
    min_size=3,
    max_size=50
).filter(lambda s: '/' in s and len(s.split('/')) == 2)

# Generate valid graphs
def graph_strategy():
    return st.builds(
        Graph,
        nodes=st.lists(node_strategy(), min_size=1, max_size=50),
        edges=st.lists(edge_strategy(), max_size=100),
        metadata=st.fixed_dictionaries({
            'schema_version': st.just('1.0'),
            'data_sources': st.lists(st.sampled_from(['github_api', 'osv', 'heuristic']))
        })
    )

# Generate valid nodes
def node_strategy():
    return st.builds(
        Node,
        id=st.text(min_size=5, max_size=100),
        type=st.sampled_from(list(NodeType)),
        label=st.text(min_size=1, max_size=100),
        metadata=st.dictionaries(st.text(), st.text()),
        provenance=provenance_strategy()
    )
```

### Continuous Integration

**CI Pipeline:**
1. Run unit tests on every commit
2. Run property tests on every PR
3. Run integration tests before merge
4. Run performance benchmarks weekly
5. Generate coverage reports (target: 80%+)

**Test Environments:**
- Local development: SQLite in-memory
- CI: SQLite file-based
- Staging: PostgreSQL (future)
- Production: PostgreSQL (future)

