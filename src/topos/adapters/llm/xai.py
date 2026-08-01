"""xAI Responses API provider — tool-calling for X Search, Web Search.

Targets the Responses API (``/v1/responses``) which supports ``x_search``
and ``web_search`` tools — these are not available on the Chat Completions
endpoint.

Follows the same xAI-first → OpenRouter fallback pattern from
``FallbackProvider``, but for the Responses API shape. OpenRouter may
not support the Responses API with tools; if it doesn't, the fallback
path uses Chat Completions with the search query embedded in the prompt
(degraded but functional).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Failure modes that trigger fallback.
_FALLBACK_STATUSES = frozenset({401, 403, 429, 500, 502, 503, 504})


class XaiProvider:
    """xAI Responses API provider with xAI-first → OpenRouter fallback.

    Primary targets ``https://api.x.ai/v1/responses``. Fallback targets
    ``https://openrouter.ai/api/v1/chat/completions`` with the query
    embedded in the user message (no tool definitions).
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.x.ai/v1",
        fallback_api_key: str = "",
        fallback_base_url: str = "https://openrouter.ai/api/v1",
        model: str = "grok-4.5",
        fallback_model: str = "x-ai/grok-4.5",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._fallback_api_key = fallback_api_key
        self._fallback_base_url = fallback_base_url.rstrip("/")
        self._model = model
        self._fallback_model = fallback_model

    async def complete(
        self,
        *,
        prompt: str,
        model: str,  # noqa: ARG002 — overridden by self._model
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a Responses API request, optionally with tools.

        Falls back to the Chat Completions endpoint if the primary fails.
        """
        _ = response_format  # Responses API handles structured output differently
        try:
            return await self._call_responses_api(
                prompt=prompt,
                model=self._model,
                tools=tools,
                **kwargs,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _FALLBACK_STATUSES:
                raise
            logger.warning(
                "XaiProvider primary failed (HTTP %d), falling back to Chat Completions. "
                "model=%s fallback_model=%s",
                exc.response.status_code,
                self._model,
                self._fallback_model,
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            logger.warning(
                "XaiProvider primary network error (%s), falling back to Chat Completions. "
                "model=%s fallback_model=%s",
                type(exc).__name__,
                self._model,
                self._fallback_model,
            )
        except Exception:
            raise

        # Fallback: Chat Completions with search query embedded in prompt.
        return await self._call_chat_completions_fallback(prompt=prompt)

    async def _call_responses_api(
        self,
        *,
        prompt: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call the xAI Responses API with optional tool definitions."""
        body: dict[str, Any] = {
            "model": model,
            "input": [{"role": "user", "content": prompt}],
        }
        if tools:
            body["tools"] = tools
        if kwargs.get("search_domain_filter"):
            body.setdefault("tools", []).append(
                {
                    "type": "web_search",
                    "filters": {"allowed_domains": kwargs["search_domain_filter"]},
                }
            )

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.post(
                f"{self._base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            return dict(resp.json())

    async def _call_chat_completions_fallback(self, prompt: str) -> dict[str, Any]:
        """Fallback: call OpenRouter Chat Completions with query in prompt.

        This is a degraded path — no tool definitions. The model may not
        perform the search, but it can attempt to answer from training data
        or call a web search via its native capability.
        """
        body: dict[str, Any] = {
            "model": self._fallback_model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Search the web for the latest information, then answer "
                        f"the following question:\n\n{prompt}"
                    ),
                }
            ],
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.post(
                f"{self._fallback_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._fallback_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://topos.local",
                    "X-Title": "Topos",
                },
                json=body,
            )
            resp.raise_for_status()
            return dict(resp.json())
