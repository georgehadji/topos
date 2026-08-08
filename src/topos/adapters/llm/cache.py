"""Cache decorator: deduplicates LLM calls keyed on prompt + model hash.

Cache the response so identical extraction tasks on the same document
(e.g. during backfill reruns) do not re-invoke the API.

A hit must never reach Telemetry: it wrote a real extraction_run row for
every call, including cache hits, which meant "a model was invoked" and "an
answer was returned from cache" were indistinguishable in the ledger — and
made the hit rate itself unmeasurable, since a hit and a miss produced the
same row shape. Cache sits outside Telemetry in the stack precisely so a hit
returns before Telemetry is ever reached; the counters below are this
module's own record of what the wrapped stack was spared.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class Cache:
    """Wraps a provider and caches responses keyed on sha256(prompt + model)."""

    def __init__(self, inner: Any, pool: asyncpg.Pool | None = None) -> None:
        self._inner = inner
        self._pool = pool
        self._memory: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        response_format: dict[str, Any] | None = None,
        cache_prefix: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "prompt": prompt,
                    "model": model,
                    "format": response_format,
                    "tools": kwargs.get("tools"),
                    "cache_prefix": cache_prefix,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

        if cache_key in self._memory:
            self.hits += 1
            return self._memory[cache_key]

        if self._pool is not None:
            cached = await self._fetch_from_db(cache_key)
            if cached is not None:
                self._memory[cache_key] = cached
                self.hits += 1
                return cached

        self.misses += 1
        result = await self._inner.complete(
            prompt=prompt,
            model=model,
            response_format=response_format,
            cache_prefix=cache_prefix,
            **kwargs,
        )

        self._memory[cache_key] = result
        if self._pool is not None:
            await self._store_in_db(cache_key, result)

        total = self.hits + self.misses
        if total % 20 == 0:
            logger.info(
                "llm_cache.rate hits=%d misses=%d rate=%.2f",
                self.hits,
                self.misses,
                self.hits / total,
            )

        return result  # type: ignore[no-any-return]

    async def _fetch_from_db(self, key: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchrow("SELECT response FROM llm_cache WHERE cache_key = $1", key)
        if row is None:
            return None
        val = row["response"]
        if not isinstance(val, dict):
            return None
        return dict(val)

    async def _store_in_db(self, key: str, response: dict[str, Any]) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                """
                INSERT INTO llm_cache (cache_key, response, created_at)
                VALUES ($1, $2::jsonb, now())
                ON CONFLICT (cache_key) DO NOTHING
                """,
                key,
                json.dumps(response),
            )
