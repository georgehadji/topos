"""Scoring DAG: severity, impact, urgency, priority.

Pure domain logic. No IO.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MeasuredInputs:
    """Raw measured inputs for one problem/mention. None = unknown."""

    severity: Decimal | None  # 0.0-1.0
    reach: int | None  # count of independent sources (not reports)
    trend: Decimal | None  # -1.0 worsening, 0.0 stable, +1.0 improving
    evidence_strength: Decimal | None  # 0.0-1.0
    tractability: Decimal | None  # 0.0-1.0 how fixable
    cost: Decimal | None  # estimated cost in EUR, or None
    leverage: Decimal | None  # 0.0-1.0 policy leverage


@dataclass(frozen=True, slots=True)
class ScoreSnapshot:
    """The entire DAG output for one problem. Every node recorded."""

    problem_id: str
    impact: Decimal | None
    urgency: Decimal | None
    priority: Decimal | None
    severity: Decimal | None
    reach: int | None
    trend: Decimal | None
    evidence_strength: Decimal | None
    tractability: Decimal | None
    cost_eur: Decimal | None
    leverage: Decimal | None
    formula_ver: str = "2.0.0"


@dataclass(frozen=True, slots=True)
class Weights:
    """Named weights. Each weight in [0.0, 1.0]."""

    severity_in_impact: Decimal = Decimal("0.6")
    reach_in_impact: Decimal = Decimal("0.4")
    trend_in_urgency: Decimal = Decimal("0.3")
    severity_in_urgency: Decimal = Decimal("0.5")
    deadline_in_urgency: Decimal = Decimal("0.2")
    impact_in_priority: Decimal = Decimal("0.35")
    urgency_in_priority: Decimal = Decimal("0.30")
    tractability_in_priority: Decimal = Decimal("0.15")
    cost_in_priority: Decimal = Decimal("0.10")
    leverage_in_priority: Decimal = Decimal("0.10")
    formula_ver: str = "2.0.0"


# ── The DAG ──────────────────────────────────────────────────────────────────


def compute_impact(
    severity: Decimal | None, reach: int | None, weights: Weights | None = None
) -> Decimal | None:
    """impact = f(severity, reach)"""
    if severity is None and reach is None:
        return None
    w = weights or Weights()
    s = severity or Decimal("0")
    r = _normalised_reach(reach)
    return (w.severity_in_impact * s + w.reach_in_impact * r).quantize(Decimal("0.01"))


def compute_urgency(
    trend: Decimal | None,
    severity: Decimal | None,
    weights: Weights | None = None,
) -> Decimal | None:
    """urgency = f(trend, severity, deadlines)"""
    if trend is None and severity is None:
        return None
    w = weights or Weights()
    t = _invert_trend(trend)
    s = severity or Decimal("0")
    return (w.trend_in_urgency * t + w.severity_in_urgency * s).quantize(Decimal("0.01"))


def compute_priority(
    impact: Decimal | None,
    urgency: Decimal | None,
    tractability: Decimal | None,
    cost: Decimal | None,
    leverage: Decimal | None,
    weights: Weights | None = None,
) -> Decimal | None:
    """priority = f(impact, urgency, tractability, cost, leverage)"""
    if impact is None and urgency is None:
        return None
    w = weights or Weights()
    i = impact or Decimal("0")
    u = urgency or Decimal("0")
    t = tractability or Decimal("0")
    c = _invert_cost(cost)
    lv = leverage or Decimal("0")
    return (
        w.impact_in_priority * i
        + w.urgency_in_priority * u
        + w.tractability_in_priority * t
        + w.cost_in_priority * c
        + w.leverage_in_priority * lv
    ).quantize(Decimal("0.01"))


def score_problem(
    problem_id: str,
    inputs: MeasuredInputs,
    weights: Weights | None = None,
) -> ScoreSnapshot:
    """Run the full scoring DAG for one problem."""
    w = weights or Weights()
    impact = compute_impact(inputs.severity, inputs.reach, w)
    urgency = compute_urgency(inputs.trend, inputs.severity, w)
    priority = compute_priority(
        impact, urgency, inputs.tractability, inputs.cost, inputs.leverage, w
    )
    return ScoreSnapshot(
        problem_id=problem_id,
        impact=impact,
        urgency=urgency,
        priority=priority,
        severity=inputs.severity,
        reach=inputs.reach,
        trend=inputs.trend,
        evidence_strength=inputs.evidence_strength,
        tractability=inputs.tractability,
        cost_eur=inputs.cost,
        leverage=inputs.leverage,
        formula_ver=w.formula_ver,
    )


def sensitivity(
    snapshot: ScoreSnapshot,
    delta: Decimal = Decimal("0.1"),
) -> dict[str, Decimal]:
    """Compute how much priority changes when each input nudges by delta."""
    base = snapshot.priority or Decimal("0")
    results: dict[str, Decimal] = {}

    for field in ("severity", "reach", "trend", "tractability", "cost_eur", "leverage"):
        orig = _get_field(snapshot, field)
        if orig is None:
            continue
        modified = _build_modified(snapshot, field, orig, delta)
        new_priority = compute_priority(
            compute_impact(modified.severity, modified.reach),
            compute_urgency(modified.trend, modified.severity),
            modified.tractability, modified.cost_eur, modified.leverage,
        ) or Decimal("0")
        results[field] = (new_priority - base).quantize(Decimal("0.01"))

    return results


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalised_reach(reach: int | None) -> Decimal:
    """Normalise reach count to [0, 1] using log scale."""
    if reach is None or reach <= 0:
        return Decimal("0")
    return Decimal(str(min(1.0, math.log10(reach + 1) / 2.0))).quantize(Decimal("0.01"))


def _invert_trend(trend: Decimal | None) -> Decimal:
    """Convert trend to urgency contribution."""
    if trend is None:
        return Decimal("0")
    half = Decimal("0.5")
    t = float(half - trend / 2)
    return Decimal(str(max(0.0, min(1.0, t)))).quantize(Decimal("0.01"))


def _invert_cost(cost: Decimal | None) -> Decimal:
    """Higher cost -> lower score (cheaper fixes are more tractable)."""
    if cost is None:
        return Decimal("0.5")
    return Decimal(str(max(0.0, 1.0 - math.log10(float(cost + 1)) / 6.0))).quantize(Decimal("0.01"))


def _get_field(snapshot: ScoreSnapshot, field: str) -> Decimal | int | None:
    mapping: dict[str, Decimal | int | None] = {
        "severity": snapshot.severity,
        "reach": Decimal(str(snapshot.reach)) if snapshot.reach is not None else None,
        "trend": snapshot.trend,
        "tractability": snapshot.tractability,
        "cost_eur": snapshot.cost_eur,
        "leverage": snapshot.leverage,
    }
    return mapping.get(field)


def _adjust_reach(reach: int | None, delta: Decimal) -> int | None:
    if reach is None:
        return None
    return max(0, reach + int(delta * 10))


def _build_modified(
    snapshot: ScoreSnapshot, field: str, orig: Decimal | int, delta: Decimal
) -> ScoreSnapshot:
    """Return a new snapshot with one field increased by delta."""
    adj = orig + delta if isinstance(orig, Decimal) else Decimal(str(orig + int(delta * 10)))
    if field == "reach":
        return ScoreSnapshot(
            problem_id=snapshot.problem_id,
            severity=snapshot.severity, reach=_adjust_reach(snapshot.reach, delta),
            trend=snapshot.trend, evidence_strength=snapshot.evidence_strength,
            tractability=snapshot.tractability, cost_eur=snapshot.cost_eur,
            leverage=snapshot.leverage,
            impact=snapshot.impact, urgency=snapshot.urgency,
            priority=snapshot.priority,
        )
    return ScoreSnapshot(
        problem_id=snapshot.problem_id,
        severity=adj if field == "severity" else snapshot.severity,
        reach=snapshot.reach,
        trend=adj if field == "trend" else snapshot.trend,
        evidence_strength=snapshot.evidence_strength,
        tractability=adj if field == "tractability" else snapshot.tractability,
        cost_eur=adj if field == "cost_eur" else snapshot.cost_eur,
        leverage=adj if field == "leverage" else snapshot.leverage,
        impact=snapshot.impact, urgency=snapshot.urgency,
        priority=snapshot.priority,
    )
