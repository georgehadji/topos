"""Unit tests: evidence corroboration and contradiction.

Pure domain tests — literal inputs, literal expected outputs.
"""

from __future__ import annotations

from decimal import Decimal

from topos.domain.evidence import ClaimSummary, analyze


def _c(claim_id: str, predicate: str, value: object, source: str = "diavgeia",
        confidence: Decimal | None = None) -> ClaimSummary:
    return ClaimSummary(
        claim_id=claim_id, predicate=predicate, value=value,
        source_id=source, confidence=confidence,
    )


def test_single_claim() -> None:
    result = analyze("prob-1", [
        _c("c1", "road_damage", "pothole"),
    ])
    assert result.total_claims == 1
    assert result.independent_sources == 1
    assert result.corroboration_score == Decimal("0.2")
    assert result.contradiction_count == 0
    assert result.evidence_strength > Decimal("0")


def test_multiple_claims_same_source() -> None:
    result = analyze("prob-2", [
        _c("c1", "road_damage", "pothole", "diavgeia"),
        _c("c2", "road_damage", "large pothole", "diavgeia"),
    ])
    assert result.independent_sources == 1
    assert result.evidence_strength > Decimal("0")


def test_multiple_claims_multiple_sources() -> None:
    result = analyze("prob-3", [
        _c("c1", "road_damage", "pothole", "diavgeia"),
        _c("c2", "road_damage", "pothole reported", "newsfeed"),
        _c("c3", "road_damage", "confirmed pothole", "municipality"),
    ])
    assert result.independent_sources == 3
    assert result.corroboration_score >= Decimal("0.5")
    assert result.evidence_strength > Decimal("0.3")


def test_contradiction_boolean_values() -> None:
    result = analyze("prob-4", [
        _c("c1", "water_quality", True, "diavgeia"),
        _c("c2", "water_quality", False, "newsfeed"),
    ])
    assert result.contradiction_count == 1
    assert result.evidence_strength < Decimal("0.5")  # penalized


def test_no_contradiction_different_predicates() -> None:
    result = analyze("prob-5", [
        _c("c1", "road_damage", True),
        _c("c2", "water_leak", False),
    ])
    assert result.contradiction_count == 0


def test_no_claims() -> None:
    result = analyze("prob-6", [])
    assert result.total_claims == 0
    assert result.independent_sources == 0
    assert result.evidence_strength == Decimal("0")


def test_many_claims_multiple_sources() -> None:
    claims = [
        _c(f"c{i}", "air_pollution", f"reading_{i}",
           "newsfeed" if i % 2 == 0 else "diavgeia")
        for i in range(8)
    ]
    result = analyze("prob-7", claims)
    assert result.total_claims == 8
    assert result.independent_sources == 2
    assert result.corroboration_score == Decimal("1.0")  # 8 claims → capped
    assert result.evidence_strength > Decimal("0")
