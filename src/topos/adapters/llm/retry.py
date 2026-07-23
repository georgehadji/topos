"""Retry decorator: exponential backoff for transient LLM failures.

Uses tenacity. Wraps the inner provider and retries on HTTP 429, 5xx,
and network errors.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable(exc: BaseException) -> bool:
    """True if the exception is a transient error worth retrying."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(
        exc,
        (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError),
    )


class Retry:
    """Wraps a provider with exponential-backoff retry logic."""

    def __init__(self, inner: Any, *, max_attempts: int = 5) -> None:
        self._inner = inner
        self._max_attempts = max_attempts

        self._retryer = retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._retryer(self._inner.complete)(  # type: ignore[no-any-return]
            prompt=prompt, model=model, response_format=response_format
        )
