# M0 — Foundations & Environment: Tasks

*Mirrors Linear milestone "M0 — Foundations & Environment" (issues DEE-5 through DEE-9). Each task notes its Linear ID and its blocking relationships. Work top to bottom; the one place order is flexible is noted below.*

## Sequence

```
DEE-5  →  DEE-6  →  ┌─ DEE-7 ─┐
                    └─ DEE-8 ─┘  →  DEE-9
```

DEE-7 and DEE-8 both depend only on DEE-6, not on each other — they can be done in either order (recommended: DEE-7 first, so DEE-8 connects to real tables). Everything else is strictly sequential.

---

## DEE-5 — Set up local PostgreSQL via Docker

*Blocked by: nothing (start here)*

Get a Postgres instance running locally in a container, with a `docker-compose.yml` checked into the repo so the environment is reproducible. Confirm connectivity from both a database client and from Python.

**Done when:** `docker compose up` gives a Postgres instance you can connect to, and the compose file is committed.

Notes:
- Pin a specific Postgres major version in the compose file rather than `latest`.
- Set database name, user, and password via environment / an `.env` pattern, not hardcoded — establishes the config habit early.
- Confirm connection two ways: a GUI/CLI client, and a one-line Python connection, so you know both paths work.

---

## DEE-6 — Choose and wire up a migration tool

*Blocked by: DEE-5*

Adopt Alembic, initialize it against the Postgres instance, and confirm the migrate-up / migrate-down cycle works with a trivial throwaway migration.

**Done when:** you can create, apply, and roll back an empty migration cleanly.

Notes:
- The throwaway migration can create and then drop a dummy table — the point is proving up *and* down both work before any real schema exists.
- Get the Alembic → database URL wiring reading from the same config source as DEE-5.

---

## DEE-7 — Write the first migration: core identity tables

*Blocked by: DEE-6*

Create `projects`, `repositories`, `packages`, `versions`, `identifiers` as an Alembic migration — just these five, not the full model. Include primary keys, the obvious foreign-key relationships, and appropriate Postgres types (`timestamptz` for timestamps, `jsonb` where source-specific payloads are expected later).

**Done when:** the migration applies cleanly and the five tables exist with sane columns and relationships.

Notes:
- Keep the repository↔package link optional/nullable — resolving it is M1's job, not M0's.
- Include created/updated `timestamptz` columns on every table.
- Verify the down-migration cleanly drops everything (respecting FK order).

---

## DEE-8 — Establish Python DB connection handling

*Blocked by: DEE-6 (can run in parallel with DEE-7)*

Set up the connection layer later code will use — connection pooling and a session/engine pattern (SQLAlchemy pairs naturally with Alembic).

**Done when:** a small script can open a connection, run a query, and close cleanly.

Notes:
- Reuse the same database-URL config source as DEE-5/DEE-6 — one place, not three.
- This is the layer M2's collectors and beyond will import, so keep it clean and importable.

---

## DEE-9 — Manual insert-and-query smoke test

*Blocked by: DEE-7 and DEE-8 (M0 exit criterion)*

Hand-insert one component (`requests` and its `psf/requests` repo) across the identity tables and query it back. This is the M0 exit criterion — proof the whole foundation works end to end before any real code builds on it.

**Done when:** one component has been inserted and retrieved by hand, with the relationships resolving correctly.

Notes:
- Insert across all the relevant tables: the project, the repository, the package, at least one version, and the identifiers.
- Query it back by joining from an identifier through to the version, confirming the relationships resolve as intended.
- This can be a throwaway script or a documented sequence of SQL — its job is verification, not reusable code.
