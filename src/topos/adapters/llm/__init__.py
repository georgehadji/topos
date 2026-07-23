"""LlmClient decorator stack assembly.

Architecture (ARCHITECTURE.md > LLM usage)::

    BudgetGuard( Cache( Retry( Telemetry( provider ) ) ) )

Factory function ``build_llm_client()`` wires everything together using
project config and an optional asyncpg pool.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from topos.adapters.llm.budget import BudgetGuard
from topos.adapters.llm.cache import Cache
from topos.adapters.llm.provider import OpenRouterProvider
from topos.adapters.llm.retry import Retry
from topos.adapters.llm.telemetry import Telemetry
from topos.config import Settings


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

    return provider
