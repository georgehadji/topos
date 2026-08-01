# ADR-011 — Approval state lives on `problem`, not in a separate table

- **Status:** Accepted
- **Date:** 2026-08-01
- **Migration:** `alembic/versions/005_recommendation_approval.py`

## Context

The recommendation workflow is implemented end to end — `domain/recommendations.py`
defines `Recommendation` with `approved_by` / `approved_at` / `exported_at`,
`service/recommendations.py` selects and updates those fields, and both
`interfaces/http/recommendations.py` and the GraphQL schema expose them.

None of those columns existed. `001_core` created `problem` without them, and no
later migration added them. The result: `GET /api/recommendations` returned HTTP
500 (`UndefinedColumnError: column p.approved_by does not exist`), and
approve / reject / export were unreachable. The feature was dead on arrival.

## Decision

Add three nullable columns to `problem`:

| Column | Type | Meaning |
|---|---|---|
| `approved_by` | `text` | Actor who signed off. NULL = not approved. |
| `approved_at` | `timestamptz` | When sign-off happened. |
| `exported_at` | `timestamptz` | When the package was exported. NULL = not exported. |

Plus a partial index on `approved_at WHERE approved_at IS NOT NULL`, because the
export queue only ever scans approved rows.

## Alternatives considered

**A separate `recommendation` table keyed by `problem_id`.** Rejected: a
recommendation is not an entity with its own lifecycle here — it is a *view* of a
scored problem plus who signed it off. A 1:1 side table would need a join on every
read and could drift out of sync with `problem.status`, which already carries
`candidate` / `tracked`. The code as written also assumes these live on `problem`;
a side table would mean rewriting four modules to fix a missing-migration bug.

**Derive approval from `audit_log`.** Rejected: `audit_log` is an append-only
record of what happened, not queryable current state. Reconstructing "is this
approved right now" would mean an aggregate over the log on every list request.

## Consequences

- `problem` gains mutable columns. This is consistent with existing practice —
  `status`, `geom` and `version` are already updated in place. The immutability
  guarantee in ARCHITECTURE.md applies to `artifact` and `claim`, and to the
  append-only `problem_event`; it has never applied to `problem` itself.
- Approval history is *not* captured by these columns — only the latest state.
  The durable history remains `audit_log` + `problem_event`.
- Reversible: `downgrade()` drops the index and the three columns.
