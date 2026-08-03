"""Unit tests: extraction service parsing and span validation.

Tests the pure functions in service/extraction.py — _parse_response
and _validate_claims. No IO, no mocks.
"""

from __future__ import annotations

from decimal import Decimal

from topos.domain.extraction import Span
from topos.service.extraction import _parse_response, _validate_claims


def test_parse_valid_json_array() -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "content": '[{"predicate": "road_damage", "value": "pothole", "span_start": 10, "span_end": 25}]'
                }
            }
        ]
    }
    result = _parse_response(raw)
    assert len(result) == 1
    assert result[0]["predicate"] == "road_damage"
    assert result[0]["value"] == "pothole"


def test_parse_wrapped_in_claims_key() -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "content": '{"claims": [{"predicate": "water_leak", "value": "broken pipe", "start": 5, "end": 15}]}'
                }
            }
        ]
    }
    result = _parse_response(raw)
    assert len(result) == 1
    assert result[0]["predicate"] == "water_leak"


def test_parse_wrapped_in_problems_key() -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "content": '{"problems": [{"predicate": "air_pollution", "value": "exceeds limits", "start": 0, "end": 10}]}'
                }
            }
        ]
    }
    result = _parse_response(raw)
    assert len(result) == 1
    assert result[0]["predicate"] == "air_pollution"


def test_parse_empty_content_returns_empty() -> None:
    raw = {"choices": [{"message": {"content": ""}}]}
    result = _parse_response(raw)
    assert result == []


def test_parse_empty_llm_response() -> None:
    result = _parse_response({})
    assert result == []


def test_parse_invalid_json_returns_empty() -> None:
    raw = {"choices": [{"message": {"content": "not json at all"}}]}
    result = _parse_response(raw)
    assert result == []


def test_validate_valid_claim() -> None:
    raw = [
        {
            "predicate": "pothole",
            "value": "large pothole on Egnatia",
            "span_start": 0,
            "span_end": 10,
        }
    ]
    result = _validate_claims(raw, "0123456789")
    assert len(result) == 1
    assert result[0].claim.predicate == "pothole"
    assert result[0].claim.value == "large pothole on Egnatia"
    assert result[0].span == Span(start=0, end=10)


def test_validate_rejects_span_out_of_bounds() -> None:
    raw = [{"predicate": "pothole", "value": "bad", "span_start": 0, "span_end": 100}]
    result = _validate_claims(raw, "short")
    assert len(result) == 0


def test_validate_rejects_negative_span() -> None:
    raw = [{"predicate": "pothole", "value": "bad", "span_start": -1, "span_end": 5}]
    result = _validate_claims(raw, "hello world")
    assert len(result) == 0


def test_validate_rejects_reversed_span() -> None:
    raw = [{"predicate": "pothole", "value": "bad", "span_start": 10, "span_end": 5}]
    result = _validate_claims(raw, "hello world")
    assert len(result) == 0


def test_validate_rejects_missing_predicate() -> None:
    raw = [{"value": "test", "span_start": 0, "span_end": 5}]
    result = _validate_claims(raw, "hello world")
    assert len(result) == 0


def test_validate_rejects_missing_value() -> None:
    raw = [{"predicate": "test", "span_start": 0, "span_end": 5}]
    result = _validate_claims(raw, "hello world")
    assert len(result) == 0


def test_validate_non_dict_items_skipped() -> None:
    raw = ["not a dict"]
    result = _validate_claims(raw, "text")
    assert len(result) == 0


def test_validate_accepts_start_end_aliases() -> None:
    raw = [{"predicate": "noise", "value": "loud", "start": 2, "end": 6}]
    result = _validate_claims(raw, "quiet loud here")
    assert len(result) == 1
    assert result[0].span == Span(start=2, end=6)


def test_validate_uses_stated_confidence() -> None:
    raw = [
        {
            "predicate": "pothole",
            "value": "large pothole, clearly visible",
            "span_start": 0,
            "span_end": 10,
            "confidence": 0.9,
        }
    ]
    result = _validate_claims(raw, "0123456789")
    assert result[0].claim.confidence == Decimal("0.9")


def test_validate_defaults_confidence_when_omitted() -> None:
    raw = [{"predicate": "pothole", "value": "maybe a pothole", "span_start": 0, "span_end": 10}]
    result = _validate_claims(raw, "0123456789")
    assert result[0].claim.confidence == Decimal("0.5")


def test_validate_clamps_out_of_range_confidence() -> None:
    raw = [
        {"predicate": "a", "value": "v", "span_start": 0, "span_end": 5, "confidence": 5},
        {"predicate": "b", "value": "v", "span_start": 0, "span_end": 5, "confidence": -1},
    ]
    result = _validate_claims(raw, "0123456789")
    assert result[0].claim.confidence == Decimal("1")
    assert result[1].claim.confidence == Decimal("0")


def test_validate_ignores_unparseable_confidence() -> None:
    raw = [
        {
            "predicate": "pothole",
            "value": "bad",
            "span_start": 0,
            "span_end": 5,
            "confidence": "very sure",
        }
    ]
    result = _validate_claims(raw, "0123456789")
    assert result[0].claim.confidence == Decimal("0.5")


def test_validate_multiple_claims_mixed_quality() -> None:
    raw = [
        {"predicate": "good", "value": "ok", "span_start": 0, "span_end": 5},
        {"predicate": "bad_span", "value": "fail", "span_start": 10, "span_end": 100},
        {"predicate": "no_value"},
        {"predicate": "also_good", "value": "fine", "span_start": 6, "span_end": 10},
    ]
    result = _validate_claims(raw, "0123456789")
    assert len(result) == 2
    assert result[0].claim.predicate == "good"
    assert result[1].claim.predicate == "also_good"
