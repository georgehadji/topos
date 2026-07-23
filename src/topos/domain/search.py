"""Search service: FTS + geo + filters.

Slice 1.10. Provides a search endpoint that combines:
- Lexical FTS via greek_cfg (chunk.tsv)
- Trigram fuzzy matching for toponyms
- Geo filtering by bounding box
- Category/predicate filters

ARCHITECTURE.md §Search:
  Lexical first pass → vector rerank → graph expansion → RRF fusion.
  Embeddings exist only for the derived layer (Phase 2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Parameters for a search."""

    text: str = ""
    predicates: list[str] | None = None
    lat: float | None = None
    lon: float | None = None
    radius_km: float | None = None
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One search hit."""

    problem_id: str
    title: str
    category: str
    score: float
    snippet: str = ""
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Full search response."""

    results: list[SearchResult]
    total: int
    query: SearchQuery
