"""Sentiment of *coverage* — pure aggregation.

Scope, deliberately narrow: this measures how a problem or category is
discussed in documents Topos already ingested. It does not model individuals,
and there is no per-person profiling anywhere in this module or the adapter
behind it.

Politician-level sentiment ("how is member X perceived") is **not** built:
there is no politician entity in the schema, so it would need entity
extraction and mention tracking first. Category-level coverage sentiment
answers the adjacent and more actionable question — which issues are
generating hostile reporting — with data that already exists.

Aggregation returns a *distribution*, never a single scalar verdict. "62%
negative across 13 documents" is auditable; "sentiment: -0.24" invites a
politician to act on a number whose construction nobody can inspect.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

__all__ = ["SentimentLabel", "SentimentSummary", "aggregate"]


class SentimentLabel(StrEnum):
    """Three buckets, not five. Greek-language classifiers do not reliably
    separate "somewhat negative" from "negative", and a scale implies a
    precision the input does not carry."""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


@dataclass(frozen=True, slots=True)
class SentimentSummary:
    """Distribution over labels for one subject.

    ``dominant`` is None on an exact tie — a coin-flip verdict presented as a
    finding is worse than saying nothing.
    """

    total: int
    negative: int
    neutral: int
    positive: int
    dominant: SentimentLabel | None
    negative_share: Decimal


def aggregate(labels: list[SentimentLabel]) -> SentimentSummary:
    """Fold labels into a distribution. Empty input yields an empty summary."""
    counts = Counter(labels)
    total = len(labels)
    negative = counts[SentimentLabel.NEGATIVE]
    neutral = counts[SentimentLabel.NEUTRAL]
    positive = counts[SentimentLabel.POSITIVE]

    return SentimentSummary(
        total=total,
        negative=negative,
        neutral=neutral,
        positive=positive,
        dominant=_dominant(counts),
        negative_share=(
            (Decimal(negative) / Decimal(total)).quantize(Decimal("0.01"))
            if total
            else Decimal("0.00")
        ),
    )


def _dominant(counts: Counter[SentimentLabel]) -> SentimentLabel | None:
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]
