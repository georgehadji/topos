# Topos — Agent Context

Constituency problem intelligence for Α΄ Θεσσαλονίκης. Ingests Greek public-sector & news sources, extracts citizen-affecting problems, geolocates/deduplicates/scores them, with full byte-range source traceability.

Deeper reference: `ARCHITECTURE.md` (the contract), `GEMINI.md` (full AI context), `docs/IMPLEMENTATION_PLAN.md`.

## Project

- **Backend:** Python 3.12, FastAPI, asyncpg (raw SQL, **no ORM**), Pydantic, Alembic (hand-written migrations), Structlog.
- **Frontend:** TypeScript, React 19, Vite, MapLibre-GL, oxlint.
- **Database:** PostgreSQL 16 (postgis, pgvector, pg_trgm, unaccent) — the ONLY datastore. No Redis/Kafka/Neo4j/Qdrant/Celery.
- **Entrypoints:** `src/topos/interfaces/http/` (FastAPI), `src/topos/interfaces/cli/` (Typer worker CLI).

## Commands

All from repo root. `PY` = `uv run`.

| Command | What it does |
|---|---|
| `make check` | Full CI gate: ruff + mypy + import-linter + filesize + pytest + alembic check |
| `make lint` | `ruff format --check` + `ruff check` |
| `make fix` | `ruff format` + `ruff check --fix` (autofix) |
| `make types` | `mypy --strict` |
| `make layers` | `lint-imports --config .importlinter` |
| `make filesize` | No .py over 400 lines |
| `make test` | All tests: unit + contract + golden |
| `make test-unit` | Domain-only, pure, no containers (`tests/unit`) |
| `make test-contract` | Adapters against real PG via testcontainers (`tests/contract`) |
| `make test-golden` | Greek fixture regressions (`tests/golden`) |
| `make cov` | Coverage with HTML report |
| `make up` / `make down` | Docker Compose dev stack |
| `make upgrade` | `alembic upgrade head` |
| `make revision m="..."` | New hand-written migration |
| `make seed` | Load sources + Thessaloniki gazetteer |

Frontend (from `web/`): `npm run dev` · `npm run build` · `npm run lint` · `npm run preview`

## Headless operation (no human, no TTY)

`make` is a convenience wrapper and is not present on every dev machine. **`topos-cli`
is the supported headless entrypoint** and needs nothing but `uv sync`.

Contract, relied on by callers:

- `--json` on every non-streaming command prints **exactly one JSON object to stdout** and
  nothing else. Logs and diagnostics go to stderr.
- Exit **0** on success, **1** on failure. Failures print `{"ok": false, "error": "..."}` to
  **stderr**, leaving stdout empty.
- stdout is pinned to UTF-8, so Greek survives redirection on Windows.
- `--help`, `version` and `sources` need no database and no network — use them to discover
  capabilities before touching anything.

```bash
uv sync                                        # only setup step required
uv run topos-cli --help
uv run topos-cli sources --json                # every source kind + its config fields
uv run topos-cli health --json                 # exits 1 if the database is unreachable
uv run topos-cli seed                          # load the source registry (idempotent)
uv run topos-cli backfill --source diavgeia --limit 100 --dry-run --json
uv run topos-cli backfill --source news --set max_per_feed=20    # override any config field
uv run topos-cli pipeline --json               # artifact count per pipeline state
uv run topos-cli cost --month current --json
uv run topos-cli export all --output-dir ./exports --json
uv run topos-cli worker --drain                # bounded: drain the queue, then exit 0
uv run topos-cli worker                        # long-running: SKIP LOCKED claim loop
uv run topos-cli serve --port 8000             # long-running: FastAPI
```

Prefer `worker --drain` in any non-interactive context. Plain `worker` never returns, and
killing it through `uv` can orphan the child process.

Discover-then-act, rather than guessing flags: `sources --json` returns each plugin's
config model, and every field in it is settable with `--set key=value`. Unknown source or
unknown field fails with exit 1 and names the valid options.

`TOPOS_DB_DSN` (see `.env.example`) is the one setting most commands need. Without an LLM
key the worker falls back to a mock client, so the pipeline still runs end to end offline.

**MCP:** with `serve` running, `POST /mcp` speaks JSON-RPC 2.0 and exposes
`search_problems`, `get_problem_detail`, `get_pipeline_status`, `list_sources`,
`get_scoring_breakdown`.

## Architecture

```
interfaces/   FastAPI routers, Typer CLI          → imports service, domain
service/      Orchestration, ports (Protocol)      → imports domain only; adapters via Protocol
adapters/     Postgres, S3, LLM, HTTP, geocode     → imports domain
domain/       Pure types, scoring, ER, FSM          → imports NOTHING from topos.*
```

- **`domain/`** — Deterministic pure functions. No IO, no `async`, no clock/random/network. Tested with literal inputs/outputs, never mocks.
- **`service/`** — Orchestration + `typing.Protocol` ports (not ABCs). `service/ports.py` defines `Clock`, `BlobStore`, `LlmClient`, `PipelineRepo`, etc.
- **`adapters/`** — Side-effecting IO: `db/` (asyncpg repos, one method per query, return domain types), `blob/` (MinIO/S3), `llm/` (OpenRouter), `sources/`, `geocode/`, `ocr/`, `stt/`.
- **`interfaces/`** — `http/` (FastAPI routers) and `cli/` (Typer workers).

**Pipeline:** `fetched → textified → chunked → extracted → geocoded → resolved → indexed → done`. Workers claim via `SKIP LOCKED`, advance one state, commit. Every step idempotent on `(artifact_id, state)`.

## Conventions

- **No ORM.** Raw parameterized SQL via asyncpg. Queries in `adapters/db/*_repo.py`. Migrations are hand-written `op.execute("...")` blocks — no autogenerate.
- **File limit: 400 lines** (enforced in CI). Split before hitting ~350.
- **Domain purity.** Logic that decides goes in `domain/` as a pure function. Adapters stay thin — no business logic.
- **Immutability.** `artifact` and `claim` are immutable (new rows, never UPDATE/DELETE content). `problem_event` is append-only.
- **Ports are `typing.Protocol`**, not ABCs. Adapters satisfy them structurally.
- **`# ponytail:` comments** mark intentional simplifications with ceiling limits and upgrade paths.
- **Greek is the dominant technical risk.** Never assume English-grade accuracy. Golden fixtures required for Greek behaviour. Tag uncertain Greek claims with `[UNVERIFIED]`.
- **Prompts are code.** Versioned files, reviewed, with golden tests. Prompt version stored on every derived fact.
- **Every ingested document is untrusted input.** Spans must resolve or the claim is rejected.
- **`make check` must be green** before any PR. This is the definition of done.
- **No new dependency, no schema change without an ADR** in `docs/`.

## Notes

<!-- add quick-notes here as the project evolves -->
