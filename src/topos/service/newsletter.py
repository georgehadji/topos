# ruff: noqa: RUF001
"""Newsletter digest: every finding, grouped by the day it was first seen.

The export commands next door emit NDJSON for machines. This emits Markdown
for a person — a constituency staffer who wants to know what Topos found this
week without opening psql.

Two rules carried over from the rest of the pipeline:

* Nothing is invented. Every line is a column from the database. A problem with
  no location prints no location; a claim with no authority prints no
  authority. There is no prose-generation step and no LLM in this module.
* Merged duplicates are counted, not printed. ``status = 'merged'`` means
  entity resolution folded the row into a surviving problem (see
  ``service/er_merge.py``), so printing it would double-report the incident.
  The count still appears in the footer, because "we deduplicated two reports"
  is itself information the reader wants.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any

import asyncpg

__all__ = ["build_newsletter"]

# Longest first so a claim's own words win over the generic fallbacks.
_SUMMARY_KEYS = (
    "description",
    "issue",
    "cause",
    "reason",
    "context",
    "program",
    "status",
)

# Rendered under the summary as "label: value" detail lines, in this order.
_DETAIL_KEYS = (
    "location",
    "affected_area",
    "affected_areas",
    "affected_streets",
    "roads_affected",
    "line_affected",
    "affected_line",
    "service",
    "duration",
    "time",
    "timeframe_mentioned",
    "restoration_timeframe",
    "affected_parties",
    "authority_responsible",
    "authority_mentioned",
    "original_budget",
    "project_budget",
    "contract_budget_5th",
    "contract_budget_1st_2nd_3rd",
    "extension_requested",
    "extension_approved",
)

_QUERY = """
SELECT
  p.id::text            AS problem_id,
  p.title,
  p.category,
  p.status,
  p.geo_conf,
  ST_Y(p.geom)          AS lat,
  ST_X(p.geom)          AS lon,
  p.first_seen,
  a.name                AS authority,
  c.value               AS claim_value,
  c.confidence,
  art.uri,
  s.kind                AS source_kind
FROM problem p
LEFT JOIN authority a      ON a.id = p.authority_id
LEFT JOIN problem_claim pc ON pc.problem_id = p.id
LEFT JOIN claim c          ON c.id = pc.claim_id AND c.retracted_at IS NULL
LEFT JOIN artifact art     ON art.id = c.artifact_id
LEFT JOIN source s         ON s.id = art.source_id
WHERE p.status <> 'retracted'
  AND ($1::timestamptz IS NULL OR p.first_seen >= $1)
  AND ($2::timestamptz IS NULL OR p.first_seen <  $2)
ORDER BY p.first_seen, p.title
"""


def _humanise(slug: str) -> str:
    """``water_supply_disruption`` -> ``Water Supply Disruption``.

    ``str.title()`` alone capitalises the letter after every digit, turning
    ``contract_budget_5th`` into ``Contract Budget 5Th``. Ordinal suffixes stay
    lowercase.
    """
    words = []
    for word in slug.replace("_", " ").split():
        if word[:1].isdigit():
            words.append(word.lower())
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _load_value(raw: Any) -> dict[str, Any]:
    """Claim values come back as raw jsonb text — no codec is registered."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {"description": raw}
        return parsed if isinstance(parsed, dict) else {"description": str(parsed)}
    return {}


def _format_detail(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{int(value):,}" if value.is_integer() else f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value).strip()


def _summarise(value: dict[str, Any]) -> str:
    for key in _SUMMARY_KEYS:
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return " ".join(text.split())
    return ""


def _render_claim(value: dict[str, Any], confidence: float | None) -> list[str]:
    """One claim as Markdown lines: a summary, then whatever detail it carries.

    The blank line before the bullets is load-bearing: without it Pandoc reads
    them as a lazy continuation of the summary paragraph and the whole claim
    collapses into one run-on line when converted to .docx.
    """
    lines: list[str] = []
    summary = _summarise(value)
    if summary:
        suffix = f" *(confidence {confidence:.2f})*" if confidence is not None else ""
        lines.extend([f"{summary}{suffix}", ""])

    for key in _DETAIL_KEYS:
        if key not in value:
            continue
        rendered = _format_detail(value[key])
        if rendered:
            lines.append(f"- {_humanise(key)}: {rendered}")
    return lines


def _render_problem(
    problem: dict[str, Any], claims: list[dict[str, Any]], *, heading: str | None
) -> list[str]:
    """One problem block. ``heading`` is omitted when the category header above
    already says the same thing — ``mentions.py`` derives most titles straight
    from the predicate, so printing both is pure duplication."""
    lines = [f"#### {heading}", ""] if heading else []

    facts: list[str] = []
    if problem["authority"]:
        facts.append(f"**Authority:** {problem['authority']}")
    if problem["lat"] is not None and problem["lon"] is not None:
        geo_conf = problem["geo_conf"]
        conf = f" (geo confidence {float(geo_conf):.2f})" if geo_conf is not None else ""
        facts.append(f"**Location:** {problem['lat']:.4f}, {problem['lon']:.4f}{conf}")
    else:
        facts.append("**Location:** not resolved")
    if facts:
        lines.extend(["  ".join(facts), ""])

    for claim in claims:
        value = _load_value(claim["claim_value"])
        conf = claim["confidence"]
        rendered = _render_claim(value, float(conf) if conf is not None else None)
        lines.extend(rendered)
        if claim["uri"]:
            source = claim["source_kind"] or "source"
            lines.append(f"- Source ({source}): {claim['uri']}")
        lines.append("")

    return lines


def _group_by_day(
    rows: list[dict[str, Any]],
) -> dict[date, dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]]:
    """Rows are a problem x claim join — fold them back into one entry per problem."""
    days: dict[date, dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]] = defaultdict(dict)
    for row in rows:
        if row["status"] == "merged":
            continue
        seen: datetime = row["first_seen"]
        bucket = days[seen.date()]
        problem_id = row["problem_id"]
        if problem_id not in bucket:
            bucket[problem_id] = (row, [])
        if row["claim_value"] is not None:
            bucket[problem_id][1].append(row)
    return days


async def build_newsletter(
    pool: asyncpg.Pool,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    title: str = "Topos — Α΄ Θεσσαλονίκης",
) -> str:
    """Render every non-retracted finding as a dated Markdown digest.

    ``since``/``until`` bound ``problem.first_seen`` (half-open: ``since`` is
    inclusive, ``until`` exclusive). Both default to unbounded — the whole
    corpus, which is what a first run wants.
    """
    async with pool.acquire() as conn:
        raw = await conn.fetch(_QUERY, since, until)
    rows = [dict(r) for r in raw]

    merged = len({r["problem_id"] for r in rows if r["status"] == "merged"})
    days = _group_by_day(rows)
    total = sum(len(bucket) for bucket in days.values())

    lines = [f"# {title}", ""]
    if total == 0:
        lines.append("No findings in this period.")
        return "\n".join(lines) + "\n"

    span = sorted(days)
    period = (
        f"{span[0].isoformat()} – {span[-1].isoformat()}"
        if span[0] != span[-1]
        else span[0].isoformat()
    )
    lines.extend([f"**{total} findings** across {len(days)} day(s) · {period}", ""])

    for day in span:
        bucket = days[day]
        lines.extend([f"## {day.isoformat()}", ""])

        by_category: dict[str, list[str]] = defaultdict(list)
        for problem, _claims in bucket.values():
            by_category[problem["category"]].append(problem["problem_id"])

        for category in sorted(by_category):
            label = _humanise(category)
            problem_ids = by_category[category]
            lines.extend([f"### {label}", ""])
            for n, problem_id in enumerate(problem_ids, start=1):
                problem, claims = bucket[problem_id]
                title = str(problem["title"])
                # Distinct title -> show it. Same as the category -> number the
                # entries instead, so two reports don't blur into one block.
                if title.casefold() != label.casefold():
                    heading: str | None = title
                elif len(problem_ids) > 1:
                    heading = f"Report {n} of {len(problem_ids)}"
                else:
                    heading = None
                lines.extend(_render_problem(problem, claims, heading=heading))

    lines.append("---")
    lines.append("")
    footer = f"Generated from the Topos database. {total} findings reported"
    if merged:
        footer += f"; {merged} duplicate report(s) merged by entity resolution and not listed"
    lines.append(footer + ".")
    return "\n".join(lines) + "\n"
