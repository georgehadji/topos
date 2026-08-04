"""Unit tests: coverage sentiment — aggregation, parsing, persistence."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.adapters.sentiment import _parse
from topos.domain.sentiment import SentimentLabel, aggregate
from topos.service.sentiment import score_sentiment

_NEG = SentimentLabel.NEGATIVE
_NEU = SentimentLabel.NEUTRAL
_POS = SentimentLabel.POSITIVE


# ── Pure aggregation ────────────────────────────────────────────────────────


def test_counts_and_share() -> None:
    summary = aggregate([_NEG, _NEG, _NEG, _NEU])
    assert summary.total == 4
    assert summary.negative == 3
    assert summary.dominant is _NEG
    assert summary.negative_share == Decimal("0.75")


def test_empty_input_is_an_empty_summary_not_a_crash() -> None:
    summary = aggregate([])
    assert summary.total == 0
    assert summary.dominant is None
    assert summary.negative_share == Decimal("0.00")


def test_exact_tie_has_no_dominant_label() -> None:
    """A coin-flip verdict presented as a finding is worse than silence."""
    assert aggregate([_NEG, _POS]).dominant is None


def test_near_tie_still_resolves() -> None:
    assert aggregate([_NEG, _NEG, _POS]).dominant is _NEG


# ── Adapter parsing ─────────────────────────────────────────────────────────


def test_parses_a_clean_label_list() -> None:
    reply = '{"labels": ["negative", "neutral"]}'
    assert _parse(reply, expected=2) == [_NEG, _NEU]


def test_parses_labels_wrapped_in_prose() -> None:
    reply = 'Ορίστε: {"labels": ["positive"]} τέλος'
    assert _parse(reply, expected=1) == [_POS]


def test_parses_a_chat_completion_dict() -> None:
    reply: dict[str, Any] = {"choices": [{"message": {"content": '{"labels": ["negative"]}'}}]}
    assert _parse(reply, expected=1) == [_NEG]


def test_length_mismatch_is_rejected() -> None:
    """A short list would misalign labels with texts, attributing one
    document's tone to another."""
    assert _parse('{"labels": ["negative"]}', expected=3) is None


def test_unknown_label_rejects_the_batch() -> None:
    assert _parse('{"labels": ["furious"]}', expected=1) is None


def test_unparseable_reply_is_rejected_not_defaulted() -> None:
    assert _parse("model had a bad day", expected=1) is None
    assert _parse("", expected=1) is None


# ── Persistence ─────────────────────────────────────────────────────────────


def _pool(rows: list[dict[str, Any]]) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    return pool, conn


def _row(problem_id: str = "p1", n: int = 2) -> dict[str, Any]:
    return {"problem_id": problem_id, "texts": json.dumps([f"κείμενο {i}" for i in range(n)])}


@pytest.mark.asyncio
async def test_writes_one_snapshot_per_problem() -> None:
    pool, conn = _pool([_row()])

    async def analyzer(texts: list[str]) -> list[SentimentLabel]:
        return [_NEG] * len(texts)

    result = await score_sentiment(pool, analyzer, model="m", prompt_ver="v1")

    assert result == {"written": 1, "skipped": 0}
    args = conn.execute.call_args.args
    assert args[2] == "negative"
    assert args[3] == 2  # sample_size


@pytest.mark.asyncio
async def test_analyzer_failure_writes_nothing_for_that_problem() -> None:
    """No row beats a neutral row: absence of a measurement and a measurement
    of neutrality are different facts."""
    pool, conn = _pool([_row()])

    async def broken(texts: list[str]) -> list[SentimentLabel]:
        raise RuntimeError("vendor down")

    result = await score_sentiment(pool, broken, model="m", prompt_ver="v1")

    assert result == {"written": 0, "skipped": 1}
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_tied_distribution_is_not_recorded() -> None:
    pool, conn = _pool([_row(n=2)])

    async def split(texts: list[str]) -> list[SentimentLabel]:
        return [_NEG, _POS]

    result = await score_sentiment(pool, split, model="m", prompt_ver="v1")

    assert result["written"] == 0
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_problem_with_no_document_text_is_skipped_silently() -> None:
    pool, _conn = _pool([{"problem_id": "p1", "texts": "[]"}])

    async def analyzer(texts: list[str]) -> list[SentimentLabel]:
        raise AssertionError("must not be called")

    result = await score_sentiment(pool, analyzer, model="m", prompt_ver="v1")

    assert result == {"written": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_model_and_prompt_version_are_persisted() -> None:
    """Without these, re-running with a new model looks like opinion moving."""
    pool, conn = _pool([_row()])

    async def analyzer(texts: list[str]) -> list[SentimentLabel]:
        return [_NEU] * len(texts)

    await score_sentiment(pool, analyzer, model="mistral-x", prompt_ver="sentiment-el-1.0.0")

    args = conn.execute.call_args.args
    assert args[7] == "mistral-x"
    assert args[8] == "sentiment-el-1.0.0"
