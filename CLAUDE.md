# Deep Signal — Open Source Project Risk Pipeline

This file is persistent context for Claude Code. Read it at the start of every
session. It describes what this project is, how it's built, and the working
agreements to follow. It is intentionally high-level and stable — specific task
state lives in Linear, not here.

## What this project is

An open-source software risk intelligence and supply-chain analysis platform.
Given a software component identifier (a GitHub repo, PyPI package, Maven
coordinate, npm package, or Package URL), the system produces a normalized,
evidence-backed profile of that component, its dependency graph, and its
associated risks — and can serve that knowledge to an LLM or another system.

The objective is NOT to produce a single opaque "risk score." It is to build an
evidence-first knowledge base where every conclusion is traceable to the
evidence that produced it. A summary score, if it ever exists, is an optional,
explainable layer on top — never the foundation.

## Core principles (these override convenience)

1. **Evidence before conclusions. Provenance is the point, not metadata.**
   Every stored fact ("observation") records where it came from, when it was
   retrieved, and how confident we are. Every finding is traceable back to its
   supporting observations and the version of the rule that produced it. This
   discipline starts with the very first table and the very first collector —
   it cannot be bolted on later.

2. **Build one narrow path all the way through before widening it.**
   Prefer a single component flowing end-to-end (resolve → enrich → store →
   assess) over building every layer partially. Widen to more ecosystems, more
   depth, and more polish only on top of a working skeleton. PyPI is the first
   and only ecosystem until the full path works.

3. **Respect the milestone boundary.** Work is decomposed into milestones (M0,
   M1, ...) tracked in Linear. Do not build ahead of the current milestone. If
   a task seems to require something from a later milestone, stop and flag it
   rather than pulling that work forward.

4. **Dependencies are a bounded, typed, partially-resolved graph — not a flat
   set.** They recurse (so they need hard budgets: max depth, max component
   count), they carry types (runtime / build / test / optional), and they exist
   in multiple states (declared constraint vs. resolved concrete version).
   These distinctions must be preserved, never collapsed into one edge.

## Stack and conventions

- **Language:** Python
- **Database:** PostgreSQL (not SQLite). Chosen for recursive CTEs, JSONB,
  concurrent access, and timezone-aware timestamps — all of which later
  milestones rely on.
- **Migrations:** Alembic. ALL schema changes go through version-controlled
  migrations from the first table onward. Never create or alter schema by hand
  against the live database.
- **DB access:** SQLAlchemy engine/session pattern with connection pooling.
- **Timestamps:** always `timestamptz`. **Source payloads:** `jsonb`.
- **Local environment:** PostgreSQL runs locally via Docker (`docker-compose.yml`
  committed to the repo). Database name/user/password come from environment /
  `.env`, never hardcoded.

## Spec-driven workflow (requirements → design → tasks)

Each milestone is planned before it is built, using a structured
requirements → design → tasks document convention (this originated as a
Kiro-style convention; we no longer use Kiro, just this structure with Claude
Code). For a milestone `MN`:

- `docs/MN/design.md` — what we're building this milestone and why; the design
  decisions, scoped to this milestone only.
- `docs/MN/tasks.md` — the concrete tasks, mirroring the Linear issues for the
  milestone, including their dependency/ordering.

When starting a milestone: read its issues from Linear, write `design.md` and
`tasks.md`, and STOP for human review before implementing. The review checkpoint
is deliberate and must not be skipped — it is where scope creep gets caught and
where the human learns the backend.

## Linear integration

- Issues and milestones live in Linear (team: Deep Signal Security; project:
  Open Source Project Risk Pipeline). Read issue details from Linear rather than
  asking for them to be pasted in.
- Each Linear issue carries a `branchName`. Use it when starting work on an
  issue so commits and PRs link back automatically.
- Update issue status to reflect reality (In Progress when work starts, Done
  when the "done when" criterion in the issue is met) — but never mark an issue
  Done before its acceptance criterion is actually satisfied.

## Guardrails

- Do not run destructive database operations (dropping data, etc.) outside of
  reversible Alembic migrations.
- Do not add dependencies or introduce frameworks beyond what a task calls for
  without flagging it first.
- When something is ambiguous or underspecified, ask rather than guessing —
  especially anything touching the data model, which is expensive to change
  later.

## Known open questions (do not silently resolve these)

- **OKF (Open Knowledge Format):** it is genuinely unresolved whether OKF is a
  pre-existing format to adopt or one being defined jointly. Do not harden an
  assumption about it. Serialization work (M6) is blocked until this is settled.
- **Default version selection** when only a package name (no version) is given.
- **Dependency closure strategy** (recursive queries vs. closure table vs.
  materialized transitive edges) and the default recursion/resource budgets.
