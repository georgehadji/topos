"""Telemetry decorator: records every LLM call as an extraction_run row.

Inner decorator in the stack: Telemetry(provider). Writes to the database
after each completion so every model invocation is auditable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from topos.domain.types import ArtifactId


class Telemetry:
    """Wraps a provider and records every call in extraction_run."""

    def __init__(self, inner: Any, pool: asyncpg.Pool | None = None) -> None:
        self._inner = inner
        self._pool = pool

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        response_format: dict[str, Any] | None = None,
        artifact_id: ArtifactId | None = None,
        prompt_ver: str = "0.0.0",
        **kwargs: Any,
    ) -> dict[str, Any]:
        started = datetime.now(UTC)
        ok = True
        result: dict[str, Any] | None = None
        try:
            result = await self._inner.complete(
                prompt=prompt, model=model, response_format=response_format, **kwargs
            )
            return result
        except Exception:
            ok = False
            raise
        finally:
            await self._record(
                artifact_id=artifact_id,
                prompt_ver=prompt_ver,
                model=model,
                started=started,
                ok=ok,
                result=result,
            )

    async def _record(
        self,
        *,
        artifact_id: ArtifactId | None,
        prompt_ver: str,
        model: str,
        started: datetime,
        ok: bool,
        result: dict[str, Any] | None,
    ) -> None:
        if self._pool is None:
            return

        if artifact_id is None:
            # extraction_run.artifact_id is NOT NULL and references artifact(id),
            # so a call with no artifact cannot be recorded here. That is the
            # normal case for discovery calls (Sonar, X Search), which search the
            # web rather than process a stored document. Inserting anyway raised
            # NotNullViolationError inside the decorator stack and took down every
            # real LLM call — the mock bypassed the stack, so it stayed hidden.
            return

        tokens_in: int | None = None
        tokens_out: int | None = None
        if result is not None:
            usage = result.get("usage", {})
            if isinstance(usage, dict):
                tokens_in = usage.get("prompt_tokens")
                tokens_out = usage.get("completion_tokens")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO extraction_run
                  (id, artifact_id, prompt_ver, model, params, started_at, cost_eur,
                   tokens_in, tokens_out, ok)
                VALUES ($1, $2, $3, $4, '{}', $5, 0, $6, $7, $8)
                """,
                uuid.uuid4(),
                artifact_id,
                prompt_ver,
                model,
                started,
                tokens_in,
                tokens_out,
                ok,
            )
