"""ER clustering service: finds and scores duplicate mention pairs.

Slice 2.3. Connects the pure domain feature functions (2.2) to the
persistence layer. Generates candidate pairs, scores them, makes decisions,
writes er_decision rows, and delegates matches to service/er_merge.py
(split out purely for the 400-line file cap — see that module's docstring).

Merges are reversible via er_decision.reverted_by (ARCHITECTURE.md >
Immutability rules): a match sets the loser's status to 'merged' and moves
its problem_claim rows onto the winner; revert_merge undoes exactly that.
"""

from __future__ import annotations

import json
import uuid
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
from topos.service.er_merge import merge as _merge
from topos.service.er_merge import revert_merge

__all__ = ["revert_merge", "run_er"]

# same_block() returns True whenever two problems share a category, so this
# is O(n^2) over every candidate pair on each run.
# ponytail: fine at the current n (single digits to low hundreds). A
# geo/time-bucketed blocking key is the upgrade path once a source backfill
# pushes candidate counts into the thousands.
_DEFAULT_MAX_PAIRS = 10000


async def run_er(
    pool: asyncpg.Pool,
    *,
    match_threshold: float = 0.55,
    max_pairs: int = _DEFAULT_MAX_PAIRS,
    actor: str = "system",
) -> dict[str, Any]:
    """Run entity resolution on all candidate mention pairs.

    Steps:
    1. Fetch all mention (problem) rows with their evidence text + location
    2. Generate candidate pairs using same_block()
    3. Compute feature vectors and make decisions
    4. Write er_decision rows for match + uncertain pairs
    5. For matches, merge the later-seen problem into the earlier one

    Returns a summary dict with counts. Idempotent: a merged problem's status
    is no longer 'candidate', so it drops out of the next run's input set —
    re-running after a merge does not re-merge or double-count it.
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

                decision_id = await _write_decision(
                    conn,
                    a["id"],
                    b["id"],
                    verdict,
                    score,
                    fv,
                    actor,
                    now,
                )

                if verdict == "match":
                    matches += 1
                    winner, loser = _older_first(a, b)
                    await _merge(
                        conn,
                        winner_id=uuid.UUID(winner["id"]),
                        loser_id=uuid.UUID(loser["id"]),
                        decision_id=decision_id,
                        actor=actor,
                    )
                else:
                    uncertain += 1

    return {
        "pairs_considered": pairs_considered,
        "matches": matches,
        "uncertain": uncertain,
    }


def _older_first(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Deterministic winner selection: earlier first_seen survives.

    Not row order (that depends on the SQL fetch, which is not guaranteed
    stable) — first_seen is a real fact about the data.
    """
    return (a, b) if a["first_seen"] <= b["first_seen"] else (b, a)


async def _fetch_mentions(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Fetch all candidate problem rows with evidence text and location.

    Evidence text is every linked claim's value, not problem.title — the
    title is derived from the predicate for any dict-valued claim
    (mentions.py:_mention_title), so same-category problems end up with
    identical titles and token overlap would compare nothing.

    ST_X is longitude, ST_Y is latitude for a geometry(Point, 4326) — the
    previous version of this query had the aliases swapped, so every
    downstream distance calculation used lat/lon transposed.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
              p.id::text,
              p.category,
              p.first_seen,
              COALESCE(string_agg(c.value::text, ' '), p.title) AS text,
              ST_Y(p.geom) AS lat,
              ST_X(p.geom) AS lon
            FROM problem p
            LEFT JOIN problem_claim pc ON pc.problem_id = p.id
            LEFT JOIN claim c ON c.id = pc.claim_id
            WHERE p.status = 'candidate'
            GROUP BY p.id, p.category, p.first_seen, p.title, p.geom
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
        # No jsonb codec is registered on this pool (see claim.value handling
        # in handlers.py) -- asyncpg needs a str for a ::jsonb param, not a
        # dict. This was unreachable before run_er had a caller, so it was
        # never exercised against a real connection.
        json.dumps(
            {
                "same_predicate": fv.same_predicate,
                "text_similarity": fv.text_similarity,
                "geo_proximity": fv.geo_proximity,
                "combined": fv.combined,
            }
        ),
        actor,
        now,
    )
    return result  # type: ignore[no-any-return]
