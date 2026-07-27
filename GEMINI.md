# Topos — Project Instructions & AI Context

This file serves as the definitive reference and instructional context for all AI agents, code-generators, and CLI sessions operating in the **Topos** workspace. It incorporates non-negotiable architectural mandates, development conventions, tooling commands, and code-style constraints.

---

## 1. Project Overview & Architecture

### Purpose
Topos is a system designed to ingest Greek public-sector and news sources for one electoral constituency (Α΄ Θεσσαλονίκης), extract citizen-affecting problems, geolocate them, deduplicate them, score them, and provide an interface for a policy office. Every extracted claim must be fully traceable to a byte-range span in its source document.

### Technologies
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic, asyncpg (raw SQL, **no ORM**), Alembic (hand-written migrations), Structlog.
- **Frontend:** TypeScript, React (v19), Vite, MapLibre-GL (for mapping), Oxlint (for linting).
- **Datastore:** PostgreSQL 16 (single database for relational, geospatial PostGIS, vector search pgvector, GIN index search, graph recursive CTEs, and SKIP LOCKED job queue) + MinIO/S3-compatible storage. No Redis, Kafka, Neo4j, Qdrant, or Celery.

### Key Directory Structure
- `src/topos/` — Backend code.
  - `domain/` — Deterministic, pure business logic, types, and value objects. Imports nothing from the rest of the app.
  - `service/` — Orchestration, transaction management, and interface ports (`typing.Protocol`).
  - `adapters/` — Side-effecting IO adapters (DB queries, S3 storage, HTTP clients, LLM, etc.).
  - `interfaces/` — FastAPI routers and Typer CLI worker entry points.
- `web/` — Frontend React SPA.
- `tests/` — Automated tests (unit tests, contract tests with real DB via `testcontainers`, and golden tests for Greek data).
- `docs/` — Architecture records, progress ledger, implementation plans, and reports.

---

## 2. Non-Negotiable Constraints & Mandates

| Rule ID | Mandate | Enforcement |
|---|---|---|
| **L1** | **No Natural Person Profiling** | No `person` table exists. Natural persons appear only as `authority` (office/role). |
| **L2** | **No Sensitive Feature Inference** | No extraction/inference of political opinion, religion, health, union, or ethnicity (absent from schemas). |
| **L5** | **Span Traceability** | `claim.span` (`int4range`) is `NOT NULL`. Claims without byte ranges are rejected at boundaries. |
| **L6** | **Approval Gate** | Recommendations require human sign-off before export (requires audit logging). |
| **L8** | **EU Data Residency** | EU hosting, EU S3 storage, EU LLM endpoints. **Do NOT run DeepSeek API runtime calls with citizen data** (non-EU hosted). |
| **SIZE** | **File Line Limits** | No Python source file may exceed **400 lines**. Enforced in CI via `make filesize`. |
| **LAYERS**| **Strict Package Layering** | `domain/` imports NOTHING from `topos.*`. Interface layer can't directly bypass service layer. Enforced by `import-linter`. |
| **IO** | **Functional Core, Imperative Shell** | Business logic (scoring, ER, state transitions, geocode ranking) must be pure functions with NO network/database IO, randoms, or clocks. IO belongs to adapters. |
| **DB** | **Raw SQL via asyncpg** | **No ORM allowed for app code.** PostGIS, ranges, and CTEs are written as hand-crafted SQL. Alembic migrations are hand-written SQL execution blocks. |

---

## 3. Tooling, Building & Running

A standard `Makefile` is located in the root of the workspace to orchestrate tasks.

### General Stack Management
- `make up` — Start the local development stack (PostgreSQL + MinIO + API + Worker).
- `make down` — Tear down the development stack.
- `make logs` — Follow logs of the API and Worker containers.
- `make db` — Enter `psql` shell in the development database.
- `make upgrade` — Apply hand-written migrations.
- `make revision m="name"` — Create a new hand-written migration revision.
- `make seed` — Load sources registry and Thessaloniki gazetteer.

### Checking Code & Formatting
Run `make check` to verify correctness before pushing. It runs:
- `make lint` — Formats and checks code with Ruff.
- `make fix` — Autofixes format and lint issues.
- `make types` — Strict static type analysis with MyPy.
- `make layers` — Validates architectural boundary layer purity with `import-linter`.
- `make filesize` — Confirms no source file exceeds 400 lines.
- `make migrations` — Confirms schema and migrations match.

### Testing & Validation
- `make test` — Runs all tests (unit, contract, and golden).
- `make test-unit` — Runs pure domain tests (extremely fast, zero mocks, zero network/containers).
- `make test-contract` — Runs adapter tests against a real PostgreSQL instance via `testcontainers`.
- `make test-golden` — Runs Greek data regressions (OCR, extraction, geocoding).
- `make cov` — Measures test coverage (domain is held to near 100%).

### Frontend (React App)
From the `/web` subdirectory:
- `npm run dev` — Start the local Vite development server.
- `npm run build` — Build and compile the app (`tsc` typecheck + Vite compile).
- `npm run lint` — Lint files using Oxlint.
- `npm run preview` — Locally preview the production build.

---

## 4. Coding & AI Agent Guidelines

- **Follow Ponytail Mode:** Prioritize simplicity, standard library features, and minimal code. Do not add speculative abstractions, extra dependencies, or unnecessary layers.
- **Pure Domain Tests:** When writing or editing `domain/` code, write pure, mock-free tests under `tests/unit/` using direct, literal inputs and expected outputs.
- **Raw SQL Performance:** When querying the database, implement clean, parameterized SQL queries within the relevant repository classes under `adapters/db/` inheriting from ports.
- **Idempotent Queue Pipeline:** Worker jobs must be idempotent and keyed on `(artifact_id, state)`.
- **Simplification Comments:** If applying intentional simplifications due to structural thresholds, tag them with a `# ponytail:` comment detailing the ceiling limits and eventual upgrade path.
- **File Length Enforcement:** Always design modules in smaller, cohesive files. If a file approaches 300-350 lines, plan to split or reorganize it before hitting the hard 400-line CI threshold.
