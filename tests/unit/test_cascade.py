"""Unit tests: adapters/llm/cascade.py — pure escalation predicate + decorator.

Phase 6 #6.5. No model calls: should_escalate is literal-input, and Cascade
is exercised against a fake inner client that records what it was asked for.
"""

from __future__ import annotations

from typing import Any

import pytest

from topos.adapters.llm.cascade import Cascade, should_escalate


def _response(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


# ── should_escalate ──────────────────────────────────────────────────────────


def test_escalates_on_empty_content() -> None:
    assert should_escalate(_response("")) is True


def test_escalates_on_no_choices() -> None:
    assert should_escalate({"choices": []}) is True


def test_escalates_on_invalid_json() -> None:
    assert should_escalate(_response("not json")) is True


def test_does_not_escalate_on_empty_list() -> None:
    assert should_escalate(_response("[]")) is False


def test_escalates_when_every_claim_confidence_below_floor() -> None:
    content = '[{"predicate": "a", "value": "v", "confidence": 0.2}, {"predicate": "b", "value": "v", "confidence": 0.3}]'
    assert should_escalate(_response(content)) is True


def test_does_not_escalate_when_one_claim_confidence_meets_floor() -> None:
    content = '[{"predicate": "a", "value": "v", "confidence": 0.2}, {"predicate": "b", "value": "v", "confidence": 0.9}]'
    assert should_escalate(_response(content)) is False


def test_does_not_escalate_when_confidence_field_absent() -> None:
    content = '[{"predicate": "a", "value": "v"}]'
    assert should_escalate(_response(content)) is False


def test_does_not_escalate_on_sentiment_shaped_response() -> None:
    """{"labels": [...]} carries no "confidence" — must never trip the
    claim-confidence branch just because it happens to parse as JSON."""
    assert should_escalate(_response('{"labels": ["negative", "neutral"]}')) is False


def test_escalates_on_claims_wrapper_key_all_low_confidence() -> None:
    content = '{"claims": [{"predicate": "a", "value": "v", "confidence": 0.1}]}'
    assert should_escalate(_response(content)) is True


# ── Cascade ───────────────────────────────────────────────────────────────────


class _FakeInner:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def complete(self, *, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(model)
        return self._responses[model]


@pytest.mark.asyncio
async def test_stops_at_first_model_that_does_not_escalate() -> None:
    inner = _FakeInner(
        {
            "cheap": _response('[{"predicate": "a", "value": "v", "confidence": 0.9}]'),
            "expensive": _response('[{"predicate": "a", "value": "v", "confidence": 0.9}]'),
        }
    )
    cascade = Cascade(inner, models=["cheap", "expensive"])

    result = await cascade.complete(prompt="p", model="ignored")

    assert inner.calls == ["cheap"]
    assert result == inner._responses["cheap"]


@pytest.mark.asyncio
async def test_escalates_to_next_model_on_low_confidence() -> None:
    inner = _FakeInner(
        {
            "cheap": _response('[{"predicate": "a", "value": "v", "confidence": 0.1}]'),
            "expensive": _response('[{"predicate": "a", "value": "v", "confidence": 0.9}]'),
        }
    )
    cascade = Cascade(inner, models=["cheap", "expensive"])

    result = await cascade.complete(prompt="p", model="ignored")

    assert inner.calls == ["cheap", "expensive"]
    assert result == inner._responses["expensive"]


@pytest.mark.asyncio
async def test_returns_last_response_when_every_model_escalates() -> None:
    inner = _FakeInner(
        {
            "cheap": _response("not json"),
            "expensive": _response("still not json"),
        }
    )
    cascade = Cascade(inner, models=["cheap", "expensive"])

    result = await cascade.complete(prompt="p", model="ignored")

    assert inner.calls == ["cheap", "expensive"]
    assert result == inner._responses["expensive"]


def test_rejects_empty_model_list() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        Cascade(_FakeInner({}), models=[])
