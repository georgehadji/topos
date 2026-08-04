# Topos (Α΄ Θεσσαλονίκης) 📍🏛️

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16%20%2B%20PostGIS-336791.svg)](https://www.postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed.svg)](https://www.docker.com)

Constituency problem intelligence for the **Α΄ Θεσσαλονίκης** electoral district.

Ingests Greek public-sector and news sources — Διαύγεια, ΚΗΜΔΗΣ, ΦΕΚ, ΔΕΔΔΗΕ outages,
the municipality and its seven suburban δήμοι, Περιφέρεια Κεντρικής Μακεδονίας, ΟΣΕΘ and
Μετρό Θεσσαλονίκης, ΦοΔΣΑ, ΟΛΘ, data.gov.gr, Meteoalarm and NOA seismicity, local news
RSS, X/social — extracts citizen-affecting problems with an LLM, geolocates and
deduplicates them, scores them, and serves the result as a map, a knowledge graph, and an
agent-callable API. Every derived fact keeps a byte-range span back to its source
document.

Run `topos-cli sources` for the live list with each plugin's configurable fields.

**Deeper reference:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (the contract) ·
[`AGENTS.md`](AGENTS.md) (working rules) · [`docs/adr/`](docs/adr) (decisions) ·
[`docs/PROGRESS.md`](docs/PROGRESS.md) (measured results).

---

## 🧭 Architecture

Clean Architecture (ports & adapters). Dependencies point inward only; `import-linter`
enforces it in CI.

```
interfaces/   FastAPI routers, Typer CLI, MCP      → imports service, domain
service/      Orchestration, ports (Protocol)      → imports domain only
adapters/     Postgres, S3, LLM, HTTP, geocode     → imports domain
domain/       Pure types, scoring, ER, FSM         → imports NOTHING from topos.*
```

- **Pure functional core.** `domain/` has no IO, no `async`, no clock, no randomness.
  Tested with literal inputs and outputs, never mocks.
- **SKIP LOCKED worker.** Workers claim one pipeline row atomically, advance one state,
  commit. Every step idempotent on `(artifact_id, state)`, so concurrent workers are safe.
- **Pipeline:** `fetched → textified → chunked → extracted → geocoded → resolved → indexed → done`.
- **No ORM.** Raw parameterized SQL via `asyncpg`; migrations are hand-written.
- **Greek is the dominant risk.** `greek_cfg` folds accents *and* inflection via the
  built-in Greek snowball stemmer: `δρόμου`/`δρόμος` → `δρομ`, `Θεσσαλονίκης`/`Θεσσαλονίκη`
  → `θεσσαλονικ`. A query for `ύδρευση` matches an indexed `ύδρευσης`. Migration 006 put
  this in place; before it, the hunspell dictionary silently did accent folding only.
- **PITR verified.** `pg_basebackup -X fetch` to S3; restore drill completed in **55s**.

---

## 🛠️ Stack

**Backend** — Python 3.12 (`mypy --strict`) · FastAPI · PostgreSQL 16 (PostGIS, pgvector,
pg_trgm, unaccent) via `asyncpg` · Alembic (hand-written) · MinIO/S3 via `aioboto3` ·
Strawberry GraphQL · OpenTelemetry + Prometheus.

**Frontend** (`web/`) — React 19 · Vite 8 · TypeScript 6 · MapLibre GL 6 · oxlint.
Force-directed graph is plain SVG, no graph library.

PostgreSQL is the **only** datastore. No Redis, Kafka, Neo4j, Qdrant or Celery.

---

## 🚀 Quickstart

Needs **Docker Desktop**, **Node 18+**, **Python 3.12** with [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                              # 1. install Python deps
cp .env.example .env                 # 2. config — set TOPOS_LLM_API_KEY for real extraction
docker compose up -d --build         # 3. postgres + minio + api + worker
uv run alembic upgrade head          # 4. apply migrations
uv run topos-cli seed                # 5. load the source registry
uv run topos-cli health --json       # 6. verify — exits 1 if the database is unreachable
```

`make up` / `make upgrade` / `make seed` are shorthands for steps 3–5. The `uv` commands
above are the portable form — `make` is not installed everywhere (notably Windows).

Then the frontend:

```bash
cd web && npm install && npm run dev
```

> **Port 5432 already taken?** The compose file publishes Postgres on `5432:5432`. If
> another instance owns that port, map it elsewhere with a compose override and set
> `TOPOS_DB_DSN` to match.

Without an LLM key the worker falls back to a built-in mock client, so the pipeline still
runs end to end offline.

---

## 🌐 Endpoints

| URL | What |
|---|---|
| [`localhost:5173`](http://localhost:5173) | React dashboard — ranked mentions, map filters, review queue, knowledge graph |
| [`localhost:8000/docs`](http://localhost:8000/docs) | Swagger UI |
| `localhost:8000/graphql` | GraphQL (Strawberry) |
| `localhost:8000/mcp` | **MCP over JSON-RPC 2.0** — see below |
| `localhost:8000/healthz` | Liveness |
| [`localhost:9001`](http://localhost:9001) | MinIO console — `topos` / `devonlydevonly` |

REST: `/api/search`, `/api/graph/problems`, `/api/recommendations`, `/api/review/tasks`,
`/artifacts`, `/api/webhooks`.

---

## 📋 CLI

`topos-cli` is the headless entrypoint. Every command is non-interactive, needs no TTY,
and takes `--json` to emit one parseable object on stdout. Exit status is 0 on success and
1 on failure, so `&&` chaining is safe.

```bash
# Discovery — no database, no network needed
uv run topos-cli --help
uv run topos-cli sources --json          # every registered source + its config fields

uv run topos-cli health --json           # config + DB reachability; exits 1 if down
uv run topos-cli pipeline --json         # artifact count per pipeline state
uv run topos-cli seed                    # load the source registry (idempotent)

# Ingest. --dry-run fetches and counts without writing.
uv run topos-cli backfill --source diavgeia --limit 100 --dry-run --json
uv run topos-cli backfill --source news --set max_per_feed=20   # override any config field

uv run topos-cli cost --month current --json     # LLM spend from extraction_run
uv run topos-cli export all --output-dir ./exports --json

# Pipeline worker. --drain processes everything pending and exits 0;
# without it the loop runs until SIGINT/SIGTERM.
uv run topos-cli worker --drain
uv run topos-cli worker
uv run topos-cli serve --port 8000       # FastAPI HTTP API
```

**Agents** can drive Topos over MCP at `POST /mcp`, which exposes `search_problems`,
`get_problem_detail`, `get_pipeline_status`, `list_sources` and `get_scoring_breakdown`.

---

## 🧪 Quality gate

```bash
make check      # what CI runs. Merge is blocked on this.
```

| Step | Gate |
|---|---|
| `make lint` | `ruff format --check` + `ruff check` |
| `make types` | `mypy --strict`, zero errors |
| `make layers` | `import-linter` — 6 architecture contracts |
| `make filesize` | No `.py` over 400 lines |
| `make test` | Full suite |
| `make migrations` | `alembic upgrade head`, then assert `alembic current` reports `(head)` |

`make migrations` deliberately does **not** use `alembic check`: that is autogenerate-based
and needs a `MetaData` object, which an ORM-less codebase does not have.

```bash
uv run pytest                              # full suite: 132 unit + 9 contract
uv run pytest tests/unit                   # pure, fast, no containers
uv run pytest tests/contract -m contract   # adapters against a real PostgreSQL
```

Contract tests need Postgres and MinIO up, and MinIO needs the `topos-artifacts` bucket.
They read `TOPOS_TEST_PG_DSN` if set, otherwise they fall back to `TOPOS_DB_DSN` from
`.env` — the same DSN the app connects with, so the two cannot drift apart.

> Contract tests delete rows for the `test` / `diavgeia` / `fek` / `deddhe` sources, so a
> full `pytest` run empties dev data. Re-populate with `topos-cli backfill` +
> `topos-cli worker --drain`.

> `tests/golden/` is currently empty. AGENTS.md requires golden fixtures for Greek
> behaviour — that is the largest open test gap.

---

## 🛡️ Backups & recovery

Single node, streamed to S3.

```bash
./infra/backup.sh          # base backup
./infra/restore-drill.sh   # timed PITR drill — run quarterly, record in docs/PROGRESS.md
```

---

## ⚖️ License

**Proprietary — commercial project. All rights reserved.**

Not open source. No redistribution, and no use outside the project without written
permission. No `LICENSE` file is committed yet; add the commercial terms before any
external distribution.
