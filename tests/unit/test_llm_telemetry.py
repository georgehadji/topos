"""Unit tests: Telemetry decorator's cost computation (ADR-014).

Confirms cost_eur is actually threaded from domain/pricing into the
extraction_run INSERT — the earlier defect was that the literal 0 was
hardcoded there regardless of what pricing said.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.adapters.llm.telemetry import Telemetry
from topos.domain.types import ArtifactId

_ARTIFACT_ID = ArtifactId(uuid.UUID("00000000-0000-0000-0000-000000000001"))


class _Provider:
    def __init__(self, usage: dict[str, int] | None) -> None:
        self._usage = usage

    async def complete(self, *, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"choices": [{"message": {"content": "ok"}}]}
        if self._usage is not None:
            result["usage"] = self._usage
        return result


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    return pool, conn


@pytest.mark.asyncio
async def test_known_model_writes_a_real_cost() -> None:
    pool, conn = _pool()
    telemetry = Telemetry(
        _Provider({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}), pool=pool
    )

    await telemetry.complete(
        prompt="p",
        model="mistralai/mistral-large-2512",
        artifact_id=_ARTIFACT_ID,
    )

    args = conn.execute.call_args.args
    cost = args[6]  # positional: id, artifact_id, prompt_ver, model, started, cost_eur, ...
    assert cost == Decimal("6.960000")


@pytest.mark.asyncio
async def test_unknown_model_writes_null_not_zero() -> None:
    """The regression this whole change exists to prevent: an unpriced call
    must not be indistinguishable from a genuinely free one."""
    pool, conn = _pool()
    telemetry = Telemetry(_Provider({"prompt_tokens": 100, "completion_tokens": 100}), pool=pool)

    await telemetry.complete(
        prompt="p",
        model="some-unlisted-model",
        artifact_id=_ARTIFACT_ID,
    )

    cost = conn.execute.call_args.args[6]
    assert cost is None


@pytest.mark.asyncio
async def test_missing_usage_writes_null_cost() -> None:
    pool, conn = _pool()
    telemetry = Telemetry(_Provider(None), pool=pool)

    await telemetry.complete(
        prompt="p",
        model="mistralai/mistral-large-2512",
        artifact_id=_ARTIFACT_ID,
    )

    assert conn.execute.call_args.args[6] is None
