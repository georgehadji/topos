"""Fallback provider: try primary, fall back to secondary on failure.

Primary is xAI direct; fallback is OpenRouter (or vice versa). Sits at the
innermost position of the decorator stack:

    BudgetGuard( Cache( Retry( Telemetry( FallbackProvider(primary, fallback) ) ) ) )

Primary failure modes that trigger fallback:
- HTTP 401/403/5xx (non-retryable auth/server errors)
- HTTP 429 rate limit (retryable, but after Retry exhaustion)
- Network/connectivity errors
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Failure modes that are worth trying a fallback for.
_FALLBACK_STATUSES = frozenset({401, 403, 429, 500, 502, 503, 504})


class FallbackProvider:
    """Try primary first; on failure, try fallback.

    Both providers are ``OpenRouterProvider`` instances (or any object with
    the same ``async def complete(...)`` signature). The fallback is tried
    once if the primary raises an ``httpx.HTTPStatusError`` with a status in
    ``_FALLBACK_STATUSES`` or a network-level exception.
    """

    def __init__(
        self,
        primary: Any,
        fallback: Any,
        *,
        primary_model: str,
        fallback_model: str,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_model = primary_model
        self._fallback_model = fallback_model

    async def complete(
        self,
        *,
        prompt: str,
        model: str,  # noqa: ARG002 — overridden by self._primary_model / self._fallback_model
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Try primary; if it fails in a way that is worth falling back, try
        # fallback with the equivalent model name.
        try:
            return await self._primary.complete(  # type: ignore[no-any-return]
                prompt=prompt,
                model=self._primary_model,
                response_format=response_format,
                **kwargs,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _FALLBACK_STATUSES:
                raise
            logger.warning(
                "Primary LLM failed (HTTP %d), falling back to secondary. "
                "primary_model=%s fallback_model=%s",
                exc.response.status_code,
                self._primary_model,
                self._fallback_model,
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            logger.warning(
                "Primary LLM network error (%s), falling back to secondary. "
                "primary_model=%s fallback_model=%s",
                type(exc).__name__,
                self._primary_model,
                self._fallback_model,
            )
        except Exception:
            # Non-network, non-HTTP errors are not safe to fall back on.
            raise

        # Fallback attempt — model name may differ on the secondary provider.
        try:
            return await self._fallback.complete(  # type: ignore[no-any-return]
                prompt=prompt,
                model=self._fallback_model,
                response_format=response_format,
                **kwargs,
            )
        except Exception:
            logger.exception(
                "Fallback LLM also failed. primary_model=%s fallback_model=%s",
                self._primary_model,
                self._fallback_model,
            )
            raise
