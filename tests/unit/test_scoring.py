"""Unit tests: scoring DAG.

Pure domain — literal inputs, literal expected outputs, no mocks.
"""

from __future__ import annotations

from decimal import Decimal

from topos.domain.scoring import (
    MeasuredInputs,
    Weights,
    compute_impact,
    compute_priority,
    compute_urgency,
    score_problem,
    sensitivity,
)


def test_impact_with_all_inputs() -> None:
    result = compute_impact(severity=Decimal("0.8"), reach=5, weights=Weights())
    assert result is not None
    assert 0.50 < float(result) < 0.80


def test_impact_none_inputs() -> None:
    assert compute_impact(None, None) is None


def test_impact_default_weights() -> None:
    result = compute_impact(Decimal("1.0"), 10)
    assert result is not None
    assert float(result) > 0.70


def test_urgency_with_severity() -> None:
    result = compute_urgency(Decimal("-0.5"), Decimal("0.7"))
    assert result is not None
    # worsening trend + high severity = high urgency
    assert float(result) > 0.50


def test_urgency_none_inputs() -> None:
    assert compute_urgency(None, None) is None


def test_priority_with_all_inputs() -> None:
    result = compute_priority(
        Decimal("0.8"),
        Decimal("0.7"),
        Decimal("0.6"),
        Decimal("50000"),
        Decimal("0.3"),
    )
    assert result is not None
    assert 0 < float(result) <= 1.0


def test_priority_none_inputs() -> None:
    assert compute_priority(None, None, None, None, None) is None


def test_score_problem_full() -> None:
    inputs = MeasuredInputs(
        severity=Decimal("0.9"),
        reach=10,
        trend=Decimal("-0.8"),
        evidence_strength=Decimal("0.7"),
        tractability=Decimal("0.4"),
        cost=Decimal("100000"),
        leverage=Decimal("0.6"),
    )
    snap = score_problem("prob-1", inputs)
    assert snap.problem_id == "prob-1"
    assert snap.impact is not None
    assert snap.urgency is not None
    assert snap.priority is not None
    assert float(snap.priority) > 0


def test_score_problem_all_none() -> None:
    inputs = MeasuredInputs(
        severity=None,
        reach=None,
        trend=None,
        evidence_strength=None,
        tractability=None,
        cost=None,
        leverage=None,
    )
    snap = score_problem("prob-2", inputs)
    assert snap.impact is None
    assert snap.urgency is None
    assert snap.priority is None


def test_score_problem_records_all_nodes() -> None:
    inputs = MeasuredInputs(
        severity=Decimal("0.5"),
        reach=3,
        trend=Decimal("0"),
        evidence_strength=Decimal("0.6"),
        tractability=Decimal("0.7"),
        cost=Decimal("10000"),
        leverage=Decimal("0.4"),
    )
    snap = score_problem("prob-3", inputs)
    assert snap.severity == Decimal("0.5")
    assert snap.reach == 3
    assert snap.trend == Decimal("0")
    assert snap.evidence_strength == Decimal("0.6")
    assert snap.tractability == Decimal("0.7")
    assert snap.cost_eur == Decimal("10000")
    assert snap.leverage == Decimal("0.4")
    assert snap.formula_ver == "2.0.0"


def test_sensitivity_returns_expected_keys() -> None:
    inputs = MeasuredInputs(
        severity=Decimal("0.5"),
        reach=3,
        trend=Decimal("0"),
        evidence_strength=Decimal("0.5"),
        tractability=Decimal("0.5"),
        cost=Decimal("10000"),
        leverage=Decimal("0.5"),
    )
    snap = score_problem("prob-4", inputs)
    sens = sensitivity(snap)
    assert "severity" in sens
    assert "reach" in sens
    assert "tractability" in sens
    assert "cost_eur" in sens
    assert "leverage" in sens


def test_sensitivity_none_inputs_skipped() -> None:
    inputs = MeasuredInputs(
        severity=None,
        reach=None,
        trend=None,
        evidence_strength=None,
        tractability=None,
        cost=None,
        leverage=None,
    )
    snap = score_problem("prob-5", inputs)
    sens = sensitivity(snap)
    assert len(sens) == 0


def test_custom_weights() -> None:
    custom = Weights(
        severity_in_impact=Decimal("0.8"),
        reach_in_impact=Decimal("0.2"),
        impact_in_priority=Decimal("0.5"),
        urgency_in_priority=Decimal("0.5"),
        tractability_in_priority=Decimal("0"),
        cost_in_priority=Decimal("0"),
        leverage_in_priority=Decimal("0"),
    )
    inputs = MeasuredInputs(
        severity=Decimal("1.0"),
        reach=0,
        trend=Decimal("-1.0"),
        evidence_strength=None,
        tractability=Decimal("0"),
        cost=Decimal("0"),
        leverage=Decimal("0"),
    )
    snap = score_problem("prob-6", inputs, weights=custom)
    assert snap.impact is not None
    assert float(snap.impact) > 0.70
