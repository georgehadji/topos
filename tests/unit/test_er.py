"""Unit tests: entity resolution blocking and feature functions.

Pure domain tests — literal inputs, literal expected outputs, no mocks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.domain.er import (
    FeatureVector,
    MentionPair,
    compute_features,
    er_decision,
    same_block,
)
from topos.service.er import _fetch_mentions, _older_first
from topos.service.er_merge import merge as _merge
from topos.service.er_merge import revert_merge

_A = "00000000-0000-0000-0000-000000000001"
_B = "00000000-0000-0000-0000-000000000002"


def test_same_block_shared_predicate() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="road_damage",
        text_a="pothole on Egnatia",
        text_b="pot hole eg nat ia",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    assert same_block(pair) is True


def test_same_block_high_text_overlap() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="water_leak",
        text_a="large pothole on Egnatia street",
        text_b="pothole on Egnatia street is large",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    # "pothole on Egnatia street large" = 5/6 ≈ 0.83 >= 0.50
    assert same_block(pair) is True


def test_same_block_low_overlap() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="water_leak",
        text_a="broken pavement",
        text_b="water pipe burst at square",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    assert same_block(pair) is False


def test_features_same_predicate_same_text() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="road_damage",
        text_a="pothole on Egnatia",
        text_b="pothole on Egnatia",
        lat_a=40.64,
        lon_a=22.94,
        lat_b=40.64,
        lon_b=22.94,
    )
    fv = compute_features(pair)
    assert fv.same_predicate == 1.0
    assert fv.text_similarity == 1.0
    assert fv.geo_proximity == 1.0
    assert fv.combined == 1.0


def test_features_different_predicates() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="water_leak",
        text_a="pothole",
        text_b="pipe burst",
        lat_a=40.64,
        lon_a=22.94,
        lat_b=40.65,
        lon_b=22.95,
    )
    fv = compute_features(pair)
    assert fv.same_predicate == 0.0
    assert fv.text_similarity == 0.0
    # ~1.5km apart → proximity ≈ 1 - 1.5/5 = 0.7
    assert 0.60 < fv.geo_proximity < 0.80
    assert 0.10 < fv.combined < 0.30


def test_features_both_no_location() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="noise",
        predicate_b="noise",
        text_a="loud music at night",
        text_b="loud music at night",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    fv = compute_features(pair)
    assert fv.geo_proximity == 1.0  # both unknown = 1.0
    assert fv.same_predicate == 1.0
    assert fv.text_similarity == 1.0


def test_features_one_location_missing() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="road_damage",
        text_a="pothole",
        text_b="pothole",
        lat_a=40.64,
        lon_a=22.94,
        lat_b=None,
        lon_b=None,
    )
    fv = compute_features(pair)
    assert fv.geo_proximity == 0.0


def test_er_decision_clear_match() -> None:

    fv = FeatureVector(same_predicate=1.0, text_similarity=1.0, geo_proximity=1.0, combined=1.0)
    verdict, _score = er_decision(fv)
    assert verdict == "match"
    assert _score >= 0.55


def test_er_decision_clear_non_match() -> None:

    fv = FeatureVector(same_predicate=0.0, text_similarity=0.0, geo_proximity=0.0, combined=0.0)
    verdict, _score = er_decision(fv)
    assert verdict == "non-match"


def test_er_decision_uncertain() -> None:

    # combined score in the uncertain band: 0.40-0.55
    fv = FeatureVector(same_predicate=1.0, text_similarity=0.3, geo_proximity=0.0, combined=0.50)
    verdict, _score = er_decision(fv, threshold=0.55)
    assert verdict == "uncertain"


# ── service/er.py: persistence-layer ER (mocked asyncpg) ──────────────────


def _mock_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    return pool


def test_older_first_picks_earlier_first_seen() -> None:
    older = {"id": _A, "first_seen": datetime(2026, 1, 1, tzinfo=UTC)}
    newer = {"id": _B, "first_seen": datetime(2026, 1, 2, tzinfo=UTC)}
    assert _older_first(newer, older) == (older, newer)
    assert _older_first(older, newer) == (older, newer)


@pytest.mark.asyncio
async def test_fetch_mentions_query_uses_correct_point_aliases() -> None:
    """ST_X is longitude, ST_Y is latitude for geometry(Point, 4326).

    Regression test for the swapped aliases: handlers.py writes
    ST_MakePoint(lon, lat), so a query reading them back must use
    ST_X(...) AS lon and ST_Y(...) AS lat, not the other way around.
    """
    conn = AsyncMock()
    conn.fetch.return_value = []
    pool = _mock_pool(conn)

    await _fetch_mentions(pool)

    sql = conn.fetch.call_args[0][0]
    assert "ST_Y(p.geom) AS lat" in sql
    assert "ST_X(p.geom) AS lon" in sql
    # Evidence text must come from linked claims, not the predicate-derived title.
    assert "string_agg(c.value::text" in sql
    assert "WHERE p.status = 'candidate'" in sql


@pytest.mark.asyncio
async def test_merge_moves_only_claims_not_already_on_winner() -> None:
    conn = AsyncMock()
    conn.fetchval.return_value = False  # loser not already merged
    moved_claim = uuid.uuid4()
    conn.fetch.return_value = [{"claim_id": moved_claim}]

    winner_id, loser_id = uuid.uuid4(), uuid.uuid4()
    await _merge(conn, winner_id=winner_id, loser_id=loser_id, decision_id=1, actor="system")

    executed = [c.args[0] for c in conn.execute.call_args_list]
    assert any("UPDATE problem_claim SET problem_id" in q for q in executed)
    assert any("UPDATE problem SET status = 'merged'" in q for q in executed)
    # Two problem_event appends: one on the loser, one on the winner.
    assert sum("INSERT INTO problem_event" in q for q in executed) == 2


@pytest.mark.asyncio
async def test_merge_is_a_noop_when_loser_already_merged() -> None:
    """Guards the transitive-merge case: A absorbs B, then A absorbs C which
    was already folded into B during the same run — the (B, C) pair must not
    re-merge or re-move claims."""
    conn = AsyncMock()
    conn.fetchval.return_value = True  # already merged

    await _merge(conn, winner_id=uuid.uuid4(), loser_id=uuid.uuid4(), decision_id=1, actor="system")

    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_revert_merge_returns_false_when_decision_not_found() -> None:
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = _mock_pool(conn)

    result = await revert_merge(pool, decision_id=999)

    assert result is False
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_revert_merge_restores_status_and_sets_reverted_by_on_original() -> None:
    conn = AsyncMock()
    a_id, b_id = uuid.uuid4(), uuid.uuid4()

    async def fetchrow_side_effect(query: str, *args: object) -> dict[str, object] | None:
        if "FROM er_decision" in query and "WHERE id = $1 AND verdict" in query:
            return {"id": 1, "a_id": a_id, "b_id": b_id}
        if "FROM problem_event" in query:
            return None  # no recorded moved-claim payload for this test
        return None

    conn.fetchrow.side_effect = fetchrow_side_effect

    async def fetchval_side_effect(query: str, *args: object) -> object:
        if "SELECT status FROM problem" in query:
            return "merged"  # a_id is the merged loser
        if "RETURNING id" in query:
            return 42  # id of the new 'reverted' decision row
        return None

    conn.fetchval.side_effect = fetchval_side_effect
    pool = _mock_pool(conn)

    result = await revert_merge(pool, decision_id=1)

    assert result is True
    executed = [c.args for c in conn.execute.call_args_list]
    restore_call = next(c for c in executed if "UPDATE problem SET status = 'candidate'" in c[0])
    assert restore_call[1] == a_id  # the loser, restored
    reverted_by_call = next(c for c in executed if "SET reverted_by" in c[0])
    assert reverted_by_call[1:] == (1, 42)  # original id, new reversal id
