"""Unit tests: OpenRouter reranking adapter.

Mocks the internal HTTP call, same convention as test_xai_provider.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from topos.adapters.rerank import OpenRouterReranker


@pytest.mark.asyncio
async def test_empty_documents_short_circuits() -> None:
    reranker = OpenRouterReranker(api_key="k", base_url="https://x", models=["m1"])
    assert await reranker("query", [], top_n=10) == []


@pytest.mark.asyncio
async def test_returns_index_score_pairs_from_first_model() -> None:
    reranker = OpenRouterReranker(api_key="k", base_url="https://x", models=["m1", "m2"])

    async def fake_rerank_with(model: str, query: str, documents: list[str], top_n: int) -> Any:
        assert model == "m1"
        return [(1, 0.9), (0, 0.2)]

    reranker._rerank_with = fake_rerank_with  # type: ignore[method-assign]

    result = await reranker("query", ["doc a", "doc b"], top_n=2)
    assert result == [(1, 0.9), (0, 0.2)]


@pytest.mark.asyncio
async def test_falls_through_to_next_model_on_failure() -> None:
    reranker = OpenRouterReranker(api_key="k", base_url="https://x", models=["broken", "good"])
    attempted: list[str] = []

    async def fake_rerank_with(model: str, query: str, documents: list[str], top_n: int) -> Any:
        attempted.append(model)
        if model == "broken":
            raise RuntimeError("503 from vendor")
        return [(0, 0.5)]

    reranker._rerank_with = fake_rerank_with  # type: ignore[method-assign]

    result = await reranker("query", ["doc"], top_n=1)
    assert attempted == ["broken", "good"]
    assert result == [(0, 0.5)]


@pytest.mark.asyncio
async def test_raises_when_every_model_fails() -> None:
    reranker = OpenRouterReranker(api_key="k", base_url="https://x", models=["m1", "m2"])

    async def always_fails(model: str, query: str, documents: list[str], top_n: int) -> Any:
        raise RuntimeError(f"{model} down")

    reranker._rerank_with = always_fails  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="all rerank models failed"):
        await reranker("query", ["doc"], top_n=1)
