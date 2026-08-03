# ADR-013 — Cross-encoder rerank via OpenRouter, not a pgvector rerank stage

- **Status:** Accepted
- **Date:** 2026-08-03
- **Supersedes:** the pgvector rerank stage implied by ADR-010
- **Adds dependency:** none (httpx already in use)

## Context

ARCHITECTURE.md > Search specifies the retrieval pipeline:

> Lexical first pass (high recall on Greek proper nouns and administrative IDs)
> -> vector rerank -> optional graph expansion -> RRF fusion.

Only the lexical pass (`adapters/db/search_repo.py`, Greek FTS + trigram) was
ever built. Results were ordered by raw `ts_rank` — a bag-of-words score with
no notion of semantic relevance.

The vector rerank stage implied by ADR-010 ("embeddings exist only for the
derived layer — problems, summaries, claim values, ~800k vectors") had
matching schema (`problem_vec`, migration 001_core.py, HNSW index on
`halfvec(1024)`) but was never implemented: no embedding generation, no
writer, no reader, anywhere in the codebase. It has been dead schema since
the table was created.

## Decision

Rerank via a hosted cross-encoder (OpenRouter's `/api/v1/rerank` endpoint)
instead of building the embedding pipeline `problem_vec` was designed for.

`SearchRepo.search()` (adapters/db/search_repo.py): when a text query and a
reranker are present, over-fetch `max(offset+limit, rerank_candidates)`
lexical hits, send `(query, [snippet, ...])` to the reranker in one call,
reorder by the returned relevance scores, then slice the requested page.
Fails open — any rerank error returns lexical order, matching the tolerance
already established for the LLM decorator stack (BudgetGuard/Retry/Cache).

Model default: `voyageai/rerank-2.5-lite` ($0.02/M tokens, ~$0.00025/search
at 50 candidates), falling back to `nvidia/llama-nemotron-rerank-vl-1b-v2:free`.
Configurable via `TOPOS_RERANK_MODELS` (ordered, comma-separated).

## Alternatives considered

**Build the pgvector pipeline as originally planned.** Rejected: requires an
embedding model, a batch/incremental embedding job for every problem update,
a re-embed migration whenever the model changes, and the HNSW index — all to
reproduce what a hosted cross-encoder does in one HTTP call. Cross-encoders
that jointly encode query and document also generally outrank cosine
similarity over independently-embedded vectors (bi-encoders) for this kind
of top-K reordering task, which is the actual reason ADR-010's "vector
rerank" line exists.

**Cohere's per-search-priced tiers** (`rerank-4-fast` at $0.002/search,
`rerank-4-pro` at $0.0025/search). Considered as the default; rejected only
because token pricing is cheaper at the candidate counts this project
operates at (dozens, not thousands, of documents per search). Both are wired
as selectable alternatives — `TOPOS_RERANK_MODELS` accepts either family.

**No reranking; keep raw `ts_rank`.** Rejected — this was the status quo
being fixed. `ts_rank` cannot express "these two problems mean the same
thing in different words," which is exactly the failure mode Greek FTS over
free-text government prose runs into.

## Consequences

- Search quality now depends on a third-party API being reachable. Fail-open
  makes that a quality degradation, not an outage — verified in
  `tests/unit/test_search.py` (reranker unset) and expected behavior on any
  rerank exception (`SearchRepo._rerank`'s try/except).
- `problem_vec` (migration 001_core.py) is now formally dead — this ADR
  records the supersession. The table and its HNSW index are left in place;
  dropping them is a separate, smaller decision.
- One more external dependency in the critical path of search, with its own
  cost line. `topos-cli search "..." --json` and `GET /api/search` both
  accept `rerank=false` for anyone who wants pure lexical ranking with zero
  external calls.
