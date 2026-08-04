"""Unit tests: the scoring service that fills score_snapshot.

The DAG itself is covered by tests/unit/test_scoring.py. These cover the
layer that was missing entirely — turning stored rows into MeasuredInputs and
persisting the result.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.domain.severity import DEFAULT_SEVERITY, severity_for
from topos.service.scoring import _extract_cost, _load_claim_values, _score_row, score_all


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "problem_id": "00000000-0000-0000-0000-000000000001",
        "category": "water_supply_disruption",
        "reach": 3,
        "evidence_strength": Decimal("0.90"),
        "claim_values": "[]",
    }
    base.update(overrides)
    return base


# ── Severity policy ─────────────────────────────────────────────────────────


def test_known_category_uses_its_baseline() -> None:
    assert severity_for("water_supply_disruption") == Decimal("0.70")


def test_life_safety_outranks_administrative() -> None:
    """The ordering is the product decision; pin it so an edit is deliberate."""
    assert severity_for("pedestrian_hazard_remediation_delay") > severity_for(
        "administrative_delay"
    )


def test_unknown_category_gets_the_neutral_default() -> None:
    """A new predicate must not silently rank last."""
    assert severity_for("some_new_predicate_2027") == DEFAULT_SEVERITY


# ── Input derivation ────────────────────────────────────────────────────────


def test_score_row_produces_a_full_scorecard() -> None:
    snapshot = _score_row(_row())
    assert snapshot.priority is not None
    assert snapshot.impact is not None
    assert snapshot.reach == 3
    assert snapshot.severity == Decimal("0.70")


def test_zero_sources_is_reported_as_unknown_not_as_measured_zero() -> None:
    """reach=0 would claim 'nobody reported this', which is not what an empty
    join means — it means the claims were retracted or never linked."""
    assert _score_row(_row(reach=0)).reach is None


def test_more_sources_raises_priority() -> None:
    """Corroboration is the main measured signal the ranking has."""
    low = _score_row(_row(reach=1)).priority
    high = _score_row(_row(reach=20)).priority
    assert low is not None
    assert high is not None
    assert high > low


def test_severity_baseline_separates_categories() -> None:
    hazard = _score_row(_row(category="pedestrian_hazard_remediation_delay")).priority
    admin = _score_row(_row(category="administrative_delay")).priority
    assert hazard is not None
    assert admin is not None
    assert hazard > admin


# ── Cost extraction ─────────────────────────────────────────────────────────


def test_cost_is_read_from_budget_fields() -> None:
    values = json.dumps([json.dumps({"project_budget": 372000.0})])
    assert _extract_cost(values) == Decimal("372000.00")


def test_largest_budget_wins_rather_than_the_sum() -> None:
    """One document restating the same contract must not inflate the cost."""
    values = json.dumps(
        [
            json.dumps({"contract_budget_5th": 330000.0}),
            json.dumps({"contract_budget_1st_2nd_3rd": 245919.47}),
        ]
    )
    assert _extract_cost(values) == Decimal("330000.00")


def test_no_budget_field_means_unknown_cost() -> None:
    assert _extract_cost(json.dumps([json.dumps({"description": "no money here"})])) is None


def test_non_numeric_budget_is_ignored() -> None:
    assert _extract_cost(json.dumps([json.dumps({"project_budget": "άγνωστο"})])) is None


def test_double_encoded_claim_values_are_unwrapped() -> None:
    """Claims are json.dumps'd into jsonb and no codec is registered, so the
    aggregate arrives as a list of JSON strings."""
    values = _load_claim_values(json.dumps([json.dumps({"a": 1})]))
    assert values == [{"a": 1}]


def test_malformed_claim_values_do_not_raise() -> None:
    assert _load_claim_values("not json") == []
    assert _extract_cost("not json") is None


# ── Persistence ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_all_writes_one_snapshot_per_problem() -> None:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_row(), _row(problem_id="p2")])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    result = await score_all(pool)

    assert result == {"scored": 2}
    inserts = [c for c in conn.execute.call_args_list if "score_snapshot" in c.args[0]]
    assert len(inserts) == 2


@pytest.mark.asyncio
async def test_snapshot_records_the_whole_dag_not_only_priority() -> None:
    """ARCHITECTURE.md requires every node be recorded so a ranking can be
    explained after the fact."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_row()])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    await score_all(pool)

    payload = json.loads(conn.execute.call_args.args[2])
    for node in ("priority", "impact", "urgency", "severity", "reach", "evidence_strength"):
        assert node in payload
    assert "severity_baseline_ver" in payload


@pytest.mark.asyncio
async def test_snapshot_priority_is_numeric_for_the_sql_cast() -> None:
    """recommendations.py does (scores->>'priority')::numeric — a Decimal
    serialised as a JSON string would break that cast."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_row()])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    await score_all(pool)

    payload = json.loads(conn.execute.call_args.args[2])
    assert isinstance(payload["priority"], (int, float))
