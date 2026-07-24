"""OpenRouter HTTP provider — inner layer of the decorator stack.

Sends prompts to the OpenRouter API (OpenAI-compatible). Returns raw dicts.
No caching, no retries, no telemetry — those are decorators above.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

# The common callable signature that every decorator layer satisfies.
# It takes prompt + model + optional response_format and returns the API dict.
LlmCallable = Callable[
    ...,
    Awaitable[dict[str, Any]],
]


class OpenRouterProvider:
    """Raw HTTP client for OpenRouter API.

    Talked to by the outer decorator layers (Cache, Retry, etc.).
    """

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request and return the full response dict."""
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        if response_format:
            body["response_format"] = response_format

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0)) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://topos.local",
                    "X-Title": "Topos",
                },
                json=body,
            )
            resp.raise_for_status()
            return dict(resp.json())
