"""LlmClient decorator stack assembly.

Architecture (ARCHITECTURE.md > LLM usage)::

    BudgetGuard( Cache( Retry( Telemetry( provider ) ) ) )

Factory function ``build_llm_client()`` wires everything together using
project config and an optional asyncpg pool.
"""

from __future__ import annotations

from typing import Any

import asyncpg
from pydantic import BaseModel

from topos.adapters.llm.budget import BudgetGuard
from topos.adapters.llm.cache import Cache
from topos.adapters.llm.fallback import FallbackProvider
from topos.adapters.llm.provider import OpenRouterProvider
from topos.adapters.llm.retry import Retry
from topos.adapters.llm.telemetry import Telemetry
from topos.config import Settings, is_placeholder_key


class StructuredLlmWrapper:
    """Wrapper that enforces the service.ports.LlmClient protocol on the decorator stack.

    If a schema (Pydantic model) is provided, it validates the response text against it.
    Otherwise, it returns the raw API response dictionary.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        schema: type[BaseModel] | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        raw_result = await self._inner.complete(
            prompt=prompt,
            model=model,
            response_format=response_format,
            tools=tools,
            **kwargs,
        )
        if schema is not None:
            choices = raw_result.get("choices", [])
            if not choices:
                raise ValueError("No choices in LLM response")
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError("Empty response content from LLM")
            return schema.model_validate_json(content)
        return raw_result


def _is_grok(model: str) -> bool:
    return "grok" in model.lower()


def _xai_name(model: str) -> str:
    """xAI's own API names Grok without a vendor prefix: ``grok-4.5``."""
    return model.split("/", 1)[-1] if _is_grok(model) else model


def _openrouter_name(model: str) -> str:
    """OpenRouter namespaces Grok under ``x-ai/``."""
    if _is_grok(model) and "/" not in model:
        return f"x-ai/{model}"
    return model


def build_llm_client(
    settings: Settings | None = None,
    pool: asyncpg.Pool | None = None,
) -> Any:
    """Assemble the decorator stack and return the outermost layer.

    The returned object satisfies ``service.ports.LlmClient`` structurally
    — it has an ``async def complete(...)`` method.

    When ``llm_provider`` is ``"xai"``, the innermost provider is a
    ``FallbackProvider`` that tries xAI direct first and OpenRouter second.
    Otherwise a single ``OpenRouterProvider`` is used.
    """
    s = settings or Settings()

    # Grok goes to xAI directly, with OpenRouter as the fallback. Keyed off the
    # model rather than llm_provider so that selecting a Grok model is enough —
    # but only when a real xAI key exists, otherwise the primary leg would fail
    # on every call before falling back.
    prefer_xai = (_is_grok(s.llm_model) or s.llm_provider == "xai") and not is_placeholder_key(
        s.xai_api_key
    )

    if prefer_xai:
        primary = OpenRouterProvider(
            api_key=s.xai_api_key,
            base_url=s.xai_base_url,
        )
        fallback = OpenRouterProvider(
            api_key=s.llm_api_key,
            base_url=s.llm_base_url,
        )
        provider: Any = FallbackProvider(
            primary=primary,
            fallback=fallback,
            primary_model=_xai_name(s.llm_model),
            fallback_model=s.llm_fallback_model or _openrouter_name(s.llm_model),
        )
    else:
        provider = OpenRouterProvider(
            api_key=s.llm_api_key,
            base_url=s.llm_base_url,
        )

    # Decorator stack: Telemetry → Retry → Cache → BudgetGuard
    # Innermost is Telemetry (writes extraction_run first)
    provider = Telemetry(provider, pool=pool)
    provider = Retry(provider)
    provider = Cache(provider, pool=pool)
    provider = BudgetGuard(provider, pool=pool, monthly_budget_eur=s.llm_monthly_budget_eur)

    return StructuredLlmWrapper(provider)
