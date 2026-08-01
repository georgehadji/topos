# Topos — Intelligence Integration Implementation Plan

**Scope:** Integration of xAI/Grok tools (web search, X search, collections search, remote MCP) and Perplexity Sonar as supplementary discovery, extraction, and analyst-Q&A capabilities.

**Status:** Draft for review. No ADR has been filed yet — Phase 0 gates all subsequent work.

**Date:** 2025-07-27

---

## 1. Executive Summary

Topos currently uses a single LLM capability: one-shot structured extraction from Greek public-sector documents via OpenRouter → Mistral Large. This works for its designed purpose but leaves significant signal on the table — real-time citizen reports on X, problems reported on websites not covered by the six existing source plugins, and the ability to ask analytical questions against the accumulated problem database.

This plan proposes five phased integrations, ordered cheapest-first per the project's ponytail-mode convention:

| Phase | Capability | Code change | Risk | EU Data Safe? |
|---|---|---|---|---|
| **0** | Drop-in model swap + fallback provider | FallbackProvider adapter | Minimal | Depends on xAI EU hosting |
| **1** | Manual analyst workflow (Grok Web, X Search, Sonar) | None | None | Public data only |
| **2** | X Search source plugin | New plugin + adapter | Medium | Public posts only |
| **2S** | Sonar web discovery plugin | New plugin + adapter | Low | Public data only |
| **3** | Collections Search analyst Q&A | Export pipeline + Grok collection | Medium | Must filter exports |
| **4** | Remote MCP server | New interface module | High | Yes, data stays EU-side |

Each phase is independently valuable and gated by the preceding phase's validation results. Phase 2S (Sonar) is a parallel track to Phase 2 (X Search) — either or both can proceed after Phase 1 proves their respective signal. No phase proceeds without green `make check` and an accepted ADR.

---

## 2. Current Architecture Assessment

### 2.1 Strengths relevant to this integration

- **Clean Architecture port system.** The `LlmClient` Protocol (`service/ports.py:30-46`) decouples consumers from providers. A new provider (xAI, Perplexity) needs only to satisfy the Protocol — no service-layer changes.
- **Decorator stack is composable.** `BudgetGuard(Cache(Retry(Telemetry(provider))))` means any new provider automatically inherits caching, retry, telemetry, and budget enforcement.
- **Source plugin registry.** The `@register` decorator pattern (`adapters/sources/registry.py:14`) makes adding a new source type a matter of subclassing `SourcePlugin` and importing the module — zero changes to the pipeline FSM or worker loop.
- **OpenAI-compatible API surface.** Both xAI and Perplexity speak OpenAI-compatible chat completions, matching what `OpenRouterProvider` already sends (`/chat/completions`).
- **Budget enforcement exists.** `BudgetGuard` (`adapters/llm/budget.py`) already caps monthly spend. Adding a second LLM endpoint means adding a second budget line, not inventing budget control from scratch.

### 2.2 Gaps and constraints

- **Tool-calling requires the Responses API, not Chat Completions.** xAI's `web_search`, `x_search`, `collections_search`, and `mcp` tools are only available via `/v1/responses` — a different endpoint and request/response shape than the current `/chat/completions`. The `LlmClient` Protocol only defines `complete()`, which has no concept of tools. A new Protocol (or an extension) is needed.
- **No golden tests exist yet.** `tests/golden/` is an empty directory. Per ARCHITECTURE.md: *"No Greek behaviour is accepted without a golden fixture with hand-verified expected output."* Any new source that produces Greek-language results (X Search, Sonar) must ship with golden fixtures — and the golden test infrastructure itself must be built first.
- **No ADRs exist yet.** `docs/adr/` is empty. Per ARCHITECTURE.md: *"No new dependency and no schema change without an ADR."* Every phase beyond Phase 0 requires at least one ADR.
- **400-line file limit.** New plugin modules, LLM adapters, and MCP handlers must fit within the 400-line ceiling. Complex adapters will need to be split into multiple cohesive files.
- **Single database constraint.** New data (social mention metadata, collection export tracking) goes into PostgreSQL or nowhere. No auxiliary stores.
- **L8 EU data residency.** Runtime inference with citizen data must use EU-hosted endpoints. Public social media posts are not citizen data per se, but any pipeline that processes them alongside citizen data needs careful boundary design.

### 2.3 Architecture fit summary

```
                                                ┌──────────────────────────┐
Phase 2-2S: New adapters  ───────────────────►  adapters/                │
            (xai_provider, social_plugin,       │  ├─ llm/                │
             sonar_plugin)                      │  │  ├─ xai.py       NEW │
                                                │  │  └─ sonar.py     NEW │
Phase 3:    Export pipeline ──────────────────►  │  ├─ sources/            │
            (collections)                        │  │  ├─ social.py    NEW │
                                                │  │  └─ sonar_web.py NEW │
Phase 4:    New interface ────────────────────►  │  └─ ...                 │
            (mcp/)                               │                         │
                                                │  service/               │
Phase 0-1:  No code changes                     │  └─ ports.py            │
            (config, manual workflow)            │     (may add            │
                                                │      ToolLlmClient      │
                                                │      Protocol)          │
                                                └──────────────────────────┘
```

---

## 3. Detailed Implementation Plan

### Phase 0 — Model Swap Experiment + Fallback Provider (config + small adapter change)

**Objective:** Evaluate whether Grok's extraction quality on Greek text justifies further investment, and implement the xAI-first → OpenRouter fallback provider pattern.

**Constraint:** Per project policy, xAI models must be called via the xAI API key first; only if that call fails (network error, auth error, rate limit, 5xx) does the system fall back to OpenRouter for the same model. Grok 4.5 supports Chat Completions on both endpoints, so both paths use the same request shape.

**Design — `FallbackProvider`:**

```
FallbackProvider
  ├── primary: OpenRouterProvider(base_url=https://api.x.ai/v1, api_key=XAI_API_KEY)
  └── fallback: OpenRouterProvider(base_url=https://openrouter.ai/api/v1, api_key=OPENROUTER_API_KEY)
```

Both targets use the Chat Completions API (`/v1/chat/completions`). The model name is `grok-4.5` on xAI direct, and `x-ai/grok-4.5` (or the OpenRouter slug) on OpenRouter. The FallbackProvider stores both model names and translates automatically.

The `FallbackProvider` sits at the innermost position in the decorator stack:

```
BudgetGuard( Cache( Retry( Telemetry( FallbackProvider(primary, fallback) ) ) ) )
```

The `Retry` decorator already handles transient failures on the same provider. The `FallbackProvider` handles the case where the primary is unreachable or returns a non-retryable error (401, 403, 5xx after retries exhausted). The fallback is tried once; if it also fails, the error propagates up.

**Settings changes:**

```ini
TOPOS_LLM_PROVIDER=xai                  # new: "openrouter" | "xai"
TOPOS_XAI_API_KEY=                      # new
TOPOS_XAI_BASE_URL=https://api.x.ai/v1  # new
TOPOS_LLM_MODEL=grok-4.5
TOPOS_LLM_FALLBACK_MODEL=x-ai/grok-4.5  # new: OpenRouter slug
```

The existing `TOPOS_LLM_API_KEY` and `TOPOS_LLM_BASE_URL` continue to serve as the OpenRouter (fallback) credentials.

**Tasks:**

| # | Task | File(s) | Est. lines |
|---|---|---|---|
| 0.1 | Add new settings fields to `Settings` class | `config.py` | +8 |
| 0.2 | Implement `FallbackProvider` (try primary, fallback on failure) | `adapters/llm/fallback.py` | ~60 |
| 0.3 | Update `build_llm_client()` to wire FallbackProvider when `llm_provider=xai` | `adapters/llm/__init__.py` | +15 |
| 0.4 | Write unit test: primary succeeds → fallback not called | `tests/unit/test_llm_stack.py` | +30 |
| 0.5 | Write unit test: primary fails → fallback called | `tests/unit/test_llm_stack.py` | +30 |
| 0.6 | Spin up local stack, configure for xAI-primary | — | — |
| 0.7 | Ingest known document; compare Grok extraction quality vs Mistral Large baseline | — | — |
| 0.8 | Kill xAI connectivity (wrong key); verify fallback to OpenRouter works | — | — |
| 0.9 | Record extraction quality comparison + fallback latency in `docs/PROGRESS.md` | — | — |

**Acceptance criteria:**
- `make check` is green.
- Unit tests pass: primary-succeeds and primary-fails scenarios.
- Grok extraction quality is at parity or better than Mistral Large on ≥3 hand-verified Greek documents.
- Cost per extraction is within the €250/month budget at current ingestion volume.
- When xAI API is unreachable, the system falls back to OpenRouter and completes the extraction.
- Fallback event is logged at WARNING level and recorded in telemetry.

**Rollback:** Set `TOPOS_LLM_PROVIDER=openrouter` to bypass the fallback logic entirely. No code to roll back.

**ADR required:** No — this is a non-destructive addition that extends the existing provider pattern without changing the Protocol.

---

### Phase 1 — Manual Analyst Workflow (no code)

**Objective:** Prove that web+X search discovers problems the existing source plugins miss, before committing to automation.

**Tasks:**

1. Define a weekly analyst workflow document (`docs/analyst_workflow.md`) with these steps:
   - Query Grok with `web_search` + `x_search` tools (via xAI Playground or SDK script):
     - *"What infrastructure problems (road damage, water outages, power cuts, flooding) were reported in Θεσσαλονίκη in the past 7 days? Cite sources."*
     - *"Search X for posts about διακοπή νερού OR διακοπή ρεύματος OR καταστροφή δρόμου in Thessaloniki since YYYY-MM-DD."*
   - Review cited URLs/posts.
   - Feed high-signal discoveries into `POST /artifacts/ingest` or manually create `artifact` rows.
2. Track for 2 weeks: how many unique problems were discovered via this workflow vs. existing plugins? How many made it through the pipeline to the UI?
3. Build the initial golden test fixture: for 5 hand-verified X posts or web articles, record the expected extracted claims (predicate, value, span).

**Acceptance criteria:**
- ≥3 unique problems discovered per week that no existing plugin detected.
- Golden fixture of ≥5 hand-verified expected outputs exists.
- Signal-to-noise ratio is documented (what fraction of returned results are actually citizen-affecting problems vs. noise).

**Rollback:** Stop running the manual workflow. No code to roll back.

**ADR required:** No — manual workflow is not a permanent system change.

---

### Phase 2 — X Search Source Plugin (new adapter module)

**Objective:** Automate X (Twitter) monitoring as a first-class source, flowing through the existing pipeline.

**Design:**

```
adapters/llm/xai.py            NEW — XaiProvider (Responses API, tool-calling)
adapters/sources/social.py     NEW — SocialPlugin (SourcePlugin subclass)
tests/unit/test_social_plugin.py    NEW
tests/golden/social/           NEW — hand-verified Greek X post fixtures
docs/adr/ADR-012-x-search.md   NEW
```

**Architecture decisions:**

1. **New `XaiProvider`** in `adapters/llm/xai.py`:
   - Targets `https://api.x.ai/v1/responses` (Responses API) for tool-calling (x_search, web_search). Does NOT use the Chat Completions path — tool-calling requires the Responses endpoint.
   - For consistency with Phase 0's fallback pattern: this provider also follows xAI-first → OpenRouter fallback. However, OpenRouter may not support the Responses API with tools. If it doesn't, the fallback for tool calls is to make a best-effort Chat Completions call with the search query embedded in the prompt — degraded but functional.
   - Implements the existing `LlmClient.complete()` Protocol, with an optional `tools: list[dict] | None = None` kwarg added to the Protocol signature. The `OpenRouterProvider` and `FallbackProvider` ignore it (or pass it through if the underlying API supports it). The `XaiProvider` uses it to invoke `x_search` / `web_search` via the Responses API.
   - This avoids creating a second Protocol while the tool surface is small.
   - Reuses the existing decorator stack: `BudgetGuard(Cache(Retry(Telemetry(XaiProvider))))`. Note: the Cache decorator keys on `sha256(prompt + model + input)`. For tool-calling, the cache key must include the tool definitions to avoid cache collisions. Plan: add `tools` to the cache key in `cache.py`.

2. **New `SocialPlugin`** in `adapters/sources/social.py`:
   - `kind = "social"`
   - `config_model = SocialConfig` with fields:
     - `platform: Literal["x"]` (forward-compatible with future platforms)
     - `queries: list[str]` — Greek query strings like `"διακοπή νερού Θεσσαλονίκη"`
     - `allowed_handles: list[str] | None` — e.g. `["@deddiede", "@CityofThess"]`
     - `lookback_hours: int = 24`
   - `fetch()` calls `XaiProvider` with `x_search` tool, parses results into `PluginArtifact` rows (one per post, `mime="text/plain"`, `meta` with post URL, timestamp, author handle).
   - The pipeline processes these normally: FETCHED → TEXTIFIED (text is the post body) → CHUNKED → EXTRACTED (LLM extracts citizen-affecting claims from the post text).
   - **Critical:** posts with images/video are skipped in this phase. Image understanding is deferred to a future enhancement (it requires a Responses API call with `enable_image_understanding`, which is a different code path).

3. **New golden test directory** `tests/golden/social/`:
   - Contains JSON fixtures: `{post_text, expected_claims: [{predicate, value, span_start, span_end}]}`
   - Test reads fixture, calls `extract_chunk()` with the post text, asserts claims match.
   - This is the "hand-verified expected output" that ARCHITECTURE.md demands for Greek-language behaviour.

**Implementation tasks (ordered):**

| # | Task | File(s) | Est. lines |
|---|---|---|---|
| 2.1 | Write ADR-012: X Search as a source | `docs/adr/ADR-012-x-search.md` | ~60 |
| 2.2 | Extend `LlmClient` Protocol with optional `tools` kwarg | `service/ports.py` | +3 |
| 2.3 | Add `tools` to cache key in `Cache.complete()` | `adapters/llm/cache.py` | +5 |
| 2.4 | Implement `XaiProvider` (Responses API, `x_search` tool, with xAI-first → OpenRouter fallback) | `adapters/llm/xai.py` | ~150 |
| 2.5 | Add `xai` to import-linter adapters independence contract | `.importlinter` | +1 |
| 2.6 | Implement `SocialPlugin` with `fetch()` calling XaiProvider | `adapters/sources/social.py` | ~150 |
| 2.7 | Register in `adapters/sources/__init__.py` | `adapters/sources/__init__.py` | +1 |
| 2.8 | Write unit tests for `SocialPlugin` (mock XaiProvider) | `tests/unit/test_social_plugin.py` | ~80 |
| 2.9 | Build golden fixture: 5 hand-verified Greek X posts → expected claims | `tests/golden/social/fixtures.json` | ~50 |
| 2.10 | Write golden test runner | `tests/golden/test_social_golden.py` | ~60 |
| 2.11 | Add `social` to `make seed` or a separate seeding command | `interfaces/cli/` | ~30 |
| 2.12 | Run `make check` and fix all failures | — | — |

**Total estimated new lines:** ~590 across 8 files.

**Testing strategy:**
- **Unit:** Mock `XaiProvider` responses; verify `SocialPlugin.fetch()` correctly parses tool results into `PluginArtifact` rows.
- **Contract:** With a real xAI API key (test environment), call `XaiProvider` with a known query, verify response shape.
- **Golden:** `tests/golden/social/` — hand-verified Greek posts → expected extraction output. Run as part of `make test-golden`.

**Acceptance criteria:**
- `make check` is green.
- `make test-golden` passes with the social golden fixtures.
- A `POST /artifacts/ingest?kind=social` call successfully creates pipeline rows from X posts.
- The pipeline advances social artifacts through to `DONE` with valid claims.
- `BudgetGuard` enforces a separate social-search budget (or the existing €250 is verified sufficient).

**Rollback:** Remove the `social` import from `adapters/sources/__init__.py`. The plugin disappears from the registry. Existing pipeline rows continue processing normally. No database migration to reverse (the plugin uses existing tables).

---

### Phase 2S — Sonar Web Discovery Plugin (new adapter module, parallel to Phase 2)

**Objective:** Automate Perplexity Sonar as a supplementary source-discovery channel, finding problems reported on Greek websites not covered by the six existing source plugins.

**Why Sonar instead of Grok Web Search for this:**

| Property | Perplexity Sonar | Grok `web_search` tool |
|---|---|---|
| Search trigger | **Always, before answer.** Architectural — search is the pipeline, not a tool. | When the model **chooses** to call the tool. Optional. |
| Hallucination guard | Structural: *"Only answer using search results. If nothing found, say so."* | Prompt-based: relies on model respecting instructions. |
| Domain filtering | `search_domain_filter` parameter (API-native) | `allowed_domains` parameter (API-native) |
| Recency filtering | `search_recency_filter` parameter (hour/day/week/month) | Date-based via `from_date`/`to_date` on `x_search` only |
| API surface | Chat Completions (`/v1/chat/completions`) — **same as existing OpenRouterProvider** | Responses API (`/v1/responses`) — different endpoint |
| Alignment with L5 | Natural: every answer claim links to a search-result citation. | Indirect: citations available but model chooses whether to cite. |

Sonar's enforced search-before-answer architecture is philosophically aligned with Topos's L5 span-traceability mandate. Every Sonar response is citation-grounded by construction — the model cannot generate unsourced claims. For a policy office where untraceable claims are rejected at the boundary, this is the safer choice for web discovery.

**Design:**

```
adapters/llm/sonar.py              NEW — SonarProvider (Chat Completions, wraps OpenRouter for perplexity/ models)
adapters/sources/sonar_web.py      NEW — SonarWebPlugin (SourcePlugin subclass)
tests/unit/test_sonar_plugin.py    NEW
tests/golden/sonar/                NEW — hand-verified Greek web-article fixtures
docs/adr/ADR-012s-sonar.md         NEW
```

**Architecture decisions:**

1. **`SonarProvider`** in `adapters/llm/sonar.py`:
   - Uses the **Chat Completions API** — same as `OpenRouterProvider`. Perplexity Sonar models (`sonar`, `sonar-pro`) are available through OpenRouter at `perplexity/sonar` and `perplexity/sonar-pro`.
   - Alternatively, can target Perplexity's API directly at `https://api.perplexity.ai/v1/chat/completions` for lower latency and direct pricing.
   - Decision: target OpenRouter first (zero new API credentials, existing `LLM_API_KEY` works). If volume warrants and latency matters, add a direct Perplexity path via `PERPLEXITY_API_KEY`.
   - Implements the existing `LlmClient.complete()` Protocol. Unlike `XaiProvider` (Phase 2), Sonar does NOT need the `tools` kwarg — search is implicit in every Sonar call, not a tool the model optionally invokes.
   - Sonar's key parameters map to the existing call signature:
     - `search_domain_filter` → passed as an extra kwarg in `complete(**kwargs)`, forwarded by the decorator stack
     - `search_recency_filter` → same mechanism
   - No changes to `Cache` decorator needed — the cache key already includes `model` and `prompt`, which is sufficient since Sonar's search parameters don't change between calls for the same source config.

2. **`SonarWebPlugin`** in `adapters/sources/sonar_web.py`:
   - `kind = "sonar_web"`
   - `config_model = SonarWebConfig` with fields:
     - `queries: list[str]` — Greek query strings like `"προβλήματα υποδομής Θεσσαλονίκη"` or `"What infrastructure problems were reported in Thessaloniki this week?"`
     - `domains: list[str]` — trusted Greek domains, e.g. `["thessaloniki.gr", "voria.gr", "typosthes.gr", "parallaximag.gr", "makthes.gr"]`
     - `recency: Literal["day", "week", "month"]` — `search_recency_filter` value
     - `max_results: int = 10` — cap on returned citations
   - `fetch()` calls `SonarProvider.complete()` with the query as the user message. The system prompt enforces grounding rules:
     ```
     Only answer using the search results provided. If the results do not contain
     the answer, say so explicitly rather than guessing. If the search results are
     related but do not match the question, state the mismatch explicitly.
     ```
   - Parses Sonar's response for `citations` (URLs) and `search_results` (title, snippet, URL).
   - For each unique URL, yields a `PluginArtifact` with:
     - `uri = url` (the web page URL)
     - `data = snippet.encode("utf-8")` (the search-result snippet as initial text)
     - `mime = "text/plain"`
     - `meta = {"source": "sonar", "query": query, "url": url, "title": title}`
   - The pipeline processes these normally: FETCHED → TEXTIFIED (worker fetches the full page via HTTP, replacing the snippet) → CHUNKED → EXTRACTED.
   - **Constraint:** Per Sonar's prompt guide, the *user message* drives search — the system prompt does not influence retrieval. Queries must be specific and descriptive. Bad: `"Θεσσαλονίκη προβλήματα"`. Good: `"What road damage, water outages, or infrastructure failures were reported in Θεσσαλονίκη municipality this week?"`

3. **Golden test directory** `tests/golden/sonar/`:
   - Contains JSON fixtures with canned Sonar API responses (search results + citations) and expected `PluginArtifact` outputs.
   - Tests verify that `SonarWebPlugin.fetch()` correctly extracts URLs and metadata from Sonar's response format.
   - Because Sonar's responses are in English (even for Greek queries), the golden fixtures validate URL extraction accuracy, not Greek-language claim quality — that's the pipeline's job in later states.

**Implementation tasks (ordered):**

| # | Task | File(s) | Est. lines |
|---|---|---|---|
| 2S.1 | Write ADR-012s: Sonar web discovery as a source | `docs/adr/ADR-012s-sonar.md` | ~60 |
| 2S.2 | Implement `SonarProvider` (Chat Completions, wraps OpenRouter → perplexity/ models) | `adapters/llm/sonar.py` | ~80 |
| 2S.3 | Add `sonar` to import-linter adapters independence contract | `.importlinter` | +1 |
| 2S.4 | Implement `SonarWebPlugin` with `fetch()` calling SonarProvider | `adapters/sources/sonar_web.py` | ~140 |
| 2S.5 | Register in `adapters/sources/__init__.py` | `adapters/sources/__init__.py` | +1 |
| 2S.6 | Write unit tests for `SonarWebPlugin` (mock SonarProvider with canned Sonar responses) | `tests/unit/test_sonar_plugin.py` | ~80 |
| 2S.7 | Build golden fixture: 5 canned Sonar API responses → expected PluginArtifact outputs | `tests/golden/sonar/fixtures.json` | ~50 |
| 2S.8 | Write golden test runner | `tests/golden/test_sonar_golden.py` | ~40 |
| 2S.9 | Add `sonar_web` to `make seed` seeding command | `interfaces/cli/seed_cmd.py` | +10 |
| 2S.10 | Run `make check` and fix all failures | — | — |

**Total estimated new lines:** ~460 across 7 files (fewer than Phase 2 because Sonar uses Chat Completions, no new API surface to implement).

**Testing strategy:**
- **Unit:** Mock `SonarProvider` with canned Perplexity API responses; verify `SonarWebPlugin.fetch()` correctly extracts URLs and metadata.
- **Contract:** With a real Perplexity API key (or OpenRouter key routing to perplexity/), call `SonarProvider` with a known Greek query, verify response shape and citation format.
- **Golden:** `tests/golden/sonar/` — canned Sonar responses → expected plugin outputs.

**Acceptance criteria:**
- `make check` is green.
- `make test-golden` includes sonar golden tests and passes.
- A `POST /artifacts/ingest?kind=sonar_web` call successfully discovers ≥3 unique URLs from Greek domains.
- Discovered artifacts advance through the pipeline to DONE with valid claims.
- `BudgetGuard` enforces spend limits on Sonar API calls.
- No file exceeds 400 lines.

**Rollback:** Remove the `sonar_web` import from `adapters/sources/__init__.py`. The plugin disappears. Existing pipeline rows continue normally.

**ADR required:** Yes — ADR-012s before any code.

---

### Phase 3 — Collections Search Analyst Q&A (export pipeline + Grok)

**Objective:** Implement the "one agentic component (grounded analyst Q&A)" that ARCHITECTURE.md reserves.

**Design:**

```
service/analyst.py                  NEW — analyst query orchestration
adapters/llm/xai.py                 EXTEND — add collections_search tool support
interfaces/http/analyst.py          NEW — GET/POST /api/analyst endpoints
tests/unit/test_analyst.py          NEW
docs/adr/ADR-013-analyst-qa.md      NEW
```

**Architecture decisions:**

1. **Two-tier approach: snapshot export, not live queries.**
   - A periodic export job (CLI command or scheduled endpoint) dumps `problem` + `claim` + `problem_event` as structured JSON files.
   - These files are uploaded to a Grok "collection" via the xAI SDK (`client.collections.create()` + `upload_document()`).
   - Analyst queries go to Grok with `collections_search(collection_ids=[...])` + `web_search()` tools.
   - Rationale: live database access via MCP (Phase 4) is architecturally cleaner but heavier. Starting with snapshots proves the Q&A patterns before investing in MCP infrastructure. This is the `# ponytail:` approach.

2. **Export format:** NDJSON (one JSON object per line), one file per entity type:
   - `problems.jsonl`: `{problem_id, title, category, status, geom_lat, geom_lon, score_priority, first_seen, last_seen}`
   - `claims.jsonl`: `{claim_id, problem_id, predicate, value, span_text, source_uri}`
   - `events.jsonl`: `{event_id, problem_id, kind, timestamp, detail}`

3. **Query interface:** A new `POST /api/analyst/ask` endpoint:
   - Accepts `{question: str}`.
   - Calls `XaiProvider` with `collections_search` + `web_search` tools.
   - Returns `{answer: str, citations: [{uri, snippet}]}`.
   - Uses the existing `BudgetGuard` (analyst queries count against the LLM budget).

4. **PII filtering:** The export pipeline must strip any field that could contain natural-person data (L1 constraint). Audit the export SQL query to ensure no `authority` names leak into analyst-facing collections.

**Implementation tasks:**

| # | Task | File(s) | Est. lines |
|---|---|---|---|
| 3.1 | Write ADR-013: analyst Q&A with collections search | `docs/adr/ADR-013-analyst-qa.md` | ~60 |
| 3.2 | Implement `export_problems` CLI command (NDJSON dump) | `interfaces/cli/export_cmd.py` | ~80 |
| 3.3 | Implement `XaiProvider.collections_upload()` method | `adapters/llm/xai.py` | +60 |
| 3.4 | Add `collections_search` tool support to `XaiProvider.complete()` | `adapters/llm/xai.py` | +40 |
| 3.5 | Implement `AnalystService.ask()` (orchestration) | `service/analyst.py` | ~100 |
| 3.6 | Implement `POST /api/analyst/ask` endpoint | `interfaces/http/analyst.py` | ~80 |
| 3.7 | Write unit tests for `AnalystService` (mock XaiProvider) | `tests/unit/test_analyst.py` | ~80 |
| 3.8 | Run `make check` and fix all failures | — | — |

**Total estimated new lines:** ~500 across 6 files.

**Testing strategy:**
- **Unit:** Mock `XaiProvider` responses with `collections_search` tool results; verify `AnalystService.ask()` returns properly formatted citations.
- **Integration:** Manual test with a real Grok collection and a subset of exported problems.
- **Golden:** Not applicable (analyst Q&A output is inherently variable).

**Acceptance criteria:**
- `make check` is green.
- `POST /api/analyst/ask` with question *"What are the highest-priority unresolved problems in Thessaloniki?"* returns a cited, grounded answer from the exported collection.
- Export pipeline excludes all natural-person data (L1 audit passes).
- Budget guard caps analyst usage within the €250/month ceiling.

**Rollback:**
- Disable the `/api/analyst` endpoint (remove route registration).
- Stop the export CLI command.
- No database migration to reverse.

---

### Phase 4 — Remote MCP Server (live database access for Grok)

**Objective:** Replace snapshot exports with live, read-only database access via MCP, enabling Grok to answer analytical questions against current data without periodic export cycles.

**Design:**

```
interfaces/mcp/__init__.py       NEW — MCP HTTP/SSE server
interfaces/mcp/tools.py           NEW — tool definitions + handlers
interfaces/mcp/auth.py            NEW — authentication middleware
tests/unit/test_mcp_tools.py      NEW
docs/adr/ADR-014-mcp-server.md    NEW
```

**Architecture decisions:**

1. **Read-only tools only.** The MCP server exposes analytical tools (search, aggregate, retrieve) but no write tools. The L6 approval gate stays human-mediated. Write-back for review workflows is explicitly deferred to a future ADR.

2. **Tool set (initial):**
   - `search_problems(query, predicates, lat, lon, radius_km, limit)` → `[{problem_id, title, category, score, lat, lon}]`
   - `get_problem_detail(problem_id)` → `{title, category, status, claims: [...], events: [...], geom}`
   - `get_pipeline_status()` → `{total, by_state: {}}`
   - `get_scoring_breakdown(problem_id)` → `{impact, urgency, priority, severity, reach, trend, ...}`
   - `list_sources()` → `[{kind, name, last_fetched}]`

3. **Transport:** HTTP/SSE (Streaming HTTP is preferred per xAI's MCP docs; SSE is fallback). Implemented as a FastAPI router mounted at `/mcp/` — consistent with the existing `interfaces/http/` pattern.

4. **Authentication:** The MCP server requires a bearer token (`TOPOS_MCP_API_KEY` env var). Grok's `authorization` parameter in the `mcp()` tool config passes this token. The MCP server validates it on every request.

5. **EU data residency (L8):** The MCP server runs on Topos's EU infrastructure. Tool *descriptions* (which Grok sees at tool-registration time) contain no PII — they're static strings. Tool *results* contain problem summaries but never raw document text or natural-person names. Grok never accesses the database directly — it only sees filtered query results.

6. **Observability:** Every MCP tool invocation writes to the existing `extraction_run` telemetry table with `prompt_ver="mcp"` and `model="grok-mcp"`. This integrates with the existing BudgetGuard — MCP tool calls count against the monthly budget.

**Implementation tasks:**

| # | Task | File(s) | Est. lines |
|---|---|---|---|
| 4.1 | Write ADR-014: MCP server for live analyst access | `docs/adr/ADR-014-mcp-server.md` | ~80 |
| 4.2 | Implement MCP protocol handler (JSON-RPC, tool listing, tool call dispatch) | `interfaces/mcp/__init__.py` | ~200 |
| 4.3 | Implement tool definitions and handlers | `interfaces/mcp/tools.py` | ~250 |
| 4.4 | Implement bearer token auth middleware | `interfaces/mcp/auth.py` | ~40 |
| 4.5 | Register MCP router in FastAPI app | `interfaces/http/app.py` (or main) | +5 |
| 4.6 | Add `mcp` to import-linter interfaces contract | `.importlinter` | +1 |
| 4.7 | Write unit tests for each tool handler | `tests/unit/test_mcp_tools.py` | ~150 |
| 4.8 | Integration test: Grok connects to MCP server, runs a query, returns cited answer | Manual | — |
| 4.9 | Run `make check` and fix all failures | — | — |

**Total estimated new lines:** ~725 across 6 files.

**Testing strategy:**
- **Unit:** Each tool handler tested with a mock database pool returning known rows. Verify JSON-RPC response format.
- **Contract:** With a real PostgreSQL (testcontainers), verify each tool returns correct data against seeded test fixtures.
- **Integration:** Manual test with xAI Playground — configure Grok with MCP tool pointing at a staging Topos instance, ask an analytical question, verify cited answer.

**Acceptance criteria:**
- `make check` is green.
- Grok successfully connects to the MCP server, lists tools, and calls at least one tool.
- `search_problems` returns correct results for a known query (verified against direct SQL).
- All tool responses comply with L1 (no natural-person data exposed).
- Telemetry records every MCP tool invocation.
- Budget guard applies to MCP-related LLM usage.

**Rollback:**
- Remove MCP router registration from the FastAPI app.
- Stop the MCP server process.
- No database migration to reverse (MCP is read-only).
- Revert to Phase 3 snapshot-based analyst Q&A.

---

## 4. Work Breakdown Structure (WBS)

```
Topos Intelligence Integration
│
├── Phase 0: Model Swap Experiment + Fallback Provider
│   ├── 0.1 Add settings fields (config.py)
│   ├── 0.2 Implement FallbackProvider
│   ├── 0.3 Wire into build_llm_client()
│   ├── 0.4 Unit test: primary succeeds
│   ├── 0.5 Unit test: primary fails → fallback
│   ├── 0.6 Spin up local stack with xAI config
│   ├── 0.7 Compare Grok vs Mistral extraction quality
│   ├── 0.8 Verify fallback trigger (kill xAI connectivity)
│   └── 0.9 Document results in PROGRESS.md
│
├── Phase 1: Manual Analyst Workflow
│   ├── 1.1 Document weekly analyst workflow
│   ├── 1.2 Run 2-week trial (Grok Web, X Search, Sonar → manual ingest)
│   ├── 1.3 Measure unique-problem discovery rate (per channel)
│   └── 1.4 Build initial golden fixtures (5 posts + 5 web articles)
│
├── Phase 2: X Search Source Plugin
│   ├── [12 tasks as above]
│
├── Phase 2S: Sonar Web Discovery Plugin
│   ├── 2S.1 ADR-012s: Sonar web discovery
│   ├── 2S.2 Implement SonarProvider (Chat Completions)
│   ├── 2S.3 Update import-linter contracts
│   ├── 2S.4 Implement SonarWebPlugin (SourcePlugin subclass)
│   ├── 2S.5 Register in sources __init__
│   ├── 2S.6 Unit tests: SonarWebPlugin
│   ├── 2S.7 Golden fixtures: 5 Sonar API responses
│   ├── 2S.8 Golden test runner
│   ├── 2S.9 CLI seed command
│   └── 2S.10 make check gate
│
├── Phase 3: Collections Search Analyst Q&A
│   ├── 3.1 ADR-013: analyst Q&A
│   ├── 3.2 CLI export command (NDJSON dump)
│   ├── 3.3 XaiProvider.collections_upload()
│   ├── 3.4 XaiProvider: collections_search tool support
│   ├── 3.5 AnalystService.ask() orchestration
│   ├── 3.6 POST /api/analyst/ask endpoint
│   ├── 3.7 Unit tests: AnalystService
│   └── 3.8 make check gate
│
└── Phase 4: Remote MCP Server
    ├── 4.1 ADR-014: MCP server
    ├── 4.2 MCP protocol handler (JSON-RPC, SSE)
    ├── 4.3 Tool definitions + handlers (5 tools)
    ├── 4.4 Bearer token auth middleware
    ├── 4.5 FastAPI router registration
    ├── 4.6 Import-linter update
    ├── 4.7 Unit tests: MCP tool handlers
    ├── 4.8 Integration test: Grok ↔ MCP
    └── 4.9 make check gate
```

---

## 5. Risk & Mitigation Matrix

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **Greek X search quality is poor** — high noise, low recall on Greek-language posts | Medium | High — kills Phase 2 value proposition | Phase 1 manual trial proves signal quality before any code is written. Golden fixtures set a measurable quality bar. |
| **Sonar Greek-domain coverage is thin** — Perplexity's index may not deeply crawl Greek municipal/news sites | Medium | Medium — limits Phase 2S discovery volume | Phase 1 manual trial includes Sonar queries alongside Grok. Measure citation count and domain coverage before committing to automation. If Sonar's Greek index is shallow, fall back to Grok Web Search for discovery. |
| **Sonar API cost at scale** — Sonar charges per-token + per-search; polling N domains weekly may exceed budget | Low | Medium — constrains Phase 2S frequency | `BudgetGuard` applies. `search_recency_filter="week"` + domain filter minimizes search cost. If cost is prohibitive, reduce query frequency to bi-weekly or monthly. |
| **xAI API changes break tool-calling** — Responses API is newer and less stable than Chat Completions | Medium | Medium — breaks Phase 2-4 | Pin a specific API version if available. Contract tests against xAI's sandbox. Fallback: Phase 3 uses OpenAI-compatible chat completions without tools (prompt-engineering the search into the system message). |
| **L8 violation via MCP tool results** — a query inadvertently returns PII through Grok | Low | Critical — regulatory breach | PII audit on every tool handler before deployment. Read-only tools only. No raw document text in tool results. Automated test that tool outputs never contain Greek name patterns. |
| **Budget overrun** — X search or analyst Q&A burns through the €250/month budget | Medium | Medium — service degraded until next month | BudgetGuard already enforces a hard ceiling. Phase 2 adds a separate social-search budget sub-limit in config. Phase 3/4 analyst queries require explicit user action (not automated), limiting burn rate. |
| **400-line limit forces awkward splits** — `interfaces/mcp/tools.py` with 5 tools exceeds 400 lines | Medium | Low — only affects code organization | Pre-split: one file per tool (`tools/search_problems.py`, `tools/get_problem_detail.py`, etc.) with a shared base in `tools/__init__.py`. The MCP protocol handler is kept under 200 lines. |
| **No golden test infrastructure** — we need golden tests but `tests/golden/` is empty | High | Medium — blocks Phase 2 acceptance | Build golden runner in Phase 1 as part of the manual trial (task 1.4). Reuse the pattern that `make test-golden` already expects: `pytest tests/golden -m golden`. |
| **xAI EU hosting unclear** — inference may run on US infrastructure | Medium | High — L8 constraint for any pipeline that touches citizen data | Phase 0 experiments use public documents only (no citizen data). Phase 2 processes public social media posts. Phase 3-4 PII-audited exports. If xAI confirms EU inference hosting is unavailable, restrict Grok to public-data discovery only and keep extraction on OpenRouter with an EU-hosted model. |

---

## 6. Testing & Quality Assurance Strategy

### 6.1 Testing layers (aligned with existing Topos test structure)

| Layer | Scope | Phase 0 | Phase 1 | Phase 2 | Phase 2S | Phase 3 | Phase 4 |
|---|---|---|---|---|---|---|---|
| **Unit** (`tests/unit/`) | Pure logic, mock adapters | N/A | N/A | `test_social_plugin.py`, `test_xai_provider.py` | `test_sonar_plugin.py` | `test_analyst.py` | `test_mcp_tools.py` |
| **Contract** (`tests/contract/`) | Real API, testcontainers PG | Manual comparison | Manual | `test_xai_contract.py` | `test_sonar_contract.py` | `test_analyst_contract.py` | `test_mcp_contract.py` |
| **Golden** (`tests/golden/`) | Hand-verified Greek expected output | Manual comparison | `fixtures/social/*.json`, `fixtures/sonar/*.json` | `test_social_golden.py` | `test_sonar_golden.py` | N/A | N/A |
| **E2E** (`tests/e2e/`) | Full stack | N/A | N/A | N/A | N/A | `test_mcp_e2e.py` |

### 6.2 CI/CD integration

- `make check` (the gate) already runs: `ruff` → `mypy --strict` → `import-linter` → `filesize` → `pytest` → `alembic check`
- New test files are auto-discovered by pytest (`testpaths = ["tests"]`).
- Contract tests use `markers = ["contract"]` and require `testcontainers`.
- Golden tests use `markers = ["golden"]`.
- CI must have access to an xAI API key (stored as a GitHub secret) for contract tests.

### 6.3 Quality gates per phase

| Phase | Gate |
|---|---|
| 0 | Manual quality comparison documented in PROGRESS.md |
| 1 | ≥3 unique problems/week discovered; golden fixtures exist for both X and web channels |
| 2 | `make check` green; golden tests pass; ADR-012 accepted |
| 2S | `make check` green; golden tests pass; ADR-012s accepted; ≥3 unique URLs discovered per query |
| 3 | `make check` green; ADR-013 accepted; PII audit pass |
| 4 | `make check` green; ADR-014 accepted; Grok integration test pass |

---

## 7. Deployment & Rollback Plan

### 7.1 Deployment sequence

All phases deploy as standard Topos releases (single Docker image, single host):

1. **Merge to main** (requires `make check` green in CI).
2. **`make deploy`** → `./infra/deploy.sh` builds new image, restarts containers.
3. **Smoke test:** `GET /api/healthz` returns 200. If Phase 3: `POST /api/analyst/ask` with a known question returns a valid response.
4. **Monitor:** OpenTelemetry + Prometheus metrics for LLM latency, error rate, budget consumption.

### 7.2 Phase-specific deployment notes

| Phase | Deployment impact | Special steps |
|---|---|---|
| 0 | New adapter + config | `make deploy`. Set `TOPOS_LLM_PROVIDER=xai` with both API keys. Restart containers. |
| 1 | None (manual workflow) | None |
| 2 | New code + new LLM endpoint | Seed the `social` source: `make seed` or `uv run topos-cli seed` |
| 2S | New code (no new endpoint) | Seed the `sonar_web` source: `make seed`. Sonar uses existing OpenRouter API key — no new credentials needed. |
| 3 | New code + new endpoint | Run initial export: `uv run topos-cli export --all` before enabling `/api/analyst` |
| 4 | New code + new interface | Deploy MCP server behind Caddy (same as API). Test Grok connection before announcing. |

### 7.3 Rollback per phase

| Phase | Rollback |
|---|---|
| 0 | Set `TOPOS_LLM_PROVIDER=openrouter`, redeploy. `FallbackProvider` is bypassed entirely. |
| 1 | Stop manual workflow |
| 2 | Remove `social` import from `adapters/sources/__init__.py`, redeploy. Pipeline rows for social artifacts park gracefully (state machine handles unknown source kinds by parking). Add `social` to `ignore_kinds` in worker config if needed. |
| 2S | Remove `sonar_web` import from `adapters/sources/__init__.py`, redeploy. Pipeline rows park gracefully. |
| 3 | Remove `POST /api/analyst/ask` route registration, redeploy. Export data remains in Grok collection (delete manually via xAI console if needed). |
| 4 | Remove MCP router from FastAPI app, redeploy. Revoke MCP API key. Grok loses tool access immediately. |

### 7.4 Backward compatibility

- **Phase 2:** The `tools` kwarg added to `LlmClient.complete()` is optional and defaults to `None`. Existing callers in `extraction.py` and `handlers.py` are unaffected.
- **Phase 2S:** Uses the existing `complete()` signature with no changes. The `SonarProvider` is a drop-in that satisfies the existing Protocol. Zero impact on existing code. Search parameters (domain filter, recency) are passed as extra kwargs through the decorator stack — the `OpenRouterProvider` ignores unrecognized kwargs.
- **Phase 3:** New endpoint. No existing endpoint changes signature.
- **Phase 4:** New router mounted at `/mcp/`. No existing route conflicts.
- **Database:** No schema changes in any phase. All new data uses existing tables (`artifact`, `pipeline`, `claim`, `problem`, `extraction_run`).
- **No new Python dependencies** in Phase 0-2S beyond what `httpx` + `pydantic` already cover. Phase 3 may add `xai-sdk` if the SDK convenience outweighs raw HTTP (ADR required per the "no new dependency" rule). Phase 4 may add a lightweight MCP server library or use raw `starlette`/FastAPI — ADR required.

---

## 8. Post-Implementation Validation Checklist

### Phase 0
- [ ] `make check` green (new `FallbackProvider` + tests + settings)
- [ ] Unit tests pass: primary-succeeds, primary-fails→fallback, both-fail propagates error
- [ ] Grok extraction quality documented (≥3 Greek documents compared against Mistral Large baseline)
- [ ] Cost per extraction recorded (xAI direct vs. OpenRouter fallback)
- [ ] Latency recorded (xAI direct vs. OpenRouter fallback)
- [ ] Fallback trigger verified (kill xAI connectivity, extraction succeeds via OpenRouter)
- [ ] Fallback event logged at WARNING with model names and error reason
- [ ] Decision documented in PROGRESS.md: proceed to Phase 1 or stop

### Phase 1
- [ ] Analyst workflow document exists at `docs/analyst_workflow.md`
- [ ] 2-week trial completed
- [ ] ≥3 unique problems/week discovered (quantified)
- [ ] Signal-to-noise ratio documented
- [ ] Golden fixture file exists with ≥5 hand-verified entries
- [ ] Decision documented: proceed to Phase 2 or stop

### Phase 2
- [ ] ADR-012 accepted and committed
- [ ] `make check` green (`ruff` + `mypy` + `import-linter` + `filesize` + `pytest` + `alembic check`)
- [ ] `make test-golden` includes social golden tests and passes
- [ ] `make test-contract` includes xAI contract test and passes
- [ ] Social source appears in `GET /api/sources` response
- [ ] `POST /artifacts/ingest?kind=social` creates pipeline rows
- [ ] Social artifacts advance through pipeline to DONE
- [ ] BudgetGuard enforces social-search sub-limit
- [ ] No file exceeds 400 lines
- [ ] L1/L2 audit: no natural-person data extracted from social posts into claims

### Phase 2S
- [ ] ADR-012s accepted and committed
- [ ] `make check` green (`ruff` + `mypy` + `import-linter` + `filesize` + `pytest` + `alembic check`)
- [ ] `make test-golden` includes sonar golden tests and passes
- [ ] `make test-contract` includes sonar contract test and passes
- [ ] Sonar source appears in `GET /api/sources` response
- [ ] `POST /artifacts/ingest?kind=sonar_web` discovers ≥3 unique URLs from Greek domains
- [ ] Sonar artifacts advance through pipeline to DONE
- [ ] `BudgetGuard` enforces spend limits on Sonar API calls
- [ ] No file exceeds 400 lines

### Phase 3
- [ ] ADR-013 accepted and committed
- [ ] `make check` green
- [ ] `uv run topos-cli export --all` produces valid NDJSON
- [ ] Export passes L1 audit (no natural-person data in exported fields)
- [ ] `POST /api/analyst/ask` returns a cited, grounded answer
- [ ] BudgetGuard applies to analyst queries
- [ ] No file exceeds 400 lines

### Phase 4
- [ ] ADR-014 accepted and committed
- [ ] `make check` green
- [ ] MCP server responds to `initialize` and `tools/list` JSON-RPC methods
- [ ] Grok successfully connects to MCP server (tested via xAI Playground)
- [ ] Each of the 5 tools returns correct data against seeded test fixtures
- [ ] L1 audit: no tool response contains natural-person data
- [ ] Telemetry records MCP tool invocations in `extraction_run`
- [ ] BudgetGuard applies to MCP-related LLM usage
- [ ] `make test-contract` includes MCP contract test and passes
- [ ] No file exceeds 400 lines
- [ ] Caddy reverse-proxy config updated for `/mcp/` route

---

## Appendix A: Files Changed Summary

| Phase | New files | Modified files |
|---|---|---|
| 0 | `adapters/llm/fallback.py` | `config.py`, `adapters/llm/__init__.py`, `tests/unit/test_llm_stack.py`, `.env` |
| 1 | `docs/analyst_workflow.md`, `tests/golden/social/fixtures.json`, `tests/golden/sonar/fixtures.json` | `docs/PROGRESS.md` |
| 2 | `adapters/llm/xai.py`, `adapters/sources/social.py`, `tests/unit/test_social_plugin.py`, `tests/golden/social/fixtures.json`, `tests/golden/test_social_golden.py`, `docs/adr/ADR-012-x-search.md` | `service/ports.py`, `adapters/llm/cache.py`, `adapters/sources/__init__.py`, `.importlinter`, `interfaces/cli/seed_cmd.py` |
| 2S | `adapters/llm/sonar.py`, `adapters/sources/sonar_web.py`, `tests/unit/test_sonar_plugin.py`, `tests/golden/sonar/fixtures.json`, `tests/golden/test_sonar_golden.py`, `docs/adr/ADR-012s-sonar.md` | `adapters/sources/__init__.py`, `.importlinter`, `interfaces/cli/seed_cmd.py` |
| 3 | `service/analyst.py`, `interfaces/http/analyst.py`, `interfaces/cli/export_cmd.py`, `tests/unit/test_analyst.py`, `docs/adr/ADR-013-analyst-qa.md` | `adapters/llm/xai.py` |
| 4 | `interfaces/mcp/__init__.py`, `interfaces/mcp/tools.py`, `interfaces/mcp/auth.py`, `tests/unit/test_mcp_tools.py`, `docs/adr/ADR-014-mcp-server.md` | `.importlinter`, `interfaces/http/app.py` |

## Appendix B: Key Open Questions

1. **Does xAI offer EU-hosted inference?** This determines whether xAI-direct can be the primary for citizen-data extraction (Phase 0+), or whether extraction must always route through OpenRouter with an EU-hosted model. The fallback pattern already accommodates both: if xAI-direct is not EU-hosted, set the primary to an EU-hosted endpoint (e.g., OpenRouter → Mistral) and use xAI-direct as a secondary path for non-citizen-data workloads. Contact xAI sales/check docs before Phase 0.
2. **Does Perplexity offer EU-hosted Sonar?** Same question. If neither offers EU hosting, both are restricted to public-data discovery roles.
3. **What is the xAI Responses API stability guarantee?** The Chat Completions API is stable; the Responses API (with tools) is newer. Check the xAI changelog/deprecation policy before Phase 2.
4. **Should Phase 3 use the `xai-sdk` Python package or raw HTTP?** Raw HTTP avoids a new dependency but the SDK handles collection upload, polling, and streaming more cleanly. ADR-013 should decide this.
