"""Assemble a QuestionBrief for a stored problem.

The only job here is reading rows and handing them to the pure renderer in
``domain/question.py``. No text is composed at this layer.

Facts are taken verbatim from claim values — the source's own words — rather
than summarised, so the resulting question says what the document said. A
paraphrase would put words in a minister's inbox that no document contains.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from topos.domain.question import QuestionBrief, SourceCitation, render_question

logger = logging.getLogger(__name__)

__all__ = ["build_brief", "draft_for_problem"]

# Claim keys that read as a statement of fact worth reciting.
_FACT_KEYS = (
    "description",
    "issue",
    "cause",
    "reason",
    "status",
    "affected_area",
    "affected_areas",
    "affected_streets",
    "roads_affected",
    "duration",
)

_MAX_FACTS = 6

_BRIEF_QUERY = """
SELECT
  p.title,
  p.category,
  p.first_seen::date  AS first_seen,
  p.last_seen::date   AS last_seen,
  a.name              AS authority,
  COUNT(DISTINCT c.artifact_id)                                        AS recurrence,
  COALESCE(json_agg(DISTINCT c.value::text) FILTER (WHERE c.value IS NOT NULL), '[]')::text
                                                                       AS claim_values,
  COALESCE(json_agg(DISTINCT art.uri) FILTER (WHERE art.uri IS NOT NULL), '[]')::text
                                                                       AS uris
FROM problem p
LEFT JOIN authority a      ON a.id = p.authority_id
LEFT JOIN problem_claim pc ON pc.problem_id = p.id
LEFT JOIN claim c          ON c.id = pc.claim_id AND c.retracted_at IS NULL
LEFT JOIN artifact art     ON art.id = c.artifact_id
WHERE p.id = $1::uuid
GROUP BY p.id, p.title, p.category, p.first_seen, p.last_seen, a.name
"""


async def draft_for_problem(pool: asyncpg.Pool, problem_id: str) -> str | None:
    """Full draft for one problem, or None when the problem does not exist."""
    brief = await build_brief(pool, problem_id)
    return render_question(brief) if brief is not None else None


async def build_brief(pool: asyncpg.Pool, problem_id: str) -> QuestionBrief | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_BRIEF_QUERY, problem_id)
    if row is None:
        return None

    values = _load_values(row["claim_values"])
    return QuestionBrief(
        title=str(row["title"]),
        category=str(row["category"]),
        citations=tuple(_citations(row["uris"])),
        authority=row["authority"],
        location=_first(values, ("location", "affected_area", "municipality")),
        facts=tuple(_facts(values)),
        budget_eur=_budget(values),
        first_seen=_as_date(row["first_seen"]),
        last_seen=_as_date(row["last_seen"]),
        recurrence=int(row["recurrence"] or 0),
    )


def _load_values(raw: Any) -> list[dict[str, Any]]:
    """Claim values arrive as jsonb text, each element itself JSON-encoded."""
    outer: Any = raw
    if isinstance(raw, str):
        try:
            outer = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(outer, list):
        return []

    out: list[dict[str, Any]] = []
    for item in outer:
        value = item
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                continue
        if isinstance(value, dict):
            out.append(value)
    return out


def _citations(raw: Any) -> list[SourceCitation]:
    uris = raw
    if isinstance(raw, str):
        try:
            uris = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(uris, list):
        return []
    return [SourceCitation(uri=str(u)) for u in uris if u]


def _facts(values: list[dict[str, Any]]) -> list[str]:
    """Verbatim fragments, deduplicated, order preserved."""
    seen: dict[str, None] = {}
    for value in values:
        for key in _FACT_KEYS:
            if key not in value:
                continue
            rendered = _stringify(value[key])
            if rendered and len(rendered) > 3:  # noqa: PLR2004
                seen.setdefault(rendered.rstrip(".") + ".", None)
    return list(seen)[:_MAX_FACTS]


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def _first(values: list[dict[str, Any]], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        for value in values:
            if key in value:
                rendered = _stringify(value[key])
                if rendered:
                    return rendered
    return None


def _budget(values: list[dict[str, Any]]) -> Decimal | None:
    """Largest stated amount — the same contract is often restated."""
    amounts: list[Decimal] = []
    for value in values:
        for key, item in value.items():
            if "budget" not in key.lower() and "cost" not in key.lower():
                continue
            try:
                amount = Decimal(str(item))
            except (ArithmeticError, ValueError, TypeError):
                continue
            if amount > 0:
                amounts.append(amount)
    return max(amounts) if amounts else None


def _as_date(value: Any) -> date | None:
    return value if isinstance(value, date) else None
