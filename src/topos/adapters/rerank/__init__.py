"""OpenRouter reranking adapter — cross-encoder search rerank.

ARCHITECTURE.md > Search specifies "lexical first pass -> vector rerank ->
graph expansion -> RRF fusion". This implements the rerank stage via
OpenRouter's hosted rerank endpoint rather than a pgvector embedding
pipeline over the derived layer — see docs/adr/ADR-013 for why.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class OpenRouterReranker:
    """Reranks documents against a query via OpenRouter's rerank endpoint.

    Tries each model in *models* in order, first one that responds wins —
    same shape as the xAI-first/OpenRouter-fallback pattern elsewhere in
    adapters/llm, generalised to an ordered list rather than a pair.

    Every failure mode (bad key, timeout, all models down) is a raised
    exception, deliberately not swallowed here — the caller
    (adapters/db/search_repo.py) decides to fail open to lexical order.
    Swallowing here would hide a fully-broken rerank config as silent no-op.
    """

    def __init__(self, *, api_key: str, base_url: str, models: list[str]) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._models = models

    async def __call__(
        self, query: str, documents: list[str], *, top_n: int
    ) -> list[tuple[int, float]]:
        """Return (original_index, relevance_score) pairs, best first."""
        if not documents:
            return []

        last_exc: Exception | None = None
        for model in self._models:
            try:
                return await self._rerank_with(model, query, documents, top_n)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "rerank model %s failed (%s), trying next", model, type(exc).__name__
                )

        raise RuntimeError(f"all rerank models failed: {last_exc}") from last_exc

    async def _rerank_with(
        self, model: str, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/rerank",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://topos.local",
                    "X-Title": "Topos",
                },
                json={
                    "model": model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return [(int(r["index"]), float(r["relevance_score"])) for r in data.get("results", [])]
