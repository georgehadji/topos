"""Sonar HTTP provider — wraps OpenRouter for Perplexity Sonar models.

Sonar runs a web search before every completion and returns cited results.
Unlike XaiProvider (which uses the Responses API tool-calling pattern),
Sonar uses the Chat Completions API — the same endpoint as OpenRouterProvider.

This provider is a thin wrapper that:
- Targets OpenRouter with a ``perplexity/`` model name
- Forwards Sonar-specific kwargs (``search_domain_filter``,
  ``search_recency_filter``) through the decorator stack
- Returns the raw API dict (same as OpenRouterProvider)
"""

from __future__ import annotations

from typing import Any

from topos.adapters.llm.fallback import FallbackProvider
from topos.adapters.llm.provider import OpenRouterProvider
from topos.config import is_placeholder_key


class SonarProvider:
    """Sonar provider via OpenRouter's Chat Completions API.

    Uses the same request shape as ``OpenRouterProvider`` but selects a
    Perplexity Sonar model. Search is implicit in every call — Sonar always
    retrieves before answering, so no ``tools`` kwarg is needed.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "perplexity/sonar-pro",
        perplexity_api_key: str = "",
        perplexity_base_url: str = "https://api.perplexity.ai",
        perplexity_model: str = "sonar-pro",
    ) -> None:
        openrouter = OpenRouterProvider(api_key=api_key, base_url=base_url)
        self._model = model

        # Perplexity direct first, OpenRouter as the fallback. Direct is worth
        # preferring: it returns the `citations` / `search_results` fields that
        # gateways drop, so discovery does not have to scrape URLs out of prose.
        if perplexity_api_key and not is_placeholder_key(perplexity_api_key):
            self._inner: Any = FallbackProvider(
                primary=OpenRouterProvider(
                    api_key=perplexity_api_key, base_url=perplexity_base_url
                ),
                fallback=openrouter,
                primary_model=perplexity_model,
                fallback_model=model,
            )
        else:
            self._inner = openrouter

    async def complete(
        self,
        *,
        prompt: str,
        model: str,  # noqa: ARG002 — overridden by self._model
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a completion to Sonar — Perplexity direct, else OpenRouter.

        Sonar-specific parameters (``search_domain_filter``,
        ``search_recency_filter``) are forwarded via ``**kwargs``.
        The ``OpenRouterProvider.complete()`` signature accepts
        ``**_kwargs`` and swallows unrecognized keys.
        """
        # FallbackProvider is untyped at this boundary, hence the explicit cast.
        result: dict[str, Any] = await self._inner.complete(
            prompt=prompt,
            model=self._model,
            response_format=response_format,
            **kwargs,
        )
        return result
