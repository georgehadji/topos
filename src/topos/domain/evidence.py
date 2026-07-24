"""Evidence: corroboration and contradiction detection.

Pure domain logic. No IO.

Slice 2.6+2.7. Given multiple claims about the same problem,
determine whether they corroborate (strengthen) or contradict
(weaken) each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class ClaimSummary:
    """A claim attached to a problem. Lightweight for evidence analysis."""

    claim_id: str
    predicate: str
    value: Any
    source_id: str  # source kind, e.g. "diavgeia"
    confidence: Decimal | None


@dataclass(frozen=True, slots=True)
class EvidenceResult:
    """Result of evidence analysis for one problem."""

    problem_id: str
    total_claims: int
    independent_sources: int  # reach count (unique sources, not reports)
    corroboration_score: Decimal  # 0.0-1.0
    contradiction_count: int
    evidence_strength: Decimal  # aggregated 0.0-1.0


def _unique_sources(claims: list[ClaimSummary]) -> int:
    """Count unique source IDs among claims."""
    return len({c.source_id for c in claims})


def _supported_by_count(claims: list[ClaimSummary]) -> Decimal:
    """Score based on number of claims (log scale, capped at 10)."""
    count = len(claims)
    if count == 0:
        return Decimal("0")
    if count == 1:
        return Decimal("0.2")
    if count <= 3:  # noqa: PLR2004
        return Decimal("0.5")
    if count <= 6:  # noqa: PLR2004
        return Decimal("0.75")
    return Decimal("1.0")


def _contradictions(claims: list[ClaimSummary]) -> int:
    """Detect contradictions: same predicate, opposing boolean values.

    Simple heuristic: if two claims share a predicate and one says
    True/yes and another says False/no, that's a contradiction.
    """
    by_predicate: dict[str, list[Any]] = {}
    for c in claims:
        by_predicate.setdefault(c.predicate, []).append(c.value)

    contradictions = 0
    for _predicate, values in by_predicate.items():
        bools = [v for v in values if isinstance(v, bool)]
        if True in bools and False in bools:
            contradictions += 1

    return contradictions


def _sources_independent(claims: list[ClaimSummary]) -> Decimal:
    """Score based on ratio of unique sources to total claims.

    Higher ratio = more independent reports = stronger evidence.
    Three outlets republishing one wire is one source.
    """
    if not claims:
        return Decimal("0")
    ratio = Decimal(len(claims)) / Decimal(max(len({c.source_id for c in claims}), 1))
    # Normalize: perfect independence (1 claim per source) → 1.0
    # All from one source → ratio / len(claims) → approaches 0
    normalized = Decimal(min(1.0, float(Decimal("1.0") / ratio)))
    return normalized.quantize(Decimal("0.01"))


def analyze(problem_id: str, claims: list[ClaimSummary]) -> EvidenceResult:
    """Run evidence analysis on all claims for a problem."""
    total = len(claims)
    sources = _unique_sources(claims)
    supported = _supported_by_count(claims)
    contradictions = _contradictions(claims)
    independence = _sources_independent(claims)

    # Evidence strength: combine support * independence, penalize contradictions
    base = supported * independence
    penalty = Decimal("0.2") * Decimal(str(contradictions))
    strength = max(Decimal("0"), base - penalty).quantize(Decimal("0.01"))

    return EvidenceResult(
        problem_id=problem_id,
        total_claims=total,
        independent_sources=sources,
        corroboration_score=supported,
        contradiction_count=contradictions,
        evidence_strength=strength,
    )
