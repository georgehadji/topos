"""BudgetGuard decorator: enforces a hard monthly spending ceiling.

If the monthly spend (sum of cost_eur in extraction_run for the current month)
exceeds the configured budget, subsequent calls are deferred.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import asyncpg


class BudgetExceeded(Exception):
    """Raised when the monthly budget has been exceeded."""


class BudgetGuard:
    """Wraps a provider and checks the monthly budget before each call."""

    def __init__(
        self,
        inner: Any,
        pool: asyncpg.Pool | None = None,
        *,
        monthly_budget_eur: float = 250.0,
    ) -> None:
        self._inner = inner
        self._pool = pool
        self._budget = monthly_budget_eur

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self._pool is not None:
            spent = await self._spent_this_month()
            if spent >= self._budget:
                raise BudgetExceeded(
                    f"Monthly budget \u20ac{self._budget:.2f} exceeded (\u20ac{spent:.4f} spent)"
                )

        return await self._inner.complete(  # type: ignore[no-any-return]
            prompt=prompt, model=model, response_format=response_format, **kwargs
        )

    async def _spent_this_month(self) -> float:
        now = datetime.now(UTC)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchval(
                """
                SELECT COALESCE(SUM(cost_eur), 0) FROM extraction_run
                WHERE started_at >= $1
                """,
                start_of_month,
            )
        return float(row or 0)
