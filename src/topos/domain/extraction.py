"""Extraction schema: what the LLM extracts from a Greek document.

L1/L2-safe: no person names, no political/health/religious/ethnic/union
inference (ARCHITECTURE.md §Non-negotiable constraints).

Every field that originates from the source document must carry a
span (int4range) pointing into the chunk text.

WARNING: This is pure domain (no IO, no project imports).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class Span:
    """A byte range into a chunk's text. NOT NULL per L5."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ClaimAtom:
    """One atomic claim extracted from a source document.

    Must resolve to a span (L5). Rejected at the boundary otherwise.
    """

    predicate: str
    value: Any  # JSON-compatible value (str, int, float, list, dict, None)
    confidence: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    """A claim bound to its source span within the chunk."""

    claim: ClaimAtom
    span: Span  # NOT NULL — constraint L5


@dataclass(frozen=True, slots=True)
class ExtractedChunk:
    """Result of extracting structured information from one chunk.

    An empty ``claims`` list is valid — the chunk might contain no
    citizen-affecting problem statements.
    """

    ord: int
    text: str
    claims: list[ExtractedClaim]


@dataclass(frozen=True, slots=True)
class Extraction:
    """Full extraction result for one artifact (across all its chunks)."""

    artifact_id: str  # UUID-as-string for simplicity in the domain layer
    chunks: list[ExtractedChunk]
    prompt_ver: str = "0.0.0"
