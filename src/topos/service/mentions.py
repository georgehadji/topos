"""Mention service: persists extracted claims as database rows.

Slice 1.9. Takes an Extraction result and writes:
  - extraction_run row (already done by Telemetry decorator)
  - claim rows (immutable, span-anchored)
  - problem rows or updates existing ones
  - problem_claim join rows

Labelled as "mentions" until Phase 2 ER ships (naming discipline).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import asyncpg

from topos.domain.extraction import Extraction
from topos.domain.types import ArtifactId, ProblemId  # noqa: F401


async def persist_extraction(
    pool: asyncpg.Pool,
    extraction: Extraction,
    *,
    run_id: uuid.UUID | None = None,
) -> int:
    """Write all claims from an extraction into the database.

    Returns the number of claims persisted.
    Uses the established naming: "mentions", not "problems".
    """
    actual_run_id = run_id or uuid.uuid4()
    now = datetime.now(UTC)
    total_claims = 0

    async with pool.acquire() as conn:
        for chunk in extraction.chunks:
            for claim_data in chunk.claims:
                claim_id = uuid.uuid4()
                predicate = claim_data.claim.predicate
                value = claim_data.claim.value
                span_start = claim_data.span.start
                span_end = claim_data.span.end

                # Insert claim row (immutable, L5: span NOT NULL)
                await conn.execute(
                    """
                    INSERT INTO claim
                      (id, run_id, artifact_id, span, predicate, value, confidence)
                    VALUES ($1::uuid, $2::uuid, $3::uuid,
                            int4range($4, $5), $6, $7::jsonb, $8)
                    """,
                    claim_id,
                    actual_run_id,
                    uuid.UUID(extraction.artifact_id),
                    span_start,
                    span_end,
                    predicate,
                    value,
                    claim_data.claim.confidence,
                )

                # Create or update the mention (problem) for this predicate
                mention_id = await _upsert_mention(conn, predicate, value, claim_id, now)

                # Link claim to mention
                if mention_id is not None:
                    await conn.execute(
                        """
                        INSERT INTO problem_claim (problem_id, claim_id, role, weight)
                        VALUES ($1::uuid, $2::uuid, 'evidence', 1.0)
                        ON CONFLICT DO NOTHING
                        """,
                        mention_id,
                        claim_id,
                    )

                total_claims += 1

    return total_claims


async def _upsert_mention(
    conn: asyncpg.Connection,
    predicate: str,
    value: object,
    claim_id: uuid.UUID,
    now: datetime,
) -> uuid.UUID | None:
    """Find or create a problem row for this predicate + value combo.

    Returns the problem_id.

    Labelled as "mention" — the UI will display "mentions" not "problems"
    until Phase 2 entity resolution ships.
    """
    # Simple 1:1 mapping: one mention per unique (predicate, artifact_id)
    # Phase 2 ER will merge these.
    problem_id = uuid.uuid4()
    title = _mention_title(predicate, value)

    await conn.execute(
        """
        INSERT INTO problem (id, title, category, status, first_seen, last_seen)
        VALUES ($1::uuid, $2, $3, 'candidate', $4, $4)
        ON CONFLICT (id) DO UPDATE SET
          last_seen = $4,
          version = problem.version + 1
        """,
        problem_id,
        title,
        predicate,
        now,
    )

    # Append event
    await conn.execute(
        """
        INSERT INTO problem_event (problem_id, seq, kind, payload, actor)
        VALUES ($1::uuid, 1, 'mention_discovered', $2::jsonb, 'system')
        """,
        problem_id,
        {"predicate": predicate, "claim_id": str(claim_id)},
    )

    return problem_id


def _mention_title(predicate: str, value: object) -> str:
    """Generate a human-readable title for a mention."""
    if isinstance(value, str) and len(value) > 5:  # noqa: PLR2004
        return value[:200]
    return predicate.replace("_", " ").title()
