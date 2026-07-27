"""Graph explorer: queries the edge table with recursive CTEs.

Leverages Postgres recursive CTEs for graph traversal (ADR-002).
Returns nodes and edges for the React graph explorer component.
"""

from __future__ import annotations

import asyncpg

from topos.domain.graph import GraphEdge, GraphNode, GraphResult


class GraphRepo:
    """Graph query implementation via asyncpg."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def explore(self, problem_id: str, depth: int = 2) -> GraphResult:
        """Traverse the graph starting from a problem.

        Uses a recursive CTE to walk edges up to *depth* hops.
        Returns all reachable nodes and edges.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH RECURSIVE graph_walk AS (
                  -- Base: start from the given problem
                  SELECT src_id, src_type, rel, dst_id, dst_type, 1 AS hop
                  FROM edge
                  WHERE src_id = $1::uuid OR dst_id = $1::uuid

                  UNION

                  -- Recursive: expand outward
                  SELECT e.src_id, e.src_type, e.rel, e.dst_id, e.dst_type, gw.hop + 1
                  FROM edge e
                  INNER JOIN graph_walk gw
                    ON (e.src_id = gw.dst_id OR e.dst_id = gw.src_id)
                  WHERE gw.hop < $2
                )
                SELECT DISTINCT src_id, src_type, rel, dst_id, dst_type
                FROM graph_walk
                """,
                problem_id,
                depth,
            )

        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []

        for r in rows:
            src_id = str(r["src_id"])
            dst_id = str(r["dst_id"])
            src_type = r["src_type"]
            dst_type = r["dst_type"]

            if src_id not in nodes:
                nodes[src_id] = GraphNode(id=src_id, type=src_type, label=src_id[:8])
            if dst_id not in nodes:
                nodes[dst_id] = GraphNode(id=dst_id, type=dst_type, label=dst_id[:8])

            edges.append(GraphEdge(source=src_id, target=dst_id, relation=r["rel"]))

        return GraphResult(nodes=list(nodes.values()), edges=edges)

    async def problem_graph(self, depth: int = 1) -> GraphResult:  # noqa: ARG002
        """Return the full problem graph (all problems + their relationships)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT src_id::text, src_type, rel, dst_id::text, dst_type
                FROM edge
            """)

            problems = await conn.fetch("SELECT id::text, title, category FROM problem LIMIT 200")

        node_map: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []

        for p in problems:
            pid = p["id"]
            node_map[pid] = GraphNode(id=pid, type="problem", label=p["title"][:60], score=0.5)

        for r in rows:
            src_id = r["src_id"]
            dst_id = r["dst_id"]
            for rid in (src_id, dst_id):
                if rid not in node_map:
                    node_map[rid] = GraphNode(
                        id=rid, type=r.get("src_type", "unknown"), label=rid[:8]
                    )
            edges.append(GraphEdge(source=src_id, target=dst_id, relation=r["rel"]))

        return GraphResult(nodes=list(node_map.values()), edges=edges)
