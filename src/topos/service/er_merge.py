"""Applying and reversing one ER merge decision.

Split out of service/er.py (which finds and scores candidate pairs) purely
for file size — the 400-line cap (Makefile > filesize) is about context
economics, not a claim that these are separate concerns. run_er is the only
caller of _merge; revert_merge is the administrative undo path.
"""

from __future__ import annotations

import json
import uuid

import asyncpg

from topos.service.mentions import append_event


async def merge(
    conn: asyncpg.Connection,
    *,
    winner_id: uuid.UUID,
    loser_id: uuid.UUID,
    decision_id: int,
    actor: str,
) -> None:
    """Merge loser into winner: move claims, retire loser, log both sides.

    Only claim_ids not already linked to the winner are moved — the
    problem_claim primary key is (problem_id, claim_id), so blindly
    repointing every row could collide if the winner already carries one of
    the same claims (evidence can be linked to more than one problem).
    Recording exactly which claim_ids moved is what lets revert_merge put
    them back precisely, rather than guessing from whatever the winner holds
    at revert time.
    """
    already_merged = await conn.fetchval(
        "SELECT status = 'merged' FROM problem WHERE id = $1::uuid", loser_id
    )
    if already_merged:
        return

    moved_rows = await conn.fetch(
        """
        SELECT claim_id FROM problem_claim
        WHERE problem_id = $1::uuid
          AND claim_id NOT IN (
            SELECT claim_id FROM problem_claim WHERE problem_id = $2::uuid
          )
        """,
        loser_id,
        winner_id,
    )
    moved_ids = [r["claim_id"] for r in moved_rows]

    if moved_ids:
        await conn.execute(
            """
            UPDATE problem_claim SET problem_id = $1::uuid
            WHERE problem_id = $2::uuid AND claim_id = ANY($3::uuid[])
            """,
            winner_id,
            loser_id,
            moved_ids,
        )

    await conn.execute(
        "UPDATE problem SET status = 'merged' WHERE id = $1::uuid",
        loser_id,
    )

    moved_str = [str(c) for c in moved_ids]
    await append_event(
        conn,
        loser_id,
        "merged_into",
        {"winner_id": str(winner_id), "decision_id": decision_id, "moved_claim_ids": moved_str},
        actor=actor,
    )
    await append_event(
        conn,
        winner_id,
        "absorbed_duplicate",
        {"loser_id": str(loser_id), "decision_id": decision_id, "moved_claim_ids": moved_str},
        actor=actor,
    )


async def revert_merge(
    pool: asyncpg.Pool,
    decision_id: int,
    *,
    actor: str = "system",
) -> bool:
    """Revert an ER merge: restore the loser's status and move its claims back.

    Returns True if a merge was reverted, False if there was nothing to
    revert (unknown decision, a non-'match' verdict, or already reverted).

    This bypasses domain.problem.can_transition deliberately — MERGED is a
    terminal state in the normal lifecycle (nothing transitions out of it),
    but a revert is an explicit administrative undo, not a queue-driven
    transition, and ARCHITECTURE.md specifies exactly this escape hatch:
    "Entity-resolution merges are er_decision rows and are reversible via
    reverted_by. An irreversible merge destroys data; merges are wrong often."
    """
    async with pool.acquire() as conn:
        decision = await conn.fetchrow(
            """
            SELECT id, a_id, b_id FROM er_decision
            WHERE id = $1 AND verdict = 'match' AND reverted_by IS NULL
            """,
            decision_id,
        )
        if decision is None:
            return False

        a_status = await conn.fetchval(
            "SELECT status FROM problem WHERE id = $1::uuid", decision["a_id"]
        )
        loser_id, winner_id = (
            (decision["a_id"], decision["b_id"])
            if a_status == "merged"
            else (decision["b_id"], decision["a_id"])
        )
        b_status = (
            a_status
            if a_status == "merged"
            else await conn.fetchval(
                "SELECT status FROM problem WHERE id = $1::uuid", decision["b_id"]
            )
        )
        if a_status != "merged" and b_status != "merged":
            # Nothing to undo — e.g. the loser was already reverted by a
            # different decision, or this row never actually merged anything.
            return False

        # Read moved_claim_ids from the merge event this decision wrote,
        # rather than trusting whatever the winner currently holds — the
        # winner may have absorbed other merges since.
        event = await conn.fetchrow(
            """
            SELECT payload FROM problem_event
            WHERE problem_id = $1::uuid AND kind = 'merged_into'
            ORDER BY seq DESC LIMIT 1
            """,
            loser_id,
        )
        moved_ids: list[uuid.UUID] = []
        if event is not None:
            # asyncpg returns jsonb as a raw string absent an explicit codec
            # (same as claim.value elsewhere in this codebase — see
            # handlers.py's handle_extracted).
            raw_payload = event["payload"]
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
            moved_ids = [uuid.UUID(c) for c in payload.get("moved_claim_ids", [])]

        if moved_ids:
            await conn.execute(
                """
                UPDATE problem_claim SET problem_id = $1::uuid
                WHERE problem_id = $2::uuid AND claim_id = ANY($3::uuid[])
                """,
                loser_id,
                winner_id,
                moved_ids,
            )

        await conn.execute(
            "UPDATE problem SET status = 'candidate' WHERE id = $1::uuid",
            loser_id,
        )

        restored = [str(c) for c in moved_ids]
        await append_event(
            conn,
            loser_id,
            "merge_reverted",
            {"decision_id": decision_id, "restored_claim_ids": restored},
            actor=actor,
        )
        await append_event(
            conn,
            winner_id,
            "merge_reverted_from",
            {"loser_id": str(loser_id), "decision_id": decision_id},
            actor=actor,
        )

        # Two-step, not a single INSERT ... reverted_by=$1: reverted_by is a
        # forward reference (the row that reverted THIS one), so it belongs
        # on the ORIGINAL row, set after the reversal row exists. The
        # previous version set it on the new row instead, so the original
        # decision's reverted_by stayed NULL forever and the idempotency
        # guard above never actually blocked a second revert.
        new_id = await conn.fetchval(
            """
            INSERT INTO er_decision (a_id, b_id, verdict, score, features, actor, at)
            SELECT a_id, b_id, 'reverted', score, features, $2, now()
            FROM er_decision WHERE id = $1
            RETURNING id
            """,
            decision_id,
            actor,
        )
        await conn.execute(
            "UPDATE er_decision SET reverted_by = $2 WHERE id = $1",
            decision_id,
            new_id,
        )

    return True
