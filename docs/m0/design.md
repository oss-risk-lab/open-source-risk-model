# M0 — Foundations & Environment: Design

*Scope: this document covers the M0 milestone only — standing up PostgreSQL, the migration workflow, and the core identity tables. It deliberately does not attempt to design the full ~25-table model, the enrichment pipeline, or the OKF format, all of which are addressed in later milestones and some of which remain open questions.*

## Purpose of M0

M0 establishes the persistence foundation everything else builds on: a running PostgreSQL database, a version-controlled schema-migration workflow, and the minimal set of identity tables needed to represent "a software component and the things it is known by." The exit criterion is deliberately concrete and small — insert one real component by hand and query it back — because the point of M0 is a trustworthy foundation, not features.

## Why PostgreSQL (not SQLite)

The current prototype runs on SQLite. The target system needs capabilities SQLite does not provide well:

- **Recursive queries** over the dependency graph (recursive CTEs) — needed once dependency traversal arrives in M3.
- **JSONB** columns for storing source-specific payloads (raw API responses) alongside normalized fields, with the ability to query into them.
- **Concurrent access** from an asynchronous API and background jobs (M7), which SQLite handles poorly.
- **Richer typing** — notably timezone-aware timestamps (`timestamptz`), which matter because provenance ("when was this observed") is central to the whole system.

M0 does not use most of these yet, but choosing Postgres now avoids a painful migration later.

## Migration-first discipline

All schema changes go through version-controlled migrations (Alembic) from the very first table. No schema is created by hand against the live database. This is non-negotiable because:

- The schema will change many times as later milestones add tables; an auditable, reversible history is essential.
- It keeps every environment (local, and any future CI/shared instance) reproducible from the same migration chain.
- It forces schema changes to be reviewed as code.

## The five core identity tables

M0 introduces only the tables needed to answer "what is this component and what is it known as." Later milestones add observations, evidence, dependencies, findings, and the rest.

- **`projects`** — the top of the hierarchy: a logical software project that may span multiple repositories and packages.
- **`repositories`** — a source repository (e.g. a GitHub repo like `psf/requests`), linked to a project.
- **`packages`** — a distributable package in some ecosystem (e.g. the PyPI package `requests`), linked to a project and (where known) to a repository.
- **`versions`** — a specific released version of a package (e.g. `requests 2.31.0`).
- **`identifiers`** — the various external identifiers a component is known by (GitHub URL, PyPI name, Package URL, etc.), each pointing back to the entity it identifies. This is the table that makes deduplication and multi-ecosystem resolution possible later.

### Design notes on these tables

- **Timestamps are `timestamptz`.** Every row records when it was created/updated. Provenance discipline starts here.
- **A `jsonb` "raw" column** is included where it's natural to keep the source payload that a row was derived from, even though M0 doesn't populate it heavily yet — establishing the pattern early is cheaper than retrofitting.
- **Foreign keys are explicit.** repositories → projects, packages → projects (and optionally → repositories), versions → packages, identifiers → the thing they identify. The repository↔package relationship is intentionally *optional* at this stage, because resolving which repo corresponds to which package is itself a non-trivial problem handled in M1.
- **No observation/evidence tables yet.** It's tempting to add them now; resist it. M0 is identity only.

## What M0 explicitly excludes

- The observation / evidence / provenance tables (M2).
- Dependency tables and graph structure (M3).
- The hierarchy applicability-scope and inheritance model (M4).
- Findings and rules (M5).
- Any API, serialization, or MCP surface (M6–M8).
- Fuzzy or confidence-based identity resolution (deferred within M1).

## Exit criterion

M0 is done when: Postgres runs locally via a committed `docker-compose.yml`; Alembic applies a migration creating the five identity tables; a Python connection layer can open, query, and close cleanly; and one component (`requests` / `psf/requests`) has been inserted by hand across the tables and queried back with its relationships resolving correctly.
