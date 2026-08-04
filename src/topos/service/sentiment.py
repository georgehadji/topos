"""Classify coverage sentiment per problem and persist a snapshot.

Reads the document text behind each problem's claims, hands it to an injected
``SentimentAnalyzer`` port, folds the labels with the pure aggregator, writes
one row.

Degrades honestly: if the analyser raises, that problem gets **no row**, not a
neutral one. Absence of a measurement and a measurement of neutrality are
different facts and the schema keeps them different.
"""

from __future__ import annotations

import json
import logging

import asyncpg

from topos.domain.sentiment import SentimentLabel, aggregate
from topos.service.ports import SentimentAnalyzer

logger = logging.getLogger(__name__)

__all__ = ["score_sentiment"]

# Per problem. Coverage sentiment saturates quickly and each text costs tokens.
_MAX_DOCS = 12

_DOCS_QUERY = """
SELECT
  p.id::text AS problem_id,
  COALESCE(
    json_agg(DISTINCT left(d.text, 1200)) FILTER (WHERE d.text IS NOT NULL),
    '[]'
  )::text AS texts
FROM problem p
JOIN problem_claim pc ON pc.problem_id = p.id
JOIN claim c          ON c.id = pc.claim_id AND c.retracted_at IS NULL
JOIN document d       ON d.artifact_id = c.artifact_id
WHERE p.status NOT IN ('merged', 'retracted')
GROUP BY p.id
"""

_INSERT = """
INSERT INTO sentiment_snapshot
  (problem_id, at, label, sample_size, negative, neutral, positive, model, prompt_ver)
VALUES ($1::uuid, now(), $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (problem_id, at) DO NOTHING
"""


async def score_sentiment(
    pool: asyncpg.Pool,
    analyzer: SentimentAnalyzer,
    *,
    model: str,
    prompt_ver: str,
) -> dict[str, int]:
    """Classify every live problem's coverage. Returns counts for logging."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_DOCS_QUERY)

        written = 0
        skipped = 0
        for row in rows:
            try:
                texts = json.loads(row["texts"])
            except (ValueError, TypeError):
                texts = []
            texts = [t for t in texts if isinstance(t, str) and t.strip()][:_MAX_DOCS]
            if not texts:
                continue

            try:
                labels = await analyzer(texts)
            except Exception as exc:
                logger.warning(
                    "sentiment.analyzer_failed problem=%s err=%s", row["problem_id"], exc
                )
                skipped += 1
                continue

            summary = aggregate(labels)
            if summary.total == 0 or summary.dominant is None:
                # A tie is not a finding. Recording one would invent a verdict.
                skipped += 1
                continue

            await conn.execute(
                _INSERT,
                row["problem_id"],
                str(summary.dominant),
                summary.total,
                summary.negative,
                summary.neutral,
                summary.positive,
                model,
                prompt_ver,
            )
            written += 1

    logger.info("sentiment.completed written=%d skipped=%d", written, skipped)
    return {"written": written, "skipped": skipped}


def label_of(value: str) -> SentimentLabel | None:
    """Parse a stored label back into the enum, or None if unrecognised."""
    try:
        return SentimentLabel(value)
    except ValueError:
        return None
