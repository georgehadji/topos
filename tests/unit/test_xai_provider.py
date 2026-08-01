"""Unit tests for XaiProvider — mock internal HTTP calls."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from topos.adapters.llm.xai import XaiProvider


@pytest.mark.asyncio
async def test_primary_success_responses_api() -> None:
    """When Responses API succeeds, result is returned."""
    provider = XaiProvider(api_key="test-key", fallback_api_key="fallback-key")

    async def fake_responses(**kw: Any) -> dict[str, Any]:
        return {"id": "resp-1", "output_text": "X search results"}

    provider._call_responses_api = fake_responses  # type: ignore[method-assign]

    result = await provider.complete(
        prompt="What problems in Thessaloniki?",
        model="grok-4.5",
        tools=[{"type": "x_search", "allowed_x_handles": ["@deddiede"]}],
    )

    assert result["id"] == "resp-1"
    assert result["output_text"] == "X search results"


@pytest.mark.asyncio
async def test_http_5xx_triggers_fallback() -> None:
    """HTTP 5xx from Responses API triggers Chat Completions fallback."""
    provider = XaiProvider(
        api_key="test-key",
        fallback_api_key="fallback-key",
    )

    async def failing_responses(**kw: Any) -> dict[str, Any]:
        raise httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
            response=httpx.Response(503),
        )

    async def fake_fallback(prompt: str) -> dict[str, Any]:
        return {"choices": [{"message": {"content": f"Fallback answer for: {prompt[:30]}"}}]}

    provider._call_responses_api = failing_responses  # type: ignore[method-assign]
    provider._call_chat_completions_fallback = fake_fallback  # type: ignore[method-assign]

    result = await provider.complete(
        prompt="What problems in Thessaloniki?",
        model="grok-4.5",
    )

    assert "choices" in result
    assert "Fallback answer" in result["choices"][0]["message"]["content"]


@pytest.mark.asyncio
async def test_http_401_triggers_fallback() -> None:
    """HTTP 401 (auth error) triggers fallback."""
    provider = XaiProvider(
        api_key="bad-key",
        fallback_api_key="good-key",
    )

    async def failing_responses(**kw: Any) -> dict[str, Any]:
        raise httpx.HTTPStatusError(
            "401 Unauthorized",
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
            response=httpx.Response(401),
        )

    async def fake_fallback(prompt: str) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "Auth fallback worked"}}]}

    provider._call_responses_api = failing_responses  # type: ignore[method-assign]
    provider._call_chat_completions_fallback = fake_fallback  # type: ignore[method-assign]

    result = await provider.complete(prompt="Test", model="grok-4.5")
    assert result["choices"][0]["message"]["content"] == "Auth fallback worked"


@pytest.mark.asyncio
async def test_network_error_triggers_fallback() -> None:
    """Network error on primary triggers fallback."""
    provider = XaiProvider(api_key="test-key", fallback_api_key="fallback-key")

    async def failing_responses(**kw: Any) -> dict[str, Any]:
        raise httpx.ConnectError("Connection refused")

    async def fake_fallback(prompt: str) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "Network fallback"}}]}

    provider._call_responses_api = failing_responses  # type: ignore[method-assign]
    provider._call_chat_completions_fallback = fake_fallback  # type: ignore[method-assign]

    result = await provider.complete(prompt="Test", model="grok-4.5")
    assert result["choices"][0]["message"]["content"] == "Network fallback"


@pytest.mark.asyncio
async def test_value_error_not_caught() -> None:
    """Non-HTTP errors on primary propagate immediately (no fallback)."""
    provider = XaiProvider(api_key="test-key", fallback_api_key="fallback-key")

    async def failing_responses(**kw: Any) -> dict[str, Any]:
        raise ValueError("Bad input")

    provider._call_responses_api = failing_responses  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Bad input"):
        await provider.complete(prompt="Test", model="grok-4.5")


@pytest.mark.asyncio
async def test_both_fail_propagates_fallback_error() -> None:
    """When both primary and fallback fail, the fallback error propagates."""
    provider = XaiProvider(api_key="test-key", fallback_api_key="fallback-key")

    async def failing_responses(**kw: Any) -> dict[str, Any]:
        raise httpx.HTTPStatusError(
            "503",
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
            response=httpx.Response(503),
        )

    async def failing_fallback(prompt: str) -> dict[str, Any]:
        raise httpx.HTTPStatusError(
            "502",
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            response=httpx.Response(502),
        )

    provider._call_responses_api = failing_responses  # type: ignore[method-assign]
    provider._call_chat_completions_fallback = failing_fallback  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError, match="502"):
        await provider.complete(prompt="Test", model="grok-4.5")


@pytest.mark.asyncio
async def test_tools_forwarded_to_responses_api() -> None:
    """Tools list is forwarded to the Responses API call."""
    provider = XaiProvider(api_key="test-key", fallback_api_key="fallback-key")

    captured: list[dict[str, Any]] = []

    async def capture_call(**kw: Any) -> dict[str, Any]:
        captured.append(kw)
        return {"id": "resp-3", "output_text": "ok"}

    provider._call_responses_api = capture_call  # type: ignore[method-assign]

    tools = [{"type": "x_search", "allowed_x_handles": ["@deddiede"]}]
    await provider.complete(prompt="Test", model="grok-4.5", tools=tools)

    assert len(captured) == 1
    assert captured[0]["tools"] == tools
