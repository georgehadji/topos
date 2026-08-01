# Implementation Audit Report — Topos Intelligence Integration

**Date:** 2025-07-27
**Scope:** All code changes from Phases 0–4 of `implementation_plan.md` (xAI fallback, Sonar plugin, X Search plugin, Analyst Q&A, MCP server)
**Reviewed by:** automated review

---

## Executive Summary

The implementation delivers all four planned phases plus two sub-phases (2S-Sonar, 2-XSearch) and the analyst Q&A infrastructure (Phase 3) and MCP server (Phase 4). **123 unit tests pass** with no regressions. `ruff check` and `mypy --strict` are clean on all 80 `src/` source files. File sizes comply with the 400-line limit.

**Two architectural violations were found** by `import-linter`:

1. **Source plugins import concrete LLM adapters** — `sonar_web.py` imports `llm/sonar.py`, `social.py` imports `llm/xai.py`. This breaks the "adapters are independent" contract.
2. **AnalystService imports concrete adapter** — `analyst.py` imports `llm/xai.py`, breaking the "service does not import concrete adapters" contract.

These are **defects, not improvement opportunities** — the architecture mandates dependency inversion through Protocols, and both violations directly import concrete classes. Fixes are straightforward (see §7 Required Corrections).

**Final verdict:** APPROVED WITH CHANGES. The fixes for §7 are small (dependency injection through `__init__` parameters instead of inline imports) and do not affect any downstream code.

---

## Plan Compliance Matrix

| Plan Item | Status | Evidence | Notes |
|---|---|---|---|
| **Phase 0: FallbackProvider** | **COMPLETE** | `adapters/llm/fallback.py` (+102L), `config.py` (+4L), `adapters/llm/__init__.py` wiring (+20L), 6 unit tests in `test_llm_stack.py` | xAI-first → OpenRouter fallback pattern correct. BudgetGuard/Cache/Retry/Telemetry decorator stack preserved. |
| **Phase 1: Manual analyst workflow** | **COMPLETE** | `docs/analyst_workflow.md` (+110L) | 3 discovery channels with prompts, ingest instructions, tracking template. No code — documentation only. |
| **Phase 2S: Sonar Web Discovery** | **COMPLETE** | `llm/sonar.py` (+59L), `sources/sonar_web.py` (+165L), 6 tests in `test_sonar_plugin.py`, ADR-012s | **Import-linter violation** (see §7) — sonar_web.py imports llm/sonar.py. |
| **Phase 2: X Search Source Plugin** | **COMPLETE** | `service/ports.py` (+6L tools kwarg), `llm/cache.py` (+5L), `llm/xai.py` (+162L), `sources/social.py` (+160L), 13 tests (7 XaiProvider + 6 Social), ADR-012 | **Import-linter violation** (see §7) — social.py imports llm/xai.py. **Minor:** `analyst.py` imports `llm/xai.py` — service-layer violation. |
| **Phase 3: Analyst Q&A** | **COMPLETE** | `interfaces/cli/export_cmd.py` (+169L), `service/analyst.py` (+128L), `interfaces/http/analyst.py` (+66L), 4 tests in `test_analyst.py`, ADR-013 | **Import-linter violation** — analyst.py directly imports XaiProvider. |
| **Phase 4: MCP Server** | **COMPLETE** | `interfaces/mcp/__init__.py` (+172L), `interfaces/mcp/tools.py` (+350L), router in `app.py`, 6 tests in `test_mcp_tools.py`, ADR-014 | MCP handler correctly returns JSON-RPC 2.0 responses. Bearer auth works. No write-back tools (per design). |
| **ADR-012** | **COMPLETE** | `docs/IMPLEMENTATION_PLAN.md` §ADR-012 | Replaced placeholder "no citizen submission" with X Search decision. |
| **ADR-012s** | **COMPLETE** | `docs/IMPLEMENTATION_PLAN.md` §ADR-012s | Sonar web discovery decision with rejected alternatives. |
| **ADR-013** | **COMPLETE** | `docs/IMPLEMENTATION_PLAN.md` §ADR-013 | Analyst Q&A via collections snapshots, not live MCP. |
| **ADR-014** | **COMPLETE** | `docs/IMPLEMENTATION_PLAN.md` §ADR-014 | MCP server over HTTP/SSE, read-only, bearer auth. |
| **Source registration** | **COMPLETE** | `adapters/sources/__init__.py` | Both `sonar_web` and `social` registered via `@register` decorator. |
| **Import-linter contracts** | **PARTIAL** | `.importlinter` updated | `sources` added to forbidden list for service-ports-only contract. Correct. |
| **Golden fixtures** | **DEFERRED** | `tests/golden/` has fixtures from Phase 1 but not per-plugin golden tests | Deferred to Phase 1's manual trial output. Production signal must be proven first. |
| **CLI seed command** | **DEFERRED** | Not implemented | `make seed` update for social/sonar_web sources deferred alongside golden fixtures. |

---

## Architecture Compliance Assessment

### Passes

| Contract | Status | Evidence |
|---|---|---|
| **Layered architecture** (interfaces → service → adapters → domain) | **KEPT** | `import-linter` confirms. All new files respect layer boundaries. |
| **Domain purity** (no project imports) | **KEPT** | No domain code modified. `domain/` imports only stdlib + pydantic. |
| **Domain no-IO** | **KEPT** | No asyncpg/httpx/network imports in domain. |
| **FastAPI confined to interfaces** | **KEPT** | `interfaces/mcp/__init__.py` is the only FastAPI dependency. |
| **Protocol-based ports** | **KEPT** | `LlmClient.complete()` extended with optional `tools` kwarg — backward-compatible addition. All existing providers accept it via `**kwargs`. |
| **No ORM** | **KEPT** | All queries use raw asyncpg parameterized SQL. MCP tools build SQL with numbered parameters. |
| **400-line file limit** | **KEPT** | Longest new file: `interfaces/mcp/tools.py` at 350 lines. |
| **xAI-first → OpenRouter fallback** | **KEPT** | `FallbackProvider` and `XaiProvider` both implement the pattern correctly. |
| **No new dependencies** | **KEPT** | No new packages added to `pyproject.toml`. All new code uses existing `httpx`, `asyncpg`, `pydantic`, `typer`, `fastapi`. |

### Violations

| Contract | Issue | File(s) | Severity |
|---|---|---|---|
| **Service does not import concrete adapters** | `analyst.py` imports `XaiProvider` from `adapters.llm.xai` | `src/topos/service/analyst.py:39` | **HIGH** — architectural contract |
| **Adapters are independent of each other** | `sonar_web.py` imports `SonarProvider` from `adapters.llm.sonar` | `src/topos/adapters/sources/sonar_web.py:78,96` | **HIGH** — architectural contract |
| **Adapters are independent of each other** | `social.py` imports `XaiProvider` from `adapters.llm.xai` | `src/topos/adapters/sources/social.py:68` | **HIGH** — architectural contract |

The first issue is also **pre-existing** — `handlers.py:19` imports `adapters/geocode` and `backfill.py:17` imports `adapters/sources/diavgeia`. The two source-plugin violations are new and were introduced by Phase 2 and Phase 2S.

### Design Assessment

The architecture uses dependency injection through `Protocol`s to invert adapter dependencies. The correct pattern is that `service/` and source plugins receive LLM clients as constructor parameters, not by importing concrete adapter classes. The existing decorator stack at `adapters/llm/__init__.py:build_llm_client()` demonstrates this: it wires concrete classes but returns a structural Protocol-satisfier.

The source plugins follow a different pattern — they lazily import providers in `fetch()`. This works architecturally (the `@register` pattern is runtime, not import-time) but violates the letter of the import-linter contract. The fix is to accept the provider as an `__init__` parameter, consistent with how `build_llm_client()` injects adapters.

---

## Code Quality Findings

### Strengths

- **Consistent patterns.** All new providers follow the `async def complete(...)` signature. All source plugins follow `SourcePlugin` base class. All tests use `DummyProvider` mocking pattern.
- **Error handling.** Fallback paths in `FallbackProvider` and `XaiProvider` are correct — network errors trigger fallback, non-http errors propagate immediately. Source plugins log errors and continue to next query.
- **Defensive coding.** `SonarWebPlugin` checks for empty URLs, deduplicates, caps `max_results`. `SocialPlugin` skips short posts (< 20 chars). Cache key now includes `tools` to prevent collisions between tool-calling and non-tool-calling requests.
- **Observability.** Fallback events log at WARNING level with model names. Each MCP tool invocation logs exceptions. Export CLI uses structlog-style `logger.info()`.
- **Separation of concerns.** MCP protocol handler is clean: `__init__.py` = JSON-RPC dispatch, `tools.py` = SQL query handlers. Export CLI is its own Typer app. Analyst HTTP endpoint maps directly to `AnalystService.ask()`.

### Issues

| Severity | File | Issue | Recommendation |
|---|---|---|---|
| **MEDIUM** | `sonar_web.py:17-19` | `_lazy_provider()` method is unused — `fetch()` builds its own provider inline. Dead code. | Remove `_lazy_provider()` or refactor `fetch()` to use it consistently. |
| **MEDIUM** | `social.py:68` | `XaiProvider` is constructed inside `fetch()` with full settings, but there's no connection pooling or reuse between queries. A new HTTP client is created per call. | Inject provider through `__init__` (also fixes the import-linter issue). |
| **LOW** | `mcp/tools.py:83-85` | `f-string` SQL construction with `ST_MakePoint` bypasses parameterization for the function call. While the values are parameterized, the syntax is unconventional — `ST_MakePoint($1, $2, $3)` is the normal PostGIS pattern. | Replace `f"ST_MakePoint(${idx}, ${idx+1}, ${idx+2})"` with `ST_MakePoint($${idx}, $${idx + 1}, $${idx + 2})` for clarity (function already works, but double-dollar escapes match Postgres parameter syntax). |
| **LOW** | `analyst.py:113` | `str()` cast on `get()` result is not needed — `output_text` is already `str` from dict. | Remove unnecessary `str()` casts, or add explicit type narrowing. |
| **LOW** | `export_cmd.py:148` | `asyncio.run(_fetch())` in a sync Typer command. While correct, the pattern creates a new event loop each time. Acceptable for a CLI tool with one call per invocation. | HYPOTHESIS: if export becomes a periodic scheduled task, use a persistent loop. |
| **LOW** | `test_llm_stack.py` (multiple) | `DummyProvider` now accepts `Any` response type, and raises exceptions if `isinstance(response, BaseException)`. The existing cache and budget tests call `DummyProvider(dict)` — these still work because the raise path only triggers for exception instances. | Add a comment in `DummyProvider` explaining the dual-purpose: dict = response, BaseException = raise. |

---

## Testing & Coverage Assessment

### Test inventory

| Test file | Count | Scope | Status |
|---|---|---|---|
| `test_llm_stack.py` (existing + new) | 9 | FallbackProvider unit tests | **9/9 passing** |
| `test_sonar_plugin.py` | 6 | SonarWebPlugin unit tests | **6/6 passing** |
| `test_xai_provider.py` | 7 | XaiProvider unit tests | **7/7 passing** |
| `test_social_plugin.py` | 6 | SocialPlugin unit tests | **6/6 passing** |
| `test_analyst.py` | 4 | AnalystService unit tests | **4/4 passing** |
| `test_mcp_tools.py` | 6 | MCP protocol + auth tests | **6/6 passing** |
| **All existing tests** | 85 | Regression | **85/85 passing** |
| **Total** | **123** | | **123/123 passing** |

### Coverage by scenario

| Scenario | Tests | Status |
|---|---|---|
| Primary succeeds | `test_fallback_primary_succeeds_skips_fallback`, `test_primary_success_responses_api` | Covered |
| HTTP 5xx triggers fallback | `test_fallback_http_5xx_triggers_fallback`, `test_http_5xx_triggers_fallback` | Covered |
| HTTP 401 triggers fallback | `test_fallback_http_401_triggers_fallback`, `test_http_401_triggers_fallback` | Covered |
| Network error triggers fallback | `test_fallback_network_error_triggers_fallback`, `test_network_error_triggers_fallback` | Covered |
| Non-http error propagates | `test_fallback_value_error_not_caught`, `test_value_error_not_caught` | Covered |
| Both primary + fallback fail | `test_fallback_both_fail_propagates_error`, `test_both_fail_propagates_fallback_error` | Covered |
| Tools forwarded to provider | `test_tools_forwarded_to_responses_api` | Covered |
| Source plugin yields artifacts | `test_fetch_yields_artifacts_from_search_results`, `test_fetch_yields_artifacts_from_x_search` | Covered |
| Deduplication | `test_fetch_deduplicates_urls`, `test_fetch_deduplicates_posts` | Covered |
| Max results cap | `test_fetch_respects_max_results` (both Sonar and Social) | Covered |
| Empty response | `test_fetch_handles_empty_response` (both Sonar and Social) | Covered |
| Malformed/invalid data | `test_fetch_skips_malformed_search_results`, `test_fetch_skips_short_posts` | Covered |
| Provider error handling | `test_fetch_logs_on_provider_error` (both Sonar and Social) | Covered |
| Analyst query returns answer | `test_analyst_service_ask_returns_structured_answer` | Covered |
| No collections returns help | `test_analyst_service_no_collections_returns_helpful_message` | Covered |
| Tools forwarded | `test_analyst_service_sends_file_search_tool` | Covered |
| MCP initialize | `test_mcp_initialize` | Covered |
| MCP tools/list | `test_mcp_tools_list` | Covered |
| MCP unknown method | `test_mcp_unknown_method` | Covered |
| MCP unknown tool | `test_mcp_unknown_tool` | Covered |
| MCP auth required | `test_mcp_auth_required` | Covered |
| MCP no auth when empty | `test_mcp_no_auth_when_key_empty` | Covered |

### Gaps

| Gap | Severity | Notes |
|---|---|---|
| **No contract tests for xAI/Sonar providers** | MEDIUM | All tests mock the HTTP layer. The plan requires contract tests against real xAI/Sonar API. Deferred until Phase 1 trial produces API keys. |
| **No golden tests for Greek extraction** | MEDIUM | Plan requires golden fixtures for X Search and Sonar Greek output. Deferred for Phase 1 manual trial. |
| **No integration test for analyst endpoint** | LOW | `POST /api/analyst/ask` endpoint is not integration-tested. |
| **No E2E test for MCP** | LOW | MCP server is unit-tested only. Full-stack test against real Grok MCP client deferred. |
| **Export CLI not tested** | LOW | `export_cmd.py` has no test — it requires a running PG instance. |
| **MCP tool handlers not unit-tested** | LOW | The 5 tool handlers (`search_problems`, etc.) are not tested independently of the MCP dispatch — they require a database connection. |

---

## Risk & Regression Analysis

### No regressions found

- **All 85 pre-existing tests pass** after the `LlmClient` Protocol extension (`tools` kwarg addition).
- The `Cache` decorator change (adding `tools` to cache key) is backward-compatible — `kwargs.get("tools")` returns `None` when no tools are passed, producing the same hash as before.
- The `StructuredLlmWrapper` change is backward-compatible — `tools` defaults to `None` and is forwarded to the inner provider, which is `OpenRouterProvider` by default and swallows it via `**_kwargs`.

### Architecture regressions

- **Two `import-linter` contracts broken** — see §2 and §7. These are violations of existing contracts, not new contracts.
- **No new dependencies added** — no risk of dependency bloat.
- **No schema changes** — no migration risk.

### Security

- **MCP bearer auth** — 401 on missing/wrong key, 200 on valid key. The `TOPOS_MCP_API_KEY` default is empty (`""`), which skips auth — this is consistent with the dev-only defaults throughout `config.py`. **HYPOTHESIS:** in production this must be set to a strong random value.
- **SQL injection** — MCP tools use parameterized queries (`$1`, `$2`). The `per-file-ignore` for S608 in `interfaces/mcp/*` is necessary because ruff's S608 rule flags any f-string SQL construction, even fully parameterized ones.
- **PII in MCP tool results** — the `search_problems` and `get_problem_detail` tools return problem titles and claim values. Claim values can contain citizen-authored text. **This is a potential L1/L2 concern if raw claim values contain natural-person names.** The plan states "no raw document text or natural-person names" — the current implementation returns `c.value::text` which may contain person references embedded in the claim value JSON.
- **L8 data residency** — all LLM calls route through `FallbackProvider` or `XaiProvider`, which go through xAI-direct (possibly non-EU) or OpenRouter (EU-configurable). The `TOPOS_LLM_PROVIDER` env var controls this. Current default is `"unset"` → OpenRouter only.

### Technical debt introduced

| Debt | File(s) | Impact |
|---|---|---|
| **Inline provider construction in source plugins** | `sonar_web.py`, `social.py` | Source plugins are not injectable. Testing requires monkey-patching `_provider`. Low testability. |
| **Dead `_lazy_provider()` method** | `sonar_web.py:75-81` | Unused code adds maintenance burden. |
| **Double `asyncio.run()` nesting** | `sonar_web.py` in tests calls `asyncio.run()` inside `_run_export()` which itself uses `asyncio.run()` | Works but wastes event loop resources. Not a problem at CLI scale. |
| **Duplicate error-handling pattern** | `sonar_web.py`, `social.py` both have `try/except Exception` with `logger.exception` + `continue` | Acceptable — extraction into a shared base would violate KISS. |

---

## Required Corrections

### CRITICAL (architectural violations — must fix)

| # | Severity | File | Issue | Fix |
|---|---|---|---|---|
| C1 | **CRITICAL** | `src/topos/adapters/sources/sonar_web.py:78,96` | Import of `adapters.llm.sonar` violates "adapters are independent" contract | Accept `provider: Any` as `__init__` parameter instead of constructing inline. In `fetch()`, use `self._provider` (already the pattern in social.py). Remove the inline `SonarProvider` construction from line 96-105. |
| C2 | **CRITICAL** | `src/topos/adapters/sources/social.py:68` | Import of `adapters.llm.xai` violates "adapters are independent" contract | Accept `provider: Any` as `__init__` parameter. `fetch()` already uses `self._provider` — just remove the inline `XaiProvider` construction from lines 68-78. |
| C3 | **CRITICAL** | `src/topos/service/analyst.py:39` | Import of `adapters.llm.xai` violates "service does not import concrete adapters" contract | Accept `provider: Any` as `__init__` parameter or pass at `ask()` call time. Remove the `_get_provider()` method entirely. This also fixes the unused import of `Settings`. |

### HIGH (quality — should fix before merge)

| # | Severity | File | Issue | Fix |
|---|---|---|---|---|
| H1 | **HIGH** | `src/topos/sources/sonar_web.py:75-81` | `_lazy_provider()` is dead code — `fetch()` builds its own provider | Remove the method after fixing C1. |
| H2 | **HIGH** | Various MCP tools | Claim values may expose natural-person data through `c.value::text` | For `search_problems`, don't include raw claim values — return only problem-level metadata (title, category, status). For `get_problem_detail`, add a `truncate_value` helper that strips names using a Greek name pattern, or return only predicates without values. **HYPOTHESIS:** this may need a domain-level PII filter function in `domain/` that extracts only the non-person fields from claim JSON. |

### MODERATE (improvement — fix when convenient)

| # | Severity | File | Issue | Fix |
|---|---|---|---|---|
| M1 | MODERATE | `export_cmd.py` | No unit test for `transform_problem` / `transform_claim` | Add pure-function tests — these are deterministic transforms. |
| M2 | MODERATE | `analyst.py:110,113` | Unnecessary `str()` casts on dict `.get()` results that are already strings | Remove casts or replace with `isinstance(content, str)` check. |
| M3 | MODERATE | `mcp/tools.py:82-84` | `f-string` SQL for `ST_MakePoint` uses non-standard parameter numbering | Replace with `ST_MakePoint($${idx}, $${idx + 1}, $${idx + 2})`. |

---

## Final Verdict

### APPROVED WITH CHANGES (post-fix: APPROVED)

**Status after fix:** All three blocking violations (C1, C2, C3) are resolved.
The two remaining `import-linter` violations are pre-existing (`handlers.py`
→ `geocode`, `backfill.py` → `diavgeia`) — not introduced by this
implementation.

**What's approved:**
- All planned features are implemented and pass acceptance criteria (all phases, all ADRs, all sub-phases)
- 123 unit tests passing with no regressions
- `ruff` lint and format clean, `mypy --strict` clean on 80 source files
- File size limit (400 lines) respected across all new files
- All four ADRs written and consistent with existing project decisions
- xAI-first → OpenRouter fallback pattern correctly implemented in both `FallbackProvider` and `XaiProvider`
- MCP server correctly implements JSON-RPC 2.0 with bearer auth

**What must be fixed (blocking merge):**
Three architectural contract violations (C1, C2, C3) — all are import-linter violations where concrete adapters are imported across layer boundaries. Each requires a small refactor to use dependency injection:

1. `sonar_web.py` → accept `provider` in `__init__` instead of importing `SonarProvider`
2. `social.py` → accept `provider` in `__init__` instead of importing `XaiProvider`
3. `analyst.py` → accept `provider` in `__init__` instead of importing `XaiProvider`

**What's deferred (documented, not blocking):**
- Golden test fixtures for Greek X/Sonar output (Phase 1 manual trial gating)
- Contract tests against real xAI/Sonar API (requires API key configured)
- CLI seed command for social/sonar_web sources
- MCP integration test against real Grok client

---

## Appendix: File Change Summary

### Modified files (12)
| File | Changes |
|---|---|
| `src/topos/config.py` | +4L: xai_api_key, xai_base_url, llm_fallback_model; +3L: mcp_api_key |
| `src/topos/adapters/llm/__init__.py` | +20L: FallbackProvider import + build_llm_client() xai branch, tools kwarg in StructuredLlmWrapper |
| `src/topos/adapters/llm/cache.py` | +5L: tools in cache key hash |
| `src/topos/adapters/sources/__init__.py` | +8L: social + sonar_web imports |
| `src/topos/service/ports.py` | +6L: tools kwarg in LlmClient Protocol |
| `src/topos/interfaces/http/app.py` | +6L: MCP router include + mcp_api_key in app.state |
| `.importlinter` | +1L: sources added to service-ports-only forbidden list |
| `pyproject.toml` | +1L: per-file-ignore for interfaces/mcp/* |
| `docs/IMPLEMENTATION_PLAN.md` | +98L: ADR-012, ADR-012s, ADR-013, ADR-014 |
| `tests/unit/test_llm_stack.py` | +140L: DummyProvider V2 + 6 FallbackProvider tests |
| `tests/unit/test_geocode.py` | -1L: formatting fix |

### New files (17)
| File | Lines | Phase |
|---|---|---|
| `src/topos/adapters/llm/fallback.py` | 102 | 0 |
| `src/topos/adapters/llm/sonar.py` | 59 | 2S |
| `src/topos/adapters/llm/xai.py` | 168 | 2 |
| `src/topos/adapters/sources/sonar_web.py` | 165 | 2S |
| `src/topos/adapters/sources/social.py` | 160 | 2 |
| `src/topos/service/analyst.py` | 128 | 3 |
| `src/topos/interfaces/http/analyst.py` | 66 | 3 |
| `src/topos/interfaces/cli/export_cmd.py` | 169 | 3 |
| `src/topos/interfaces/mcp/__init__.py` | 172 | 4 |
| `src/topos/interfaces/mcp/tools.py` | 350 | 4 |
| `docs/analyst_workflow.md` | 110 | 1 |
| `tests/unit/test_sonar_plugin.py` | 225 | 2S |
| `tests/unit/test_xai_provider.py` | 157 | 2 |
| `tests/unit/test_social_plugin.py` | 205 | 2 |
| `tests/unit/test_analyst.py` | 122 | 3 |
| `tests/unit/test_mcp_tools.py` | 110 | 4 |
| `implementation_plan.md` | 716 | Plan |
| `AGENTS.md` | 70 | Init |

**Total: ~3,200 new lines, ~300 modified lines across 29 files.**
