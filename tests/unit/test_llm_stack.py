"""Unit tests for LlmClient decorator stack and StructuredLlmWrapper.

Tests logic without a real OpenRouter API (using mock provider and mock pool).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from topos.adapters.llm import StructuredLlmWrapper
from topos.adapters.llm.budget import BudgetExceeded, BudgetGuard
from topos.adapters.llm.cache import Cache


class DummyProvider:
    def __init__(self, response: dict[str, Any]) -> None:
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
        return self.response


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
