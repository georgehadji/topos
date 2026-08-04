"""Run the scoring DAG over stored problems and persist the snapshots.

``domain/scoring.py`` has been complete and tested since Phase 2 and had zero
callers: ``score_problem`` was never invoked and ``score_snapshot`` was never
written. Everything downstream that ranks — ``service/recommendations.py``,
the MCP ``top_problems`` tool — reads that empty table, so "which problem
matters most", the one question the product exists to answer, returned
nothing. This module is the missing link.

Which inputs are real, and which are policy:

* ``reach`` — measured. COUNT(DISTINCT artifact_id) over the problem's
  non-retracted claims, i.e. how many *independent documents* reported it.
  Deliberately not the claim count: three claims off one article is one
  source, and treating it as three would let a single wordy story outrank a
  genuinely corroborated problem.
* ``evidence_strength`` — measured. Mean claim confidence.
* ``cost`` — measured when present. Greek council minutes state contract
  values, and the extractor already captures them as ``*_budget`` fields.
* ``severity`` — policy. See ``domain/severity.py``.
* ``trend``, ``tractability``, ``leverage`` — left None. Nothing in the data
  supports them yet, and the DAG handles None. Trend in particular needs a
  history of snapshots, which only exists once this has run for a while.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from typing import Any

import asyncpg

from topos.domain.scoring import MeasuredInputs, ScoreSnapshot, score_problem
from topos.domain.severity import BASELINE_VER, severity_for

logger = logging.getLogger(__name__)

__all__ = ["score_all"]

# Claim value keys that carry a monetary amount, in EUR.
_COST_KEYS = (
    "project_budget",
    "original_budget",
    "contract_budget",
    "budget",
    "cost",
    "amount",
)

_INPUTS_QUERY = """
SELECT
  p.id::text                                        AS problem_id,
  p.category,
  COUNT(DISTINCT c.artifact_id)                     AS reach,
  AVG(c.confidence)                                 AS evidence_strength,
  COALESCE(
    json_agg(c.value ORDER BY c.id) FILTER (WHERE c.value IS NOT NULL),
    '[]'
  )::text                                           AS claim_values
FROM problem p
LEFT JOIN problem_claim pc ON pc.problem_id = p.id
LEFT JOIN claim c          ON c.id = pc.claim_id AND c.retracted_at IS NULL
WHERE p.status NOT IN ('merged', 'retracted')
GROUP BY p.id, p.category
"""


async def score_all(pool: asyncpg.Pool) -> dict[str, int]:
    """Score every live problem and append a snapshot for each.

    Idempotent per run only in the sense that re-running appends a new row at
    a new ``at``; ``score_snapshot`` is history, keyed (problem_id, at), and
    readers take the latest. That is what makes trend computable later.

    Returns counts for the caller to log.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(_INPUTS_QUERY)

        scored = 0
        for row in rows:
            snapshot = _score_row(dict(row))
            await _write_snapshot(conn, snapshot)
            scored += 1

    logger.info("scoring.completed problems=%d", scored)
    return {"scored": scored}


def _score_row(row: dict[str, Any]) -> ScoreSnapshot:
    """Turn one aggregated DB row into a full scorecard."""
    reach = int(row["reach"] or 0)
    inputs = MeasuredInputs(
        severity=severity_for(str(row["category"] or "")),
        # 0 sources means the problem has no surviving claim — report it as
        # unknown rather than as a measured zero, which would be a real
        # "nobody reported this" finding and is not what happened.
        reach=reach or None,
        trend=None,
        evidence_strength=_as_decimal(row["evidence_strength"]),
        tractability=None,
        cost=_extract_cost(row["claim_values"]),
        leverage=None,
    )
    return score_problem(str(row["problem_id"]), inputs)


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _extract_cost(raw: Any) -> Decimal | None:
    """Largest monetary figure across the problem's claims, if any.

    Largest rather than summed: the same contract value is often restated
    across several claims from one document, so summing would inflate it.
    """
    values = _load_claim_values(raw)
    amounts: list[Decimal] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        for key, item in value.items():
            if not any(marker in key.lower() for marker in _COST_KEYS):
                continue
            amount = _as_decimal(item)
            if amount is not None and amount > 0:
                amounts.append(amount)
    return max(amounts) if amounts else None


def _load_claim_values(raw: Any) -> list[Any]:
    """The aggregated claim values, which arrive as jsonb text.

    Each element may itself be a JSON *string* rather than an object: claims
    are written with ``json.dumps`` into a jsonb column, and no jsonb codec is
    registered on the pool, so a double-encoded layer is normal here.
    """
    outer: Any = raw
    if isinstance(raw, str):
        try:
            outer = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(outer, list):
        return []

    values: list[Any] = []
    for item in outer:
        if isinstance(item, str):
            try:
                values.append(json.loads(item))
            except (ValueError, TypeError):
                continue
        else:
            values.append(item)
    return values


async def _write_snapshot(conn: asyncpg.Connection, snapshot: ScoreSnapshot) -> None:
    """Append one scorecard. The whole DAG goes in, not just priority —
    ARCHITECTURE.md requires every node be recorded so a ranking can be
    explained and audited after the fact."""
    scores = {k: _jsonable(v) for k, v in asdict(snapshot).items() if k != "problem_id"}
    scores["severity_baseline_ver"] = BASELINE_VER

    await conn.execute(
        """
        INSERT INTO score_snapshot (problem_id, at, scores, formula_ver)
        VALUES ($1::uuid, now(), $2::jsonb, $3)
        ON CONFLICT (problem_id, at) DO NOTHING
        """,
        snapshot.problem_id,
        json.dumps(scores),
        snapshot.formula_ver,
    )


def _jsonable(value: Any) -> Any:
    """Decimals are not JSON-serialisable; keep them as strings-of-numbers so
    the numeric casts in recommendations.py's query still work."""
    if isinstance(value, Decimal):
        return float(value)
    return value
