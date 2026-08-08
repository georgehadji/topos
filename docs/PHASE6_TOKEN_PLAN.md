# Phase 6 — Token cost reduction

Implementation plan for the findings in the token-consumption research.
Written against the existing architecture; no new layer, no new dependency.

---

## 1. The architecture already has the right pattern

`adapters/llm/__init__.py` assembles cross-cutting LLM concerns as a
**Decorator** chain over a provider:

```
BudgetGuard( Cache( Retry( Telemetry( provider ) ) ) )
```

Every concern in this plan is either another link in that chain, a **policy
object** consulted before the chain is entered, or a pure function in
`domain/`. Nothing here needs a new abstraction — and that constraint is
useful, because it forces each optimisation to declare exactly where in the
call path it acts.

Paradigm is unchanged: **functional core, imperative shell**. Pricing,
gating decisions and near-duplicate detection are pure functions in
`domain/`; the decorators are the shell that applies them.

### 1.1 Fix the chain order first

The current order has two defects that only show up under load:

| Boundary | Problem today |
|---|---|
| `BudgetGuard` outside `Cache` | A cache hit costs nothing, but is refused once the month's budget is exhausted. The system stops serving free answers. |
| `Cache` outside `Telemetry` | A cache hit never reaches `Telemetry`, so hit rate is invisible. Cache effectiveness cannot be measured. |

Target order:

```
Cache( BudgetGuard( Cascade( Retry( Telemetry( provider ) ) ) ) )
```

Justification per boundary, outermost first:

- **Cache** — free results served without consulting budget, retry or logging.
- **BudgetGuard** — gates only real spend.
- **Cascade** (new) — chooses the model; may call inward more than once.
- **Retry** — transient failures, per model attempt.
- **Telemetry** — records every real attempt, innermost, where `usage` exists.

Cache hit/miss is emitted as a counter from `Cache` itself, not by moving it
inward: a hit must not write an `extraction_run` row, because that table means
"a model was invoked".

---

## 2. Work items

### 6.1 — Compute `cost_eur` *(prerequisite for everything)*

`Telemetry._record` inserts the literal `0` into `cost_eur`. Therefore
`topos-cli cost` always reports €0 and `BudgetGuard._spent_this_month` always
returns 0 — the configured €250 ceiling has never been able to fire.
`tokens_in`/`tokens_out` *are* recorded, so the only missing piece is price.

- **New:** `domain/pricing.py` — pure.
  `cost_eur(model: str, tokens_in: int, tokens_out: int, cached_in: int = 0) -> Decimal`
  backed by a versioned per-model rate table, same shape and rationale as
  `domain/severity.py`: a table someone must deliberately edit, not constants
  scattered through adapters.
- **Change:** `Telemetry._record` calls it.
- **Pattern:** **policy object** (data-only Strategy). Unknown model returns
  `None`, and the row records NULL rather than 0 — an unpriced call must not
  look free, which is the same failure this item is fixing.
- **Test:** a known model and token count produce a known cost; an unknown
  model yields NULL, not zero.

Do this first. Every item below is justified by numbers this produces, and
none of them can be evaluated without it.

### 6.2 — Skip the LLM for out-of-area documents *(largest structural win)*

`is_out_of_area` already exists, is pure, and costs nothing — but runs in
`persist_extraction`, **after** the extraction call is paid for. Of 19
problems, 5 were out-of-area: roughly a quarter of extraction spend bought
rows that were then discarded.

- **New:** `domain/gate.py` — pure.
  `should_extract(text: str) -> ExtractionDecision` where the result carries a
  boolean and a *reason*.
- **Change:** `handlers.handle_chunked` consults it before `extract_artifact`;
  on refusal the artifact advances with a logged reason and no LLM call.
- **Pattern:** **Specification**. Returning a reason rather than a bare bool is
  the point — a silently skipped document is indistinguishable from a document
  that yielded nothing, and this project has already been bitten by exactly
  that ambiguity.
- **Risk to measure, not assume:** the gate sees the whole document, where the
  filter previously saw one claim. Full text is likelier to contain a
  home-term, so the veto fires more often and the gate is *more* conservative —
  but that must be shown, not asserted. Extend `tests/golden/greek_cases.json`
  with document-length inputs before enabling.
- **Ordering:** keep the existing post-extraction filter. Belt and braces cost
  nothing at that layer, and the gate is the optimisation, not the correctness
  boundary.

### 6.3 — Near-duplicate gate *(same insertion point)*

The same story arrives via `news`, `sonar_web` and `websearch`. `backfill`
dedups on exact `sha256`; near-identical copies each pay for extraction, and
ER merges them only afterwards.

- **New:** `domain/simhash.py` — pure `simhash(text) -> int`,
  `hamming(a, b) -> int`.
- **Change:** the same gate in 6.2 also refuses a document within N bits of one
  already extracted, reusing the earlier extraction's claims.
- **Pattern:** same **Specification**, second rule. One insertion point, two
  reasons — not two gates.
- **`ponytail:`** comment required: the lookup is a linear scan of recent
  hashes. Fine at 10², wrong at 10⁶; upgrade path is a BK-tree or an index.

### 6.4 — Prompt caching *(needs a port change and a model change)*

388 static tokens precede every extraction call; 159 precede every sentiment
call. Provider-side caching discounts those ~90% at Anthropic, ~50% at OpenAI,
passed through by OpenRouter.

Two blockers, both real:

1. **Model.** OpenRouter caching covers Anthropic, Google Vertex, Azure,
   Bedrock, DeepSeek, Moonshot and Qwen. It does **not** cover Mistral, and
   `llm_model` defaults to `mistralai/mistral-large-2512`.
2. **Port shape.** `LlmClient.complete(prompt: str, ...)` is a flat string.
   Marking a cacheable prefix needs the prefix to be a distinct part.

- **Change:** `service/ports.py` — add optional `cache_prefix: str | None` to
  `LlmClient.complete`. Providers that support caching send it as a separate
  cached block; providers that do not simply concatenate. Backwards compatible,
  and no caller is forced to change.
- **Change:** `extraction.py` / `adapters/sentiment` pass their static preamble
  as `cache_prefix` instead of interpolating it into one string.
- **Pattern:** **capability flag on the adapter**, not a subclass hierarchy.
  One boolean beats a parallel class tree for a difference this small.
- **Sequencing:** land the port change first — it is a no-op until a
  cache-capable model is selected, so the two can be reviewed separately.

### 6.5 — Model cascade *(now safe, because golden fixtures exist)*

`mistral-large` is a premium tier for a mechanical extraction task. A cascade
tries a cheap model and escalates only on a parse failure or a low-confidence
result.

- **New:** `adapters/llm/cascade.py` — `Cascade` decorator, positioned as in
  §1.1.
- **Config:** `llm_cascade_models` — comma-separated, cheapest first. Mirrors
  the existing `rerank_models` convention exactly.
- **Pattern:** **Chain of Responsibility**. Each link handles the request or
  passes it on; the escalation predicate is a pure function so it can be tested
  without a model.
- **Precondition:** the golden fixtures from Phase 5 are what make this
  evaluable. Without them, "the cheap model is good enough" is an opinion.
  Add an extraction-level golden case before enabling.

### 6.6 — Batch API *(deferred, and why)*

OpenAI Batch and Anthropic Message Batches are 50% off and stack with caching
(≈25% of standard). Backfill is inherently asynchronous, so it fits.

**Not scheduled.** It changes the call shape from request/response to
submit-and-poll, which means a queue table, a drain command and a second code
path through the worker — a large change whose saving is 50% of a bill that is
currently unmeasured. Revisit after 6.1 produces a real monthly figure and if
that figure justifies it.

Recorded here so the option is not rediscovered from scratch.

### 6.7 — Chunking *(investigate before optimising)*

`handle_textified` writes the entire document as a single chunk regardless of
size. Two consequences worth confirming against the largest stored artifact:

- a long PDF becomes one very large call, and may exceed the model's context;
- there is no way to skip the irrelevant 90% of a long procedural document.

Real chunking would let 6.2's gate act per chunk rather than per document,
which is where the remaining savings on council minutes live. Measure first —
this is a hypothesis, not a finding.

---

## 3. Sequencing

| Phase | Items | Gate to the next |
|---|---|---|
| A | 6.1 cost, cache hit-rate counter, fix chain order | a real €/month figure exists — **DONE** |
| B | 6.2 out-of-area gate, 6.3 near-dup | measured call-count drop — **DONE**, 2/18 docs (11.1%) on the current corpus, see docs/PROGRESS.md > Measurements |
| C | 6.4 port change → cache-capable model evaluation | golden fixtures still green — **DONE** |
| D | 6.5 cascade | golden fixtures still green — **DONE**, `adapters/llm/cascade.py`; disabled by default (`llm_cascade_models` empty) until a cheap-model quality comparison exists |
| — | 6.6 batch, 6.7 chunking | only if A's numbers justify |

A must come first and is not optional. Every later item is a claim about
saving money; without 6.1 none of those claims can be checked, and this
codebase has already shipped four defects that passed their unit tests and
failed against real data.

### Definition of done, per item

1. `make check` green — ruff, mypy strict, 6/6 import-linter contracts, ≤400 lines.
2. Pure logic has literal-input unit tests; Greek behaviour has a golden case.
3. **A before/after token count from `extraction_run`**, not an estimate.
4. Skips and cache hits are logged with a reason. Nothing is silently dropped.

---

## 4. ADRs owed

| ADR | Subject | Status |
|---|---|---|
| 019 | `cache_prefix` on the `LlmClient` port | **Written** |
| 020 | Model family change away from Mistral, if 6.4 proceeds | **Not yet** — `llm_model` is still `mistralai/mistral-large-2512`; only the port change landed, no model was actually switched, so there is no decision yet to record |
| 021 | Decorator chain ordering and its invariants | **Written** — covers the chain as of Cascade (#6.5) landing |
