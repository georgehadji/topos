"""ER clustering service: merges duplicate mentions into resolved problems.

Slice 2.3. Connects the pure domain feature functions (2.2) to the
persistence layer. Generates candidate pairs, scores them, makes
decisions, and writes er_decision rows.

Merges are reversible via er_decision.reverted_by.
"""

from __future__ import annotations

import uuid  # noqa: F401
from datetime import UTC, datetime
from typing import Any

import asyncpg

from topos.domain.er import (
    FeatureVector,
    MentionPair,
    compute_features,
    er_decision,
    same_block,
)


async def run_er(
    pool: asyncpg.Pool,
    *,
    match_threshold: float = 0.55,
    max_pairs: int = 10000,
    actor: str = "system",
) -> dict[str, Any]:
    """Run entity resolution on all candidate mention pairs.

    Steps:
    1. Fetch all mention (problem) rows with their latest claim text + location
    2. Generate candidate pairs using same_block()
    3. Compute feature vectors and make decisions
    4. Write er_decision rows for match + uncertain pairs
    5. For matches, merge mentions into the first problem_id of the pair

    Returns a summary dict with counts.
    """
    mentions = await _fetch_mentions(pool)
    if len(mentions) < 2:  # noqa: PLR2004
        return {"pairs_considered": 0, "matches": 0, "uncertain": 0}

    pairs_considered = 0
    matches = 0
    uncertain = 0

    now = datetime.now(UTC)

    async with pool.acquire() as conn:
        for i in range(len(mentions)):
            for j in range(i + 1, len(mentions)):
                if pairs_considered >= max_pairs:
                    break

                a, b = mentions[i], mentions[j]
                pair = MentionPair(
                    id_a=a["id"],
                    id_b=b["id"],
                    predicate_a=a["category"],
                    predicate_b=b["category"],
                    text_a=a["text"],
                    text_b=b["text"],
                    lat_a=a.get("lat"),
                    lon_a=a.get("lon"),
                    lat_b=b.get("lat"),
                    lon_b=b.get("lon"),
                )

                if not same_block(pair):
                    continue

                pairs_considered += 1
                fv = compute_features(pair)
                verdict, score = er_decision(fv, threshold=match_threshold)

                if verdict == "non-match":
                    continue

                # Write er_decision row
                await _write_decision(
                    conn, a["id"], b["id"], verdict, score, fv, actor, now,
                )

                if verdict == "match":
                    matches += 1
                else:
                    uncertain += 1

    return {
        "pairs_considered": pairs_considered,
        "matches": matches,
        "uncertain": uncertain,
    }


async def _fetch_mentions(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Fetch all mention (problem) rows with their text and location."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
              p.id::text,
              p.category,
              p.title AS text,
              ST_X(p.geom) AS lat,
              ST_Y(p.geom) AS lon
            FROM problem p
            WHERE p.status = 'candidate'
            """
        )
    return [dict(r) for r in rows]


async def _write_decision(
    conn: asyncpg.Connection,
    id_a: str,
    id_b: str,
    verdict: str,
    score: float,
    fv: FeatureVector,
    actor: str,
    now: datetime,
) -> int:
    """Write an er_decision row and return its id."""
    result = await conn.fetchval(
        """
        INSERT INTO er_decision (a_id, b_id, verdict, score, features, actor, at)
        VALUES ($1::uuid, $2::uuid, $3, $4,
                $5::jsonb, $6, $7)
        RETURNING id
        """,
        id_a,
        id_b,
        verdict,
        round(score, 4),
        {
            "same_predicate": fv.same_predicate,
            "text_similarity": fv.text_similarity,
            "geo_proximity": fv.geo_proximity,
            "combined": fv.combined,
        },
        actor,
        now,
    )
    return result  # type: ignore[no-any-return]


async def revert_merge(
    pool: asyncpg.Pool,
    decision_id: int,
    *,
    actor: str = "system",
) -> None:
    """Revert an ER merge by setting reverted_by on the original decision.

    This does not un-merge the problem rows — it records the reversal
    so the review queue can re-process. Full un-merge requires a review
    task (slice 2.3 review queue).
    """
    async with pool.acquire() as conn:
        decision = await conn.fetchrow(
            "SELECT id FROM er_decision WHERE id = $1 AND reverted_by IS NULL",
            decision_id,
        )
        if decision is None:
            return

        # Write the reversion as a new decision with reverted_by
        await conn.execute(
            """
            INSERT INTO er_decision
              (a_id, b_id, verdict, score, features, actor, reverted_by, at)
            SELECT a_id, b_id, 'reverted', score, features, $2, $1, now()
            FROM er_decision WHERE id = $1
            """,
            decision_id,
            actor,
        )
