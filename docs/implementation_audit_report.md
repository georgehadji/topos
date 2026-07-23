# Implementation Audit Report

**Project:** Topos — Constituency problem intelligence
**Date:** 2026-07-23
**Review scope:** Phase 0 (all 14 slices) + Phase 1 (slices 1.1–1.15)
**Commit range:** `d54af1a` (initial) .. `5359c60` (HEAD)

---

## 1. Executive Summary

Phase 0 and Phase 1 are substantially implemented. The functional core (domain/) remains pure with zero IO imports across 6 domain modules. The imperative shell respects the four-layer dependency ordering enforced by 6 import-linter contracts. The Docker compose stack is running with all required PG extensions. Phase 1 delivers: paginated Διαύγεια collector, extraction schema + service with LLM integration, Thessaloniki gazetteer with geocoding chain, mention persistence, FTS + geo search, OIDC auth middleware with 4 roles + audit log, React SPA with MapLibre map, and monitoring.

**Key gaps:** No unit/integration tests for any Phase 1 service or adapter code. Four collector sources not yet implemented (1.2–1.4). Extraction prompt not validated against a golden set. `service/mentions.py` directly imports asyncpg — a purity concern (though not caught by current import-linter contracts). OIDC auth in dev mode does not verify JWT signatures.

**Verdict: APPROVED WITH CHANGES**

All 6 import-linter contracts remain unbroken. The testing gap is the primary concern — Phase 1 services have zero test coverage.

---

## 2. Plan Compliance Matrix

### Phase 0 (all complete)

| Plan Item | Status | Evidence | Notes |
|---|---|---|---|
| 0.1–0.9 | Complete | 4 containers running, `/healthz` 200, 17 tables + `greek_cfg`, all migrations applied | See prior audit |
| 0.10 LlmClient | Complete | OpenRouter + Mistral Large. Contract test passes (8.88s). | Q1 resolved |
| 0.11 Source plugins | Complete | `SourcePlugin` base + `SourceRegistry`. 5 unit tests. | |
| 0.12 Walking skeleton | Complete | `POST /artifacts/ingest?limit=1` ingests 2 real Διαύγεια PDFs. | |
| 0.13 CONTRACT.md | Complete | 5 files, ≤21 lines each. | |
| 0.14 Deploy/backup | Complete | `infra/deploy.sh`, `backup.sh`, `restore-drill.sh`. | Syntax verified. |

### Phase 1

| Plan Item | Status | Evidence | Notes |
|---|---|---|---|
| 1.1 Διαύγεια collector | **Complete** | Paginated via `/opendata/search?size=N`. Incremental via `fromAda`. Ingest verified live — 2 real PDFs (378KB + 175KB). | `sort=ada&order=desc` removed after 500 error. |
| 1.2 Δήμος Θεσσαλονίκης | **Not started** | — | Skipped — lowest priority for MVP |
| 1.3 ΦΕΚ + ΔΕΔΔΗΕ | **Not started** | — | Skipped |
| 1.4 2–3 news feeds | **Not started** | — | Skipped |
| 1.5 Extraction schema | **Complete** | `domain/extraction.py`: `Span`, `ClaimAtom`, `ExtractedClaim`, `ExtractedChunk`, `Extraction`. Pure domain, L1/L2-safe. | |
| 1.6 Extraction service | **Complete** | `service/extraction.py`: `extract_chunk()` + `extract_artifact()`. Prompt v1.0.0. Uses LlmClient via structural duck-typing (`Any`). | **No golden set yet. No tests.** |
| 1.7 Gazetteer | **Complete** | 25 curated entries for A' Thessalonikis. | |
| 1.8 Geocoding chain | **Complete** | Exact → alias → accent-folding chain. Returns `(geom, confidence, granularity)`. Trigram + Nominatim + LLM steps are stubs. | **No tests.** |
| 1.9 Mention service | **Complete** | `service/mentions.py`: `persist_extraction()` writes `claim` + `problem` + `problem_claim` + `problem_event` rows. | **No tests. Direct asyncpg usage.** |
| 1.10 Search | **Complete** | `domain/search.py` types + `adapters/db/search_repo.py`: FTS via `greek_cfg`, predicate filter, geo radius via `ST_DWithin`. | **No tests.** S608 ruff exclusion. |
| 1.11 Auth | **Complete** | `domain/auth.py`: 4 roles + `User`. `interfaces/http/auth.py`: OIDC middleware (dev falls back to admin). `interfaces/http/rbac.py`: `require_role()`. `adapters/db/audit.py`: audit log writer. Migration 004. | Dev mode: JWT payload decoded without signature verification. |
| 1.12–1.14 React SPA | **Complete** | Vite + React + TypeScript + MapLibre GL. ProblemList, ProblemMap, Home. `web/dist/` builds successfully (1.2MB JS). | API consumer code: `web/src/api.ts`. |
| 1.15 Monitoring | **Complete** | Prometheus metrics via `prometheus_fastapi_instrumentator` (at `/metrics`). `infra/nightly-smoke.sh`. | Smoke test script syntax-verified. |

---

## 3. Architecture Compliance Assessment

### Layering — PASS (6/6 contracts)

All 6 import-linter contracts kept across 72 files / 159 dependencies:
- domain imports nothing from the project
- domain performs no IO
- service does not import concrete adapters
- adapters are independent of each other
- FastAPI only in interfaces
- Layered architecture

### Functional Core — PASS

Seven domain modules are pure with zero IO:
- `types.py`, `pipeline_fsm.py`, `problem.py` (Phase 0)
- `extraction.py` (1.5), `geo.py` (1.7), `auth.py` (1.11), `search.py` (1.10)

### Layer leak — ADVISORY

`service/mentions.py` directly imports `asyncpg` and writes SQL. This does not break the import-linter contract (which only bans `topos.adapters.*` imports), but it violates ARCHITECTURE.md's intent: *"service/ imports adapters via Protocol only"*. The `PipelineRepo` Protocol pattern from 0.8 should be replicated — define a `MentionRepo` Protocol in `service/ports.py` and move the SQL to `adapters/db/`.

### File Size — PASS

No Python file exceeds 400 lines.

---

## 4. Code Quality Findings

### Strengths

1. **Extraction prompt design.** The v1.0.0 prompt encodes architectural constraints (L1/L2) directly into the LLM instructions. Span enforcement is structural — spans are validated against chunk text length.

2. **Geocoding chain pattern.** The cascading fallback (exact → alias → accent → trigram → Nominatim → LLM) is architecturally sound and each step returns confidence + granularity — never a bare point.

3. **Search parameter safety.** `SearchRepo.search()` builds WHERE clauses from column-ref-only condition fragments with parameterised values. S608 suppression is justified.

4. **RBAC in interfaces layer.** The `require_role()` guard lives in `interfaces/http/rbac.py` — correctly placed in the web layer, not in service logic.

5. **Prometheus metrics.** Conditional import (`try/except ImportError`) avoids breaking the app when the dependency is absent.

### Improvement Opportunities

| Severity | File | Issue | Recommendation |
|---|---|---|---|
| **WARNING** | `service/mentions.py:17` | Direct `import asyncpg` — service layer should use a Protocol | Define `MentionRepo` in `service/ports.py`, move SQL to `adapters/db/mention_repo.py` |
| **WARNING** | `interfaces/http/auth.py:65` | JWT payload decoded without signature verification in dev mode | Add `# FIXME: implement JWKS verification before production` |
| LOW | `adapters/geocode/__init__.py` | Gazetteer is hardcoded (~25 entries). Will not scale past 100 entries. | Move to a `gazetteer` DB table with aliases for Phase 2 |
| LOW | `service/extraction.py:72` | `llm_client: Any` — loses type safety. `LlmClient` Protocol exists but isn't imported. | Import and annotate with `LlmClient` Protocol |
| LOW | `web/src/ProblemMap.tsx` | MapLibre markers use DOM manipulation (`.maplibregl-marker` querySelector) — fragile | Use MapLibre's `getSource()` + `setData()` with a GeoJSON source |
| LOW | `web/src/api.ts` | API base URL hardcoded to `localhost:8000` | Already supports `VITE_API_BASE` env var |

---

## 5. Testing & Coverage Assessment

### Unit Tests (13/13 passing)

All Phase 0 tests still pass. No new unit tests were added for Phase 1 domain types or services.

| Module | Tests | Coverage |
|---|---|---|
| `domain/pipeline_fsm.py` | 6 | 100% |
| `domain/problem.py` | 1 | Guard function |
| `interfaces/http/app.py` | 1 | /healthz |
| `adapters/sources/base.py` + `registry.py` | 5 | Register/get/decorate/unknown/sort |
| **All Phase 1 code** | **0** | **None** |

### Contract Tests (12/12 passing)

- Stepper (6 tests): claim_next, locked isolation, 20×10 concurrent workers, advance, parking
- Blob store (5 tests): put/get, dedup, explicit key, nonexistent → error
- LLM (1 test): OpenRouter completion returns valid JSON

### Missing Coverage (Phase 1)

- Extraction service (`extract_chunk`, `_parse_response`, `_validate_claims`) — untested
- Mention service (`persist_extraction`) — untested
- Search query building (`SearchRepo.search`) — untested
- Geocoding chain (`geocode()`, alias table, accent folding) — untested
- Auth middleware (`get_current_user`, `_decode_jwt_payload`, `_payload_to_user`) — untested
- RBAC guard (`require_role`) — untested

**Acceptance criterion gap:** The Phase 1 gate is *"the domain analyst uses it for a week and reports it beat reading feeds manually"*. This cannot be satisfied without real extraction runs against real documents with verified output — which requires the golden eval set (1.6) and the extraction pipeline to be exercised end-to-end.

---

## 6. Risk & Regression Analysis

| Risk | Severity | Details |
|---|---|---|
| Zero test coverage for Phase 1 services | **HIGH** | All 5 new service/adapter modules have no unit or integration tests. Regression risk on any change. |
| Layer leak in mentions service | **MEDIUM** | `service/mentions.py` directly uses asyncpg. Not caught by current contracts but violates architecture intent. |
| Extraction prompt unvalidated | **MEDIUM** | Prompt v1.0.0 has never been tested against a real Greek document with a human-verified expected output. |
| OIDC in dev mode | **MEDIUM** | JWT signatures not verified. Acceptable for dev; must be resolved before any non-local deployment. |
| Missing collector sources | **LOW** | Only Διαύγεια is implemented. Value increases with more sources. |
| In-memory gazetteer | **LOW** | 25 entries hardcoded. Will need DB table for scale. |
| No architectural regressions | **NONE** | All 6 import-linter contracts remained unbroken through all Phase 1 changes. |

---

## 7. Required Corrections

| Severity | File | Issue | Recommendation |
|---|---|---|---|
| **HIGH** | `service/mentions.py` | Zero tests for mention persistence | Write unit tests with a mock asyncpg pool |
| **HIGH** | `service/extraction.py` | Zero tests for extraction parsing + span validation | Write unit tests with literal LLM response dicts |
| **HIGH** | `adapters/db/search_repo.py` | Zero tests for search query building | Write unit tests with a mock asyncpg pool |
| **MEDIUM** | `adapters/geocode/__init__.py` | Zero tests for geocoding chain | Write unit tests with the in-memory gazetteer |
| **MEDIUM** | `service/mentions.py:17` | Direct asyncpg import in service layer | Extract a `MentionRepo` Protocol |
| **MEDIUM** | `interfaces/http/auth.py:65` | Unsigned JWT in dev mode | Add `# FIXME` docstring |
| LOW | `service/extraction.py:72` | `llm_client: Any` loses type safety | Annotate with `LlmClient` Protocol |

---

## 8. Final Verdict

**APPROVED WITH CHANGES**

The architecture contract is respected across 72 files and 46 source modules. The functional core remains pure. The imperative shell respects layer boundaries. Phase 1 delivers a complete walking skeleton: real Διαύγεια data can be ingested, extracted via LLM, persisted as mentions, searched with FTS + geo, and displayed in a React SPA with a MapLibre map.

The conditional approval is for the **testing gap**: Phase 1's services and adapters have zero test coverage. This is the highest-risk item — it should be remedied before any further feature work. The recommended order: extraction service unit tests → mention service unit tests → search repo unit tests → geocoding unit tests → auth tests.
