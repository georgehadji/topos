"""Unit tests for LlmClient decorator stack and StructuredLlmWrapper.

Tests logic without a real OpenRouter API (using mock provider and mock pool).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from topos.adapters.llm import StructuredLlmWrapper
from topos.adapters.llm.budget import BudgetExceeded, BudgetGuard
from topos.adapters.llm.cache import Cache
from topos.adapters.llm.fallback import FallbackProvider


class DummyProvider:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls = 0

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response  # type: ignore[no-any-return]


class SampleModel(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_structured_llm_wrapper_parses_json_schema() -> None:
    raw_response = {"choices": [{"message": {"content": '{"answer": "validated-hello"}'}}]}
    provider = DummyProvider(raw_response)
    wrapper = StructuredLlmWrapper(provider)

    # Without schema: returns raw dict
    res_raw = await wrapper.complete(prompt="Hi", model="test-model")
    assert res_raw == raw_response
    assert provider.calls == 1

    # With schema: returns Pydantic model instance
    res_schema = await wrapper.complete(prompt="Hi", model="test-model", schema=SampleModel)
    assert isinstance(res_schema, SampleModel)
    assert res_schema.answer == "validated-hello"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_budget_guard_limit_checked() -> None:
    provider = DummyProvider({"choices": []})

    # Create a mock of BudgetGuard that always has some spent
    guard = BudgetGuard(provider, pool=None, monthly_budget_eur=10.0)

    # Spy/mock the _spent_this_month to exceed budget
    async def mock_spent() -> float:
        return 15.0

    guard._spent_this_month = mock_spent  # type: ignore[method-assign]

    # We must provide a mock pool so that spent check is triggered
    guard._pool = object()

    with pytest.raises(BudgetExceeded):
        await guard.complete(prompt="Hi", model="test-model")


@pytest.mark.asyncio
async def test_cache_hits_memory() -> None:
    provider = DummyProvider({"choices": [{"message": {"content": "response-1"}}]})
    cache = Cache(provider, pool=None)

    # First call: misses memory cache, calls provider
    res1 = await cache.complete(prompt="Hi", model="test-model")
    assert provider.calls == 1

    # Second call: hits memory cache, does not call provider
    res2 = await cache.complete(prompt="Hi", model="test-model")
    assert provider.calls == 1
    assert res1 == res2


# ── FallbackProvider tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_primary_succeeds_skips_fallback() -> None:
    """When the primary succeeds, fallback is never called."""
    primary = DummyProvider({"choices": [{"message": {"content": "primary-ok"}}]})
    fallback = DummyProvider({"choices": [{"message": {"content": "fallback-ok"}}]})

    provider = FallbackProvider(
        primary=primary,
        fallback=fallback,
        primary_model="grok-4.5",
        fallback_model="x-ai/grok-4.5",
    )
    result = await provider.complete(prompt="Test", model="ignored")
    assert primary.calls == 1
    assert fallback.calls == 0
    assert result["choices"][0]["message"]["content"] == "primary-ok"


@pytest.mark.asyncio
async def test_fallback_http_5xx_triggers_fallback() -> None:
    """When primary raises HTTP 503, fallback returns its answer."""
    primary = DummyProvider(
        httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=httpx.Request("POST", "https://primary.test"),
            response=httpx.Response(503),
        )
    )
    fallback = DummyProvider({"choices": [{"message": {"content": "fallback-ok"}}]})

    provider = FallbackProvider(
        primary=primary,
        fallback=fallback,
        primary_model="grok-4.5",
        fallback_model="x-ai/grok-4.5",
    )
    result = await provider.complete(prompt="Test", model="ignored")
    assert primary.calls == 1
    assert fallback.calls == 1
    assert result["choices"][0]["message"]["content"] == "fallback-ok"


@pytest.mark.asyncio
async def test_fallback_http_401_triggers_fallback() -> None:
    """Auth errors (401) on primary trigger fallback."""
    primary = DummyProvider(
        httpx.HTTPStatusError(
            "401 Unauthorized",
            request=httpx.Request("POST", "https://primary.test"),
            response=httpx.Response(401),
        )
    )
    fallback = DummyProvider({"choices": [{"message": {"content": "fallback-auth"}}]})

    provider = FallbackProvider(
        primary=primary,
        fallback=fallback,
        primary_model="grok-4.5",
        fallback_model="x-ai/grok-4.5",
    )
    result = await provider.complete(prompt="Test", model="ignored")
    assert fallback.calls == 1
    assert result["choices"][0]["message"]["content"] == "fallback-auth"


@pytest.mark.asyncio
async def test_fallback_both_fail_propagates_error() -> None:
    """When both primary and fallback fail, the fallback error propagates."""
    primary = DummyProvider(
        httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=httpx.Request("POST", "https://primary.test"),
            response=httpx.Response(503),
        )
    )
    fallback = DummyProvider(
        httpx.HTTPStatusError(
            "502 Bad Gateway",
            request=httpx.Request("POST", "https://fallback.test"),
            response=httpx.Response(502),
        )
    )

    provider = FallbackProvider(
        primary=primary,
        fallback=fallback,
        primary_model="grok-4.5",
        fallback_model="x-ai/grok-4.5",
    )
    with pytest.raises(httpx.HTTPStatusError, match="502"):
        await provider.complete(prompt="Test", model="ignored")
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_fallback_network_error_triggers_fallback() -> None:
    """ConnectError on primary triggers fallback."""
    primary = DummyProvider(httpx.ConnectError("Connection refused"))
    fallback = DummyProvider({"choices": [{"message": {"content": "fallback-net"}}]})

    provider = FallbackProvider(
        primary=primary,
        fallback=fallback,
        primary_model="grok-4.5",
        fallback_model="x-ai/grok-4.5",
    )
    result = await provider.complete(prompt="Test", model="ignored")
    assert fallback.calls == 1
    assert result["choices"][0]["message"]["content"] == "fallback-net"


@pytest.mark.asyncio
async def test_fallback_value_error_not_caught() -> None:
    """Non-network, non-HTTP errors on primary propagate immediately (no fallback)."""
    primary = DummyProvider(ValueError("bad input"))
    fallback = DummyProvider({"choices": [{"message": {"content": "should-not-run"}}]})

    provider = FallbackProvider(
        primary=primary,
        fallback=fallback,
        primary_model="grok-4.5",
        fallback_model="x-ai/grok-4.5",
    )
    with pytest.raises(ValueError, match="bad input"):
        await provider.complete(prompt="Test", model="ignored")
    assert fallback.calls == 0  # fallback never called
