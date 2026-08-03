# Topos — Architecture (always load this)

Paste this file into every implementation session. It is the contract between the plan and the
code. If code and this file disagree, the code is wrong — or this file needs an ADR first.

Full reasoning: `docs/IMPLEMENTATION_PLAN.md`. Task ledger: `docs/PROGRESS.md`.

---

## What this is

A system that ingests Greek public-sector and news sources for one electoral constituency
(Α΄ Θεσσαλονίκης), extracts citizen-affecting problems, geolocates them, deduplicates them,
scores them, and shows a policy office what changed — with every claim traceable to a byte
range in a source document.

Users: ~8 internal. Not a consumer product. 1 engineer, no ops team.

---

## Non-negotiable constraints

| ID | Constraint | Enforced by |
|---|---|---|
| L1 | No profile of any natural person | No `person` table exists. Persons appear only as `authority` (an office) |
| L2 | No inference of political opinion, health, religion, ethnicity, union membership | Those fields are absent from the extraction Pydantic schema — unrepresentable, not filtered |
| L5 | Every claim resolves to a source span | `claim.span int4range` is NOT NULL; claims with unresolvable spans are rejected at the boundary |
| L6 | Recommendations need human sign-off before export | Approval gate + audit log |
| L8 | EU data residency | EU host, EU object storage, EU LLM endpoint |
| L10 | Per-source rights honoured | `source.rights` jsonb, checked before storage and display |

**DeepSeek writes this code. DeepSeek's API must never be called at runtime with citizen data**
(non-EU hosting, violates L8). Runtime inference uses the configured EU endpoint only.

---

## Shape

Two processes, one image, one database, one host.

```
React SPA → Caddy → FastAPI (api)  ─┐
                    Worker (pipeline)┴→ PostgreSQL 16  +  S3-compatible object storage
                                       (postgis, pgvector, pg_trgm, unaccent)
```

**PostgreSQL is the only database.** It is the relational store, the geospatial store, the
vector store, the search index, the graph (edge table + recursive CTEs), and the job queue.
Do not add Redis, Kafka, Neo4j, OpenSearch, Qdrant, or Celery. Each was explicitly rejected
(ADR-002/004). Proposing one requires an ADR.

---

## Layering — enforced by `import-linter` in CI

```
interfaces/   http routers, cli      → may import: service, domain
service/      orchestration, ports   → may import: domain          (adapters via Protocol only)
adapters/     postgres, s3, llm, http→ may import: domain
domain/       pure logic             → imports NOTHING from topos.*
```

`domain/` rules: no IO, no `async`, no network, no clock reads, no randomness, no imports from
other project packages. Only stdlib + pydantic. If you need the time, it is a parameter.

Ports (`service/ports.py`) are `typing.Protocol`, not ABCs. Adapters satisfy them structurally.

---

## Core paradigm: functional core, imperative shell

Everything that **decides** is a pure function in `domain/`:
scoring, entity-resolution features, geocode candidate ranking, pipeline state transitions,
corroboration, deduplication, Greek text normalisation.

Everything that **does IO** is a thin adapter with no logic in it.

**Why:** pure functions are tested with literal inputs and literal expected outputs — no mocks.
Mock-heavy tests written by an LLM assert the mocks and prove nothing. This is the single most
important rule in this document.

```python
# domain/scoring.py — YES
def priority(impact: float, urgency: float, tractability: float, weights: Weights) -> Score: ...

# domain/scoring.py — NO
async def priority(problem_id: UUID, db: Database) -> Score: ...
```

---

## Repository layout

```
src/topos/
  domain/     types  problem  scoring  resolution  geo  evidence  text_gr
  service/    ports  ingest  extract  resolve  score  search  review  pipeline
  adapters/   db/  blob/  llm/  http/  geocode/  ocr/  stt/  sources/
  interfaces/ http/  cli/
tests/        unit/ (domain, no mocks)  contract/ (real PG)  golden/ (Greek fixtures)  e2e/
eval/         labelled Greek eval sets + runner
alembic/      hand-written migrations (no autogenerate)
web/          React + Vite + MapLibre
```

**File limit: 400 lines.** Enforced in CI. Reason is context economics, not style.

---

## Data access

**Raw SQL via asyncpg. No ORM.** PostGIS geometry, `int4range`, `tstzrange`, `halfvec` and
recursive CTEs are all worse through an ORM. Queries live in `adapters/db/` repository classes,
one method per query, returning domain types.

Migrations are hand-written Alembic `op.execute("...")`. No autogenerate.

Every write path goes through a Unit of Work: one transaction per request or per pipeline step.

---

## The pipeline (ADR-004)

Each artifact has a row in `pipeline` with an explicit state. Workers claim one item, advance
exactly one state, commit. No broker.

```
fetched → textified → chunked → extracted → geocoded → resolved → indexed → done
                                                                          ↘ parked
```

Claim query — this is the entire queue:

```sql
UPDATE pipeline SET locked_until = now() + interval '10 min', attempts = attempts + 1
WHERE artifact_id = (
  SELECT artifact_id FROM pipeline
  WHERE state <> 'done' AND run_after <= now()
    AND (locked_until IS NULL OR locked_until < now())
  ORDER BY run_after FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *;
```

**Every step must be idempotent keyed on `(artifact_id, state)`.** At-least-once delivery.
After N attempts → `parked` + a `review_task`. Enqueue shares the transaction with the data
write, so a job can never be lost.

The transition table itself lives in `domain/problem.py` as a pure function and is unit-tested
independently of the database.

---

## Immutability rules

- `artifact` is immutable. A changed source produces a **new row** with `observed_seq + 1` and
  `superseded_by` on the old one. Never UPDATE content.
- `claim` is immutable. Retraction sets `retracted_at`. **Never DELETE a claim.**
- `problem_event` is append-only. `problem` is a rebuildable projection of it (ADR-007).
- Entity-resolution merges are `er_decision` rows and are reversible via `reverted_by`.
  An irreversible merge destroys data; merges are wrong often.

---

## LLM usage

One `LlmClient` Protocol, one decorator stack:

```
BudgetGuard( Cache( Retry( Telemetry( provider ) ) ) )
```

- **BudgetGuard**: hard monthly ceiling. On breach it defers work to a queue. It never overspends.
- **Cache**: keyed on `sha256(prompt_version + model + input)`. Makes backfill reruns ~free.
- **Telemetry**: every call writes an `extraction_run` row — prompt version, model, params,
  tokens, cost. Nothing calls a model without leaving a record.

**Prompts are code**: versioned files, reviewed, with golden tests. The prompt version is stored
on every derived fact.

**Every ingested document is untrusted input.** Document text goes in a delimited, labelled
untrusted region. Output is schema-validated. Any output whose spans do not resolve into the
source is rejected. Injection canaries live in the golden set.

**There is one agentic component** (grounded analyst Q&A). Extraction, summarization and OCR
correction are single-shot structured-output calls, not agents. Geocoding, deduplication,
scoring, routing and alerting are deterministic code — do not put an LLM in them.

---

## Search (ADR-010, rerank stage superseded by ADR-013)

Raw chunks are **lexical only** (Greek FTS + trigram).

Retrieval: lexical first pass (high recall on Greek proper nouns and administrative IDs) →
rerank → optional graph expansion → RRF fusion.

The rerank stage runs via a hosted cross-encoder (OpenRouter `/rerank`), not the pgvector
pipeline ADR-010 originally implied — see ADR-013 for why. `problem_vec` (migration 001_core.py)
is dead schema as a result: created, never written, never read.

---

## Greek

The dominant technical risk. Never assume English-grade accuracy.

- Postgres 16 **does** ship a Greek snowball stemmer. `greek_cfg` is `unaccent` +
  `el_gr_stem` (snowball `greek`) + `simple` as fallback, set by migration 006. It folds
  inflection and accents: `δρόμου`/`δρόμος` → `δρομ`, `Θεσσαλονίκης`/`Θεσσαλονίκη` → `θεσσαλονικ`.
  The earlier hunspell `el_GR` dictionary never stemmed — Debian ships it as a flag-less
  expanded word list — so `greek_cfg` did accent folding only until 006. Verify quality; do not assume.
- Toponyms: genitive→nominative (`Εγνατίας`→`Εγνατία`), accent folding, Latin transliteration,
  informal neighbourhoods (`Τούμπα` / `Άνω Τούμπα`) as curated fuzzy polygons.
- Geocoding returns `(geom, confidence, granularity)` — never a bare point. The UI draws the
  uncertainty.
- No Greek behaviour is accepted without a golden fixture with hand-verified expected output.

---

## Scoring

A DAG, not a list of siblings:

```
measured: severity  reach  trend  evidence_strength  tractability  cost
derived:  impact  = f(severity, reach)
          urgency = f(trend, severity, deadlines)
          priority= f(impact, urgency, tractability, cost, leverage)
```

Pure functions. Weights in a versioned config file, never in code. Missing inputs are
explicitly `unknown`, never silently zero. Every computation writes a `score_snapshot`
containing **every node**, so any past ranking stays explainable.

`reach` counts **independent sources**, not reports — three outlets republishing one wire is
one source. This is what makes the ranking resistant to coordinated submission.

---

## Definition of done for any slice

`make check` green — which runs:

```
ruff · mypy --strict · import-linter · file-length ≤400 · pytest · alembic check
```

plus: the named acceptance test passes · `CONTRACT.md` updated if an interface moved ·
`docs/PROGRESS.md` updated · **no new dependency and no schema change without an ADR**.

---

## Rules for the implementer

1. Touch only the files listed in the task. Nothing else.
2. Do not add dependencies. Do not change the schema. Do not cross module boundaries.
3. If the contract is wrong or ambiguous, **stop and say so**. Do not improvise an interface.
4. Put logic in `domain/` as a pure function. Adapters stay thin.
5. Write the test against real values, not mocks. Mock only the network boundary.
6. If you cannot verify something about Greek, say `[UNVERIFIED]` — do not guess and move on.
7. Prefer deleting code to adding an abstraction. YAGNI applies hard at this team size.
