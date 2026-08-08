# ADR-021: LLM decorator chain — final order and its invariants

## Status

Accepted

## Context

ADR-015 fixed the ordering defect (`BudgetGuard` outside `Cache`) and, in its
Consequences section, named where a future `Cascade` decorator (Phase 6 #6.5)
would slot in without needing another reorder: between `BudgetGuard` and
`Retry`. That slot is no longer speculative — `adapters/llm/cascade.py` now
exists and `build_llm_client()` inserts it there when `llm_cascade_models` is
configured. This ADR records the chain as it now actually is, and states the
invariant each boundary depends on, so a future addition has the same
one-question test ADR-015 used ("what does this layer need to see, and what
must never reach it") instead of re-deriving it from scratch.

## Decision

```
Cache( BudgetGuard( [Cascade( )] Retry( Telemetry( provider ) ) ) )
```

`Cascade` is bracketed because it is conditional — present only when
`llm_cascade_models` is non-empty, absent otherwise (see ADR at
`docs/PHASE6_TOKEN_PLAN.md` #6.5 for why it defaults off). The chain with
`Cascade` absent is exactly ADR-015's order; nothing about that order changed.

Per-layer invariant, outermost first:

- **Cache** — must see every call before anything else does, including a
  budget-exhausted one. Its hit/miss counters are the only place cache
  effectiveness is observable (ADR-015).
- **BudgetGuard** — must see the model actually about to be billed, which
  means it sits outside `Cascade`: it gates the cascade as one spend
  decision, not per-attempt. If `BudgetGuard` were inside `Cascade`, a
  budget-exhausted month could still burn spend on the first two attempts of
  a three-model cascade before refusing the third.
- **Cascade** — must see each model's *raw* response to judge
  `should_escalate`, and must sit outside `Retry` so a transient failure on
  the cheap model retries on that same model before Cascade gives up on it
  and pays for a pricier one. Owns model selection while present: the
  `model` a caller passes is ignored, same as `rerank_models` overrides a
  caller's per-call choice.
- **Retry** — per-model-attempt transient-failure handling; unaware cascade
  exists above it.
- **Telemetry** — innermost, unconditionally records every real attempt
  (`usage` only exists post-call). A three-attempt cascade writes three
  `extraction_run` rows, one per model tried — this is deliberate: the
  point of measuring is to see what the cascade actually cost, not to
  collapse it back into a single-call illusion.

## Consequences

- A cascade of N models is N `extraction_run` rows when every attempt
  escalates, one when the first attempt succeeds. `docs/PROGRESS.md` >
  Measurements should read this as "calls", not "documents", once cascade is
  enabled — the two stop being the same number.
- Any future decorator answers two questions before it's given a slot:
  what does it need to see (raw response? validated claims? cost?), and what
  must never reach the layers inside it (budget-exhausted refusals must
  never reach Telemetry as a spend; a cache hit must never reach Cascade).
- `ARCHITECTURE.md` > LLM usage should be updated to show the bracketed
  `Cascade` slot alongside the ADR-015 order.

## Alternatives considered

- **Cascade outside BudgetGuard.** Rejected — the whole point of a budget
  ceiling is per-month spend, and letting every cascade attempt bypass it
  individually defeats that.
- **Cascade inside Retry (nested per-model retry-then-escalate).** Rejected —
  conflates two different failure modes (transient network error vs. the
  model producing a bad-but-valid answer) into one decorator, which was
  exactly the kind of coupling ADR-015's "leave BudgetGuard outermost,
  special-case Cache inside it" alternative was rejected for.
