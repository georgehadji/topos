"""Graph types: problems, authorities, and their relationships.

Pure domain. Leverages the edge table (ARCHITECTURE.md ADR-002)
for recursive CTE traversal.

The graph shows:
  - Problems linked to authorities
  - Problems linked to other problems (related, caused_by, duplicates)
  - Problems linked to sources
  - Authorities linked to parent authorities
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One node in the problem graph."""

    id: str
    type: str  # "problem", "authority", "source"
    label: str
    score: float | None = None


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One edge connecting two nodes."""

    source: str
    target: str
    relation: str  # e.g. "responsible_for", "related_to", "caused_by"
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class GraphResult:
    """Result of a graph traversal query."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
