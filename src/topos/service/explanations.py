"""Greek explanations for scores.

Slice 2.5. Uses the LlmClient to generate human-readable Greek
explanations for each score component. Pure orchestration —
the domain types are stateless.

Generates text like:
  "-H σοβαρότητα του προβλήματος είναι υψηλή (0.85/1.0) επειδή..."
  "The urgency is elevated because the trend is worsening..."
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from topos.domain.scoring import ScoreSnapshot

_EXPLANATION_PROMPT = (
    "You are a policy analyst for the constituency of A' Thessalonikis.\n"
    "Generate a concise Greek explanation (2-3 sentences) for why a\n"
    "citizen-affecting problem received the following scores.\n"
    "\n"
    "Score summary:\n"
    "- Severity: {severity}\n"
    "- Reach (independent sources): {reach}\n"
    "- Trend: {trend}\n"
    "- Evidence strength: {evidence_strength}\n"
    "- Tractability: {tractability}\n"
    "- Estimated cost: {cost}\n"
    "- Policy leverage: {leverage}\n"
    "\n"
    "Derived scores:\n"
    "- Impact: {impact}\n"
    "- Urgency: {urgency}\n"
    "- Priority: {priority}\n"
    "\n"
    "Rules:\n"
    "1. Write in Greek (el-GR).\n"
    "2. Explain WHY each score is what it is.\n"
    "3. Mention the contributing factors (e.g. 'high severity because...').\n"
    "4. Keep it factual — no speculation.\n"
    "5. Do not mention methodology or weights.\n"
    "6. Maximum 150 words.\n"
    '7. Respond with a JSON object with a single field "explanation".\n'
)


def format_score(value: Decimal | None, label: str = "") -> str:
    """Format a score value for the prompt."""
    if value is None:
        return f"{label}: unknown" if label else "unknown"
    pct = float(value) * 100
    return f"{label}: {pct:.0f}%" if label else f"{pct:.0f}%"


def build_explanation_prompt(snapshot: ScoreSnapshot) -> str:
    """Build the LLM prompt from a score snapshot."""
    return _EXPLANATION_PROMPT.format(
        severity=format_score(snapshot.severity, "Severity"),
        reach=f"{snapshot.reach} independent sources" if snapshot.reach else "unknown",
        trend=format_score(snapshot.trend, "Trend"),
        evidence_strength=format_score(snapshot.evidence_strength, "Evidence"),
        tractability=format_score(snapshot.tractability, "Tractability"),
        cost=f"EUR {snapshot.cost_eur:,.0f}" if snapshot.cost_eur else "unknown",
        leverage=format_score(snapshot.leverage, "Leverage"),
        impact=format_score(snapshot.impact, "Impact"),
        urgency=format_score(snapshot.urgency, "Urgency"),
        priority=format_score(snapshot.priority, "Priority"),
    )


async def generate_explanation(
    llm_client: Any,
    snapshot: ScoreSnapshot,
    *,
    model: str = "mistralai/mistral-large-2512",
) -> str:
    """Generate a Greek explanation for a score snapshot.

    Returns the explanation text, or an empty string on failure.
    """
    prompt = build_explanation_prompt(snapshot)

    try:
        result = await llm_client.complete(
            prompt=prompt,
            model=model,
            response_format={"type": "json_object"},
        )
    except Exception:
        return ""

    try:
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        import json  # noqa: PLC0415

        parsed = json.loads(content)
        return str(parsed.get("explanation", ""))
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return ""
