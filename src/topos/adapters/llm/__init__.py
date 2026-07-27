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
from topos.adapters.llm.provider import OpenRouterProvider
from topos.adapters.llm.retry import Retry
from topos.adapters.llm.telemetry import Telemetry
from topos.config import Settings


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
        **kwargs: Any,
    ) -> Any:
        raw_result = await self._inner.complete(
            prompt=prompt,
            model=model,
            response_format=response_format,
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


def build_llm_client(
    settings: Settings | None = None,
    pool: asyncpg.Pool | None = None,
) -> Any:
    """Assemble the decorator stack and return the outermost layer.

    The returned object satisfies ``service.ports.LlmClient`` structurally
    — it has an ``async def complete(...)`` method.
    """
    s = settings or Settings()

    provider: Any = OpenRouterProvider(
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
