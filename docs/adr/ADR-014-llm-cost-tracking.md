# ADR-014: LLM cost tracking — priced vs. free must be distinguishable

## Status

Accepted

## Context

`Telemetry._record` (`adapters/llm/telemetry.py`) has, since the decorator
stack was written, inserted the literal `0` into `extraction_run.cost_eur` on
every call:

```sql
INSERT INTO extraction_run
  (id, artifact_id, prompt_ver, model, params, started_at, cost_eur, ...)
VALUES ($1, $2, $3, $4, '{}', $5, 0, ...)
```

Two consequences, both silent:

- `topos-cli cost` (`SUM(cost_eur)` over the month) has always reported €0.
- `BudgetGuard` (`adapters/llm/budget.py`) checks
  `SUM(cost_eur) >= monthly_budget_eur` before every call. With every row at
  `0`, the configured €250/month ceiling has never been capable of firing.

`tokens_in`/`tokens_out` were already recorded correctly — pricing was the
only missing input.

## Decision

1. Add `domain/pricing.py`: a pure `cost_eur(model, tokens_in, tokens_out) ->
   Decimal | None`, backed by an explicit per-model USD-per-million-token
   table (same shape and rationale as `domain/severity.py`: a table someone
   edits deliberately, versioned, not a formula). Converted to EUR at a fixed
   documented rate, not a live FX call.
2. **Unknown model or missing token counts returns `None`, not `0`.** Pricing
   the call at zero would assert "this was free," which is a stronger and
   false claim than "this project does not yet know the price." That
   distinction is the entire point of this change — collapsing it back to `0`
   reproduces the original defect under a different name.
3. Migration `009_nullable_cost_eur`: `extraction_run.cost_eur` changes from
   `NOT NULL DEFAULT 0` to nullable, no default. `SUM()` in Postgres ignores
   `NULL`, so `BudgetGuard`'s check now correctly excludes unpriced calls from
   the ceiling rather than counting them as free spend.

## Consequences

- `BudgetGuard`'s ceiling becomes load-bearing for every priced model. It
  remains inert for any model without a price-table entry — adding a new
  model to `config.py` without a matching entry in `domain/pricing.py`
  silently leaves that model's spend outside the budget check. This is a
  known gap, not a fixed one: the table must be maintained alongside the
  model list.
- Sonar's per-request web-search surcharge ($6–14 per 1000 requests) is not
  token-denominated and `Telemetry` only has token counts. It is not modelled.
  `cost_eur` for Sonar calls is therefore a floor on the true cost, not the
  full bill.
- The FX rate is a fixed constant, captured 2026-08-05, not a live lookup.
  Acceptable for a €250/month budget check; revisit if the budget or the
  currency-sensitivity of decisions made from `topos-cli cost` grows.

## Alternatives considered

- **Keep `cost_eur` `NOT NULL`, default unpriced calls to `0`.** Rejected —
  this is the status quo defect, not a fix.
- **Live FX rate via an external API.** Rejected for now: adds a network
  dependency and a failure mode (rate unavailable) to a code path that must
  not block extraction, for precision this project's budget does not need.
