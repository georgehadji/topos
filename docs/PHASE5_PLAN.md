# Phase 5 — Product plan

Everything outstanding: the additions, the optimisations, the fixes. Written
against the architecture that exists, not a redesign of it.

Legal/compliance design (GDPR Art. 9 on political opinion data) is **excluded
at the owner's instruction** and is not addressed anywhere below. It is a
prerequisite for deployment, not for implementation.

---

## 1. Paradigm

The codebase already uses **functional core, imperative shell**, and the
correct decision is to keep it rather than introduce a second style:

- `domain/` — pure functions over frozen dataclasses. Deterministic, no `async`,
  no clock, no project imports. Enforced by `domain-purity` and `domain-no-IO`.
- `service/` — the imperative shell. Async, does IO, orchestrates.
- `adapters/` — leaves. Independent of each other.
- `interfaces/` — the only layer allowed to choose a concrete adapter.

Two rules follow for everything in this plan, and they resolve most design
questions before they get asked:

1. **If it can be a pure function over data, it goes in `domain/`.** Scoring,
   projections, aggregation, drafting structure, blocking keys — all pure.
2. **If it needs the network, a clock, or a database, it goes in `service/`
   behind a `Protocol` in `ports.py`.**

The reason this matters commercially: every number a politician is shown must
be explainable and reproducible. A pure core means any output can be
recomputed from stored inputs and audited. That is the product's actual moat,
and the paradigm is what protects it.

### Established patterns to reuse (do not invent alternatives)

| Pattern | Where it already lives | Reuse for |
|---|---|---|
| Registry + decorator | `adapters/sources/registry.py` | new sources |
| Template Method | `adapters/sources/feedbase.py` | new feed sources |
| Ports (structural `Protocol`) | `service/ports.py` | sentiment, question rendering |
| Repository | `adapters/db/*_repo.py` | new read models |
| Event sourcing | `problem_event` + `mentions.append_event` | accountability timeline |
| Policy object | `domain/severity.py` | per-tenant scoring policy |
| Strategy | `adapters/rerank`, source plugins | ER blocking, sentiment backends |

---

## 2. Work items

Ordered by dependency, not by appeal. Each names the modules it touches so the
400-line cap and the layer contracts can be checked before writing code.

### 5.1 — Purge fabricated ΔΕΔΔΗΕ rows *(fix, blocked on a running DB)*

The plugin no longer fabricates, but rows written by the old code are still in
dev and are indistinguishable from real findings by inspection alone. They are
identifiable by artifact URI: the old scheme was `deddhe://outage_9874` and
`deddhe://outage_9875`, both literal constants.

- **New:** `interfaces/cli/admin_cmd.py` — `topos-cli admin purge-fabricated`
- **Pattern:** none needed; a targeted delete with a printed dry-run first.
- **Must:** delete `problem` rows only via the claim → `problem_claim` join, so
  a problem corroborated by a *real* source as well is not destroyed.
- **Test:** contract test asserting a problem with one fabricated and one real
  claim survives with the fabricated claim removed.

### 5.2 — Accountability timeline *(addition — the differentiator)*

"This contract was extended in February and again in August." Nothing else on
the market does this because it needs longitudinal document tracking, which
`problem_event` already provides and nothing reads.

- **New:** `domain/timeline.py` — pure left fold:
  `project_timeline(events: Sequence[TimelineEvent]) -> Timeline`
- **New:** `service/timeline.py` — fetch events for a problem, call the fold.
- **New:** `interfaces/http/timeline.py`, MCP tool `problem_timeline`.
- **Pattern:** **read-model projection** over an event stream — a catamorphism.
  The projection must be a pure fold so a timeline can be recomputed from the
  event log at any time and never drifts from it.
- **Domain types:** `TimelineEvent(seq, kind, at, payload)` frozen;
  `Timeline(problem_id, entries, first_seen, last_seen, recurrence_count)`.
- **Note:** `problem_event.seq` is already unique per problem and gap-free via
  `append_event`, so ordering is total and needs no timestamp tiebreak.

### 5.3 — Trend, and closing the scoring DAG *(optimisation)*

`MeasuredInputs.trend` is `None` today, so `compute_urgency` runs on severity
alone. Once 5.1 has produced a history, trend becomes computable — and it is
the input that makes `urgency` mean anything.

- **New:** `domain/trend.py` — pure:
  `compute_trend(history: Sequence[ScorePoint]) -> Decimal | None`
  Returns `None` for fewer than two points. Never extrapolates.
- **Change:** `service/scoring.py` — read the last N snapshots per problem,
  pass `trend` into `MeasuredInputs`.
- **Pattern:** pure function over a time series; no new abstraction.
- **Watch:** `score_snapshot` is append-only and grows per problem per run.
  Add a retention policy in the same slice or the table becomes the largest in
  the database within weeks.

### 5.4 — ER blocking key *(optimisation — the scaling ceiling)*

`same_block` returns `True` whenever categories match, so `run_er` is O(n²)
over all candidates. Fine at n=19, untenable at n=10⁵ — and it now runs after
*every* artifact.

- **Change:** `domain/er.py` — add `block_key(mention) -> str`, a pure function
  combining category + geohash prefix + time bucket.
- **Change:** `service/er.py` — group by `block_key`, compare within groups.
- **Pattern:** **Strategy**, selected by config, so the current
  everything-matches behaviour stays available for small corpora and tests.
- **Test:** property test that any pair the current `same_block` accepts and
  that shares a block key is still compared — i.e. no silent recall loss.

### 5.5 — Incremental scoring *(optimisation)*

`score_all` rescoring the whole corpus after every artifact is O(n) work per
ingest, i.e. O(n²) per backfill.

- **Change:** `service/scoring.py` — accept an optional dirty set of problem
  ids; `handle_geocoded` passes the problems ER touched.
- **Pattern:** **dirty-set / incremental recomputation.** Keep the full-corpus
  path as `topos-cli admin rescore` for formula-version bumps.

### 5.6 — Parliamentary question drafts *(addition — highest willingness to pay)*

Greek ministers must answer written questions within 25 days. The span-anchored
provenance already in the database is exactly the raw material.

The split matters and is the whole reason this is safe to ship:

- **New:** `domain/question.py` — pure. Assembles a `QuestionBrief` from a
  problem, its claims, authority and citations. **Facts only, no prose.**
- **New port:** `QuestionRenderer` in `service/ports.py` — brief → Greek prose.
- **New adapter:** `adapters/question/` — LLM-backed renderer.
- **Pattern:** **Builder** for the brief; **Strategy** via the port for
  rendering. The LLM may phrase, never source: every factual token in the
  output must trace to a field in the brief, and the brief is built by pure
  code from stored claims.
- **Test:** golden fixture — a fixed brief must render to prose containing
  every citation in the brief and no numeral absent from it.

### 5.7 — Citizen-demand sources *(addition — closes the "what people want" gap)*

Every current source is institutional. They describe what the state does, not
what residents want.

- **Change:** `adapters/sources/data_gov.py` — currently yields dataset
  *metadata*. Add resource-level fetching for the complaint and defect
  registers it already surfaces, which are real citizen demand, officially
  published and aggregate.
- **New:** `adapters/sources/reviews.py` — public reviews of public facilities
  (ΚΕΠ, hospitals, schools). Aggregate signal, no profiling.
- **Pattern:** existing Registry + Template Method. No new abstraction.
- **Note:** this is the only item that changes what the product can *answer*,
  as opposed to how well it answers what it already does.

### 5.8 — Sentiment *(addition)*

Two distinct things, and conflating them is the standard mistake:

- **Coverage sentiment** — how a *problem category* or a *named public figure*
  is discussed in published media. Aggregate, from documents already ingested.
- Constituent-level opinion profiling — **out of scope for this plan.**

Design:

- **New:** `domain/sentiment.py` — pure aggregation:
  `aggregate(labels: Sequence[SentimentLabel]) -> SentimentSummary`.
  Distribution and mean, never a single scalar verdict.
- **New port:** `SentimentAnalyzer` in `service/ports.py`:
  `async def __call__(self, texts: list[str], *) -> list[SentimentLabel]`
- **New adapter:** `adapters/sentiment/` — LLM classifier, Greek-tuned prompt.
- **Pattern:** **Strategy** behind a port, mirroring `Reranker` exactly —
  including fail-open: an analyser outage degrades to "no sentiment", never to
  a neutral score, because a fabricated neutral is indistinguishable from a
  measured one.
- **Storage:** new `sentiment_snapshot` table, same append-only shape as
  `score_snapshot`, so trend works the same way.
- **Greek is the technical risk here**, not the plumbing. Ship with a golden
  set (5.9) or the numbers are unfalsifiable.

### 5.9 — Golden fixtures for Greek behaviour *(fix — the largest test gap)*

`tests/golden/` is empty while `AGENTS.md` and `ARCHITECTURE.md` both require
golden fixtures for Greek behaviour. Everything above that touches Greek text —
sentiment, question drafting, geocoding — is unfalsifiable without this.

- **New:** `tests/golden/` — frozen Greek input → expected extraction,
  geocoding, sentiment label.
- **Pattern:** approval testing. A diff is a decision to review, not a failure
  to fix by editing the expectation.
- **Minimum:** the 14 real findings already in the newsletter, hand-checked
  once, then frozen.

### 5.10 — Geocoding recall *(fix)*

8 of 14 findings had `Location: not resolved`. For a product sold on a map,
that is the most visible quality defect.

- **Change:** `adapters/geocode/` — resolver chain: curated table → OSM seed →
  fuzzy match, first hit wins, confidence decreasing along the chain.
- **Pattern:** **Chain of Responsibility**, each link pure and independently
  testable.
- **Measure first.** Add a recall metric over the golden set before changing
  the resolver, otherwise there is no way to tell an improvement from a
  regression.

---

## 3. Cross-cutting

### Per-tenant scoring policy

`domain/severity.py` is currently one global table. `domain/tenancy.py` already
anticipates multiple constituencies, and severity is a *political* judgement —
two clients will disagree about whether administrative delay outranks road
congestion.

- **Change:** `score_all` takes an injected `SeverityPolicy`; the global table
  becomes the default instance.
- **Pattern:** **Policy object** (a Strategy carrying only data). Keep it a
  frozen dataclass so a snapshot can record which policy version produced it —
  `score_snapshot.scores.severity_baseline_ver` already reserves the field.

### Stale contract documentation

`service/CONTRACT.md` states service must not import `asyncpg`. The enforced
`service-ports-only` contract forbids only `topos.adapters.*`, and
`service/er.py`, `handlers.py`, `mentions.py` and `scoring.py` all import
asyncpg today. Either the doc is wrong or the architecture intends a
`ProblemRepo` port that does not exist.

**Decide explicitly, in an ADR, before adding more service modules that take a
`Pool`** — 5.2, 5.3 and 5.8 all would. Recommendation: accept `asyncpg` in
service as the pragmatic status quo and correct the document, because
introducing repository ports for every read is a large change that buys
testability the existing mocked-pool tests already provide.

### ADRs to write

| ADR | Subject |
|---|---|
| 014 | Timeline as a pure projection over `problem_event` |
| 015 | LLM may phrase but never source (question drafting) |
| 016 | asyncpg in service — accept, or introduce repository ports |
| 017 | Sentiment scope: coverage-level only |
| 018 | `score_snapshot` retention policy |

---

## 4. Sequencing

Dependency-ordered. Each phase ends green: `make check` plus `pytest`.

| Phase | Items | Unblocks |
|---|---|---|
| A | 5.1 purge, 5.9 golden fixtures | trustworthy data + a measurable baseline |
| B | 5.10 geocoding, 5.4 blocking, 5.5 incremental | quality and scale |
| C | 5.2 timeline, 5.3 trend | the differentiating features |
| D | 5.6 questions, 5.7 citizen demand | the sellable work product |
| E | 5.8 sentiment | the requested addition, last because it depends on 5.9 |

**A before everything.** Building features on a corpus containing fabricated
outages, with no golden set to detect regression, means later measurements
cannot be trusted — the same failure mode that let the ΔΕΔΔΗΕ fabrication and
the disconnected scoring DAG survive this long.

### Definition of done, per item

1. Layer contracts kept (`make layers`) — 6/6.
2. `ruff` and `mypy --strict` clean.
3. Files ≤ 400 lines.
4. Pure logic has literal-input unit tests; Greek behaviour has a golden fixture.
5. **Verified against live data, not only mocks.** Every defect found this
   session — the fabricated outages, the dead scoring DAG, the unwired entity
   resolution, the swapped lat/lon — passed its unit tests.
