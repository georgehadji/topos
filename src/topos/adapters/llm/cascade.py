"""Cascade decorator: try cheaper models first, escalate on a bad result.

Phase 6 #6.5. Positioned between BudgetGuard and Retry (ADR-015): each
attempt still goes through Retry/Telemetry innermost, so a model's own
transient failure retries before Cascade gives up on it and tries the next.

Chain of Responsibility over `models`, cheapest first. `should_escalate` is
the pure escalation predicate — parse failure, or (when the response looks
like a list of claim-shaped dicts, as domain/extraction.py's claims are) every
item's confidence below a floor. It judges only the raw JSON content, so it
applies unchanged to any caller (extraction, sentiment) without knowing their
schema in advance; a caller whose JSON carries no "confidence" field (e.g.
sentiment's `{"labels": [...]}`) simply never trips that branch.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Below this, every claim in a response is treated as not worth trusting from
# the cheap model. Matches domain/extraction.py's own default-confidence
# floor (_validate_claims defaults an unstated confidence to 0.5).
_CONFIDENCE_FLOOR = 0.5


def should_escalate(response: dict[str, Any]) -> bool:
    """True when *response* is bad enough to retry on the next model."""
    content = _content_of(response)
    if not content:
        return True
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return True

    items: Any = parsed
    if isinstance(parsed, dict):
        items = parsed.get("claims") or parsed.get("problems") or []
    if not isinstance(items, list) or not items:
        return False

    confidences = [i["confidence"] for i in items if isinstance(i, dict) and "confidence" in i]
    numeric = [c for c in confidences if isinstance(c, int | float)]
    if not numeric:
        return False
    return all(c < _CONFIDENCE_FLOOR for c in numeric)


def _content_of(response: dict[str, Any]) -> str | None:
    choices = response.get("choices") or []
    if not choices:
        return None
    content = choices[0].get("message", {}).get("content")
    return content or None


class Cascade:
    """Tries each of `models` in order, escalating past one whose result
    fails `should_escalate`. Owns model selection while active — the
    `model` a caller passes is ignored, same as `rerank_models` overrides a
    caller's choice for search reranking.
    """

    def __init__(self, inner: Any, *, models: list[str]) -> None:
        if not models:
            raise ValueError("Cascade needs at least one model")
        self._inner = inner
        self._models = models

    async def complete(
        self,
        *,
        prompt: str,
        model: str,  # noqa: ARG002 — Cascade owns model selection while active
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {}
        for candidate in self._models:
            response = await self._inner.complete(
                prompt=prompt, model=candidate, response_format=response_format, **kwargs
            )
            if not should_escalate(response):
                return response
            logger.info("cascade escalating past %s", candidate)
        return response
