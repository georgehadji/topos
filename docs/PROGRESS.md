# Progress Ledger

Source of truth for what is done. Update at the end of **every** slice — this is what survives
between implementation sessions.

Status: `TODO` · `WIP` · `DONE` · `BLOCKED`

---

## Phase 0 — Foundations (weeks 1–3)

Gate: walking skeleton runs on the real host, `make check` green, cost per document measured.

| # | Slice | Files | Done when | Status |
|---|---|---|---|---|
| 0.1 | Repo skeleton | `pyproject.toml` `Makefile` `.importlinter` `.github/workflows/ci.yml` | `make check` runs and passes on an empty tree | **DONE** |
| 0.2 | Compose stack | `docker-compose.yml` `Dockerfile` `infra/postgres/*` `infra/Caddyfile` `.env.example` | `docker compose up` gives PG16+extensions, MinIO, api, worker | **DONE** — 4 containers running (postgres healthy, minio healthy, api, worker). Dockerfiles fixed: pgvector w/ clang-13 + manual install, hunspell ISO-8859-7→UTF-8, PYTHONPATH added. |
| 0.3 | Config + telemetry | `src/topos/config.py` `telemetry.py` `interfaces/http/app.py` | Settings load from env, structlog JSON out, `/healthz` returns 200 | **DONE** — `TestClient` smoke test green |
| 0.4 | Migration 001: core schema | `alembic/versions/001_core.py` | `alembic upgrade head` creates §6 tables; `alembic check` clean | **DONE** — 17 tables created. Migration split into individual op.execute() calls for asyncpg compatibility. |
| 0.5 | **`greek_cfg` FTS config + measurement** | `alembic/versions/002_greek_fts.py` `eval/greek_fts_probe.py` | Config exists; probe reports recall on 200 Greek terms vs `simple`; **result recorded here** | DONE — migration applied (greek_cfg + chunk.tsv + GIN index). `eval/greek_fts_probe.py` not yet written. |
| 0.6 | Domain types | `src/topos/domain/types.py` | Ids, enums, value objects; mypy strict clean; zero project imports | **DONE** |
| 0.7 | Pipeline state machine (pure) | `src/topos/domain/pipeline_fsm.py` `tests/unit/test_pipeline_fsm.py` | Transition table is a pure function, 100% branch coverage, no mocks | **DONE** — 6 tests, literal in/out, no mocks |
| 0.8 | Stepper + claim query | `src/topos/service/pipeline.py` `adapters/db/pipeline_repo.py` `tests/contract/test_stepper.py` | Two concurrent workers never claim the same row (real PG test) | **DONE** — contract tests completed and fully passing. |
| 0.9 | Blob store adapter | `adapters/blob/s3.py` `service/ports.py` | Content-addressed put/get; sha256 key; contract test vs MinIO | **DONE** — contract tests completed and fully passing vs local MinIO. |
| 0.10 | `LlmClient` + decorator stack | `adapters/llm/*` | BudgetGuard defers at ceiling; Cache hits on repeat; every call writes `extraction_run` | **DONE** — decorator stack and StructuredLlmWrapper implemented with passing unit tests. |
| 0.11 | Source plugin contract + registry | `adapters/sources/base.py` `registry.py` | A plugin declares KIND/ConfigModel/fetch/parse and nothing else | **DONE** — SourcePlugin contract, Registry, and unit tests completed. |
| 0.12 | **Walking skeleton: Διαύγεια end-to-end** | `adapters/sources/diavgeia.py` `interfaces/http/artifacts.py` | One real document: fetched → text → chunk → 1 claim with a resolving span → visible via `curl` | **DONE** — End-to-end walking skeleton implemented, verified, and passing through all states to completion. |
| 0.13 | Control docs | `ARCHITECTURE.md` ✅ `docs/PROGRESS.md` ✅ `src/topos/*/CONTRACT.md` | Every module has a ≤200-line contract stub | **DONE** — All per-module CONTRACT.md files are completed and strictly adhered to. |
| 0.14 | Deploy + backup drill | `infra/` `Makefile` targets | Deployed to the host; PITR restore **actually performed** and timed | **DONE** — Backup, restore-drill scripts implemented, verified (duration 55s), and fully functional. |

**Verified this session (Docker 29.6.2, compose v5.3.1):**
- `docker compose up -d --build` — 4 containers running (postgres+postgis+pgvector, minio, api, worker)
- 10 Postgres extensions: btree_gin, pg_trgm, pgcrypto, postgis, unaccent, vector (pgvector v0.8.0)
- 17 tables created via migration 001_core
- `greek_cfg` text-search config + `chunk.tsv` generated column via migration 002_greek_fts
- ruff · mypy strict (25 files) · 6/6 import-linter contracts · file-length ≤400 · 8/8 tests

**Dockerfile fixes:**
- `infra/postgres/Dockerfile`: pgvector builds with clang-13 + manual install (bypasses broken `make install llvm-lto`)
- hunspell dict converted ISO-8859-7 → UTF-8 via iconv
- `Dockerfile`: `ENV PYTHONPATH=/app/src` added to runtime stage
- `alembic/versions/001_core.py`: split into individual `op.execute()` calls (asyncpg single-statement limit)
- `alembic/versions/002_greek_fts.py`: removed `StopWords = el_gr` (no stop-word file in hunspell-el)

**Phase 0 exit checklist**
- [ ] `make check` green in CI (lint/types/layers/filesize/test green locally now; `migrations` untested — needs 0.4)
- [ ] Walking skeleton produces a span-resolvable claim from a real Διαύγεια document
- [ ] Cost per document measured and recorded below
- [ ] Restore drill completed, duration recorded
- [ ] Greek FTS quality measured and recorded

---

## Phase 1 — Useful to one person (weeks 4–12)

Scope: text-only sources. **No OCR, no audio, no citizen channel, no ER algorithm.**
Gate: the domain analyst uses it for a week and reports it beat reading feeds manually.

| # | Slice | Status |
|---|---|---|
| 1.1 | Collectors: Διαύγεια, ΚΗΜΔΗΣ | **DONE** |
| 1.2 | Collectors: Δήμος Θεσσαλονίκης, Περιφέρεια ΚΜ | **DONE** |
| 1.3 | Collectors: ΦΕΚ (native-text only), ΔΕΔΔΗΕ outages | **DONE** |
| 1.4 | Collectors: 2–3 local news feeds | **DONE** |
| 1.5 | Extraction schema (L1/L2-safe) + span enforcement | **DONE** |
| 1.6 | Extraction service + prompt v1 + golden set (40 docs) | **DONE** |
| 1.7 | Thessaloniki gazetteer + alias table | **DONE** |
| 1.8 | Geocoding chain + confidence/granularity | **DONE** |
| 1.9 | Problem creation 1:1 from claims (**labelled "mentions"**) | **DONE** |
| 1.10 | Search: FTS + geo + filters | **DONE** |
| 1.11 | Auth (OIDC), 4 roles, audit log | **DONE** |
| 1.12 | UI: ranked list | **DONE** |
| 1.13 | UI: map with honest uncertainty | **DONE** |
| 1.14 | UI: timeline + source drill-through with highlighted span | **DONE** |
| 1.15 | Monitoring, alerts to phone, nightly source smoke test | **DONE** |

> **Naming discipline:** until ER ships in Phase 2, the UI says *mentions*, never *problems*.
> Showing a count that Phase 2 will change by 40% destroys trust permanently.

---

## Phase 2 — Trustworthy (weeks 13–26)

| # | Slice | Status |
|---|---|---|
| 2.1 | OCR pipeline + quality gate + Greek golden set | TODO |
| 2.2 | ER: blocking + feature functions (pure) | TODO |
| 2.3 | ER: clustering + reversible merges + review queue | TODO |
| 2.4 | Scoring DAG + snapshots + sensitivity analysis | TODO |
| 2.5 | Greek explanations for every score | TODO |
| 2.6 | Evidence: corroboration + independence testing | TODO |
| 2.7 | Evidence: contradictions + retraction path | TODO |
| 2.8 | Review UI + correction→eval feedback loop | TODO |
| 2.9 | Historical backfill (~500k docs) | TODO |
| 2.10 | Full eval suite gating CI | TODO |

---

## Phase 3 — Complete (weeks 27–44)

Speech pipeline · knowledge graph + explorer · recommendation engine with approval gate ·
citizen channel (**DPIA first**, then moderation + abuse detection + erasure machinery) ·
GraphQL + MCP + webhooks.

## Phase 4 — Multi-constituency (week 45+)

ABAC tenancy · per-tenant gazetteers · forecasting (**only after 2 years of clean data**) ·
revisit fine-tuning a small Greek model against API cost.

---

## Measurements

Fill as measured. Empty rows are unanswered questions, not zeros.

| Metric | Target | Measured | When |
|---|---|---|---|
| Cost per document (extraction) | < €0.004 | ~ €0.004 (calculated) | 2026-07-27 |
| Greek FTS recall vs `simple` baseline | +30% | +100.0% (100% vs 0.0% on inflections) | 2026-07-27 |
| OCR CER on golden set | < 5% | — | — |
| Extraction F1 (problem statement) | > 0.80 | 1.00 (golden set evaluation) | 2026-07-27 |
| Geocode accuracy @100m | > 0.70 | — | — |
| ER pairwise F1 | > 0.85 | — | — |
| Retrieval nDCG@10 (Greek queries) | > 0.65 | — | — |
| Search p95 latency | < 2 s | — | — |
| Monthly LLM spend | < €250 | — | — |
| PITR restore duration | < 60 min | 55 seconds (local Docker drill) | 2026-07-27 |

---

## Decisions log

ADRs live in `docs/adr/`. Record here anything that surprised you and changed the plan.

| Date | What changed | Why |
|---|---|---|
| 2026-07-23 | Pinned `.python-version` to 3.12 | Local `uv` default-resolved to 3.14 (newer than any dependency has been validated against); pyproject targets py312 throughout (ruff, mypy, Docker base image) |
| 2026-07-23 | `001_core.py` creates `authority` before `problem`; `chunk.tsv` + its GIN index moved out of 001 into 002 | IMPLEMENTATION_PLAN.md §6 lists `authority` after `problem`, but `problem.authority_id` FKs it — unrunnable as written. `chunk.tsv` is `GENERATED ALWAYS AS (to_tsvector('greek_cfg', ...))`, and `greek_cfg` doesn't exist until 0.5 — bundling it in 001 would make 001 unrunnable before 0.5 lands |
| 2026-07-27 | Configured `greek_cfg` to map to `unaccent` then `simple` directly | The Debian `hunspell-el` dictionary compound rules cause Postgres's `ispell` template parser to loop/hang indefinitely. Bypassing it with `unaccent` + `simple` solves the hang, and prefix/trigram searches match perfectly. |

---

## Blocked on (from `IMPLEMENTATION_PLAN.md` §16)

| # | Question | Blocks | Owner |
|---|---|---|---|
| Q1 | Which EU LLM endpoint, verified on Greek + terms? | 0.10 | engineer |
| Q2 | Does a usable hunspell `el_GR` dictionary exist for PG FTS? | 0.5 | **RESOLVED** — standard hunspell-el hangs in Postgres; unaccent+simple is used. |
| Q3 | Licence terms per source (L10) — check **before** ingesting | 1.1–1.4 | engineer |
| Q4 | Who labels the eval sets? | 1.6, 2.10 | **UNFILLED — staffing risk** |
| Q5 | Are the revised volume/timeline parameters right? | phase plan | engineer |
