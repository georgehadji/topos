# ADR-019: `cache_prefix` on the `LlmClient` port

## Status

Accepted

## Context

`extraction.py`'s prompt carries 388 static tokens ahead of the chunk text on
every extraction call; `adapters/sentiment`'s carries 159 ahead of every
sentiment call. Provider-side prompt caching (Anthropic, Google Vertex,
Azure, Bedrock, DeepSeek, Moonshot, Qwen — all passed through by OpenRouter)
discounts a repeated prefix by ~90% at Anthropic, ~50% at OpenAI-compatible
vendors, but only if the caller marks which part of the prompt is the
repeated prefix. `LlmClient.complete(prompt: str, ...)` took one flat string,
so nothing could be marked.

Two blockers, both real and separable:

1. **Model.** `llm_model` defaults to `mistralai/mistral-large-2512`.
   OpenRouter caching does not cover Mistral. Marking a prefix on a Mistral
   call has no effect either way.
2. **Port shape.** Fixed by this ADR.

## Decision

- `service/ports.py`: `LlmClient.complete` gains an optional
  `cache_prefix: str | None = None`.
- `adapters/llm/provider.py` (`OpenRouterProvider`): a pure helper,
  `_content_for(prompt, cache_prefix)`, builds the OpenAI-compatible message
  `content`. Without a prefix it is the original plain string. With one, it
  is a content-parts array — `[{"type": "text", "text": cache_prefix,
  "cache_control": {"type": "ephemeral"}}, {"type": "text", "text": prompt}]`
  — the same shape Anthropic's own API uses for cache marking, forwarded
  as-is by OpenRouter. A provider that does not understand `cache_control`
  still reads the same two parts concatenated in order, so the effective
  prompt text is unchanged.
- `adapters/llm/cache.py`: `cache_prefix` is folded into the cache key
  alongside `prompt`/`model`/`format`/`tools`, since it is now part of the
  effective request.
- Every other layer (`Retry`, `BudgetGuard`, `Telemetry`, `FallbackProvider`,
  `StructuredLlmWrapper`) already forwards unrecognised keyword arguments
  through `**kwargs`, so `cache_prefix` passes through them unchanged with no
  edit required.
- `service/extraction.py` and `adapters/sentiment/__init__.py`: each prompt
  template is split into a static preamble, passed as `cache_prefix`, and a
  per-call suffix (chunk text / numbered texts), passed as `prompt`. The
  concatenation is unchanged from the single-string template that preceded
  it — this is a routing change, not a wording change.

Sequenced as a port change only: **no model changes in this ADR.**
`llm_model` stays on Mistral, which OpenRouter does not cache, so
`cache_prefix` currently makes `_content_for` build the array form but caches
nothing — a no-op in practice until a cache-capable model is selected
(`docs/PHASE6_TOKEN_PLAN.md` #6.4's own sequencing note: land the port change
first, review the model change separately).

## Consequences

- No caller is forced to pass `cache_prefix`; every existing call site
  (`adapters/sources/sonar_web.py`, direct `llm_client.complete()` calls
  elsewhere) is unaffected.
- Once `llm_model` moves to a cache-capable model (ADR-020, not yet written),
  the same code path starts producing real savings with no further change to
  `extraction.py` or `adapters/sentiment`.
- `XaiProvider`'s Responses API has a different request shape (`input`, not
  `messages`) and is not used for extraction or sentiment; `cache_prefix`
  reaching it via `**kwargs` is silently unused, which is correct — there is
  nothing to cache in a tool-calling search call.

## Alternatives considered

- **A `CacheableLlmClient` subtype / second protocol.** Rejected — a boolean
  capability on one method beats a parallel class hierarchy for a difference
  this small (mirrors the "capability flag on the adapter" pattern already
  used for `FallbackProvider`).
- **Land the model change in the same PR.** Rejected per the plan's own
  sequencing: the port change and the model change are independent claims
  and should be reviewable (and revertable) independently.
