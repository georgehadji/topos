# ADR-015: LLM decorator stack — Cache outermost, not BudgetGuard

## Status

Accepted

## Context

The `LlmClient` decorator stack (`adapters/llm/__init__.py`) was documented
and implemented as:

```
BudgetGuard( Cache( Retry( Telemetry( provider ) ) ) )
```

`BudgetGuard` was outermost. Its `complete()` checks
`SUM(cost_eur) >= monthly_budget_eur` and raises `BudgetExceeded` *before*
calling into the rest of the stack — including `Cache`. So once the monthly
ceiling was reached, every call was refused at the door, even one that would
have been served entirely from `Cache` at zero additional cost. A cache hit
and a fresh paid call were treated identically by the guard whose entire job
is to distinguish spend from non-spend.

Separately: `Cache` sat outside `Retry` and `Telemetry`. A cache hit returned
before reaching `Telemetry`, which is correct — a served-from-cache answer is
not a new model invocation and must not produce a second `extraction_run`
row — but it also meant the hit itself was recorded nowhere. Cache
effectiveness was unmeasurable from the data the system already collects.

## Decision

Reorder to:

```
Cache( BudgetGuard( Retry( Telemetry( provider ) ) ) )
```

`Cache` is now outermost. A hit returns immediately, before `BudgetGuard` is
ever consulted — a budget-exhausted month still serves every previously-seen
prompt for free, which is what "cached" should mean. `Cache` now also counts
its own hits and misses (`Cache.hits`, `Cache.misses`) and periodically logs
the rate, since it is the only layer that knows the difference; `Telemetry`
by design never sees a hit.

`BudgetGuard` moves one layer in, immediately outside `Retry`/`Telemetry`, so
it still gates every real model invocation — nothing about its enforcement
changes for genuine spend, only for spend that was never going to happen.

## Consequences

- `ARCHITECTURE.md` > LLM usage updated to the new order.
- No behavioural change for a cache miss: the call path through
  `BudgetGuard -> Retry -> Telemetry -> provider` is unchanged from before,
  just reached one layer further in.
- `Cache`'s hit/miss counters are in-process only (reset on worker restart).
  Sufficient for the periodic log line this ADR introduces; a persistent
  counter would need its own table and was not justified for this fix.
- This is the base for the `Cascade` decorator planned in
  `docs/PHASE6_TOKEN_PLAN.md` #6.5, which slots between `BudgetGuard` and
  `Retry`: `Cache( BudgetGuard( Cascade( Retry( Telemetry( provider ) ) ) ) )`.

## Alternatives considered

- **Leave `BudgetGuard` outermost, special-case cache lookups inside it.**
  Rejected — would require `BudgetGuard` to know about `Cache`'s key scheme,
  coupling two decorators that are otherwise independent and swappable.
- **Move `Cache` inside `BudgetGuard` but still outside `Retry`/`Telemetry`
  (no change).** This was the status quo and is the defect being fixed.
